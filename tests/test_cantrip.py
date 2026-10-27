from pathlib import Path

from cantrip import spell
from cantrip.cli import main
from cantrip.draft import draft
from cantrip.lead import Lead
from cantrip.score import score
from cantrip.sources import csv_file

ROOT = Path(__file__).resolve().parent.parent
CONFIG = spell.load("stargazers-to-leads")


def test_csv_source_reads_luma_style_columns():
    leads = list(csv_file.people(ROOT / "examples" / "luma-guests.csv"))
    assert [lead.name for lead in leads] == ["Ada Example", "Grace Sample", "Linus Placeholder"]
    assert leads[0].company == "Example Labs"
    assert leads[1].title == "Founder & CTO"


def test_score_gives_reasons_and_tiers():
    lead = score(Lead(name="Ada", company="Example Labs", title="Head of DevRel", email="a@x.io"), CONFIG["icp"])
    assert lead.tier in {"hot", "warm"}
    assert any("role" in r for r in lead.reasons)


def test_keywords_match_whole_words_only():
    lead = score(Lead(name="Sam", bio="Maintainer of a mail client"), CONFIG["icp"])
    assert not any("mentions" in r for r in lead.reasons)


def test_target_company_and_exclude():
    icp = dict(CONFIG["icp"], target_companies=["Snowflake"], exclude=["rival.com"])
    assert "Snowflake is on the target list" in score(Lead(company="Snowflake"), icp).reasons
    assert score(Lead(company="Rival", email="x@rival.com", title="CTO"), icp).score == 0


def test_draft_fills_template_without_placeholders_left():
    lead = draft(score(Lead(name="Grace Sample", company="Sample AI", title="Founder", source="csv:guests",
                            signal="registered"), CONFIG["icp"]), dict(CONFIG, sender="Yu", event_name="AI Day"))
    assert lead.draft.startswith("Hi Grace")
    assert "AI Day" in lead.draft and "{" not in lead.draft


def test_cli_end_to_end(tmp_path, capsys):
    out = tmp_path / "leads.csv"
    assert main(["cast", "stargazers-to-leads", "--csv", str(ROOT / "examples" / "luma-guests.csv"),
                 "--event", "AI Day", "--out", str(out)]) == 0
    assert "Nothing was sent" in capsys.readouterr().out
    assert out.read_text().count("\n") > 3
