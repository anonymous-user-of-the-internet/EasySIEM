import logging
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import text
from app import db
from models import AlertRule, AlertEvent, EventsEnriched
from utils.email_sender import EmailSender

logger = logging.getLogger(__name__)

class AlertEngine:
    def __init__(self):
        self.email_sender = EmailSender()
    
    def evaluate_rules(self):
        """
        Evaluate all active alert rules
        """
        rules = AlertRule.query.filter_by(is_active=True).all()
        
        for rule in rules:
            try:
                self._evaluate_rule(rule)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.id}: {str(e)}")
    
    def _evaluate_rule(self, rule):
        """
        Evaluate a single alert rule
        """
        if rule.rule_type == 'threshold':
            self._evaluate_threshold_rule(rule)
        elif rule.rule_type == 'correlation':
            self._evaluate_correlation_rule(rule)
    
    def _evaluate_threshold_rule(self, rule):
        """
        Evaluate a threshold-based alert rule
        """
        try:
            # Build SQL query based on rule filter
            time_window = timedelta(minutes=rule.time_window_minutes)
            start_time = datetime.now(timezone.utc) - time_window
            
            # Parse filter query and build WHERE clause
            where_clause = self._build_where_clause(rule.filter_query)
            
            query = text(f"""
                SELECT COUNT(*) as event_count
                FROM events_enriched 
                WHERE ts >= :start_time 
                AND ({where_clause})
            """)
            
            result = db.session.execute(query, {'start_time': start_time}).fetchone()
            event_count = result.event_count
            
            if event_count >= rule.threshold_count:
                # Check if we already alerted recently to avoid spam
                recent_alert = AlertEvent.query.filter_by(rule_id=rule.id)\
                    .filter(AlertEvent.triggered_at > start_time)\
                    .first()
                
                if not recent_alert:
                    self._trigger_alert(rule, event_count)
                    
        except Exception as e:
            logger.error(f"Error evaluating threshold rule {rule.id}: {str(e)}")
    
    def _evaluate_correlation_rule(self, rule):
        """
        Evaluate a correlation-based alert rule
        TODO: Implement more sophisticated correlation logic
        """
        logger.info(f"Correlation rule evaluation not yet implemented for rule {rule.id}")
    
    def _build_where_clause(self, filter_query):
        """
        Build SQL WHERE clause from filter query
        Simple implementation - in production, use a proper query parser
        """
        # Basic filter parsing - extend as needed
        if 'event_type=' in filter_query:
            # Extract event_type value
            import re
            match = re.search(r'event_type="([^"]+)"', filter_query)
            if match:
                event_type = match.group(1)
                return f"event_type = '{event_type}'"
        
        # Default fallback
        return "1=1"
    
    def _trigger_alert(self, rule, event_count):
        """
        Trigger an alert for a rule
        """
        try:
            # Create alert event record
            alert_event = AlertEvent(
                rule_id=rule.id,
                triggered_at=datetime.now(timezone.utc),
                event_count=event_count,
                details={
                    'rule_name': rule.name,
                    'threshold': rule.threshold_count,
                    'actual_count': event_count,
                    'time_window': rule.time_window_minutes
                }
            )
            
            db.session.add(alert_event)
            db.session.commit()
            
            # Send email notification
            if rule.email_recipients:
                self._send_alert_email(rule, alert_event)
                alert_event.email_sent = True
                db.session.commit()
            
            logger.info(f"Alert triggered for rule {rule.name}: {event_count} events")
            
        except Exception as e:
            logger.error(f"Error triggering alert for rule {rule.id}: {str(e)}")
            db.session.rollback()
    
    def _send_alert_email(self, rule, alert_event):
        """
        Send email notification for alert
        """
        try:
            subject = f"SIEM Alert: {rule.name}"
            
            body = f"""
            Alert Details:
            
            Rule: {rule.name}
            Description: {rule.description or 'N/A'}
            
            Threshold: {rule.threshold_count} events in {rule.time_window_minutes} minutes
            Actual Count: {alert_event.event_count} events
            
            Triggered At: {alert_event.triggered_at}
            
            Please investigate this security event.
            """
            
            self.email_sender.send_email(
                recipients=rule.email_recipients,
                subject=subject,
                body=body
            )
            
        except Exception as e:
            logger.error(f"Error sending alert email: {str(e)}")
    
    def create_rule(self, name, description, rule_type, filter_query, 
                   threshold_count, time_window_minutes, email_recipients, created_by):
        """
        Create a new alert rule
        """
        try:
            rule = AlertRule(
                name=name,
                description=description,
                rule_type=rule_type,
                filter_query=filter_query,
                threshold_count=threshold_count,
                time_window_minutes=time_window_minutes,
                email_recipients=email_recipients,
                created_by=created_by
            )
            
            db.session.add(rule)
            db.session.commit()
            
            logger.info(f"Created alert rule: {name}")
            return rule
            
        except Exception as e:
            logger.error(f"Error creating alert rule: {str(e)}")
            db.session.rollback()
            raise
    
    def get_recent_alerts(self, limit=10):
        """
        Get recent alert events
        """
        return AlertEvent.query\
            .join(AlertRule)\
            .order_by(AlertEvent.triggered_at.desc())\
            .limit(limit)\
            .all()
