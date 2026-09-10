"""Validate the vendor contract and retry individual pages, sharing 429 cooldowns."""

import logging
import random
import time
from datetime import timezone as dt_timezone
from email.utils import parsedate_to_datetime

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import Currency, PaymentMethod, TransactionType

logger = logging.getLogger(__name__)


class VendorError(Exception):
    pass


class VendorAuthError(VendorError):
    pass


class MoneyField(serializers.DecimalField):
    def __init__(self):
        super().__init__(max_digits=18, decimal_places=2)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Expected a decimal string.")
        return super().to_internal_value(data)


class InvoicePayload(serializers.Serializer):
    id = serializers.CharField(source="external_id", max_length=100)
    customer_id = serializers.CharField(max_length=100)
    customer_name = serializers.CharField(max_length=255)
    customer_email = serializers.EmailField(max_length=254)
    currency = serializers.ChoiceField(choices=Currency.choices)
    issue_date = serializers.DateField()
    due_date = serializers.DateField()
    status = serializers.ChoiceField(choices=["draft", "open", "paid", "void"])
    subtotal = MoneyField()
    tax = MoneyField()
    total = MoneyField()
    amount_paid = MoneyField()
    note = serializers.CharField(allow_null=True, allow_blank=True, trim_whitespace=False)
    updated_at = serializers.DateTimeField(source="vendor_updated_at")


class TransactionPayload(serializers.Serializer):
    id = serializers.CharField(source="external_id", max_length=100)
    invoice_id = serializers.CharField(source="external_invoice_id", max_length=100, allow_null=True)
    type = serializers.ChoiceField(choices=TransactionType.choices)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    amount = MoneyField()
    currency = serializers.ChoiceField(choices=Currency.choices)
    occurred_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField(source="vendor_updated_at")


def retry_after_seconds(value):
    if value is None:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=dt_timezone.utc)
            return max(0, (moment - timezone.now()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0


class VendorClient:
    attempts = 5  # Total attempts, including the first request.
    timeout = (3.05, 10)
    page_size = 100

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["X-API-Key"] = settings.EXTERNAL_ACCOUNTING_API_KEY
        self.cooldown_until = 0

    def close(self):
        self.session.close()

    def page(self, source, page, updated_since):
        params = {"page": page, "page_size": self.page_size}
        if updated_since is not None:
            params["updated_since"] = updated_since.isoformat()
        url = f"{settings.EXTERNAL_ACCOUNTING_BASE_URL.rstrip('/')}/api/v1/{source}"
        error = ""
        for attempt in range(self.attempts):
            delay = self.cooldown_until - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                response = self.session.get(url, params=params, timeout=self.timeout, allow_redirects=False)
            except (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as exc:
                error = type(exc).__name__
            else:
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise VendorError(f"{source} page {page}: invalid JSON") from exc
                    self.validate_page(payload, source, page)
                    return payload
                error = f"HTTP {response.status_code}"
                if response.status_code in (401, 403):
                    raise VendorAuthError(f"{source} page {page}: {error}")
                if response.status_code != 429 and not 500 <= response.status_code < 600:
                    raise VendorError(f"{source} page {page}: {error}")
                if response.status_code == 429:
                    self.cooldown_until = max(
                        self.cooldown_until,
                        time.monotonic() + retry_after_seconds(response.headers.get("Retry-After")),
                    )
            # Preserve cooldown even on the final attempt, for the next source.
            logger.warning("Vendor %s page %s attempt %s/%s: %s", source, page, attempt + 1, self.attempts, error)
            if attempt + 1 < self.attempts:
                self.cooldown_until = max(self.cooldown_until, time.monotonic() + 2**attempt + random.uniform(0, 0.5))
        raise VendorError(f"{source} page {page}: {error} after {self.attempts} attempts")

    def validate_page(self, payload, source, page):
        if not isinstance(payload, dict):
            raise VendorError(f"{source} page {page}: invalid page envelope")
        items, total, next_page = payload.get("items"), payload.get("total"), payload.get("next_page")
        if (
            payload.get("page") != page
            or payload.get("page_size") != self.page_size
            or not isinstance(items, list)
            or len(items) > self.page_size
            or type(total) is not int or total < 0
            or "next_page" not in payload
            or (next_page is not None and (type(next_page) is not int or next_page != page + 1 or not items))
        ):
            raise VendorError(f"{source} page {page}: invalid pagination metadata")
