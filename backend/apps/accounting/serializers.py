from rest_framework import serializers

from .models import SyncRun


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
