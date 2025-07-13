"""
Session cleanup task for the SIEM platform
Periodically removes expired sessions from Redis
"""

from celery import shared_task
import logging
from app import app
from utils.session_manager import SessionManager

logger = logging.getLogger(__name__)

@shared_task
def cleanup_expired_sessions():
    """Celery task to clean up expired sessions"""
    try:
        with app.app_context():
            session_manager = SessionManager(app)
            redis = session_manager.redis
            
            # Get all session keys
            session_keys = redis.keys('session:*')
            sessions_cleaned = 0
            
            for key in session_keys:
                session_id = key.decode().split(':')[1]
                session_data = session_manager.get_session(session_id)
                
                if session_data is None:
                    sessions_cleaned += 1
            
            logger.info(f"Session cleanup completed. Removed {sessions_cleaned} expired sessions.")
            
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")
        raise

@shared_task
def log_active_sessions():
    """Celery task to log active session statistics"""
    try:
        with app.app_context():
            session_manager = SessionManager(app)
            redis = session_manager.redis
            
            # Count active sessions
            session_count = len(redis.keys('session:*'))
            
            # Count unique users with active sessions
            user_count = len(redis.keys('user_sessions:*'))
            
            logger.info(f"Active sessions: {session_count}, Unique users: {user_count}")
            
    except Exception as e:
        logger.error(f"Error logging session statistics: {e}")
        raise
