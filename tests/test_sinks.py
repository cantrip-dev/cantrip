"""CRM connectors, with the network replaced by a recorder."""

import json

import pytest

from cantrip import sinks
from cantrip.lead import Lead
from cantrip.sinks import espocrm, hubspot, notion, twenty
from cantrip.sinks.http import CRMError


class Recorder:
    """Stands in for sinks.http.call: records each request and answers from `routes`."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers, body=None, retries=3):
        self.calls.append((method, url, body))
        for (m, part), answer in self.routes.items():
            if m == method and part in url:
                return answer(body) if callable(answer) else answer
        return {}


def leads():
    return [
        Lead(name="Ada Lovelace", email="ada@acme.dev", company="Acme", title="VP Engineering", score=70, tier="hot",
             reasons=["VP", "target company"], draft="Hi Ada", source_url="https://acme.dev/team", evidence="Ada leads"),
        Lead(name="Bob Ng", company="Beta", title="Engineer", score=40, tier="warm"),
        Lead(name="Cy Cold", company="Gamma", score=5, tier="cold"),
        Lead(name="", company="Delta", score=60, tier="hot"),
    ]


def test_notion_adds_missing_columns_and_skips_existing(monkeypatch):
    rec = Recorder({
        ("GET", "/databases/"): {"properties": {"Lead": {"type": "title"}, "Email": {"type": "email"},
                                                "Status": {"type": "status"}}},
        ("POST", "/query"): lambda body: {"results": [{}] if "email" in json.dumps(body) else []},
    })
    monkeypatch.setattr(notion, "call", rec)
    monkeypatch.setattr(notion.time, "sleep", lambda _: None)
    crm = sinks.connect("notion", {"CANTRIP_NOTION_TOKEN": "t",
                                   "CANTRIP_NOTION_DATABASE": "https://www.notion.so/me/Leads-0123456789abcdef0123456789abcdef?v=1"})
    assert crm.db == "0123456789abcdef0123456789abcdef"
    rows = leads()
    counts = sinks.push(crm, rows, min_tier="warm", progress=lambda _: None)
    assert counts == {"added": 1, "already there": 1, "skipped": 1, "failed": 0}
    patch = next(body for m, url, body in rec.calls if m == "PATCH")
    assert "Email" not in patch["properties"] and "Tier" in patch["properties"] and "Status" not in patch["properties"]
    page = next(body for m, url, body in rec.calls if m == "POST" and url.endswith("/pages"))
    assert page["properties"]["Lead"]["title"][0]["text"]["content"] == "Bob Ng"  # uses the database's own title column
    assert "Status" not in page["properties"]  # their own status column is theirs to fill
    assert page["properties"]["Tier"]["select"]["name"] == "warm"
    assert rows[0].crm == "already in Notion" and rows[2].crm == ""


def test_hubspot_creates_contact_with_note(monkeypatch):
    rec = Recorder({("POST", "/contacts/search"): {"total": 0}, ("POST", "/contacts"): {"id": "42"}})
    monkeypatch.setattr(hubspot, "call", rec)
    counts = sinks.push(sinks.connect("hubspot", {"CANTRIP_HUBSPOT_TOKEN": "t"}), leads()[:1], progress=lambda _: None)
    assert counts["added"] == 1
    contact = next(b for m, u, b in rec.calls if u.endswith("/contacts") and m == "POST")
    assert contact["properties"]["firstname"] == "Ada" and contact["properties"]["email"] == "ada@acme.dev"
    note = next(b for m, u, b in rec.calls if u.endswith("/notes"))
    assert note["associations"][0]["to"]["id"] == "42" and "not sent" in note["properties"]["hs_note_body"]


def test_twenty_links_company_once(monkeypatch):
    rec = Recorder({("GET", "/people"): {"data": {"people": []}},
                    ("GET", "/companies"): {"data": {"companies": []}},
                    ("POST", "/companies"): {"data": {"createCompany": {"id": "c1"}}},
                    ("POST", "/people"): {"data": {"createPerson": {"id": "p1"}}},
                    ("POST", "/notes"): {"data": {"createNote": {"id": "n1"}}}})
    monkeypatch.setattr(twenty, "call", rec)
    two = [Lead(name="A One", company="Acme", tier="hot"), Lead(name="B Two", company="Acme", tier="hot")]
    counts = sinks.push(sinks.connect("twenty", {"CANTRIP_TWENTY_KEY": "k"}), two, progress=lambda _: None)
    assert counts["added"] == 2
    assert sum(1 for m, u, _ in rec.calls if m == "POST" and u.endswith("/companies")) == 1
    person = next(b for m, u, b in rec.calls if m == "POST" and u.endswith("/people"))
    assert person["companyId"] == "c1" and person["name"] == {"firstName": "A", "lastName": "One"}
    assert any(u.endswith("/noteTargets") for _, u, _ in rec.calls)


def test_espocrm_lead_and_dedupe(monkeypatch):
    rec = Recorder({("GET", "emailAddress"): {"total": 1}, ("GET", "/Lead?"): {"total": 0}})
    monkeypatch.setattr(espocrm, "call", rec)
    crm = sinks.connect("espocrm", {"CANTRIP_ESPO_KEY": "k", "CANTRIP_ESPO_URL": "https://crm.example.com/"})
    counts = sinks.push(crm, leads()[:2], progress=lambda _: None)
    assert counts["added"] == 1 and counts["already there"] == 1
    lead = next(b for m, u, b in rec.calls if m == "POST")
    assert lead["lastName"] == "Ng" and lead["status"] == "New" and rec.calls[-1][1].startswith("https://crm.example.com/api/v1/")


def test_missing_settings_and_broken_connection(monkeypatch):
    for name in sinks.CRMS:
        for var in sinks.CRMS[name][1]:
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(CRMError):
            sinks.connect(name)

    def broken(*a, **k):
        raise CRMError("answered 401")
    monkeypatch.setattr(hubspot, "call", broken)
    with pytest.raises(CRMError):
        sinks.push(sinks.connect("hubspot", {"CANTRIP_HUBSPOT_TOKEN": "t"}), leads(), progress=lambda _: None)
