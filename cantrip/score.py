"""Score a lead against your ideal customer profile (ICP).

Every point comes with a reason, so a person can see why a lead ranked
where it did. No black box: the rules live in the spell's TOML file.
Rules a spell leaves out simply don't count.
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


def _best_level(text: str, levels: list[dict[str, Any]]) -> tuple[int, str]:
    """Highest-scoring level whose words appear in `text`: (points, matched word)."""
    best = (0, "")
    for level in levels:
        word = _has_any(text, level.get("words", []))
        if word and level.get("points", 0) > best[0]:
            best = (level["points"], word)
    return best


def score(lead: Lead, icp: dict[str, Any]) -> Lead:
    points, reasons = 0, []
    weights = icp.get("weights", {})
    about = " ".join([lead.title, lead.bio])

    company = lead.company or (lead.email_domain.split(".")[0].title() if lead.has_work_email else "")
    if company:
        points += weights.get("has_company", 0)
        target = _has_any(" ".join([company, lead.email_domain]), icp.get("target_companies", []))
        if target:
            points += weights.get("target_company", 0)
            reasons.append(f"{target} is on your target list")

    seniority, word = _best_level(about, icp.get("seniority", []))
    if seniority:
        points += seniority
        reasons.append(f"senior: {word}")

    function, word = _best_level(about, icp.get("functions", []))
    if function:
        points += function
        reasons.append(f"role: {word}")

    topic = _has_any(" ".join([about, company]), icp.get("keywords", []))
    if topic:
        points += weights.get("keyword", 0)
        reasons.append(f"mentions {topic}")

    langs = [lang for lang in lead.top_languages if lang in icp.get("languages", [])]
    if langs:
        points += weights.get("language", 0)
        reasons.append(f"codes in {', '.join(langs)}")

    if weights.get("influence") and lead.followers >= icp.get("influencer_followers", 500):
        points += weights["influence"]
        reasons.append(f"{lead.followers} GitHub followers")

    if lead.signal == "attended":
        points += weights.get("attended", 0)
        reasons.append("attended")
    elif lead.signal == "contributed":
        points += weights.get("contributed", 0)
        reasons.append("contributed code")
    elif lead.signal == "mentioned" and lead.name:
        points += weights.get("named_person", 0)
        reasons.append("named on the page")

    if lead.has_work_email:
        points += weights.get("work_email", 0)
        reasons.append("work email")
    elif lead.email or lead.linkedin or lead.website:
        points += weights.get("reachable", 0)
        reasons.append("reachable")

    low = _has_any(about, icp.get("deprioritize", []))
    if low:
        points += weights.get("deprioritize", 0)
        reasons.append(f"lower priority: {low}")

    if _has_any(" ".join([company, lead.email_domain]), icp.get("exclude", [])):
        points, reasons = 0, ["excluded by your ICP"]

    tiers = icp.get("tiers", DEFAULT_TIERS)
    lead.score = max(0, min(points, 100))
    lead.tier = "hot" if lead.score >= tiers["hot"] else "warm" if lead.score >= tiers["warm"] else "cold"
    lead.reasons = reasons
    return lead
