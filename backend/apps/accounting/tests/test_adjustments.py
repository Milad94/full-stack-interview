from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounting.models import Adjustment, Invoice

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 10, 12, tzinfo=dt_timezone.utc)
URL = "/api/adjustments/"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def invoices():
    return [Invoice.objects.create(
        external_id=f"INV-{currency}", customer_id=f"CUS-{currency}",
        customer_name=f"Customer {currency}", customer_email="ap@example.com",
        currency=currency, status="open", issue_date=NOW.date(), due_date=NOW.date(),
        subtotal=Decimal("100.00"), tax=Decimal("0.00"), total=Decimal("100.00"),
        amount_paid=Decimal("0.00"), vendor_updated_at=NOW,
    ) for currency in ["EUR", "USD"]]


def test_crud_exact_amounts_and_owned_fields(api, invoices, monkeypatch):
    inv = invoices[0]
    mirror_before = list(Invoice.objects.values())
    monkeypatch.setattr(timezone, "now", lambda: NOW)
    response = api.post(URL, {
        "invoice": inv.pk, "amount": "-9999999999999999.99", "reason": "  Write-off  ",
        "currency": "GBP", "created_at": "2000-01-01T00:00:00Z",
    }, format="json")
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == "-9999999999999999.99"
    assert data["currency"] == "EUR"
    assert data["reason"] == "Write-off"
    assert data["invoice_external_id"] == inv.external_id
    obj = Adjustment.objects.get(pk=data["id"])
    assert obj.amount == Decimal("-9999999999999999.99")
    assert obj.created_at == obj.updated_at == NOW
    detail = f'{URL}{data["id"]}/'
    assert api.get(detail).json() == data

    monkeypatch.setattr(timezone, "now", lambda: NOW + timedelta(minutes=1))
    response = api.patch(detail, {"amount": "0.10"}, format="json")
    assert response.status_code == 200
    assert response.json()["amount"] == "0.10"
    obj.refresh_from_db()
    assert obj.created_at == NOW
    assert obj.updated_at == NOW + timedelta(minutes=1)

    response = api.put(detail, {
        "invoice": inv.pk, "amount": "12.34", "reason": "Disputed fee",
    }, format="json")
    assert response.status_code == 200
    assert response.json()["amount"] == "12.34"
    assert response.json()["reason"] == "Disputed fee"
    assert api.delete(detail).status_code == 204
    assert api.get(detail).status_code == 404
    assert not Adjustment.objects.exists()
    assert list(Invoice.objects.values()) == mirror_before


@pytest.mark.parametrize("field,value", [
    ("invoice", None), ("invoice", 999999), ("invoice", "INV-EUR"),
    ("amount", None), ("amount", "0"), ("amount", "-0.00"),
    ("amount", "1.001"), ("amount", "10000000000000000.00"),
    ("amount", "NaN"), ("amount", "Infinity"), ("amount", "invalid"),
    ("amount", 12.34), ("amount", 12), ("amount", True),
    ("reason", None), ("reason", " \n\t "), ("reason", "x" * 1001),
])
def test_invalid_fields_return_field_errors_without_writes(api, invoices, field, value):
    payload = {"invoice": invoices[0].pk, "amount": "-1.23", "reason": "Correction"}
    response = api.post(URL, {**payload, field: value}, format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert isinstance(response.json()[field], list)
    assert not Adjustment.objects.exists()

    obj = Adjustment.objects.create(invoice=invoices[0], amount="-1.23", currency="EUR", reason="Correction")
    before = Adjustment.objects.values().get(pk=obj.pk)
    response = api.patch(f"{URL}{obj.pk}/", {field: value}, format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert Adjustment.objects.values().get(pk=obj.pk) == before


def test_required_fields_are_reported_together(api):
    response = api.post(URL, {}, format="json")
    assert response.status_code == 400
    assert set(response.json()) == {"invoice", "amount", "reason"}


def test_currency_snapshot_survives_edits_and_changes_on_invoice_reassignment(api, invoices):
    inv, other = invoices
    obj = Adjustment.objects.create(invoice=inv, amount="-1.23", currency="EUR", reason="Correction")
    Invoice.objects.filter(pk=inv.pk).update(currency="GBP")
    detail = f"{URL}{obj.pk}/"
    # A form can submit the same invoice again after the vendor changes currency.
    response = api.put(detail, {
        "invoice": inv.pk, "amount": "-2.34", "reason": "Updated correction", "currency": "GBP",
    }, format="json")
    assert response.status_code == 200
    assert response.json()["currency"] == "EUR"
    response = api.patch(detail, {"invoice": other.pk}, format="json")
    assert response.status_code == 200
    assert response.json()["currency"] == "USD"
    assert response.json()["invoice_external_id"] == other.external_id


def test_list_pagination_filters_search_and_bounded_queries(api, invoices, django_assert_num_queries):
    inv, other = invoices
    Adjustment.objects.bulk_create([
        Adjustment(invoice=inv, amount="-1.01", currency="EUR", reason="Disputed fee")
        for _ in range(105)
    ] + [Adjustment(invoice=other, amount="2.02", currency="USD", reason="Conversion difference")])
    expected = list(Adjustment.objects.values_list("pk", flat=True))
    with django_assert_num_queries(2):
        response = api.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 106
    assert len(data["results"]) == 25
    assert data["previous"] is None and "page=2" in data["next"]
    assert [row["id"] for row in data["results"]] == expected[:25]
    page2 = api.get(URL, {"page": 2}).json()
    assert [row["id"] for row in page2["results"]] == expected[25:50]
    with django_assert_num_queries(2):
        large_page = api.get(URL, {"page_size": 1000}).json()
    assert len(large_page["results"]) == 100
    assert len(api.get(URL, {"page_size": 10}).json()["results"]) == 10

    for params, count in [
        ({"invoice": inv.pk}, 105), ({"currency": "USD"}, 1),
        ({"search": "disputed"}, 105), ({"search": "INV-USD"}, 1),
        ({"search": "Customer USD"}, 1),
        ({"invoice": inv.pk, "currency": "EUR", "search": "fee"}, 105),
        ({"invoice": inv.pk, "search": "conversion"}, 0),
    ]:
        response = api.get(URL, params)
        assert response.status_code == 200
        assert response.json()["count"] == count
    for params, field in [({"invoice": "not-an-id"}, "invoice"), ({"currency": "JPY"}, "currency")]:
        response = api.get(URL, params)
        assert response.status_code == 400
        assert field in response.json()
    assert api.get(URL, {"page": 999}).status_code == 404


def test_invoice_lookup_for_form_is_paginated_and_searchable(api, invoices):
    response = api.get("/api/invoices/", {"search": "Customer EUR"})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0] == {
        "id": invoices[0].pk, "external_id": "INV-EUR", "customer_name": "Customer EUR",
        "currency": "EUR",
    }


def test_database_protects_adjustment_amount_currency_and_invoice(invoices):
    obj = Adjustment.objects.create(invoice=invoices[0], amount="-1.23", currency="EUR", reason="Correction")
    for changes, constraint in [
        ({"amount": Decimal("0.00")}, "adjustment_amount_nonzero"),
        ({"currency": "JPY"}, "adjustment_currency_valid"),
    ]:
        with pytest.raises(IntegrityError) as error, transaction.atomic():
            Adjustment.objects.filter(pk=obj.pk).update(**changes)
        assert error.value.__cause__.diag.constraint_name == constraint
    with pytest.raises(ProtectedError):
        invoices[0].delete()
    assert Adjustment.objects.filter(pk=obj.pk).exists()
