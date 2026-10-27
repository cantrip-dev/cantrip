"""People from a CSV export: Luma guests, a meetup list, a form.

Column names are matched loosely, so a Luma export works as-is.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from cantrip.lead import Lead

ALIASES = {
    "name": ("name", "full name", "full_name"),
    "email": ("email", "email address"),
    "company": ("company", "company name", "organization", "organisation", "what company do you work for?"),
    "title": ("title", "job title", "role", "what is your role?"),
    "handle": ("handle", "github", "github username", "username"),
    "location": ("location", "city"),
    "bio": ("bio", "about"),
    "website": ("website", "url", "linkedin", "linkedin url"),
}


def _pick(row: dict[str, str], field: str) -> str:
    lowered = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for alias in ALIASES[field]:
        if lowered.get(alias):
            return lowered[alias]
    if field == "name" and (lowered.get("first_name") or lowered.get("first name")):
        first = lowered.get("first_name") or lowered.get("first name")
        last = lowered.get("last_name") or lowered.get("last name") or ""
        return f"{first} {last}".strip()
    return ""


def people(path: str | Path, source: str = "", signal: str = "registered") -> Iterator[Lead]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            lead = Lead(source=source or f"csv:{path.stem}", signal=signal)
            for field in ALIASES:
                setattr(lead, field, _pick(row, field))
            if lead.name or lead.email or lead.handle:
                yield lead
