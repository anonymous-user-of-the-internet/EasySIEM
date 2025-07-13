import json
import re
import yaml
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

class EventParser:
    def __init__(self):
        self.patterns = self._load_grok_patterns()
    
    def _load_grok_patterns(self):
        """
        Load Grok-like parsing patterns from configuration
        """
        patterns = {
            'ssh_failed': {
                'pattern': r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+sshd\[\d+\]:\s+Failed password for (?P<user>\S+) from (?P<src_ip>\d+\.\d+\.\d+\.\d+)',
                'event_type': 'ssh_login_failed'
            },
            'ssh_success': {
                'pattern': r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+sshd\[\d+\]:\s+Accepted password for (?P<user>\S+) from (?P<src_ip>\d+\.\d+\.\d+\.\d+)',
                'event_type': 'ssh_login_success'
            },
            'apache_access': {
                'pattern': r'(?P<src_ip>\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[(?P<timestamp>[^\]]+)\]\s+"(?P<method>\S+)\s+(?P<url>\S+)\s+HTTP/[^"]+"\s+(?P<status>\d+)\s+(?P<size>\d+)',
                'event_type': 'web_access'
            },
            'syslog_generic': {
                'pattern': r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<process>\S+):\s+(?P<message>.*)',
                'event_type': 'syslog'
            }
        }
        return patterns
    
    def parse_message(self, raw_message):
        """
        Parse a raw message and extract structured data
        """
        try:
            payload = raw_message['payload']
            raw_text = payload.get('raw', '')
            
            # Try to parse as JSON first
            if self._is_json(raw_text):
                parsed_data = json.loads(raw_text)
                return {
                    'event_type': parsed_data.get('event_type', 'json_event'),
                    'timestamp': self._parse_timestamp(parsed_data.get('timestamp')),
                    'fields': parsed_data,
                    'message': str(parsed_data)
                }
            
            # Try grok patterns
            for pattern_name, pattern_config in self.patterns.items():
                match = re.search(pattern_config['pattern'], raw_text)
                if match:
                    fields = match.groupdict()
                    return {
                        'event_type': pattern_config['event_type'],
                        'timestamp': self._parse_timestamp(fields.get('timestamp')),
                        'fields': fields,
                        'message': raw_text
                    }
            
            # Fallback to generic parsing
            return {
                'event_type': 'unknown',
                'timestamp': datetime.now(timezone.utc),
                'fields': {'raw': raw_text},
                'message': raw_text
            }
            
        except Exception as e:
            logger.error(f"Error parsing message: {str(e)}")
            return {
                'event_type': 'parse_error',
                'timestamp': datetime.now(timezone.utc),
                'fields': {'error': str(e), 'raw': raw_message.get('payload', {}).get('raw', '')},
                'message': f"Parse error: {str(e)}"
            }
    
    def _is_json(self, text):
        """
        Check if text is valid JSON
        """
        try:
            json.loads(text)
            return True
        except (ValueError, TypeError):
            return False
    
    def _parse_timestamp(self, timestamp_str):
        """
        Parse various timestamp formats
        """
        if not timestamp_str:
            return datetime.now(timezone.utc)
        
        # Try different timestamp formats
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%b %d %H:%M:%S',  # syslog format
            '%d/%b/%Y:%H:%M:%S %z',  # Apache format
        ]
        
        for fmt in formats:
            try:
                if fmt == '%b %d %H:%M:%S':
                    # Add current year for syslog format
                    timestamp_str = f"{datetime.now().year} {timestamp_str}"
                    fmt = '%Y %b %d %H:%M:%S'
                
                parsed = datetime.strptime(timestamp_str, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
        
        # If all else fails, return current time
        logger.warning(f"Could not parse timestamp: {timestamp_str}")
        return datetime.now(timezone.utc)
    
    def normalize_fields(self, parsed_event):
        """
        Normalize field names and values
        """
        normalized = parsed_event.copy()
        fields = normalized.get('fields', {})
        
        # Normalize common field names
        field_mappings = {
            'user': 'username',
            'source_ip': 'src_ip',
            'dest_ip': 'dst_ip',
            'source_port': 'src_port',
            'dest_port': 'dst_port'
        }
        
        for old_name, new_name in field_mappings.items():
            if old_name in fields:
                fields[new_name] = fields.pop(old_name)
        
        normalized['fields'] = fields
        return normalized
