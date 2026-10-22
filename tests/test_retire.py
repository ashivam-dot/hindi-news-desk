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
    monkeypatch.setattr(youtube, "plays_publicly", lambda vid: None)  # no network: an unread page trusts the API
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
    assert "still reads back public" in health["steps"][0] and not ledger.published()[0].get("retire_page_read")
    cli.retire_listed(health)  # the next run tries again, and this time YouTube keeps it
    row = ledger.published()[0]
    assert row["retire_read_back"] == "private" and row["retired_at"] == "2026-10-22T00:48:41"
    calls = api["api"].updates
    cli.retire_listed(health)
    assert api["api"].updates == calls and len(health["steps"]) == 2  # done: never read again
    # A row read back through the API alone (before the page check) is read once more.
    ledger.update_published("V", {"retire_page_read": None})
    monkeypatch.setattr(youtube, "plays_publicly", lambda vid: True)
    cli.retire_listed(health)
    assert "watch page still plays it" in health["steps"][-1] and api["api"].updates == calls + 1


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


def test_a_short_the_api_reads_private_but_the_watch_page_still_plays_is_sent_again(api, monkeypatch):
    """2026-10-22: YM2dyGiYNJQ read back private through the API and its public watch page still played it."""
    plays = {"V": True}
    monkeypatch.setattr(youtube, "plays_publicly", lambda vid: plays[vid])
    api["api"] = Api(privacy="private")
    with pytest.raises(RuntimeError, match="watch page still plays it"):
        youtube.retire("V")
    assert api["api"].updates == 1  # the update is sent again, not skipped because the API says private
    plays["V"] = False
    assert youtube.retire("V") == "private" and api["api"].updates == 1


def test_the_watch_page_status_is_read_from_its_playability(monkeypatch):
    import requests
    pages = {"a": '..."playabilityStatus":{"status":"OK","x":1}', "b": '"playabilityStatus":{"status":"LOGIN_REQUIRED"}',
             "c": "<html>consent</html>"}
    monkeypatch.setattr(requests, "get", lambda url, **kw: type("R", (), {"text": pages[url.split("v=")[1][0]]})())
    assert [youtube.plays_publicly(v) for v in "abc"] == [True, False, None]
    monkeypatch.setattr(requests, "get", lambda url, **kw: (_ for _ in ()).throw(OSError("offline")))
    assert youtube.plays_publicly("a") is None
