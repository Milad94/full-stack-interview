# Implementation notes

Tasks 1–3 are implemented: accounting sync, the dashboard, and manual adjustments. The supplied stack is retained, no application dependencies were added, and `mock-service/` and its default failure settings are unchanged. 

## Running and checking the project

Start the backend services with `docker compose up --build`. Migrations run automatically when the backend starts. On an existing running checkout:

```bash
docker compose exec backend python manage.py migrate
docker compose restart worker beat
docker compose exec backend pytest
```

Run the frontend on the host in a separate terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to backend port 8000. For another port, use `VITE_API_PROXY_TARGET=http://localhost:<port> npm run dev`.

Frontend checks, from `frontend/`:

```bash
npm run typecheck
npm run lint
npm run build
npm test
```

Frontend tests use Node's built-in runner with TypeScript stripping and require Node 22.18+ or Node 24. Backend tests use real PostgreSQL and stub vendor HTTP responses with the existing `responses` dependency.

Beat runs the sync every 1,800 seconds. `ACCOUNTING_SYNC_INTERVAL_SECONDS` controls this interval; `ACCOUNTING_SYNC_OVERLAP_SECONDS` defaults to 60. These settings must reach the worker/beat environment as appropriate. Compose forwards `ACCOUNTING_SYNC_TIME_LIMIT_SECONDS` to the backend, worker and beat; for example, `ACCOUNTING_SYNC_TIME_LIMIT_SECONDS=1800 docker compose up -d` sets a 30-minute execution limit.

Manual sync uses `POST /api/sync-runs/`; it returns HTTP 202 and a stored run ID. Poll `GET /api/sync-runs/<id>/` for the result. Publication failure returns HTTP 503 with a recorded failed run.

## Decisions and tradeoffs

### Page commits, independent checkpoints and idempotency

Invoices and transactions have separate checkpoints and time budgets. Each page is fully validated, then its upserts and progress counters commit in one database transaction. A failed page rolls back without discarding earlier pages. An incomplete source keeps its previous checkpoint, so a later run can replay safely. Either source failing makes the overall run failed, while the other can still succeed unless a global failure, such as invalid credentials or a lost database session, prevents it.

I chose page commits to avoid holding a transaction open across network waits and losing all progress on failure. The cost is partial visibility: the dashboard can see committed pages before the whole sync finishes.

Unique vendor IDs prevent duplicate records. Existing rows are fetched in bulk for each page; unchanged payloads incur no write. Payloads are compared field by field and applied in received order, including duplicate IDs. Timestamp equality is not enough to skip a payload: content can change within the same second, and the mock can move a future seed timestamp back to the present. `records_touched` counts committed create/update operations, not distinct IDs.

Transactions retain the vendor's invoice ID separately from their nullable local foreign key. After processing both sources, a database update links all resolvable transactions, including older ones absent from the current response. A changed vendor invoice reference clears the old local link first. Unresolved references are reported separately and do not fail the sync.

### Incremental boundaries and changing pagination

The first sync is a full scan. Later requests use the committed watermark minus a configurable 60-second overlap, with the same filter across every page and rescan. The vendor's inclusive filter is preserved: no epsilon is added to skip equal timestamps.

The overlap deliberately re-reads records just before the boundary. It can recover newly visible records with slightly older timestamps, for example because of delayed visibility, differing timestamp precision or clock skew. These are defensive integration scenarios, not claims that the mock implements replicas or caches. Idempotent upserts make replay safe; the cost is extra reads and validation. Sixty seconds is a chosen tolerance, not a guaranteed bound on vendor delay.

After a successful traversal, the new watermark uses `min(latest, started)`, or `started` for an empty scan, and never moves backwards from its previous value. Capping it at the source's start time is deliberate: a future `updated_at` from the mock must not push the filter into the future and hide subsequent changes dated before that value.

Each traversal collects unique IDs and the set of reported totals. A changing total or a unique-ID count that does not match it triggers a restart from page one, with fresh coverage sets. Three traversals is the chosen cap to bound work; persistent inconsistency fails the source without advancing its checkpoint. It can indicate dataset churn or inconsistent vendor responses, not necessarily a rate-limit problem.

This detects some offset-pagination inconsistencies, but matching counts do not prove snapshot completeness or that every version is current. Stronger guarantees require vendor support, such as a frozen snapshot across pages or a durable ordered change feed. Retrying more cannot establish those guarantees.

### Concurrency, retries and bounded execution

A PostgreSQL session advisory lock on the same connection used for writes prevents overlapping syncs. Losing that connection aborts processing; reconnecting would not restore ownership of the lock. Normal exit or session closure releases it. A later lock owner marks abandoned running executions `interrupted`.

Vendor requests have connect/read timeouts of 3.05/10 seconds and five attempts total, with exponential backoff and up to 0.5 seconds jitter. Transient network failures, 429 and 5xx responses retry the same page. Other HTTP errors and malformed payloads fail promptly; 401/403 stop both sources. `Retry-After` accepts seconds or an HTTP date. Both sources share the remaining cooldown, even after the last failed attempt or a source timeout, so switching sources cannot bypass the vendor's rate limit.

The 40-minute default whole-task limit and equal per-source budgets are implementation choices for bounded execution. The soft limit normally fires 30 seconds before the hard limit; after reserving finalization time, each source gets 19 minutes 30 seconds by default. A source timeout preserves committed work and gives the next source its own budget. After rollback, counters are reloaded from the database because Python objects do not roll back automatically.

