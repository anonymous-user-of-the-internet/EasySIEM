from datetime import datetime, timezone
from sqlalchemy import text, Index
from app import db
from flask_login import UserMixin

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)

class EventsRaw(db.Model):
    __tablename__ = 'events_raw'
    
    id = db.Column(db.BigInteger, primary_key=True)
    received_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    source = db.Column(db.Text, nullable=False)
    host = db.Column(db.Text)
    payload = db.Column(db.JSON, nullable=False)
    
    # Add index for better query performance
    __table_args__ = (
        Index('idx_events_raw_received_at', 'received_at'),
        Index('idx_events_raw_source', 'source'),
    )

class EventsEnriched(db.Model):
    __tablename__ = 'events_enriched'
    
    id = db.Column(db.BigInteger, primary_key=True)
    raw_id = db.Column(db.BigInteger, db.ForeignKey('events_raw.id'))
    ts = db.Column(db.DateTime, nullable=False)
    source = db.Column(db.Text, nullable=False)
    host = db.Column(db.Text)
    event_type = db.Column(db.Text)
    message = db.Column(db.Text)
    enrichment = db.Column(db.JSON)  # GeoIP, threat intel, etc.
    event_metadata = db.Column(db.JSON)    # parsed fields
    
    # Relationships
    raw_event = db.relationship('EventsRaw', backref='enriched_events')
    
    # Indexes for better performance
    __table_args__ = (
        Index('idx_events_enriched_ts_desc', 'ts', postgresql_using='btree'),
        Index('idx_events_enriched_event_type', 'event_type'),
        Index('idx_events_enriched_source', 'source'),

    )

class AlertRule(db.Model):
    __tablename__ = 'alert_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    rule_type = db.Column(db.String(50), nullable=False)  # threshold, correlation
    filter_query = db.Column(db.Text, nullable=False)
    threshold_count = db.Column(db.Integer)
    time_window_minutes = db.Column(db.Integer)
    email_recipients = db.Column(db.JSON)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    creator = db.relationship('User', backref='alert_rules')

class AlertEvent(db.Model):
    __tablename__ = 'alert_events'
    
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('alert_rules.id'), nullable=False)
    triggered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    event_count = db.Column(db.Integer)
    details = db.Column(db.JSON)
    email_sent = db.Column(db.Boolean, default=False)
    
    # Relationships
    rule = db.relationship('AlertRule', backref='triggered_events')

class Dashboard(db.Model):
    __tablename__ = 'dashboards'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    layout_config = db.Column(db.JSON)  # Widget configuration
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_public = db.Column(db.Boolean, default=False)
    
    # Relationships
    creator = db.relationship('User', backref='dashboards')

class SystemHealth(db.Model):
    __tablename__ = 'system_health'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    component = db.Column(db.String(100), nullable=False)  # ingestion, parser, enricher
    status = db.Column(db.String(20), nullable=False)  # healthy, warning, critical
    metrics = db.Column(db.JSON)  # CPU, memory, queue depth, etc.
    
    __table_args__ = (
        Index('idx_system_health_timestamp', 'timestamp'),
        Index('idx_system_health_component', 'component'),
    )
