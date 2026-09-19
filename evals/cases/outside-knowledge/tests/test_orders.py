import pytest
from orders import Order, OrderLine, total_cents
from pydantic import ValidationError


def _order(**kw):
    defaults = {
        "reference": "SO-1",
        "lines": [{"sku": "widget", "quantity": 2, "unit_price_cents": 500}],
    }
    return Order(**{**defaults, **kw})


def test_total_is_gross_minus_discount():
    assert total_cents(_order(discount_cents=250)) == 750


def test_total_without_a_discount():
    assert total_cents(_order()) == 1000


def test_quantity_must_be_positive():
    with pytest.raises(ValidationError):
        OrderLine(sku="widget", quantity=0, unit_price_cents=500)


def test_discount_cannot_exceed_the_order_total():
    with pytest.raises(ValidationError):
        _order(discount_cents=99_999)
