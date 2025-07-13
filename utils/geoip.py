"""
GeoIP Lookup Utility
Provides IP geolocation services using MaxMind GeoLite2 database
"""

import os
import logging
import ipaddress
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

try:
    import maxminddb
    MAXMIND_AVAILABLE = True
except ImportError:
    MAXMIND_AVAILABLE = False
    logger.warning("maxminddb library not available. GeoIP lookups will be disabled.")

class GeoIPLookup:
    """
    GeoIP lookup service using MaxMind GeoLite2 database
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get('GEOIP_DB_PATH', '/opt/geoip/GeoLite2-City.mmdb')
        self.reader = None
        self._initialize_reader()
    
    def _initialize_reader(self):
        """Initialize the MaxMind database reader"""
        if not MAXMIND_AVAILABLE:
            logger.warning("MaxMind library not available, GeoIP lookups disabled")
            return
        
        try:
            if os.path.exists(self.db_path):
                self.reader = maxminddb.open_database(self.db_path)
                logger.info(f"GeoIP database loaded from {self.db_path}")
            else:
                logger.warning(f"GeoIP database not found at {self.db_path}")
                logger.info("To enable GeoIP lookups:")
                logger.info("1. Download GeoLite2-City.mmdb from MaxMind")
                logger.info("2. Place it at /opt/geoip/GeoLite2-City.mmdb")
                logger.info("3. Or set GEOIP_DB_PATH environment variable")
        except Exception as e:
            logger.error(f"Error loading GeoIP database: {e}")
    
    def lookup(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """
        Perform GeoIP lookup for an IP address
        
        Args:
            ip_address: The IP address to lookup
            
        Returns:
            Dictionary containing geolocation data or None if lookup fails
        """
        if not self.reader:
            return None
        
        try:
            # Validate IP address
            ip_obj = ipaddress.ip_address(ip_address)
            
            # Skip private/local addresses
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                return {
                    'country': 'Private/Local',
                    'country_code': 'XX',
                    'city': 'Private/Local',
                    'latitude': None,
                    'longitude': None,
                    'accuracy_radius': None,
                    'is_private': True
                }
            
            # Perform lookup
            result = self.reader.get(ip_address)
            if not result:
                return None
            
            # Extract relevant information
            geo_data = {
                'country': self._safe_get(result, 'country', 'names', 'en', default='Unknown'),
                'country_code': self._safe_get(result, 'country', 'iso_code', default='XX'),
                'city': self._safe_get(result, 'city', 'names', 'en', default='Unknown'),
                'latitude': self._safe_get(result, 'location', 'latitude'),
                'longitude': self._safe_get(result, 'location', 'longitude'),
                'accuracy_radius': self._safe_get(result, 'location', 'accuracy_radius'),
                'timezone': self._safe_get(result, 'location', 'time_zone'),
                'is_private': False
            }
            
            # Add subdivision (state/province) if available
            subdivisions = result.get('subdivisions', [])
            if subdivisions:
                geo_data['subdivision'] = subdivisions[0].get('names', {}).get('en', 'Unknown')
                geo_data['subdivision_code'] = subdivisions[0].get('iso_code', '')
            
            # Add postal code if available
            if 'postal' in result:
                geo_data['postal_code'] = result['postal'].get('code', '')
            
            # Add ASN information if available (from GeoLite2-ASN database)
            if 'autonomous_system_number' in result:
                geo_data['asn'] = result.get('autonomous_system_number')
                geo_data['asn_organization'] = result.get('autonomous_system_organization', '')
            
            return geo_data
            
        except ValueError as e:
            logger.warning(f"Invalid IP address format: {ip_address}")
            return None
        except Exception as e:
            logger.error(f"Error performing GeoIP lookup for {ip_address}: {e}")
            return None
    
    def _safe_get(self, data: Dict, *keys, default=None):
        """
        Safely traverse nested dictionary keys
        
        Args:
            data: Dictionary to traverse
            *keys: Keys to traverse in order
            default: Default value if key path doesn't exist
            
        Returns:
            Value at the key path or default
        """
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def lookup_batch(self, ip_addresses: list) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Perform batch GeoIP lookups
        
        Args:
            ip_addresses: List of IP addresses to lookup
            
        Returns:
            Dictionary mapping IP addresses to their geolocation data
        """
        results = {}
        for ip in ip_addresses:
            results[ip] = self.lookup(ip)
        return results
    
    def is_available(self) -> bool:
        """
        Check if GeoIP lookups are available
        
        Returns:
            True if GeoIP database is loaded and ready
        """
        return self.reader is not None
    
    def get_database_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the loaded GeoIP database
        
        Returns:
            Dictionary containing database metadata or None
        """
        if not self.reader:
            return None
        
        try:
            metadata = self.reader.metadata()
            return {
                'database_type': metadata.database_type,
                'binary_format_major_version': metadata.binary_format_major_version,
                'binary_format_minor_version': metadata.binary_format_minor_version,
                'build_epoch': metadata.build_epoch,
                'description': metadata.description,
                'ip_version': metadata.ip_version,
                'languages': metadata.languages,
                'node_count': metadata.node_count,
                'record_size': metadata.record_size
            }
        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return None
    
    def close(self):
        """Close the GeoIP database reader"""
        if self.reader:
            self.reader.close()
            self.reader = None
            logger.info("GeoIP database reader closed")


# Singleton instance for global use
_geoip_instance = None

def get_geoip_instance() -> GeoIPLookup:
    """
    Get a singleton instance of GeoIPLookup
    
    Returns:
        GeoIPLookup instance
    """
    global _geoip_instance
    if _geoip_instance is None:
        _geoip_instance = GeoIPLookup()
    return _geoip_instance

def lookup_ip(ip_address: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function for single IP lookup
    
    Args:
        ip_address: IP address to lookup
        
    Returns:
        Geolocation data or None
    """
    return get_geoip_instance().lookup(ip_address)

def is_geoip_available() -> bool:
    """
    Check if GeoIP lookups are available
    
    Returns:
        True if GeoIP is available
    """
    return get_geoip_instance().is_available()
