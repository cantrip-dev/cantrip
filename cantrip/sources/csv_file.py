"""People from a CSV export: a Luma guest list, a registration form, an Eventbrite or Meetup list.

Eventbrite and Meetup put the first and last name in separate columns, sometimes
with different capitalisation ("First name", "Last Name"), so those are joined here.
Luma keeps a single `name` column.

Columns are matched by name, loosely, so most exports work as they are:
any column with "company" or "organization" in its header is the company,
"title", "role" or "position" is the job, "linkedin" is the LinkedIn URL, and
so on. A Luma export's `checked_in_at` column marks who actually attended.
"""

from __future__ import annotations

import csv
import io
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
        yield from _read(csv.DictReader(fh), source or f"csv:{path.stem}", signal)


def people_from_text(text: str, source: str = "csv:upload", signal: str = "registered") -> Iterator[Lead]:
    """Same as `people`, for CSV text already in memory (an upload in the UI)."""
    yield from _read(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))), source, signal)


def _read(reader: csv.DictReader, source: str, signal: str) -> Iterator[Lead]:
    columns = _match_columns(reader.fieldnames or [])
    for row in reader:
        values = {field: (row.get(header) or "").strip() for field, header in columns.items()}
        if not values.get("name"):
            lowered = {str(key).strip().lower(): value for key, value in row.items() if key}
            first = next((lowered[key] for key in ("first_name", "first name", "firstname", "given name")
                          if lowered.get(key)), "").strip()
            last = next((lowered[key] for key in ("last_name", "last name", "lastname", "surname")
                         if lowered.get(key)), "").strip()
            values["name"] = f"{first} {last}".strip()
        lead = Lead(source=source, signal=signal)
        for field in ("name", "email", "company", "title", "linkedin", "location", "website"):
            setattr(lead, field, values.get(field, ""))
        if values.get("github"):
            lead.github = login_from(values["github"])
        if "attended" in values:
            lead.signal = "attended" if _attended(values["attended"]) else signal
        if lead.name or lead.email or lead.linkedin:
            yield lead
