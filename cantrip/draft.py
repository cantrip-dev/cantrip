"""Draft a first note for each lead. Drafts only: Cantrip never sends.

v0.1 fills a template you control. Point an agent at the spell's SPELL.md to
have it rewrite each draft around what it learns about the person instead.
"""

from __future__ import annotations

from string import Formatter
from typing import Any

from cantrip.lead import Lead

SIGNAL_PHRASES = {
    "registered": "signed up for {event}",
    "attended": "came to {event}",
    "contributed": "contributed to {origin}",
    "starred": "starred {origin}",
    "found": "work on {topic}",
}


def _context(lead: Lead, spell: dict[str, Any]) -> dict[str, str]:
    origin = lead.source.split(":", 1)[-1]
    phrase = SIGNAL_PHRASES.get(lead.signal, "{origin}").format(
        origin=origin, event=spell.get("event_name") or "the event",
        topic=", ".join(lead.top_languages[:2]) or "open source")
    return {
        "first_name": lead.first_name,
        "company": lead.company or "your team",
        "title": lead.title or "your work",
        "event": spell.get("event_name") or "the event",
        "signal": phrase,
        "reason": lead.reasons[0] if lead.reasons else "",
        "sender": spell.get("sender", ""),
        "product": spell.get("product", ""),
        "ask": spell.get("ask", ""),
    }


def draft(lead: Lead, spell: dict[str, Any]) -> Lead:
    templates = spell.get("templates", {})
    template = templates.get(lead.tier) or templates.get("default", "")
    ctx = _context(lead, spell)
    unknown = {f for _, f, _, _ in Formatter().parse(template) if f} - ctx.keys()
    if unknown:
        raise ValueError(f"template uses unknown fields: {', '.join(sorted(unknown))}")
    lead.draft = template.format(**ctx).strip()
    return lead
