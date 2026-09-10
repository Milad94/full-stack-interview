from rest_framework import serializers


class MoneyField(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(max_digits=18, decimal_places=2, coerce_to_string=True, **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Expected a decimal string.")
        return super().to_internal_value(data)
