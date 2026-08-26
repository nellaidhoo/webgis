"""
Rate limiting middleware for WebGIS API endpoints.
Uses Django's cache framework for simplicity (no external dependencies).
"""
from django.core.cache import cache
from django.http import JsonResponse
import time


class RateLimitMiddleware:
    """
    Simple rate limiting middleware.
    
    Usage: Add to MIDDLEWARE in settings.py
    Configure RATE_LIMITS in settings.py:
        RATE_LIMITS = {
            'auth': {'requests': 10, 'window': 60},  # 10 requests per minute
            'upload': {'requests': 5, 'window': 300},  # 5 requests per 5 minutes
            'search': {'requests': 30, 'window': 60},  # 30 requests per minute
            'default': {'requests': 60, 'window': 60},  # 60 requests per minute
        }
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self._rate_limits = None

    @property
    def rate_limits(self):
        if self._rate_limits is None:
            from django.conf import settings
            self._rate_limits = getattr(settings, 'RATE_LIMITS', {
                'auth': {'requests': 10, 'window': 60},
                'upload': {'requests': 5, 'window': 300},
                'search': {'requests': 30, 'window': 60},
                'default': {'requests': 60, 'window': 60},
            })
        return self._rate_limits
    
    def __call__(self, request):
        # Skip rate limiting for non-API requests
        if not request.path.startswith('/api/'):
            return self.get_response(request)
        
        # Determine rate limit category
        category = self.get_category(request)
        limits = self.rate_limits.get(category, self.rate_limits.get('default', {'requests': 60, 'window': 60}))
        
        # Get client identifier
        client_id = self.get_client_id(request)
        
        # Check rate limit
        if self.is_rate_limited(client_id, category, limits):
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'category': category,
                'limit': limits['requests'],
                'window': limits['window'],
                'retry_after': self.get_retry_after(client_id, category)
            }, status=429)
        
        # Record this request
        self.record_request(client_id, category, limits)
        
        return self.get_response(request)
    
    def get_category(self, request):
        """Determine rate limit category based on request path."""
        path = request.path.lower()
        
        if '/auth/' in path:
            return 'auth'
        elif '/import/' in path and request.method == 'POST':
            return 'upload'
        elif '/search/' in path:
            return 'search'
        else:
            return 'default'
    
    def get_client_id(self, request):
        """Get unique client identifier (IP + user agent)."""
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:50]
        return f"{ip}:{user_agent}"
    
    def is_rate_limited(self, client_id, category, limits):
        """Check if client has exceeded rate limit."""
        cache_key = f"ratelimit:{category}:{client_id}"
        requests = cache.get(cache_key, [])
        
        now = time.time()
        window = limits['window']
        
        # Filter requests within current window
        recent_requests = [r for r in requests if now - r < window]
        
        return len(recent_requests) >= limits['requests']
    
    def record_request(self, client_id, category, limits):
        """Record this request in the cache."""
        cache_key = f"ratelimit:{category}:{client_id}"
        requests = cache.get(cache_key, [])
        
        now = time.time()
        window = limits['window']
        
        # Filter requests within current window and add new one
        recent_requests = [r for r in requests if now - r < window]
        recent_requests.append(now)
        
        # Store with TTL equal to window
        cache.set(cache_key, recent_requests, limits['window'])
    
    def get_retry_after(self, client_id, category):
        """Calculate seconds until next request is allowed."""
        cache_key = f"ratelimit:{category}:{client_id}"
        requests = cache.get(cache_key, [])
        
        if not requests:
            return 0
        
        oldest = min(requests)
        return max(0, int(oldest + self.rate_limits[category]['window'] - time.time()))
