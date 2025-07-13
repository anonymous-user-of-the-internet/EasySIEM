"""
Session management for SIEM platform
Provides Redis-based session handling with security features
"""

from datetime import datetime, timedelta
import json
from uuid import uuid4
from flask import session
from redis import Redis
from flask_login import user_loaded_from_header

class SessionManager:
    def __init__(self, app=None, redis_url=None):
        self.app = app
        self.redis_url = redis_url or app.config.get('REDIS_URL', 'redis://localhost:6379/1')
        self.redis = Redis.from_url(self.redis_url)
        self.session_lifetime = int(app.config.get('SESSION_LIFETIME', 86400))  # 24 hours default
        self.max_sessions = int(app.config.get('MAX_USER_SESSIONS', 5))

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the session manager with the Flask app"""
        self.app = app
        
        # Set session configuration
        app.config.update(
            SESSION_TYPE='redis',
            PERMANENT_SESSION_LIFETIME=timedelta(seconds=self.session_lifetime),
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax'
        )

        # Register session cleanup with Flask-Login
        @user_loaded_from_header.connect
        def on_user_loaded(sender, user=None, **kwargs):
            if user:
                self.cleanup_expired_sessions(user.id)

    def create_session(self, user_id, user_agent, ip_address):
        """Create a new session for a user"""
        session_id = str(uuid4())
        session_data = {
            'user_id': user_id,
            'session_id': session_id,
            'user_agent': user_agent,
            'ip_address': ip_address,
            'created_at': datetime.utcnow().isoformat(),
            'last_accessed': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(seconds=self.session_lifetime)).isoformat()
        }

        # Store session in Redis
        self.redis.setex(
            f'session:{session_id}',
            self.session_lifetime,
            json.dumps(session_data)
        )

        # Add session to user's session list
        user_sessions_key = f'user_sessions:{user_id}'
        self.redis.sadd(user_sessions_key, session_id)

        # Enforce max sessions per user
        self._enforce_max_sessions(user_id)

        return session_id

    def get_session(self, session_id):
        """Retrieve and validate a session"""
        session_key = f'session:{session_id}'
        session_data = self.redis.get(session_key)

        if not session_data:
            return None

        session_data = json.loads(session_data)
        
        # Update last accessed time
        session_data['last_accessed'] = datetime.utcnow().isoformat()
        self.redis.setex(
            session_key,
            self.session_lifetime,
            json.dumps(session_data)
        )

        return session_data

    def delete_session(self, session_id):
        """Delete a specific session"""
        session_key = f'session:{session_id}'
        session_data = self.redis.get(session_key)

        if session_data:
            session_data = json.loads(session_data)
            user_id = session_data.get('user_id')
            if user_id:
                self.redis.srem(f'user_sessions:{user_id}', session_id)
            
            self.redis.delete(session_key)

    def get_user_sessions(self, user_id):
        """Get all active sessions for a user"""
        sessions = []
        session_ids = self.redis.smembers(f'user_sessions:{user_id}')

        for session_id in session_ids:
            session_data = self.redis.get(f'session:{session_id.decode()}')
            if session_data:
                sessions.append(json.loads(session_data))

        return sessions

    def cleanup_expired_sessions(self, user_id):
        """Clean up expired sessions for a user"""
        session_ids = self.redis.smembers(f'user_sessions:{user_id}')
        now = datetime.utcnow()

        for session_id in session_ids:
            session_key = f'session:{session_id.decode()}'
            session_data = self.redis.get(session_key)

            if session_data:
                session_data = json.loads(session_data)
                expires_at = datetime.fromisoformat(session_data['expires_at'])
                
                if expires_at < now:
                    self.delete_session(session_id.decode())

    def _enforce_max_sessions(self, user_id):
        """Enforce maximum number of sessions per user"""
        sessions = self.get_user_sessions(user_id)
        
        if len(sessions) > self.max_sessions:
            # Sort sessions by last accessed time and remove oldest
            sorted_sessions = sorted(
                sessions,
                key=lambda x: datetime.fromisoformat(x['last_accessed'])
            )
            
            for session in sorted_sessions[:-self.max_sessions]:
                self.delete_session(session['session_id'])

    def revoke_all_user_sessions(self, user_id):
        """Revoke all sessions for a specific user"""
        sessions = self.get_user_sessions(user_id)
        for session in sessions:
            self.delete_session(session['session_id'])

    def validate_session(self, session_id, user_agent, ip_address):
        """Validate session integrity and security"""
        session_data = self.get_session(session_id)
        if not session_data:
            return False

        # Check if session is expired
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if expires_at < datetime.utcnow():
            self.delete_session(session_id)
            return False

        # Validate user agent and IP (optional strict checking)
        if self.app.config.get('STRICT_SESSION_SECURITY', False):
            if session_data['user_agent'] != user_agent:
                self.delete_session(session_id)
                return False
            
            if session_data['ip_address'] != ip_address:
                self.delete_session(session_id)
                return False

        return True
