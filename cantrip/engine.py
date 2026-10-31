"""The shared core of a run, used by both the command line and the UI."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from cantrip.draft import draft
from cantrip.lead import Lead
from cantrip.score import score
from cantrip.sources import github
from cantrip.sources import web as web_source

TIERS_KEPT = {"hot": {"hot"}, "warm": {"hot", "warm"}, "cold": {"hot", "warm", "cold"}}


def unique(leads: Iterable[Lead]) -> Iterator[Lead]:
    seen = set()
    for lead in leads:
        if lead.key and lead.key in seen:
            continue
        seen.add(lead.key)
        yield lead


def said_no(lead: Lead, people: list[str]) -> bool:
    """Whether the person is on the profile's [skip] list, by GitHub login, email or LinkedIn link."""
    mine = {github.login_from(p).lower() for p in people} | {p.strip().lower().rstrip("/") for p in people}
    return bool(mine & {lead.github.lower(), lead.email.lower(), lead.linkedin.lower().rstrip("/")} - {""})


def run(config: dict[str, Any], leads: Iterable[Lead], add_github: bool = False,
        min_tier: str = "cold") -> list[Lead]:
    """Score and draft every lead, best first, leaving out anyone you said no to.
    Raises urllib.error.HTTPError if GitHub refuses."""
    results = []
    for lead in unique(leads):
        if said_no(lead, config.get("skip_people", [])):
            continue
        if add_github and lead.github and not lead.followers:
            github.enrich(lead)
        results.append(draft(score(lead, config.get("icp", {})), config))
    results.sort(key=lambda lead: lead.score, reverse=True)
    return [lead for lead in results if lead.tier in TIERS_KEPT[min_tier]]


def enhance(results: list[Lead], config: dict[str, Any], ai, search=None, research: bool = False,
            ai_drafts: bool = True, top: int = 15, progress=print) -> None:
    """For the best `top` leads: research them on the web, and/or rewrite their drafts with AI."""
    # Only people get drafts: a company with nobody named has no one to write to yet.
    people = [lead for lead in results if lead.tier != "cold" and (lead.name or lead.github)]
    for i, lead in enumerate(people[:top], 1):
        who = lead.name or lead.company or lead.github
        if research and search is not None:
            progress(f"[{i}] researching {who}")
            lead.research = web_source.research(ai, search, lead, config=config)
        if ai_drafts:
            progress(f"[{i}] writing a draft for {who}")
            lead.draft = web_source.write_draft(ai, lead, config)
