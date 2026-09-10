from celery import shared_task
from django.conf import settings

from .sync import run_sync


@shared_task(
    name="accounting.sync_external_data",
    # Reserve up to 30 seconds inside the overall limit to record failure and
    # release the session lock. Prefork kills a stuck child at the hard limit.
    soft_time_limit=settings.ACCOUNTING_SYNC_SOFT_TIME_LIMIT_SECONDS,
    time_limit=settings.ACCOUNTING_SYNC_TIME_LIMIT_SECONDS,
)
def sync_external_data(run_id=None) -> dict:
    run = run_sync(run_id)
    return {"run_id": str(run.pk), "status": run.status}
