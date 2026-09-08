import os


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


SEED = _int("SEED", 1337)
API_KEY = os.getenv("API_KEY", "dev-secret-key")

MAX_PAGE_SIZE = _int("MAX_PAGE_SIZE", 100)
DEFAULT_PAGE_SIZE = _int("DEFAULT_PAGE_SIZE", 50)

# Chance a data request fails with 500/503 instead of returning data.
FAILURE_RATE = _float("FAILURE_RATE", 0.15)
# Chance a data request is served, but slowly (to exercise client timeouts).
SLOW_RATE = _float("SLOW_RATE", 0.10)
SLOW_MIN_SECONDS = _float("SLOW_MIN_SECONDS", 3.0)
SLOW_MAX_SECONDS = _float("SLOW_MAX_SECONDS", 8.0)

RATE_LIMIT_REQUESTS = _int("RATE_LIMIT_REQUESTS", 120)
RATE_LIMIT_WINDOW_SECONDS = _int("RATE_LIMIT_WINDOW_SECONDS", 60)

# The upstream dataset keeps changing, like a real accounting system would.
DRIFT_INTERVAL_SECONDS = _int("DRIFT_INTERVAL_SECONDS", 60)
DRIFT_RECORDS_PER_TICK = _int("DRIFT_RECORDS_PER_TICK", 5)

INVOICE_COUNT = _int("INVOICE_COUNT", 240)
