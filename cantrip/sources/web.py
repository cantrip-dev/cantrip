"""Find leads on the open web, guided by your profile.

1. An AI model reads your profile (and an optional brief) and plans searches.
2. A search service runs them; Cantrip reads the top pages.
3. The model lists only the people and companies a page actually names, with
   a short quote as evidence. Anyone whose name isn't really on the page is
   dropped, so made-up leads don't get through.
"""

from __future__ import annotations

import json
import re
from datetime import date
from collections.abc import Iterator
from typing import Any

from cantrip.ai import AI
from cantrip.lead import Lead
from cantrip.web import Search

PLAN_SYSTEM = """You plan web searches that find sales leads: named people, with their job titles, at companies that match
an ideal customer profile.
Good searches return pages that name people with their roles: conference speaker and sponsor pages, funding and
launch announcements that quote a founder or executive, "X joins Y as head of Z" news, team and about pages,
podcast and meetup guest pages, company blog posts signed by their author.
Rules: write plain searches the way a person would type them, 3 to 9 words; you may quote a job title, but use no
site: or OR operators; don't search LinkedIn; avoid searches that return job postings, job boards or "top 10 tools" roundups.
Vary the angle across searches: different sources, roles and company types.
Examples of good searches: "head of developer relations" AI startup joins | AI infrastructure startup raises seed
round founder | developer conference 2026 sponsors | "VP of marketing" devtools podcast interview"""

EXTRACT_SYSTEM = """You extract sales leads from one web page. List only people and companies the page itself names.
Rules:
- Never invent anyone or anything. If the page doesn't state a title or company, leave it empty.
- "evidence" is a short exact quote from the page (under 200 characters) showing why they're relevant.
- A company with no named person is only worth listing when the page shows it fits the profile (e.g. it sponsors
  events, launched something relevant, is hiring for a buyer role). Leave name and title empty for it.
  Don't list companies that are merely mentioned in a roundup, a "top 10" list or an ad.
- List only people the page presents in a role of their own: a speaker, an author, a founder or executive quoted
  or announced, a team member. Skip people mentioned in passing (e.g. a company's founders named on a job listing,
  a CEO cited in an article about something else), journalists and unrelated commenters.
- Job boards and listings of many companies are poor sources: list nothing from them unless the page names a
  specific person who fits.
- At most 15 leads per page."""

RESEARCH_SYSTEM = """You research one sales lead from web pages, to help write a relevant first note.
Write 2 to 4 short factual bullets about the person or their company that a salesperson could mention:
recent launches, funding, talks, posts, hiring, product focus. Every bullet must come from the pages given
and end with its source URL in brackets. If the pages are about someone else, say "No reliable information found." """

DRAFT_SYSTEM = """You write a short first outreach note from a founder or seller to a lead.
Rules: under 90 words; plain, warm and specific; open with the lead's first name; mention one true detail from
the evidence or research given; say briefly what's being offered and why it fits them, using only the offer and
pitch as written; end with the ask, as given, as a question; sign with the sender's name if given. No subject line.
Use only facts given here: never invent a date, a timeline, a meeting, a result, a number or a shared history."""


def _profile_brief(config: dict[str, Any]) -> str:
    icp = config.get("icp", {})
    roles = [w for level in icp.get("functions", []) for w in level.get("words", [])]
    return json.dumps({
        "selling": config.get("product", ""), "pitch": config.get("pitch", ""), "buyer_and_champion_roles": roles,
        "target_companies": icp.get("target_companies", []), "fit_keywords": icp.get("keywords", []),
        "skip": icp.get("exclude", []),
    })


def plan(ai: AI, config: dict[str, Any], brief: str = "", count: int = 8) -> list[str]:
    user = (f"Today is {date.today():%B %d, %Y}; favour recent pages.\n"
            f"Ideal customer profile: {_profile_brief(config)}\n"
            + (f"Extra brief from the user: {brief}\n" if brief else "")
            + f'Write {count} different web searches. Return {{"queries": ["..."]}}.')
    data = ai.json(PLAN_SYSTEM, user, max_tokens=800)
    queries = data.get("queries", []) if isinstance(data, dict) else data
    return [q.strip() for q in queries if isinstance(q, str) and q.strip()][:count]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _on_page(value: str, page: str) -> bool:
    return bool(value) and _norm(value) in page


