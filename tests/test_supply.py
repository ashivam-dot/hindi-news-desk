"""Story supply (2026-10-13): young articles wait instead of being given up, headlines and searches find fresh story
articles by their words, low Trends traffic counts, GDACS alerts lead to their disaster's article, Orbitwire's
article-only stories are recognised, and a story short of its own photos fills in with photos of its places."""
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from desk import cli, gdacs, ledger, media, news, orbitwire, plan, trends, writer

NOW = datetime(2026, 10, 13, 8, tzinfo=timezone.utc)


def test_a_moved_article_keeps_its_wikidata_item(monkeypatch):
    from desk import wiki

    old, new = "October 2026 attacks on Saudi Arabia airports", "October 2026 attacks on Saudi airports"
    calls = []

    def get_json(url, params):
        calls.append(url)
        if url == wiki.API:
            return {"query": {"redirects": [{"from": old, "to": new}],
                              "pages": [{"title": new}, {"title": "2026 Aubagne school shooting"},
                                        {"title": "Mike Ditka", "pageprops": {"wikibase_item": "Q1355840"}}]}}
        assert params["titles"] == f"{new}|2026 Aubagne school shooting"
        return {"entities": {"Q141695384": {"sitelinks": {"enwiki": {"title": new}}}, "-1": {"missing": ""}}}

    monkeypatch.setattr(wiki.net, "get_json", get_json)
    info = wiki.page_info([old, "2026 Aubagne school shooting", "Mike Ditka"])
    assert info[old]["qid"] == info[new]["qid"] == "Q141695384" and info[old]["title"] == new
    assert info["2026 Aubagne school shooting"]["qid"] is None and info["2026 Aubagne school shooting"]["unlinked"]
    assert info["Mike Ditka"]["qid"] == "Q1355840" and not info[new]["unlinked"]
    assert calls == [wiki.API, wiki.WD_API]

    def wikidata_down(url, params):
        if url == wiki.API:
            return get_json(url, params)
        raise RuntimeError("wikidata: HTTP 429")

    monkeypatch.setattr(wiki.net, "get_json", wikidata_down)
    info = wiki.page_info([old, "2026 Aubagne school shooting"])
    assert info[old]["qid"] is None and not info[old]["unlinked"] and not info["2026 Aubagne school shooting"]["unlinked"]


