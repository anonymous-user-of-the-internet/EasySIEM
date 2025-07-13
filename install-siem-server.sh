#!/bin/bash

# SIEM Server One-Click Installation Script
# This script installs and configures a complete SIEM platform
# Supports: Ubuntu 20.04+, Debian 11+, CentOS 8+, RHEL 8+

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
SIEM_USER="siem"
SIEM_GROUP="siem"
INSTALL_DIR="/opt/siem"
LOG_DIR="/var/log/siem"
SERVICE_NAME="siem-server"
GITHUB_REPO="https://github.com/your-org/siem-platform.git"  # Update with actual repo
BRANCH="main"

# Default database configuration
DB_NAME="siem"
DB_USER="siem_user"
DB_PASSWORD=""

# Generate secure passwords
generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_banner() {
    echo -e "${PURPLE}"
    cat << 'EOF'
 ____  ___ _____ __  __   ____                           
/ ___|_ _| ____|  \/  | / ___|  ___ _ ____   _____ _ __   
\___ \| ||  _| | |\/| | \___ \ / _ \ '__\ \ / / _ \ '__|  
 ___) | || |___| |  | |  ___) |  __/ |   \ V /  __/ |     
|____/___|_____|_|  |_| |____/ \___|_|    \_/ \___|_|     
                                                          
Security Information & Event Management Platform
One-Click Installation Script
EOF
    echo -e "${NC}"
}

# Check if script is run as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        echo "Please run: sudo $0"
        exit 1
    fi
}

# Detect operating system
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VERSION=$VERSION_ID
    else
        log_error "Cannot detect operating system"
        exit 1
    fi
    
    log_info "Detected OS: $OS $VERSION"
}

# Install system dependencies
install_dependencies() {
    log_step "Installing system dependencies..."
    
    case $OS in
        "Ubuntu"*|"Debian"*)
            apt-get update
            apt-get install -y \
                python3 python3-pip python3-venv python3-dev \
                postgresql postgresql-contrib \
                redis-server \
                rabbitmq-server \
                nginx \
                git curl wget \
                systemd \
                software-properties-common \
                apt-transport-https \
                ca-certificates \
                gnupg \
                lsb-release \
                ufw
            ;;
        "CentOS"*|"Red Hat"*|"Rocky"*|"AlmaLinux"*)
            yum update -y
            yum install -y epel-release
            yum install -y \
                python3 python3-pip python3-devel \
                postgresql postgresql-server postgresql-contrib \
                redis \
                rabbitmq-server \
                nginx \
                git curl wget \
                systemd \
                firewalld
            
            # Initialize PostgreSQL on RHEL-based systems
            if [[ ! -d /var/lib/pgsql/data/base ]]; then
                postgresql-setup --initdb
            fi
            ;;
        *)
            log_error "Unsupported operating system: $OS"
            exit 1
            ;;
    esac
    
    log_info "System dependencies installed successfully"
}

# Configure PostgreSQL
setup_postgresql() {
    log_step "Configuring PostgreSQL database..."
    
    # Generate secure password if not set
    if [[ -z "$DB_PASSWORD" ]]; then
        DB_PASSWORD=$(generate_password)
    fi
    
    # Start and enable PostgreSQL
    systemctl start postgresql
    systemctl enable postgresql
    
    # Create database and user
    sudo -u postgres psql << EOF
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
ALTER USER $DB_USER CREATEDB;
\q
EOF
    
    # Update PostgreSQL configuration for remote connections
    PG_VERSION=$(sudo -u postgres psql -t -c "SELECT version();" | grep -oP '\d+\.\d+' | head -1)
    PG_CONFIG_DIR="/etc/postgresql/$PG_VERSION/main"
    
    if [[ -d $PG_CONFIG_DIR ]]; then
        # Allow local connections
        sed -i "s/#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" "$PG_CONFIG_DIR/postgresql.conf"
        
        # Configure authentication
        if ! grep -q "$DB_USER" "$PG_CONFIG_DIR/pg_hba.conf"; then
            echo "local   $DB_NAME    $DB_USER                                md5" >> "$PG_CONFIG_DIR/pg_hba.conf"
        fi
        
        systemctl restart postgresql
    fi
    
    log_info "PostgreSQL configured successfully"
    log_info "Database: $DB_NAME, User: $DB_USER"
}

