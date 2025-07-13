import os

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/siem')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # RabbitMQ configuration
    RABBITMQ_URL = os.environ.get('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
    
    # Redis configuration
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Email configuration
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'localhost')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    ALERT_FROM_EMAIL = os.environ.get('ALERT_FROM_EMAIL', 'alerts@siem.local')
    
    # GeoIP configuration
    GEOIP_DB_PATH = os.environ.get('GEOIP_DB_PATH', '/opt/geoip/GeoLite2-City.mmdb')
    
    # Agent authentication
    AGENT_API_TOKEN = os.environ.get('AGENT_API_TOKEN', 'siem-agent-token-change-me')
    
    # Pagination
    EVENTS_PER_PAGE = 50
    
    # Archive settings
    DAYS_TO_KEEP_HOT = int(os.environ.get('DAYS_TO_KEEP_HOT', '7'))
    DAYS_TO_KEEP_ARCHIVE = int(os.environ.get('DAYS_TO_KEEP_ARCHIVE', '365'))
