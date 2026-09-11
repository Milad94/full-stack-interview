# Phase 1: accounting sync

Scope: README Task 1 backend, plus manual-trigger and run-history APIs, including the configurable whole-sync time limit requested in `notes.md`. Later backend work and the completed frontend are documented below. No dependencies were added, and the vendor implementation and chaos defaults are unchanged.

## Running

```bash
docker compose up --build
# On an already running checkout:
docker compose exec backend python manage.py migrate
docker compose restart worker beat
# Tests use real PostgreSQL, with responses stubbing HTTP:
docker compose exec backend pytest
```

Beat schedules `accounting.sync_external_data` every 1,800 seconds, configurable with `ACCOUNTING_SYNC_INTERVAL_SECONDS`. New migrations are included under `backend/apps/accounting/migrations/`.

Each Celery sync has a hard execution limit of 2,400 seconds (40 minutes), including requests, backoff, rescans, database work and reconciliation. Change it through `ACCOUNTING_SYNC_TIME_LIMIT_SECONDS` (minimum 2 seconds); Compose passes this environment variable to the backend, worker and beat. For example, `ACCOUNTING_SYNC_TIME_LIMIT_SECONDS=1800 docker compose up -d` recreates them with a 30-minute limit. Queue waiting time is excluded.

The soft limit fires 30 seconds before the hard limit (at least 1 second after execution starts for small configured limits). It records the run as failed, preserves committed pages and completed-source checkpoints, and releases the lock. Any current atomic page write rolls back; run counters are reloaded from the database so rolled-back changes are not reported as saved. A timeout during Retry-After stops the sync; it never sends a premature retry.

If cleanup itself hangs, Celery terminates the prefork child at the hard limit. Its PostgreSQL session closes and releases the advisory lock. The next lock owner repairs any abandoned running record as interrupted. These limits require the Docker worker's Linux/prefork pool; calling `run_sync()` directly or using Celery eager/solo mode does not enforce them. See [Celery time limits](https://docs.celeryq.dev/en/v5.5.3/userguide/workers.html#time-limits).

Each source also has its own equal time budget, derived from the whole-run limit: the default is 1,170 seconds (19 minutes 30 seconds) per source. We reserve 30 seconds before the whole-task soft limit for reconciliation/finalization; with very small configured limits this reserve scales down to one third of the soft limit. The remaining time is split equally between the two sources. Neither source borrows the other's unused budget. Changing the whole-run setting automatically recalculates both budgets.

One SIGALRM timer covers each entire source traversal, including all HTTP reads, sleeps, page writes and rescans. It interrupts an in-progress wait; it is not just a time check between requests. A source timeout fails only that source, reloads its committed counters after rollback, leaves its incomplete checkpoint unchanged, and proceeds to the other source with a fresh budget while retaining the same global lock. Per-source `time_limit_seconds` is exposed in run history. The overall result is failed if either source failed. This uses the main thread of the Linux prefork child and a separate signal from Celery's SIGUSR1 soft limit. See [Python timers](https://docs.python.org/3/library/signal.html#signal.setitimer).

Manual trigger and polling:

```bash
curl -X POST http://localhost:8000/api/sync-runs/
curl http://localhost:8000/api/sync-runs/<id>/
curl 'http://localhost:8000/api/sync-runs/?status=failed&page=1'
```

POST returns HTTP 202 and a durable `id` with `status: queued`; GET by ID is the polling contract. The list is paginated, newest first. Publishing failure returns HTTP 503 with the recorded failure. Requests are separate runs; simultaneous workers skip when the global sync lock is busy. A queued task that starts after another run finishes can execute another incremental sync. There is no queue deduplication or frontend in this phase.

Statuses: `queued`, `running`, `succeeded`, `failed`, `skipped`, `interrupted`. Each run records timestamps, duration, per-source outcome/filter/checkpoint, pages, scans, received payloads, created/updated/unchanged counts, errors, reconciled links, and unresolved references. `records_touched` counts committed create/update operations (not distinct IDs); repeated identical payloads count as unchanged. Reconciled FK links are reported separately. Partial page progress and its counters commit together. A failure in either source makes the overall run failed, even if the other succeeded.

## ADR-001: independent checkpoints and page commits

Status: accepted for this take-home.

