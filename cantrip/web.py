"""Web search and page reading, with a choice of search service.

    CANTRIP_SEARCH         tavily | brave | serpapi | searxng   (default: tavily)
    CANTRIP_SEARCH_KEY     the service's API key (SearXNG needs none)
    CANTRIP_SEARCH_URL     your SearXNG address, e.g. http://localhost:8888

SearXNG is free and self-hosted; the others have free tiers. Keys are read
from the environment only and never written to disk.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

PROVIDERS = ("tavily", "brave", "serpapi", "searxng")
UA = "Mozilla/5.0 (compatible; Cantrip/0.1; +https://github.com/cantrip-dev/cantrip)"


class SearchError(Exception):
    pass


@dataclass
class Result:
    url: str
    title: str = ""
    snippet: str = ""
    content: str = ""  # page text, when the service returns it


def _request(url: str, data: dict | None = None, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"User-Agent": UA, **({"Content-Type": "application/json"} if data else {}),
                                          **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(3_000_000)


@dataclass
class Search:
    provider: str = "tavily"
    key: str = ""
    url: str = ""
    searches: int = 0
    pages: int = 0
    skipped: int = 0  # pages that couldn't be read (blocked, empty or script-only)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Search":
        return cls(provider=(os.environ.get("CANTRIP_SEARCH") or "tavily").lower(),
                   key=os.environ.get("CANTRIP_SEARCH_KEY", ""), url=os.environ.get("CANTRIP_SEARCH_URL", ""))

    @property
    def ready(self) -> bool:
        return self.provider in PROVIDERS and bool(self.url if self.provider == "searxng" else self.key)

    def search(self, query: str, count: int = 5) -> list[Result]:
        self.searches += 1
        try:
            return getattr(self, f"_{self.provider}")(query, count)[:count]
        except urllib.error.HTTPError as err:
            raise SearchError(f"{self.provider} answered {err.code} for '{query}'"
                              + (": check your search key" if err.code in (401, 403) else "")) from err
        except urllib.error.URLError as err:
            raise SearchError(f"Couldn't reach {self.provider}: {err.reason}") from err

    def _tavily(self, query: str, count: int) -> list[Result]:
        data = json.loads(_request("https://api.tavily.com/search", {
            "query": query, "max_results": count, "include_raw_content": True}, {"Authorization": f"Bearer {self.key}"}))
        return [Result(r["url"], r.get("title", ""), r.get("content", ""), r.get("raw_content") or "")
                for r in data.get("results", [])]

    def _brave(self, query: str, count: int) -> list[Result]:
        q = urllib.parse.urlencode({"q": query, "count": count})
        data = json.loads(_request(f"https://api.search.brave.com/res/v1/web/search?{q}",
                                   headers={"X-Subscription-Token": self.key, "Accept": "application/json"}))
        return [Result(r["url"], r.get("title", ""), r.get("description", ""))
                for r in data.get("web", {}).get("results", [])]

    def _serpapi(self, query: str, count: int) -> list[Result]:
        base = self.url or "https://serpapi.com"
        q = urllib.parse.urlencode({"engine": "google", "q": query, "num": count, "api_key": self.key})
        data = json.loads(_request(f"{base.rstrip('/')}/search.json?{q}"))
        return [Result(r["link"], r.get("title", ""), r.get("snippet", "")) for r in data.get("organic_results", [])]

    def _searxng(self, query: str, count: int) -> list[Result]:
        q = urllib.parse.urlencode({"q": query, "format": "json"})
        data = json.loads(_request(f"{self.url.rstrip('/')}/search?{q}"))
        return [Result(r["url"], r.get("title", ""), r.get("content", "")) for r in data.get("results", [])]

    def read(self, result: Result, max_chars: int = 12000) -> str:
        """The page's text: what the service returned, or the page itself."""
        if len(result.content) > 500:
            return result.content[:max_chars]
        self.pages += 1
        try:
            raw = _request(result.url, timeout=20).decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ValueError) as err:
            self.errors.append(f"couldn't read {result.url}: {err}")
            return (result.title + "\n" + result.snippet)[:max_chars]
        return page_text(raw)[:max_chars]


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def page_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.parts)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", text)).strip()
