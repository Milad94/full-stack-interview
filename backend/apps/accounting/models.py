"""Data model for the local mirror of the external accounting service.

Nothing is defined for you on purpose — the schema is part of what we want to
talk through. You will need somewhere to put, at minimum:

  * Invoices mirrored from the external service. Remember these arrive with the
    vendor's own identifiers, monetary values as decimal strings, mixed
    currencies, and an `updated_at` that changes upstream.
  * Transactions (payments / refunds / fees), which may or may not point at an
    invoice you have already seen.
  * A record of each sync run, good enough to answer "did the last sync work,
    when was it, and what did it touch?" from the dashboard.
  * Whatever the manual-adjustments feature needs (see README task 3).

Things worth deciding deliberately rather than by accident: which field is the
natural key for upserts, what you index, how you store money, and what happens
to a transaction whose invoice has not been synced yet.
"""

from django.db import models  # noqa: F401
