from datetime import date

import pytest

from billing import InvoiceLine, invoice_total, line_total, prorate
from billing.money import round_money
from billing.proration import billed_days


def test_round_money_rounds_half_away_from_zero():
    assert round_money(2.675) == 2.68
    assert round_money(1.005) == 1.01


def test_round_money_leaves_exact_values_alone():
    assert round_money(10.0) == 10.0
    assert round_money(3.14) == 3.14


def test_line_total_applies_line_discount():
    line = InvoiceLine("widget", quantity=3, unit_price=10.0, line_discount_pct=10.0)
    assert line_total(line) == 27.0


def test_coupon_reduces_the_taxable_base():
    lines = [InvoiceLine("widget", quantity=1, unit_price=100.0)]
    # 100 - 20 coupon = 80 taxable, then 10% tax = 88.00
    assert invoice_total(lines, tax_pct=10.0, coupon=20.0) == 88.0


def test_invoice_total_without_coupon_is_just_tax():
    lines = [InvoiceLine("widget", quantity=2, unit_price=50.0)]
    assert invoice_total(lines, tax_pct=10.0) == 110.0


def test_coupon_never_makes_a_total_negative():
    lines = [InvoiceLine("widget", quantity=1, unit_price=10.0)]
    assert invoice_total(lines, tax_pct=10.0, coupon=500.0) == 0.0


def test_billed_days_is_inclusive():
    assert billed_days(date(2026, 4, 1), date(2026, 4, 30)) == 30


def test_prorate_charges_inclusive_days():
    charge = prorate(30.0, date(2026, 4, 1), date(2026, 4, 15), days_in_month=30)
    assert charge == 15.0


def test_prorate_rejects_zero_days_in_month():
    with pytest.raises(ValueError):
        prorate(30.0, date(2026, 4, 1), date(2026, 4, 15), days_in_month=0)
