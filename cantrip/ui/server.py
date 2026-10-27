"""The Cantrip UI: a local web page for your profile and your runs.

It runs on your own computer (127.0.0.1 only), uses only Python's standard
library, and keeps everything in local files: your profile in cantrip.toml,
your results wherever you download them. Keys typed into the page (GitHub,
AI, search) are used for that run only and are never written to disk.
"""

from __future__ import annotations

import json
import os
import threading
import tomllib
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cantrip import __version__, engine, profile, sinks, spell
from cantrip.ai import AI, AIError
from cantrip.web import Search, SearchError
from cantrip.report import summary
from cantrip.sources import csv_file, github
from cantrip.sources import web as web_source

HERE = Path(__file__).resolve().parent
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
SOURCES = ("csv", "search", "users", "contributors", "stars", "web")
MAX_BODY = 50 * 1024 * 1024


def _spells() -> list[dict[str, str]]:
    found = []
    for folder in sorted(spell.SPELLBOOK.iterdir()):
        toml = folder / "spell.toml"
        if toml.exists():
            found.append({"name": folder.name, "about": spell.load(str(folder)).get("about", "")})
    return found


def _ai(req: dict[str, Any]) -> AI:
    env = AI.from_env()
    return AI.make(req.get("ai_provider") or env.provider, (req.get("ai_key") or "").strip() or env.key,
                   (req.get("ai_base_url") or "").strip() or (env.base_url if not req.get("ai_provider") else ""),
                   (req.get("ai_model") or "").strip() or (env.model if not req.get("ai_provider") else ""))


def _search(req: dict[str, Any]) -> Search:
    env = Search.from_env()
    provider = req.get("search_provider") or env.provider
    key = (req.get("search_key") or "").strip() or (env.key if not req.get("search_provider") else "")
    reader = (req.get("reader_key") or "").strip() or env.reader_key or (key if provider == "tinyfish" else "")
    return Search(provider=provider, key=key, url=(req.get("search_url") or "").strip() or env.url,
                  category=(req.get("search_category") or "").strip() or env.category, reader_key=reader)


def _leads_for(req: dict[str, Any], config=None, ai=None, search=None):
    source, value = req.get("source"), (req.get("value") or "").strip()
    limit, enrich = int(req.get("limit") or 50), not req.get("no_enrich")
    if source not in SOURCES:
        raise ValueError("Pick where the people come from.")
    if source == "web":
        return web_source.find(ai, search, config, brief=value, max_queries=int(req.get("queries") or 6),
                               pages_per_query=int(req.get("pages") or 3), progress=lambda _: None)
    if not value:
        raise ValueError("Add a CSV file." if source == "csv" else "Fill in the GitHub search, list or repo.")
    if source == "csv":
        return csv_file.people_from_text(value, source=f"csv:{req.get('filename') or 'upload'}",
                                         signal=req.get("signal") or "registered")
    if source == "search":
        return github.search(value, limit=limit, do_enrich=enrich)
    if source == "users":
        return github.users(value.splitlines(), do_enrich=enrich)
    if source == "contributors":
        return github.contributors(value, limit=limit, do_enrich=enrich)
    return github.stargazers(value, limit=limit, do_enrich=enrich)


