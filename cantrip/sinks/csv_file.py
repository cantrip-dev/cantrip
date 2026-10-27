from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from cantrip.lead import Lead


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe(value):
    # Leads come from guest lists and web pages: a cell starting with = + - @ would run as a
    # formula when the CSV is opened in a spreadsheet, so it gets a leading '.
    return "'" + value if isinstance(value, str) and value.startswith(FORMULA_START) else value


def write(leads: Iterable[Lead], path: str | Path) -> int:
    rows = [{k: _safe(v) for k, v in lead.to_row().items()} for lead in leads]
    if not rows:
        Path(path).write_text("")
        return 0
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
