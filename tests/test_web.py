import json
from pathlib import Path

from cantrip import engine, profile, spell
from cantrip.ai import AI
from cantrip.lead import Lead
from cantrip.sources import web as web_source
from cantrip.web import Result, page_text

ROOT = Path(__file__).resolve().parent.parent
CONFIG = profile.apply(spell.load("web-to-leads"),
                       profile.load(ROOT / "examples" / "profiles" / "event-sponsorships.toml"))

PAGE = """Speakers at DevConf 2026. Maya Chen, Head of Developer Relations at Vectorly, will talk about
community-led growth for AI tools. Vectorly just raised a $6M seed round. Sam Ortiz is a Senior Engineer at Acme.
Sponsors include Graphite, which is hiring its first head of marketing. Lee Park, VP Marketing at Vectorly, attended."""


class FakeAI(AI):
    """Answers like a model would, without a network: plans, extracts (including one made-up person), drafts."""

    def __init__(self):
        super().__init__(key="test")
        self.prompts = []

    def chat(self, system, user, max_tokens=1500):
        self.calls += 1
        self.prompts.append((system, user))
        if "plan web searches" in system:
            return json.dumps({"queries": ["devrel leaders AI tools", "AI developer conference sponsors 2026"]})
        if "extract sales leads" in system:
            return json.dumps({"leads": [
                {"name": "Maya Chen", "title": "Head of Developer Relations", "company": "Vectorly",
                 "evidence": "Maya Chen, Head of Developer Relations at Vectorly, will talk about",
                 "why_now": "Vectorly just raised a $6M seed round", "stage": "seed"},
                {"name": "Lee Park", "title": "VP Marketing", "company": "Vectorly",
                 "evidence": "Lee Park, VP Marketing at Vectorly, attended"},  # fits, but no why-now: warm at most
                {"name": "Sam Ortiz", "title": "Senior Engineer", "company": "",
                 "evidence": "made-up praise for Sam"},  # no real quote from the page: dropped
                {"name": "Priya Ghost", "title": "VP Marketing", "company": "Nowhere Inc",
                 "evidence": "Priya Ghost leads marketing"},  # not on the page: must be dropped
                {"name": "", "title": "Head of Marketing", "company": "Graphite", "evidence": "Sponsors include Graphite",
                 "why_now": "Graphite, which is hiring its first head of marketing"},
            ]})
        if "research one sales lead" in system:
            return "- Vectorly launched an open-source SDK this month [https://example.com/news]"
        if "one opening sentence" in system:
            return "Saw that Vectorly raised a $6M seed round." if "Vectorly" in user else "You're probably busy."
        raise AssertionError(system)


class FakeSearch:
    def __init__(self):
        self.searches = 0
        self.skipped = 0

    def search(self, query, count=5):
        self.searches += 1
        return [Result(f"https://devconf.example/{self.searches}", "DevConf speakers", "", PAGE * 3)]

    def read(self, result, max_chars=12000):
        return result.content[:max_chars]


def test_plan_reads_the_profile():
    ai = FakeAI()
    assert web_source.plan(ai, CONFIG, "", 2) == ["devrel leaders AI tools", "AI developer conference sponsors 2026"]
    assert "sponsorships for AI Builders Day" in ai.prompts[0][1]


def test_find_keeps_only_people_and_companies_on_the_page():
    leads = list(web_source.find(FakeAI(), FakeSearch(), CONFIG, max_queries=2, progress=lambda _: None))
    names = {lead.name for lead in leads}
    assert "Maya Chen" in names and "Priya Ghost" not in names and "Sam Ortiz" not in names
    company_only = [lead for lead in leads if not lead.name]
    assert company_only and company_only[0].title == ""  # a role with no person isn't kept as a title
    maya = next(lead for lead in leads if lead.name == "Maya Chen")
    assert maya.source_url.startswith("https://devconf.example/") and maya.evidence.startswith("Maya Chen")


