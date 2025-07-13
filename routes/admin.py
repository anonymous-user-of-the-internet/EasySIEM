"""
Admin routes for SIEM management
"""

import os
import zipfile
import tempfile
from flask import Blueprint, render_template, request, jsonify, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin privileges required', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/agent-generator')
@login_required
@admin_required
def agent_generator():
    """Agent generator page"""
    return render_template('admin/agent_generator.html')

@admin_bp.route('/generate-agent', methods=['POST'])
@login_required
@admin_required
def generate_agent():
    """Generate and download customized agent package"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['siem_endpoint', 'api_token', 'agent_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Generate configuration
        config_content = generate_agent_config(data)
        
        # Create agent package
        package_path = create_agent_package(config_content, data.get('agent_id', 'siem-agent'))
        
        return send_file(
            package_path,
            as_attachment=True,
            download_name=f"siem-agent-{data.get('agent_id', 'package')}.zip",
            mimetype='application/zip'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_agent_config(data):
    """Generate agent configuration YAML"""
    log_sources = data.get('log_sources', [])
    syslog_ports = data.get('syslog_ports', [])
    
    # Build file sources
    file_sources_yaml = ""
    if log_sources:
        file_sources_yaml = "file_sources:\n"
        for source in log_sources:
            if source.get('path'):
                file_sources_yaml += f'  - name: "{source.get("name", "custom")}"\n'
                file_sources_yaml += f'    path: "{source["path"]}"\n'
    
    # Build syslog sources
    syslog_sources_yaml = ""
    if syslog_ports:
        syslog_sources_yaml = "syslog_sources:\n"
        for port_config in syslog_ports:
            port = port_config.get('port')
            if port:
                syslog_sources_yaml += f'  - name: "syslog-{port}"\n'
                syslog_sources_yaml += f'    port: {port}\n'
    
    config_template = f"""# SIEM Agent Configuration File
# Generated automatically for {data.get('agent_id', 'agent')}

# SIEM Platform Connection
siem_endpoint: "{data['siem_endpoint']}"
api_token: "{data['api_token']}"

# Batch Settings
batch_size: {data.get('batch_size', 10)}
batch_timeout: {data.get('batch_timeout', 5)}

# Log Sources
{file_sources_yaml}

# Syslog Listeners
{syslog_sources_yaml}

# Systemd Journal Integration
systemd_journal:
  enabled: {str(data.get('systemd_enabled', True)).lower()}

# Log Level
log_level: "{data.get('log_level', 'INFO')}"

# Agent Identification
agent_id: "{data['agent_id']}"

# Connection Settings
connection:
  timeout: {data.get('timeout', 10)}
  retry_attempts: {data.get('retry_attempts', 3)}
  retry_delay: {data.get('retry_delay', 5)}

# Security Settings
security:
  verify_ssl: {str(data.get('verify_ssl', True)).lower()}
  ca_cert_path: {f'"{data["ca_cert_path"]}"' if data.get('ca_cert_path') else 'null'}
"""
    
    return config_template

def create_agent_package(config_content, agent_id):
    """Create agent installation package"""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    package_path = os.path.join(temp_dir, f'siem-agent-{agent_id}.zip')
    
    with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add agent script
        agent_script_path = os.path.join(os.path.dirname(__file__), '..', 'agent', 'siem_agent.py')
        zipf.write(agent_script_path, 'siem_agent.py')
        
        # Add configuration
        zipf.writestr('config.yaml', config_content)
        
        # Add installation script
        install_script_path = os.path.join(os.path.dirname(__file__), '..', 'agent', 'install.sh')
        zipf.write(install_script_path, 'install.sh')
        
        # Add systemd service file
        service_path = os.path.join(os.path.dirname(__file__), '..', 'agent', 'siem-agent.service')
        zipf.write(service_path, 'siem-agent.service')
        
        # Add README
        readme_content = f"""# SIEM Agent Installation Package
# Generated for: {agent_id}

## Installation Instructions

1. Extract this package to a temporary directory
2. Make the installation script executable:
   chmod +x install.sh

3. Run the installation script as root:
   sudo ./install.sh

4. The agent will be installed and started automatically

## Configuration

The agent is pre-configured with your settings. 
Configuration file location: /etc/siem-agent/config.yaml

## Service Management

- Start: sudo systemctl start siem-agent
- Stop: sudo systemctl stop siem-agent  
- Status: sudo systemctl status siem-agent
- Logs: sudo journalctl -u siem-agent -f

## Support

Check the SIEM dashboard for incoming events after installation.
"""
        zipf.writestr('README.txt', readme_content)
    
    return package_path