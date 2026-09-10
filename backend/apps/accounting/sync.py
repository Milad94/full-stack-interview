"""Accounting sync orchestration. HTTP waits never hold a DB transaction open."""

import logging
import signal
from contextlib import contextmanager
from datetime import timedelta

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.db.models import Exists, OuterRef, Subquery
from django.utils import timezone

from .models import Invoice, SyncCheckpoint, SyncRun, Transaction
from .vendor import InvoicePayload, TransactionPayload, VendorAuthError, VendorClient, VendorError

logger = logging.getLogger(__name__)
LOCK_KEY = 731_240_001
SOURCES = {"invoices": (Invoice, InvoicePayload), "transactions": (Transaction, TransactionPayload)}
MAX_SCANS = 3


class SourceTimeLimitExceeded(Exception):
    pass


@contextmanager
def source_time_limit(source, seconds):
    """Interrupt a slow source without ending the Celery task or its DB session.

    Runs on the main thread of the Linux prefork child. Celery uses SIGUSR1
    for its whole-task soft limit, so this timer uses SIGALRM independently.
    """
    def expired(_signum, _frame):
        raise SourceTimeLimitExceeded(f"{source}: exceeded {seconds:g}s source time budget")

    if signal.getitimer(signal.ITIMER_REAL)[0]:
        raise RuntimeError("The sync worker already has an active SIGALRM timer")
    previous_handler = signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


@contextmanager
def sync_lock():
    # The lock and every ORM write use the SAME session. Losing it aborts the run;
    # a separate lock connection could die while a data connection kept writing.
    connection.ensure_connection()
    session = connection.connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY])
        acquired = cursor.fetchone()[0]

    def check_session():
        if connection.connection is not session or session.closed:
            raise DatabaseError("Sync lost its PostgreSQL lock session")

    try:
        yield check_session if acquired else None
    finally:
        if acquired and connection.connection is session and not session.closed:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
            except DatabaseError:
                connection.close()


def store_page(model, rows):
    """Upsert every payload in order, including changes within the same second."""
    existing = model.objects.in_bulk([row["external_id"] for row in rows], field_name="external_id")
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for row in rows:
        obj = existing.get(row["external_id"])
        if obj is None:
            obj = model.objects.create(**row)
            existing[row["external_id"]] = obj
            counts["created"] += 1
            continue
        # Do not use timestamp equality as a content check, or assume monotonic
        # versions: the mock seeds future timestamps then drifts them to now.
        changed = [key for key, value in row.items() if getattr(obj, key) != value]
        if not changed:
            counts["unchanged"] += 1
            continue
        for key in changed:
            setattr(obj, key, row[key])
        if model is Transaction and "external_invoice_id" in changed:
            obj.invoice_id = None
            changed.append("invoice")
        obj.save(update_fields=changed)
        counts["updated"] += 1
    return counts


def sync_source(run, source, client, check_session):
    model, serializer_class = SOURCES[source]
    checkpoint, _ = SyncCheckpoint.objects.get_or_create(source=source)
    since = checkpoint.watermark
    if since is not None:
        since -= timedelta(seconds=settings.ACCOUNTING_SYNC_OVERLAP_SECONDS)
    started = timezone.now()
    result = {
        "status": "running", "updated_since": since.isoformat() if since else None,
        "watermark": checkpoint.watermark.isoformat() if checkpoint.watermark else None,
        "pages": 0, "scans": 0, "received": 0, "created": 0, "updated": 0, "unchanged": 0,
        "error": "", "time_limit_seconds": settings.ACCOUNTING_SYNC_SOURCE_TIME_LIMIT_SECONDS,
    }
    run.sources[source] = result
    run.save(update_fields=["sources"])
    try:
        with source_time_limit(source, result["time_limit_seconds"]):
            latest = None
            for scan in range(1, MAX_SCANS + 1):
                seen, totals = set(), set()
                page = 1
                result["scans"] = scan
                while page is not None:
                    payload = client.page(source, page, since)
                    check_session()
                    serializer = serializer_class(data=payload["items"], many=True)
                    if not serializer.is_valid():
                        raise VendorError(f"{source} page {page}: invalid records: {serializer.errors}")
                    rows = serializer.validated_data
                    with transaction.atomic():
                        counts = store_page(model, rows)
                        for key, count in counts.items():
                            result[key] += count
                        result["received"] += len(rows)
                        result["pages"] += 1
                        run.save(update_fields=["sources"])
                    for row in rows:
                        seen.add(row["external_id"])
                        stamp = row["vendor_updated_at"]
                        latest = stamp if latest is None else max(latest, stamp)
                    totals.add(payload["total"])
                    page = payload["next_page"]
                # Reset seen/totals each pass: IDs from a previous pass must not mask
                # a missing row in this pass. This detects drift, not a true snapshot.
                if len(totals) == 1 and len(seen) == next(iter(totals)):
                    check_session()
                    with transaction.atomic():
                        # Future-dated seed records must not move the filter beyond
                        # changes made now. Never add an epsilon to inclusive bounds.
                        watermark = min(latest, started) if latest else started
                        if checkpoint.watermark:
                            watermark = max(checkpoint.watermark, watermark)
                        checkpoint.watermark = watermark
                        checkpoint.save(update_fields=["watermark"])
                        result.update(status="succeeded", watermark=watermark.isoformat())
                        run.save(update_fields=["sources"])
                    return
            raise VendorError(f"{source}: pagination coverage inconsistent after {MAX_SCANS} scans")
    except (VendorError, SourceTimeLimitExceeded) as exc:
        check_session()
        # A timeout may arrive after in-memory counters changed inside a page
        # transaction. Keep only committed data and its committed counters.
        run.refresh_from_db(fields=["sources"])
        result = run.sources[source]
        if result["status"] != "succeeded":
            result.update(status="failed", error=str(exc))
            run.save(update_fields=["sources"])
        if isinstance(exc, VendorAuthError):
            raise


