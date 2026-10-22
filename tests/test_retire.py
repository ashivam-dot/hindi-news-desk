import json

import pytest

from desk import cli, config, ledger, youtube


class Call:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class Api:
    """One video on YouTube; `ignore` makes YouTube accept the update and keep the video public."""

    def __init__(self, privacy="public", channel=None, ignore=0):
        self.privacy, self.channel, self.ignore, self.updates = privacy, channel or config.CHANNEL_ID, ignore, 0

    def videos(self):
        api = self

        class Res:
            def list(self, part, id):
                return Call(lambda: {"items": [] if api.privacy is None else [
                    {"snippet": {"channelId": api.channel}, "status": {"privacyStatus": api.privacy}}]})

            def update(self, part, body):
                def go():
                    api.updates += 1
                    if api.updates > api.ignore:
                        api.privacy = body["status"]["privacyStatus"]
                    return {}
                return Call(go)
        return Res()


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(youtube, "RETIRE_WAIT", 0)
    monkeypatch.setattr(youtube, "identity", lambda api: {})
    monkeypatch.setattr(youtube, "plays_publicly", lambda vid: False)  # no network: the public read agrees with the API
    holder = {}
    monkeypatch.setattr(youtube, "client", lambda *a: holder["api"])
    return holder


def test_retire_reads_back_and_raises_when_youtube_keeps_the_video_public(api):
    api["api"] = Api()
    assert youtube.retire("V") == "private" and api["api"].updates == 1
    api["api"] = Api(ignore=1)  # 2026-10-22: YM2dyGiYNJQ was logged retired and stayed public
    with pytest.raises(RuntimeError, match="still reads back public"):
        youtube.retire("V")
    api["api"] = Api(privacy=None)
    assert youtube.retire("V") == "missing"
    api["api"] = Api(channel="UCother")
    with pytest.raises(youtube.WrongChannel):
        youtube.retire("V")