# Configure Redis
setup_redis() {
    log_step "Configuring Redis..."
    
    systemctl start redis-server || systemctl start redis
    systemctl enable redis-server || systemctl enable redis
    
    # Configure Redis for production
    REDIS_CONF="/etc/redis/redis.conf"
    if [[ -f "$REDIS_CONF" ]]; then
        sed -i 's/^# maxmemory <bytes>/maxmemory 256mb/' "$REDIS_CONF"
        sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' "$REDIS_CONF"
        systemctl restart redis-server || systemctl restart redis
    fi
    
    log_info "Redis configured successfully"
}

# Configure RabbitMQ
setup_rabbitmq() {
    log_step "Configuring RabbitMQ..."
    
    systemctl start rabbitmq-server
    systemctl enable rabbitmq-server
    
    # Enable management plugin
    rabbitmq-plugins enable rabbitmq_management
    
    # Create SIEM user
    RABBITMQ_PASSWORD=$(generate_password)
    rabbitmqctl add_user siem "$RABBITMQ_PASSWORD"
    rabbitmqctl set_user_tags siem administrator
    rabbitmqctl set_permissions -p / siem ".*" ".*" ".*"
    
    log_info "RabbitMQ configured successfully"
    log_info "RabbitMQ User: siem, Password: $RABBITMQ_PASSWORD"
}

# Create SIEM user and directories
setup_siem_user() {
    log_step "Creating SIEM user and directories..."
    
    # Create system user
    if ! id "$SIEM_USER" &>/dev/null; then
        useradd --system --home-dir $INSTALL_DIR --shell /bin/bash $SIEM_USER
    fi
    
    # Create directories
    mkdir -p $INSTALL_DIR
    mkdir -p $LOG_DIR
    mkdir -p /etc/siem
    
    # Set permissions
    chown -R $SIEM_USER:$SIEM_GROUP $INSTALL_DIR
    chown -R $SIEM_USER:$SIEM_GROUP $LOG_DIR
    chown -R $SIEM_USER:$SIEM_GROUP /etc/siem
    
    log_info "SIEM user and directories created"
}

# Install SIEM application
install_siem_app() {
    log_step "Installing SIEM application..."
    
    # Clone repository
    cd /tmp
    if [[ -d "siem-platform" ]]; then
        rm -rf siem-platform
    fi
    
    git clone $GITHUB_REPO siem-platform
    cd siem-platform
    git checkout $BRANCH
    
    # Copy application files
    cp -r * $INSTALL_DIR/
    chown -R $SIEM_USER:$SIEM_GROUP $INSTALL_DIR
    
    # Create Python virtual environment
    sudo -u $SIEM_USER python3 -m venv $INSTALL_DIR/venv
    
    # Install Python dependencies
    sudo -u $SIEM_USER $INSTALL_DIR/venv/bin/pip install --upgrade pip
    sudo -u $SIEM_USER $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt
    
    log_info "SIEM application installed"
}

# Generate SIEM configuration
create_siem_config() {
    log_step "Creating SIEM configuration..."
    
    # Generate secret keys
    SESSION_SECRET=$(generate_password)
    AGENT_API_TOKEN="siem-agent-$(generate_password)"
    
    # Create environment configuration
    cat > /etc/siem/config.env << EOF
# SIEM Server Configuration
# Generated on $(date)

# Database Configuration
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME

# Session Security
SESSION_SECRET=$SESSION_SECRET

# Message Queue Configuration  
RABBITMQ_URL=amqp://siem:$RABBITMQ_PASSWORD@localhost:5672/
REDIS_URL=redis://localhost:6379/0

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Agent Authentication
AGENT_API_TOKEN=$AGENT_API_TOKEN

# Email Configuration (update as needed)
SMTP_SERVER=localhost
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
ALERT_FROM_EMAIL=alerts@$(hostname -d || echo "siem.local")

# GeoIP Configuration
GEOIP_DB_PATH=/opt/geoip/GeoLite2-City.mmdb

# Log Retention
DAYS_TO_KEEP_HOT=7
DAYS_TO_KEEP_ARCHIVE=365

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=false
EOF
    
    # Set secure permissions
    chmod 600 /etc/siem/config.env
    chown $SIEM_USER:$SIEM_GROUP /etc/siem/config.env
    
    log_info "SIEM configuration created"
    log_info "Agent API Token: $AGENT_API_TOKEN"
}

