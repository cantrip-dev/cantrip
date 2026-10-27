"""Send leads to HubSpot as contacts, each with a note holding the score, the
reasons, the source and the draft. Works on HubSpot's free plan.

Setup: in HubSpot, Settings > Integrations > Private apps (newer accounts:
Development > Legacy apps) > Create, with the scopes crm.objects.contacts.read and
crm.objects.contacts.write; copy its access token into CANTRIP_HUBSPOT_TOKEN.
"""

from __future__ import annotations

import time

from cantrip.lead import Lead
from cantrip.sinks.http import CRMError, call, note_text, split_name

API = "https://api.hubapi.com/crm/v3/objects"
NOTE_TO_CONTACT = 202  # HubSpot's built-in association type for a note on a contact


class HubSpot:
    label = "HubSpot"

    def __init__(self, token: str):
        if not token:
            raise CRMError("HubSpot needs CANTRIP_HUBSPOT_TOKEN, a private app's access token.")
        self.headers = {"Authorization": f"Bearer {token}"}

    def prepare(self) -> None:
        call("GET", f"{API}/contacts?limit=1", self.headers)  # checks the token before the run

    def find(self, lead: Lead) -> bool:
        first, last = split_name(lead.name)
        if lead.email:
            filters = [{"propertyName": "email", "operator": "EQ", "value": lead.email}]
        else:
            filters = [{"propertyName": "firstname", "operator": "EQ", "value": first}]
            if last:
                filters.append({"propertyName": "lastname", "operator": "EQ", "value": last})
            if lead.company:
                filters.append({"propertyName": "company", "operator": "EQ", "value": lead.company})
        found = call("POST", f"{API}/contacts/search", self.headers,
                     {"filterGroups": [{"filters": filters}], "limit": 1})
        return bool(found.get("total"))

    def add(self, lead: Lead) -> None:
        first, last = split_name(lead.name)
        props = {"firstname": first, "lastname": last, "company": lead.company, "jobtitle": lead.title,
                 "lifecyclestage": "lead"}
        if lead.email:
            props["email"] = lead.email
        if lead.website.startswith("http"):
            props["website"] = lead.website
        contact = call("POST", f"{API}/contacts", self.headers, {"properties": {k: v for k, v in props.items() if v}})
        call("POST", f"{API}/notes", self.headers, {
            "properties": {"hs_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "hs_note_body": note_text(lead).replace("\n", "<br>")},
            "associations": [{"to": {"id": contact["id"]}, "types": [
                {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": NOTE_TO_CONTACT}]}],
        })
