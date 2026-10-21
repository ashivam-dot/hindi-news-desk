import importlib
import json
from datetime import datetime, timedelta

import pytest

from desk import channel, cli, config, ledger, youtube

UC = "UC" + "c" * 22
NOW = datetime(2026, 10, 22, 9, tzinfo=channel.PACIFIC)


class Err(Exception):
    """A googleapiclient HttpError as the desk reads it: resp.status and the JSON content."""

    def __init__(self, status, reason):
        super().__init__(f"HTTP {status} {reason}")
        self.resp = type("R", (), {"status": status})()
        self.content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()


class Call:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class Fake:
    """channels, playlists, playlistItems and channelSections in memory; every call is logged, and `fail` maps a
    call name ("playlistItems.insert") to the error it raises."""

    def __init__(self, title="क्यों हुआ"):
        self.branding = {"channel": {"title": title, "description": "हादसे और युद्ध। सुधार पिन कमेंट में।",
                                     "unsubscribedTrailer": "TRAILER"}, "image": {"x": 1}}
        self.lists, self.items, self.sections, self.calls, self.fail = {}, {}, [], [], {}

    def _do(self, name, fn):
        def call(**kw):
            self.calls.append(name)
            if name in self.fail:
                raise self.fail[name]
            return Call(lambda: fn(**kw))
        return call

    def _res(self, prefix, **fns):
        return type("Res", (), {k: staticmethod(self._do(f"{prefix}.{k}", f)) for k, f in fns.items()})()

    def channels(self):
        def lst(part, id=None, mine=None):
            if mine:
                return {"items": [{"id": UC}]}
            return {"items": [{"id": UC, "brandingSettings": json.loads(json.dumps(self.branding))}]}

        def upd(part, body):
            assert body["id"] == UC and body["brandingSettings"]["channel"]["title"]
            self.branding = body["brandingSettings"]
            return body
        return self._res("channels", list=lst, update=upd)

    def playlists(self):
        def lst(part, mine, maxResults, pageToken=None):
            return {"items": [{"id": i, "snippet": {"title": t}} for i, t in self.lists.items()]}

        def ins(part, body):
            pid = f"PL{len(self.lists)}"
            self.lists[pid] = body["snippet"]["title"]
            self.items[pid] = []
            return {"id": pid}
        return self._res("playlists", list=lst, insert=ins)

    def playlistItems(self):
        def lst(part, playlistId, maxResults, pageToken=None):
            return {"items": [{"contentDetails": {"videoId": v}} for v in self.items[playlistId]]}

        def ins(part, body):
            s = body["snippet"]
            self.items[s["playlistId"]].insert(0, s["resourceId"]["videoId"])
            return {}
        return self._res("playlistItems", list=lst, insert=ins)

    def channelSections(self):
        def lst(part, mine):
            return {"items": [{"contentDetails": {"playlists": [p]}} for p in self.sections]}

        def ins(part, body):
            self.sections += body["contentDetails"]["playlists"]
            return {"id": f"SEC{len(self.sections)}"}
        return self._res("channelSections", list=lst, insert=ins)


def row(vid, category="economy", **kw):
    return {"video_id": vid, "category": category, "kind": "explainer", "privacy": "public",
            "title": "पेट्रोल के दाम क्यों बढ़े", **kw}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(config, "CHANNEL_ID", UC)
    monkeypatch.setattr(youtube, "scopes", lambda: {"https://www.googleapis.com/auth/youtube"})
    api = Fake()
    monkeypatch.setattr(youtube, "client", lambda: api)
    return api


def published(rows):
    ledger.save("published", rows)


def test_the_about_is_within_youtubes_limits_and_promises_nothing_the_desk_does_not_do():
    assert len(channel.ABOUT) <= channel.ABOUT_LIMIT and len(channel.keywords()) <= channel.KEYWORDS_LIMIT
    for word in ("पिन", "pinned", "हादसे", "युद्ध", "व्यूज़", "views"):
        assert word not in channel.ABOUT
    for must in ("AI", "Wikipedia/Wikidata", "दो स्वतंत्र", "इंसानों ने", config.CONTACT, "सुधार"):
        assert must in channel.ABOUT
    assert '"hindi news"' in channel.keywords() and " RBI " in f" {channel.keywords()} "


