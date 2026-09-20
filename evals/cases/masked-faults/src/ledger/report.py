"""Period reporting."""

from datetime import date

from .parse import Transaction


def in_period(transactions: list[Transaction], start: date, end: date) -> list[Transaction]:
    """Transactions falling in a reporting period.

    Both endpoints are inclusive: a transaction dated on the last day of the
    period belongs to that period.
    """
    return [t for t in transactions if start <= t.on < end]


def total_cents(transactions: list[Transaction]) -> int:
    """Sum of the amounts."""
    return sum(t.amount_cents for t in transactions)


def large_count(transactions: list[Transaction]) -> int:
    """How many of these are classified as large."""
    return sum(1 for t in transactions if t.bucket == "large")
