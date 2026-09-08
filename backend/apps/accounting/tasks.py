"""Celery tasks.

The worker and a `celery beat` scheduler are already running against RabbitMQ
(see docker-compose.yml). What is missing is the work itself.

Requirements for the sync (see README task 1):

  * Runs automatically every 30 minutes, and can also be triggered on demand
    from the dashboard.
  * Pulls invoices and transactions from the external service, which paginates,
    caps `page_size` at 100, and returns records ordered by `updated_at`.
  * Is idempotent: running it twice in a row must not duplicate or corrupt
    anything. Note that `updated_since` on the external API is INCLUSIVE, so
    you will re-see records you already have.
  * Survives the vendor being unreliable — it injects 5xx responses, 429s with
    a `Retry-After` header, and multi-second latency spikes. A failed page
    should not silently drop data, and a bad run should not poison the next one.
  * Records what happened, so the dashboard can show sync health.

How you structure this — one task or several, how you retry, whether you
checkpoint progress, how you avoid two runs overlapping — is yours to decide.
"""

from celery import shared_task


@shared_task(name="accounting.sync_external_data")
def sync_external_data() -> dict:
    raise NotImplementedError("See README task 1.")
