from datetime import date
from pathlib import Path

from ledger import in_period, large_count, load, total_cents

DATA = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"
SEPTEMBER = (date(2026, 9, 1), date(2026, 9, 30))


def september():
    return in_period(load(DATA), *SEPTEMBER)


def test_every_row_is_read():
    assert len(load(DATA)) == 200


def test_september_includes_the_final_day():
    """A transaction dated on the last day of the period belongs to it."""
    assert len(september()) == 200


def test_september_total():
    assert total_cents(september()) == 9_508_554


def test_large_is_inclusive_of_the_threshold():
    """An amount exactly equal to the threshold counts as large."""
    assert large_count(september()) == 49
