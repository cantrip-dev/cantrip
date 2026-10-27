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
an ideal customer profile, ideally at a moment that makes now a good time to reach them (the profile's why_now
signals).
Good searches return pages about ONE company or ONE person, with a why-now signal on the page: a single company's
funding or launch announcement quoting its founder, "X joins Y as head of Z" news, "we're hiring our first ..." posts
by the company itself, a founder's own post or podcast episode about what they're working on now, a team page.
Bad searches return pages that list many people or companies: funding roundups, "top 50 founders" lists, investor
lists, job boards, award lists, big conference speaker lists. Skip those angles entirely.
If the profile lists company stages, aim at companies of that stage, not large or public companies.
Rules: write plain searches the way a person would type them, 3 to 9 words; you may quote a phrase, but use no
site: or OR operators; don't search LinkedIn. Vary the angle across searches: different signals, roles and sources.
Examples of good searches: devtool startup announces seed round founder | "head of growth" joins AI startup |
"our first sales hire" startup founder blog | open source startup launches cloud founder interview"""

EXTRACT_SYSTEM = """You extract sales leads from one web page, for the ideal customer profile given. Quality matters far
more than quantity: an empty list is a fine answer.
Rules:
- List only people and companies the page itself names. Never invent anyone or anything; if the page doesn't
  state a title, company or stage, leave it empty.
- List only people the page presents in a role of their own at a company that plausibly fits the profile: a founder
  or executive announced or quoted about their own company, an author writing about their own work, a new hire
  announced. Skip people mentioned in passing, people in lists of many people or companies (roundups, rankings,
  investor lists, speaker grids), journalists, investors and commenters.
- If the profile lists company stages, skip people at large, established or public companies.
- "evidence": a short exact quote from the page (under 200 characters) showing who they are and why they fit.
- "why_now": a short exact quote from the page showing one of the profile's why_now signals for this person or
  their company (e.g. a round just raised, a first sales or growth hire, a launch). Leave it empty unless the page
  really says so; don't stretch an unrelated detail into a signal.
