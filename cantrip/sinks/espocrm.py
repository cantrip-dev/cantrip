"""Send leads to EspoCRM, the open-source CRM, as Leads with status New; the
score, reasons, source and draft go in the description.

Setup: in EspoCRM, Administration > API Users > create one with an API key and a
role that can create and read Leads; set CANTRIP_ESPO_KEY to the key and
CANTRIP_ESPO_URL to your EspoCRM address.
"""

from __future__ import annotations

import urllib.parse

from cantrip.lead import Lead
from cantrip.sinks.http import CRMError, call, note_text, split_name


class EspoCRM:
    label = "EspoCRM"

    def __init__(self, key: str, url: str):
        if not key or not url:
            raise CRMError("EspoCRM needs CANTRIP_ESPO_KEY (an API user's key) and CANTRIP_ESPO_URL (its address).")
        self.base = url.rstrip("/") + "/api/v1"
        self.headers = {"X-Api-Key": key}

    def prepare(self) -> None:
        call("GET", f"{self.base}/Lead?maxSize=1", self.headers)

    def find(self, lead: Lead) -> bool:
        if lead.email:
            where = [("equals", "emailAddress", lead.email)]
        else:
            first, last = split_name(lead.name)
            where = [("equals", "firstName", first), ("equals", "lastName", last)]
        params = {"maxSize": 1, "select": "id"}
        for i, (kind, attribute, value) in enumerate(where):
            params.update({f"where[{i}][type]": kind, f"where[{i}][attribute]": attribute, f"where[{i}][value]": value})
        found = call("GET", f"{self.base}/Lead?{urllib.parse.urlencode(params)}", self.headers)
        return bool(found.get("total"))

    def add(self, lead: Lead) -> None:
        first, last = split_name(lead.name)
        record = {"firstName": first, "lastName": last or first, "accountName": lead.company, "title": lead.title,
                  "status": "New", "description": note_text(lead)}
        if lead.email:
            record["emailAddress"] = lead.email
        if lead.website.startswith("http"):
            record["website"] = lead.website
        call("POST", f"{self.base}/Lead", self.headers, {k: v for k, v in record.items() if v})
