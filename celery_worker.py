"""
Celery Worker for SIEM Background Tasks
Handles parsing, enrichment, alerting, and other background processing
"""

import os
import json
import logging
from datetime import datetime, timezone

from celery import Celery, Task
from app import create_app, db
from models import EventsRaw, EventsEnriched, AlertRule, AlertEvent
from services.parser import EventParser
from services.enrichment import EnrichmentService
from services.alert_engine import AlertEngine
from services.rabbitmq_client import RabbitMQClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app context
flask_app = create_app()

# Configure Celery
celery = Celery(__name__)
celery.conf.update(
    broker_url=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    result_backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_routes={
        'parse_raw_event': {'queue': 'parsing'},
        'enrich_event': {'queue': 'enrichment'},
        'evaluate_alert_rules': {'queue': 'alerting'},
        'cleanup_old_events': {'queue': 'maintenance'},
    }
)

class ContextTask(Task):
    """
    Custom Celery task that provides Flask application context
    """
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask

@celery.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def parse_raw_event(self, raw_event_data):
    """
    Parse a raw event and create normalized event
    
    Args:
        raw_event_data: Dictionary containing raw event information
    """
    try:
        logger.info(f"Parsing raw event: {raw_event_data.get('raw_id')}")
        
        parser = EventParser()
        parsed_event = parser.parse_message(raw_event_data)
        normalized_event = parser.normalize_fields(parsed_event)
        
        # Add source information
        normalized_event['source'] = raw_event_data.get('source')
        normalized_event['host'] = raw_event_data.get('host')
        
        # Trigger enrichment
        enrich_event.delay(raw_event_data.get('raw_id'), normalized_event)
        
        logger.info(f"Successfully parsed event {raw_event_data.get('raw_id')}")
        
    except Exception as e:
        logger.error(f"Error parsing event {raw_event_data.get('raw_id')}: {e}")
        raise

@celery.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def enrich_event(self, raw_id, parsed_event):
    """
    Enrich a parsed event with additional context
    
    Args:
        raw_id: ID of the raw event
        parsed_event: Parsed event data
    """
    try:
        logger.info(f"Enriching event: {raw_id}")
        
        enrichment_service = EnrichmentService()
        enriched_event = enrichment_service.enrich_event(raw_id, parsed_event)
        
        logger.info(f"Successfully enriched event {enriched_event.id}")
        
    except Exception as e:
        logger.error(f"Error enriching event {raw_id}: {e}")
        raise

@celery.task
def evaluate_alert_rules():
    """
    Evaluate all active alert rules
    """
    try:
        logger.info("Evaluating alert rules")
        
        alert_engine = AlertEngine()
        alert_engine.evaluate_rules()
        
        logger.info("Alert rule evaluation completed")
        
    except Exception as e:
        logger.error(f"Error evaluating alert rules: {e}")
        raise

