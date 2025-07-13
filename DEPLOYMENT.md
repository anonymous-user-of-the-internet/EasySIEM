# SIEM Platform Deployment Guide

## Quick Start

### One-Click Server Installation

1. **Download the installation script:**
```bash
curl -o install-siem-server.sh https://raw.githubusercontent.com/your-org/siem-platform/main/install-siem-server.sh
chmod +x install-siem-server.sh
```

2. **Run the installation:**
```bash
sudo ./install-siem-server.sh
```

The script will automatically:
- Install all system dependencies (PostgreSQL, Redis, RabbitMQ, Nginx)
- Create SIEM user and directories
- Configure database and message queues
- Install and configure the SIEM application
- Set up systemd services
- Configure firewall rules
- Initialize the database with default users

### Custom Installation Options

```bash
# Set custom database password
sudo ./install-siem-server.sh --db-password "your-secure-password"

# Use custom repository
sudo ./install-siem-server.sh --repo "https://github.com/yourorg/siem.git"

# Use specific branch
sudo ./install-siem-server.sh --branch "production"
```

## Agent Deployment

### Web-Based Agent Generator

1. **Access the SIEM dashboard** at `http://your-server-ip`
2. **Login** with admin credentials (admin/admin123)
3. **Navigate** to User Menu → "Agent Generator"
4. **Configure agent settings:**
   - SIEM Server endpoint
   - Unique agent ID
   - Log file paths to monitor
   - Syslog listener ports
   - Security settings

5. **Download** the generated ZIP package
6. **Deploy** to target systems:
```bash
# Transfer to target server
scp siem-agent-server01.zip user@target-server:~

# Extract and install
unzip siem-agent-server01.zip
sudo ./install.sh
```

### Manual Agent Configuration

If you prefer manual configuration, edit `/etc/siem-agent/config.yaml`:

```yaml
# SIEM Platform Connection
siem_endpoint: "http://your-siem-server:5000/api/ingest"
api_token: "your-secure-api-token"

# Agent Identification
agent_id: "web-server-01"

# Log Sources
file_sources:
  - name: "auth"
    path: "/var/log/auth.log"
  - name: "apache-access"
    path: "/var/log/apache2/access.log"

# Syslog Listeners
syslog_sources:
  - name: "network-devices"
    port: 514
```

## System Requirements

### SIEM Server

**Minimum Requirements:**
- 4 CPU cores
- 8 GB RAM
- 100 GB disk space
- Ubuntu 20.04+ / CentOS 8+ / Debian 11+

**Recommended for Production:**
- 8 CPU cores
- 16 GB RAM
- 500 GB SSD storage
- Dedicated database server

### SIEM Agent

**Requirements:**
- 1 CPU core
- 512 MB RAM
- 1 GB disk space
- Python 3.6+
- systemd support

## Network Configuration

### Required Ports

**SIEM Server:**
- `80/tcp` - HTTP web interface
- `443/tcp` - HTTPS (if SSL configured)
- `5432/tcp` - PostgreSQL (if remote database)

**Agent Communication:**
- `514/udp` - Standard syslog
- `5514/udp` - Custom syslog port

### Firewall Rules

The installation script automatically configures firewall rules. For manual setup:

**Ubuntu/Debian (UFW):**
```bash
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 514/udp
ufw allow 5514/udp
```

**CentOS/RHEL (firewalld):**
```bash
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --permanent --add-port=514/udp
firewall-cmd --permanent --add-port=5514/udp
firewall-cmd --reload
```

## Post-Installation Configuration

### 1. Change Default Credentials

Login to the web interface and change the default admin password:
- URL: `http://your-server-ip`
- Username: `admin`
- Password: `admin123`

### 2. Configure Email Alerts

Edit `/etc/siem/config.env`:
```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=alerts@yourcompany.com
SMTP_PASSWORD=your-app-password
ALERT_FROM_EMAIL=siem-alerts@yourcompany.com
```

Restart services:
```bash
sudo systemctl restart siem-server siem-worker
```

### 3. SSL/HTTPS Configuration

Install SSL certificate and update Nginx configuration:
```bash
# Install Let's Encrypt certificate
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# Or use custom certificate
sudo cp your-cert.pem /etc/ssl/certs/
sudo cp your-key.pem /etc/ssl/private/
```

### 4. Configure GeoIP

