"""Stargazers of a GitHub repo, with their public profile.

Uses GitHub's public API, which only lists stargazers to signed-in requests:
set GITHUB_TOKEN. A classic token with no scopes reads any public repo; a
fine-grained token reads only the repos it covers.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from collections.abc import Iterator

from cantrip.lead import Lead

API = "https://api.github.com"


def _get(url: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "cantrip"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _top_languages(login: str, limit: int = 3) -> list[str]:
    repos = _get(f"{API}/users/{login}/repos?per_page=100&sort=pushed")
    counts = Counter(r["language"] for r in repos if r.get("language") and not r.get("fork"))
    return [lang for lang, _ in counts.most_common(limit)]


def stargazers(repo: str, limit: int = 100, enrich: bool = True) -> Iterator[Lead]:
    """Yield up to `limit` stargazers of `owner/name`, newest pages last."""
    page, seen = 1, 0
    while seen < limit:
        batch = _get(f"{API}/repos/{repo}/stargazers?per_page=100&page={page}")
        if not batch:
            return
        for user in batch:
            if seen >= limit:
                return
            seen += 1
            lead = Lead(handle=user["login"], source=f"github-stars:{repo}", signal="starred")
            if enrich:
                profile = _get(f"{API}/users/{user['login']}")
                lead.name = profile.get("name") or ""
                lead.email = profile.get("email") or ""  # only if they made it public
                lead.company = (profile.get("company") or "").lstrip("@").strip()
                lead.location = profile.get("location") or ""
                lead.bio = profile.get("bio") or ""
                lead.website = profile.get("blog") or ""
                lead.followers = profile.get("followers") or 0
                lead.public_repos = profile.get("public_repos") or 0
                lead.top_languages = _top_languages(user["login"])
            yield lead
        page += 1
