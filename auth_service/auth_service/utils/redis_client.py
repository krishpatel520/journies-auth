import redis
import json
from django.conf import settings
from auth_service.logger import logger_object

logger = logger_object('redis_client')


class RedisClient:
    """Redis client for publishing events to Redis Streams"""

    def __init__(self):
        """Initialize Redis connection"""
        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            # Test connection
            self.client.ping()
            logger.info(f"Redis connection successful - {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as e:
            logger.error(f"Redis connection failed: {str(e)}")
            self.client = None

    def publish_event(self, stream_name: str, data: dict, operation: str = "create"):
        """
        Publish event to Redis Stream (persistent)

        Args:
            stream_name: Redis stream name (e.g., 'journies:stream:users')
            data: Dictionary containing event data
            operation: Operation type - 'create', 'update', or 'delete'
        """
        if not self.client:
            logger.warning("Redis not available, skipping publish")
            return

        try:
            # Add operation and status fields for tracking
            data['operation'] = operation
            data['status'] = 'pending'

            # Convert all boolean values to strings (Redis only accepts strings, ints, floats, bytes)
            for key, value in data.items():
                if isinstance(value, bool):
                    data[key] = str(value)

            # Add event to stream (XADD)
            event_id = self.client.xadd(stream_name, data)
            logger.info(f"Published {operation} event to stream {stream_name} with ID {event_id}: {data}")
            return event_id
        except Exception as e:
            logger.error(f"Error publishing to Redis stream: {str(e)}")
            return None


# Global Redis client instance
redis_client = RedisClient()

