from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text, func
from datetime import datetime, timedelta, timezone
from app import db
from models import EventsEnriched, AlertEvent, AlertRule, SystemHealth

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    """
    Main dashboard page
    """
    return render_template('dashboard.html')

@dashboard_bp.route('/events')
@login_required
def events():
    """
    Events page
    """
    return render_template('events.html')

@dashboard_bp.route('/alerts')
@login_required
def alerts():
    """
    Alerts page
    """
    return render_template('alerts.html')

@dashboard_bp.route('/api/dashboard/stats')
@login_required
def dashboard_stats():
    """
    Get dashboard statistics
    """
    try:
        # Get stats for last 24 hours
        start_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        # Total events
        total_events = EventsEnriched.query.filter(
            EventsEnriched.ts >= start_time
        ).count()
        
        # Events by type
        events_by_type = db.session.execute(text("""
            SELECT event_type, COUNT(*) as count
            FROM events_enriched 
            WHERE ts >= :start_time
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        """), {'start_time': start_time}).fetchall()
        
        # Events by hour for chart
        events_by_hour = db.session.execute(text("""
            SELECT 
                DATE_TRUNC('hour', ts) as hour,
                COUNT(*) as count
            FROM events_enriched 
            WHERE ts >= :start_time
            GROUP BY DATE_TRUNC('hour', ts)
            ORDER BY hour
        """), {'start_time': start_time}).fetchall()
        
        # Top source hosts
        top_hosts = db.session.execute(text("""
            SELECT host, COUNT(*) as count
            FROM events_enriched 
            WHERE ts >= :start_time AND host IS NOT NULL
            GROUP BY host
            ORDER BY count DESC
            LIMIT 10
        """), {'start_time': start_time}).fetchall()
        
        # Recent alerts
        recent_alerts = AlertEvent.query\
            .join(AlertRule)\
            .filter(AlertEvent.triggered_at >= start_time)\
            .order_by(AlertEvent.triggered_at.desc())\
            .limit(5)\
            .all()
        
        return jsonify({
            'total_events': total_events,
            'events_by_type': [{'type': row.event_type, 'count': row.count} for row in events_by_type],
            'events_by_hour': [{'hour': row.hour.isoformat(), 'count': row.count} for row in events_by_hour],
            'top_hosts': [{'host': row.host, 'count': row.count} for row in top_hosts],
            'recent_alerts': [{
                'id': alert.id,
                'rule_name': alert.rule.name,
                'triggered_at': alert.triggered_at.isoformat(),
                'event_count': alert.event_count
            } for alert in recent_alerts]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/events')
@login_required
def api_events():
    """
    Get events with filtering and pagination
    """
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        event_type = request.args.get('event_type')
        source = request.args.get('source')
        host = request.args.get('host')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        search = request.args.get('search')
        
        # Build query
        query = EventsEnriched.query
        
        if event_type:
            query = query.filter(EventsEnriched.event_type == event_type)
        
        if source:
            query = query.filter(EventsEnriched.source == source)
        
        if host:
            query = query.filter(EventsEnriched.host == host)
        
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            query = query.filter(EventsEnriched.ts >= start_dt)
        
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            query = query.filter(EventsEnriched.ts <= end_dt)
        
        if search:
            query = query.filter(EventsEnriched.message.contains(search))
        
        # Order by timestamp descending
        query = query.order_by(EventsEnriched.ts.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        events = []
        for event in pagination.items:
            events.append({
                'id': event.id,
                'ts': event.ts.isoformat(),
                'source': event.source,
                'host': event.host,
                'event_type': event.event_type,
                'message': event.message,
                'enrichment': event.enrichment,
                'metadata': event.event_metadata
            })
        
        return jsonify({
            'events': events,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': pagination.page,
            'per_page': pagination.per_page
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/alerts')
@login_required
def api_alerts():
    """
    Get alerts with pagination
    """
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        pagination = AlertEvent.query\
            .join(AlertRule)\
            .order_by(AlertEvent.triggered_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        alerts = []
        for alert in pagination.items:
            alerts.append({
                'id': alert.id,
                'rule_name': alert.rule.name,
                'rule_description': alert.rule.description,
                'triggered_at': alert.triggered_at.isoformat(),
                'event_count': alert.event_count,
                'details': alert.details,
                'email_sent': alert.email_sent
            })
        
        return jsonify({
            'alerts': alerts,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': pagination.page
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/system/health')
@login_required
def system_health():
    """
    Get system health status
    """
    try:
        # Get latest health metrics for each component
        latest_health = db.session.execute(text("""
            SELECT DISTINCT ON (component) 
                component, status, metrics, timestamp
            FROM system_health 
            ORDER BY component, timestamp DESC
        """)).fetchall()
        
        health_data = []
        for row in latest_health:
            health_data.append({
                'component': row.component,
                'status': row.status,
                'metrics': row.metrics,
                'timestamp': row.timestamp.isoformat()
            })
        
        return jsonify({'health': health_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
