import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("accounting")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "accounting-sync": {
        "task": "accounting.sync_external_data",
        "schedule": settings.ACCOUNTING_SYNC_INTERVAL_SECONDS,
    },
}


@app.task(name="config.debug_task")
def debug_task() -> str:
    """Sanity check that the worker is reachable: `celery -A config call config.debug_task`."""
    return "pong"
