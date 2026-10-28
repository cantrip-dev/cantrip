"""The Cantrip UI: a web page for your profile and your runs.

By default it runs on your own computer (127.0.0.1) with nothing to sign in to. It can also be
deployed on a server (see the README's "Deploy it"): then it asks for the password set in
CANTRIP_PASSWORD before it shows anything, and won't start without one. CANTRIP_DEMO=1 runs a
public demo instead: no password and no keys, each visitor gets their own profile for the visit,
and only the guest-list spell runs, on a sample list or the visitor's own file, which is never stored. It uses only Python's
standard library and keeps everything in local files: your profile in cantrip.toml, your results
wherever you download them. Keys typed into the page (GitHub, AI, search) are used for that run
only and are never written to disk.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import tomllib
from collections import OrderedDict
import urllib.error
import urllib.parse
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
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MIN_PASSWORD = 12
EXAMPLES = HERE.parent.parent / "examples"
DEMO_SPELL = "attendees-to-leads"
DEMO_MAX_BODY = 2 * 1024 * 1024
DEMO_MAX_ROWS = 1000
DEMO_SESSIONS = 5000
DEMO_ONLY = ("That's not in the demo. Run your own copy for GitHub and web spells, AI drafts and CRMs: "
             "https://github.com/cantrip-dev/cantrip")
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


def _hostname(value: str) -> str:
    """'Example.com:8765' or 'https://example.com' -> 'example.com'."""
    value = (value or "").strip()
    if "://" not in value:
        value = "//" + value
    try:
        return (urllib.parse.urlsplit(value).hostname or "").lower()
    except ValueError:
        return ""


def _allowed_hosts() -> set[str]:
    return {_hostname(h) for h in os.environ.get("CANTRIP_ALLOWED_HOSTS", "").split(",") if h.strip()}


class Handler(BaseHTTPRequestHandler):
    profile_path: Path = profile.DEFAULT_PATH
    password_hash: bytes | None = None  # set when CANTRIP_PASSWORD is: then every page asks for it
    allowed_hosts: set[str] = set()     # extra hostnames this copy answers to (CANTRIP_ALLOWED_HOSTS)
    demo = False                        # CANTRIP_DEMO: a public demo, see the module docstring
    demo_profiles: OrderedDict = OrderedDict()  # visitor's cookie -> their profile, oldest dropped first
    cookie: str | None = None           # set on a reply that starts a demo visit
    demo_lock = threading.Lock()
    run_lock = threading.Lock()
    last_results: list = []  # the latest run's leads, for "Add to CRM"

    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal quiet
        pass

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self.cookie:
            self.send_header("Set-Cookie", f"cantrip_demo={self.cookie}; HttpOnly; SameSite=Lax; Max-Age=86400")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: Any, status: int = 200) -> None:
        self._send(status, json.dumps(data).encode(), "application/json")

    def _trusted(self) -> bool:
        host = _hostname(self.headers.get("Host") or "")
        if self.demo:
            pass  # a demo holds no keys or files worth guarding by address; the Origin check below still runs
        elif self.password_hash is None:
            # No password: answer only pages served from this computer (guards against DNS rebinding).
            if host not in LOCAL_HOSTS and host not in self.allowed_hosts:
                return False
        elif self.allowed_hosts and host not in self.allowed_hosts and host not in LOCAL_HOSTS:
            return False
        # Refuse requests another website makes from the user's browser: the Origin must be this site.
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        same_site = {host, _hostname(self.headers.get("X-Forwarded-Host") or "")} | self.allowed_hosts
        return _hostname(origin) in same_site - {""}

    def _signed_in(self) -> bool:
        if self.password_hash is None:
            return True
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Basic "):
            try:
                given = base64.b64decode(auth[6:], validate=True).decode().partition(":")[2]
            except (ValueError, UnicodeDecodeError):
                given = ""
            if hmac.compare_digest(hashlib.sha256(given.encode()).digest(), self.password_hash):
                return True
            time.sleep(1)  # slows down password guessing
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Cantrip", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain")
        body = b"Sign in with the password set in CANTRIP_PASSWORD (any user name)."
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def do_GET(self) -> None:
        if self.path in ("/healthz", "/api/health"):  # for hosting platforms' health checks: says nothing else
            return self._send(200, b"ok", "text/plain")
        if not self._trusted():
            return self._send(403, b"Forbidden", "text/plain")
        if not self._signed_in():
            return
        if self.path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/logo.png":
            return self._send(200, (HERE / "logo.png").read_bytes(), "image/png")
        if self.path == "/api/state":
            if self.demo:
                return self._json(self._demo_state())
            mine = None
            if self.profile_path.exists():
                with self.profile_path.open("rb") as fh:
                    mine = tomllib.load(fh)
            return self._json({"version": __version__, "profile": mine, "profile_path": self.profile_path.name,
                               "spells": _spells(), "questions": [[k, q, h] for k, q, h in profile.QUESTIONS],
                               "has_token": bool(os.environ.get("GITHUB_TOKEN")),
                               "has_ai": AI.from_env().ready, "has_search": Search.from_env().ready,
                               "crms": {name: {"label": label, "set": all(os.environ.get(v) for v in needs[:1])}
                                        for name, (label, needs) in sinks.CRMS.items()}})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self) -> None:
        if not self._trusted() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(403, b"Forbidden", "text/plain")
        if not self._signed_in():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > (DEMO_MAX_BODY if self.demo else MAX_BODY):
            return self._json({"error": "That file is too big (2 MB in the demo)." if self.demo
                               else "That file is too big (50 MB at most)."}, 413)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "Bad request."}, 400)
        if self.demo and self.path in ("/api/why-now", "/api/crm"):
            return self._json({"error": DEMO_ONLY}, 403)
        if self.path == "/api/profile":
            return self._save_profile(req)
        if self.path == "/api/run":
            return self._run(self._demo_request(req) if self.demo else req)
        if self.path == "/api/why-now":
            return self._why_now(req)
        if self.path == "/api/crm":
            return self._crm(req)
        self._send(404, b"Not found", "text/plain")

    # ---- the public demo ----
    def _visitor(self) -> str:
        """The visitor's demo id, from their cookie; a new visitor gets one, starting from the example profile."""
        cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
        visit = cookies.get("cantrip_demo", "")
        with self.demo_lock:
            if visit in self.demo_profiles:
                self.demo_profiles.move_to_end(visit)
                return visit
            visit = secrets.token_urlsafe(18)
            self.cookie = visit
            example = EXAMPLES / "profiles" / "event-sponsorships.toml"
            self.demo_profiles[visit] = profile.load(example) if example.exists() else None
            while len(self.demo_profiles) > DEMO_SESSIONS:
                self.demo_profiles.popitem(last=False)
            return visit

    def _demo_state(self) -> dict[str, Any]:
        return {"version": __version__, "demo": True, "profile": self.demo_profiles[self._visitor()],
                "profile_path": "a demo profile, kept for this visit only",
                "spells": [s for s in _spells() if s["name"] == DEMO_SPELL],
                "questions": [[k, q, h] for k, q, h in profile.QUESTIONS],
                "has_token": False, "has_ai": False, "has_search": False, "crms": {}}

    def _demo_request(self, req: dict[str, Any]) -> dict[str, Any]:
        """Only the guest-list spell, on the visitor's file or the sample list; no keys, AI or GitHub."""
        value = req.get("value") or ""
        if not value.strip():
            sample = EXAMPLES / "demo-guests.csv"
            value = sample.read_text() if sample.exists() else ""
            req["filename"] = "sample"
        elif value.count("\n") > DEMO_MAX_ROWS:
            value = "\n".join(value.splitlines()[:DEMO_MAX_ROWS + 1])
        keep = ("event", "signal", "min_tier", "filename")
        return {"spell": DEMO_SPELL, "source": "csv", "value": value, **{k: req[k] for k in keep if req.get(k)}}

    def _save_profile(self, req: dict[str, Any]) -> None:
        answers = {k: v for k, v in req.items() if isinstance(v, str) and v.strip()}
        if self.demo:
            visit = self._visitor()
            with tempfile.TemporaryDirectory() as tmp:  # checked and tidied the same way, then kept in memory
                try:
                    mine = profile.load(profile.init(answers, Path(tmp) / "p.toml", interactive=False))
                except ValueError as err:
                    return self._json({"error": str(err).replace("buyer_roles", "who buys it")}, 400)
            self.demo_profiles[visit] = mine
            return self._json({"ok": True, "profile": mine})
        try:
            profile.update(answers, self.profile_path)
        except ValueError as err:
            return self._json({"error": str(err).replace("buyer_roles", "who buys it")}, 400)
        with self.profile_path.open("rb") as fh:
            self._json({"ok": True, "profile": tomllib.load(fh)})

    def _run(self, req: dict[str, Any]) -> None:
        try:
            mine = self.demo_profiles[self._visitor()] if self.demo else profile.load(self.profile_path)
            if mine is None:
                raise profile.ProfileMissing
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
        if not self.demo:
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


