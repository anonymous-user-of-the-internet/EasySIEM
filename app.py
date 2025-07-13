import os
import logging
from flask import Flask, session, request, current_app, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

def create_app():
    # Create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Configure the database
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/siem")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # SIEM specific configuration
    app.config["RABBITMQ_URL"] = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    app.config["REDIS_URL"] = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    app.config["SMTP_SERVER"] = os.environ.get("SMTP_SERVER", "localhost")
    app.config["SMTP_PORT"] = int(os.environ.get("SMTP_PORT", "587"))
    app.config["SMTP_USERNAME"] = os.environ.get("SMTP_USERNAME", "")
    app.config["SMTP_PASSWORD"] = os.environ.get("SMTP_PASSWORD", "")
    app.config["ALERT_FROM_EMAIL"] = os.environ.get("ALERT_FROM_EMAIL", "alerts@siem.local")
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access the SIEM dashboard.'
    
    # Initialize session management
    from utils.session_manager import SessionManager
    session_manager = SessionManager(app)
    app.session_manager = session_manager

    @app.before_request
    def validate_session():
        if not getattr(current_app, 'session_manager', None):
            return
            
        if 'session_id' in session:
            user_agent = request.headers.get('User-Agent')
            ip_address = request.remote_addr
            
            if not current_app.session_manager.validate_session(
                session['session_id'],
                user_agent,
                ip_address
            ):
                session.clear()
                return redirect(url_for('auth.login'))
    
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))
    
    # Register blueprints
    from routes.dashboard import dashboard_bp
    from routes.api import api_bp
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp)
    
    # Create database tables
    with app.app_context():
        import models
        db.create_all()
        
        # Create default admin user if it doesn't exist
        from models import User
        from werkzeug.security import generate_password_hash
        
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@siem.local',
                password_hash=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            logging.info("Created default admin user: admin/admin123")
    
    return app

app = create_app()
