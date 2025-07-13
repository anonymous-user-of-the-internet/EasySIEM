from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from services.ingestion import IngestionService, authenticate_agent
from services.alert_engine import AlertEngine
from models import AlertRule
from app import db

api_bp = Blueprint('api', __name__)

@api_bp.route('/ingest', methods=['POST'])
def ingest():
    """
    Ingest events from agents
    """
    # Check authentication
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    if not authenticate_agent(token):
        return jsonify({'error': 'Invalid agent token'}), 401
    
    # Validate request data
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Empty request body'}), 400
    
    # Ingest the event
    ingestion_service = IngestionService()
    result, status_code = ingestion_service.ingest_event(data)
    
    return jsonify(result), status_code

@api_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint
    """
    return jsonify({
        'status': 'healthy',
        'service': 'SIEM API',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@api_bp.route('/stats', methods=['GET'])
@login_required
def stats():
    """
    Get ingestion statistics
    """
    ingestion_service = IngestionService()
    result, status_code = ingestion_service.get_ingestion_stats()
    
    return jsonify(result), status_code

@api_bp.route('/alert-rules', methods=['GET', 'POST'])
@login_required
def alert_rules():
    """
    Manage alert rules
    """
    if request.method == 'GET':
        rules = AlertRule.query.all()
        return jsonify({
            'rules': [{
                'id': rule.id,
                'name': rule.name,
                'description': rule.description,
                'rule_type': rule.rule_type,
                'filter_query': rule.filter_query,
                'threshold_count': rule.threshold_count,
                'time_window_minutes': rule.time_window_minutes,
                'email_recipients': rule.email_recipients,
                'is_active': rule.is_active,
                'created_at': rule.created_at.isoformat()
            } for rule in rules]
        })
    
    elif request.method == 'POST':
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'rule_type', 'filter_query', 'threshold_count', 'time_window_minutes']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        try:
            alert_engine = AlertEngine()
            rule = alert_engine.create_rule(
                name=data['name'],
                description=data.get('description', ''),
                rule_type=data['rule_type'],
                filter_query=data['filter_query'],
                threshold_count=data['threshold_count'],
                time_window_minutes=data['time_window_minutes'],
                email_recipients=data.get('email_recipients', []),
                created_by=current_user.id
            )
            
            return jsonify({
                'message': 'Alert rule created successfully',
                'rule_id': rule.id
            }), 201
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@api_bp.route('/alert-rules/<int:rule_id>', methods=['DELETE', 'PUT'])
@login_required
def alert_rule_detail(rule_id):
    """
    Manage individual alert rule
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    rule = AlertRule.query.get_or_404(rule_id)
    
    if request.method == 'DELETE':
        try:
            db.session.delete(rule)
            db.session.commit()
            return jsonify({'message': 'Alert rule deleted successfully'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'PUT':
        data = request.get_json()
        
        try:
            # Update rule fields
            if 'name' in data:
                rule.name = data['name']
            if 'description' in data:
                rule.description = data['description']
            if 'filter_query' in data:
                rule.filter_query = data['filter_query']
            if 'threshold_count' in data:
                rule.threshold_count = data['threshold_count']
            if 'time_window_minutes' in data:
                rule.time_window_minutes = data['time_window_minutes']
            if 'email_recipients' in data:
                rule.email_recipients = data['email_recipients']
            if 'is_active' in data:
                rule.is_active = data['is_active']
            
            db.session.commit()
            
            return jsonify({'message': 'Alert rule updated successfully'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

@api_bp.route('/search', methods=['POST'])
@login_required
def search():
    """
    Advanced search endpoint
    """
    data = request.get_json()
    
    try:
        from sqlalchemy import text
        
        # Build search query
        query_parts = []
        params = {}
        
        if data.get('event_type'):
            query_parts.append("event_type = :event_type")
            params['event_type'] = data['event_type']
        
        if data.get('source'):
            query_parts.append("source = :source")
            params['source'] = data['source']
        
        if data.get('start_time'):
            query_parts.append("ts >= :start_time")
            params['start_time'] = data['start_time']
        
        if data.get('end_time'):
            query_parts.append("ts <= :end_time")
            params['end_time'] = data['end_time']
        
        if data.get('search_text'):
            query_parts.append("message ILIKE :search_text")
            params['search_text'] = f"%{data['search_text']}%"
        
        where_clause = " AND ".join(query_parts) if query_parts else "1=1"
        
        # Execute search
        sql = f"""
            SELECT id, ts, source, host, event_type, message, enrichment, event_metadata
            FROM events_enriched 
            WHERE {where_clause}
            ORDER BY ts DESC
            LIMIT :limit
        """
        
        params['limit'] = data.get('limit', 100)
        
        result = db.session.execute(text(sql), params).fetchall()
        
        events = []
        for row in result:
            events.append({
                'id': row.id,
                'ts': row.ts.isoformat(),
                'source': row.source,
                'host': row.host,
                'event_type': row.event_type,
                'message': row.message,
                'enrichment': row.enrichment,
                'metadata': row.metadata
            })
        
        return jsonify({'events': events, 'total': len(events)})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
