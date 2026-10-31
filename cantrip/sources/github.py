"""Find people by their GitHub profile.

Four ways in, all through GitHub's public API:
- `search`: GitHub's user search ("language:python location:seattle agents")
- `users`: a list of logins or profile URLs you already have
- `contributors`: people who committed to a repo, leaving out bots, AI coding agents and the repo owner's own team
- `stargazers`: people who starred a repo (GitHub requires GITHUB_TOKEN for this)

Each person is filled in from their public profile. Set GITHUB_TOKEN for
5,000 requests an hour; without it GitHub allows 60, enough for a quick try.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterable, Iterator

from cantrip.lead import Lead

API = "https://api.github.com"


def _get(url: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "cantrip"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def login_from(value: str) -> str:
    """'https://github.com/octocat', '@octocat' or 'octocat' -> 'octocat'."""
    value = value.strip().rstrip("/")
    match = re.search(r"github\.com/([A-Za-z0-9-]+)", value)
    return match.group(1) if match else value.lstrip("@")


def _top_languages(login: str, limit: int = 3) -> list[str]:
    repos = _get(f"{API}/users/{login}/repos?per_page=100&sort=pushed")
    counts = Counter(r["language"] for r in repos if r.get("language") and not r.get("fork"))
    return [lang for lang, _ in counts.most_common(limit)]


def enrich(lead: Lead) -> Lead:
    """Fill in a lead from the public GitHub profile of `lead.github`.
    Fields the lead already has (say, from an attendee list) are kept."""
    profile = _get(f"{API}/users/{lead.github}")
    lead.name = lead.name or profile.get("name") or ""
    lead.email = lead.email or profile.get("email") or ""  # only if they made it public
    lead.company = lead.company or (profile.get("company") or "").lstrip("@").strip()
    lead.location = lead.location or profile.get("location") or ""
    lead.bio = lead.bio or profile.get("bio") or ""
    lead.website = lead.website or profile.get("blog") or ""
    lead.followers = profile.get("followers") or 0
    lead.public_repos = profile.get("public_repos") or 0
    lead.top_languages = _top_languages(lead.github)
    return lead


def _paged(url: str, limit: int, key: str | None = None) -> Iterator[dict]:
    page, seen = 1, 0
    sep = "&" if "?" in url else "?"
    while seen < limit:
        data = _get(f"{url}{sep}per_page=100&page={page}")
        batch = data.get(key, []) if key else data
        if not batch:
            return
        for item in batch:
            if seen >= limit:
                return
            seen += 1
            yield item
        page += 1


def _people(logins: Iterable[str], source: str, signal: str, do_enrich: bool) -> Iterator[Lead]:
    for login in logins:
        lead = Lead(github=login, source=source, signal=signal)
        yield enrich(lead) if do_enrich else lead


def search(query: str, limit: int = 50, do_enrich: bool = True) -> Iterator[Lead]:
    users = _paged(f"{API}/search/users?q={urllib.parse.quote(query)}", min(limit, 1000), key="items")
    yield from _people((u["login"] for u in users if u.get("type") == "User"), f"github-search:{query}", "found", do_enrich)


def users(values: Iterable[str], do_enrich: bool = True) -> Iterator[Lead]:
    logins = [login_from(v) for v in values if v.strip() and not v.strip().startswith("#")]
    yield from _people(logins, "github-list", "found", do_enrich)


# AI coding agents that GitHub lists as users rather than bots, so their commits look like a person's.
AI_AGENTS = {"claude", "codex", "copilot-swe-agent", "cursoragent", "openhands-agent"}

_COMPANY_SUFFIXES = ("inc", "ltd", "llc", "gmbh", "corp", "hq", "oss", "labs", "ai", "io", "dev", "app", "team")


def _company_keys(text: str) -> set[str]:
    """Ways a company's name is written, boiled down: "@renderinc", "render.com", "Render OSS" -> {"render", ...}."""
    text = re.sub(r"^https?://(www\.)?", "", (text or "").strip().lower()).lstrip("@").split("/")[0]
    key = re.sub(r"[^a-z0-9]", "", re.sub(r"\.(com|io|ai|dev|co|org|net|app|sh)$", "", text))
    keys = {key} | {key[: -len(s)] for s in _COMPANY_SUFFIXES if key.endswith(s)}
    return {k for k in keys if len(k) >= 3}


def _owner_company(repo: str) -> set[str]:
    """The company behind a repo owned by an organization; nothing for a personal repo."""
    owner = _get(f"{API}/users/{repo.split('/')[0]}")
    if owner.get("type") != "Organization":
        return set()
    return set().union(*(_company_keys(owner.get(k) or "") for k in ("login", "name", "blog")))


def contributors(repo: str, limit: int = 100, do_enrich: bool = True) -> Iterator[Lead]:
    """Most commits first, as GitHub lists them, each with their commit count. Skipped, and not counted toward
    `limit`: bots, AI coding agents, and (once their profile is read) people who work at the company that owns
    the repo, who are its team rather than leads."""
    team = _owner_company(repo) if do_enrich else set()
    people = (p for p in _paged(f"{API}/repos/{repo}/contributors", 10_000)
              if p.get("type") == "User" and p["login"].lower() not in AI_AGENTS)
    found = 0
    for person in people:
        if found >= limit:
            return
        lead = Lead(github=person["login"], source=f"github-contributors:{repo}", signal="contributed",
                    contributions=person.get("contributions") or 0)
        if do_enrich:
            enrich(lead)
            if team & _company_keys(lead.company):
                continue
        found += 1
        yield lead


def stargazers(repo: str, limit: int = 100, do_enrich: bool = True) -> Iterator[Lead]:
    people = _paged(f"{API}/repos/{repo}/stargazers", limit)
    yield from _people((u["login"] for u in people), f"github-stars:{repo}", "starred", do_enrich)