def test_scoring_and_ai_drafts_for_people_only():
    ai, search = FakeAI(), FakeSearch()
    results = engine.run(CONFIG, web_source.find(ai, search, CONFIG, max_queries=1, progress=lambda _: None))
    assert results[0].name == "Maya Chen" and results[0].tier == "hot"
    assert any(r.startswith("why now: Vectorly just raised") for r in results[0].reasons)
    lee = next(lead for lead in results if lead.name == "Lee Park")
    assert lee.tier == "warm" and "warm until there's a why-now signal" in lee.reasons
    engine.enhance(results, CONFIG, ai, search, research=True, ai_drafts=True, progress=lambda _: None)
    assert results[0].draft.startswith("Hi Maya") and "open-source SDK" in results[0].research
    graphite = next(lead for lead in results if lead.company == "Graphite")
    assert "Hi Maya" not in graphite.draft  # no AI draft for a company with nobody named


def test_draft_is_a_factual_hook_plus_the_profile_words():
    ai = FakeAI()
    note = web_source.write_draft(ai, Lead(name="Maya Chen", company="Vectorly", why_now="Vectorly raised a seed"), CONFIG)
    assert note.startswith("Hi Maya,\n\nSaw that Vectorly raised a $6M seed round. I'm building " + CONFIG["product"])
    assert f"Would you be open to {CONFIG['ask']}?" in note
    guess = web_source.write_draft(ai, Lead(name="Lee Park", title="VP Marketing", company="Bigco",
                                            evidence="Lee Park attended"), CONFIG)
    assert "probably" not in guess and "I'm writing to you as VP Marketing at Bigco." in guess  # guessing hook dropped
    bare = web_source.write_draft(ai, Lead(name="Sam Ortiz"), CONFIG)
    assert len(ai.prompts) == 2 and bare.startswith("Hi Sam,\n\nI'm building")  # nothing to hook on: no AI call


def test_ai_provider_choice():
    assert AI.make("anthropic", "k").base_url == "https://api.anthropic.com"
    assert AI.make(base_url="http://localhost:11434/v1").ready  # a local model needs no key
    assert not AI.make().ready


def test_page_text_drops_scripts_and_menus():
    text = page_text("<html><nav>Menu</nav><script>x=1</script><p>Hello <b>there</b></p><footer>f</footer></html>")
    assert text == "Hello there"


def test_blocked_and_video_sites_are_skipped():
    assert web_source._skip("https://www.youtube.com/watch?v=1", [])
    assert web_source._skip("https://old.reddit.com/r/x", [])
    assert web_source._skip("https://example.com/a", ["example.com"])
    assert not web_source._skip("https://devconf.example/speakers", [])


def test_exa_and_tinyfish_requests(monkeypatch):
    from cantrip import web
    seen = []

    def fake(url, data=None, headers=None, timeout=30):
        seen.append((url, data, headers))
        if "exa.ai" in url:
            return json.dumps({"results": [{"url": "https://a.dev", "title": "A", "text": "x" * 600}]}).encode()
        if "fetch.tinyfish" in url:
            return json.dumps({"results": [{"text": "page text from tinyfish"}]}).encode()
        return json.dumps({"results": [{"url": "https://b.dev", "title": "B", "snippet": "s"}]}).encode()
    monkeypatch.setattr(web, "_request", fake)

    exa = web.Search(provider="exa", key="k", category="people")
    found = exa.search("devrel leads", 3)
    assert found[0].url == "https://a.dev" and seen[0][1]["category"] == "people"
    assert exa.read(found[0]).startswith("x") and exa.pages == 0  # Exa returned the page text

    tf = web.Search(provider="tinyfish", key="k", reader_key="k")
    hit = tf.search("devrel", 3)[0]
    assert "query=devrel" in seen[1][0] and seen[1][2]["X-API-Key"] == "k"
    assert tf.read(hit) == "page text from tinyfish"


