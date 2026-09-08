"""Seeded, slowly-drifting fake accounting dataset.

The dataset is deterministic for a given SEED, so two candidates running the
service see the same starting data. A background "drift" job then mutates a
handful of records every DRIFT_INTERVAL_SECONDS and bumps their ``updated_at``,
which is what makes incremental (watermark-based) syncing meaningful.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import config

CURRENCIES = ("USD", "USD", "USD", "USD", "EUR", "GBP")
INVOICE_STATUSES = ("draft", "open", "paid", "void")
TRANSACTION_TYPES = ("payment", "payment", "payment", "refund", "fee")
PAYMENT_METHODS = ("bank_transfer", "card", "cash", "cheque")

COMPANY_PREFIX = (
    "Northwind", "Blue Ridge", "Vertex", "Cobalt", "Ironwood", "Lumen",
    "Harbour", "Solaris", "Kestrel", "Meridian", "Alder", "Quarry",
    "Copperline", "Fenwick", "Granite", "Halcyon",
)
COMPANY_SUFFIX = ("Logistics", "Foods", "Studios", "Partners", "Labs", "Group", "Trading", "Systems")


def _money(value: Decimal | float | str) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_timestamp(value: str) -> str:
    """Canonicalise a client-supplied ISO timestamp so it compares against stored values.

    Stored timestamps are second-precision UTC with a `Z` suffix, and filtering is a plain
    string comparison, so `+00:00` offsets and sub-second precision have to be flattened first.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _iso(parsed)


