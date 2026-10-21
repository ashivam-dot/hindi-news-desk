from datetime import date, datetime, timedelta, timezone

import pytest

from desk import ledger, news, plan, trends


def utc(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def test_the_desk_covers_only_the_big_stories_and_never_runs_past_youtubes_limit():
    # Owner, 2026-10-21: only the really high-profile stories, each covered properly.
    assert plan.MAX_PER_DAY + plan.BREAKING_EXTRA <= plan.YOUTUBE_DAILY_UPLOADS
    assert plan.MAX_PER_DAY <= 6 and plan.BREAKING_EXTRA >= 1 and plan.MIN_GAP.total_seconds() <= 20 * 60


def test_a_low_place_or_a_low_demand_kind_needs_a_higher_place():
    from datetime import datetime, timezone

    at = datetime(2026, 10, 21, 8, tzinfo=timezone.utc)
    base = {"id": "kh-x", "kind": "explainer", "region": "india", "top": {"IN": 15}, "fame": 1000,
            "news_at": at.isoformat()}
    assert "too low" in plan.unpopular(base | {"category": "court", "top_score": 0.3}, at)
    assert plan.unpopular(base | {"category": "court", "top_score": 0.5}, at) is None
    assert "near the top" in plan.unpopular(base | {"category": "economy", "top_score": 0.5}, at)
    assert plan.unpopular(base | {"category": "economy", "top_score": 0.8}, at) is None
    assert plan.demand({"category": "attack"}) > plan.demand({"category": "diplomacy"})


def test_regular_shorts_go_out_min_gap_apart_up_to_the_cap_an_ist_day(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(plan, "MAX_PER_DAY", 10)
    monkeypatch.setattr(plan, "YOUTUBE_DAILY_UPLOADS", 20)  # the lanes alone, past YouTube's own limit
    at = utc(9, 12)  # 17:30 IST
    assert plan.can_publish(at) is None
    ledger.record_publish({"id": "wk-a", "published_at": "2026-10-09T11:50:00+00:00", "loss": False})
    assert "h ago" in plan.can_publish(at)
    assert plan.can_publish(at, breaking=True) is None  # breaking news never waits for the last Short
    assert plan.can_publish(utc(9, 12, 20)) is None
    # Nine more that IST day (from 02:00 UTC = 07:30 IST): ten in all.
    for i in range(9):
        ledger.record_publish({"id": f"wk-{i}", "published_at": f"2026-10-09T{2 + i:02d}:00:00+00:00", "loss": False})
    late = utc(9, 16)  # 21:30 IST
    assert "today" in plan.can_publish(late)
    assert plan.can_publish(late, breaking=True) is None
    # A case angle may take the spare slot too, but MIN_GAP after the last Short.
    assert plan.can_publish(late, spare=True) is None
    assert "h ago" in plan.can_publish(utc(9, 10, 10), spare=True)
    # 19:00 UTC on 9 October is already 00:30 IST on 10 October: a new IST day.
    assert plan.can_publish(utc(9, 19)) is None


def test_breaking_extra_is_two_and_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(plan, "MAX_PER_DAY", 10)
    monkeypatch.setattr(plan, "YOUTUBE_DAILY_UPLOADS", 20)  # the lanes alone, past YouTube's own limit
    for i in range(12):
        ledger.record_publish({"id": f"wk-{i}", "published_at": f"2026-10-09T{2 + i:02d}:00:00+00:00", "loss": False})
    assert "today" in plan.can_publish(utc(9, 15), breaking=True)
    monkeypatch.setattr(plan, "BREAKING_EXTRA", 0)
    ledger.save("published", ledger.published()[:10])
    assert "today" in plan.can_publish(utc(9, 15), breaking=True)


def _day(n, retired=(), start=2):
    """n uploads on 9 October from 07:30 IST, an hour apart; those indexed in `retired` made private since."""
    return [{"id": f"wk-{i}", "video_id": f"v{i}", "published_at": f"2026-10-09T{start + i:02d}:00:00+00:00",
             **({"privacy": "private", "retired_at": "2026-10-09T12:00:00+00:00"} if i in retired else {})}
            for i in range(n)]


def test_retired_shorts_free_their_slots_but_count_toward_youtubes_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    late = utc(9, 16)  # 21:30 IST
    ledger.save("published", _day(8))
    assert "already 8 Shorts today" in plan.can_publish(late, breaking=True)
    # 21 Oct 2026: three of the day's uploads retired, and every run held "already N Shorts today".
    ledger.save("published", _day(7, retired={3, 4}))
    assert plan.can_publish(late) is None
    assert plan.can_publish(late, spare=True) is None and plan.can_publish(late, breaking=True) is None
    # YouTube counts the retired uploads too; the last two before its limit are breaking news's alone.
    ledger.save("published", _day(8, retired={3, 4, 7}))
    assert "wait for breaking news" in plan.can_publish(late)
    assert "wait for breaking news" in plan.can_publish(late, spare=True)
    assert plan.can_publish(late, breaking=True) is None
    ledger.save("published", _day(10, retired={0, 1, 2, 3, 4}))
    assert "YouTube's limit" in plan.can_publish(late, breaking=True)


def test_retirements_never_let_regular_shorts_take_breaking_news_last_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    late = utc(9, 16)  # 21:30 IST
    # Nine uploads, four retired: five on the channel, under every lane's cap, yet only breaking news may go.
    ledger.save("published", _day(9, retired={0, 1, 2, 3}))
    assert "wait for breaking news" in plan.can_publish(late)
    assert "wait for breaking news" in plan.can_publish(late, spare=True)
    assert plan.can_publish(late, breaking=True) is None
    ready, notes = plan.lineup([{"id": "wk-Q1", "title": "x", "fame": 10 ** 6, "news_at": late.isoformat(),
                                 "top": None},
                                {"id": "nw-case-angle", "title": "y", "fame": 10, "case": "A case", "top": None}], late)
    assert [c["id"] for c in ready] == ["wk-Q1"] and ready[0]["breaking"]
    assert notes == ["hold nw-case-angle: already 9 uploads today (IST); the last 2 before YouTube's limit wait for "
                     "breaking news"]
    # Regular Shorts stop at eight uploads, so a breaking story still has the ninth and the tenth.
    for n in range(plan.YOUTUBE_DAILY_UPLOADS - plan.BREAKING_EXTRA, plan.YOUTUBE_DAILY_UPLOADS):
        ledger.save("published", _day(n, retired=set(range(n - 4))))
        assert plan.can_publish(late, breaking=True) is None, n
    monkeypatch.setattr(plan, "BREAKING_EXTRA", 0)  # a hard cap for every lane
    ledger.save("published", _day(9, retired={0, 1, 2, 3}))
    assert plan.can_publish(late) is None


def test_a_short_and_its_remake_count_once(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    rows = _day(6)
    ledger.save("published", rows)
    assert "already 6 Shorts today" in plan.can_publish(utc(9, 16))
    ledger.save("published", rows[:5] + [rows[5] | {"replaced": "v0"}])
    assert plan.can_publish(utc(9, 16)) is None
    assert len(plan.on_channel(ledger.published())) == 5


def test_the_evening_keeps_two_regular_slots_but_breaking_news_never_waits(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    ledger.save("published", _day(plan.MAX_PER_DAY - plan.EVENING_RESERVE))  # the last at 10:30 IST
    noon = utc(9, 11)  # 16:30 IST
    assert "wait for 18:00 IST" in plan.can_publish(noon)
    assert "wait for 18:00 IST" in plan.can_publish(noon, spare=True)
    assert plan.can_publish(noon, breaking=True) is None
    assert plan.can_publish(utc(9, 12, 30)) is None  # 18:00 IST
    ledger.save("published", _day(plan.MAX_PER_DAY - plan.EVENING_RESERVE - 1))
    assert plan.can_publish(noon) is None
    ready, notes = plan.lineup([{"id": "wk-Q1", "title": "x", "fame": 10 ** 6, "news_at": noon.isoformat(),
                                 "top": None}], noon)
    assert ready and not notes


def test_a_scheduled_short_only_blocks_the_half_hour_around_it(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    ledger.record_publish({"id": "wk-s", "published_at": "2026-10-10T03:45:00+00:00", "loss": False})
    assert plan.can_publish(utc(10, 3)) is None
    assert "scheduled" in plan.can_publish(utc(10, 3, 30))
    assert "h ago" in plan.can_publish(utc(10, 4))


@pytest.mark.parametrize("at, open_", [(utc(9, 1, 29), False), (utc(9, 1, 30), True), (utc(9, 18, 29), True),
                                       (utc(9, 18, 30), False), (utc(9, 20), False)])
def test_window_is_seven_to_midnight_ist(at, open_):
    # 01:30 UTC is 07:00 IST and 18:30 UTC is midnight IST.
    assert plan.in_window(at) is open_


def test_lineup_holds_regular_stories_at_night_but_not_breaking_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    at = utc(9, 20)  # 01:30 IST
    quiet = {"id": "wk-1", "kind": "incident", "region": "india", "fame": 150_000, "news_at": "2026-10-09T18:00:00+00:00"}
    big = {"id": "wk-2", "kind": "incident", "region": "india", "fame": 900_000, "news_at": "2026-10-09T19:00:00+00:00"}
    ready, notes = plan.lineup([quiet, big], at)
    assert [c["id"] for c in ready] == ["wk-2"] and ready[0]["breaking"]
    assert any("07:00-24:00 IST" in n for n in notes)
    ready, _ = plan.lineup([quiet], utc(10, 5))
    assert [c["id"] for c in ready] == ["wk-1"]


def test_a_story_that_missed_its_moment_is_dropped_not_held(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    at = utc(10, 6)  # 11:30 IST
    old_death = {"id": "wk-d", "kind": "death", "category": "death", "fame": 300_000, "date": "2026-10-06",
                 "views": 300_000, "traffic": 0, "news_at": None}
    ready, notes = plan.lineup([old_death], at)
    assert ready == [] and any(n.startswith("drop wk-d:") for n in notes)
    # Still trending live: in Google Trends, or a lead headline under a day old.
    for live in ({"traffic": 50_000}, {"news_at": "2026-10-10T01:00:00+00:00"}):
        ready, _ = plan.lineup([old_death | live], at)
        assert [c["id"] for c in ready] == ["wk-d"]
    yesterday = old_death | {"date": "2026-10-09"}
    ready, _ = plan.lineup([yesterday], at)
    assert [c["id"] for c in ready] == ["wk-d"]


def test_india_first():
    at = utc(9, 14)
    base = {"kind": "incident", "category": "flood", "fame": 200_000, "news_at": "2026-10-09T12:00:00+00:00"}
    india, linked, world = base | {"region": "india"}, base | {"india_link": True}, base | {"region": "world"}
    assert plan.priority(india, at) > plan.priority(linked, at) > plan.priority(world, at)
    assert plan.priority(base | {"region": "india", "fame": 130_000}, at) > plan.priority(world, at)


def test_a_story_without_dates_is_fresh():
    assert plan.age_hours({"kind": "death", "fame": 1}, utc(9, 14)) == 0.0


def test_fresh_story_beats_bigger_stale_one():
    at = utc(9, 14)
    fresh = {"id": "a", "kind": "incident", "category": "protest", "fame": 200_000, "news_at": "2026-10-09T12:00:00+00:00"}
    stale = {"id": "b", "kind": "incident", "category": "flood", "fame": 600_000, "date": "2026-10-06"}
    assert plan.priority(fresh, at) > plan.priority(stale, at)


def test_breaking_lane():
    at = utc(9, 14)
    crash = {"kind": "incident", "category": "aviation", "fame": 900_000, "date": "2026-09-10",
             "news_at": "2026-10-09T13:00:00+00:00"}
    assert plan.age_hours(crash, at) > 600 and not plan.is_breaking(crash, at)
    war = {"kind": "incident", "category": "conflict", "fame": 2_000_000, "news_at": "2026-10-09T13:00:00+00:00"}
    assert not plan.is_breaking(war, at)
    quake = {"kind": "incident", "category": "earthquake", "mag": 7.2, "age_h": 4, "fame": 90_000}
    assert plan.is_breaking(quake, at) and not plan.is_breaking(quake | {"age_h": 30}, at)
    assert plan.is_breaking(quake | {"mag": 6.4, "alert": "orange"}, at)
    assert not plan.is_breaking(quake | {"mag": 6.4, "alert": "yellow"}, at)


def test_trending_quakes_get_their_usgs_magnitude(monkeypatch):
    from desk import usgs

    q = usgs.Quake("us1", 7.1, "20 km N of X", datetime(2026, 10, 9, 3, tzinfo=timezone.utc), 10.0, 20.0, 10.0,
                   "red", 900, "https://earthquake.usgs.gov/earthquakes/eventpage/us1")
    monkeypatch.setattr(usgs, "recent", lambda: [q])
    cands = [{"category": "earthquake", "coords": [10.5, 20.2], "date": "2026-10-09"},
             {"category": "earthquake", "coords": [-30, 100], "date": "2026-10-09"}]
    assert plan._quake_facts(cands) == []
    assert cands[0]["mag"] == 7.1 and cands[0]["alert"] == "red" and "mag" not in cands[1]


def test_ledger_skip_marks_done(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    assert not ledger.is_done("wk-x")
    ledger.skip("wk-x", "gate: test")
    assert ledger.is_done("wk-x")


@pytest.mark.parametrize("title,cat", [
    ("2026 Erie shooting", "attack"), ("2026 anti-CEC protests", "protest"), ("Flydubai Flight 1073", None),
    ("2026 Panama earthquake", "earthquake"), ("2026 Hyderabad building collapse", "disaster"),
    ("Cyclone Montha (2026)", "cyclone"), ("2026 Delhi riots", None), ("2026 Bihar Legislative Assembly election", None),
    ("2019 Kerala floods", None), ("October 2026 King Khalid International Airport attack", "attack"),
    ("Tiger attack", None), ("Strictly Come Dancing series 24", None), ("2026 FIFA World Cup", None),
])
def test_fresh_event_articles_are_recognised_by_their_title(title, cat):
    assert trends.title_kind(title, date(2026, 10, 11)) == cat


def test_a_headline_resolves_to_the_event_article_not_its_city(monkeypatch):
    hits = [{"title": "Erie, Pennsylvania", "timestamp": "2026-10-11T05:00:00Z"},
            {"title": "2026 Erie shooting", "timestamp": "2026-10-11T06:00:00Z"},
            {"title": "Erie County", "timestamp": "2020-01-01T00:00:00Z"}]
    monkeypatch.setattr(news.net, "get_json", lambda *a, **k: {"query": {"search": hits}})
    now = utc(11, 7)
    assert news.match("Shooting leaves 9 dead including suspect in Erie, Pennsylvania", now) == "2026 Erie shooting"
    assert news.match("Erie mayor opens new library", now) == "Erie, Pennsylvania"


def test_radar_keeps_a_fresh_article_wikidata_does_not_know_yet(monkeypatch):
    hits = {"2026 Erie shooting": {"views": 0, "traffic": 0, "via": ["google-news:x"], "news": 125_000,
                                   "news_at": "2026-10-11T03:00:00+00:00", "headlines": ["9 dead in Erie"],
                                   "geos": {"US"}},
            "Happy Days": {"views": 0, "traffic": 0, "via": ["google-news:y"], "news": 125_000}}
    monkeypatch.setattr(trends, "_signals", lambda: (hits, []))
    monkeypatch.setattr(trends.wiki, "page_info", lambda titles: {t: {"title": t, "qid": None if "Erie" in t else "Q1",
                                                                       "lat": None, "lon": None, "unlinked": "Erie" in t}
                                                                   for t in titles})
    monkeypatch.setattr(trends.wiki, "classify", lambda qids: {q: set() for q in qids})
    monkeypatch.setattr(trends.wiki, "entities", lambda qids: {q: {} for q in qids})
    monkeypatch.setattr(trends.wiki, "created", lambda title: datetime(2026, 10, 11, 4, tzinfo=timezone.utc))
    out = trends.radar(date(2026, 10, 11))["candidates"]
    assert [(c["id"], c["category"], c["qid"], c["date"]) for c in out] == [
        ("wp-2026_Erie_shooting", "attack", None, "2026-10-11")]


PORTAL = """{{Current events|year=2026|month=10|day=10}}
'''Armed conflicts and attacks'''
*[[Houthi–Saudi conflict]]
**[[October 2026 King Khalid International Airport attack]]
***Twelve people are killed in a [[Houthis|Houthi]] missile attack on [[King Khalid International Airport]].
'''Law and crime'''
*[[Censorship in India]]
**[[2026 anti-CEC protests]]
***Police detain protest leaders in [[New Delhi]].
*[[2026 Erie shooting|Erie shooting]]
"""


def test_current_events_lists_story_articles_not_the_links_in_summaries(monkeypatch):
    from desk import wiki
    monkeypatch.setattr(wiki.net, "get_json", lambda *a, **k: {"parse": {"wikitext": PORTAL}})
    assert wiki.current_events(date(2026, 10, 10)) == [
        ("Houthi–Saudi conflict", False), ("October 2026 King Khalid International Airport attack", False),
        ("Censorship in India", True), ("2026 anti-CEC protests", True), ("2026 Erie shooting", False)]
    monkeypatch.setattr(wiki.net, "get_json", lambda *a, **k: {"error": {"code": "missingtitle"}})
    assert wiki.current_events(date(2026, 10, 12)) == []


def test_a_listed_protest_is_news_and_an_india_story(monkeypatch):
    monkeypatch.setattr(trends.wiki, "top_articles", lambda: (date(2026, 10, 10), []))
    monkeypatch.setattr(trends, "google_trends", lambda geo: [])
    monkeypatch.setattr(trends.news, "signals", lambda **k: ({}, []))
    monkeypatch.setattr(trends, "story_pool", lambda today, errors: [])
    monkeypatch.setattr(trends, "gdacs_hits", lambda today: [])
    monkeypatch.setattr(trends.wiki, "current_events",
                        lambda day: [("2026 anti-CEC protests", True)] if day == date(2026, 10, 11) else [])
    monkeypatch.setattr(trends, "datetime", type("D", (datetime,), {"now": staticmethod(lambda tz=None: utc(11, 7))}))
    monkeypatch.setattr(trends.wiki, "page_info", lambda titles: {t: {"title": t, "qid": None, "lat": None, "lon": None,
                                                                      "unlinked": True} for t in titles})
    monkeypatch.setattr(trends.wiki, "classify", lambda qids: {})
    monkeypatch.setattr(trends.wiki, "entities", lambda qids: {})
    out = trends.radar(date(2026, 10, 11))["candidates"]
    assert [(c["id"], c["category"], c["region"], c["fame"]) for c in out] == [
        ("wp-2026_anti-CEC_protests", "protest", "india", trends.PORTAL_FAME)]


def test_a_story_told_before_wikidata_knew_it_does_not_come_back(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    ledger.skip(trends.article_id("2026 Erie shooting"), "published as wp-")
    cand = {"id": "wk-Q9", "qid": "Q9", "title": "2026 Erie shooting", "category": "attack", "fame": 1}
    monkeypatch.setattr(plan.trends, "radar", lambda: {"candidates": [cand], "errors": []})
    monkeypatch.setattr(plan, "_quake_facts", lambda cands: [])
    monkeypatch.setattr(plan.orbitwire, "fetch", lambda: {"published": [], "candidates": []})
    assert plan.watch(save=False)["candidates"] == []


def test_a_remake_comes_back_under_a_new_id_until_its_old_video_is_replaced(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(plan, "REMAKES", tmp_path / "remakes")
    (tmp_path / "remakes").mkdir()
    (tmp_path / "remakes" / "tiger.json").write_text(json.dumps(
        {"story": "nw-20261018-tiger-shroff-attack", "replaces": "OLD", "until": "2099-01-01T00:00:00+00:00"}))
    ledger.record_publish({"id": "nw-20261018-tiger-shroff-attack", "published_at": "2026-10-20T02:08:25+00:00",
                           "video_id": "OLD"})
    shifted = {"id": "nw-20261019-tiger-shroff-attack", "title": "Tiger Shroff attack", "category": "attack",
               "kind": "incident", "fame": 1}
    same = shifted | {"id": "nw-20261018-tiger-shroff-attack"}
    other = {"id": "nw-20261019-pune-fire", "title": "Pune fire", "category": "fire", "kind": "incident", "fame": 1}
    monkeypatch.setattr(plan, "_quake_facts", lambda cands: [])
    monkeypatch.setattr(plan.orbitwire, "fetch", lambda: {"published": [], "candidates": []})

    for cand, new_id in ((shifted, "nw-20261019-tiger-shroff-attack"), (same, "nw-20261018-tiger-shroff-attack-r2")):
        monkeypatch.setattr(plan.trends, "radar", lambda c=cand: {"candidates": [c, other], "errors": []})
        found = plan.watch(save=False)["candidates"]
        again = [c for c in found if c.get("replaces")]
        assert [(c["id"], c["replaces"], c["remake_of"]) for c in again] == \
            [(new_id, "OLD", "nw-20261018-tiger-shroff-attack")]
        ready, _ = plan.lineup(found, utc(20, 8))
        assert ready[0]["id"] == new_id

    ledger.record_publish({"id": "nw-20261019-tiger-shroff-attack", "published_at": "2026-10-20T08:00:00+00:00",
                           "replaces": "OLD"})
    assert plan.remakes() == []
    monkeypatch.setattr(plan.trends, "radar", lambda: {"candidates": [shifted], "errors": []})
    assert plan.watch(save=False)["candidates"] == []


def test_a_case_comes_back_angle_by_angle_until_each_is_on_the_channel(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(plan, "CASES", tmp_path / "cases")
    monkeypatch.setattr(plan, "REMAKES", tmp_path / "remakes")
    (tmp_path / "cases").mkdir()
    (tmp_path / "remakes").mkdir()
    report = {"url": "u9", "owner": "NDTV", "title": "Jackie Shroff on the firing"}
    (tmp_path / "cases" / "tiger.json").write_text(json.dumps(
        {"name": "tiger", "story": "nw-20261019-tiger-shroff-attack", "until": "2099-01-01T00:00:00+00:00",
         "region": "india", "status": "All three caught.", "names_ok": ["Tiger Shroff"], "angles": [
             {"key": "family", "focus": "The family.", "reports": [report], "names_ok": ["Jackie Shroff"],
              "words": ["Jackie"]},
             {"key": "probe", "focus": "The probe.", "reports": [report], "arrests": True}]}))
    ledger.record_publish({"id": "nw-20261019-tiger-shroff-attack", "published_at": "2026-10-19T08:01:00+00:00",
                           "video_id": "NEW", "title": "पहला"})
    cand = {"id": "nw-20261020-tiger-shroff-attack", "title": "Tiger Shroff attack", "category": "attack",
            "kind": "incident", "fame": 1, "top_score": 1.15}
    monkeypatch.setattr(plan.trends, "radar", lambda: {"candidates": [cand], "errors": []})
    monkeypatch.setattr(plan, "_quake_facts", lambda cands: [])
    monkeypatch.setattr(plan.orbitwire, "fetch", lambda: {"published": [], "candidates": []})
    found = plan.watch(save=False)["candidates"]
    angles = [c for c in found if c.get("case")]
    assert [c["id"] for c in angles] == ["nw-20261019-tiger-shroff-attack-family",
                                         "nw-20261019-tiger-shroff-attack-probe"]
    family = angles[0]
    assert family["names_ok"] == ["Tiger Shroff", "Jackie Shroff"] and family["earlier"] == ["पहला"]
    assert family["reports"] == [report] and not family["arrests"] and angles[1]["arrests"]
    assert family["case_words"] == ["Jackie"] and angles[1]["case_words"] == []
    assert family["region"] == "india" and family["case_status"] == "All three caught."
    ready, _ = plan.lineup(found + [{"id": "wk-Q1", "title": "x", "fame": 10 ** 9}], utc(20, 12))
    assert ready[0]["id"] == family["id"]
    ledger.record_publish({"id": family["id"], "published_at": "2026-10-19T10:00:00+00:00", "video_id": "F",
                           "case": "tiger", "title": "परिवार"})
    later = plan.watch(save=False)["candidates"]
    assert [c["id"] for c in later] == ["nw-20261019-tiger-shroff-attack-probe"]
    assert later[0]["earlier"] == ["पहला", "परिवार"]
    # Off the radar and days old, the case still runs its angles from the candidate its file keeps.
    spec = json.loads((tmp_path / "cases" / "tiger.json").read_text())
    (tmp_path / "cases" / "tiger.json").write_text(json.dumps(spec | {"never": ["Bishnoi"], "cand": cand | {
        "id": "nw-20261019-tiger-shroff-attack", "news_at": "2026-10-19T08:00:00+00:00",
        "headlines": ["How the Bishnoi gang plays it", "Tiger Shroff shooters caught in Kota"]}}))
    monkeypatch.setattr(plan.trends, "radar", lambda: {"candidates": [], "errors": []})
    off = plan.watch(save=False)["candidates"]
    assert [c["id"] for c in off] == ["nw-20261019-tiger-shroff-attack-probe"]
    assert off[0]["headlines"] == ["Tiger Shroff shooters caught in Kota"] and off[0]["never"] == ["Bishnoi"]
    ready, notes = plan.lineup(off, utc(22, 12))
    assert [c["id"] for c in ready] == ["nw-20261019-tiger-shroff-attack-probe"], notes
    # Within CASE_GAP of the case's last Short, neither an angle nor a follow-up part of its story comes up.
    monkeypatch.setattr(plan.trends, "radar", lambda: {"candidates": [cand], "errors": []})
    just = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
    ledger.record_publish({"id": "nw-20261019-tiger-shroff-attack-chase", "published_at": just, "video_id": "C",
                           "case": "tiger", "title": "पीछा"})
    assert plan.watch(save=False)["candidates"] == []


def test_a_case_angle_is_made_again_once_and_replaces_its_old_short(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(plan, "CASES", tmp_path / "cases")
    monkeypatch.setattr(plan, "REMAKES", tmp_path / "remakes")
    (tmp_path / "cases").mkdir()
    (tmp_path / "remakes").mkdir()
    cand = {"id": "nw-20261019-tiger-shroff-attack", "title": "Tiger Shroff attack", "category": "attack",
            "kind": "incident", "fame": 1, "top_score": 1.15, "news_at": "2026-10-19T08:00:00+00:00"}
    angle = {"key": "family", "focus": "The family.", "reports": [{"url": "u9", "owner": "NDTV"}]}
    (tmp_path / "cases" / "tiger.json").write_text(json.dumps(
        {"name": "tiger", "story": cand["id"], "until": "2099-01-01T00:00:00+00:00", "cand": cand,
         "angles": [angle | {"key": "family-r2", "replaces": "OLD", "draft": {"title": "t"}}, angle]}))
    ledger.record_publish({"id": cand["id"] + "-family", "published_at": "2026-10-19T10:00:00+00:00",
                           "video_id": "OLD", "case": "tiger", "title": "जय किशन"})
    monkeypatch.setattr(plan.trends, "radar", lambda: {"candidates": [], "errors": []})
    monkeypatch.setattr(plan, "_quake_facts", lambda cands: [])
    monkeypatch.setattr(plan.orbitwire, "fetch", lambda: {"published": [], "candidates": []})
    again = plan.watch(save=False)["candidates"]
    assert [(c["id"], c.get("replaces"), c.get("remake_of")) for c in again] == [
        (cand["id"] + "-family-r2", "OLD", cand["id"] + "-family")]
    assert again[0]["draft"] == {"title": "t"}
    ledger.record_publish({"id": cand["id"] + "-family-r3", "published_at": "2026-10-19T12:00:00+00:00",
                           "video_id": "NEW", "case": "tiger", "title": "जैकी श्रॉफ", "replaced": "OLD"})
    assert plan.watch(save=False)["candidates"] == []


def test_an_ongoing_story_is_not_repeated_across_a_week_boundary_or_a_series():
    sunday = trends.story_id("Q1", "protest", date(2026, 10, 11))
    monday = trends.story_id("Q1", "protest", date(2026, 10, 12))
    assert sunday != monday and sunday.startswith("wk-Q1-2026w")
    assert trends.story_id("Q1", "flood", date(2026, 10, 11)) == "wk-Q1"
    rows = [{"id": "wk-Q1-p1", "published_at": "2026-10-11T23:00:00+00:00"}]
    at = datetime(2026, 10, 12, 1, 7, tzinfo=timezone.utc)
    assert plan.cooling({"qid": "Q1", "category": "protest", "id": monday}, at, rows)
    assert not plan.cooling({"qid": "Q11", "category": "protest", "id": "wk-Q11-2026w42"}, at, rows)
    assert not plan.cooling({"qid": "Q1", "category": "protest"}, datetime(2026, 10, 18, 2, tzinfo=timezone.utc), rows)


def test_ended_or_old_movements_are_not_news():
    def ent(**claims):
        return {"claims": {p: [{"mainsnak": {"datavalue": {"value": {"time": v}}}}] for p, v in claims.items()}}
    today = date(2026, 10, 9)
    assert trends.is_current(ent(P571="+2026-05-00T00:00:00Z"), "movement", today)
    assert not trends.is_current(ent(P580="+2026-06-06T00:00:00Z", P582="+2026-07-25T00:00:00Z"), "protest", today)
    assert not trends.is_current(ent(P580="+2020-08-09T00:00:00Z"), "protest", today)
    assert not trends.is_current(ent(), "movement", today)
    assert not trends.is_current(ent(), "conflict", today)
    assert trends.is_current(ent(P580="+2026-02-28T00:00:00Z"), "conflict", today)
    assert trends.is_current(ent(), "protest", today)


def test_india_link():
    india = {"claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q668"}}}}]}}
    abroad = {"claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q30"}}}}]}}
    assert trends.region(india, set()) == "india"
    assert trends.india_link(abroad, {"IN"}) and not trends.india_link(abroad, {"US"})
    assert trends.india_link(abroad, {"US"}, hindi_news=1)


