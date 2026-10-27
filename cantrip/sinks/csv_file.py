from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from cantrip.lead import Lead


def write(leads: Iterable[Lead], path: str | Path) -> int:
    rows = [lead.to_row() for lead in leads]
    if not rows:
        Path(path).write_text("")
        return 0
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
