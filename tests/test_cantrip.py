from pathlib import Path

import pytest

from cantrip import profile, spell
from cantrip.cli import main
from cantrip.draft import draft
from cantrip.lead import Lead
from cantrip.score import score
from cantrip.sources import csv_file, github

ROOT = Path(__file__).resolve().parent.parent
GUESTS = ROOT / "examples" / "luma-guests.csv"
PROFILES = ROOT / "examples" / "profiles"
SPONSORS = profile.apply(spell.load("attendees-to-leads"), profile.load(PROFILES / "event-sponsorships.toml"))
DEVTOOL = profile.apply(spell.load("github-to-leads"), profile.load(PROFILES / "devtool-startup.toml"))


@pytest.mark.parametrize("name", ["devtool-startup", "event-sponsorships", "b2b-saas"])
@pytest.mark.parametrize("spell_name", ["attendees-to-leads", "github-to-leads"])
def test_every_example_profile_works_with_every_spell(name, spell_name):
    config = profile.apply(spell.load(spell_name), profile.load(PROFILES / f"{name}.toml"))
    leads = [draft(score(lead, config["icp"]), config) for lead in csv_file.people(GUESTS)]
    assert all(lead.draft and "{" not in lead.draft for lead in leads)


def test_profile_sets_product_roles_and_seniority():
    assert SPONSORS["product"].startswith("sponsorship")
    assert SPONSORS["icp"]["functions"][0]["points"] == profile.BUYER_POINTS
    assert SPONSORS["icp"]["seniority"][0]["points"] == 45  # "high" scales 30 by 1.5
    ignored = profile.apply(spell.load("attendees-to-leads"), {"icp": {"seniority": "ignore"}})
    assert ignored["icp"]["seniority"] == []


def test_same_people_rank_differently_for_different_products():
    people = list(csv_file.people(GUESTS))[:4]
    devtool = profile.apply(spell.load("attendees-to-leads"), profile.load(PROFILES / "devtool-startup.toml"))
    by_sponsor = max(people, key=lambda lead: score(Lead(**vars(lead)), SPONSORS["icp"]).score)
    by_devtool = max(people, key=lambda lead: score(Lead(**vars(lead)), devtool["icp"]).score)
    assert by_sponsor.name == "Ada Example"  # DevRel buys sponsorships
    assert by_devtool.name == "Grace Sample"  # the CTO buys infrastructure


def test_init_writes_a_profile_that_loads(tmp_path):
    path = profile.init({"name": "Pipewise", "pitch": "deal forecasting", "buyer_roles": "revops, cro",
                         "exclude": "pipewise.io"}, tmp_path / "cantrip.toml", interactive=False)
    loaded = profile.load(path)
    assert loaded["product"]["name"] == "Pipewise"
    assert loaded["icp"]["buyer_roles"] == ["revops", "cro"]


def test_init_asks_for_what_is_missing(tmp_path):
    replies = iter(["Pipewise", "deal forecasting", "revops", "", "high"] + [""] * 10)
    path = profile.init({}, tmp_path / "p.toml", ask=lambda _: next(replies), interactive=True)
    assert profile.load(path)["icp"]["seniority"] == "high"


def test_init_needs_the_essentials(tmp_path):
    with pytest.raises(ValueError, match="buyer_roles"):
        profile.init({"name": "X", "pitch": "y"}, tmp_path / "p.toml", interactive=False)


def test_csv_reads_luma_export_with_custom_questions():
    leads = list(csv_file.people(GUESTS))
    ada = leads[0]
    assert (ada.name, ada.company, ada.title) == ("Ada Example", "Example Labs", "Head of Developer Relations")
    assert ada.linkedin.endswith("/ada_example")
    assert ada.signal == "attended" and leads[1].signal == "registered"


def test_attendee_scoring_reasons():
    ada, grace, linus, ming = (score(lead, SPONSORS["icp"]) for lead in list(csv_file.people(GUESTS))[:4])
    assert ada.tier == "hot" and "role: developer relations" in ada.reasons
    assert "senior: founder" in grace.reasons and "work email" not in grace.reasons
    assert linus.tier == "cold" and any("student" in r for r in linus.reasons)


def test_keywords_match_whole_words_only():
    lead = score(Lead(name="Sam", bio="Maintainer of a mail client"), DEVTOOL["icp"])
    assert not any("mentions" in r for r in lead.reasons)


def test_target_company_and_exclude():
    icp = dict(SPONSORS["icp"], target_companies=["Snowflake"], exclude=["rival.com"])
    assert "Snowflake is on your target list" in score(Lead(email="a@snowflake.com"), icp).reasons
    assert score(Lead(company="Rival", email="x@rival.com", title="CTO"), icp).score == 0


def test_github_login_from_url_or_handle():
    assert github.login_from("https://github.com/octocat/") == "octocat"
    assert github.login_from("@octocat") == "octocat"


def test_github_profile_scoring_and_draft():
    lead = Lead(github="dev", company="Agentco", bio="CTO. Building RAG search", followers=900,
                top_languages=["Python", "Shell"], signal="contributed", source="github-contributors:a/b")
    lead = draft(score(lead, DEVTOOL["icp"]), DEVTOOL)
    assert lead.tier == "hot"
    assert "codes in Python" in lead.reasons and "900 GitHub followers" in lead.reasons
    assert "contributed to a/b" in lead.draft and "Acme Vector, a vector database" in lead.draft


def test_cast_without_profile_explains_what_to_do(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["cast", "attendees-to-leads", "--csv", str(GUESTS)]) == 2
    assert "cantrip init" in capsys.readouterr().err


def test_cli_end_to_end_merges_duplicates(tmp_path, capsys):
    out = tmp_path / "leads.csv"
    assert main(["cast", "attendees-to-leads", "--csv", str(GUESTS), "--profile",
                 str(PROFILES / "event-sponsorships.toml"), "--event", "AI Day", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "4 leads" in printed and "Nothing was sent" in printed
    assert "Example Labs (2)" in printed
    assert "Thanks for being part of AI Day" in out.read_text()


def test_plain_cantrip_opens_the_app(monkeypatch):
    from cantrip.ui import server

    seen = {}
    monkeypatch.setattr(server, "serve", lambda **kw: seen.update(kw))
    assert main([]) == 0
    assert seen["port"] == 8765 and seen["open_browser"] is True
