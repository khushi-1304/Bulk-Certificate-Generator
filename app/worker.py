"""
Celery application instance.
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "bulk_certificate_generator",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# Import task modules so @celery_app.task decorators execute and register tasks.
# This must come AFTER celery_app is created (no circular import — batch_processor
# only imports the already-defined celery_app object).
import app.services.batch_processor  # noqa: F401
