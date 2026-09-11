from rest_framework import serializers

from .fields import MoneyField
from .models import Adjustment, Invoice, SyncRun, validate_nonzero_amount


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["id", "external_id", "customer_name", "currency"]
        read_only_fields = fields


class AdjustmentSerializer(serializers.ModelSerializer):
    amount = MoneyField(validators=[validate_nonzero_amount])
    invoice_external_id = serializers.CharField(source="invoice.external_id", read_only=True)
    customer_name = serializers.CharField(source="invoice.customer_name", read_only=True)

    class Meta:
        model = Adjustment
        fields = [
            "id", "invoice", "invoice_external_id", "customer_name", "amount", "currency",
            "reason", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "currency", "created_at", "updated_at"]

    def validate(self, attrs):
        invoice = attrs.get("invoice")
        # Capture the currency only on creation or an explicit invoice reassignment.
        # Resubmitting the same invoice in PUT must preserve the original currency.
        if invoice is not None and (self.instance is None or invoice.pk != self.instance.invoice_id):
            attrs["currency"] = invoice.currency
        return attrs


class SyncRunSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.ReadOnlyField()
    records_touched = serializers.ReadOnlyField()

    class Meta:
        model = SyncRun
        fields = [
            "id", "trigger", "status", "created_at", "started_at", "finished_at",
            "duration_seconds", "records_touched", "sources", "reconciled", "unresolved", "error",
        ]
        read_only_fields = fields


class CurrencyAmountSerializer(serializers.Serializer):
    currency = serializers.CharField()
    # A sum can exceed the precision of an individual invoice/transaction.
    amount = serializers.DecimalField(max_digits=None, decimal_places=2, coerce_to_string=True)


class CollectionPeriodSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    timezone = serializers.CharField()


class InvoiceStatusCountSerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()


class DashboardSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    collection_period = CollectionPeriodSerializer()
    total_invoices = serializers.IntegerField()
    outstanding_by_currency = CurrencyAmountSerializer(many=True)
    collected_this_month_by_currency = CurrencyAmountSerializer(many=True)
    invoices_by_status = InvoiceStatusCountSerializer(many=True)
    last_sync = SyncRunSerializer(allow_null=True)