def test_the_about_is_read_modified_and_written_back_whole_then_left_alone(fake):
    published([])
    line = channel.run({"about"}, NOW)
    got = fake.branding["channel"]
    assert got["title"] == "क्यों हुआ" and got["unsubscribedTrailer"] == "TRAILER" and fake.branding["image"]
    assert got["description"] == channel.ABOUT and got["defaultLanguage"] == "hi" and got["country"] == "IN"
    assert "about: set and read back" in line and "53 units this run" in line
    fake.calls.clear()
    assert "nothing left" in channel.run({"about"}, NOW) and fake.calls == []


def test_an_about_youtube_does_not_read_back_is_not_marked_done(fake, monkeypatch):
    published([])
    real = fake.channels

    def stale():  # the update "succeeds" but YouTube still shows the old About
        res = real()
        res.update = lambda **kw: Call(lambda: fake.calls.append("channels.update"))
        return res
    monkeypatch.setattr(fake, "channels", stale)
    assert "does not read back" in channel.run({"about"}, NOW)
    assert "about" not in ledger.load(channel.STATE, {})


def test_families_are_ad_friendly_public_current_stories_only(fake):
    published([row("A1"), row("A2", category="crime"), row("A3", privacy="private"), row("A4", retired_at="x"),
               row("A5", kind="advisory"), row("A6", title="पेट्रोल पंप मालिक गिरफ्तार"), row("A7", replaced="A1"),
               row("S1", category="health"), row("S2", category="science")])
    assert channel.eligible() == {"economy": ["A7"], "science": ["S1", "S2"]}


def test_playlists_are_made_filled_and_shown_once(fake):
    published([row("A1"), row("A2"), row("S1", category="science"), row("W1", category="world"),
               row("W2", category="weather")])
    line = channel.run({"playlists"}, NOW)
    assert "1 made, 2 Shorts added, 1 sections, 0 Shorts left" in line
    (pid,) = fake.lists
    assert fake.lists[pid] == channel.FAMILIES["economy"][0] and fake.items[pid] == ["A2", "A1"]
    assert fake.sections == [pid]
    fake.calls.clear()
    assert "nothing left" in channel.run({"playlists"}, NOW) and fake.calls == []
    published([row("A1"), row("A2"), row("A3")])
    assert "0 made, 1 Shorts added, 0 sections" in channel.run({"playlists"}, NOW)
    assert fake.items[pid] == ["A3", "A2", "A1"] and "playlistItems.list" not in fake.calls


def test_a_playlist_made_before_the_state_was_lost_is_found_by_its_title(fake):
    fake.lists["PLold"] = channel.FAMILIES["economy"][0]
    fake.items["PLold"] = ["A1"]
    published([row("A1"), row("A2")])
    assert "0 made, 1 Shorts added" in channel.run({"playlists"}, NOW)
    assert fake.items["PLold"] == ["A2", "A1"] and "playlists.insert" not in fake.calls


def test_the_unit_caps_spread_the_work_over_runs_and_days(fake, monkeypatch):
    monkeypatch.setattr(channel, "RUN_UNITS", 160)
    monkeypatch.setattr(channel, "DAY_UNITS", 330)
    published([row(f"A{i}") for i in range(8)])
    first = channel.run({"playlists"}, NOW)  # identity 1, playlists.list 1, insert 50, items.list 1, 2 adds
    assert "unit cap reached" in first and "1 made, 2 Shorts added" in first and "6 Shorts left" in first
    assert "3 Shorts added" in channel.run({"playlists"}, NOW)
    third = channel.run({"playlists"}, NOW)
    assert "0 Shorts added" in third and "305 today" in third
    assert "3 Shorts added, 0 sections, 0 Shorts left" in channel.run({"playlists"}, NOW + timedelta(days=1))
    (pid,) = fake.lists
    assert len(fake.items[pid]) == 8 and len(set(fake.items[pid])) == 8


def test_a_spent_quota_stops_the_setup_until_the_pacific_day_ends(fake):
    published([row("A1"), row("A2")])
    fake.fail["playlistItems.insert"] = Err(403, "quotaExceeded")
    assert "quota is spent (quotaExceeded); stopped until tomorrow" in channel.run({"playlists"}, NOW)
    fake.calls.clear()
    assert "stopped for today" in channel.run({"playlists"}, NOW) and fake.calls == []
    del fake.fail["playlistItems.insert"]
    assert "2 Shorts added" in channel.run({"playlists"}, NOW + timedelta(days=1))


def test_a_rate_limit_ends_only_this_run(fake):
    published([row("A1"), row("A2")])
    fake.fail["playlistItems.insert"] = Err(403, "rateLimitExceeded")
    assert "stopped for this run" in channel.run({"playlists"}, NOW)
    del fake.fail["playlistItems.insert"]
    assert "2 Shorts added" in channel.run({"playlists"}, NOW)


