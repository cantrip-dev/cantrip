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
community-led growth for AI tools. Sam Ortiz is a Senior Engineer at Acme. Sponsors include Graphite."""


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
                 "evidence": "Maya Chen, Head of Developer Relations at Vectorly, will talk about"},
                {"name": "Priya Ghost", "title": "VP Marketing", "company": "Nowhere Inc",
                 "evidence": "Priya Ghost leads marketing"},  # not on the page: must be dropped
                {"name": "", "title": "Head of Marketing", "company": "Graphite", "evidence": "Sponsors include Graphite"},
            ]})
        if "research one sales lead" in system:
            return "- Vectorly launched an open-source SDK this month [https://example.com/news]"
        if "first outreach note" in system:
            return "Hi Maya, I saw your DevConf talk on community-led growth. Would you be open to a quick call?"
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
    assert "Maya Chen" in names and "Priya Ghost" not in names
    company_only = [lead for lead in leads if not lead.name]
    assert company_only and company_only[0].title == ""  # a role with no person isn't kept as a title
    maya = next(lead for lead in leads if lead.name == "Maya Chen")
    assert maya.source_url.startswith("https://devconf.example/") and maya.evidence.startswith("Maya Chen")


def test_scoring_and_ai_drafts_for_people_only():
    ai, search = FakeAI(), FakeSearch()
    results = engine.run(CONFIG, web_source.find(ai, search, CONFIG, max_queries=1, progress=lambda _: None))
    assert results[0].name == "Maya Chen" and results[0].tier == "hot"
    engine.enhance(results, CONFIG, ai, search, research=True, ai_drafts=True, progress=lambda _: None)
    assert results[0].draft.startswith("Hi Maya") and "open-source SDK" in results[0].research
    graphite = next(lead for lead in results if lead.company == "Graphite")
    assert "Hi Maya" not in graphite.draft  # no AI draft for a company with nobody named


def test_draft_prompt_keeps_lead_and_offer_apart():
    ai = FakeAI()
    web_source.write_draft(ai, Lead(name="Maya Chen", evidence="spoke at DevConf", source_url="https://x.example",
                                    signal="mentioned"), dict(CONFIG, event_name="AI Builders Day"))
    facts = json.loads(ai.prompts[-1][1])
    assert facts["about_the_lead"]["how_they_came_to_us"] == ""
    assert facts["about_our_offer"]["our_event"] == "AI Builders Day"


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
