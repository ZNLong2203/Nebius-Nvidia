"""Reading the transaction file."""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .rules import THRESHOLD_CENTS, classify


@dataclass(frozen=True)
class Transaction:
    id: str
    on: date
    amount_cents: int
    category: str
    bucket: str


def load(path: str | Path) -> list[Transaction]:
    """Read every transaction in the file, in order."""
    out: list[Transaction] = []
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            amount = int(row["amount_cents"])
            out.append(
                Transaction(
                    id=row["id"],
                    on=date.fromisoformat(row["date"]),
                    amount_cents=amount,
                    category=row["category"],
                    bucket=classify(amount),
                )
            )
    return out
