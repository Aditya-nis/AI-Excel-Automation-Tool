# Ensure celery app is loaded when django starts if celery is installed
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    pass