def reconcile_invoices():
    matching = Invoice.objects.filter(external_id=OuterRef("external_invoice_id"))
    unresolved = Transaction.objects.filter(invoice__isnull=True, external_invoice_id__isnull=False)
    reconciled = unresolved.filter(Exists(matching)).update(invoice_id=Subquery(matching.values("pk")[:1]))
    return reconciled, unresolved.count()


def run_sync(run_id=None):
    with sync_lock() as check_session:
        run = SyncRun.objects.get(pk=run_id) if run_id else SyncRun.objects.create()
        if not check_session:
            # A redelivery of the active task must not mark that active run skipped.
            SyncRun.objects.filter(pk=run.pk, status=SyncRun.Status.QUEUED).update(
                status=SyncRun.Status.SKIPPED, finished_at=timezone.now(), error="Another sync holds the lock",
            )
            run.refresh_from_db()
            return run
        if run.status not in (SyncRun.Status.QUEUED, SyncRun.Status.RUNNING):
            return run  # Duplicate delivery of an already completed manual task.
        now = timezone.now()
        SyncRun.objects.filter(status=SyncRun.Status.RUNNING).exclude(pk=run.pk).update(
            status=SyncRun.Status.INTERRUPTED, finished_at=now,
            error="Previous worker stopped before finishing; recovered after acquiring sync lock",
        )
        run.status, run.started_at, run.finished_at = SyncRun.Status.RUNNING, now, None
        run.sources, run.error = {}, ""
        run.save()
        client = VendorClient()
        try:
            for source in SOURCES:
                check_session()
                sync_source(run, source, client, check_session)
            check_session()
            run.reconciled, run.unresolved = reconcile_invoices()
            errors = [result["error"] for result in run.sources.values() if result["status"] == "failed"]
            run.status = SyncRun.Status.FAILED if errors else SyncRun.Status.SUCCEEDED
            run.error = "; ".join(errors)
        except SoftTimeLimitExceeded:
            check_session()
            # A signal can interrupt an atomic page write after in-memory
            # counters changed. Reload only the progress actually committed.
            run.refresh_from_db()
            run.status = SyncRun.Status.FAILED
            run.error = "Sync exceeded its execution time limit"
            logger.warning("Sync %s exceeded its execution time limit", run.pk)
        except DatabaseError:
            # Do not reconnect and continue writing without our lock. The next
            # lock owner repairs this running record as interrupted.
            logger.exception("Sync %s lost database access", run.pk)
            raise
        except Exception as exc:
            check_session()
            logger.exception("Sync %s failed", run.pk)
            run.status = SyncRun.Status.FAILED
            run.error = str(exc)
        finally:
            client.close()
        check_session()
        if run.status == SyncRun.Status.FAILED:
            for result in run.sources.values():
                if result["status"] == "running":
                    result.update(status="failed", error=run.error)
        run.finished_at = timezone.now()
        run.save()
        logger.info("Sync %s: %s, touched=%s", run.pk, run.status, run.records_touched)
        return run


def enqueue_sync():
    from kombu.exceptions import OperationalError

    from .tasks import sync_external_data

    run = SyncRun.objects.create(trigger="manual")
    try:
        sync_external_data.apply_async(args=[str(run.pk)], task_id=str(run.pk), retry=False)
    except (OperationalError, OSError):
        # Only change a queued record: publication may have reached the broker
        # before its acknowledgement was lost.
        SyncRun.objects.filter(pk=run.pk, status=SyncRun.Status.QUEUED).update(
            status=SyncRun.Status.FAILED, finished_at=timezone.now(), error="Could not enqueue sync",
        )
        run.refresh_from_db()
        return run, False
    return run, True
