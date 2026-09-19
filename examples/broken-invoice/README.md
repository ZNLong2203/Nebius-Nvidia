# broken-invoice

A deliberately broken billing module: Arborist's demo target, and one case in
`evals/`.

Three independent bugs, in three different files, none of which masks another:

1. `money.round_money` uses Python's banker's rounding, so half-cent amounts
   round down instead of away from zero.
2. `invoice.invoice_total` subtracts the coupon *after* tax, charging the
   customer tax on money they never paid.
3. `proration.billed_days` treats the period end date as exclusive, losing one
   day on every prorated charge.

Nine tests, four of them red. Each bug needs a different fix in a different
file, which is the point: a search that branches can test three rival theories
against the same starting state and keep whichever partial repairs hold, while
a linear agent has to guess the right order and never regress.

```bash
python -m pytest -q
# 4 failed, 5 passed
```
