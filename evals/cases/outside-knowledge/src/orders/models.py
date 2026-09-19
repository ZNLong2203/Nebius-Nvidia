"""Order models.

An order is a reference plus a list of lines, optionally with a discount. A line
quantity must be positive, and a discount may not exceed the order total.
"""

from pydantic import BaseModel, root_validator, validator


class OrderLine(BaseModel):
    sku: str
    quantity: int
    unit_price_cents: int

    @validator("quantity")
    def quantity_is_positive(cls, value):
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value


class Order(BaseModel):
    reference: str
    lines: list[OrderLine]
    discount_cents: int = 0

    @root_validator
    def discount_within_total(cls, values):
        lines = values.get("lines") or []
        gross = sum(line.quantity * line.unit_price_cents for line in lines)
        if values.get("discount_cents", 0) > gross:
            raise ValueError("discount exceeds the order total")
        return values


def total_cents(order: Order) -> int:
    gross = sum(line.quantity * line.unit_price_cents for line in order.lines)
    return gross - order.discount_cents
