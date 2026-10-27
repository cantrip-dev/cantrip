"""The shared core of a run, used by both the command line and the UI."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from cantrip.draft import draft
from cantrip.lead import Lead
from cantrip.score import score
from cantrip.sources import github

TIERS_KEPT = {"hot": {"hot"}, "warm": {"hot", "warm"}, "cold": {"hot", "warm", "cold"}}


def unique(leads: Iterable[Lead]) -> Iterator[Lead]:
    seen = set()
    for lead in leads:
        if lead.key and lead.key in seen:
            continue
        seen.add(lead.key)
        yield lead


def run(config: dict[str, Any], leads: Iterable[Lead], add_github: bool = False,
        min_tier: str = "cold") -> list[Lead]:
    """Score and draft every lead, best first. Raises urllib.error.HTTPError if GitHub refuses."""
    results = []
    for lead in unique(leads):
        if add_github and lead.github and not lead.followers:
            github.enrich(lead)
        results.append(draft(score(lead, config.get("icp", {})), config))
    results.sort(key=lambda lead: lead.score, reverse=True)
    return [lead for lead in results if lead.tier in TIERS_KEPT[min_tier]]
