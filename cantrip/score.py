"""Score a lead against your ideal customer profile (ICP).

Every point comes with a reason, so a person can see why a lead ranked
where it did. No black box: the rules live in the spell's TOML file.
"""

from __future__ import annotations

import re
from typing import Any

from cantrip.lead import Lead

DEFAULT_TIERS = {"hot": 60, "warm": 30}


def _has_any(text: str, words: list[str]) -> str:
    """First word from `words` found in `text` as a whole word, ignoring case."""
    for word in words:
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE):
            return word
    return ""


def score(lead: Lead, icp: dict[str, Any]) -> Lead:
    points, reasons = 0, []
    weights = icp.get("weights", {})

    if lead.company:
        points += weights.get("has_company", 10)
        reasons.append(f"works at {lead.company}")
        target = _has_any(lead.company, icp.get("target_companies", []))
        if target:
            points += weights.get("target_company", 40)
            reasons.append(f"{target} is on the target list")

    about = " ".join([lead.title, lead.bio])
    role = _has_any(about, icp.get("roles", []))
    if role:
        points += weights.get("role", 25)
        reasons.append(f"role looks like {role}")

    topic = _has_any(" ".join([about, lead.company]), icp.get("keywords", []))
    if topic:
        points += weights.get("keyword", 15)
        reasons.append(f"mentions {topic}")

    langs = [lang for lang in lead.top_languages if lang in icp.get("languages", [])]
    if langs:
        points += weights.get("language", 10)
        reasons.append(f"writes {', '.join(langs)}")

    if lead.followers >= icp.get("influencer_followers", 500):
        points += weights.get("influence", 15)
        reasons.append(f"{lead.followers} GitHub followers")

    if lead.email or lead.website:
        points += weights.get("reachable", 5)
        reasons.append("has a public way to reach them")

    if _has_any(" ".join([lead.company, lead.email]), icp.get("exclude", [])):
        points = 0
        reasons = ["excluded by your ICP"]

    tiers = icp.get("tiers", DEFAULT_TIERS)
    lead.score = min(points, 100)
    lead.tier = "hot" if lead.score >= tiers["hot"] else "warm" if lead.score >= tiers["warm"] else "cold"
    lead.reasons = reasons
    return lead