Invoices and transactions have separate checkpoints, time budgets and unique vendor IDs. Each page is validated completely, then upserted in a database transaction. A failing request retries the same page; exhausted retries or the source deadline fail that source and keep its previous checkpoint. Previously committed pages stay visible and are safe to replay. The other source gets its own reserved budget, except for global failures such as invalid credentials or a lost database session. The shared vendor rate limit remains binding on both sources.

Amounts are exact `DecimalField(18, 2)` values validated from decimal strings, with currency retained on each record. No conversion, rounding, or cross-currency aggregation is performed. Current vendor status/type/currency values are validated; a new unsupported value fails that source visibly instead of storing partially understood data. Timestamp equality is not used to skip payloads: two changes can share the same second. Every payload is compared to local fields. Local mirror primary keys remain stable for future adjustments; sync never deletes invoices or transactions.

Currency (`USD`, `EUR`, `GBP`), transaction type (`payment`, `refund`, `fee`) and payment method (`bank_transfer`, `card`, `cash`, `cheque`) are defined once as `TextChoices` in the models and reused by the vendor serializers. Database CHECK constraints also enforce these values on direct ORM/SQL writes. Migration `0002_constrain_currency_and_payments` adds the constraints without converting existing data; existing records were checked for unsupported values before applying it. Supporting additional values later requires updating the choices and generating a migration.

An entire-run transaction would give atomic visibility but hold a transaction open across network waits and discard useful progress on failure. Page commits accept partial visibility to allow simple recovery. At larger volumes, profile per-record writes before replacing them with batched upserts; the current in-bulk page lookup avoids one read per payload and unchanged records incur no write.

Transactions retain `external_invoice_id` independently of their nullable FK. After processing both sources, a database UPDATE attaches all resolvable old and new transactions, even those absent from this incremental response. A missing vendor reference and an unresolved reference remain distinguishable. Unresolved references do not fail the run.

## Incremental boundaries and mutable pagination

`updated_since` is fixed across every page and rescan for a source. On success its watermark advances to the largest observed `updated_at`, capped at the source's scan start (the mock can seed future timestamps). An empty successful scan uses the scan start. Incremental reads overlap by 60 seconds, configurable with `ACCOUNTING_SYNC_OVERLAP_SECONDS`; the inclusive boundary is never advanced by an epsilon. Records with the same timestamp are therefore safe to re-fetch, and future seed dates do not hide current drift.

Each traversal tracks unique IDs and every reported total. A changed total or an ID count differing from that total triggers a fresh traversal, at most three traversals in total. Each traversal uses its own coverage set, and duplicate payloads are still applied. An unresolved mismatch fails the source without advancing its checkpoint.

This detects some offset-pagination drift; it does not provide snapshot consistency. A matching count cannot prove that every version is current. The initial full scan is particularly sensitive: an old skipped record cannot be recovered by a short incremental overlap. Arbitrarily late/backdated updates outside the overlap are also not guaranteed to be discovered. There is no recurring full rescan. If stronger completeness is required, the next step is a vendor snapshot/change feed or a stable `(updated_at, id)` cursor contract, not unbounded retries. This limitation follows the supplied design notes.

## ADR-002: PostgreSQL session lock and request retries

Status: accepted for the provided PostgreSQL/Celery stack.

The task acquires PostgreSQL advisory lock `731240001` on the same Django database session used for mirror writes. Competing sessions skip. The lock is released in `finally`; closing/crashing the session also releases it. Losing the session aborts processing rather than reconnecting and continuing without the lock. Only a subsequent lock owner may mark abandoned running records interrupted. Re-delivery of an already completed manual run is a no-op.

Requests use connect/read timeouts of 3.05/10 seconds, five attempts **total**, exponential backoff and up to 0.5 seconds jitter. Timeouts, connection errors, 429 and 5xx responses retry. Other HTTP errors and malformed payloads fail promptly; 401/403 abort both sources. `Retry-After` accepts both seconds and HTTP dates. No request is sent before its cooldown expires, including when the fifth request fails: one HTTP client shares the remaining cooldown with the other source. A source or whole-run deadline can stop waiting without sending another request. No page number is advanced on a failed request.

