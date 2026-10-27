from pathlib import Path

from cantrip import spell
from cantrip.cli import main
from cantrip.draft import draft
from cantrip.lead import Lead
from cantrip.score import score
from cantrip.sources import csv_file, github

ROOT = Path(__file__).resolve().parent.parent
ATTENDEES = spell.load("attendees-to-leads")
GITHUB = spell.load("github-to-leads")
GUESTS = ROOT / "examples" / "luma-guests.csv"


def test_csv_reads_luma_export_with_custom_questions():
    leads = list(csv_file.people(GUESTS))
    ada = leads[0]
    assert (ada.name, ada.company, ada.title) == ("Ada Example", "Example Labs", "Head of Developer Relations")
    assert ada.linkedin.endswith("/ada-example")
    assert ada.signal == "attended" and leads[1].signal == "registered"


def test_attendee_scoring_sorts_by_seniority_function_and_email():
    ada, grace, linus, ming = (score(lead, ATTENDEES["icp"]) for lead in list(csv_file.people(GUESTS))[:4])
    assert ada.tier == "hot" and "role: developer relations" in ada.reasons
    assert "senior: founder" in grace.reasons and "work email" not in grace.reasons
    assert linus.tier == "cold" and any("student" in r for r in linus.reasons)
    assert ada.score > ming.score > linus.score


def test_keywords_match_whole_words_only():
    lead = score(Lead(name="Sam", bio="Maintainer of a mail client"), GITHUB["icp"])
    assert not any("mentions" in r for r in lead.reasons)


def test_target_company_and_exclude():
    icp = dict(ATTENDEES["icp"], target_companies=["Snowflake"], exclude=["rival.com"])
    assert "Snowflake is on your target list" in score(Lead(email="a@snowflake.com"), icp).reasons
    assert score(Lead(company="Rival", email="x@rival.com", title="CTO"), icp).score == 0


def test_github_login_from_url_or_handle():
    assert github.login_from("https://github.com/octocat/") == "octocat"
    assert github.login_from("@octocat") == "octocat"


def test_github_profile_scoring():
    lead = Lead(github="dev", company="Agentco", bio="Founder. Building AI agents", followers=900,
                top_languages=["Python", "Shell"], signal="contributed", source="github-contributors:a/b")
    lead = draft(score(lead, GITHUB["icp"]), dict(GITHUB, sender="Yu"))
    assert lead.tier == "hot"
    assert "codes in Python" in lead.reasons and "900 GitHub followers" in lead.reasons
    assert "contributed to a/b" in lead.draft and "{" not in lead.draft


def test_cli_end_to_end_merges_duplicates(tmp_path, capsys):
    out = tmp_path / "leads.csv"
    assert main(["cast", "attendees-to-leads", "--csv", str(GUESTS), "--event", "AI Day", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "4 leads" in printed and "Nothing was sent" in printed
    assert "Example Labs (2)" in printed
    assert "Thanks for joining us at AI Day" in out.read_text()
