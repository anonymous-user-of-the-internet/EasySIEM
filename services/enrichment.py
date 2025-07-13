import logging
import socket
import ipaddress
from datetime import datetime, timezone
from utils.geoip import GeoIPLookup
from app import db
from models import EventsEnriched

logger = logging.getLogger(__name__)

class EnrichmentService:
    def __init__(self):
        self.geoip = GeoIPLookup()
        self.dns_cache = {}
        self.threat_ips = self._load_threat_intel()
    
    def _load_threat_intel(self):
        """
        Load threat intelligence data (simplified for PoC)
        In production, this would fetch from threat feeds
        """
        # Sample malicious IPs for demo
        return {
            '192.168.1.100',  # Example malicious IP
            '10.0.0.99',      # Another example
        }
    
    def enrich_event(self, raw_id, parsed_event):
        """
        Enrich a parsed event with additional context
        """
        try:
            enrichment = {}
            fields = parsed_event.get('fields', {})
            
            # Extract IP addresses for enrichment
            ip_fields = ['src_ip', 'dst_ip', 'client_ip', 'remote_ip']
            for field in ip_fields:
                if field in fields:
                    ip = fields[field]
                    if self._is_valid_ip(ip):
                        enrichment[field] = self._enrich_ip(ip)
            
            # Add threat intelligence tags
            threat_tags = self._check_threat_intel(fields)
            if threat_tags:
                enrichment['threat_intel'] = threat_tags
            
            # Create enriched event record
            enriched_event = EventsEnriched(
                raw_id=raw_id,
                ts=parsed_event.get('timestamp', datetime.now(timezone.utc)),
                source=parsed_event.get('source', 'unknown'),
                host=parsed_event.get('host', 'unknown'),
                event_type=parsed_event.get('event_type', 'unknown'),
                message=parsed_event.get('message', ''),
                enrichment=enrichment,
                event_metadata=fields
            )
            
            db.session.add(enriched_event)
            db.session.commit()
            
            logger.info(f"Enriched event {enriched_event.id} from raw {raw_id}")
            return enriched_event
            
        except Exception as e:
            logger.error(f"Error enriching event {raw_id}: {str(e)}")
            db.session.rollback()
            raise
    
    def _is_valid_ip(self, ip_str):
        """
        Check if string is a valid IP address
        """
        try:
            ipaddress.ip_address(ip_str)
            return True
        except ValueError:
            return False
    
    def _enrich_ip(self, ip):
        """
        Enrich IP address with GeoIP and DNS data
        """
        enrichment = {}
        
        # GeoIP lookup
        try:
            geo_data = self.geoip.lookup(ip)
            if geo_data:
                enrichment['geoip'] = geo_data
        except Exception as e:
            logger.warning(f"GeoIP lookup failed for {ip}: {str(e)}")
        
        # DNS reverse lookup (with caching)
        if ip not in self.dns_cache:
            try:
                hostname = socket.gethostbyaddr(ip)[0]
                self.dns_cache[ip] = hostname
            except (socket.herror, socket.gaierror):
                self.dns_cache[ip] = None
        
        if self.dns_cache[ip]:
            enrichment['hostname'] = self.dns_cache[ip]
        
        return enrichment
    
    def _check_threat_intel(self, fields):
        """
        Check event fields against threat intelligence
        """
        tags = []
        
        # Check IPs against threat feed
        ip_fields = ['src_ip', 'dst_ip', 'client_ip', 'remote_ip']
        for field in ip_fields:
            if field in fields and fields[field] in self.threat_ips:
                tags.append('malicious_ip')
                break
        
        # Add more threat intel checks here
        # - Domain reputation
        # - File hashes
        # - User behavior analytics
        
        return tags
    
    def get_enrichment_stats(self):
        """
        Get enrichment statistics
        """
        try:
            from sqlalchemy import text
            
            result = db.session.execute(text("""
                SELECT 
                    COUNT(*) as total_enriched,
                    COUNT(CASE WHEN enrichment::text LIKE '%geoip%' THEN 1 END) as geoip_enriched,
                    COUNT(CASE WHEN enrichment::text LIKE '%threat_intel%' THEN 1 END) as threat_tagged
                FROM events_enriched 
                WHERE ts > NOW() - INTERVAL '24 hours'
            """)).fetchone()
            
            return {
                'total_enriched': result.total_enriched,
                'geoip_enriched': result.geoip_enriched,
                'threat_tagged': result.threat_tagged
            }
            
        except Exception as e:
            logger.error(f"Error getting enrichment stats: {str(e)}")
            return {}