# Create systemd services
create_systemd_services() {
    log_step "Creating systemd services..."
    
    # SIEM Web Server Service
    cat > /etc/systemd/system/siem-server.service << EOF
[Unit]
Description=SIEM Web Server
After=network.target postgresql.service redis.service rabbitmq-server.service
Wants=postgresql.service redis.service rabbitmq-server.service

[Service]
Type=simple
User=$SIEM_USER
Group=$SIEM_GROUP
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
EnvironmentFile=/etc/siem/config.env
ExecStart=$INSTALL_DIR/venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 main:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # SIEM Celery Worker Service
    cat > /etc/systemd/system/siem-worker.service << EOF
[Unit]
Description=SIEM Celery Worker
After=network.target postgresql.service redis.service rabbitmq-server.service
Wants=postgresql.service redis.service rabbitmq-server.service

[Service]
Type=simple
User=$SIEM_USER
Group=$SIEM_GROUP
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
EnvironmentFile=/etc/siem/config.env
ExecStart=$INSTALL_DIR/venv/bin/celery -A celery_worker worker --loglevel=info --concurrency=4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # SIEM Celery Beat Service (Scheduler)
    cat > /etc/systemd/system/siem-scheduler.service << EOF
[Unit]
Description=SIEM Celery Beat Scheduler
After=network.target postgresql.service redis.service rabbitmq-server.service
Wants=postgresql.service redis.service rabbitmq-server.service

[Service]
Type=simple
User=$SIEM_USER
Group=$SIEM_GROUP
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
EnvironmentFile=/etc/siem/config.env
ExecStart=$INSTALL_DIR/venv/bin/celery -A celery_worker beat --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    
    log_info "Systemd services created"
}

# Configure Nginx reverse proxy
setup_nginx() {
    log_step "Configuring Nginx reverse proxy..."
    
    # Remove default site
    rm -f /etc/nginx/sites-enabled/default
    
    # Create SIEM site configuration
    cat > /etc/nginx/sites-available/siem << EOF
server {
    listen 80;
    server_name _;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";
    
    # Increase client max body size for log uploads
    client_max_body_size 100M;
    
    # Main application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Static files
    location /static {
        alias $INSTALL_DIR/static;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF
    
    # Enable site
    ln -sf /etc/nginx/sites-available/siem /etc/nginx/sites-enabled/
    
    # Test configuration
    nginx -t
    
    # Start and enable Nginx
    systemctl start nginx
    systemctl enable nginx
    
    log_info "Nginx configured successfully"
}

# Initialize database
initialize_database() {
    log_step "Initializing SIEM database..."
    
    cd $INSTALL_DIR
    
    # Set environment variables
    export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
    export SESSION_SECRET=$(grep SESSION_SECRET /etc/siem/config.env | cut -d'=' -f2)
    
    # Run database initialization
    sudo -u $SIEM_USER -E $INSTALL_DIR/venv/bin/python init_db.py
    
    log_info "Database initialized successfully"
}

# Configure firewall
setup_firewall() {
    log_step "Configuring firewall..."
    
    case $OS in
        "Ubuntu"*|"Debian"*)
            # Configure UFW
            ufw --force enable
            ufw allow ssh
            ufw allow 80/tcp
            ufw allow 443/tcp
            ufw allow 514/udp  # Syslog
            ufw allow 5514/udp # Custom syslog
            ;;
        "CentOS"*|"Red Hat"*|"Rocky"*|"AlmaLinux"*)
            # Configure firewalld
            systemctl start firewalld
            systemctl enable firewalld
            firewall-cmd --permanent --add-service=ssh
            firewall-cmd --permanent --add-service=http
            firewall-cmd --permanent --add-service=https
            firewall-cmd --permanent --add-port=514/udp
            firewall-cmd --permanent --add-port=5514/udp
            firewall-cmd --reload
            ;;
    esac
    
    log_info "Firewall configured successfully"
}

