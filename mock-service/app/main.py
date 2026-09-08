"""Mock external accounting service.

Stands in for a third-party accounting SaaS. Deliberately unhelpful in the ways
real integrations are: API-key auth, capped page sizes, `updated_at` filtering
with inclusive bounds, injected 5xx/429 responses and latency spikes, and a
dataset that keeps drifting under you.

Not part of the exercise — do not modify. Treat it as a vendor you cannot patch.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections import deque
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import config
from .data import dataset, normalize_timestamp

_chaos = random.Random(config.SEED + 1)
_request_log: deque[float] = deque()


# ----------------------------------------------------------------- lifespan


async def _drift_loop() -> None:
    while True:
        await asyncio.sleep(config.DRIFT_INTERVAL_SECONDS)
        result = dataset.drift(config.DRIFT_RECORDS_PER_TICK)
        print(f"[drift] {result}", flush=True)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_drift_loop()) if config.DRIFT_INTERVAL_SECONDS > 0 else None
    print(
        f"[mock-accounting] invoices={len(dataset.invoices)} "
        f"transactions={len(dataset.transactions)} "
        f"failure_rate={config.FAILURE_RATE} slow_rate={config.SLOW_RATE}",
        flush=True,
    )
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Mock Accounting Service",
    version="1.0.0",
    description="Pretend third-party accounting API. Flaky on purpose.",
    lifespan=lifespan,
)


# -------------------------------------------------------------- middleware


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if x_api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


def enforce_rate_limit() -> None:
    now = time.monotonic()
    window_start = now - config.RATE_LIMIT_WINDOW_SECONDS
    while _request_log and _request_log[0] < window_start:
        _request_log.popleft()

    if len(_request_log) >= config.RATE_LIMIT_REQUESTS:
        retry_after = int(config.RATE_LIMIT_WINDOW_SECONDS - (now - _request_log[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {config.RATE_LIMIT_REQUESTS} requests / "
            f"{config.RATE_LIMIT_WINDOW_SECONDS}s.",
            headers={"Retry-After": str(retry_after)},
        )
    _request_log.append(now)


async def inject_chaos() -> None:
    if _chaos.random() < config.FAILURE_RATE:
        status = _chaos.choice([500, 502, 503])
        raise HTTPException(status_code=status, detail="Upstream accounting service error.")

    if _chaos.random() < config.SLOW_RATE:
        await asyncio.sleep(_chaos.uniform(config.SLOW_MIN_SECONDS, config.SLOW_MAX_SECONDS))


DataEndpoint = [Depends(require_api_key), Depends(enforce_rate_limit), Depends(inject_chaos)]


# ---------------------------------------------------------------- endpoints


@app.get("/health", summary="Always healthy, never flaky.")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "invoices": len(dataset.invoices),
        "transactions": len(dataset.transactions),
    }


def _page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = config.DEFAULT_PAGE_SIZE,
    updated_since: Annotated[
        str | None,
        Query(description="ISO-8601 UTC timestamp. Returns records with updated_at >= this value (INCLUSIVE)."),
    ] = None,
) -> dict[str, Any]:
    if page_size > config.MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"page_size may not exceed {config.MAX_PAGE_SIZE}.",
        )
    if updated_since:
        try:
            updated_since = normalize_timestamp(updated_since)
        except ValueError:
            raise HTTPException(status_code=422, detail="updated_since must be an ISO-8601 timestamp.") from None
    return {"page": page, "page_size": page_size, "updated_since": updated_since}


@app.get("/api/v1/invoices", dependencies=DataEndpoint, summary="List invoices, oldest change first.")
async def list_invoices(params: Annotated[dict[str, Any], Depends(_page_params)]) -> dict[str, Any]:
    return dataset.list_invoices(**params)


@app.get("/api/v1/transactions", dependencies=DataEndpoint, summary="List transactions, oldest change first.")
async def list_transactions(params: Annotated[dict[str, Any], Depends(_page_params)]) -> dict[str, Any]:
    return dataset.list_transactions(**params)


@app.post("/admin/drift", summary="Force the dataset to change right now (never flaky).")
async def force_drift(records: Annotated[int, Query(ge=1, le=50)] = 5) -> dict[str, Any]:
    return dataset.drift(records)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"status": exc.status_code, "message": exc.detail}},
        headers=exc.headers,
    )
