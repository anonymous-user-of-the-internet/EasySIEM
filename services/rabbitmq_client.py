import pika
import json
import logging
from flask import current_app

logger = logging.getLogger(__name__)

class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self._connect()
    
    def _connect(self):
        """
        Connect to RabbitMQ
        """
        try:
            rabbitmq_url = current_app.config.get('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
            connection_params = pika.URLParameters(rabbitmq_url)
            self.connection = pika.BlockingConnection(connection_params)
            self.channel = self.connection.channel()
            
            # Declare exchanges and queues
            self._setup_exchanges_and_queues()
            
            logger.info("Connected to RabbitMQ")
            
        except Exception as e:
            logger.error(f"Error connecting to RabbitMQ: {str(e)}")
            raise
    
    def _setup_exchanges_and_queues(self):
        """
        Setup RabbitMQ exchanges and queues
        """
        # Declare topic exchange for raw logs
        self.channel.exchange_declare(
            exchange='logs.raw',
            exchange_type='topic',
            durable=True
        )
        
        # Declare queues for different log sources
        queues = ['syslog', 'apache', 'ssh', 'firewall']
        
        for queue_name in queues:
            queue_full_name = f'q.raw.{queue_name}'
            self.channel.queue_declare(queue=queue_full_name, durable=True)
            
            # Bind queue to exchange with routing key
            self.channel.queue_bind(
                exchange='logs.raw',
                queue=queue_full_name,
                routing_key=f'raw.{queue_name}'
            )
        
        # Generic queue for unknown sources
        self.channel.queue_declare(queue='q.raw.unknown', durable=True)
        self.channel.queue_bind(
            exchange='logs.raw',
            queue='q.raw.unknown',
            routing_key='raw.*'
        )
    
    def publish_message(self, exchange, routing_key, message):
        """
        Publish a message to RabbitMQ
        """
        try:
            if not self.connection or self.connection.is_closed:
                self._connect()
            
            self.channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                )
            )
            
        except Exception as e:
            logger.error(f"Error publishing message: {str(e)}")
            raise
    
    def consume_messages(self, queue_name, callback):
        """
        Consume messages from a queue
        """
        try:
            if not self.connection or self.connection.is_closed:
                self._connect()
            
            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(
                queue=queue_name,
                on_message_callback=callback
            )
            
            logger.info(f"Starting to consume from queue: {queue_name}")
            self.channel.start_consuming()
            
        except Exception as e:
            logger.error(f"Error consuming messages: {str(e)}")
            raise
    
    def close(self):
        """
        Close RabbitMQ connection
        """
        if self.connection and not self.connection.is_closed:
            self.connection.close()
