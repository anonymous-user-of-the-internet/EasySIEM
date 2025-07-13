import json
import logging
from datetime import datetime, timezone
from flask import request, jsonify, current_app
from app import db
from models import EventsRaw
from services.rabbitmq_client import RabbitMQClient

logger = logging.getLogger(__name__)

class IngestionService:
    def __init__(self):
        self.rabbitmq = RabbitMQClient()
    
    def ingest_event(self, data):
        """
        Ingest a raw event from an agent
        """
        try:
            # Validate required fields
            if not data.get('source') or not data.get('raw'):
                return {'error': 'Missing required fields: source, raw'}, 400
            
            # Create raw event record
            raw_event = EventsRaw(
                received_at=datetime.now(timezone.utc),
                source=data['source'],
                host=data.get('host', 'unknown'),
                payload={
                    'timestamp': data.get('timestamp'),
                    'raw': data['raw'],
                    'agent_info': data.get('agent_info', {})
                }
            )
            
            db.session.add(raw_event)
            db.session.commit()
            
            # Send to RabbitMQ for processing
            message = {
                'raw_id': raw_event.id,
                'source': raw_event.source,
                'host': raw_event.host,
                'payload': raw_event.payload
            }
            
            routing_key = f"raw.{raw_event.source}"
            self.rabbitmq.publish_message('logs.raw', routing_key, message)
            
            logger.info(f"Ingested event {raw_event.id} from {raw_event.source}")
            
            return {'message': 'Event ingested successfully', 'event_id': raw_event.id}, 201
            
        except Exception as e:
            logger.error(f"Error ingesting event: {str(e)}")
            db.session.rollback()
            return {'error': 'Failed to ingest event'}, 500
    
    def get_ingestion_stats(self):
        """
        Get ingestion statistics
        """
        try:
            # Events in last 24 hours
            from sqlalchemy import func, text
            
            result = db.session.execute(text("""
                SELECT 
                    source,
                    COUNT(*) as count,
                    MAX(received_at) as last_received
                FROM events_raw 
                WHERE received_at > NOW() - INTERVAL '24 hours'
                GROUP BY source
                ORDER BY count DESC
            """)).fetchall()
            
            stats = []
            for row in result:
                stats.append({
                    'source': row.source,
                    'count': row.count,
                    'last_received': row.last_received.isoformat() if row.last_received else None
                })
            
            return {'stats': stats}, 200
            
        except Exception as e:
            logger.error(f"Error getting ingestion stats: {str(e)}")
            return {'error': 'Failed to get stats'}, 500

def authenticate_agent(token):
    """
    Authenticate agent API token
    """
    expected_token = current_app.config.get('AGENT_API_TOKEN', 'siem-agent-token-change-me')
    return token == expected_token
