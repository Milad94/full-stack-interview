from datetime import timedelta
from decimal import Decimal
from email.utils import format_datetime
from threading import Event
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import psycopg
import pytest
import requests
import responses
from celery.exceptions import SoftTimeLimitExceeded
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.accounting.models import Adjustment, Invoice, SyncCheckpoint, SyncRun, Transaction
from apps.accounting.sync import LOCK_KEY, SourceTimeLimitExceeded, run_sync, sync_lock
from apps.accounting.tasks import sync_external_data
from apps.accounting.vendor import InvoicePayload, TransactionPayload, VendorClient, retry_after_seconds

pytestmark = pytest.mark.django_db(transaction=True)
STAMP = "2026-01-01T12:00:00Z"


def invoice(id="INV-1", **changes):
    return {
        "id": id, "customer_id": "CUS-1", "customer_name": "Example",
        "customer_email": "ap@example.com", "currency": "EUR",
        "issue_date": "2026-01-01", "due_date": "2026-02-01", "status": "open",
        "subtotal": "100.01", "tax": "20.00", "total": "120.01", "amount_paid": "0.00",
        "note": None, "updated_at": STAMP, **changes,
    }


def payment(id="TRX-1", invoice_id="INV-1", **changes):
    return {
        "id": id, "invoice_id": invoice_id, "type": "payment", "method": "card",
        "amount": "120.01", "currency": "EUR", "occurred_at": STAMP, "updated_at": STAMP,
        **changes,
    }


@pytest.mark.parametrize("model,serializer_class,payload,field,allowed,invalid,constraint", [
    (Invoice, InvoicePayload, invoice, "currency", ["USD", "EUR", "GBP"], "JPY", "invoice_currency_valid"),
    (Transaction, TransactionPayload, payment, "currency", ["USD", "EUR", "GBP"], "JPY", "transaction_currency_valid"),
    (Transaction, TransactionPayload, payment, "type", ["payment", "refund", "fee"], "transfer", "transaction_type_valid"),
    (Transaction, TransactionPayload, payment, "method", ["bank_transfer", "card", "cash", "cheque"], "crypto", "transaction_method_valid"),
])
def test_currency_and_payment_contract_enforced_at_input_and_database(
    model, serializer_class, payload, field, allowed, invalid, constraint,
):
    serializer = serializer_class(data=payload(**{field: invalid}))
    assert not serializer.is_valid()
    assert field in serializer.errors

    for value in allowed:
        serializer = serializer_class(data=payload(**{field: value}))
        assert serializer.is_valid(), serializer.errors
        obj, _ = model.objects.update_or_create(
            external_id=serializer.validated_data["external_id"], defaults=serializer.validated_data,
        )
        assert getattr(obj, field) == value

    # QuerySet.update bypasses serializer and model validation; PostgreSQL must
    # enforce the contract as well, without changing the previously valid row.
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            model.objects.filter(pk=obj.pk).update(**{field: invalid})
    assert error.value.__cause__.diag.constraint_name == constraint
    obj.refresh_from_db()
    assert getattr(obj, field) == allowed[-1]


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock:
        now = 0
        sleeps = []

        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr("apps.accounting.vendor.time.monotonic", lambda: clock.now)
    monkeypatch.setattr("apps.accounting.vendor.time.sleep", clock.sleep)
    monkeypatch.setattr("apps.accounting.vendor.random.uniform", lambda *_: 0)
    return clock


@pytest.fixture
def vendor(settings):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        def page(source, items=None, number=1, total=None, next_page=None, status=200, headers=None, body=None):
            kwargs = {"body": body} if body is not None else {
                "json": {
                    "items": items or [], "page": number, "page_size": 100,
                    "total": len(items or []) if total is None else total, "next_page": next_page,
                },
            }
            mock.get(
                f"{settings.EXTERNAL_ACCOUNTING_BASE_URL}/api/v1/{source}",
                status=status, headers=headers,
                match=[responses.matchers.query_param_matcher({"page": str(number), "page_size": "100"}, strict_match=False)],
                **kwargs,
            )
        mock.page = page
        yield mock


