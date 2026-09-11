from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.accounting.models import Invoice, SyncRun, Transaction

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 10, 12, tzinfo=dt_timezone.utc)


def invoice(external_id, **changes):
    return Invoice(
        **{
            "external_id": external_id, "customer_id": "CUS-1", "customer_name": "Example",
            "customer_email": "ap@example.com", "currency": "USD", "status": "open",
            "issue_date": NOW.date(), "due_date": NOW.date(),
            "subtotal": Decimal("10.10"), "tax": Decimal("0.00"),
            "total": Decimal("10.10"), "amount_paid": Decimal("0.00"),
            "vendor_updated_at": NOW, **changes,
        }
    )


def payment(external_id, **changes):
    return Transaction(
        **{
            "external_id": external_id, "external_invoice_id": "NOT-SYNCED-YET",
            "type": "payment", "method": "card", "currency": "USD",
            "amount": Decimal("0.10"), "occurred_at": NOW, "vendor_updated_at": NOW,
            **changes,
        }
    )


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


def test_dashboard_money_statuses_and_unresolved_collections(client, django_assert_num_queries):
    Invoice.objects.bulk_create([
        invoice("open-1", amount_paid=Decimal("0.10")),
        invoice("open-2", total=Decimal("0.20")),
        invoice("overpaid", total=Decimal("1.00"), amount_paid=Decimal("5.00")),
        invoice("eur", currency="EUR", total=Decimal("22.22")),
        invoice("gbp", currency="GBP", total=Decimal("33.33")),
        invoice("paid", status="paid"), invoice("draft", status="draft"),
        invoice("void", status="void"),
    ])
    Transaction.objects.bulk_create([
        payment("usd-1"), payment("usd-2", amount=Decimal("0.20")),
        payment("eur", currency="EUR", amount=Decimal("12.34")),
        payment("gbp", currency="GBP", amount=Decimal("56.78")),
        payment("refund", type="refund", amount=Decimal("90.00")),
        payment("fee", type="fee", amount=Decimal("80.00")),
    ])
    with django_assert_num_queries(5):
        response = client.get("/api/dashboard/")
    assert response.status_code == 200
    data = response.json()
    assert data["total_invoices"] == 8
    assert data["outstanding_by_currency"] == [
        {"currency": "EUR", "amount": "22.22"},
        {"currency": "GBP", "amount": "33.33"},
        {"currency": "USD", "amount": "10.20"},
    ]
    assert data["collected_this_month_by_currency"] == [
        {"currency": "EUR", "amount": "12.34"},
        {"currency": "GBP", "amount": "56.78"},
        {"currency": "USD", "amount": "0.30"},
    ]
    assert data["invoices_by_status"] == [
        {"status": "draft", "count": 1}, {"status": "open", "count": 5},
        {"status": "paid", "count": 1}, {"status": "void", "count": 1},
    ]


@pytest.mark.parametrize("year,month,tz_name", [
    (2026, 12, "UTC"), (2028, 2, "Asia/Tehran"), (2026, 3, "America/New_York"),
])
def test_collection_month_boundaries(client, monkeypatch, year, month, tz_name):
    zone = ZoneInfo(tz_name)
    start = datetime(year, month, 1, tzinfo=zone)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=zone)
    monkeypatch.setattr(timezone, "now", lambda: start + timedelta(days=9))
    Transaction.objects.bulk_create([
        payment("before", occurred_at=start - timedelta(microseconds=1), amount=Decimal("100.00")),
        payment("start", occurred_at=start, amount=Decimal("1.01")),
        payment("last", occurred_at=end - timedelta(microseconds=1), amount=Decimal("2.02")),
        payment("next", occurred_at=end, amount=Decimal("200.00")),
    ])
    with timezone.override(zone):
        data = client.get("/api/dashboard/").json()
    assert data["collected_this_month_by_currency"] == [{"currency": "USD", "amount": "3.03"}]


def test_last_sync_reports_actual_execution_even_with_newer_queued_or_skipped_requests(client):
    SyncRun.objects.create(status="succeeded", started_at=NOW - timedelta(hours=1))
    last = SyncRun.objects.create(
        status="failed", started_at=NOW - timedelta(minutes=2), finished_at=NOW,
        error="transactions failed", sources={
            "invoices": {"created": 2, "updated": 3, "unchanged": 100},
            "transactions": {"created": 4, "updated": 0},
        },
    )
    SyncRun.objects.create(status="skipped", finished_at=NOW)
    SyncRun.objects.create(status="queued")
    data = client.get("/api/dashboard/").json()["last_sync"]
    assert data["id"] == str(last.pk)
    assert data["status"] == "failed"
    assert data["records_touched"] == 9
    assert data["error"] == "transactions failed"
    assert datetime.fromisoformat(data["started_at"]) == last.started_at


def test_empty_dashboard(client):
    data = client.get("/api/dashboard/").json()
    assert data["total_invoices"] == 0
    assert data["outstanding_by_currency"] == []
    assert data["collected_this_month_by_currency"] == []
    assert data["invoices_by_status"] == []
    assert data["last_sync"] is None


def test_large_totals_and_query_count_do_not_depend_on_record_count(client, django_assert_num_queries):
    # Sums exceed DecimalField(18, 2) on an individual row and must still serialize exactly.
    amount = Decimal("9999999999999999.99")
    Invoice.objects.bulk_create([invoice(f"inv-{i}", total=amount) for i in range(1000)])
    Transaction.objects.bulk_create([payment(f"trx-{i}", amount=amount) for i in range(1000)])
    with django_assert_num_queries(5):
        response = client.get("/api/dashboard/")
    data = response.json()
    assert data["total_invoices"] == 1000
    assert data["outstanding_by_currency"] == [{"currency": "USD", "amount": "9999999999999999990.00"}]
    assert data["collected_this_month_by_currency"] == [{"currency": "USD", "amount": "9999999999999999990.00"}]
