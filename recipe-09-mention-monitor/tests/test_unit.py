import httpx

from agent import run_poll
from integrations.hn import search_mentions as hn_search
from integrations.reddit import search_mentions as reddit_search
from integrations.slack import post_alert
from lib.store import JsonStore


def test_hn_search_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"hits": [{"objectID": "1", "title": "InstaVM launch", "url": "https://x.com", "comment_text": "Great tool"}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mentions = hn_search("InstaVM", client=client)
    assert len(mentions) == 1
    assert mentions[0].source == "hackernews"


def test_reddit_search_parses():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>InstaVM on Reddit</title>
        <link href="https://reddit.com/r/test/1"/>
        <summary>Discussion about InstaVM</summary>
      </entry>
    </feed>"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=rss)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mentions = reddit_search("InstaVM", client=client)
    assert len(mentions) == 1
    assert mentions[0].source == "reddit"


def test_slack_dry_run():
    result = post_alert(text="test", dry_run=True)
    assert result.dry_run is True
    assert result.sent is False


def test_run_poll_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_hn(brand, *, limit=10, client=None):
        from integrations.hn import Mention

        return [Mention(id="hn-1", title="T", url="https://hn.com", source="hackernews", text="InstaVM rocks")]

    def fake_reddit(brand, *, limit=10, client=None):
        return []

    monkeypatch.setattr("agent.hn_integration.search_mentions", fake_hn)
    monkeypatch.setattr("agent.reddit_integration.search_mentions", fake_reddit)
    result = run_poll(dry_run=True)
    assert result.dry_run is True
    assert result.new == 1
    assert result.alerted >= 1


def test_store_dedup(tmp_path):
    store = JsonStore(tmp_path / "seen.json")
    assert not store.seen("a")
    store.mark_many(["a"])
    store.flush()
    assert JsonStore(tmp_path / "seen.json").seen("a")
