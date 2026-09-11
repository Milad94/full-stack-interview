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
        read_only_fields = ["currency"]

    def validate(self, attrs):
        invoice = attrs.get("invoice")
        # Preserve the stored currency unless this is a new adjustment
        # or it is reassigned to another invoice.
        if invoice is not None and (self.instance is None or invoice.pk != self.instance.invoice_id):
            attrs["currency"] = invoice.currency
        return attrs


class SyncRunSerializer(serializers.ModelSerializer):
    records_touched = serializers.ReadOnlyField()

    class Meta:
        model = SyncRun
        fields = [
            "id", "status", "started_at", "records_touched", "error",
        ]


class CurrencyAmountSerializer(serializers.Serializer):
    currency = serializers.CharField()
    # A sum can exceed the precision of an individual invoice/transaction.
    amount = serializers.DecimalField(max_digits=None, decimal_places=2, coerce_to_string=True)


class InvoiceStatusCountSerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()


class DashboardSerializer(serializers.Serializer):
    total_invoices = serializers.IntegerField()
    outstanding_by_currency = CurrencyAmountSerializer(many=True)
    collected_this_month_by_currency = CurrencyAmountSerializer(many=True)
    invoices_by_status = InvoiceStatusCountSerializer(many=True)
    last_sync = SyncRunSerializer(allow_null=True)