def test_second_run_leaves_mirror_unchanged_and_uses_inclusive_filter(vendor):
    vendor.page("invoices", [invoice()])
    vendor.page("transactions", [payment()])
    first = run_sync()
    before = list(Invoice.objects.values()), list(Transaction.objects.values())
    second = run_sync()
    assert first.status == second.status == "succeeded"
    assert second.records_touched == 0
    assert before == (list(Invoice.objects.values()), list(Transaction.objects.values()))
    assert Invoice.objects.get().total == Decimal("120.01")
    assert Transaction.objects.get().invoice == Invoice.objects.get()
    query = parse_qs(urlsplit(vendor.calls[2].request.url).query)
    assert query["updated_since"] == ["2026-01-01T11:59:00+00:00"]
    assert vendor.calls[0].request.headers["X-API-Key"] == "dev-secret-key"
    assert vendor.calls[0].request.req_kwargs["timeout"] == (3.05, 10)


@pytest.mark.parametrize("fail_second_page", [False, True])
def test_adjustments_survive_vendor_updates_failures_and_replay(vendor, fail_second_page):
    vendor.page("invoices", [invoice()])
    vendor.page("transactions")
    assert run_sync().status == "succeeded"
    inv = Invoice.objects.get()
    Adjustment.objects.bulk_create([
        Adjustment(invoice=inv, amount=Decimal("-10.01"), currency="EUR", reason="Write-off"),
        Adjustment(invoice=inv, amount=Decimal("0.25"), currency="EUR", reason="Disputed fee"),
    ])
    before = list(Adjustment.objects.values())
    vendor.reset()
    changed = invoice(status="paid", amount_paid="120.01", currency="USD")
    vendor.page("invoices", [changed, changed], total=2, next_page=2)
    if fail_second_page:
        vendor.page("invoices", number=2, status=503)
    else:
        vendor.page("invoices", [invoice("INV-2")], number=2, total=2)
    vendor.page("transactions")
    assert run_sync().status == ("failed" if fail_second_page else "succeeded")
    inv.refresh_from_db()
    assert inv.status == "paid" and inv.currency == "USD"
    assert list(Adjustment.objects.values()) == before

    vendor.reset()
    vendor.page("invoices", [changed, invoice("INV-2")])
    vendor.page("transactions")
    assert run_sync().status == "succeeded"
    assert run_sync().status == "succeeded"
    assert list(Adjustment.objects.values()) == before


def test_failed_page_keeps_checkpoint_and_next_run_recovers(vendor):
    vendor.page("invoices", [invoice()], total=2, next_page=2)
    vendor.page("invoices", number=2, status=503)
    vendor.page("transactions", [payment()])
    failed = run_sync()
    assert failed.status == "failed"
    assert Invoice.objects.count() == 1
    assert failed.sources["invoices"]["created"] == 1
    assert failed.sources["transactions"]["status"] == "succeeded"
    assert SyncCheckpoint.objects.get(source="invoices").watermark is None
    assert SyncCheckpoint.objects.get(source="transactions").watermark is not None
    assert len([call for call in vendor.calls if "page=2" in call.request.url]) == 5
    vendor.reset()
    vendor.page("invoices", [invoice()], total=2, next_page=2)
    vendor.page("invoices", [invoice("INV-2")], number=2, total=2)
    vendor.page("transactions", [payment()])
    recovered = run_sync()
    assert recovered.status == "succeeded"
    assert Invoice.objects.count() == 2
    assert recovered.sources["invoices"]["created"] == 1
    assert SyncCheckpoint.objects.get(source="invoices").watermark is not None


def test_failed_incremental_source_retains_existing_watermark(vendor):
    old = timezone.now() - timedelta(days=1)
    SyncCheckpoint.objects.create(source="invoices", watermark=old)
    vendor.page("invoices", [invoice()], total=2, next_page=2)
    vendor.page("invoices", number=2, status=500)
    vendor.page("transactions")
    assert run_sync().status == "failed"
    assert SyncCheckpoint.objects.get(source="invoices").watermark == old


@pytest.mark.parametrize("failure", [500, 502, 503, requests.Timeout("slow"), requests.ConnectionError("offline")])
def test_transient_failure_retries_same_page(vendor, failure):
    if isinstance(failure, int):
        vendor.page("invoices", status=failure)
    else:
        vendor.page("invoices", body=failure)
    vendor.page("invoices", [invoice()])
    vendor.page("transactions")
    assert run_sync().status == "succeeded"
    assert vendor.calls[0].request.url == vendor.calls[1].request.url


