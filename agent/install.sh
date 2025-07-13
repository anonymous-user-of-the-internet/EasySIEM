#!/bin/bash

# SIEM Agent Installation Script
# This script installs the SIEM agent on Linux systems

set -e

# Configuration
AGENT_USER="siem-agent"
AGENT_GROUP="siem-agent"
INSTALL_DIR="/opt/siem-agent"
CONFIG_DIR="/etc/siem-agent"
LOG_DIR="/var/log/siem-agent"
SERVICE_NAME="siem-agent"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

# Check if script is run as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
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
    log_info "Installing system dependencies..."
    
    case $OS in
        "Ubuntu"*|"Debian"*)
            apt-get update
            apt-get install -y python3 python3-pip python3-venv systemd
            ;;
        "CentOS"*|"Red Hat"*|"Rocky"*|"AlmaLinux"*)
            yum update -y
            yum install -y python3 python3-pip systemd
            # Install python3-venv if available
            yum install -y python3-venv || pip3 install virtualenv
            ;;
        "Fedora"*)
            dnf update -y
            dnf install -y python3 python3-pip python3-venv systemd
            ;;
        *)
            log_warn "Unsupported OS: $OS. Proceeding with manual dependency check..."
            ;;
    esac
}

# Create system user and group
create_user() {
    log_info "Creating system user and group..."
    
    # Create group if it doesn't exist
    if ! getent group $AGENT_GROUP >/dev/null 2>&1; then
        groupadd --system $AGENT_GROUP
        log_info "Created group: $AGENT_GROUP"
    fi
    
    # Create user if it doesn't exist
    if ! getent passwd $AGENT_USER >/dev/null 2>&1; then
        useradd --system --gid $AGENT_GROUP --home-dir $INSTALL_DIR \
                --shell /bin/false --comment "SIEM Agent User" $AGENT_USER
        log_info "Created user: $AGENT_USER"
    fi
}

# Create directories
create_directories() {
    log_info "Creating directories..."
    
    mkdir -p $INSTALL_DIR
    mkdir -p $CONFIG_DIR
    mkdir -p $LOG_DIR
    
    # Set ownership and permissions
    chown -R $AGENT_USER:$AGENT_GROUP $INSTALL_DIR
    chown -R $AGENT_USER:$AGENT_GROUP $CONFIG_DIR
    chown -R $AGENT_USER:$AGENT_GROUP $LOG_DIR
    
    chmod 755 $INSTALL_DIR
    chmod 750 $CONFIG_DIR
    chmod 750 $LOG_DIR
}

# Install Python dependencies
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    # Create virtual environment
    python3 -m venv $INSTALL_DIR/venv
    
    # Activate virtual environment and install packages
    source $INSTALL_DIR/venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install required packages
    pip install \
        requests \
        PyYAML \
        systemd-python
    
    deactivate
    
    # Set ownership
    chown -R $AGENT_USER:$AGENT_GROUP $INSTALL_DIR/venv
}

# Install agent files
install_agent() {
    log_info "Installing SIEM agent files..."
    
    # Copy agent script
    if [[ -f "siem_agent.py" ]]; then
        cp siem_agent.py $INSTALL_DIR/
        chmod 755 $INSTALL_DIR/siem_agent.py
        chown $AGENT_USER:$AGENT_GROUP $INSTALL_DIR/siem_agent.py
    else
        log_error "siem_agent.py not found in current directory"
        exit 1
    fi
    
    # Copy configuration file
    if [[ -f "config.yaml" ]]; then
        if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
            cp config.yaml $CONFIG_DIR/
            chmod 640 $CONFIG_DIR/config.yaml
            chown $AGENT_USER:$AGENT_GROUP $CONFIG_DIR/config.yaml
            log_info "Installed default configuration file"
        else
            log_warn "Configuration file already exists, skipping..."
        fi
    else
        log_error "config.yaml not found in current directory"
        exit 1
    fi
    
    # Create wrapper script
    cat > $INSTALL_DIR/siem-agent << 'EOF'
#!/bin/bash
INSTALL_DIR="/opt/siem-agent"
source $INSTALL_DIR/venv/bin/activate
exec python3 $INSTALL_DIR/siem_agent.py "$@"
EOF
    
    chmod 755 $INSTALL_DIR/siem-agent
    chown $AGENT_USER:$AGENT_GROUP $INSTALL_DIR/siem-agent
}

# Install systemd service
install_service() {
    log_info "Installing systemd service..."
    
    # Copy service file
    if [[ -f "siem-agent.service" ]]; then
        cp siem-agent.service /etc/systemd/system/
        chmod 644 /etc/systemd/system/siem-agent.service
        
        # Reload systemd
        systemctl daemon-reload
        
        log_info "Systemd service installed"
    else
        log_error "siem-agent.service not found in current directory"
        exit 1
    fi
}

# Configure log rotation
setup_logrotate() {
    log_info "Setting up log rotation..."
    
    cat > /etc/logrotate.d/siem-agent << 'EOF'
/var/log/siem-agent/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 siem-agent siem-agent
    postrotate
        systemctl reload siem-agent >/dev/null 2>&1 || true
    endscript
}
EOF
    
    log_info "Log rotation configured"
}

# Configure firewall (if needed)
configure_firewall() {
    log_info "Checking firewall configuration..."
    
    # Check if ufw is installed and active
    if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
        log_warn "UFW firewall is active. You may need to allow syslog ports:"
        log_warn "  sudo ufw allow 514/udp"
        log_warn "  sudo ufw allow 5514/udp"
    fi
    
    # Check if firewalld is installed and active
    if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
        log_warn "firewalld is active. You may need to allow syslog ports:"
        log_warn "  sudo firewall-cmd --permanent --add-port=514/udp"
        log_warn "  sudo firewall-cmd --permanent --add-port=5514/udp"
        log_warn "  sudo firewall-cmd --reload"
    fi
}

# Main installation function
main() {
    log_info "Starting SIEM Agent installation..."
    
    check_root
    detect_os
    install_dependencies
    create_user
    create_directories
    install_python_deps
    install_agent
    install_service
    setup_logrotate
    configure_firewall
    
    log_info "Installation completed successfully!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Edit configuration: $CONFIG_DIR/config.yaml"
    log_info "2. Update the SIEM endpoint and API token"
    log_info "3. Start the service: systemctl start $SERVICE_NAME"
    log_info "4. Enable auto-start: systemctl enable $SERVICE_NAME"
    log_info "5. Check status: systemctl status $SERVICE_NAME"
    log_info "6. View logs: journalctl -u $SERVICE_NAME -f"
}

# Run installation
main "$@"