Download MaxMind GeoLite2 database:
```bash
sudo mkdir -p /opt/geoip
cd /opt/geoip
sudo wget "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=YOUR_KEY&suffix=tar.gz"
sudo tar -xzf GeoLite2-City_*.tar.gz
sudo mv GeoLite2-City_*/GeoLite2-City.mmdb .
sudo chown siem:siem GeoLite2-City.mmdb
```

## Service Management

### SIEM Services

```bash
# Check status
sudo systemctl status siem-server
sudo systemctl status siem-worker
sudo systemctl status siem-scheduler

# Start/Stop/Restart
sudo systemctl start siem-server
sudo systemctl stop siem-worker
sudo systemctl restart siem-scheduler

# View logs
sudo journalctl -u siem-server -f
sudo journalctl -u siem-worker -f
```

### Database Services

```bash
# PostgreSQL
sudo systemctl status postgresql
sudo systemctl restart postgresql

# Redis
sudo systemctl status redis-server
sudo systemctl restart redis-server

# RabbitMQ
sudo systemctl status rabbitmq-server
sudo systemctl restart rabbitmq-server
```

## Monitoring and Maintenance

### Health Checks

The SIEM includes health monitoring endpoints:
- Web UI: `http://your-server/health`
- API: `http://your-server/api/health`

### Log Locations

- **SIEM Application**: `/var/log/siem/`
- **Nginx**: `/var/log/nginx/`
- **PostgreSQL**: `/var/log/postgresql/`
- **System logs**: `journalctl -u siem-*`

### Backup Procedures

**Database Backup:**
```bash
# Create backup
sudo -u postgres pg_dump siem > siem_backup_$(date +%Y%m%d).sql

# Restore backup
sudo -u postgres psql siem < siem_backup_20250713.sql
```

**Configuration Backup:**
```bash
# Backup configuration
sudo tar -czf siem_config_backup.tar.gz /etc/siem/ /opt/siem/
```

### Performance Tuning

**PostgreSQL Optimization:**
```sql
-- Update postgresql.conf
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB
```

**Redis Optimization:**
```bash
# Edit /etc/redis/redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru
```

## Troubleshooting

### Common Issues

**1. Service won't start:**
```bash
# Check service status
sudo systemctl status siem-server

# Check logs for errors
sudo journalctl -u siem-server -n 50

# Check configuration
sudo nginx -t
```

**2. Database connection errors:**
```bash
# Test database connection
sudo -u siem psql "postgresql://siem_user:password@localhost:5432/siem"

# Check PostgreSQL status
sudo systemctl status postgresql
```

**3. Agent connection issues:**
```bash
# Test API endpoint
curl -X POST http://your-server:5000/api/ingest \
  -H "Authorization: Bearer your-api-token" \
  -H "Content-Type: application/json" \
  -d '{"source":"test","host":"test","payload":{"raw":"test log"}}'
```

**4. Memory issues:**
```bash
# Check system resources
free -h
df -h
top -p $(pgrep -f siem)

# Restart services if needed
sudo systemctl restart siem-worker
```

### Log Analysis

**Check for errors:**
```bash
# Application errors
sudo grep -i error /var/log/siem/*.log

# System errors
sudo journalctl --since "1 hour ago" | grep -i error

# Database errors
sudo tail -f /var/log/postgresql/postgresql-*.log
```

## Production Deployment Best Practices

### Security Hardening

1. **Change all default passwords**
2. **Configure SSL/TLS encryption**
3. **Set up firewall rules**
4. **Regular security updates**
5. **Monitor access logs**

### High Availability

1. **Database replication**
2. **Load balancing**
3. **Service monitoring**
4. **Automated backups**
5. **Disaster recovery plan**

### Scaling Guidelines

**Vertical Scaling:**
- Increase CPU and memory for single-server deployment
- Optimize database performance
- Tune worker processes

**Horizontal Scaling:**
- Separate database server
- Multiple SIEM worker nodes
- Load balancer for web interface
- Redis clustering for message queue

## Support and Documentation

- **Project Repository**: https://github.com/your-org/siem-platform
- **Issue Tracker**: https://github.com/your-org/siem-platform/issues
- **Documentation**: https://docs.your-org.com/siem
- **Community**: https://community.your-org.com/siem

For technical support, please create an issue in the GitHub repository with:
- System information (`uname -a`)
- Service logs (`journalctl -u siem-server`)
- Configuration details (sanitized)
- Steps to reproduce the issue