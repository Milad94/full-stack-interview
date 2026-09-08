"""Serializers.

Manual adjustments need real validation — the frontend surfaces field errors,
so return them per-field rather than as one opaque message. Think about what an
invalid adjustment actually looks like in this domain.
"""

from rest_framework import serializers  # noqa: F401
