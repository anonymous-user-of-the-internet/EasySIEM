#!/usr/bin/env python3
"""
SIEM Agent - Log Collection and Forwarding Agent
Collects logs from various sources and forwards them to the SIEM platform
"""

import os
import sys
import time
import json
import yaml
import signal
import logging
import threading
import requests
import socket
from pathlib import Path
from datetime import datetime, timezone
from queue import Queue, Empty
import select
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/siem-agent.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('siem-agent')

class SIEMAgent:
    def __init__(self, config_path='/etc/siem-agent/config.yaml'):
        self.config_path = config_path
        self.config = self._load_config()
        self.running = False
        self.threads = []
        self.event_queue = Queue(maxsize=10000)
        self.hostname = socket.gethostname()
        
        # Statistics
        self.stats = {
            'events_collected': 0,
            'events_sent': 0,
            'events_failed': 0,
            'start_time': None
        }
        
        # Signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Validate required configuration
            required_fields = ['siem_endpoint', 'api_token']
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required configuration field: {field}")
            
            return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            sys.exit(1)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
    
    def start(self):
        """Start the SIEM agent"""
        logger.info("Starting SIEM Agent...")
        self.running = True
        self.stats['start_time'] = datetime.now(timezone.utc)
        
        try:
            # Start event sender thread
            sender_thread = threading.Thread(target=self._event_sender, daemon=True)
            sender_thread.start()
            self.threads.append(sender_thread)
            
            # Start file tail threads
            for source in self.config.get('file_sources', []):
                thread = threading.Thread(
                    target=self._tail_file,
                    args=(source['path'], source['name']),
                    daemon=True
                )
                thread.start()
                self.threads.append(thread)
            
            # Start syslog listener threads
            for source in self.config.get('syslog_sources', []):
                thread = threading.Thread(
                    target=self._listen_syslog,
                    args=(source['port'], source['name']),
                    daemon=True
                )
                thread.start()
                self.threads.append(thread)
            
            # Start journal reader if enabled
            if self.config.get('systemd_journal', {}).get('enabled', False):
                thread = threading.Thread(target=self._read_journal, daemon=True)
                thread.start()
                self.threads.append(thread)
            
            # Start statistics reporter
            stats_thread = threading.Thread(target=self._stats_reporter, daemon=True)
            stats_thread.start()
            self.threads.append(stats_thread)
            
            logger.info(f"SIEM Agent started with {len(self.threads)} threads")
            
            # Main loop - keep the process running
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error starting SIEM Agent: {e}")
            self.stop()
    
    def stop(self):
        """Stop the SIEM agent"""
        logger.info("Stopping SIEM Agent...")
        self.running = False
        
        # Wait for threads to finish (with timeout)
        for thread in self.threads:
            thread.join(timeout=5)
        
        # Send remaining events in queue
        self._flush_event_queue()
        
        logger.info("SIEM Agent stopped")
    
    def _tail_file(self, file_path, source_name):
        """Tail a log file and send new lines"""
        logger.info(f"Starting file tail for {file_path} (source: {source_name})")
        
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"Log file {file_path} does not exist, waiting...")
                while not file_path.exists() and self.running:
                    time.sleep(5)
            
            with open(file_path, 'r') as f:
                # Seek to end of file
                f.seek(0, 2)
                
                while self.running:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    
                    line = line.strip()
                    if line:
                        self._queue_event(source_name, line)
                        
        except Exception as e:
            logger.error(f"Error tailing file {file_path}: {e}")
    
    def _listen_syslog(self, port, source_name):
        """Listen for syslog messages on UDP port"""
        logger.info(f"Starting syslog listener on port {port} (source: {source_name})")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            sock.settimeout(1.0)
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(65535)
                    message = data.decode('utf-8', errors='ignore').strip()
                    if message:
                        self._queue_event(source_name, message, {'remote_addr': addr[0]})
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error receiving syslog message: {e}")
                    
        except Exception as e:
            logger.error(f"Error starting syslog listener on port {port}: {e}")
        finally:
            try:
                sock.close()
            except:
                pass
    
    def _read_journal(self):
        """Read systemd journal logs"""
        logger.info("Starting systemd journal reader")
        
        try:
            # Use journalctl to follow the journal
            cmd = ['journalctl', '-f', '--output=json', '--no-pager']
            
            # Add filters if specified
            journal_config = self.config.get('systemd_journal', {})
            if journal_config.get('units'):
                for unit in journal_config['units']:
                    cmd.extend(['-u', unit])
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            while self.running and process.poll() is None:
                try:
                    # Use select to check if data is available
                    ready, _, _ = select.select([process.stdout], [], [], 1.0)
                    if ready:
                        line = process.stdout.readline()
                        if line:
                            try:
                                journal_entry = json.loads(line.strip())
                                message = journal_entry.get('MESSAGE', '')
                                if message:
                                    metadata = {
                                        'unit': journal_entry.get('_SYSTEMD_UNIT', ''),
                                        'pid': journal_entry.get('_PID', ''),
                                        'priority': journal_entry.get('PRIORITY', '')
                                    }
                                    self._queue_event('systemd-journal', message, metadata)
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    logger.error(f"Error reading journal: {e}")
                    break
            
            process.terminate()
            
        except Exception as e:
            logger.error(f"Error starting journal reader: {e}")
    
    def _queue_event(self, source, raw_data, metadata=None):
        """Queue an event for sending to SIEM"""
        event = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'host': self.hostname,
            'source': source,
            'raw': raw_data,
            'agent_info': {
                'version': '1.0.0',
                'agent_id': self.hostname
            }
        }
        
        if metadata:
            event['agent_info'].update(metadata)
        
        try:
            self.event_queue.put(event, timeout=1)
            self.stats['events_collected'] += 1
        except:
            logger.warning("Event queue is full, dropping event")
    
    def _event_sender(self):
        """Send events to SIEM platform"""
        logger.info("Starting event sender thread")
        
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self.config['api_token']}"
        })
        
        batch_size = self.config.get('batch_size', 10)
        batch_timeout = self.config.get('batch_timeout', 5)
        
        events_batch = []
        last_send = time.time()
        
        while self.running or not self.event_queue.empty():
            try:
                # Get event with timeout
                event = self.event_queue.get(timeout=1)
                events_batch.append(event)
                
                # Send batch if size or timeout reached
                current_time = time.time()
                if (len(events_batch) >= batch_size or 
                    current_time - last_send >= batch_timeout):
                    
                    self._send_batch(session, events_batch)
                    events_batch = []
                    last_send = current_time
                    
            except Empty:
                # Timeout - send any pending events
                if events_batch:
                    self._send_batch(session, events_batch)
                    events_batch = []
                    last_send = time.time()
                continue
            except Exception as e:
                logger.error(f"Error in event sender: {e}")
                time.sleep(1)
        
        # Send any remaining events
        if events_batch:
            self._send_batch(session, events_batch)
    
    def _send_batch(self, session, events):
        """Send a batch of events to SIEM"""
        try:
            if len(events) == 1:
                # Send single event
                response = session.post(
                    self.config['siem_endpoint'],
                    json=events[0],
                    timeout=10
                )
            else:
                # Send batch (if batch endpoint exists)
                batch_endpoint = self.config.get('batch_endpoint', 
                                                self.config['siem_endpoint'] + '/batch')
                response = session.post(
                    batch_endpoint,
                    json={'events': events},
                    timeout=10
                )
            
            if response.status_code in [200, 201]:
                self.stats['events_sent'] += len(events)
                logger.debug(f"Successfully sent {len(events)} events")
            else:
                self.stats['events_failed'] += len(events)
                logger.error(f"Failed to send events: HTTP {response.status_code} - {response.text}")
                
        except Exception as e:
            self.stats['events_failed'] += len(events)
            logger.error(f"Error sending events to SIEM: {e}")
    
    def _flush_event_queue(self):
        """Flush remaining events in queue"""
        if self.event_queue.empty():
            return
        
        logger.info("Flushing remaining events...")
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self.config['api_token']}"
        })
        
        events = []
        while not self.event_queue.empty():
            try:
                events.append(self.event_queue.get_nowait())
                if len(events) >= 50:  # Send in chunks
                    self._send_batch(session, events)
                    events = []
            except Empty:
                break
        
        if events:
            self._send_batch(session, events)
    
    def _stats_reporter(self):
        """Report statistics periodically"""
        while self.running:
            time.sleep(60)  # Report every minute
            
            uptime = datetime.now(timezone.utc) - self.stats['start_time']
            logger.info(
                f"Agent Stats - Uptime: {uptime}, "
                f"Collected: {self.stats['events_collected']}, "
                f"Sent: {self.stats['events_sent']}, "
                f"Failed: {self.stats['events_failed']}, "
                f"Queue Size: {self.event_queue.qsize()}"
            )


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SIEM Log Collection Agent')
    parser.add_argument(
        '--config', 
        default='/etc/siem-agent/config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--test', 
        action='store_true',
        help='Test configuration and exit'
    )
    
    args = parser.parse_args()
    
    # Create agent
    agent = SIEMAgent(args.config)
    
    if args.test:
        logger.info("Configuration test successful")
        return 0
    
    try:
        agent.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