def extract(ai: AI, config: dict[str, Any], url: str, text: str) -> list[Lead]:
    user = (f"Ideal customer profile: {_profile_brief(config)}\nPage URL: {url}\nPage text:\n{text}\n\n"
            'Return {"leads": [{"name": "", "title": "", "company": "", "evidence": "", '
            '"linkedin": "", "website": ""}]}.')
    data = ai.json(EXTRACT_SYSTEM, user, max_tokens=2000)
    page, leads = _norm(text), []
    for item in (data.get("leads", []) if isinstance(data, dict) else []):
        if not isinstance(item, dict):
            continue
        name, company = (item.get("name") or "").strip(), (item.get("company") or "").strip()
        if name and _norm(name) == _norm(company):
            name = ""  # a company put in the name field
        # Keep only what the page really says: the person (or, for a company lead, the company) must appear on it.
        if not (_on_page(name, page) if name else _on_page(company, page)):
            continue
        title = (item.get("title") or "").strip() if name else ""  # a role without a person isn't a lead
        linkedin = (item.get("linkedin") or "").strip()
        evidence = (item.get("evidence") or "").strip()
        if evidence and _norm(evidence)[:40] not in page:
            evidence = ""  # not a real quote from the page, so don't build a draft on it
        leads.append(Lead(
            name=name, company=company if _on_page(company, page) else "", title=title if _on_page(title, page) else "",
            linkedin=linkedin if "linkedin.com/" in linkedin and _on_page(linkedin, page) else "",
            website=(item.get("website") or "").strip(), evidence=evidence[:300],
            source=f"web:{url}", source_url=url, signal="mentioned"))
    return leads


# Sites that block automated reading, need a login, or are video/job boards with no names worth extracting.
SKIP_DOMAINS = ("linkedin.com", "youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com",
                "x.com", "twitter.com", "reddit.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
                "wellfound.com", "quora.com", "pinterest.com")


def _skip(url: str, extra: list[str]) -> bool:
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
    return any(host == d or host.endswith("." + d) for d in (*SKIP_DOMAINS, *extra))


def find(ai: AI, search: Search, config: dict[str, Any], brief: str = "", queries: list[str] | None = None,
         max_queries: int = 8, pages_per_query: int = 3, progress=print) -> Iterator[Lead]:
    queries = queries or plan(ai, config, brief, max_queries)
    skip = config.get("skip_domains", [])
    seen_urls: set[str] = set()
    for i, query in enumerate(queries, 1):
        progress(f"[{i}/{len(queries)}] searching: {query}")
        read = 0
        # Ask for extra results: some pages are skipped or can't be read.
        for result in search.search(query, count=pages_per_query * 2 + 2):
            if read >= pages_per_query:
                break
            if result.url in seen_urls or _skip(result.url, skip):
                continue
            seen_urls.add(result.url)
            text = search.read(result)
            if len(text) < 300:
                search.skipped += 1
                continue
            read += 1
            yield from extract(ai, config, result.url, text)


def research(ai: AI, search: Search, lead: Lead, pages: int = 3) -> str:
    who = " ".join(part for part in (f'"{lead.name}"' if lead.name else "", lead.company) if part)
    if not who:
        return ""
    sources = []
    for result in search.search(who, count=pages):
        if "linkedin.com" in result.url:
            continue
        sources.append(f"URL: {result.url}\n{search.read(result, max_chars=4000)}")
    if not sources:
        return ""
    user = (f"Lead: {lead.name or '(unknown)'}, {lead.title or '(title unknown)'} at {lead.company or '(company unknown)'}\n\n"
            + "\n\n---\n\n".join(sources))
    return ai.chat(RESEARCH_SYSTEM, user, max_tokens=500).strip()


def write_draft(ai: AI, lead: Lead, config: dict[str, Any]) -> str:
    facts = {
        "about_the_lead": {
            "name": lead.name, "title": lead.title, "company": lead.company,
            "what_a_page_said_about_them": lead.evidence, "page_it_was_on": lead.source_url,
            "how_they_came_to_us": "" if lead.signal == "mentioned" else lead.signal,
            "research_notes": lead.research,
        },
        "about_our_offer": {
            "offer": config.get("product", ""), "pitch": config.get("pitch", ""),
            "our_event": config.get("event_name", ""),
        },
        "ask": config.get("ask") or "a quick call", "sender": config.get("sender", ""),
        "note": "about_the_lead and about_our_offer are separate: the lead has no link to our offer or event "
                "unless how_they_came_to_us says so.",
    }
    return ai.chat(DRAFT_SYSTEM, json.dumps(facts), max_tokens=400).strip()