def test_feed_dates_without_a_zone_do_not_break_the_feed(monkeypatch):
    rss = ("<rss><channel><item><title>Quake hits city - Outlet</title><pubDate>Fri, 09 Oct 2026 10:00:00 -0000"
           "</pubDate></item><item><title>No outlet here</title><pubDate>Fri, 09 Oct 2026 11:00:00 GMT</pubDate>"
           "</item></channel></rss>")
    monkeypatch.setattr(news.net, "get", lambda *a, **k: rss)
    items = news.headlines("IN", utc(9, 12))
    assert [i["outlet"] for i in items] == ["Outlet", ""] and all(i["at"].endswith("+00:00") for i in items)


def test_hindi_google_news_is_watched(monkeypatch):
    assert "hl=hi&gl=IN&ceid=IN:hi" in news.FEEDS["IN-hi"]
    rss = ("<rss><channel><item><title>ब्रेकिंग: वाराणसी में बाढ़ से हालात गंभीर - अमर उजाला</title>"
           "<pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>")
    monkeypatch.setattr(news.net, "get", lambda *a, **k: rss)
    items = news.headlines("IN-hi", utc(9, 12))
    assert items[0]["title"] == "वाराणसी में बाढ़ से हालात गंभीर" and items[0]["outlet"] == "अमर उजाला"


