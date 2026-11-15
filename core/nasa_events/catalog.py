"""Reads the project's variable catalog (core selection + master definitions)."""
from __future__ import annotations

import csv
from functools import lru_cache

from .config import CORE_CSV, MASTER_CSV


@lru_cache(maxsize=1)
def load_core_selection() -> tuple[dict, ...]:
    with CORE_CSV.open(encoding="utf-8") as fh:
        return tuple(csv.DictReader(fh))


def core_codes(source: str | None = None) -> list[str]:
    """Codes marked as 'nucleo' (optionally filtered by source)."""
    return [
        row["codigo"]
        for row in load_core_selection()
        if row["disposicion"] == "nucleo" and (source is None or row["fuente"] == source)
    ]


@lru_cache(maxsize=1)
def variable_metadata() -> dict[str, dict]:
    """Master CSV rows keyed by variable/layer code."""
    with MASTER_CSV.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return {row["Variable (código)"].strip(): row for row in rows}


def metadata(code: str) -> dict | None:
    return variable_metadata().get(code)
