"""Invoice totals."""

from dataclasses import dataclass

from .money import pct, round_money


@dataclass
class InvoiceLine:
    description: str
    quantity: int
    unit_price: float
    line_discount_pct: float = 0.0


def line_total(line: InvoiceLine) -> float:
    """Total for a single line, after its own discount."""
    gross = line.quantity * line.unit_price
    return round_money(gross - pct(gross, line.line_discount_pct))


def invoice_total(
    lines: list[InvoiceLine],
    tax_pct: float = 0.0,
    coupon: float = 0.0,
) -> float:
    '''Total payable for an invoice.

    Order of operations matters. A coupon is a reduction of the taxable base,
    so it comes off the subtotal *before* tax is calculated -- not off the
    grand total afterwards, which would silently charge the customer tax on
    money they never paid.
    '''
    subtotal = round_money(sum(line_total(line) for line in lines))
    taxable = max(0.0, subtotal - coupon)
    taxed = taxable + pct(taxable, tax_pct)
    return round_money(taxed)
