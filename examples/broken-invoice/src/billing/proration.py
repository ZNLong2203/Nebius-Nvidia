"""Prorated charges for partial billing periods."""

from datetime import date

from .money import round_money


def billed_days(start: date, end: date) -> int:
    '''Number of days billed for a period.

    Both endpoints are inclusive: a subscription that runs from the 1st to the
    30th is billed for 30 days, not 29.
    '''
    return (end - start).days + 1


def prorate(monthly_price: float, start: date, end: date, days_in_month: int = 30) -> float:
    """Charge for a partial month."""
    if days_in_month <= 0:
        raise ValueError("days_in_month must be positive")
    days = billed_days(start, end)
    return round_money(monthly_price * days / days_in_month)