The soft limit records `failed` and performs cleanup; the hard limit terminates a stuck worker child. A hard kill can leave the run marked `running` until the next lock owner repairs it. These mechanisms rely on the Docker Linux/prefork worker and signal handling; direct `run_sync()` calls or eager/solo mode do not enforce Celery's task limits. Waiting occupies a worker slot, and session advisory locks require direct connections or session pooling, not transaction pooling.

Manual publication uses `retry=False` to surface broker failures promptly. If RabbitMQ accepted a message just before the connection failed, the API can still record that queued run as failed; a later delivery is consumed without syncing. I accepted this visible, retryable failure instead of adding an outbox, because guaranteed manual delivery is not required and scheduled sync remains a fallback.

The UI prevents ordinary repeated clicks, but separate requests are separate runs. The lock prevents concurrent execution, not sequential queued runs; a task starting after the lock is released may sync again. Delivery of an already completed manual run is a no-op.

### Financial correctness and dashboard queries

Money uses `DecimalField(18, 2)` and decimal strings in API payloads and frontend forms/display. Supported currencies and transaction types/methods are validated in serializers and database constraints. No implicit rounding, currency conversion or cross-currency total is performed.

Dashboard definitions are explicit:

- Invoice count includes all statuses.
- Outstanding is the sum of `max(total - amount_paid, 0)` for open invoices, grouped by currency. An overpayment does not cancel another invoice's debt.
- Collections this month are gross `payment` amounts in each transaction's currency, including payments with an unresolved invoice. Refunds and fees are excluded.
- Sync health shows the most recently started execution, including a running one; queued/skipped requests do not hide it.

All aggregation runs in PostgreSQL. The dashboard uses five queries and indexed timestamp ranges for month filtering. Constant query count still involves processing matching rows; it does not imply constant database work.

### Locally owned adjustments and frontend behavior

Adjustments live in a separate table that sync never writes. Their required `PROTECT` foreign key prevents deleting an invoice with adjustments. Amounts must be nonzero decimal strings; the invoice must exist and the trimmed reason must be nonempty and at most 1,000 characters. Negative amounts mean reductions and positive amounts mean increases.

Currency is copied from the invoice when the adjustment is created and preserved if that invoice later changes currency. Explicitly choosing a different invoice adopts its currency without converting the amount; the UI explains this. Keeping a stored currency avoids silently changing the meaning of old corrections.

Adjustments do not change vendor balances or dashboard totals: Task 3 asks to record corrections, and applying them to balances would need additional accounting rules. Lists use server pagination, filtering/search and `select_related` to avoid N+1 queries.

The frontend uses the required React/MUI, TanStack Query, react-hook-form and yup stack. It handles loading, error and empty states, maps server field errors to inputs, polls manual sync every three seconds and refreshes relevant queries when it finishes. Invoice search is debounced and fetches up to 25 matches rather than all invoices. Table sorting is disabled because sorting only the current server page would be misleading. Deletion requires confirmation.

## What I would do with another week

My priority would be observability and measuring whether the current sync keeps up with expected data volume and vendor changes. I would track per-source duration, time since the last successful sync, request/retry counts, 429 responses, cooldown time, rescans and coverage failures. Separating vendor latency, waiting and database write time would identify the bottleneck. An operational dashboard, alerts for overdue successful syncs/repeated failures, and controlled load tests in a separate harness would make the results actionable.

I would then optimize local writes if database work dominates; discuss rate limits, larger pages or bulk endpoints if API throughput is the constraint; or discuss snapshots/change feeds if live pagination repeatedly produces inconsistent coverage. Healthy metrics cannot prove that no records are missing. If the business requires guaranteed capture of every change, that requirement already warrants a vendor API discussion.

## Known limitations and unfinished work

- The current API offers no snapshot, durable change stream or deletion/tombstone contract. Matching counts can miss dataset changes; old records skipped in the initial scan and changes outside the overlap are not guaranteed to be recovered. There is no recurring full rescan or inferred deletion.
- There is no immediate watchdog for abandoned runs, guaranteed manual message delivery or queue deduplication. A web-process crash before publication can leave a queued record; a worker crash can leave a running record until a later run repairs it.
- Throughput is bounded by vendor rate limits and page size. Coverage sets use memory proportional to the distinct IDs in a traversal. A source cannot continue in the same worker after a hard kill of that worker.
- Adjustment edits use last-write-wins behavior; edit history and conflict detection are not implemented.
- Invoice lookup requires refining searches beyond the first 25 matches. Sync tracking is per browser tab.
- The frontend build reports a bundle-size warning (previously measured at about 1.47 MB minified / 454 KB gzip); route-level lazy loading is not implemented.
- Browser checks were temporary validation scripts, not a maintained browser-test suite.

## Validation summary

During implementation, PostgreSQL-backed tests covered replay/idempotency, mid-page rollback, independent checkpoints, lock contention and recovery, retries/shared cooldowns, source/task timeouts, future and equal timestamps, pagination coverage, currency separation, dashboard totals and adjustment validation/isolation. The latest sync-only run recorded in this work passed all 39 tests; earlier full-backend validation recorded 70 passing tests.

Django checks and migration consistency checks passed. Frontend type checking, lint, production build and four money/form tests passed. Browser checks exercised sync feedback, loading/error/empty states and adjustment CRUD with both controlled responses and the real API. Real Celery/prefork tests also exercised slow HTTP streams and soft/hard termination. These are recorded implementation results, not a claim that the checks were rerun for this documentation edit.
