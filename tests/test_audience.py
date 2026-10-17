"""What the Hindi audience watches (2026-10-18 review of the channel's own numbers)."""
from datetime import datetime, timedelta, timezone

from desk import explain, gate, outlets, plan
from desk.spec import Beat, Short

from .test_outlets import item

NOW = datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)


def explainer(**kw):
    return {"id": "kh-20261017-Q1", "kind": "explainer", "category": "world", "region": "world", "fame": 300_000,
            "news_at": NOW.isoformat()} | kw


def test_a_world_explainer_needs_the_hindi_lists():
    pope = explainer(top={"IN": 14}, top_score=0.35)
    assert "Hindi newsrooms" in plan.unpopular(pope, NOW)
    white_house = explainer(top={"IN": 2, "IN-nation": 5}, top_score=1.09)
    assert "Hindi newsrooms" in plan.unpopular(white_house, NOW)
    imran = explainer(top={"IN": 5, "IN-hi-nation": 10}, top_score=1.08)
    assert plan.unpopular(imran, NOW) is None
    court = explainer(region="india", category="court", top={"IN": 9, "IN-nation": 5}, top_score=0.84)
    assert plan.unpopular(court, NOW) is None


def test_an_explainers_headline_count_never_makes_it_famous():
    unlisted = explainer(region="india", fame=500_000, top={}, top_score=0)
    assert "not in Google News India" in plan.unpopular(unlisted, NOW)
    death = {"id": "wk-Q2", "kind": "death", "category": "death", "fame": 500_000, "top": {}, "top_score": 0,
             "news_at": NOW.isoformat()}
    assert plan.unpopular(death, NOW) is None


def test_follow_up_parts_are_off():
    first = {"id": "kh-20261017-Q1", "published_at": (NOW - timedelta(hours=4)).isoformat(), "title": "भाग एक",
             "report_urls": ["u1"]}
    reports = [{"url": f"u{n}", "owner": f"O{n}", "title": "t"} for n in range(1, 6)]
    assert plan.follow_up({"id": "kh-20261017-Q1", "top_score": 1.9, "reports": reports}, [first], NOW) is None


def test_a_month_is_never_a_centre():
    assert explain.NOT_A_CENTRE.search("tenth month in the Julian and Gregorian calendars")
    assert not explain.NOT_A_CENTRE.search("Indian politician")


def test_four_indian_newsrooms_on_one_incident_make_an_nw_story():
    kolkata = [item("indiatoday", "19 killed, at least 35 injured in stampede at Kolkata Durga Puja pandal", 3, now=NOW),
               item("ht", "At least 17 dead in stampede-like situation at Kolkata's Chorbagan Durga Puja pandal", 3,
                    now=NOW),
               item("toi", "Kolkata stampede: 10 detained, including Durga Puja organisers; 19 dead", 2, now=NOW),
               item("news18", "At Least 17 Dead, 35 Injured In Stampede At Kolkata Durga Puja Pandal", 1, now=NOW)]
    got = outlets.stories(kolkata, NOW)
    assert [c["id"] for c in got] == ["nw-20261017-kolkata-disaster"] and len(got[0]["owners"]) == 4
    assert outlets.stories(kolkata[:3], NOW) == []  # three Indian owners still need an official or international one


def test_collapses_are_incidents_and_a_blame_game_is_not_a_volcano():
    assert outlets.headline_kind("4 Killed After Part Of Chimney Collapses At Power Plant In Bengal's Asansol") \
        == "disaster"
    assert outlets.headline_kind("Part of Durga Puja pandal collapses in north Kolkata") == "disaster"
    assert outlets.headline_kind("Talks collapse over seat-sharing") is None
    assert outlets.headline_kind("Kolkata Stampede Tragedy: 17 Dead, Political Blame Game Erupts") == "disaster"
    assert outlets.headline_kind("Volcano erupts in Iceland, lava reaches road") == "volcano"


def test_a_lead_story_may_go_out_on_its_one_photo():
    photo = {"file": "File:A.jpg", "license": "CC BY-SA 4.0", "page": "https://commons.wikimedia.org/wiki/File:A.jpg"}
    short = Short(id="kh-20261017-Q2", kind="explainer", title="t", beats=[Beat("x", "photo:0")], facts=[],
                  sources=["https://x"], loss=False, credits=[photo["page"]], scene={"photos": [photo]})
    assert any("photos: only 1" in p for p in gate._story(short))
    short.scene["min_photos"] = 1
    assert not any("photos: only" in p for p in gate._story(short))
