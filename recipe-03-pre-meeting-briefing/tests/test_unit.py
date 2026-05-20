import httpx

from agent import build_briefing, parse_cal_event, run_briefing
from integrations.exa import ResearchHit, research_attendee


def test_research_attendee_parses(monkeypatch):
    monkeypatch.setenv("EXA_MOCK", "0")
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"url": "https://x.com", "title": "News", "text": "Raised seed"}]},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    hits = research_attendee("Jane", "Acme", "jane@acme.vc", client=client)
    assert len(hits) >= 1
    assert hits[0].url == "https://x.com"


def test_parse_cal_event():
    event = {
        "attendees": [{"name": "Jane", "email": "jane@acme.vc", "organization": "Acme"}],
        "startTime": "2026-05-20T15:00:00Z",
        "title": "Intro",
    }
    parsed = parse_cal_event(event)
    assert parsed["attendee_name"] == "Jane"
    assert parsed["company"] == "Acme"


def test_build_briefing_dry_run(monkeypatch):
    def fake_research(name, company, email, *, client=None):
        return [ResearchHit(url="https://x.com", title="Hit", snippet="Snippet")]

    monkeypatch.setattr("agent.research_attendee", fake_research)
    result = build_briefing(
        {"attendees": [{"name": "Jane", "email": "j@x.com", "organization": "Acme"}]},
        dry_run=True,
    )
    assert result.dry_run is True
    assert "Jane" in result.briefing


def test_run_briefing_dry_run(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_research(name, company, email, *, client=None):
        return [ResearchHit(url="https://x.com", title="Hit", snippet="Snippet")]

    monkeypatch.setattr("agent.research_attendee", fake_research)
    result = run_briefing(dry_run=True)
    assert result.dry_run is True
    assert result.new == 1