class Dataset:
    def __init__(self, seed: int, invoice_count: int) -> None:
        self.rng = random.Random(seed)
        self.invoices: dict[str, dict[str, Any]] = {}
        self.transactions: dict[str, dict[str, Any]] = {}
        self._next_invoice_number = 1
        self._next_transaction_number = 1
        self._build(invoice_count)

    # ---------------------------------------------------------------- build

    def _customers(self, count: int) -> list[dict[str, str]]:
        seen: set[str] = set()
        customers: list[dict[str, str]] = []
        while len(customers) < count:
            name = f"{self.rng.choice(COMPANY_PREFIX)} {self.rng.choice(COMPANY_SUFFIX)}"
            if name in seen:
                continue
            seen.add(name)
            slug = name.lower().replace(" ", "-")
            customers.append(
                {
                    "customer_id": f"CUS-{len(customers) + 1:04d}",
                    "customer_name": name,
                    "customer_email": f"ap@{slug}.example.com",
                }
            )
        return customers

    def _build(self, invoice_count: int) -> None:
        customers = self._customers(18)
        now = datetime.now(timezone.utc)

        for _ in range(invoice_count):
            customer = self.rng.choice(customers)
            issued = now - timedelta(days=self.rng.randint(0, 400), hours=self.rng.randint(0, 23))
            invoice = self._make_invoice(customer, issued)
            self.invoices[invoice["id"]] = invoice
            for transaction in self._make_transactions_for(invoice):
                self.transactions[transaction["id"]] = transaction

    def _make_invoice(self, customer: dict[str, str], issued: datetime) -> dict[str, Any]:
        invoice_id = f"INV-{self._next_invoice_number:06d}"
        self._next_invoice_number += 1

        subtotal = Decimal(self.rng.randrange(9_00, 24_000_00)) / 100
        tax = (subtotal * Decimal(self.rng.choice(["0", "0.05", "0.09", "0.20"]))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total = subtotal + tax
        status = self.rng.choices(INVOICE_STATUSES, weights=[5, 40, 50, 5])[0]

        if status == "paid":
            amount_paid = total
        elif status == "open":
            amount_paid = (total * Decimal(self.rng.choice(["0", "0", "0.25", "0.5"]))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            amount_paid = Decimal("0.00")

        issue_day: date = issued.date()
        terms = self.rng.choice([14, 30, 45, 60])

        return {
            "id": invoice_id,
            "customer_id": customer["customer_id"],
            "customer_name": customer["customer_name"],
            "customer_email": customer["customer_email"],
            "currency": self.rng.choice(CURRENCIES),
            "issue_date": issue_day.isoformat(),
            "due_date": (issue_day + timedelta(days=terms)).isoformat(),
            "status": status,
            "subtotal": _money(subtotal),
            "tax": _money(tax),
            "total": _money(total),
            "amount_paid": _money(amount_paid),
            "note": None,
            "updated_at": _iso(issued + timedelta(hours=self.rng.randint(0, 72))),
        }

    def _make_transactions_for(self, invoice: dict[str, Any]) -> list[dict[str, Any]]:
        paid = Decimal(invoice["amount_paid"])
        if paid <= 0:
            return []

        issued = datetime.fromisoformat(invoice["issue_date"]).replace(tzinfo=timezone.utc)
        splits = 1 if self.rng.random() < 0.7 else 2
        remaining = paid
        out: list[dict[str, Any]] = []
        for index in range(splits):
            amount = remaining if index == splits - 1 else (remaining / 2).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            remaining -= amount
            occurred = issued + timedelta(days=self.rng.randint(1, 40), hours=self.rng.randint(0, 23))
            out.append(self._make_transaction(invoice, "payment", amount, occurred))
        return out

    def _make_transaction(
        self,
        invoice: dict[str, Any] | None,
        kind: str,
        amount: Decimal,
        occurred: datetime,
    ) -> dict[str, Any]:
        transaction_id = f"TRX-{self._next_transaction_number:06d}"
        self._next_transaction_number += 1
        return {
            "id": transaction_id,
            "invoice_id": invoice["id"] if invoice else None,
            "type": kind,
            "method": self.rng.choice(PAYMENT_METHODS),
            "amount": _money(amount),
            "currency": invoice["currency"] if invoice else "USD",
            "occurred_at": _iso(occurred),
            "updated_at": _iso(occurred),
        }

    # ---------------------------------------------------------------- drift

    def drift(self, records: int) -> dict[str, int]:
        """Mutate a few records the way a live accounting system would."""
        now = datetime.now(timezone.utc)
        changed_invoices = 0
        new_transactions = 0

        candidates = [inv for inv in self.invoices.values() if inv["status"] in ("open", "draft")]
        self.rng.shuffle(candidates)

        for invoice in candidates[:records]:
            total = Decimal(invoice["total"])
            paid = Decimal(invoice["amount_paid"])
            outstanding = total - paid
            if outstanding <= 0:
                continue

            roll = self.rng.random()
            if roll < 0.15:
                invoice["status"] = "void"
            else:
                payment = outstanding if roll < 0.65 else (outstanding / 2).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                invoice["amount_paid"] = _money(paid + payment)
                invoice["status"] = "paid" if paid + payment >= total else "open"
                transaction = self._make_transaction(invoice, "payment", payment, now)
                self.transactions[transaction["id"]] = transaction
                new_transactions += 1

            invoice["updated_at"] = _iso(now)
            changed_invoices += 1

        # Occasionally a brand new invoice shows up upstream.
        if self.rng.random() < 0.5:
            sample = self.rng.choice(list(self.invoices.values()))
            customer = {
                "customer_id": sample["customer_id"],
                "customer_name": sample["customer_name"],
                "customer_email": sample["customer_email"],
            }
            invoice = self._make_invoice(customer, now)
            invoice["status"] = "open"
            invoice["amount_paid"] = "0.00"
            invoice["updated_at"] = _iso(now)
            self.invoices[invoice["id"]] = invoice
            changed_invoices += 1

        return {"invoices_changed": changed_invoices, "transactions_created": new_transactions}

    # --------------------------------------------------------------- query

    @staticmethod
    def _page(
        rows: list[dict[str, Any]],
        page: int,
        page_size: int,
        updated_since: str | None,
    ) -> dict[str, Any]:
        if updated_since:
            rows = [row for row in rows if row["updated_at"] >= updated_since]

        rows = sorted(rows, key=lambda row: (row["updated_at"], row["id"]))
        total = len(rows)
        start = (page - 1) * page_size
        items = rows[start : start + page_size]
        has_next = start + page_size < total
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "next_page": page + 1 if has_next else None,
        }

    def list_invoices(self, page: int, page_size: int, updated_since: str | None) -> dict[str, Any]:
        return self._page(list(self.invoices.values()), page, page_size, updated_since)

    def list_transactions(self, page: int, page_size: int, updated_since: str | None) -> dict[str, Any]:
        return self._page(list(self.transactions.values()), page, page_size, updated_since)


dataset = Dataset(seed=config.SEED, invoice_count=config.INVOICE_COUNT)
