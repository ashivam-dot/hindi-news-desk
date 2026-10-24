from datetime import datetime, timedelta, timezone

import pytest

from desk import ledger, plan, revisit, wiki

AT = datetime(2026, 10, 24, 11, 0, tzinfo=timezone.utc)
TIGER = {"labels": {"en": {"value": "Tiger Shroff"}}, "sitelinks": {"enwiki": {"title": "Tiger Shroff"}},
         "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}}


def row(i, at, video, qid="Q16202406", case="tiger-shroff-2026-10-20", urls=(), heads=None, sid=None):
    return {"id": sid or f"nw-20261019-tiger-shroff-attack-{i}", "qid": qid, "case": case, "video_id": video,
            "published_at": at.isoformat(), "title": f"Tiger Shroff: angle {i}", "category": "attack",
            "region": "india", "report_urls": list(urls),
            "headlines": heads or ["Tiger Shroff firing: accused caught in Kota",
                                   "Tiger Shroff firing case: Kota court hands accused to Mumbai Police"]}


def item(title, owner, at, url=None):
    return {"title": title, "owner": owner, "outlet": owner, "outlet_hi": owner, "group": "Indian national",
            "lang": "en", "at": at.isoformat(), "url": url or f"https://x/{owner}/{abs(hash(title))}"}


@pytest.fixture
def tiger(monkeypatch):
    monkeypatch.setattr(wiki, "entities", lambda qids: {q: TIGER for q in qids})
    monkeypatch.setattr(wiki, "claims", lambda ent, pid: [{"value": "Q5"}] if pid == "P31" else [])
    monkeypatch.setattr(wiki, "common_hindi", lambda ent: "टाइगर श्रॉफ")
    monkeypatch.setattr(ledger, "is_done", lambda sid: False)
    rows = [row(1, AT - timedelta(days=3, hours=6), "a"), row(2, AT - timedelta(days=3), "b"),
            row(9, AT - timedelta(hours=20), "z", qid="Q1", case=None, sid="kh-20261023-Q1",
                heads=["Om Birla speaks on rules"])]
    rows += [row(10 + i, AT - timedelta(days=2, hours=i), f"n{i}", qid=f"Q{10 + i}", case=None,
                 sid=f"kh-20261022-Q{10 + i}") for i in range(4)]
    views = {"a": 1070, "b": 840, "z": 30} | {f"n{i}": 40 for i in range(4)}
    return rows, views


def test_a_quiet_channel_brings_back_the_hit_case_with_its_new_reports(tiger):
    rows, views = tiger
    since = AT - timedelta(hours=6)
    items = [item("3 accused in Tiger Shroff shooting case sent to police custody till October 28", "HT Media", since),
             item("Tiger Shroff attack: Police recover 2 firearms from Surat, another suspect detained in Kota",
                  "Indian Express Group", since),
             item("Tiger Shroff to star in new action film", "Network18", since)]
    cands, notes = revisit.candidates(rows, AT, items=items, views=views)
    assert [c["id"] for c in cands] == ["kh-20261024-Q16202406-update"]
    c = cands[0]
    assert c["owners"] == ["HT Media", "Indian Express Group"]  # the film headline shares no word of the case
    assert c["earlier"] == ["Tiger Shroff: angle 1", "Tiger Shroff: angle 2"]
    assert c["fame"] == revisit.REVISIT_FAME and c["category_hi"] == "घटना" and c["person"]
    assert "since" in c["focus"].lower()
    assert "5 owners" not in notes[0] and "2 owners' new reports on Tiger Shroff" in notes[0]


def test_news_already_told_or_from_one_owner_brings_nothing_back(tiger):
    rows, views = tiger
    old = AT - timedelta(days=4)  # before the last Short
    used = "https://x/used"
    rows[-2]["report_urls"] = [used]
    items = [item("Tiger Shroff firing: accused caught in Kota", "HT Media", old),
             item("Tiger Shroff firing case: Kota police custody", "Network18", AT - timedelta(hours=2), url=used),
             item("Tiger Shroff firing case: custody till October 28", "NDTV", AT - timedelta(hours=2))]
    cands, notes = revisit.candidates(rows, AT, items=items, views=views)
    assert cands == [] and "1 owners reported new news on Tiger Shroff" in notes[0]


def test_only_a_quiet_channel_revisits_and_at_most_per_day():
    busy = [row(1, AT - timedelta(minutes=40), "a")]
    assert not revisit.due(busy, AT)
    quiet = [row(1, AT - timedelta(hours=3), "a")]
    assert revisit.due(quiet, AT)
    used = quiet + [row(i, AT - timedelta(hours=3 + i), f"u{i}", sid=f"kh-20261024-Q{i}-update")
                    for i in range(revisit.PER_DAY)]
    assert not revisit.due(used, AT)


def test_a_story_viewers_did_not_watch_is_no_hit():
    rows = [row(1, AT - timedelta(days=2), "a"), row(2, AT - timedelta(days=2), "b", qid="Q2", case=None),
            row(3, AT - timedelta(days=12), "c", qid="Q3", case=None)]
    found = revisit.hits(rows, {"a": 60, "b": 40, "c": 5000}, AT)
    assert found == []  # 60 is under MIN_VIEWS; the 5,000-view Short is older than LOOKBACK_DAYS


def test_story_words_leave_out_the_name_and_passing_words():
    rows = [row(1, AT, "a", heads=["Tiger Shroff firing: police help in morning raid in Kota",
                                   "Tiger Shroff case: Kota court remands accused"])]
    words = revisit.story_words(rows, "Tiger Shroff")
    assert "kota" in words and "tiger" not in words and "shroff" not in words
    assert "morning" not in words and "help" not in words  # in one headline only


def test_a_revisit_ranks_below_every_fresh_story():
    fresh = {"id": "kh-20261024-Q5", "fame": 50000, "kind": "explainer", "region": "india", "date": "2026-10-24",
             "news_at": AT.isoformat()}
    old = fresh | {"id": "kh-20261024-Q6-update", "fame": revisit.REVISIT_FAME}
    assert plan.priority(fresh, AT) > plan.priority(old, AT)