A source deadline stops its retries but does not clear a shared 429 cooldown. If invoices times out after 5 seconds of an 18-second cooldown, transactions must still wait the remaining 13 seconds within its own budget. If a global cooldown outlasts both budgets, both sources fail without sending early requests. The independence guarantee concerns endpoint-specific failures, not a vendor-wide prohibition on requests.

The tradeoff is occupying a worker slot during waits. Task-level Celery retry would require persisting traversal state and managing lock ownership across sessions. If measured waits become operationally expensive, introduce persisted resumable work with a lease and then use Celery countdowns. Session advisory locks also require direct PostgreSQL connections or session pooling; transaction pooling is incompatible.

References: [PostgreSQL advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS), [Requests timeouts](https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts).

## Remaining limits / another week

- Frontend dashboard and adjustments UI are now implemented; see the frontend phase below for validation and remaining limits.
- The whole-sync time limit is a configurable operational guard, not a guarantee that the vendor's dataset can be consumed fast enough. If healthy runs hit it repeatedly, investigate throughput and the vendor API before increasing it.
- Source timers and Celery's soft limit require Python signal handling to run. A native/runtime hang that prevents this is a global worker failure: the hard limit terminates the process, so the other source cannot continue in that same run. Splitting work into isolated processes/tasks would require a different run/lock lifecycle; it is not needed for the supplied HTTP failure model.
- Worker death can leave a running record until the next lock owner repairs it. Beat/manual runs provide recovery; there is no immediate crash watchdog or durable outbox for the database-to-broker publication gap. A web-process crash before publication can leave a queued record. Inspect prolonged queued status and trigger a new run if necessary.
- There is no vendor deletion/tombstone contract, so sync does not infer deletions from missing records.
- Coverage sets take memory proportional to distinct records in the filtered traversal. Rate limiting is reactive via the vendor's shared 429 cooldown. Neither retries nor a different schedule can solve changes arriving faster than the vendor API can serve them.

## Validation performed

- 38 tests passed on Python 3.12 / Django 5.2.6 / PostgreSQL 16, including real competing PostgreSQL sessions, page rollback, recovery, idempotency, retry/cooldown behavior, validation, reconciliation, API enqueue failure, soft-timeout rollback/lock release, independent source timers, shared cooldown preservation after source expiry, and allowed currency/payment values enforced at both the vendor boundary and database.
- Real HTTP responses streaming one byte every 50 milliseconds were tested with a Linux/prefork worker and shortened source budgets: stalled invoices failed while transactions succeeded; stalled transactions failed while the successful invoice checkpoint and reconciliation were preserved. A separate hard-timeout check ignored both soft signals and confirmed process termination, lock release and recovery by the replacement worker.
- A real Linux/prefork Celery worker was tested with a temporary five-second hard limit: the soft limit recorded failure and preserved checkpoints; an intentionally ignored soft signal led to hard termination and PostgreSQL lock release; the replacement worker completed another sync and marked the abandoned run interrupted.
- Django system checks passed; `makemigrations --check --dry-run` reported no changes; the initial migration applied successfully.
- End-to-end POST/poll against Docker Django, RabbitMQ and Celery with the vendor's default chaos settings: initial run created 240 invoices and 221 transactions; the second incremental run changed zero records; forced drift updated 5 invoices and added 5 transactions. All three runs succeeded, with no unresolved references.
- Local port 5432 was occupied. Validation used temporary Docker port overrides (Postgres 55433, backend 18000, vendor 18001) and an isolated test database on 55432. The repository's port configuration is unchanged. Validation services were stopped afterward.

## Task 2: dashboard backend

`GET /api/dashboard/` provides the dashboard read model. It reads the local mirror and never calls the vendor or enqueues a sync. The React page is documented in the frontend phase below.

Response fields:

- `total_invoices`: count of all invoices, including draft, open, paid and void.
- `outstanding_by_currency`: rows with `currency` and decimal-string `amount`. Outstanding is the sum of `max(total - amount_paid, 0)` for open invoices. Draft/paid/void invoices are excluded; an overpayment does not cancel another invoice's debt.
- `collected_this_month_by_currency`: gross `payment` amounts grouped by the transaction's own currency, including payments whose invoice has not arrived. Refunds and fees are excluded. No exchange-rate conversion or cross-currency total is invented.
- `collection_period`: `start` (inclusive), `end` (exclusive), and `timezone`. This is the full current calendar month in Django's configured timezone (currently UTC), based on `occurred_at`, not sync/update time. Future-dated transactions within that month are included; transactions in the next month are excluded.
- `invoices_by_status`: rows with `status` and `count`, for the invoices-by-status chart.
- `last_sync`: the existing SyncRun representation for the most recently started execution, including status, timestamps, duration, records touched and errors. A running execution is included. New queued/skipped requests do not hide an actual previous execution. It is `null` before any sync has started.
- `generated_at`: when this dashboard response began being assembled, not a claim of vendor freshness or snapshot consistency.