def test_india_trends_come_first():
    assert trends.GEOS[0] == "IN"


def test_a_case_has_three_angles_a_day_and_six_in_all_and_the_rest_wait(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(plan, "CASES", tmp_path / "cases")
    (tmp_path / "cases").mkdir()
    story = "nw-20261019-tiger-shroff-attack"
    cand = {"id": story, "title": "Tiger Shroff attack", "category": "attack", "kind": "incident", "fame": 1,
            "top_score": 1.15, "news_at": "2026-10-19T08:00:00+00:00"}
    keys = [f"a{i}" for i in range(9)]
    angles = [{"key": k, "focus": k, "reports": [{"url": "u", "owner": "NDTV"}]} for k in keys]
    angles.append({"key": "a0-r2", "focus": "again", "reports": [{"url": "u", "owner": "NDTV"}], "replaces": "V0"})
    (tmp_path / "cases" / "tiger.json").write_text(json.dumps(
        {"name": "tiger", "story": story, "until": "2099-01-01T00:00:00+00:00", "cand": cand, "angles": angles}))

    def told(i, at, **extra):
        ledger.record_publish({"id": f"{story}-a{i}", "published_at": at, "video_id": f"V{i}", "case": "tiger",
                               "title": f"t{i}"} | extra)

    def waiting(at):
        return {c["angle"]: c.get("case_wait") for c in plan.angles_of(cand, plan.cases(at), ledger.published(), at)}

    at = utc(20, 12)  # 17:30 IST on 20 October
    for i, hour in enumerate((3, 5, 7)):
        told(i, f"2026-10-20T{hour:02d}:00:00+00:00")
    held = waiting(at)
    assert all("3 of the case's angles today" in held[k] for k in keys[3:]) and "today" in held["a0-r2"]
    ready, notes = plan.lineup(plan.angles_of(cand, plan.cases(at), ledger.published(), at), at)
    assert ready == [] and any(n.startswith(f"hold {story}-a3: 3 of the case's angles today") for n in notes)
    # A retired angle is off the channel: its day's slot is free again.
    ledger.update_published("V2", {"privacy": "private", "retired_at": "2026-10-20T09:00:00+00:00"})
    assert waiting(at)["a3"] is None
    # Six on the channel in all: no new angle the next day, but an angle made again replaces its old Short.
    for i, hour in ((3, 1), (4, 2), (5, 3), (6, 4)):
        told(i, f"2026-10-19T{hour:02d}:00:00+00:00")
    nxt = utc(21, 13)
    held = waiting(nxt)
    assert "6 of the case's Shorts on the channel" in held["a7"] and held["a0-r2"] is None
    monkeypatch.setattr(plan, "CASE_MAX_TOTAL", 7)
    assert waiting(nxt)["a7"] is None


def test_ad_suitability_ranks_crime_down_and_explainers_up_but_never_breaking_news():
    at = utc(21, 8)
    base = {"kind": "explainer", "category": "news", "fame": 1000, "news_at": at.isoformat()}
    firing = base | {"id": "kh-f", "title": "Tiger Shroff", "story": "Tiger Shroff survives shooting attempt"}
    bail = base | {"id": "kh-b", "title": "राहुल गांधी", "hindi_headlines": ["मानहानि केस में जमानत मिली"]}
    petrol = base | {"id": "kh-p", "title": "Petrol", "story": "Petrol and diesel prices cut by Rs 2"}
    gold = base | {"id": "kh-g", "title": "सोना", "hindi_headlines": ["सोने के दाम में बड़ी गिरावट"]}
    plain = base | {"id": "kh-n", "title": "Shashi Tharoor", "story": "Shashi Tharoor amid row over Rahul Gandhi"}
    assert [plan.ad_class(c) for c in (firing, bail, petrol, gold, plain)] == \
        ["sensitive", "sensitive", "friendly", "friendly", None]
    # Sensitive wins; a death is not crime unless it was an accident; cardiac arrest is no arrest.
    assert plan.ad_class(base | {"story": "GST council meets after the court verdict"}) == "sensitive"
    assert plan.ad_class({"category": "death", "title": "Lata Mangeshkar", "story": "dies of cardiac arrest"}) is None
    assert plan.ad_class({"category": "death", "story": "actor dies in a road accident"}) == "sensitive"
    assert plan.ad_class({"title": "सोनाक्षी सिन्हा", "hindi_headlines": ["अस्पताल में भर्ती"]}) is None
    assert plan.ad_class({"category": "attack", "title": "x"}) == "sensitive"
    # A Hindi stem inside another word is not that word; words that fit any story need their pairing word.
    for text in ("मैच के दौरान खिलाड़ी घायल", "दामाद ने कहा", "नियमित जांच", "दिल का दौरा पड़ने से निधन",
                 "कीमती तोहफा", "Kohli talks about retirement", "Salman Khan visits Lilavati", "Stock market crash"):
        assert plan.ad_class({"title": text}) is None, text
    for text in ("मोदी का जापान दौरा", "प्रधानमंत्री के दौरे से पहले", "नए नियमों से", "दामों में बढ़ोतरी",
                 "Modi's state visit to Japan", "India-US trade talks", "Petrol price hike"):
        assert plan.ad_class({"title": text}) == "friendly", text
    assert plan.ad_class({"title": "Bus crash kills five"}) == "sensitive"
    assert plan.ad_factor(firing, at) == plan.AD_SENSITIVE < 1 < plan.AD_FRIENDLY == plan.ad_factor(petrol, at)
    assert plan.ad_factor(plain, at) == 1.0
    assert plan.priority(firing, at) < plan.priority(plain, at) < plan.priority(petrol, at)
    # Breaking news is told whatever it is about.
    loud = firing | {"kind": "incident", "fame": 500_000, "news_at": (at - timedelta(hours=1)).isoformat()}
    assert plan.is_breaking(loud, at) and plan.ad_factor(loud, at) == 1.0
    note = plan.ad_note([firing, petrol, plain, loud], at)
    assert note.startswith("ad-suitability x0.8") and "kh-f" in note and "kh-p" in note and "kh-n" not in note
    assert plan.ad_note([plain], at) is None
