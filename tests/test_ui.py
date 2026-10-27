import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from cantrip.ui.server import Handler

ROOT = Path(__file__).resolve().parent.parent
GUESTS = (ROOT / "examples" / "luma-guests.csv").read_text()


@pytest.fixture
def ui(tmp_path):
    Handler.profile_path = tmp_path / "cantrip.toml"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def call(url, body=None, host=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    if host:
        req.add_header("Host", host)
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
