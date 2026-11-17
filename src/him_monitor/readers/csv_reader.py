from __future__ import annotations

import csv
from pathlib import Path


def read_csv(path: str | Path) -> tuple[list[dict[str, str]], str | None]:
    """Read a CSV artifact without imposing laboratory-specific column names."""
    try:
        with Path(path).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return [], "CSV has no header row"
            return list(reader), None
    except (OSError, csv.Error, UnicodeError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
