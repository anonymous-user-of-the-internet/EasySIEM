#!/bin/sh

# Set default values for required environment variables
export DB_PASSWORD=${DB_PASSWORD:-siem_password}
export RABBITMQ_USER=${RABBITMQ_USER:-siem}
export RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD:-siem_password}
export SESSION_SECRET=${SESSION_SECRET:-$(openssl rand -hex 32)}

# Create necessary directories
mkdir -p logs

# Start all services with docker-compose
docker-compose up -d

# Wait for services to be healthy
echo "Waiting for services to be ready..."
sleep 30

# Initialize the database
docker-compose exec web python init_db.py

echo "
🎉 SIEM Platform is now running!

Access the services at:
- Web Interface: http://localhost:5000
- RabbitMQ Management: http://localhost:15672

Default Credentials:
- Web Interface: admin / admin123
- RabbitMQ: $RABBITMQ_USER / $RABBITMQ_PASSWORD

To view logs:
docker-compose logs -f

To stop the platform:
docker-compose down
"