# Start all services
start_services() {
    log_step "Starting SIEM services..."
    
    # Start database services first
    systemctl start postgresql
    systemctl start redis-server || systemctl start redis
    systemctl start rabbitmq-server
    
    # Start SIEM services
    systemctl enable siem-server
    systemctl enable siem-worker
    systemctl enable siem-scheduler
    
    systemctl start siem-server
    systemctl start siem-worker
    systemctl start siem-scheduler
    
    # Start web server
    systemctl restart nginx
    
    log_info "All services started successfully"
}

# Create requirements.txt file
create_requirements() {
    cat > $INSTALL_DIR/requirements.txt << EOF
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Flask-Login==0.6.2
psycopg2-binary==2.9.7
celery==5.3.1
redis==4.6.0
pika==1.3.2
requests==2.31.0
PyYAML==6.0.1
email-validator==2.0.0
gunicorn==21.2.0
Werkzeug==2.3.7
SQLAlchemy==2.0.19
maxminddb==2.4.1
psutil==5.9.5
EOF
}

# Verify installation
verify_installation() {
    log_step "Verifying installation..."
    
    # Check services
    services=("postgresql" "redis-server" "rabbitmq-server" "nginx" "siem-server" "siem-worker" "siem-scheduler")
    
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service" || systemctl is-active --quiet "${service%%-*}"; then
            log_info "✓ $service is running"
        else
            log_warn "✗ $service is not running"
        fi
    done
    
    # Check web interface
    sleep 5
    if curl -s http://localhost > /dev/null; then
        log_info "✓ Web interface is accessible"
    else
        log_warn "✗ Web interface is not accessible"
    fi
    
    # Check database connection
    if sudo -u $SIEM_USER psql "postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME" -c "\q" 2>/dev/null; then
        log_info "✓ Database connection successful"
    else
        log_warn "✗ Database connection failed"
    fi
}

# Print installation summary
print_summary() {
    echo -e "${GREEN}"
    cat << EOF

🎉 SIEM Installation Complete!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🌐 Web Interface: http://$(hostname -I | awk '{print $1}')
   Default Login: admin / admin123

🔑 Database Credentials:
   Database: $DB_NAME
   Username: $DB_USER  
   Password: $DB_PASSWORD

🤖 Agent API Token: 
   $(grep AGENT_API_TOKEN /etc/siem/config.env | cut -d'=' -f2)

📁 Installation Directory: $INSTALL_DIR
📋 Configuration: /etc/siem/config.env
📊 Logs: $LOG_DIR

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 Next Steps:
1. Access the web interface and change the default password
2. Configure email settings in /etc/siem/config.env
3. Download and install agents on target systems
4. Configure alert rules and dashboards

📚 Documentation: https://github.com/your-org/siem-platform

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Service Management:
• systemctl status siem-server
• systemctl status siem-worker  
• systemctl status siem-scheduler
• systemctl restart nginx

EOF
    echo -e "${NC}"
}

# Main installation function
main() {
    print_banner
    
    log_info "Starting SIEM platform installation..."
    
    check_root
    detect_os
    install_dependencies
    setup_postgresql
    setup_redis
    setup_rabbitmq
    setup_siem_user
    create_requirements
    install_siem_app
    create_siem_config
    create_systemd_services
    setup_nginx
    initialize_database
    setup_firewall
    start_services
    verify_installation
    print_summary
    
    log_info "Installation completed successfully!"
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "SIEM Server Installation Script"
        echo ""
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --db-password  Set custom database password"
        echo "  --repo         Set custom GitHub repository URL"
        echo "  --branch       Set custom Git branch (default: main)"
        echo ""
        echo "Example:"
        echo "  $0 --db-password mypassword --repo https://github.com/myorg/siem.git"
        exit 0
        ;;
    --db-password)
        DB_PASSWORD="$2"
        shift 2
        ;;
    --repo)
        GITHUB_REPO="$2"
        shift 2
        ;;
    --branch)
        BRANCH="$2"
        shift 2
        ;;
esac

# Run main installation
main "$@"