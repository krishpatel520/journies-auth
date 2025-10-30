from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware:
    """Rate limiting middleware to prevent API abuse"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Rate limit configurations
        self.limits = {
            '/api/v1/users/login/': {'requests': 5, 'window': 300},  # 5 requests per 5 minutes
            '/api/v1/users/signup/': {'requests': 3, 'window': 3600},  # 3 requests per hour
            '/api/v1/users/reset_password/': {'requests': 3, 'window': 3600},  # 3 requests per hour
            'default': {'requests': 100, 'window': 3600}  # 100 requests per hour for other endpoints
        }
    
    def __call__(self, request):
        # Get client IP
        ip = self.get_client_ip(request)
        
        # Check rate limit
        if self.is_rate_limited(request, ip):
            logger.warning(f"Rate limit exceeded for IP: {ip}, Path: {request.path}")
            return JsonResponse({
                'error': 'Rate limit exceeded. Please try again later.'
            }, status=429)
        
        response = self.get_response(request)
        return response
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def is_rate_limited(self, request, ip):
        """Check if request should be rate limited"""
        path = request.path
        
        # Get rate limit config for this path
        config = self.limits.get(path, self.limits['default'])
        
        # Create cache key
        cache_key = f"rate_limit:{ip}:{path}"
        
        # Get current request count
        current_requests = cache.get(cache_key, 0)
        
        # Check if limit exceeded
        if current_requests >= config['requests']:
            return True
        
        # Increment counter
        cache.set(cache_key, current_requests + 1, config['window'])
        
        return False