Empty grouped results are `[]`; absent currencies/statuses have no matching records. The frontend can display zero or an empty state. Money is always a string with two decimal places, including sums larger than an individual row's DecimalField capacity. Pages committed during an ongoing sync can be visible to the dashboard; these queries do not promise an atomic snapshot across both resources.

The existing `POST /api/sync-runs/` supplies immediate HTTP 202 feedback and an ID for the Sync now button; `GET /api/sync-runs/<id>/` supports polling. Refresh the dashboard when that run finishes. The run-history list and broker-failure HTTP 503 behavior remain available.

All counts, sums, subtraction, clamping and grouping execute in PostgreSQL using ORM count/annotate expressions. No invoice/transaction queryset is iterated in Python to calculate figures. The endpoint uses five queries, returns only grouped rows and one run, and has no invoice/transaction joins or N+1 queries. Exact counts/sums still process matching database rows; constant query count does not imply constant database work. Month filtering uses an indexed timestamp range, without applying a month extraction function to the column. Migration `0003_dashboard_query_indexes` adds `(type, occurred_at)` and `SyncRun.started_at` indexes. Apply it with `docker compose exec backend python manage.py migrate`.

Validation: 45 backend tests passed on PostgreSQL, including seven new dashboard cases covering currency separation, exact large totals, overpayments/status exclusions, unresolved payments, refund/fee exclusion, empty state, last-sync selection, and month boundaries across December/year rollover, leap February and a DST transition. With 1,000 invoices and 1,000 transactions, the endpoint still used five queries. Existing enqueue/polling and vendor-failure tests also passed. No dependencies were added.

## Task 3: manual adjustments backend

Implemented only the backend requested for this phase. No authentication, dependencies, frontend changes, or changes to `mock-service/` were added. Apply migration `0004_adjustment` with `docker compose exec backend python manage.py migrate` (fresh `docker compose up --build` applies migrations automatically).

API contract:

