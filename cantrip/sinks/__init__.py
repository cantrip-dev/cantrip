"""Where scored leads go: a CSV file, and optionally a CRM or a Notion database.

Every CRM connector adds people who aren't there yet and leaves people who
are alone (it never overwrites your status or notes), so you can run a spell
again without creating duplicates or contacting anyone twice.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from cantrip.lead import Lead
from cantrip.sinks.http import CRMError

CRMS = {
    "notion": ("Notion database", ("CANTRIP_NOTION_TOKEN", "CANTRIP_NOTION_DATABASE")),
    "hubspot": ("HubSpot (free plan works)", ("CANTRIP_HUBSPOT_TOKEN",)),
    "twenty": ("Twenty (open source)", ("CANTRIP_TWENTY_KEY", "CANTRIP_TWENTY_URL")),
    "espocrm": ("EspoCRM (open source)", ("CANTRIP_ESPO_KEY", "CANTRIP_ESPO_URL")),
}
TIER_RANK = {"hot": 2, "warm": 1, "cold": 0}


def connect(name: str, settings: dict[str, str] | None = None):
    """Make the connector for `name`, from `settings` (UI fields) or environment variables."""
    settings = {k: v for k, v in (settings or {}).items() if v}
    get = lambda key: settings.get(key) or os.environ.get(key, "")  # noqa: E731
    if name == "notion":
        from cantrip.sinks.notion import Notion
        return Notion(get("CANTRIP_NOTION_TOKEN"), get("CANTRIP_NOTION_DATABASE"))
    if name == "hubspot":
        from cantrip.sinks.hubspot import HubSpot
        return HubSpot(get("CANTRIP_HUBSPOT_TOKEN"))
    if name == "twenty":
        from cantrip.sinks.twenty import Twenty
        return Twenty(get("CANTRIP_TWENTY_KEY"), get("CANTRIP_TWENTY_URL") or "https://api.twenty.com")
    if name == "espocrm":
        from cantrip.sinks.espocrm import EspoCRM
        return EspoCRM(get("CANTRIP_ESPO_KEY"), get("CANTRIP_ESPO_URL"))
    raise CRMError(f"Unknown CRM '{name}'. Choose one of: {', '.join(CRMS)}.")


def push(crm, leads: Iterable[Lead], min_tier: str = "warm", progress=print) -> dict[str, int]:
    """Send people at or above `min_tier` to the CRM. Returns counts; sets each lead's `crm` field."""
    counts = {"added": 0, "already there": 0, "skipped": 0, "failed": 0}
    crm.prepare()
    for lead in leads:
        if TIER_RANK.get(lead.tier, 0) < TIER_RANK[min_tier]:
            continue
        if not lead.name:
            lead.crm = "skipped: no person named"
            counts["skipped"] += 1
            continue
        try:
            if crm.find(lead):
                lead.crm = f"already in {crm.label}"
                counts["already there"] += 1
            else:
                crm.add(lead)
                lead.crm = f"added to {crm.label}"
                counts["added"] += 1
                progress(f"added {lead.name} to {crm.label}")
        except CRMError as err:
            lead.crm = f"failed: {err}"
            counts["failed"] += 1
            if counts["failed"] >= 3 and counts["added"] == 0:
                raise  # the connection itself is broken; stop instead of failing every lead
    return counts
