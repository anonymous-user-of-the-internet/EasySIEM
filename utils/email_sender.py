"""
Email Sender Utility
Handles email notifications for SIEM alerts
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailSender:
    """
    Email sender for SIEM alert notifications
    """
    
    def __init__(self, smtp_server: Optional[str] = None, smtp_port: Optional[int] = None,
                 username: Optional[str] = None, password: Optional[str] = None,
                 use_tls: bool = True, from_email: Optional[str] = None):
        """
        Initialize email sender
        
        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            username: SMTP authentication username
            password: SMTP authentication password
            use_tls: Whether to use TLS encryption
            from_email: From email address
        """
        self.smtp_server = smtp_server or os.environ.get('SMTP_SERVER', 'localhost')
        self.smtp_port = smtp_port or int(os.environ.get('SMTP_PORT', '587'))
        self.username = username or os.environ.get('SMTP_USERNAME', '')
        self.password = password or os.environ.get('SMTP_PASSWORD', '')
        self.use_tls = use_tls
        self.from_email = from_email or os.environ.get('ALERT_FROM_EMAIL', 'alerts@siem.local')
        
        logger.info(f"Email sender initialized with server: {self.smtp_server}:{self.smtp_port}")
    
    def send_email(self, recipients: List[str], subject: str, body: str,
                   html_body: Optional[str] = None, attachments: Optional[List[str]] = None) -> bool:
        """
        Send an email
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            body: Plain text email body
            html_body: HTML email body (optional)
            attachments: List of file paths to attach (optional)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            msg['Date'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            # Add plain text body
            text_part = MIMEText(body, 'plain')
            msg.attach(text_part)
            
            # Add HTML body if provided
            if html_body:
                html_part = MIMEText(html_body, 'html')
                msg.attach(html_part)
            
            # Add attachments if provided
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        self._attach_file(msg, file_path)
                    else:
                        logger.warning(f"Attachment file not found: {file_path}")
            
            # Send email
            return self._send_message(msg, recipients)
            
        except Exception as e:
            logger.error(f"Error creating email: {e}")
            return False
    
    def send_alert_email(self, recipients: List[str], alert_data: Dict[str, Any]) -> bool:
        """
        Send a formatted alert email
        
        Args:
            recipients: List of recipient email addresses
            alert_data: Dictionary containing alert information
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            # Extract alert information
            rule_name = alert_data.get('rule_name', 'Unknown Rule')
            event_count = alert_data.get('event_count', 0)
            threshold = alert_data.get('threshold', 0)
            time_window = alert_data.get('time_window', 0)
            triggered_at = alert_data.get('triggered_at', datetime.utcnow())
            rule_description = alert_data.get('rule_description', '')
            
            # Create subject
            subject = f"SIEM Alert: {rule_name}"
            
            # Create plain text body
            body = f"""
SECURITY ALERT

Alert Rule: {rule_name}
Description: {rule_description}

Event Details:
- Threshold: {threshold} events in {time_window} minutes
- Actual Count: {event_count} events
- Triggered At: {triggered_at}

Please investigate this security event immediately.

---
This is an automated message from the SIEM platform.
            """.strip()
            
            # Create HTML body
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .alert-box {{ 
                        background-color: #f8d7da; 
                        border: 1px solid #f5c6cb; 
                        color: #721c24; 
                        padding: 15px; 
                        border-radius: 5px; 
                        margin-bottom: 20px;
                    }}
                    .details {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
                    .metric {{ margin: 5px 0; }}
                    .footer {{ margin-top: 20px; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="alert-box">
                    <h2>🚨 SECURITY ALERT</h2>
                    <h3>{rule_name}</h3>
                </div>
                
                <div class="details">
                    <h4>Alert Details</h4>
                    <div class="metric"><strong>Description:</strong> {rule_description}</div>
                    <div class="metric"><strong>Threshold:</strong> {threshold} events in {time_window} minutes</div>
                    <div class="metric"><strong>Actual Count:</strong> {event_count} events</div>
                    <div class="metric"><strong>Triggered At:</strong> {triggered_at}</div>
                </div>
                
                <p><strong>Action Required:</strong> Please investigate this security event immediately.</p>
                
                <div class="footer">
                    This is an automated message from the SIEM platform.
                </div>
            </body>
            </html>
            """
            
            return self.send_email(recipients, subject, body, html_body)
            
        except Exception as e:
            logger.error(f"Error sending alert email: {e}")
            return False
    
    def send_system_health_email(self, recipients: List[str], health_data: Dict[str, Any]) -> bool:
        """
        Send a system health notification email
        
        Args:
            recipients: List of recipient email addresses
            health_data: Dictionary containing system health information
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            status = health_data.get('status', 'unknown')
            component = health_data.get('component', 'system')
            metrics = health_data.get('metrics', {})
            timestamp = health_data.get('timestamp', datetime.utcnow())
            
            # Create subject based on status
            if status == 'critical':
                subject = f"🔴 CRITICAL: SIEM {component} Health Alert"
            elif status == 'warning':
                subject = f"🟡 WARNING: SIEM {component} Health Alert"
            else:
                subject = f"✅ INFO: SIEM {component} Health Update"
            
            # Create body
            body = f"""
SIEM SYSTEM HEALTH NOTIFICATION

Component: {component}
Status: {status.upper()}
Timestamp: {timestamp}

Metrics:
"""
            
            for key, value in metrics.items():
                body += f"- {key}: {value}\n"
            
            body += """
---
This is an automated message from the SIEM platform.
"""
            
            return self.send_email(recipients, subject, body)
            
        except Exception as e:
            logger.error(f"Error sending health email: {e}")
            return False
    
    def _attach_file(self, msg: MIMEMultipart, file_path: str):
        """
        Attach a file to the email message
        
        Args:
            msg: Email message object
            file_path: Path to file to attach
        """
        try:
            with open(file_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {os.path.basename(file_path)}'
            )
            
            msg.attach(part)
            
        except Exception as e:
            logger.error(f"Error attaching file {file_path}: {e}")
    
    def _send_message(self, msg: MIMEMultipart, recipients: List[str]) -> bool:
        """
        Send the email message
        
        Args:
            msg: Email message object
            recipients: List of recipient email addresses
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create SMTP connection
            if self.smtp_port == 465:
                # Use SSL
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                # Use regular connection, possibly with STARTTLS
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                if self.use_tls:
                    server.starttls()
            
            # Login if credentials provided
            if self.username and self.password:
                server.login(self.username, self.password)
            
            # Send email
            text = msg.as_string()
            server.sendmail(self.from_email, recipients, text)
            server.quit()
            
            logger.info(f"Email sent successfully to {recipients}")
            return True
            
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test the email connection and configuration
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                if self.use_tls:
                    server.starttls()
            
            if self.username and self.password:
                server.login(self.username, self.password)
            
            server.quit()
            logger.info("Email connection test successful")
            return True
            
        except Exception as e:
            logger.error(f"Email connection test failed: {e}")
            return False


# Singleton instance for global use
_email_instance = None

def get_email_sender() -> EmailSender:
    """
    Get a singleton instance of EmailSender
    
    Returns:
        EmailSender instance
    """
    global _email_instance
    if _email_instance is None:
        _email_instance = EmailSender()
    return _email_instance

def send_alert_notification(recipients: List[str], alert_data: Dict[str, Any]) -> bool:
    """
    Convenience function for sending alert notifications
    
    Args:
        recipients: List of recipient email addresses
        alert_data: Alert information dictionary
        
    Returns:
        True if sent successfully, False otherwise
    """
    return get_email_sender().send_alert_email(recipients, alert_data)

def test_email_configuration() -> bool:
    """
    Test the email configuration
    
    Returns:
        True if configuration is valid, False otherwise
    """
    return get_email_sender().test_connection()
