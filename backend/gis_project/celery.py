import os
from celery import Celery

# Set default Django settings module for celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gis_project.settings')

app = Celery('gis_project')

# Load settings from Django settings using string namespace CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover task modules from all registered Django app configs.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