- "stage": the company's stage or size only as the page states it (e.g. "seed", "Series A", "public company").
- A company with no named person: list it only with a why_now quote. Leave name and title empty.
- At most 5 leads per page."""

RESEARCH_SYSTEM = """You research one sales lead from web pages, to help write a relevant first note.
Write 2 to 4 short factual bullets about the person or their company that a salesperson could use, most useful
first: anything matching the seller's why-now signals (given), then recent launches, funding, hiring, posts about
the problem the seller's product solves. Every bullet must come from the pages given and end with its source URL
in brackets. Don't include facts unrelated to the seller's offer. If the pages are about someone else, say
"No reliable information found." """

HOOK_SYSTEM = """You write the one opening sentence of an outreach note: a plain statement of a fact about the lead,
taken from the why_now quote (or, if there is none, from the evidence only when it is directly about the problem the
seller's pitch solves). The rest of the note is written separately, so write nothing else.
Rules: under 25 words; a statement of fact, e.g. "Saw that Acme closed its seed round in June." Don't add what it
means for them, what they need, plan, feel or will face; no "probably", "now comes", "as you scale", no praise,
no "congrats". Don't say "just" unless the quote dates it to the last few weeks. Don't mention the seller's offer.
If nothing given qualifies, answer exactly: NONE"""

GUESSING = re.compile(r"\b(probably|likely|you'll|you will|you need|you're going to|now comes|as you scale|"
                      r"which means|congrat\w*|must be|I bet|imagine)\b", re.IGNORECASE)


WHY_NOW_SYSTEM = """You help a seller decide when to reach out. Given what they sell and who buys it, propose the
why-now signals: public, findable events that make a company or person likely to need the offer right now.
Rules:
- Each signal is narrow and specific to this offer and buyer, not something every company does ("just launched a
  product" is too broad; "hiring its first sales or growth person" is specific for a sales tool).
- Each must show up on a page about ONE company or person: its own announcement, job post, launch post, or a
  founder's own post. Not on news roundups, listicles or job boards.
- "why": one plain sentence on why that moment makes the offer timely.
- "search": 3 to 9 plain words that would return such pages about individual companies (no operators)."""

WHY_NOW_CHECK = """You check search results. Return the numbers of the results that are about one specific, named
company or person showing the signal given (its own announcement, job post, launch or post). Exclude roundups,
lists, guides, how-to articles, job boards with many companies, and generic pages."""


def _profile_brief(config: dict[str, Any]) -> str:
    icp = config.get("icp", {})
    roles = [w for level in icp.get("functions", []) for w in level.get("words", [])]
    return json.dumps({
        "selling": config.get("product", ""), "pitch": config.get("pitch", ""), "buyer_and_champion_roles": roles,
        "why_now": icp.get("why_now", []), "company_stages": icp.get("stages", []),
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


ROUNDUP_COMPANIES = 3  # this many different companies on one page means a list or roundup


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], 1)}


def _stale(quote: str, today: date | None = None) -> bool:
    """True when the newest date in the quote is more than six months old."""
    today = today or date.today()
    found = []
    for month, year in re.findall(r"(?:\b([A-Za-z]{3})[a-z]*\.?\s+(?:\d{1,2},?\s+)?)?\b(20\d\d)\b", quote):
        found.append(date(int(year), MONTHS.get(month.lower(), 12), 1))
    return bool(found) and (today - max(found)).days > 183


def _dated(quote: str) -> bool:
    return bool(re.search(r"\b20\d\d\b", quote))


def _quote(value: Any, page: str) -> str:
    """The quote, if it really is on the page; otherwise nothing, so no draft is built on it."""
    quote = (value or "").strip() if isinstance(value, str) else ""
    return quote if quote and _norm(quote)[:40] in page else ""


def extract(ai: AI, config: dict[str, Any], url: str, text: str) -> list[Lead]:
    user = (f"Today is {date.today():%B %d, %Y}. A why_now only counts if the page shows it happened in the last six "
            "months; if the page is older or undated, leave why_now empty.\n"
            f"Ideal customer profile: {_profile_brief(config)}\nPage URL: {url}\nPage text:\n{text}\n\n"
            'Return {"leads": [{"name": "", "title": "", "company": "", "evidence": "", "why_now": "", '
            '"stage": "", "linkedin": "", "website": ""}]}.')
    data = ai.json(EXTRACT_SYSTEM, user, max_tokens=2000)
    page, leads = _norm(text), []
    items = [i for i in (data.get("leads", []) if isinstance(data, dict) else []) if isinstance(i, dict)]
    companies = {_norm(i.get("company") or "") for i in items if _on_page(i.get("company") or "", page)} - {""}
    if len(companies) >= ROUNDUP_COMPANIES:
        return []  # a page about many companies is a roundup, not a signal from any one of them
    for item in items:
        name, company = (item.get("name") or "").strip(), (item.get("company") or "").strip()
        if name and _norm(name) == _norm(company):
            name = ""  # a company put in the name field
        # Keep only what the page really says: the person (or, for a company lead, the company) must appear on it.
        if not (_on_page(name, page) if name else _on_page(company, page)):
            continue
        title = (item.get("title") or "").strip() if name else ""  # a role without a person isn't a lead
        linkedin = (item.get("linkedin") or "").strip()
        evidence = _quote(item.get("evidence"), page)
        why_now = _quote(item.get("why_now"), page)
        if why_now and (_stale(why_now) or (not _dated(why_now) and _stale(text[:4000]))):
            evidence, why_now = evidence or why_now, ""  # old news: still a fit, but not a reason to write now
        if not (evidence or why_now):
            continue  # nothing on the page shows why they fit: quality over quantity
        if not name and not why_now:
            continue  # a company with nobody named is only worth it with a reason to reach out now
        stage = (item.get("stage") or "").strip()
        leads.append(Lead(
            name=name, company=company if _on_page(company, page) else "", title=title if _on_page(title, page) else "",
            linkedin=linkedin if "linkedin.com/" in linkedin and _on_page(linkedin, page) else "",
            website=(item.get("website") or "").strip(), evidence=evidence[:300], why_now=why_now[:300],
            stage=stage if _on_page(stage, page) else "",
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
            # Exa's people index returns profile pages from its own copy; that's allowed when you ask for it.
            from_index = result.content and getattr(search, "category", "") == "people"
            if result.url in seen_urls or (_skip(result.url, skip) and not from_index):
                continue
            seen_urls.add(result.url)
            text = search.read(result)
            if len(text) < 300:
                search.skipped += 1
                continue
            read += 1
            yield from extract(ai, config, result.url, text)


def research(ai: AI, search: Search, lead: Lead, pages: int = 3, config: dict[str, Any] | None = None) -> str:
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
    icp = (config or {}).get("icp", {})
    user = (f"Seller's offer: {(config or {}).get('pitch', '')}\nSeller's why-now signals: {icp.get('why_now', [])}\n"
            f"Lead: {lead.name or '(unknown)'}, {lead.title or '(title unknown)'} at {lead.company or '(company unknown)'}\n\n"
            + "\n\n---\n\n".join(sources))
    return ai.chat(RESEARCH_SYSTEM, user, max_tokens=500).strip()


def write_hook(ai: AI, lead: Lead, config: dict[str, Any]) -> str:
    """One factual opening line, or "" when nothing honest qualifies."""
    if not (lead.why_now or lead.evidence or lead.research):
        return ""
    facts = {"today": f"{date.today():%B %d, %Y}", "lead": {"name": lead.name, "title": lead.title,
             "company": lead.company}, "why_now_quote": lead.why_now, "evidence": lead.evidence,
             "research": lead.research, "seller_pitch": config.get("pitch", "")}
    hook = ai.chat(HOOK_SYSTEM, json.dumps(facts), max_tokens=120).strip().strip('"')
    if not hook or hook.upper().startswith("NONE") or GUESSING.search(hook) or len(hook.split()) > 30:
        return ""  # a hook that guesses or stretches is worse than none
    return hook


def write_draft(ai: AI, lead: Lead, config: dict[str, Any]) -> str:
    """The note: an AI-written factual hook, then the offer and ask exactly as the profile states them."""
    hook = write_hook(ai, lead, config)
    product, pitch = config.get("product", ""), config.get("pitch", "")
    offer = f"I'm building {product}, {pitch}." if pitch else f"I'm building {product}."
    if not hook and lead.title and lead.company:
        hook = f"I'm writing to you as {lead.title} at {lead.company}."
    ask = config.get("ask") or "a quick call"
    parts = [f"Hi {lead.first_name},", " ".join(p for p in (hook, offer) if p), f"Would you be open to {ask}?"]
    if config.get("sender"):
        parts.append(config["sender"])
    return "\n\n".join(parts)


def suggest_why_now(ai: AI, config: dict[str, Any], search: Search | None = None, count: int = 6,
                    progress=print) -> list[dict[str, Any]]:
    """Propose why-now signals for the profile; with a search service, check each one shows up on the web."""
    user = (f"Today is {date.today():%B %d, %Y}.\nProfile: {_profile_brief(config)}\n"
            f'Propose {count} signals. Return {{"signals": [{{"signal": "", "why": "", "search": ""}}]}}. '
            "Write each signal as a short phrase, e.g. \"just raised a seed round\".")
    data = ai.json(WHY_NOW_SYSTEM, user, max_tokens=1200)
    found = []
    for item in (data.get("signals", []) if isinstance(data, dict) else [])[:count]:
        if not isinstance(item, dict) or not (item.get("signal") or "").strip():
            continue
        signal = {"signal": item["signal"].strip(), "why": (item.get("why") or "").strip(),
                  "search": (item.get("search") or "").strip(), "examples": []}
        if search is not None and signal["search"]:
            progress(f"checking: {signal['search']}")
            try:
                hits = search.search(signal["search"], count=5)
            except Exception as err:  # a failed check shouldn't lose the suggestion
                progress(f"  couldn't check it: {err}")
                hits = []
            hits = [r for r in hits if not _skip(r.url, [])]
            if hits:
                listing = "\n".join(f"{i}. {r.title} | {r.url} | {r.snippet[:200]}" for i, r in enumerate(hits))
                verdict = ai.json(WHY_NOW_CHECK, f"Signal: {signal['signal']}\nResults:\n{listing}\n"
                                  'Return {"specific": [numbers]}.', max_tokens=200)
                keep = verdict.get("specific", []) if isinstance(verdict, dict) else []
                signal["examples"] = [{"title": hits[i].title, "url": hits[i].url}
                                      for i in keep if isinstance(i, int) and 0 <= i < len(hits)][:3]
        found.append(signal)
    return found
