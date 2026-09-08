# Take-home: Accounting sync & dashboard

You are building an internal tool that mirrors data from a third-party accounting service and
surfaces it to the finance team.

The infrastructure is already wired up. The interesting parts — the sync, the dashboard, and one
CRUD feature — are not. That's the exercise.

**Timebox: two days, and we mean it.** We are looking for roughly 6–8 hours of focused work, not a
weekend. If you run out of time, stop and write down what you'd do next in `NOTES.md`; an honest
"here's where I stopped and why" reads better than a rushed half-feature.

Afterwards we'll sit down together and walk through the code. Expect questions about *why*, so
where you made a judgement call, be ready to defend it.

---

## What you're given

| Piece | Where | State |
| --- | --- | --- |
| Mock external accounting API | `mock-service/` (FastAPI, port 8001) | Done. **Do not modify.** |
| Django + DRF project | `backend/` (port 8000) | Configured; app logic is stubbed out |
| Celery worker + beat against RabbitMQ | `docker-compose.yml` | Running; no tasks written |
| Postgres | `docker-compose.yml` (port 5432) | Running |
| React + TS frontend | `frontend/` (Vite, port 5173) | Scaffolded with one example feature |

Auth and user management are **out of scope**. Don't build login, roles, or permissions. The
Django admin has a bootstrapped `admin` / `admin` superuser if you want to eyeball the database.

## Setup

```bash
# Backend, worker, beat, Postgres, RabbitMQ, mock service
docker compose up --build

# Frontend (no Docker)
cd frontend
npm install
npm run dev
```

Then:

- App: http://localhost:5173
- API: http://localhost:8000/api/health/
- Django admin: http://localhost:8000/admin/ (`admin` / `admin`)
- Mock accounting API docs: http://localhost:8001/docs
- RabbitMQ management UI: http://localhost:15672 (`guest` / `guest`)

Useful commands:

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend pytest
docker compose logs -f worker beat
```

---

## The external service

Base URL inside compose: `http://mock-accounting:8001` (from your host: `http://localhost:8001`).
Auth: `X-API-Key: dev-secret-key`. Both are already in Django settings as
`EXTERNAL_ACCOUNTING_BASE_URL` / `EXTERNAL_ACCOUNTING_API_KEY`.

```
GET /api/v1/invoices?page=1&page_size=50&updated_since=2026-01-01T00:00:00Z
GET /api/v1/transactions?page=1&page_size=50&updated_since=...
```

Response:

```json
{
  "items": [ ... ],
  "page": 1,
  "page_size": 50,
  "total": 240,
  "next_page": 2
}
```

Things you need to know about it, because they are all deliberate:

- `page_size` is **capped at 100**; asking for more is a 422.
- Results are ordered by `updated_at` ascending.
- `updated_since` is **inclusive** (`updated_at >= value`), so you will re-fetch records you
  already have on every incremental run.
- Money arrives as **decimal strings** (`"1204.50"`), and invoices come in **USD, EUR and GBP**.
- It fails. Roughly 15% of data requests return 500/502/503, ~10% take 3–8 seconds, and there's a
  rate limit of 120 requests/minute that answers with 429 + `Retry-After`.
- The upstream dataset **drifts**: every 60 seconds a handful of invoices change status or get
  paid, and new invoices appear. `POST /admin/drift` forces it immediately, which is the fastest
  way to test an incremental sync without waiting.
- Transactions may reference an invoice you haven't stored yet.

You may turn `FAILURE_RATE` / `SLOW_RATE` down in `docker-compose.yml` while building. Put them
back before submitting — we run it at the defaults.

---

## Task 1 — Sync pipeline (the main event)

Mirror invoices and transactions into Postgres with a Celery task.

**Must:**

1. Run automatically **every 30 minutes** via Celery beat, and be triggerable on demand from the
   dashboard.
2. Handle pagination across the full dataset.
3. Be **idempotent** — running it twice must not duplicate or corrupt data.
4. Survive the vendor: retries with backoff, respect `Retry-After` on 429, don't hang forever on a
   slow response, and don't lose a page because one request failed.
5. Not run two syncs on top of each other.
6. Record each run (when, how long, outcome, what it touched, what went wrong) so the dashboard can
   report sync health.
7. Do incremental syncs after the first one. A full re-scan every 30 minutes is not acceptable, and
   note that watermarking against an inclusive filter has an edge case worth thinking about.

Design the schema yourself — `backend/apps/accounting/models.py` is empty on purpose.

**We'd like to see tests here**, at minimum: a second run changes nothing, and a mid-pagination
failure leaves the database in a sane state. `responses` is installed for stubbing the vendor.

## Task 2 — Dashboard

A single page in the React app showing:

1. Summary figures: total invoices, total outstanding, amount collected this month.
2. One chart (`@mui/x-charts`) — invoices by status, or collections over time, your call.
3. Sync health: when the last sync ran, whether it succeeded, how many records it touched.
4. A **Sync now** button that enqueues the task, gives immediate feedback, and reflects the result
   when it lands. Polling is fine; websockets are not expected.

Aggregation happens **in the database**. If you find yourself looping over a queryset in Python to
add up money, stop.

Mixed currencies are your problem to handle. Any defensible answer is fine — sum per currency, or
pick one and label it — as long as the number on screen isn't quietly wrong.

## Task 3 — Manual adjustments (form + table)

Finance needs to record corrections against synced invoices (a write-off, a disputed fee, a
currency-conversion difference).

**Backend:** DRF CRUD for an adjustment — at least an invoice reference, an amount, a reason, and
created/updated timestamps. Real validation with per-field errors. The list endpoint is paginated
and filterable/searchable.

**Frontend:** a react-hook-form + yup form to create and edit, and a table (`@mui/x-data-grid`)
with server-side pagination, a filter, and edit/delete. Server-side validation errors must land on
the right field.

Adjustments are ours, not the vendor's — a sync must never overwrite or delete them.

---

## Ground rules

- Stack is fixed: Django, DRF, Celery, RabbitMQ, Postgres on the backend; React, TypeScript, MUI,
  TanStack Query, react-hook-form, yup on the frontend. See `frontend/AGENTS.md` — those frontend
  conventions are requirements, not suggestions.
- Using AI assistance is fine and expected. Understanding every line you submit is also expected.
- Don't spend time on: authentication, deployment, CI, visual polish beyond "tidy and legible",
  Docker for the frontend, or 100% test coverage.

## What we care about

Correctness of the sync under failure and repetition; a schema that fits the domain; queries that
scale; sensible API design; a frontend that follows the conventions and handles loading, error and
empty states; and clear reasoning.

## Submitting

A git repo (or zip) with your commit history, plus a `NOTES.md` covering:

- How to run anything that isn't just `docker compose up`.
- The decisions you'd want to defend, and the tradeoffs behind them.
- What you'd do with another week.
- Anything you knowingly left broken or unfinished.
