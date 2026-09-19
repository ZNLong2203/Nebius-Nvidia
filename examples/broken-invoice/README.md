# broken-invoice

A small billing module: line totals, invoice totals with tax and coupons, and
prorated charges for partial months.

```bash
python -m pytest -q
# 4 failed, 5 passed
```

The suite is red. Each test docstring and each function docstring states the
behaviour that is expected; the implementations do not all match.
