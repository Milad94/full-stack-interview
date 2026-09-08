# Repository conventions

Monorepo for the take-home exercise. See `README.md` for the task itself.

```
backend/        Django 5 + DRF + Celery. Runs in Docker.
mock-service/   FastAPI stand-in for the vendor. Do not modify.
frontend/       React 19 + TS + Vite. Runs on the host, not in Docker.
```

## Frontend

`frontend/AGENTS.md` is binding, and the detailed rules live in `frontend/.claude/skills/`.
Read the relevant skill before writing frontend code. Short version: react-hook-form for forms,
yup for validation, MUI + emotion for UI, TanStack Query for server state — and nothing else.

## Backend

- Business logic belongs in the app, not in views or tasks. Views stay thin.
- Money is `DecimalField`. Never float.
- Aggregate in the database with `annotate`/`aggregate`. Looping a queryset to total something is
  a bug.
- Anything touching the external vendor must assume it will fail, hang, or return the same record
  twice.
- Tasks are idempotent and re-runnable by default.
- Migrations are committed.

## Don't

- Don't modify `mock-service/` — it represents a vendor you can't patch.
- Don't add authentication; it's out of scope.
- Don't add dependencies without a note in `NOTES.md` explaining why.
