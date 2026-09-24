"""Money helpers.

Every amount in this package is a float number of currency units, rounded to
 two decimal places at each boundary.
"""


def round_money(amount: float) -> float:
    """Round a monetary amount to two decimal places.

    Half-cent amounts must round away from zero, the way an invoice reader
    expects: 2.675 -> 2.68, not 2.67.
    """
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def pct(value: float, percent: float) -> float:
    """Apply a percentage to a value."""
    return value * (percent / 100.0)
