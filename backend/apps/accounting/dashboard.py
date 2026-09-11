"""Read dashboard figures from the local mirror; all aggregation runs in SQL."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import Invoice, SyncRun, Transaction, TransactionType


def dashboard_summary():
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1)

    return {
        "total_invoices": Invoice.objects.count(),
        "outstanding_by_currency": (
            Invoice.objects.filter(status="open")
            .values("currency")
            .annotate(amount=Sum(Greatest(F("total") - F("amount_paid"), Value(Decimal("0.00")))))
            .order_by("currency")
        ),
        # Gross payments, including unresolved invoice references. Joining invoices
        # would drop valid collections and could use the wrong currency.
        "collected_this_month_by_currency": (
            Transaction.objects.filter(
                type=TransactionType.PAYMENT,
                occurred_at__gte=month_start,
                occurred_at__lt=month_end,
            )
            .values("currency")
            .annotate(amount=Sum("amount"))
            .order_by("currency")
        ),
        "invoices_by_status": (
            Invoice.objects.values("status").annotate(count=Count("pk")).order_by("status")
        ),
        # A queued/skipped request must not hide the last sync that actually ran.
        "last_sync": SyncRun.objects.filter(started_at__isnull=False).order_by("-started_at").first(),
    }
