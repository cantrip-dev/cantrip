import base64
import hashlib
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from cantrip.ui import server
from cantrip.ui.server import Handler

ROOT = Path(__file__).resolve().parent.parent
GUESTS = (ROOT / "examples" / "luma-guests.csv").read_text()


@pytest.fixture
def ui(tmp_path):
    Handler.profile_path = tmp_path / "cantrip.toml"
    Handler.password_hash, Handler.allowed_hosts, Handler.demo = None, set(), False
    Handler.demo_profiles.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def call(url, body=None, host=None, origin=None, password=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    if password is not None:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"me:{password}".encode()).decode())
    if host:
        req.add_header("Host", host)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_page_and_state(ui):
    status, page = call(ui + "/")
    assert status == 200 and b"Cast a spell" in page
    state = json.loads(call(ui + "/api/state")[1])
    assert state["profile"] is None
    assert {"attendees-to-leads", "github-to-leads"} <= {s["name"] for s in state["spells"]}
    assert {s["name"]: s["source"] for s in state["spells"]}["contributors-to-leads"] == "contributors"
    assert {s["name"]: s["source"] for s in state["spells"]}["forks-to-leads"] == "forks"


def test_profile_then_run(ui):
    status, body = call(ui + "/api/run", {"spell": "attendees-to-leads", "source": "csv", "value": GUESTS})
    assert status == 400 and b"profile" in body
    status, body = call(ui + "/api/profile", {"name": "Acme", "pitch": "a thing", "buyer_roles": "cto, devrel"})
    assert status == 200 and json.loads(body)["profile"]["icp"]["buyer_roles"] == ["cto", "devrel"]
    status, body = call(ui + "/api/run", {"spell": "attendees-to-leads", "source": "csv", "value": GUESTS,
                                          "event": "AI Day"})
    leads = json.loads(body)["leads"]
    assert status == 200 and len(leads) == 4
    assert leads[0]["score"] >= leads[-1]["score"] and "AI Day" in leads[0]["draft"]


def test_profile_needs_essentials(ui):
    status, body = call(ui + "/api/profile", {"name": "Acme"})
    assert status == 400 and b"who buys it" in body


def test_other_hosts_are_refused(ui):
    assert call(ui + "/api/state", host="evil.example")[0] == 403


def test_other_websites_are_refused(ui):
    body = {"name": "X", "pitch": "y", "buyer_roles": "cto"}
    assert call(ui + "/api/profile", body, origin="https://evil.example")[0] == 403
    assert call(ui + "/api/profile", body, origin=ui)[0] == 200


def test_deployed_copy_asks_for_the_password(ui, monkeypatch):
    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    Handler.password_hash = hashlib.sha256(b"correct horse battery").digest()
    assert call(ui + "/healthz")[0] == 200  # health checks need no password and learn nothing
    assert call(ui + "/api/state")[0] == 401
    assert call(ui + "/api/state", password="wrong password!")[0] == 401
    assert call(ui + "/api/state", host="leads.example.com", password="correct horse battery")[0] == 200
    body = {"name": "X", "pitch": "y", "buyer_roles": "cto"}
    # Signed in or not, another website can't make the browser save or run anything.
    assert call(ui + "/api/profile", body, host="leads.example.com", origin="https://evil.example",
                password="correct horse battery")[0] == 403
    assert call(ui + "/api/profile", body, host="leads.example.com", origin="https://leads.example.com",
                password="correct horse battery")[0] == 200


def test_allowed_hosts_lock_a_deployed_copy_to_its_address(ui):
    Handler.password_hash = hashlib.sha256(b"correct horse battery").digest()
    Handler.allowed_hosts = {"leads.example.com"}
    assert call(ui + "/api/state", host="other.example", password="correct horse battery")[0] == 403
    assert call(ui + "/api/state", host="leads.example.com", password="correct horse battery")[0] == 200


def test_no_password_off_this_computer_refuses_to_start(monkeypatch, tmp_path):
    monkeypatch.delenv("CANTRIP_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="CANTRIP_PASSWORD"):
        server.serve(host="0.0.0.0", profile_path=tmp_path / "p.toml", open_browser=False)
    monkeypatch.setenv("CANTRIP_PASSWORD", "short")
    with pytest.raises(SystemExit, match="at least 12"):
        server.serve(host="0.0.0.0", profile_path=tmp_path / "p.toml", open_browser=False)


def demo_call(url, body=None, cookie=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read()), resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read()), None


def test_demo_gives_each_visitor_a_profile_and_keeps_nothing(ui, tmp_path):
    Handler.demo = True
    status, state, set_cookie = demo_call(ui + "/api/state")
    assert status == 200 and state["demo"] and state["profile"]["product"]["name"] == "Cantrip"
    assert [s["name"] for s in state["spells"]] == ["attendees-to-leads"]
    me = set_cookie.split(";")[0]
    # Casting with no file sorts the sample list; asking for GitHub still runs only the guest-list spell.
    status, out, _ = demo_call(ui + "/api/run", {"spell": "github-to-leads", "source": "search", "value": ""}, me)
    assert status == 200 and len(out["leads"]) == 20
    # My profile is mine: another visitor still sees the example, and nothing is written to disk.
    status, _, _ = demo_call(ui + "/api/profile", {"name": "Mine", "pitch": "p", "buyer_roles": "cto"}, me)
    assert status == 200 and demo_call(ui + "/api/state", None, me)[1]["profile"]["product"]["name"] == "Mine"
    assert demo_call(ui + "/api/state")[1]["profile"]["product"]["name"] != "Mine"
    assert not Handler.profile_path.exists()
    for path in ("/api/why-now", "/api/crm"):
        assert demo_call(ui + path, {}, me)[0] == 403
    assert call(ui + "/api/health")[0] == 200


def test_marking_a_lead_no_keeps_them_out_of_later_runs(ui):
    call(ui + "/api/profile", {"name": "Acme", "pitch": "a thing", "buyer_roles": "cto, devrel"})
    first = json.loads(call(ui + "/api/run", {"spell": "attendees-to-leads", "source": "csv", "value": GUESTS})[1])["leads"]
    status, body = call(ui + "/api/no", {"who": first[0]["email"]})
    assert status == 200 and json.loads(body)["people"] == [first[0]["email"]]
    again = json.loads(call(ui + "/api/run", {"spell": "attendees-to-leads", "source": "csv", "value": GUESTS})[1])["leads"]
    assert first[0]["email"] not in {lead["email"] for lead in again} and len(again) == len(first) - 1
    assert call(ui + "/api/no", {"who": ""})[0] == 400


def test_a_read_only_profile_says_how_to_add_the_no_by_hand(ui):
    call(ui + "/api/profile", {"name": "Acme", "pitch": "a thing", "buyer_roles": "cto"})
    Handler.profile_path.chmod(0o444)
    try:
        status, body = call(ui + "/api/no", {"who": "ada"})
    finally:
        Handler.profile_path.chmod(0o644)
    assert status == 409 and "[skip]" in json.loads(body)["error"] and json.loads(body)["readonly"]
