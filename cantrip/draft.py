"""Draft a first note for each lead. Drafts only: Cantrip never sends.

v0.1 fills a template you control. Point an agent at the spell's SPELL.md to
have it rewrite each draft around what it learns about the person instead.
"""

from __future__ import annotations

import re
from string import Formatter
from typing import Any

from cantrip.lead import Lead

SIGNAL_PHRASES = {
    "registered": "signed up for {event}",
    "attended": "came to {event}",
    "contributed": "contributed to {origin}",
    "starred": "starred {origin}",
    "forked": "forked {origin}",
    "found": "build with {topic}",
    "mentioned": "came up on {page}",
}


def _site(url: str) -> str:
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return host or "my research"


def _context(lead: Lead, spell: dict[str, Any]) -> dict[str, str]:
    origin = lead.source.split(":", 1)[-1]
    product, pitch = spell.get("product", "what we're building"), spell.get("pitch", "")
    phrase = SIGNAL_PHRASES.get(lead.signal, "{origin}").format(
        origin=origin, event=spell.get("event_name") or "the event", page=_site(lead.source_url),
        topic=", ".join(lead.top_languages[:2]) or "open source")
    if lead.signal == "contributed" and lead.contributions:
        phrase = f"made {lead.contributions} commit{'' if lead.contributions == 1 else 's'} to {origin}"
    if lead.signal == "forked" and lead.fork_pushed:
        phrase = f"forked {origin} and pushed to your copy since"
    return {
        "first_name": lead.first_name,
        "company": lead.company or "your team",
        "title": lead.title or "your work",
        "event": spell.get("event_name") or "the event",
        "signal": phrase,
        "reason": lead.reasons[0] if lead.reasons else "",
        "sender": spell.get("sender", ""),
        "product": product,
        "pitch": pitch,
        "product_line": f"{product}, {pitch}" if pitch else product,
        "ask": spell.get("ask") or "a quick call",
    }


def draft(lead: Lead, spell: dict[str, Any]) -> Lead:
    if not (lead.name or lead.github):
        lead.draft = ""  # a company with nobody named: no one to write to yet
        return lead
    templates = spell.get("templates", {})
    template = templates.get(lead.tier) or templates.get("default", "")
    ctx = _context(lead, spell)
    unknown = {f for _, f, _, _ in Formatter().parse(template) if f} - ctx.keys()
    if unknown:
        raise ValueError(f"template uses unknown fields: {', '.join(sorted(unknown))}")
    lead.draft = template.format(**ctx).strip()
    return lead
