import redis
import json
from django.conf import settings
from auth_service.logger import logger_object

logger = logger_object('redis_client')


class RedisClient:
    """Redis client for publishing events to pub/sub channels"""
    
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
    
    def publish_event(self, channel: str, data: dict):
        """
        Publish event to Redis channel
        
        Args:
            channel: Redis channel name
            data: Dictionary containing event data
        """
        if not self.client:
            logger.warning("Redis not available, skipping publish")
            return
        
        try:
            message = json.dumps(data)
            self.client.publish(channel, message)
            logger.info(f"Published to {channel}: {data}")
        except Exception as e:
            logger.error(f"Error publishing to Redis: {str(e)}")


# Global Redis client instance
redis_client = RedisClient()