def test_429_waits_at_least_retry_after(vendor, clock):
    vendor.page("invoices", status=429, headers={"Retry-After": "18"})
    vendor.page("invoices")
    vendor.page("transactions")
    assert run_sync().status == "succeeded"
    assert clock.sleeps == [18]


def test_final_429_cooldown_is_shared_with_other_source(vendor, clock):
    vendor.page("invoices", status=429, headers={"Retry-After": "30"})
    vendor.page("transactions")
    run = run_sync()
    assert run.status == "failed"
    assert run.sources["transactions"]["status"] == "succeeded"
    assert clock.sleeps == [30] * 5


def test_http_date_retry_after():
    value = format_datetime(timezone.now() + timedelta(seconds=40), usegmt=True)
    assert 38 <= retry_after_seconds(value) <= 40
    assert retry_after_seconds("invalid") == 0


@pytest.mark.parametrize("status, calls", [(401, 1), (403, 1), (422, 2)])
def test_permanent_errors_are_not_retried(vendor, status, calls):
    vendor.page("invoices", status=status)
    vendor.page("transactions")
    assert run_sync().status == "failed"
    assert len(vendor.calls) == calls


def test_unknown_invoice_is_preserved_and_reconciled_on_later_run(vendor):
    vendor.page("invoices")
    vendor.page("transactions", [payment(), payment("TRX-2", invoice_id=None)])
    first = run_sync()
    assert first.unresolved == 1
    assert Transaction.objects.get(external_id="TRX-1").external_invoice_id == "INV-1"
    vendor.reset()
    vendor.page("invoices", [invoice()])
    vendor.page("transactions")  # Old transaction no longer in the incremental response.
    second = run_sync()
    assert second.reconciled == 1 and second.unresolved == 0
    assert Transaction.objects.get(external_id="TRX-1").invoice == Invoice.objects.get()
    assert Transaction.objects.get(external_id="TRX-2").invoice is None


def test_same_timestamp_changed_payload_and_duplicate_are_applied(vendor):
    vendor.page("invoices", [invoice(), invoice(status="paid", amount_paid="120.01")], total=1)
    vendor.page("transactions")
    run = run_sync()
    assert run.status == "succeeded"
    assert Invoice.objects.count() == 1
    assert Invoice.objects.get().status == "paid"
    assert run.sources["invoices"]["created"] == run.sources["invoices"]["updated"] == 1


def test_drifting_pagination_rescans_from_page_one(vendor):
    vendor.page("invoices", [invoice()], total=2, next_page=2)
    vendor.page("invoices", [invoice(status="paid")], number=2, total=2)
    vendor.page("invoices", [invoice("INV-2")], total=2, next_page=2)
    vendor.page("invoices", [invoice(status="paid")], number=2, total=2)
    vendor.page("transactions")
    run = run_sync()
    assert run.status == "succeeded"
    assert run.sources["invoices"]["scans"] == 2
    assert Invoice.objects.count() == 2


def test_repeated_coverage_mismatch_fails_without_checkpoint(vendor):
    vendor.page("invoices", [invoice()], total=2)
    vendor.page("transactions")
    run = run_sync()
    assert run.status == "failed"
    assert run.sources["invoices"]["scans"] == 3
    assert SyncCheckpoint.objects.get(source="invoices").watermark is None


def test_invalid_money_rolls_back_entire_page(vendor):
    vendor.page("invoices", [invoice(), invoice("INV-2", total=120.01)])
    vendor.page("transactions")
    run = run_sync()
    assert run.status == "failed"
    assert Invoice.objects.count() == 0
    assert "decimal string" in run.error


def test_future_seed_timestamp_does_not_hide_current_drift(vendor):
    future = (timezone.now() + timedelta(days=3)).isoformat()
    vendor.page("invoices", [invoice(updated_at=future)])
    vendor.page("transactions")
    before = timezone.now()
    run_sync()
    assert before <= SyncCheckpoint.objects.get(source="invoices").watermark <= timezone.now()
    vendor.reset()
    vendor.page("invoices", [invoice(status="paid", updated_at=timezone.now().isoformat())])
    vendor.page("transactions")
    assert run_sync().status == "succeeded"
    assert Invoice.objects.get().status == "paid"