def serve(port: int | None = None, profile_path: str | Path | None = None, open_browser: bool = True,
          host: str | None = None) -> None:
    """Run the app. Defaults come from the environment, so a deployed copy needs no flags:
    CANTRIP_HOST (127.0.0.1), PORT or CANTRIP_PORT (8765), CANTRIP_PROFILE (./cantrip.toml),
    CANTRIP_PASSWORD and CANTRIP_ALLOWED_HOSTS."""
    host = host or os.environ.get("CANTRIP_HOST") or "127.0.0.1"
    port = port or int(os.environ.get("PORT") or os.environ.get("CANTRIP_PORT") or 8765)
    profile_path = profile_path or os.environ.get("CANTRIP_PROFILE")
    Handler.profile_path = Path(profile_path) if profile_path else profile.DEFAULT_PATH
    Handler.profile_path.parent.mkdir(parents=True, exist_ok=True)
    Handler.allowed_hosts = _allowed_hosts()
    Handler.demo = os.environ.get("CANTRIP_DEMO", "").lower() in ("1", "true", "yes")
    password = os.environ.get("CANTRIP_PASSWORD", "")
    local = host in LOCAL_HOSTS and not (Handler.allowed_hosts - set(LOCAL_HOSTS))
    if Handler.demo:
        print("Demo mode: no password and no keys; only the guest-list spell runs.", flush=True)
    elif not local and len(password) < MIN_PASSWORD:
        sys.exit(f"Cantrip won't run on {host} without a password: anyone who reaches it could use your keys. "
                 f"Set CANTRIP_PASSWORD to at least {MIN_PASSWORD} characters (in the server's settings or .env).")
    Handler.password_hash = hashlib.sha256(password.encode()).digest() if password else None
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError:
        if not local:
            raise
        server = ThreadingHTTPServer((host, 0), Handler)  # port taken on this computer: pick a free one
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{server.server_address[1]}/"
    where = f"on port {server.server_address[1]}, all addresses" if host == "0.0.0.0" else f"at {url}"
    print(f"Cantrip is running {where}  (profile: {Handler.profile_path.resolve()})", flush=True)
    if Handler.password_hash:
        print("Sign-in: the password in CANTRIP_PASSWORD (any user name). Serve it over https.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser and local:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
