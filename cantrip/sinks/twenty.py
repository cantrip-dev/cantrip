"""Send leads to Twenty, the open-source CRM, as people linked to their
company, each with a note holding the score, reasons, source and draft.

Setup: in Twenty, Settings > Developers (APIs & Webhooks) > Create API key; copy it into
CANTRIP_TWENTY_KEY. For a self-hosted Twenty, set CANTRIP_TWENTY_URL to its
address (default: Twenty's cloud, https://api.twenty.com).
"""

from __future__ import annotations

import json
import urllib.parse

from cantrip.lead import Lead
from cantrip.sinks.http import CRMError, call, note_text, split_name


def _first(data: dict) -> dict | None:
    """Twenty wraps results as {"data": {"people": [...]}} or {"data": {"createPerson": {...}}}."""
    for value in (data.get("data") or {}).values():
        if isinstance(value, list):
            return value[0] if value else None
        if isinstance(value, dict):
            return value
    return None


def _q(value: str) -> str:
    return json.dumps(value)  # quoted for Twenty's filter syntax


class Twenty:
    label = "Twenty"

    def __init__(self, key: str, url: str):
        if not key:
            raise CRMError("Twenty needs CANTRIP_TWENTY_KEY (an API key) and, if self-hosted, CANTRIP_TWENTY_URL.")
        self.base = url.rstrip("/") + "/rest"
        self.headers = {"Authorization": f"Bearer {key}"}
        self.companies: dict[str, str] = {}

    def _get(self, path: str, flt: str):
        return _first(call("GET", f"{self.base}/{path}?limit=1&filter={urllib.parse.quote(flt)}", self.headers))

    def prepare(self) -> None:
        call("GET", f"{self.base}/people?limit=1", self.headers)  # checks the key and address

    def find(self, lead: Lead) -> bool:
        if lead.email:
            return self._get("people", f"emails.primaryEmail[eq]:{_q(lead.email)}") is not None
        first, last = split_name(lead.name)
        flt = f"and(name.firstName[eq]:{_q(first)},name.lastName[eq]:{_q(last)})"
        return self._get("people", flt) is not None

    def _company_id(self, name: str) -> str | None:
        if not name:
            return None
        if name not in self.companies:
            found = self._get("companies", f"name[eq]:{_q(name)}")
            if found is None:
                found = _first(call("POST", f"{self.base}/companies", self.headers, {"name": name}))
            self.companies[name] = (found or {}).get("id")
        return self.companies[name]

    def add(self, lead: Lead) -> None:
        first, last = split_name(lead.name)
        person = {"name": {"firstName": first, "lastName": last}, "jobTitle": lead.title}
        if lead.email:
            person["emails"] = {"primaryEmail": lead.email}
        if lead.linkedin.startswith("http"):
            person["linkedinLink"] = {"primaryLinkUrl": lead.linkedin}
        company = self._company_id(lead.company)
        if company:
            person["companyId"] = company
        created = _first(call("POST", f"{self.base}/people", self.headers, person)) or {}
        try:  # the note is a bonus: older Twenty versions name its body field differently
            note = _first(call("POST", f"{self.base}/notes", self.headers,
                               {"title": f"Cantrip: {lead.score} ({lead.tier})",
                                "bodyV2": {"markdown": note_text(lead)}})) or {}
            if note.get("id") and created.get("id"):
                call("POST", f"{self.base}/noteTargets", self.headers,
                     {"noteId": note["id"], "personId": created["id"]})
        except CRMError:
            pass
