"""A short summary of a run, printed after the CSV is written."""

from __future__ import annotations

from collections import Counter

from cantrip.lead import Lead


def summary(leads: list[Lead], top: int = 10) -> str:
    tiers = Counter(lead.tier for lead in leads)
    lines = [f"hot {tiers['hot']}, warm {tiers['warm']}, cold {tiers['cold']}"]
    companies = Counter(lead.company for lead in leads if lead.company and lead.tier != "cold")
    multi = [(c, n) for c, n in companies.most_common(top) if n > 1]
    if multi:
        lines.append("Companies with several good-fit people: " + ", ".join(f"{c} ({n})" for c, n in multi))
    best = [lead for lead in leads if lead.tier == "hot"][:5]
    if best:
        lines.append("Top leads:")
        for lead in best:
            role = " at ".join(part for part in (lead.title, lead.company) if part)
            lines.append(f"  {lead.score:>3}  {lead.name or lead.github}" + (f", {role}" if role else ""))
    return "\n".join(lines)
