"""Send leads to a Notion database: one row per person, with a Status column to work from.

Setup: create an integration at notion.so/profile/integrations, copy its secret
(CANTRIP_NOTION_TOKEN), open your database, press ... > Connections and add the
integration, then copy the database link (CANTRIP_NOTION_DATABASE). Cantrip adds
any columns it needs the first time; your own columns are left alone.
"""

from __future__ import annotations

import re
import time

from cantrip.lead import Lead
from cantrip.sinks.http import CRMError, call

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
STATUSES = ["New", "Drafted", "Sent", "Replied", "Meeting", "Won", "Lost", "Not now"]
COLUMNS = {
    "Email": {"email": {}},
    "Company": {"rich_text": {}},
    "Title": {"rich_text": {}},
    "Score": {"number": {}},
    "Tier": {"select": {"options": [{"name": "hot", "color": "red"}, {"name": "warm", "color": "yellow"},
                                    {"name": "cold", "color": "gray"}]}},
    "Status": {"select": {"options": [{"name": s} for s in STATUSES]}},
    "LinkedIn": {"url": {}},
    "Source": {"url": {}},
    "Why": {"rich_text": {}},
    "Found": {"date": {}},
}


def database_id(value: str) -> str:
    """Accepts a database ID or a notion.so link to it."""
    match = re.search(r"([0-9a-f]{32})", value.replace("-", ""))
    if not match:
        raise CRMError("That doesn't look like a Notion database link or ID.")
    return match.group(1)


def _text(value: str) -> list[dict]:
    return [{"type": "text", "text": {"content": value[:2000]}}] if value else []


class Notion:
    label = "Notion"

    def __init__(self, token: str, database: str):
        if not token or not database:
            raise CRMError("Notion needs CANTRIP_NOTION_TOKEN (an integration secret) and CANTRIP_NOTION_DATABASE "
                           "(the database link).")
        self.headers = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
        self.db = database_id(database)
        self.title_column = "Name"
        self.types: dict[str, str] = {}

    def _call(self, method: str, path: str, body=None):
        time.sleep(0.35)  # Notion allows about 3 requests a second
        return call(method, f"{API}{path}", self.headers, body)

    def prepare(self) -> None:
        db = self._call("GET", f"/databases/{self.db}")
        columns = db.get("properties", {})
        self.title_column = next((name for name, col in columns.items() if col.get("type") == "title"), "Name")
        missing = {name: spec for name, spec in COLUMNS.items() if name not in columns}
        if missing:
            self._call("PATCH", f"/databases/{self.db}", {"properties": missing})
        self.types = {name: col.get("type") for name, col in columns.items()}
        self.types.update({name: next(iter(spec)) for name, spec in missing.items()})

    def find(self, lead: Lead) -> bool:
        if lead.email:
            flt = {"property": "Email", "email": {"equals": lead.email}}
        elif lead.linkedin:
            flt = {"property": "LinkedIn", "url": {"equals": lead.linkedin}}
        else:
            flt = {"and": [{"property": self.title_column, "title": {"equals": lead.name}},
                           {"property": "Company", "rich_text": {"equals": lead.company}}]}
        found = self._call("POST", f"/databases/{self.db}/query", {"filter": flt, "page_size": 1})
        return bool(found.get("results"))

    def add(self, lead: Lead) -> None:
        props = {
            self.title_column: {"title": _text(lead.name)},
            "Company": {"rich_text": _text(lead.company)},
            "Title": {"rich_text": _text(lead.title)},
            "Score": {"number": lead.score},
            "Tier": {"select": {"name": lead.tier or "cold"}},
            "Status": {"select": {"name": "Drafted" if lead.draft else "New"}},
            "Why": {"rich_text": _text("; ".join(lead.reasons))},
            "Found": {"date": {"start": time.strftime("%Y-%m-%d")}},
        }
        if lead.email:
            props["Email"] = {"email": lead.email}
        if lead.linkedin.startswith("http"):
            props["LinkedIn"] = {"url": lead.linkedin}
        if (lead.source_url or "").startswith("http"):
            props["Source"] = {"url": lead.source_url}
        blocks = []
        for heading, body in (("Evidence", lead.evidence), ("Research", lead.research), ("Draft (not sent)", lead.draft)):
            if body:
                blocks.append({"object": "block", "type": "heading_3",
                               "heading_3": {"rich_text": _text(heading)}})
                blocks += [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": _text(chunk)}}
                           for chunk in [body[i:i + 2000] for i in range(0, len(body), 2000)]]
        # A column you already had with another type (say a Notion "status" column) is left for you to fill.
        props = {k: v for k, v in props.items() if k == self.title_column or self.types.get(k) == next(iter(v))}
        self._call("POST", "/pages", {"parent": {"database_id": self.db}, "properties": props, "children": blocks})
