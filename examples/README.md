# Example repositories

Fixtures Arborist is demonstrated against. **The answer keys live here, not
inside the fixtures**, because anything inside a fixture is loaded into the
agent's context — a README that lists the bugs is an answer key, and a demo that
reads one proves nothing.

Keep the same rule for anything you add: the fixture describes the *expected
behaviour* (docstrings, test names), never the defect.

---

## broken-invoice

A billing module with **three independent bugs** in three files. Nine tests,
four red.

1. `money.round_money` uses Python's banker's rounding, so half-cent amounts
   round toward even instead of away from zero.
2. `invoice.invoice_total` subtracts the coupon *after* tax, charging the
   customer tax on money they never paid.
3. `proration.billed_days` treats the period end date as exclusive, losing one
   day on every prorated charge.

**What it measures: depth.** No single edit fixes all three, and none of them
masks another, so the search has to keep a partial repair and build the next fix
on top of it. A run that reaches green does so at depth 3.
