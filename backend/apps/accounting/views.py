"""API views.

You need, roughly (see README tasks 2 and 3):

  * Dashboard summary data — totals, outstanding amounts, a breakdown to chart,
    and the state of the most recent sync.
  * A "sync now" endpoint that enqueues the Celery task and returns immediately.
  * CRUD for manual adjustments, list endpoint paginated + filterable/searchable.

DRF's pagination and filter backends are already configured in settings.
Aggregation belongs in the database, not in a Python loop over a queryset.
"""

from rest_framework.viewsets import ViewSet  # noqa: F401