def test_tavily_and_searxng_requests(monkeypatch):
    import io
    import urllib.error

    import pytest

    from cantrip import web
    seen = []

    def fake(url, data=None, headers=None, timeout=30):
        seen.append((url, data, headers))
        if "tavily" in url:
            return json.dumps({"results": [{"url": "https://t.dev", "title": "T", "content": "c",
                                            "raw_content": "y" * 600}]}).encode()
        if "nojson" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(b""))
        return json.dumps({"results": [{"url": "https://s.dev", "title": "S", "content": "snip"}]}).encode()
    monkeypatch.setattr(web, "_request", fake)

    tavily = web.Search(provider="tavily", key="tvly-k")
    hit = tavily.search("devrel", 3)[0]
    assert seen[0][2]["Authorization"] == "Bearer tvly-k" and seen[0][1]["include_raw_content"] is True
    assert tavily.read(hit).startswith("y")  # Tavily returned the page, so nothing else is fetched

    sx = web.Search(provider="searxng", url="http://localhost:8888/")
    assert sx.ready and sx.search("devrel", 3)[0].url == "https://s.dev"
    assert seen[1][0].startswith("http://localhost:8888/search?") and "format=json" in seen[1][0]
    with pytest.raises(web.SearchError, match="formats"):
        web.Search(provider="searxng", url="http://nojson").search("x")


def test_draft_rules_and_why_now_suggestions():
    ai = FakeAI()
    web_source.write_draft(ai, Lead(name="Maya Chen", why_now="Vectorly just raised a seed round"), CONFIG)
    system, user = ai.prompts[-1]
    assert "Don't mention the seller's offer" in system and json.loads(user)["why_now_quote"].startswith("Vectorly")

    class SuggestAI(AI):
        def chat(self, system, user, max_tokens=1500):
            if "check search results" in system:
                return json.dumps({"specific": [0]})
            return json.dumps({"signals": [{"signal": "just raised a seed round", "why": "new budget",
                                            "search": "devtool startup raises seed round"}]})
    found = web_source.suggest_why_now(SuggestAI(key="k"), CONFIG, FakeSearch(), progress=lambda _: None)
    assert found[0]["signal"] == "just raised a seed round" and found[0]["examples"][0]["url"].startswith("https://")


def test_profile_update_keeps_hand_edits(tmp_path):
    path = tmp_path / "cantrip.toml"
    path.write_text('[product]\nname = "X"\npitch = "y"\n[icp]\nbuyer_roles = ["cto"]\n'
                    '[weights]\nkeyword = 40\n[templates]\nhot = """\nHi {first_name}\n"""\n')
    profile.update({"name": "X", "pitch": "y", "buyer_roles": "cto, founder", "why_now": "raised a seed round"}, path)
    loaded = profile.load(path)
    assert loaded["weights"]["keyword"] == 40 and loaded["templates"]["hot"].strip() == "Hi {first_name}"
    assert loaded["icp"]["why_now"] == ["raised a seed round"]


def test_roundups_stages_and_exclusions():
    from cantrip.score import score

    class RoundupAI(FakeAI):
        def chat(self, system, user, max_tokens=1500):
            if "extract sales leads" in system:
                return json.dumps({"leads": [{"name": "", "company": c, "why_now": "Sponsors include Graphite"}
                                             for c in ("Graphite", "Vectorly", "Acme", "Bigco")]})
            return super().chat(system, user, max_tokens)
    assert web_source.extract(RoundupAI(), CONFIG, "https://x.example", PAGE) == []

    icp = dict(CONFIG["icp"], stages=["seed", "yc"], exclude=["clay.com"])
    yc = score(Lead(name="A B", title="Founder", company="Nex", stage="S2026", why_now="live today"), icp)
    late = score(Lead(name="C D", title="CEO", company="Tabs", stage="Series B", why_now="raised $55M"), icp)
    clay = score(Lead(name="E F", title="CEO", company="Clay"), icp)
    assert "stage: S2026" in yc.reasons and late.tier != "hot" and clay.reasons == ["excluded by your ICP"]


def test_old_news_is_not_a_why_now():
    from datetime import date
    today = date(2026, 10, 27)
    assert web_source._stale("raised $34M in January 2024", today)
    assert web_source._stale("Series B: $40.3M (May 2025)", today)
    assert not web_source._stale("closed a $44 million seed round on Sept. 1, 2026", today)
    assert not web_source._stale("joins Every as head of growth", today)
    assert web_source._stale("Posted March 3, 2023. Union.ai today announced its Series A", today)
