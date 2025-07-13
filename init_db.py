#!/usr/bin/env python3
"""
Database Initialization Script
Creates tables, indexes, partitions, and initial data for the SIEM platform
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from models import User, EventsRaw, EventsEnriched, AlertRule, AlertEvent, Dashboard, SystemHealth
from werkzeug.security import generate_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_database_tables():
    """Create all database tables"""
    logger.info("Creating database tables...")
    
    try:
        db.create_all()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        raise

def create_partitions():
    """Create table partitions for better performance"""
    logger.info("Creating table partitions...")
    
    try:
        # Create partitions for events_raw table for the next 30 days
        for i in range(30):
            date = datetime.now(timezone.utc) + timedelta(days=i)
            table_name = f"events_raw_{date.strftime('%Y%m%d')}"
            start_date = date.strftime('%Y-%m-%d')
            end_date = (date + timedelta(days=1)).strftime('%Y-%m-%d')
            
            partition_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} PARTITION OF events_raw
            FOR VALUES FROM ('{start_date}') TO ('{end_date}');
            """
            
            try:
                db.session.execute(text(partition_sql))
                logger.debug(f"Created partition: {table_name}")
            except Exception as e:
                # Partition might already exist
                logger.debug(f"Partition {table_name} already exists or error: {e}")
        
        db.session.commit()
        logger.info("Table partitions created successfully")
        
    except Exception as e:
        logger.error(f"Error creating partitions: {e}")
        db.session.rollback()
        raise

def create_indexes():
    """Create additional database indexes for performance"""
    logger.info("Creating database indexes...")
    
    indexes = [
        # Additional indexes for events_enriched
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_enriched_source_ts ON events_enriched(source, ts DESC);",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_enriched_host_ts ON events_enriched(host, ts DESC);",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_enriched_event_type_ts ON events_enriched(event_type, ts DESC);",
        
        # Indexes for alert events
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alert_events_rule_id_triggered_at ON alert_events(rule_id, triggered_at DESC);",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alert_events_triggered_at ON alert_events(triggered_at DESC);",
        
        # Indexes for system health
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_system_health_component_timestamp ON system_health(component, timestamp DESC);",
        
        # Indexes for users
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email ON users(email);",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_last_login ON users(last_login DESC);",
    ]
    
    for index_sql in indexes:
        try:
            db.session.execute(text(index_sql))
            logger.debug(f"Created index: {index_sql.split()[5]}")
        except Exception as e:
            logger.warning(f"Index creation failed (might already exist): {e}")
    
    try:
        db.session.commit()
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        db.session.rollback()

def create_default_users():
    """Create default admin user and sample users"""
    logger.info("Creating default users...")
    
    try:
        # Create admin user
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@siem.local',
                password_hash=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            logger.info("Created default admin user: admin/admin123")
        else:
            logger.info("Admin user already exists")
        
        # Create analyst user
        analyst = User.query.filter_by(username='analyst').first()
        if not analyst:
            analyst = User(
                username='analyst',
                email='analyst@siem.local',
                password_hash=generate_password_hash('analyst123'),
                is_admin=False
            )
            db.session.add(analyst)
            logger.info("Created analyst user: analyst/analyst123")
        else:
            logger.info("Analyst user already exists")
        
        db.session.commit()
        logger.info("Default users created successfully")
        
    except Exception as e:
        logger.error(f"Error creating default users: {e}")
        db.session.rollback()
        raise

def create_default_alert_rules():
    """Create default alert rules"""
    logger.info("Creating default alert rules...")
    
    try:
        # Get admin user for rule ownership
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            logger.warning("Admin user not found, skipping default alert rules")
            return
        
        default_rules = [
            {
                'name': 'SSH Brute Force Attack',
                'description': 'Detects multiple failed SSH login attempts',
                'rule_type': 'threshold',
                'filter_query': 'event_type="ssh_login_failed"',
                'threshold_count': 5,
                'time_window_minutes': 5,
                'email_recipients': ['admin@siem.local']
            },
            {
                'name': 'High Volume of Events',
                'description': 'Detects unusually high volume of events from a single source',
                'rule_type': 'threshold',
                'filter_query': 'source="syslog"',
                'threshold_count': 100,
                'time_window_minutes': 10,
                'email_recipients': ['admin@siem.local']
            },
            {
                'name': 'Web Server Errors',
                'description': 'Detects multiple HTTP 5xx errors',
                'rule_type': 'threshold',
                'filter_query': 'event_type="web_access" AND message LIKE "%50%"',
                'threshold_count': 10,
                'time_window_minutes': 5,
                'email_recipients': ['admin@siem.local']
            }
        ]
        
        for rule_data in default_rules:
            existing_rule = AlertRule.query.filter_by(name=rule_data['name']).first()
            if not existing_rule:
                rule = AlertRule(
                    name=rule_data['name'],
                    description=rule_data['description'],
                    rule_type=rule_data['rule_type'],
                    filter_query=rule_data['filter_query'],
                    threshold_count=rule_data['threshold_count'],
                    time_window_minutes=rule_data['time_window_minutes'],
                    email_recipients=rule_data['email_recipients'],
                    created_by=admin.id
                )
                db.session.add(rule)
                logger.info(f"Created alert rule: {rule_data['name']}")
            else:
                logger.info(f"Alert rule already exists: {rule_data['name']}")
        
        db.session.commit()
        logger.info("Default alert rules created successfully")
        
    except Exception as e:
        logger.error(f"Error creating default alert rules: {e}")
        db.session.rollback()