def test_database_error_rolls_back_page_and_is_recovered(vendor, monkeypatch):
    vendor.page("invoices", [invoice(), invoice("INV-2")])
    vendor.page("transactions")
    original = Invoice.save

    def fail_second(obj, *args, **kwargs):
        if obj.external_id == "INV-2":
            raise DatabaseError("Database write failed")
        return original(obj, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Invoice, "save", fail_second)
        with pytest.raises(DatabaseError):
            run_sync()
    assert Invoice.objects.count() == 0
    abandoned = SyncRun.objects.get()
    assert abandoned.sources["invoices"]["created"] == 0
    assert SyncCheckpoint.objects.get(source="invoices").watermark is None
    assert run_sync().status == "succeeded"
    assert Invoice.objects.count() == 2
    abandoned.refresh_from_db()
    assert abandoned.status == "interrupted"


def test_time_limit_during_backoff_preserves_progress_and_releases_lock(vendor, monkeypatch):
    vendor.page("invoices", [invoice()], total=2, next_page=2)
    vendor.page("invoices", number=2, status=429, headers={"Retry-After": "3600"})
    with monkeypatch.context() as patch:
        patch.setattr("apps.accounting.vendor.time.sleep", Mock(side_effect=SoftTimeLimitExceeded))
        run = run_sync()
    assert run.status == "failed"
    assert "execution time limit" in run.error
    assert run.finished_at is not None
    assert Invoice.objects.count() == 1
    assert run.sources["invoices"]["created"] == 1
    assert SyncCheckpoint.objects.get(source="invoices").watermark is None
    assert "transactions" not in run.sources
    with psycopg.connect(**connection.get_connection_params(), autocommit=True) as other:
        assert other.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY]).fetchone()[0]
    vendor.reset()
    vendor.page("invoices", [invoice(), invoice("INV-2")])
    vendor.page("transactions")
    assert run_sync().status == "succeeded"
    assert Invoice.objects.count() == 2


def test_time_limit_during_page_commit_does_not_record_rolled_back_counts(vendor, monkeypatch):
    vendor.page("invoices", [invoice()])
    original = SyncRun.save

    def timeout_on_page_save(run, *args, **kwargs):
        if run.sources.get("invoices", {}).get("created") == 1:
            raise SoftTimeLimitExceeded()
        return original(run, *args, **kwargs)

    monkeypatch.setattr(SyncRun, "save", timeout_on_page_save)
    run = run_sync()
    assert run.status == "failed"
    assert run.records_touched == 0
    assert Invoice.objects.count() == 0
    assert SyncCheckpoint.objects.get(source="invoices").watermark is None


@pytest.mark.parametrize("slow_source", ["invoices", "transactions"])
def test_source_timeout_does_not_prevent_other_source(vendor, monkeypatch, settings, slow_source):
    settings.ACCOUNTING_SYNC_SOURCE_TIME_LIMIT_SECONDS = 0.2
    vendor.page("invoices", [invoice()])
    vendor.page("transactions", [payment()])
    original = VendorClient.page

    def slow_page(client, source, *args):
        if source == slow_source:
            Event().wait(5)  # A real blocking call, interrupted by SIGALRM.
        return original(client, source, *args)

    monkeypatch.setattr(VendorClient, "page", slow_page)
    run = run_sync()
    healthy_source = "transactions" if slow_source == "invoices" else "invoices"
    assert run.status == "failed"
    assert run.sources[slow_source]["status"] == "failed"
    assert "source time budget" in run.sources[slow_source]["error"]
    assert run.sources[healthy_source]["status"] == "succeeded"
    assert SyncCheckpoint.objects.get(source=slow_source).watermark is None
    assert SyncCheckpoint.objects.get(source=healthy_source).watermark is not None
    assert Invoice.objects.count() == (slow_source != "invoices")
    assert Transaction.objects.count() == (slow_source != "transactions")


