import uuid

from django.db import models


class Currency(models.TextChoices):
    USD = "USD", "US dollar"
    EUR = "EUR", "Euro"
    GBP = "GBP", "British pound"


class TransactionType(models.TextChoices):
    PAYMENT = "payment", "Payment"
    REFUND = "refund", "Refund"
    FEE = "fee", "Fee"


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    CARD = "card", "Card"
    CASH = "cash", "Cash"
    CHEQUE = "cheque", "Cheque"


class Invoice(models.Model):
    external_id = models.CharField(max_length=100, unique=True)
    customer_id = models.CharField(max_length=100)
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    currency = models.CharField(max_length=3, choices=Currency.choices)
    issue_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, db_index=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2)
    tax = models.DecimalField(max_digits=18, decimal_places=2)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=18, decimal_places=2)
    note = models.TextField(null=True, blank=True)
    vendor_updated_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(currency__in=Currency.values), name="invoice_currency_valid"),
        ]


class Transaction(models.Model):
    external_id = models.CharField(max_length=100, unique=True)
    external_invoice_id = models.CharField(max_length=100, null=True, db_index=True)
    invoice = models.ForeignKey(Invoice, null=True, on_delete=models.SET_NULL, related_name="transactions")
    type = models.CharField(max_length=20, choices=TransactionType.choices)
    method = models.CharField(max_length=30, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    occurred_at = models.DateTimeField(db_index=True)
    vendor_updated_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(currency__in=Currency.values), name="transaction_currency_valid"),
            models.CheckConstraint(condition=models.Q(type__in=TransactionType.values), name="transaction_type_valid"),
            models.CheckConstraint(condition=models.Q(method__in=PaymentMethod.values), name="transaction_method_valid"),
        ]


class SyncCheckpoint(models.Model):
    source = models.CharField(max_length=20, primary_key=True)
    watermark = models.DateTimeField(null=True)


class SyncRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        SKIPPED = "skipped"
        INTERRUPTED = "interrupted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trigger = models.CharField(max_length=20, default="scheduled")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    sources = models.JSONField(default=dict)
    reconciled = models.PositiveIntegerField(default=0)
    unresolved = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def duration_seconds(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    @property
    def records_touched(self):
        return sum(source.get("created", 0) + source.get("updated", 0) for source in self.sources.values())