- `POST /api/adjustments/` creates an adjustment (201).
- `GET /api/adjustments/` lists adjustments (200).
- `GET /api/adjustments/<id>/`, `PUT /api/adjustments/<id>/`, `PATCH /api/adjustments/<id>/`, and `DELETE /api/adjustments/<id>/` provide retrieve, replace, partial update, and delete (200/200/200/204). A missing record returns 404.
- Writable fields: `invoice` (the local integer invoice ID, not the vendor's external ID), `amount` (decimal string), and `reason`. All three are required for POST/PUT; PATCH validates supplied fields.
- Responses also contain `id`, `invoice_external_id`, `customer_name`, `currency`, `created_at`, and `updated_at`. Currency and timestamps are server-owned. Invoice labels reflect the current mirror; currency is the adjustment's stored currency.
- Lists use DRF's `{count, next, previous, results}` envelope. `page` is one-based; `page_size` defaults to 25 and is capped at 100. DRF falls back to the default size for invalid/nonpositive sizes; an invalid or out-of-range page returns 404. Default order is newest first, with ID breaking timestamp ties.
- Combine exact filters `invoice=<local-id>` and `currency=EUR` with `search=<text>`. Search matches reason, vendor invoice ID, and customer name using DRF's case-insensitive partial-word search. Invalid invoice/currency filter values return 400 with field errors. Optional `ordering` supports `created_at`, `updated_at`, `amount`, and `id`; prefix `-` for descending, and include `id` to break ties when choosing a custom ordering (for example `ordering=-amount,-id`). Amount sorting compares numeric amounts without exchange-rate conversion; filter by currency when comparing monetary values.
- The form can find existing invoices through the list-only `GET /api/invoices/?search=...` endpoint with the same pagination. It exposes only the local ID, vendor ID, customer name, and currency needed by the form. There is no invoice detail or write endpoint.

Example (replace `1` with an ID from `/api/invoices/`):

```bash
curl -X POST http://localhost:8000/api/adjustments/ \
  -H 'Content-Type: application/json' \
  -d '{"invoice":1,"amount":"-12.34","reason":"Write-off"}'
curl 'http://localhost:8000/api/adjustments/?invoice=1&search=write-off&page=1&page_size=25'
curl -X PATCH http://localhost:8000/api/adjustments/1/ \
  -H 'Content-Type: application/json' \
  -d '{"amount":"-10.00","reason":"Corrected write-off"}'
```

Validation returns HTTP 400 with field-to-message-list errors, for example `{"amount":["Amount must not be zero."]}`. The future frontend can map these directly to react-hook-form fields. Invoice must exist. Amount accepts positive/negative values up to 16 integer digits and two decimal places, rejects zero, excess precision, nonfinite values, and JSON numbers (send strings to avoid floating-point precision loss). The existing vendor money field is shared with this API. Reason is trimmed, required, nonblank, and limited to 1,000 characters. No silent rounding or limit based on invoice balance is applied; corrections may apply to any synced invoice status. PostgreSQL additionally enforces nonzero amounts, supported currencies, and referential integrity.

### ADR-003: locally owned corrections and stored currency

Status: accepted for this take-home.

Task 3 requires storing corrections independently of the vendor mirror. Adjustments therefore have a separate table and a required `PROTECT` foreign key to the stable local invoice ID. Django refuses deletion of an invoice with adjustments; the database foreign key also prevents orphaning them. Users can explicitly delete adjustments through their own CRUD endpoint. Sync still only writes invoices/transactions and never writes this table.

The working convention is that negative amounts represent a reduction and positive amounts an increase. Amounts are stored as `DecimalField(18, 2)`; zero corrections are rejected. Currency is copied from the selected invoice when creating an adjustment, then preserved even if a later sync changes the invoice's currency. Updating amount/reason or submitting the same invoice again preserves that currency. Explicitly reassigning to another invoice captures the new invoice's currency; the supplied/retained numeric amount is then denominated in that currency, with no conversion. The frontend should show the selected currency alongside the amount before submission.

Task 3 requests recording corrections, so these records do not mutate vendor balances or alter Task 2's dashboard totals. Net adjusted outstanding, FX conversion, and accounting posting rules would need a separate specified calculation. This also avoids silently adding amounts from different currencies.

Deriving currency on every read would be smaller but could silently reinterpret an existing correction after an upstream currency change. Storing a currency snapshot costs one small column and keeps the amount meaningful. If later requirements allow corrections in an independently selected currency, retain this column and make it explicitly selectable/validated; existing rows need no currency backfill. Changes to posting or net-balance calculations need separate domain rules and tests before inclusion in the dashboard.

List queries paginate in PostgreSQL and join the invoice once with `select_related`, avoiding one extra query per adjustment. A composite `(created_at DESC, id DESC)` index supports default listing and the invoice foreign key is indexed. Substring search still scans matching text; a full-text/trigram search index is deferred until measured data size warrants it. Offset pages can shift when rows are created/deleted between requests. Concurrent edits use ordinary CRUD last-write-wins behavior; an audit trail or optimistic concurrency can be added if finance's workflow requires them.

The React form/table and server-error mapping are covered in the frontend phase below. With another week, confirm sign/posting rules with finance before computing adjusted totals, and evaluate whether edit history or conflict detection is needed.

Validation: 70 backend tests passed on Python 3.12 / Django 5.2.6 / PostgreSQL 16, including 25 new cases for adjustment CRUD, exact signed amounts, field errors on create/update, required fields, timestamp ownership, currency preservation/reassignment, filters/search/pagination, list-only invoice lookup, database constraints, protected invoice deletion, and adjustment survival through successful/failed/replayed syncs with duplicate and changed vendor payloads. Lists used two queries for both 25-row and 100-row pages. Django system checks and `makemigrations --check --dry-run` passed; all migrations, including `0004_adjustment`, applied successfully to a fresh temporary database. Tests used the existing backend Docker image with the current source mounted and an isolated PostgreSQL container, without changing the project's data, services, port configuration, or vendor chaos defaults. The temporary database was stopped after validation.

## Frontend: dashboard and manual adjustments

Completed Tasks 2 and 3 using the existing React/MUI stack and feature structure. No application dependencies were added. The example health feature was removed; the two existing routes now contain working pages. `frontend/package-lock.json` records the resolved dependencies for reproducible installs. The backend and mock-service source are unchanged.

Run `npm ci` and `npm run dev` in `frontend/`. The existing Vite proxy forwards `/api` to port 8000; use `VITE_API_PROXY_TARGET=http://localhost:<port> npm run dev` for another backend port. Check with `npm run typecheck`, `npm run lint`, `npm run build`, and `npm test`. The tests use Node's built-in runner with TypeScript stripping (Node 22.18+ or Node 24); no test framework was added.

Decisions:

- The dashboard displays server-provided totals separately by currency and labels the collection period/timezone. Money stays as decimal strings through form validation, requests and display; formatting only inserts separators, so even large aggregate totals keep their cents. Adjustments do not alter dashboard totals.
- A bar chart shows invoice counts by status. Loading, error and empty states are explicit. The layout uses the existing theme and switches to top navigation on small screens; the table scrolls horizontally when necessary.
- Manual sync requests receive immediate queued feedback and are polled by their returned ID every three seconds until a final status. One Sync status card displays the current manual request or the latest execution, avoiding duplicate details when both APIs describe the same run. A newer scheduled execution replaces an older completed manual request in that card. The latest manual request ID is stored in sessionStorage so navigation/reload in the same tab preserves tracking. The dashboard also refreshes every 15 seconds (three seconds while its last execution is running), making scheduled runs visible. Completing a manual run, including failure after partial progress, invalidates dashboard, invoice and adjustment queries. Polling pauses in background tabs. POST is not retried automatically, and the button prevents repeated submissions while a known sync is active. The backend remains responsible for cross-tab/concurrent-run exclusion.
- The adjustment dialog serves both create and edit. Invoice search is debounced by 300 ms and returns up to 25 matches; users narrow the search instead of downloading all invoices. Existing selections are populated from the table row, so editing does not depend on finding that invoice on the first lookup page. The stored currency is retained for the original invoice; choosing another invoice displays its currency and an explicit no-conversion message.
- Yup validates signed, nonzero decimal amounts (up to 16 integer digits and two fractional digits) and a trimmed reason of at most 1,000 characters. DRF field errors map to the corresponding input; non-field/network errors appear inside the dialog. Submission disables controls until it finishes.
- The DataGrid uses server pagination with 10/25/50/100 rows, plus an explicit Apply/Clear search and currency filter form. Sorting is disabled to avoid sorting only a single server page. Filter/page values are in query keys; previous rows remain visible under a loading indicator between requests. Writes invalidate list queries and return to the first page, including deletion of the only row on a later page. Delete requires confirmation; cancel performs no write.

Validation performed:

- TypeScript checks, ESLint and the production build passed. Four focused tests passed for exact formatting of large totals, signed decimal payloads, invalid amounts and required invoice/reason fields.
- Headless Chromium checks with controlled API responses passed for queued/running/succeeded/failed syncs, tracking after reload, dashboard refresh after completion, exact large monetary values, empty/error/retry states, create/edit/delete and cancellation, client/server field errors, non-field errors, server search/pagination, and deletion of the last row on page two. No React/page errors were observed. Desktop and mobile screenshots were inspected; the chart's axis height was adjusted so all status labels render.
- A second browser check used the real Django API through Vite: loaded the dashboard/chart, searched invoices, created one marked test correction, filtered the list, edited the correction with its existing invoice and removed that correction. All operations returned the expected 201/200/204 responses. A real manual sync through Django/RabbitMQ/Celery succeeded with 34 committed create/update operations.
- Docker validation used the existing temporary Compose override that removes the PostgreSQL host port mapping, because another project owns port 5432. No repository Compose changes or vendor failure-rate changes were made.

Remaining limits: Vite reports a bundle-size warning (about 1.47 MB minified / 454 KB gzip). The straightforward static imports were retained for this exercise; route-level lazy loading is a possible follow-up. Invoice lookup intentionally requires refining searches beyond the first 25 matches. Concurrent adjustment edits retain the backend's last-write-wins behavior, and sync tracking is per browser tab. The temporary browser checks are validation scripts, not an added Playwright dependency or a maintained browser-test suite.
