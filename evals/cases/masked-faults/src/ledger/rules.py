"""Classification rules for ledger entries."""

# A transaction is "large" at or above five hundred currency units.
THRESHOLD = 50_000


def is_large(amount_cents: int) -> bool:
    """Whether an amount counts as large.

    The boundary is inclusive: an amount exactly equal to the threshold is
    large.
    """
    return amount_cents > THRESHOLD


def classify(amount_cents: int) -> str:
    """Bucket an amount for reporting."""
    return "large" if is_large(amount_cents) else "ordinary"
