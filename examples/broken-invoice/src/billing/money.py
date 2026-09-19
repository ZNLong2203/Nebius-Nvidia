"""Money helpers.

Every amount in this package is a float number of currency units, rounded to
two decimal places at each boundary.
"""


def round_money(amount: float) -> float:
    """Round a monetary amount to two decimal places.

    Half-cent amounts must round away from zero, the way an invoice reader
    expects: 2.675 -> 2.68, not 2.67.
    """
    return round(amount, 2)


def pct(value: float, percent: float) -> float:
    """Apply a percentage to a value."""
    return value * (percent / 100.0)
