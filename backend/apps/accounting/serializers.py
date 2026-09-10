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