def test_source_budget_covers_all_pages_and_is_not_reset_per_request(vendor, monkeypatch, settings):
    settings.ACCOUNTING_SYNC_SOURCE_TIME_LIMIT_SECONDS = 0.4
    vendor.page("invoices", [invoice()], total=2, next_page=2)
    vendor.page("invoices", [invoice("INV-2")], number=2, total=2)
    vendor.page("transactions", [payment()])
    original = VendorClient.page

    def slow_pages(client, source, *args):
        if source == "invoices":
            Event().wait(0.25)
        return original(client, source, *args)

    monkeypatch.setattr(VendorClient, "page", slow_pages)
    run = run_sync()
    assert run.sources["invoices"]["status"] == "failed"
    assert run.sources["invoices"]["created"] == 1
    assert run.sources["invoices"]["pages"] == 1
    assert Invoice.objects.count() == 1
    assert SyncCheckpoint.objects.get(source="invoices").watermark is None
    assert run.sources["transactions"]["status"] == "succeeded"
    assert Transaction.objects.get().invoice == Invoice.objects.get()


def test_source_timeout_rolls_back_current_page_then_runs_other_source(vendor, monkeypatch):
    vendor.page("invoices", [invoice()])
    vendor.page("transactions", [payment()])
    original = SyncRun.save

    def timeout_on_page_save(run, *args, **kwargs):
        if run.sources.get("invoices", {}).get("created") == 1:
            raise SourceTimeLimitExceeded("invoices: exceeded source time budget")
        return original(run, *args, **kwargs)

    monkeypatch.setattr(SyncRun, "save", timeout_on_page_save)
    run = run_sync()
    assert run.status == "failed"
    assert run.sources["invoices"]["created"] == 0
    assert Invoice.objects.count() == 0
    assert SyncCheckpoint.objects.get(source="invoices").watermark is None
    assert run.sources["transactions"]["status"] == "succeeded"
    assert Transaction.objects.count() == 1
    assert run.unresolved == 1


def test_source_timeout_preserves_remaining_shared_retry_after(vendor, clock, monkeypatch):
    vendor.page("invoices", status=429, headers={"Retry-After": "18"})
    vendor.page("transactions", [payment()])

    def interrupted_sleep(seconds):
        if not clock.sleeps:
            clock.sleep(5)
            raise SourceTimeLimitExceeded("invoices: exceeded source time budget")
        clock.sleep(seconds)

    monkeypatch.setattr("apps.accounting.vendor.time.sleep", interrupted_sleep)
    run = run_sync()
    assert run.sources["invoices"]["status"] == "failed"
    assert run.sources["transactions"]["status"] == "succeeded"
    assert clock.sleeps == [5, 13]
    assert len(vendor.calls) == 2


def test_competing_postgres_session_skips_then_recovers_interrupted_run(vendor):
    stale = SyncRun.objects.create(status="running", started_at=timezone.now())
    with psycopg.connect(**connection.get_connection_params(), autocommit=True) as holder:
        holder.execute("SELECT pg_advisory_lock(%s)", [LOCK_KEY])
        assert run_sync().status == "skipped"
        stale.refresh_from_db()
        assert stale.status == "running"
        assert len(vendor.calls) == 0
        # Wait for the server to acknowledge release; closing a client socket
        # alone doesn't mean PostgreSQL has processed the disconnect yet.
        holder.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
    vendor.page("invoices")
    vendor.page("transactions")
    assert run_sync().status == "succeeded"
    stale.refresh_from_db()
    assert stale.status == "interrupted"


def test_lost_lock_session_is_not_silently_reopened():
    with sync_lock() as check:
        connection.close()
        with pytest.raises(DatabaseError, match="lock session"):
            check()


def test_completed_task_redelivery_is_noop(vendor):
    vendor.page("invoices")
    vendor.page("transactions")
    run = run_sync()
    assert sync_external_data(str(run.pk))["status"] == "succeeded"
    assert len(vendor.calls) == 2


def test_api_enqueues_and_exposes_pollable_run(client, monkeypatch):
    publish = Mock()
    monkeypatch.setattr(sync_external_data, "apply_async", publish)
    response = client.post("/api/sync-runs/", data={}, content_type="application/json")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    publish.assert_called_once_with(args=[data["id"]], task_id=data["id"], retry=False)
    assert client.get(f"/api/sync-runs/{data['id']}/").json()["status"] == "queued"


def test_broker_failure_returns_503_and_records_failure(client, monkeypatch):
    monkeypatch.setattr(sync_external_data, "apply_async", Mock(side_effect=OperationalError("offline")))
    response = client.post("/api/sync-runs/", data={}, content_type="application/json")
    assert response.status_code == 503
    assert response.json()["status"] == "failed"
    assert SyncRun.objects.get().error == "Could not enqueue sync"