@celery.task
def cleanup_old_events():
    """
    Clean up old events based on retention policy
    """
    try:
        logger.info("Starting event cleanup")
        
        # Get retention settings
        days_to_keep_hot = int(os.environ.get('DAYS_TO_KEEP_HOT', '7'))
        days_to_keep_archive = int(os.environ.get('DAYS_TO_KEEP_ARCHIVE', '365'))
        
        from sqlalchemy import text
        from datetime import timedelta
        
        # Archive old enriched events (move to archive table or compress)
        archive_cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep_hot)
        
        # Delete very old events
        delete_cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep_archive)
        
        # Count events to be archived/deleted
        events_to_archive = db.session.execute(text("""
            SELECT COUNT(*) FROM events_enriched 
            WHERE ts < :archive_cutoff AND ts >= :delete_cutoff
        """), {
            'archive_cutoff': archive_cutoff,
            'delete_cutoff': delete_cutoff
        }).scalar()
        
        events_to_delete = db.session.execute(text("""
            SELECT COUNT(*) FROM events_enriched 
            WHERE ts < :delete_cutoff
        """), {'delete_cutoff': delete_cutoff}).scalar()
        
        logger.info(f"Events to archive: {events_to_archive}, Events to delete: {events_to_delete}")
        
        # Delete old events (implement archiving first in production)
        if events_to_delete > 0:
            db.session.execute(text("""
                DELETE FROM events_enriched WHERE ts < :delete_cutoff
            """), {'delete_cutoff': delete_cutoff})
            
            db.session.execute(text("""
                DELETE FROM events_raw WHERE received_at < :delete_cutoff
            """), {'delete_cutoff': delete_cutoff})
            
            db.session.commit()
            
            logger.info(f"Deleted {events_to_delete} old events")
        
        # Clean up old alert events
        alert_retention_days = 90
        alert_cutoff = datetime.now(timezone.utc) - timedelta(days=alert_retention_days)
        
        old_alerts = db.session.execute(text("""
            SELECT COUNT(*) FROM alert_events WHERE triggered_at < :cutoff
        """), {'cutoff': alert_cutoff}).scalar()
        
        if old_alerts > 0:
            db.session.execute(text("""
                DELETE FROM alert_events WHERE triggered_at < :cutoff
            """), {'cutoff': alert_cutoff})
            db.session.commit()
            
            logger.info(f"Deleted {old_alerts} old alert events")
        
        logger.info("Event cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise

@celery.task
def system_health_check():
    """
    Perform system health checks and update health status
    """
    try:
        logger.info("Performing system health check")
        
        from models import SystemHealth
        import psutil
        
        # Check system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Check database connectivity
        try:
            db.session.execute(text("SELECT 1")).scalar()
            db_status = 'healthy'
        except Exception:
            db_status = 'critical'
        
        # Check recent event ingestion
        recent_events = db.session.execute(text("""
            SELECT COUNT(*) FROM events_raw 
            WHERE received_at > NOW() - INTERVAL '5 minutes'
        """)).scalar()
        
        ingestion_status = 'healthy' if recent_events > 0 else 'warning'
        
        # Determine overall status
        if db_status == 'critical' or cpu_percent > 90 or memory.percent > 90:
            overall_status = 'critical'
        elif cpu_percent > 70 or memory.percent > 70 or ingestion_status == 'warning':
            overall_status = 'warning'
        else:
            overall_status = 'healthy'
        
        # Store health data
        health_record = SystemHealth(
            component='system',
            status=overall_status,
            metrics={
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
                'recent_events': recent_events,
                'database_status': db_status,
                'ingestion_status': ingestion_status
            }
        )
        
        db.session.add(health_record)
        db.session.commit()
        
        logger.info(f"System health check completed: {overall_status}")
        
        # Send alert if critical
        if overall_status == 'critical':
            send_health_alert.delay({
                'status': overall_status,
                'component': 'system',
                'metrics': health_record.metrics,
                'timestamp': health_record.timestamp
            })
        
    except Exception as e:
        logger.error(f"Error during health check: {e}")
        raise

@celery.task
def send_health_alert(health_data):
    """
    Send health alert notification
    
    Args:
        health_data: Dictionary containing health information
    """
    try:
        from utils.email_sender import get_email_sender
        
        # Get admin email addresses
        admin_emails = os.environ.get('ADMIN_EMAILS', 'admin@siem.local').split(',')
        admin_emails = [email.strip() for email in admin_emails if email.strip()]
        
        if admin_emails:
            email_sender = get_email_sender()
            email_sender.send_system_health_email(admin_emails, health_data)
            logger.info("Health alert sent to administrators")
        
    except Exception as e:
        logger.error(f"Error sending health alert: {e}")

@celery.task
def process_rabbitmq_queue(queue_name):
    """
    Process messages from a specific RabbitMQ queue
    
    Args:
        queue_name: Name of the queue to process
    """
    try:
        logger.info(f"Processing RabbitMQ queue: {queue_name}")
        
        rabbitmq = RabbitMQClient()
        
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body)
                
                # Process the message based on queue type
                if 'raw' in queue_name:
                    parse_raw_event.delay(message)
                
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                logger.error(f"Error processing message from {queue_name}: {e}")
                # Reject message and requeue for retry
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        
        rabbitmq.consume_messages(queue_name, callback)
        
    except Exception as e:
        logger.error(f"Error processing queue {queue_name}: {e}")
        raise

# Periodic tasks setup
from celery.schedules import crontab

celery.conf.beat_schedule = {
    'evaluate-alert-rules': {
        'task': 'evaluate_alert_rules',
        'schedule': 60.0,  # Every minute
    },
    'system-health-check': {
        'task': 'system_health_check',
        'schedule': 300.0,  # Every 5 minutes
    },
    'cleanup-old-events': {
        'task': 'cleanup_old_events',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}

if __name__ == '__main__':
    celery.start()