class Handler(BaseHTTPRequestHandler):
    profile_path: Path = profile.DEFAULT_PATH
    run_lock = threading.Lock()
    last_results: list = []  # the latest run's leads, for "Add to CRM"

    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal quiet
        pass

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: Any, status: int = 200) -> None:
        self._send(status, json.dumps(data).encode(), "application/json")

    def _trusted(self) -> bool:
        # Only answer pages served from this computer (guards against DNS rebinding).
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ALLOWED_HOSTS

    def do_GET(self) -> None:
        if not self._trusted():
            return self._send(403, b"Forbidden", "text/plain")
        if self.path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/logo.png":
            return self._send(200, (HERE / "logo.png").read_bytes(), "image/png")
        if self.path == "/api/state":
            mine = None
            if self.profile_path.exists():
                with self.profile_path.open("rb") as fh:
                    mine = tomllib.load(fh)
            return self._json({"version": __version__, "profile": mine, "profile_path": str(self.profile_path),
                               "spells": _spells(), "questions": [[k, q, h] for k, q, h in profile.QUESTIONS],
                               "has_token": bool(os.environ.get("GITHUB_TOKEN")),
                               "has_ai": AI.from_env().ready, "has_search": Search.from_env().ready,
                               "crms": {name: {"label": label, "set": all(os.environ.get(v) for v in needs[:1])}
                                        for name, (label, needs) in sinks.CRMS.items()}})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self) -> None:
        if not self._trusted() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(403, b"Forbidden", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json({"error": "That file is too big (50 MB at most)."}, 413)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "Bad request."}, 400)
        if self.path == "/api/profile":
            return self._save_profile(req)
        if self.path == "/api/run":
            return self._run(req)
        if self.path == "/api/why-now":
            return self._why_now(req)
        if self.path == "/api/crm":
            return self._crm(req)
        self._send(404, b"Not found", "text/plain")

    def _save_profile(self, req: dict[str, Any]) -> None:
        answers = {k: v for k, v in req.items() if isinstance(v, str) and v.strip()}
        try:
            profile.update(answers, self.profile_path)
        except ValueError as err:
            return self._json({"error": str(err).replace("buyer_roles", "who buys it")}, 400)
        with self.profile_path.open("rb") as fh:
            self._json({"ok": True, "profile": tomllib.load(fh)})

    def _run(self, req: dict[str, Any]) -> None:
        try:
            mine = profile.load(self.profile_path)
        except profile.ProfileMissing:
            return self._json({"error": "Set up your profile first: what you sell and who buys it."}, 400)
        if req.get("spell") not in {s["name"] for s in _spells()}:
            return self._json({"error": "Pick a spell."}, 400)
        config = profile.apply(spell.load(req["spell"]), mine)
        if req.get("event"):
            config["event_name"] = req["event"]
        token = (req.get("token") or "").strip()
        uses_web = req.get("source") == "web" or bool(req.get("research"))
        ai_drafts = bool(req.get("ai_drafts", config.get("ai_drafts", False)))
        ai = search = None
        try:
            if uses_web or ai_drafts:
                ai = _ai(req)
                if not ai.ready:
                    return self._json({"error": "Add an AI key under AI settings (or point it at a local model)."}, 400)
            if uses_web:
                search = _search(req)
                if not search.ready:
                    return self._json({"error": "Add a search service key under AI settings."}, 400)
        except AIError as err:
            return self._json({"error": str(err)}, 400)
        with self.run_lock:  # one run at a time, so a typed token never leaks into another run
            saved = os.environ.get("GITHUB_TOKEN")
            if token:
                os.environ["GITHUB_TOKEN"] = token
            try:
                leads = _leads_for(req, config, ai, search)
                results = engine.run(config, leads, add_github=bool(req.get("add_github")),
                                     min_tier=req.get("min_tier") or "cold")
                if ai is not None and (req.get("research") or ai_drafts):
                    engine.enhance(results, config, ai, search, research=bool(req.get("research")),
                                   ai_drafts=ai_drafts, top=int(req.get("top") or 15), progress=lambda _: None)
            except (AIError, SearchError) as err:
                return self._json({"error": str(err)}, 502)
            except ValueError as err:
                return self._json({"error": str(err)}, 400)
            except urllib.error.HTTPError as err:
                msg = ("GitHub refused the request. Add a GitHub token: stargazers always need one, and a "
                       "fine-grained token only reads the repos it covers." if err.code in (401, 403)
                       else f"GitHub answered {err.code}. Try again in a minute.")
                return self._json({"error": msg}, 502)
            except urllib.error.URLError:
                return self._json({"error": "Couldn't reach GitHub. Check your internet connection."}, 502)
            finally:
                if token:
                    if saved is None:
                        os.environ.pop("GITHUB_TOKEN", None)
                    else:
                        os.environ["GITHUB_TOKEN"] = saved
        usage = (f"{ai.calls} AI calls" + (f", {search.searches} searches" if search else "")
                 + (f" ({search.skipped} pages couldn't be read)" if search and search.skipped else "")) if ai else ""
        if search is not None and search.warning():
            usage = (usage + ". " if usage else "") + "Warning: " + search.warning()
        Handler.last_results = results
        self._json({"leads": [lead.to_row() for lead in results], "summary": summary(results), "usage": usage})

    def _why_now(self, req: dict[str, Any]) -> None:
        try:
            config = profile.apply(spell.load("web-to-leads"), profile.load(self.profile_path))
        except profile.ProfileMissing:
            return self._json({"error": "Set up your profile first."}, 400)
        try:
            ai = _ai(req)
            if not ai.ready:
                return self._json({"error": "Add an AI key under AI and search settings (in step 2)."}, 400)
            search = _search(req)
            found = web_source.suggest_why_now(ai, config, search if search.ready else None, progress=lambda _: None)
        except (AIError, SearchError) as err:
            return self._json({"error": str(err)}, 502)
        self._json({"signals": found, "checked": search.ready})

    def _crm(self, req: dict[str, Any]) -> None:
        if not self.last_results:
            return self._json({"error": "Cast a spell first, then add its leads."}, 400)
        settings = {k: str(v).strip() for k, v in (req.get("settings") or {}).items() if k.startswith("CANTRIP_")}
        with self.run_lock:
            try:
                crm = sinks.connect(req.get("crm") or "", settings)
                counts = sinks.push(crm, self.last_results, min_tier=req.get("min_tier") or "warm",
                                    progress=lambda _: None)
            except sinks.CRMError as err:
                return self._json({"error": str(err)}, 502)
        self._json({"counts": counts, "label": crm.label, "leads": [lead.to_row() for lead in self.last_results]})


def serve(port: int = 8765, profile_path: str | Path | None = None, open_browser: bool = True) -> None:
    Handler.profile_path = Path(profile_path) if profile_path else profile.DEFAULT_PATH
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:  # port taken: let the system pick a free one
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Cantrip is running at {url}  (profile: {Handler.profile_path.resolve()})", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
