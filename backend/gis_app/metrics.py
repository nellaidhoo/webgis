"""
Simple cache-based metrics for WebGIS platform.
No external dependencies required - uses Django's cache framework.
"""
from django.core.cache import cache
from django.db import connection
import os

class MetricsCache:
    """Simple metrics storage using Django cache."""
    
    def __init__(self):
        self.prefix = 'metrics.'
    
    def increment(self, key, amount=1):
        """Increment a counter."""
        full_key = f"{self.prefix}{key}"
        current = cache.get(full_key, 0)
        cache.set(full_key, current + amount, 300)  # 5 min TTL
    
    def gauge(self, key, value):
        """Set a gauge value."""
        full_key = f"{self.prefix}{key}"
        cache.set(full_key, value, 300)
    
    def get_counter(self, key):
        """Get a counter value."""
        full_key = f"{self.prefix}{key}"
        return cache.get(full_key, 0)
    
    def get_gauge(self, key):
        """Get a gauge value."""
        full_key = f"{self.prefix}{key}"
        return cache.get(full_key, 0)
    
    def get_queue_depth(self):
        """Get current Celery queue depth."""
        try:
            # For filesystem broker
            broker_url = os.environ.get('CELERY_BROKER_URL', '')
            if 'filesystem://' in broker_url:
                data_out = '/opt/webgis/broker/data_out'
                if os.path.exists(data_out):
                    return len([f for f in os.listdir(data_out) if f.endswith('.msg')])
            
            # For Redis broker
            if 'redis://' in broker_url:
                import redis
                r = redis.from_url(broker_url)
                return r.llen('celery')
        except:
            pass
        return 0
    
    def get_all_metrics(self):
        """Get all metrics."""
        return {
            'imports': {
                'total': self.get_counter('imports.total'),
                'errors': self.get_counter('imports.errors'),
                'success': self.get_counter('imports.success'),
            },
            'approvals': {
                'total': self.get_counter('approvals.total'),
            },
            'queue': {
                'depth': self.get_queue_depth(),
            },
            'system': {
                'disk_free_gb': self.get_gauge('system.disk_free_gb'),
                'celery_workers': self.get_gauge('system.celery_workers'),
            }
        }

# Global metrics instance
metrics = MetricsCache()


def update_system_metrics():
    """Update system metrics (call periodically or on health check)."""
    try:
        # Disk space
        import shutil
        total, used, free = shutil.disk_usage('/')
        metrics.gauge('system.disk_free_gb', round(free / (1024**3), 1))
        
        # Celery workers
        try:
            from celery import current_app
            inspect = current_app.control.inspect()
            active = inspect.active()
            metrics.gauge('system.celery_workers', len(active or {}))
        except:
            metrics.gauge('system.celery_workers', 0)
    except:
        pass
