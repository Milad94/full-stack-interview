import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("accounting")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# TODO(candidate): register the periodic sync here (or via django-celery-beat).
# The broker (RabbitMQ) and a `celery beat` container are already running —
# see docker-compose.yml. How you schedule it, and what you do about overlapping
# runs, retries and time limits, is up to you.
#
# app.conf.beat_schedule = {...}


@app.task(name="config.debug_task")
def debug_task() -> str:
    """Sanity check that the worker is reachable: `celery -A config call config.debug_task`."""
    return "pong"