def test_a_young_article_waits_and_a_story_given_up_only_for_that_comes_back(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    young = "gate: the article is under 6 hours old; facts may still move"
    ledger.skip("wp-2026_Aubagne_school_shooting", "gave up after 6 tries: " + young)
    ledger.skip("wk-Q1", "gave up after 6 tries: gate: only 1 usable photos of X on Wikimedia Commons (want 3)")
    assert not ledger.is_done("wp-2026_Aubagne_school_shooting") and ledger.is_done("wk-Q1")
    ledger.save("retries", {"wk-Q2": {"count": 6, "reason": young, "at": "x"}})
    assert ledger.retry("wk-Q2", "gate: only 2 usable photos of Y on Wikimedia Commons (want 3)")
    assert ledger.load("retries", {})["wk-Q2"]["count"] == 1


def test_a_run_waits_for_young_articles_without_counting_a_try_or_taking_a_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(cli, "WORK", tmp_path)
    from desk import voice
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(cli.config, "channel_id_ready", lambda: True)
    monkeypatch.setattr(ledger, "set_identity", lambda: None)
    monkeypatch.setattr(cli.learn, "refresh", lambda: None)
    monkeypatch.setattr(cli, "_advisory", lambda h, d: None)
    cands = [{"id": f"wp-young-{i}", "kind": "incident", "fame": 9} for i in range(4)] + \
            [{"id": "wk-Q5", "kind": "incident", "fame": 1}]
    monkeypatch.setattr(plan, "watch", lambda save=True: {"candidates": cands, "trending": cands, "notes": []})
    monkeypatch.setattr(plan, "lineup", lambda c: (c, []))
    tried = []

    def prepare(c):
        tried.append(c["id"])
        raise ValueError("gate: the article is under 6 hours old; facts may still move (ready in 2.0 h)"
                         if c["id"].startswith("wp-young") else "gate: only 1 usable photos of X (want 3)")
    monkeypatch.setattr(cli, "prepare", prepare)
    health = cli.run()
    assert tried[-1] == "wk-Q5" and sum(s.startswith("wait wp-young") for s in health["steps"]) == 4
    assert set(ledger.load("retries", {})) == {"wk-Q5"} and ledger.load("skipped", {}) == {}


POOL = [news.pool_item("2026 Aubagne school shooting"), news.pool_item("RJ Mitte", person=True, hi="आरजे मिट्टे"),
        news.pool_item("October 2026 attacks on Saudi Arabia airports"), news.pool_item("2026 Budhi Gandaki flood"),
        news.pool_item("Mike Love", person=True)]


@pytest.mark.parametrize("headline, title", [
    ("RJ Mitte, 'Breaking Bad' actor and disability rights champion, dies at 34", "RJ Mitte"),
    ("ब्रेकिंग बैड के अभिनेता आरजे मिट्टे का 34 वर्ष की उम्र में निधन", "RJ Mitte"),
    ("Aubagne school shooting: teenager held after teacher wounded", "2026 Aubagne school shooting"),
    ("Saudi warning system stayed silent before deadly airport attacks",
     "October 2026 attacks on Saudi Arabia airports"),
    ("Budhi Gandaki flood sweeps away bridges in Gorkha", "2026 Budhi Gandaki flood"),
    ("Teen wounds headmaster and teacher after opening fire at French school", None),  # names no place
    ("Aubagne mayor opens a new library", None),  # one word is not enough
    ("A love song for Mike's birthday", None),  # a person needs their whole name
    ("Flash flood hits northern Nepal", None),
])
def test_headlines_find_fresh_story_articles_by_their_words(headline, title):
    assert news.reverse(headline, POOL) == title


def test_an_ambiguous_headline_matches_nothing():
    pool = [news.pool_item("2026 Gorkha flood"), news.pool_item("2026 Gorkha landslide")]
    assert news.reverse("Gorkha disaster: flood and landslide hit Gorkha district", pool) is None


def test_a_headline_prefers_the_pool_article_over_an_old_search_hit(monkeypatch):
    items = [{"title": "Saudi warning system stayed silent before deadly airport attacks", "outlet": "X", "outlets": 5,
              "at": "2026-10-13T07:00:00+00:00", "feed": "US"},
             {"title": "आरजे मिट्टे का निधन", "outlet": "Y", "outlets": 2, "at": "2026-10-13T06:00:00+00:00",
              "feed": "IN-hi"}]
    monkeypatch.setattr(news, "FEEDS", {"US": "u", "IN-hi": "h"})
    monkeypatch.setattr(news, "headlines", lambda feed, now=None: [i for i in items if i["feed"] == feed])
    monkeypatch.setattr(news, "match", lambda h, now=None, lang="en": "Crocus City Hall attack" if lang == "en" else None)
    monkeypatch.setattr(news.wiki, "hi_to_en", lambda titles: {})
    hits, errors = news.signals(NOW, pool=POOL)
    assert set(hits) == {"October 2026 attacks on Saudi Arabia airports", "RJ Mitte"} and errors == []
    assert hits["RJ Mitte"]["hindi_news"] == 1 and hits["RJ Mitte"]["hindi_headlines"] == ["आरजे मिट्टे का निधन"]


def test_a_hindi_world_section_is_not_an_india_signal(monkeypatch):
    items = [{"title": "आरजे मिट्टे का निधन", "outlet": "Y", "outlets": 1, "at": "2026-10-13T06:00:00+00:00",
              "feed": "IN-hi-world"}]
    monkeypatch.setattr(news, "FEEDS", {"IN-hi-world": "w"})
    monkeypatch.setattr(news, "headlines", lambda feed, now=None: items)
    monkeypatch.setattr(news, "match", lambda *a, **k: None)
    monkeypatch.setattr(news.wiki, "hi_to_en", lambda titles: {})
    hits, _ = news.signals(NOW, pool=POOL)
    assert hits["RJ Mitte"]["geos"] == {"world"} and hits["RJ Mitte"]["hindi_news"] == 1


def _quiet_sources(monkeypatch, pool=()):
    monkeypatch.setattr(trends.wiki, "top_articles", lambda: (date(2026, 10, 12), []))
    monkeypatch.setattr(trends.wiki, "current_events", lambda day: [])
    monkeypatch.setattr(trends.news, "signals", lambda **k: ({}, []))
    monkeypatch.setattr(trends, "story_pool", lambda today, errors: list(pool))
    monkeypatch.setattr(trends, "gdacs_hits", lambda today: [])


def test_any_listed_search_counts_and_its_news_items_find_the_story(monkeypatch):
    _quiet_sources(monkeypatch, [news.pool_item("RJ Mitte", person=True)])
    monkeypatch.setattr(trends, "google_trends", lambda geo: [
        {"query": "breaking bad actor", "traffic": 200, "geo": geo,
         "news": ["RJ Mitte, Breaking Bad actor, dies at 34"]}] if geo == "US" else [])
    monkeypatch.setattr(trends, "_resolve", lambda q: pytest.fail("searched although a news item named the story"))
    hits, _ = trends._signals()
    assert hits["RJ Mitte"]["traffic"] == 200 and hits["RJ Mitte"]["geos"] == {"US"}


def test_deep_most_read_keeps_only_deaths_and_fresh_events(monkeypatch):
    _quiet_sources(monkeypatch, [news.pool_item("Madhu Kambikar", person=True)])
    top = [(f"Article {i}", 50_000 - i) for i in range(trends.TOP_N)] + [
        ("Some Footballer", 9000), ("Madhu Kambikar", 8000), ("2026 Kerala boat accident", 7000)]
    monkeypatch.setattr(trends.wiki, "top_articles", lambda: (date(2026, 10, 12), top))
    monkeypatch.setattr(trends, "google_trends", lambda geo: [])
    monkeypatch.setattr(trends.wiki, "page_info", lambda titles: {})
    hits, _ = trends._signals()
    assert "Madhu Kambikar" in hits and "2026 Kerala boat accident" in hits and "Some Footballer" not in hits


@pytest.mark.parametrize("alert, subject", [
    ({"kind": "TC", "title": "Orange notification for tropical cyclone SIMON-26. Population affected"},
     ("Simon", "cyclone")),
    ({"kind": "TC", "title": "Green notification for tropical cyclone TWENTYEIGHT-26."}, (None, "cyclone")),
    ({"kind": "VO", "title": "Volcanic eruption is on going for Kanlaon in Philippines"}, ("Kanlaon", "volcano")),
    ({"kind": "EQ", "title": "Orange earthquake (Magnitude 7.7M, Depth:12.647km) in Panama 09/10/2026 17:56 UTC",
      "country": ""}, ("Panama", "earthquake")),
    ({"kind": "FL", "title": "Red flood alert in India", "country": "India"}, ("India", "flood")),
])
def test_gdacs_alerts_name_their_disaster(alert, subject):
    assert gdacs.subject(alert) == subject


def test_a_gdacs_alert_leads_to_its_disaster_article(monkeypatch):
    monkeypatch.setattr(gdacs, "alerts", lambda: [
        {"id": "gdacs-TC-1", "kind": "TC", "level": "Orange", "published": "2026-10-12T02:00:00+00:00",
         "title": "Orange notification for tropical cyclone MONTHA-26."},
        {"id": "gdacs-TC-2", "kind": "TC", "level": "Red", "published": "2026-10-01T02:00:00+00:00",
         "title": "Red notification for tropical cyclone OLDIE-26."}])
    searched = []
    monkeypatch.setattr(trends.net, "get_json", lambda url, params: searched.append(params["srsearch"]) or {
        "query": {"search": [{"title": "Montha (film)"}, {"title": "Cyclone Montha (2026)"}]}})
    assert [(t, a["id"]) for t, a in trends.gdacs_hits(date(2026, 10, 13))] == [("Cyclone Montha (2026)", "gdacs-TC-1")]
    assert searched == ["2026 Montha cyclone"]


def test_orbitwire_stories_told_before_wikidata_knew_them_are_shared():
    s = {"published": [{"id": "wp-2026_Aubagne_school_shooting", "published_at": "2026-10-12T20:00:00+00:00"},
                       {"id": "wk-Q77", "article": "2026 Erie shooting", "published_at": "2026-10-12T20:00:00+00:00"}],
         "candidates": {"candidates": [{"id": "wp-2026_French_supermarket_cyber_attack", "qid": None,
                                        "title": "2026 French supermarket cyber attack"}]}}
    assert orbitwire.overlap(None, s, NOW, title="2026 Aubagne school shooting")["status"] == "published"
    assert orbitwire.overlap("Q9", s, NOW, title="2026 Aubagne school shooting")["status"] == "published"
    assert orbitwire.overlap(None, s, NOW, story_id="wp-2026_Erie_shooting")["orbitwire_id"] == "wk-Q77"
    assert orbitwire.overlap(None, s, NOW, title="2026 French supermarket cyber attack") is None
    assert orbitwire.overlap(None, s, NOW, title="2026 Gorkha flood") is None


def test_low_traffic_floor():
    assert trends.TRENDS_MIN_TRAFFIC <= 100 and trends.title_kind("2026 ISSF World Shooting Championships",
                                                                  date(2026, 10, 13)) is None


def _photo(name, origin="article"):
    return media.Photo(file=f"File:{name}.jpg", url="u", page=f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
                       width=1600, height=1200, author="A", license="CC BY 4.0", description=name, date="",
                       origin=origin)


@pytest.fixture
def photos(monkeypatch, tmp_path):
    """Own photos and context photos by name; a name containing 'face' has a big face, 'tiny' a small one."""
    shelf = {"own": [], "context": []}
    monkeypatch.setattr(media, "find", lambda *a, **k: shelf["own"])
    monkeypatch.setattr(media, "context", lambda qids, limit=6, exclude=None: [p for p in shelf["context"]
                                                                               if p.file not in (exclude or set())])

    def download(found, folder):
        for p in found:
            p.path = str(Path(folder) / Path(p.file).name)
        return found
    monkeypatch.setattr(media, "download", download)
    import cv2
    monkeypatch.setattr(cv2, "imread", lambda path: np.zeros((1000, 1000, 3), np.uint8))
    me = np.ones(128) / np.sqrt(128)

    def detect(img, _calls=[]):
        name = _calls.pop(0) if _calls else ""
        return [{"box": (0, 0, 300, 300), "score": 0.9, "feature": me}] if "face" in name else (
            [{"box": (0, 0, 20, 20), "score": 0.9, "feature": me}] if "tiny" in name else [])
    order = []
    monkeypatch.setattr(writer.faces, "detect", lambda img: detect(img, order))
    return shelf, order, tmp_path


def test_a_tribute_short_of_portraits_fills_in_with_its_places_but_never_other_faces(photos):
    shelf, order, tmp = photos
    shelf["own"] = [_photo("Madhu Kambikar face")]
    shelf["context"] = [_photo("Kolhapur skyline", "related"), _photo("Crowd face at a school", "place"),
                        _photo("Shivaji University tiny", "place")]
    order += ["face", "", "face", "tiny"]
    got = writer.pick_photos("Madhu Kambikar", {}, tmp, person=True, context_qids=["Q1"])
    assert [p["file"] for p in got] == ["File:Madhu Kambikar face.jpg", "File:Kolhapur skyline.jpg",
                                       "File:Shivaji University tiny.jpg"]
    assert got[0]["focus"] and got[1]["focus"] is None


def test_a_persons_own_portraits_go_before_photos_with_strangers(photos, monkeypatch):
    shelf, order, tmp = photos
    shelf["own"] = [_photo("Rahul with students"), _photo("Rahul portrait"), _photo("Rahul at a desk")]
    me, other = np.ones(128) / np.sqrt(128), np.eye(128)[0]
    faces = {"students": [(0, 0, 300, 300, me), (400, 0, 280, 280, other)], "portrait": [(0, 0, 300, 300, me)],
             "desk": [(0, 0, 300, 300, me), (500, 500, 40, 40, other)]}
    calls = iter(["students", "portrait", "desk"])
    monkeypatch.setattr(writer.faces, "detect", lambda img: [
        {"box": f[:4], "score": 0.9, "feature": f[4]} for f in faces[next(calls)]])
    got = writer.pick_photos("Rahul Gandhi", {}, tmp, person=True)
    assert [p["file"] for p in got] == ["File:Rahul portrait.jpg", "File:Rahul at a desk.jpg",
                                       "File:Rahul with students.jpg"]
    assert [p["others"] for p in got] == [0, 0, 1]


def test_no_portrait_means_no_tribute_and_enough_photos_means_no_fill(photos):
    shelf, order, tmp = photos
    shelf["context"] = [_photo("Kolhapur skyline", "related")] * 3
    assert writer.pick_photos("Madhu Kambikar", {}, tmp, person=True, context_qids=["Q1"]) == []
    shelf["own"] = [_photo(f"Flood {i}") for i in range(3)]
    got = writer.pick_photos("2026 Gorkha flood", {}, tmp, person=False, context_qids=["Q1"])
    assert [p["file"] for p in got] == [f"File:Flood {i}.jpg" for i in range(3)]


def test_person_and_incident_context_items():
    claims = {pid: [{"mainsnak": {"datavalue": {"value": {"id": q}}}}] for pid, q in
              (("P19", "Q100"), ("P69", "Q200"), ("P166", "Q300"), ("P21", "Q6581072"), ("P131", "Q400"))}
    assert writer.person_context({"claims": claims}) == ["Q100", "Q200", "Q300"]
    assert writer.incident_context({"claims": claims}, ["Q9", "Q400"]) == ["Q9", "Q400"]
    assert writer.incident_context({"claims": claims}, []) == ["Q400"]
    assert writer.incident_context({}, []) == []