def test_a_deleted_video_is_noted_and_never_retried(fake):
    published([row("A1"), row("A2"), row("A3")])
    real = fake.playlistItems

    def refusing():
        res = real()
        insert = res.insert

        def ins(part, body):
            if body["snippet"]["resourceId"]["videoId"] == "A2":
                fake.calls.append("playlistItems.insert")
                raise Err(404, "videoNotFound")
            return insert(part=part, body=body)
        res.insert = ins
        return res
    fake.playlistItems = refusing
    assert "2 Shorts added" in channel.run({"playlists"}, NOW)
    state = ledger.load(channel.STATE, {})
    assert "videoNotFound" in state["playlists"]["economy"]["failed"]["A2"]
    fake.calls.clear()
    assert "nothing left" in channel.run({"playlists"}, NOW)


def test_a_refused_section_is_not_retried(fake):
    published([row("A1"), row("A2")])
    fake.fail["channelSections.insert"] = Err(400, "channelSectionLimitExceeded")
    assert "0 sections" in channel.run({"playlists"}, NOW)
    assert ledger.load(channel.STATE, {})["playlists"]["economy"]["section"].startswith("refused")
    fake.calls.clear()
    assert "nothing left" in channel.run({"playlists"}, NOW) and fake.calls == []


def test_no_write_scope_is_one_line_and_no_call(fake, monkeypatch):
    published([row("A1"), row("A2")])
    monkeypatch.setattr(youtube, "scopes", lambda: {"https://www.googleapis.com/auth/youtube.upload"})
    monkeypatch.setattr(youtube, "client", lambda: pytest.fail("signed in"))
    assert "no youtube or youtube.force-ssl scope" in channel.run({"about", "playlists"}, NOW)


def test_a_403_refusal_waits_for_the_next_day(fake):
    published([])
    fake.fail["channels.update"] = Err(403, "forbidden")
    assert "refused the write (HTTP 403 forbidden); stopped until tomorrow" in channel.run({"about"}, NOW)
    assert "stopped for today" in channel.run({"about"}, NOW)


def test_desk_untag_words_switch_the_jobs_on(monkeypatch):
    try:
        for value, untag, jobs in (("true", True, set()), ("", False, set()), ("TRUE", True, set()),
                                   ("untag about playlists", True, {"about", "playlists"}),
                                   ("about,playlists", False, {"about", "playlists"}), ("abouts", False, set())):
            monkeypatch.setenv("DESK_UNTAG", value)
            importlib.reload(config)
            assert (config.UNTAG, set(config.CHANNEL_JOBS)) == (untag, jobs), value
    finally:
        monkeypatch.delenv("DESK_UNTAG", raising=False)
        importlib.reload(config)


def test_untag_on_a_spent_quota_says_quota_not_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(config, "CHANNEL_ID", UC)
    monkeypatch.setattr(youtube, "scopes", lambda: None)

    def update(**kw):
        raise Err(403, "quotaExceeded")
    api = type("Api", (), {"videos": lambda self: type("V", (), {"update": staticmethod(update)})()})()
    monkeypatch.setattr(youtube, "client", lambda: api)
    monkeypatch.setattr(youtube, "identity", lambda a: {"id": UC})
    monkeypatch.setattr(youtube, "recent", lambda a, c: [{"id": "V1", "snippet": {
        "title": "t", "channelId": UC, "tags": [config.MARKER + "nw-x", "a"]}}])
    with pytest.raises(youtube.QuotaExceeded, match="quotaExceeded"):
        youtube.untag()


def test_the_run_does_the_channel_jobs_last_and_survives_them(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CHANNEL_JOBS", frozenset({"about"}))
    monkeypatch.setattr(config, "CHANNEL_ID", UC)
    from desk import channel as ch
    monkeypatch.setattr(ch, "run", lambda jobs: (_ for _ in ()).throw(RuntimeError("boom")))
    health = {"steps": ["published x"]}
    cli._channel_jobs(health)
    assert health["steps"] == ["published x", "channel: RuntimeError: boom"]
    monkeypatch.setattr(ch, "run", lambda jobs: "channel: about: done")
    held = {"steps": [], "held": "hold: quota"}
    cli._channel_jobs(held)
    assert held["steps"] == []
    cli._channel_jobs(health)
    assert health["steps"][-1] == "channel: about: done"