def create_default_dashboard():
    """Create default dashboard"""
    logger.info("Creating default dashboard...")
    
    try:
        # Get admin user for dashboard ownership
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            logger.warning("Admin user not found, skipping default dashboard")
            return
        
        default_dashboard = Dashboard.query.filter_by(name='Security Overview').first()
        if not default_dashboard:
            dashboard_config = {
                'widgets': [
                    {
                        'id': 'events-timeline',
                        'type': 'line-chart',
                        'title': 'Events Timeline',
                        'position': {'x': 0, 'y': 0, 'w': 8, 'h': 4}
                    },
                    {
                        'id': 'events-by-type',
                        'type': 'pie-chart',
                        'title': 'Events by Type',
                        'position': {'x': 8, 'y': 0, 'w': 4, 'h': 4}
                    },
                    {
                        'id': 'recent-alerts',
                        'type': 'table',
                        'title': 'Recent Alerts',
                        'position': {'x': 0, 'y': 4, 'w': 6, 'h': 4}
                    },
                    {
                        'id': 'top-sources',
                        'type': 'bar-chart',
                        'title': 'Top Event Sources',
                        'position': {'x': 6, 'y': 4, 'w': 6, 'h': 4}
                    }
                ]
            }
            
            dashboard = Dashboard(
                name='Security Overview',
                description='Default security monitoring dashboard',
                layout_config=dashboard_config,
                created_by=admin.id,
                is_public=True
            )
            db.session.add(dashboard)
            logger.info("Created default dashboard: Security Overview")
        else:
            logger.info("Default dashboard already exists")
        
        db.session.commit()
        logger.info("Default dashboard created successfully")
        
    except Exception as e:
        logger.error(f"Error creating default dashboard: {e}")
        db.session.rollback()

def create_system_health_record():
    """Create initial system health record"""
    logger.info("Creating initial system health record...")
    
    try:
        health_record = SystemHealth(
            component='system',
            status='healthy',
            metrics={
                'initialization': True,
                'database': 'connected',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        )
        db.session.add(health_record)
        db.session.commit()
        logger.info("Initial system health record created")
        
    except Exception as e:
        logger.error(f"Error creating system health record: {e}")
        db.session.rollback()

def optimize_database():
    """Run database optimization commands"""
    logger.info("Optimizing database...")
    
    try:
        # Update table statistics
        db.session.execute(text("ANALYZE;"))
        
        # Vacuum to reclaim space (if needed)
        # Note: VACUUM cannot be run inside a transaction
        db.session.commit()
        
        logger.info("Database optimization completed")
        
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")

def verify_installation():
    """Verify that the installation was successful"""
    logger.info("Verifying installation...")
    
    try:
        # Check tables exist
        tables = ['users', 'events_raw', 'events_enriched', 'alert_rules', 'alert_events', 'dashboards', 'system_health']
        for table in tables:
            result = db.session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            logger.info(f"Table {table}: {result} records")
        
        # Check admin user
        admin = User.query.filter_by(username='admin').first()
        if admin:
            logger.info(f"Admin user exists: {admin.email}")
        else:
            logger.error("Admin user not found!")
            return False
        
        # Check alert rules
        rule_count = AlertRule.query.count()
        logger.info(f"Alert rules: {rule_count}")
        
        # Check dashboard
        dashboard_count = Dashboard.query.count()
        logger.info(f"Dashboards: {dashboard_count}")
        
        logger.info("Installation verification completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Installation verification failed: {e}")
        return False

def main():
    """Main initialization function"""
    logger.info("Starting SIEM database initialization...")
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        try:
            # Step 1: Create tables
            create_database_tables()
            
            # Step 2: Create partitions
            create_partitions()
            
            # Step 3: Create indexes
            create_indexes()
            
            # Step 4: Create default users
            create_default_users()
            
            # Step 5: Create default alert rules
            create_default_alert_rules()
            
            # Step 6: Create default dashboard
            create_default_dashboard()
            
            # Step 7: Create initial system health record
            create_system_health_record()
            
            # Step 8: Optimize database
            optimize_database()
            
            # Step 9: Verify installation
            if verify_installation():
                logger.info("🎉 SIEM database initialization completed successfully!")
                logger.info("")
                logger.info("Next steps:")
                logger.info("1. Start the Flask application: python main.py")
                logger.info("2. Start the Celery worker: celery -A celery_worker worker --loglevel=info")
                logger.info("3. Start the Celery beat scheduler: celery -A celery_worker beat --loglevel=info")
                logger.info("4. Install and configure the agent on target systems")
                logger.info("5. Access the web interface at http://localhost:5000")
                logger.info("")
                logger.info("Default credentials:")
                logger.info("  Admin: admin / admin123")
                logger.info("  Analyst: analyst / analyst123")
            else:
                logger.error("❌ Database initialization verification failed!")
                return 1
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
