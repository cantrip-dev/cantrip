"""People from a CSV export: a Luma guest list, a registration form, a meetup list.

Columns are matched by name, loosely, so most exports work as they are:
any column with "company" or "organization" in its header is the company,
"title", "role" or "position" is the job, "linkedin" is the LinkedIn URL, and
so on. A Luma export's `checked_in_at` column marks who actually attended.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from cantrip.lead import Lead
from cantrip.sources.github import login_from

# field -> (exact header names, words that may appear inside a header)
COLUMNS = {
    "name": (("name", "full name", "full_name", "attendee name"), ()),
    "email": (("email", "email address", "e-mail"), ("email",)),
    "company": (("company",), ("company", "organization", "organisation", "employer", "work for")),
    "title": (("title",), ("job title", "title", "role", "position", "what do you do")),
    "linkedin": (("linkedin",), ("linkedin",)),
    "github": (("github",), ("github",)),
    "location": (("location", "city"), ("location", "city")),
    "website": (("website", "url"), ("website",)),
}
ATTENDED_COLUMNS = ("checked_in_at", "checked in", "attended", "checked_in")


def _match_columns(headers: list[str]) -> dict[str, str]:
    lowered = {h: h.strip().lower() for h in headers if h}
    found: dict[str, str] = {}
    for field, (exact, contains) in COLUMNS.items():
        hit = next((h for h, low in lowered.items() if low in exact), None)
        hit = hit or next((h for h, low in lowered.items() if any(word in low for word in contains)
                           and h not in found.values()), None)
        if hit:
            found[field] = hit
    for h, low in lowered.items():
        if low in ATTENDED_COLUMNS:
            found["attended"] = h
    return found


def _attended(value: str) -> bool:
    return value.strip().lower() not in ("", "no", "false", "0", "n")


def people(path: str | Path, source: str = "", signal: str = "registered") -> Iterator[Lead]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = _match_columns(reader.fieldnames or [])
        for row in reader:
            values = {field: (row.get(header) or "").strip() for field, header in columns.items()}
            if not values.get("name"):
                first = (row.get("first_name") or row.get("First Name") or "").strip()
                last = (row.get("last_name") or row.get("Last Name") or "").strip()
                values["name"] = f"{first} {last}".strip()
            lead = Lead(source=source or f"csv:{path.stem}", signal=signal)
            for field in ("name", "email", "company", "title", "linkedin", "location", "website"):
                setattr(lead, field, values.get(field, ""))
            if values.get("github"):
                lead.github = login_from(values["github"])
            if "attended" in values:
                lead.signal = "attended" if _attended(values["attended"]) else signal
            if lead.name or lead.email or lead.linkedin:
                yield lead