def test_a_listed_short_marked_retired_before_the_read_back_is_checked_once_more(api, tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(cli, "RETIRE", tmp_path / "retire.json")
    cli.RETIRE.write_text(json.dumps([{"video_id": "V", "why": "wrong"}]))
    ledger.save("published", [{"id": "s", "video_id": "V", "privacy": "private", "retired_at": "2026-10-22T00:48:41"}])
    api["api"] = Api(ignore=1)
    health = {"steps": []}
    cli.retire_listed(health)
    assert "still reads back public" in health["steps"][0] and not ledger.published()[0].get("retire_public_read")
    cli.retire_listed(health)  # the next run tries again, and this time YouTube keeps it
    row = ledger.published()[0]
    assert row["retire_read_back"] == "private" and row["retired_at"] == "2026-10-22T00:48:41"
    calls = api["api"].updates
    cli.retire_listed(health)
    assert api["api"].updates == calls and len(health["steps"]) == 2  # done: never read again
    # A row read back through the API alone (before the page check) is read once more.
    ledger.update_published("V", {"retire_public_read": None})
    monkeypatch.setattr(youtube, "plays_publicly", lambda vid: True)
    cli.retire_listed(health)
    assert "still plays publicly" in health["steps"][-1] and api["api"].updates == calls + 2


class TitleApi:
    """One video's snippet on YouTube; `ignore` makes YouTube accept the update and keep the old title."""

    def __init__(self, ignore=0):
        self.snippet = {"channelId": config.CHANNEL_ID, "title": "old", "description": "d", "categoryId": "25",
                        "tags": ["t"], "defaultLanguage": "hi"}
        self.ignore, self.sent = ignore, []

    def videos(self):
        api = self

        class Res:
            def list(self, part, id):
                return Call(lambda: {"items": [{"snippet": dict(api.snippet)}]})

            def update(self, part, body):
                def go():
                    api.sent.append(body)
                    if len(api.sent) > api.ignore:
                        api.snippet.update(body["snippet"])
                    return {}
                return Call(go)
        return Res()


def test_a_listed_retitle_keeps_the_rest_of_the_snippet_reads_back_and_is_done_once(api, tmp_path, monkeypatch):
    monkeypatch.setattr(youtube, "scopes", lambda: None)
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(cli, "RETITLE", tmp_path / "retitle.json")
    cli.RETITLE.write_text(json.dumps([{"video_id": "V", "title": "new", "why": "unclear"}]))
    ledger.save("published", [{"id": "s", "video_id": "V", "title": "old", "privacy": "public"}])
    api["api"] = TitleApi(ignore=1)
    health = {"steps": []}
    cli.retitle_listed(health)
    assert "does not read back" in health["steps"][0] and ledger.published()[0]["title"] == "old"
    cli.retitle_listed(health)
    sent = api["api"].sent[-1]["snippet"]
    assert sent == {"title": "new", "description": "d", "categoryId": "25", "tags": ["t"], "defaultLanguage": "hi"}
    row = ledger.published()[0]
    assert row["title"] == "new" and row["old_title"] == "old" and row["retitled_why"] == "unclear"
    cli.retitle_listed(health)
    assert len(api["api"].sent) == 2 and len(health["steps"]) == 2  # done: never written again


def test_a_short_the_api_reads_private_but_the_watch_page_still_plays_is_sent_again(api, monkeypatch, tmp_path):
    """2026-10-22: YM2dyGiYNJQ read back private through the API and kept playing publicly, twice."""
    plays = {"V": True}
    monkeypatch.setattr(youtube, "plays_publicly", lambda vid: plays[vid])
    api["api"] = Api(privacy="private")
    with pytest.raises(RuntimeError, match="still plays publicly"):
        youtube.retire("V")
    assert api["api"].updates == 2  # sent through unlisted and back, not skipped because the API says private
    plays["V"] = False
    assert youtube.retire("V") == "private" and api["api"].updates == 2
    plays["V"] = None  # a runner's bot check: neither public read says, so the row is read again next run
    assert youtube.retire("V") == youtube.PAGE_UNREAD and api["api"].updates == 2
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(cli, "RETIRE", tmp_path / "retire.json")
    cli.RETIRE.write_text(json.dumps([{"video_id": "V", "why": "wrong"}]))
    ledger.save("published", [{"id": "s", "video_id": "V", "privacy": "private", "retire_page_read": True}])
    cli.retire_listed({"steps": []})  # the older page read-back is not trusted
    assert ledger.published()[0]["retire_public_read"] is False


@pytest.mark.parametrize("oembed, page, plays", [
    (200, "", True), (403, "", False),
    (429, '..."playabilityStatus":{"status":"OK","x":1}', True),
    (429, '"playabilityStatus":{"status":"LOGIN_REQUIRED","reason":"Private video"}', False),
    (429, '"playabilityStatus":{"status":"LOGIN_REQUIRED","reason":"Sign in to confirm you’re not a bot"}', None),
    (429, "<html>consent</html>", None),
])
def test_the_public_read_is_oembed_then_the_watch_pages_playability(monkeypatch, oembed, page, plays):
    import requests

    def get(url, **kw):
        return type("R", (), {"status_code": oembed if "oembed" in url else 200, "text": page})()
    monkeypatch.setattr(requests, "get", get)
    assert youtube.plays_publicly("a") is plays


def test_an_offline_public_read_says_nothing(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda url, **kw: (_ for _ in ()).throw(OSError("offline")))
    assert youtube.plays_publicly("a") is None


def test_a_retirement_that_keeps_failing_stops_spending_quota(api, tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(cli, "RETIRE", tmp_path / "retire.json")
    monkeypatch.setattr(youtube, "plays_publicly", lambda vid: True)
    cli.RETIRE.write_text(json.dumps([{"video_id": "V", "why": "wrong"}]))
    ledger.save("published", [{"id": "s", "video_id": "V", "privacy": "private"}])
    api["api"] = Api(privacy="private")
    health = {"steps": []}
    for _ in range(cli.RETIRE_TRIES + 2):
        cli.retire_listed(health)
    assert api["api"].updates == 2 * cli.RETIRE_TRIES and "make it private in Studio" in health["steps"][-1]

