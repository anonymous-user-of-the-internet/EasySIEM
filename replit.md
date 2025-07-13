# SIEM Platform - Security Information & Event Management

## Overview
This is a comprehensive SIEM (Security Information & Event Management) platform built with Python, Flask, and PostgreSQL. The system provides real-time log collection, parsing, enrichment, alerting, and dashboard visualization for security monitoring and incident response.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Core Architecture Pattern
The system follows a microservices-inspired architecture with event-driven processing:

1. **Agent-based log collection** - Lightweight Python agents collect logs from various sources
2. **Message queue ingestion** - RabbitMQ handles reliable event routing and buffering
3. **Asynchronous processing** - Celery workers handle parsing, enrichment, and alerting
4. **Web dashboard** - Flask web application provides user interface and API endpoints
5. **PostgreSQL storage** - Partitioned tables for efficient storage and querying

### Technology Stack
- **Backend**: Flask (Python web framework)
- **Database**: PostgreSQL with table partitioning
- **Message Broker**: RabbitMQ for event queuing
- **Task Queue**: Celery with Redis backend
- **Frontend**: Bootstrap with Chart.js for visualization
- **Authentication**: Flask-Login for session management

## Key Components

### 1. Log Collection Agents (`agent/siem_agent.py`)
- **Purpose**: Collect logs from various sources (files, syslog, Windows events, APIs)
- **Key Features**:
  - File tailing with inotify
  - UDP/TCP syslog listeners
  - Configurable via YAML
  - Reliable forwarding to SIEM platform
- **Architecture Decision**: Lightweight agents minimize resource impact on monitored systems

### 2. Ingestion Service (`services/ingestion.py`)
- **Purpose**: Receive events from agents and queue for processing
- **Key Features**:
  - REST API endpoint for agent communication
  - Token-based authentication
  - Raw event storage in PostgreSQL
  - RabbitMQ message publishing
- **Architecture Decision**: Separate ingestion from processing for scalability and reliability

### 3. Event Processing Pipeline
- **Parser Service** (`services/parser.py`): Extract structured data from raw logs using regex patterns
- **Enrichment Service** (`services/enrichment.py`): Add context (GeoIP, threat intel, DNS resolution)
- **Alert Engine** (`services/alert_engine.py`): Evaluate rules and generate alerts

### 4. Web Dashboard (`routes/`)
- **Authentication**: Login/logout with session management
- **Dashboard**: Real-time statistics and charts
- **Events**: Searchable event browser with filtering
- **Alerts**: Alert management and rule configuration

### 5. Background Workers (`celery_worker.py`)
- **Parsing Queue**: Process raw events into structured format
- **Enrichment Queue**: Add contextual information
- **Alerting Queue**: Evaluate alert rules
- **Maintenance Queue**: Cleanup and archival tasks

## Data Flow

1. **Collection**: Agents collect logs and send to `/ingest` API endpoint
2. **Ingestion**: Raw events stored in `events_raw` table and published to RabbitMQ
3. **Parsing**: Celery workers parse raw events using pattern matching
4. **Enrichment**: Additional context added (GeoIP, threat intelligence)
5. **Storage**: Enriched events stored in `events_enriched` table
6. **Alerting**: Rules evaluated against enriched events
7. **Visualization**: Web dashboard queries enriched events for display

### Database Schema
- **events_raw**: Raw event storage with JSON payload
- **events_enriched**: Parsed and enriched events with structured fields
- **alert_rules**: Configurable alerting rules
- **alert_events**: Generated alerts
- **users**: Authentication and authorization

## External Dependencies

### Required Services
- **PostgreSQL**: Primary data storage with partitioning support
- **RabbitMQ**: Message queuing for reliable event processing
- **Redis**: Celery task queue backend and caching

### Optional Integrations
- **MaxMind GeoIP**: IP geolocation enrichment
- **SMTP Server**: Email alert notifications
- **Threat Intelligence**: External threat feed integration

### Python Libraries
- Flask ecosystem (Flask, Flask-Login, Flask-SQLAlchemy)
- Celery for background processing
- Pika for RabbitMQ communication
- SQLAlchemy for database ORM
- Requests for HTTP client functionality

## Deployment Strategy

### Environment Configuration
- **Database**: PostgreSQL with connection pooling and partitioning
- **Message Broker**: RabbitMQ with durable queues and topic exchanges
- **Worker Scaling**: Multiple Celery workers can be deployed for horizontal scaling
- **Web Server**: Flask with Gunicorn for production deployment

### Security Considerations
- Token-based authentication for agents
- Session-based authentication for web users
- Admin privileges for sensitive operations
- Input validation and SQL injection prevention

### Operational Features
- **Health Monitoring**: System health checks and statistics
- **Data Retention**: Configurable retention policies with archival
- **Performance**: Database indexing and query optimization
- **Reliability**: Message persistence and worker failure recovery

The architecture prioritizes scalability, reliability, and ease of deployment while maintaining security best practices for handling sensitive log data.