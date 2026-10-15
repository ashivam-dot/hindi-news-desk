from datetime import datetime, timedelta, timezone

from desk import plan, top

NOW = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)


def lead(feed, rank, title):
    return {"feed": feed, "rank": rank, "title": title, "outlets": 5, "at": NOW.isoformat()}


LISTS = {
    "IN": [lead("IN", 1, "Converts To Non-Hindu Religions Can't Claim Backward Class Quota, Says Supreme Court"),
           lead("IN", 8, "PM Modi inaugurates Rs 3,350 crore projects in Ladakh, including new Leh airport terminal")],
    "IN-hi": [lead("IN-hi", 2, "नाना पाटेकर के निधन पर बॉलीवुड में शोक"),
              lead("IN-hi", 8, "अंकिता भंडारी मर्डर केस: पिता ने रखीं पांच मांगें, राहुल गांधी- न्याय की लड़ाई न दबेगी")],
    "IN-nation": [], "IN-hi-nation": [],
}


def test_a_story_is_ranked_by_its_place_in_the_english_and_hindi_lists():
    sc = {"id": "kh-1", "phrase": "Supreme Court", "label_hi": "भारत का सर्वोच्च न्यायालय",
          "headlines": ["SC: converts to Islam, Christianity can't claim backward class quota"]}
    modi = {"id": "kh-2", "headlines": ["Modi opens new Leh airport terminal in Ladakh"]}
    nana = {"id": "wk-3", "label_hi": "नाना पाटेकर", "headlines": ["Nana Patekar dies at 75"]}
    rahul = {"id": "kh-4", "phrase": "Rahul Gandhi", "label_hi": "राहुल गांधी",
             "headlines": ["Rahul Gandhi hosts INDIA bloc high tea"]}
    kenya = {"id": "kh-5", "headlines": ["Kenya confirms second Ebola case"]}
    top.mark([sc, modi, nana, rahul, kenya], LISTS)
    assert sc["top"] == {"IN": 1} and sc["top_score"] == 1.0
    assert modi["top"] == {"IN": 8} and 0.6 < modi["top_score"] < 0.7
    assert nana["top"] == {"IN-hi": 2} and nana["top_headlines"] == ["नाना पाटेकर के निधन पर बॉलीवुड में शोक"]
    assert rahul["top"] == {}  # named late in a headline about another story
    assert kenya["top"] == {} and kenya["top_score"] == 0


def test_the_centre_must_be_the_person_the_headlines_describe():
    from desk import explain

    titles = ["Actor Imran Khan asked to leave India after participating in protest",
              "Imran Khan, actor, gets leave India notice", "Dipke backs Imran Khan"]
    assert explain.headline_role(titles, "Imran Khan") == "actor"
    assert explain.headline_role(["Imran Khan backs Dipke"], "Imran Khan") is None
    pm = {"descriptions": {"en": {"value": "Prime Minister of Pakistan from 2018 to 2022"}}}
    actor = {"descriptions": {"en": {"value": "Indian actor"}}}
    assert not explain.fits_role(pm, "actor") and explain.fits_role(actor, "actor")


def test_unreadable_lists_rank_nothing_and_drop_nothing():
    c = {"id": "kh-5", "headlines": ["Kenya confirms second Ebola case"], "fame": 100_000}
    top.mark([c], None)
    assert c["top"] is None and plan.unpopular(c, NOW) is None


def test_only_top_stories_go_out():
    random = {"id": "kh-5", "kind": "explainer", "category": "health", "fame": 150_000, "top": {}, "top_score": 0}
    assert "not in Google News India" in plan.unpopular(random, NOW)
    assert plan.unpopular(random | {"top": {"IN-hi": 12}, "top_score": 0.45}, NOW) is None
    assert plan.unpopular(random | {"traffic": 2000, "geos": ["IN"]}, NOW) is None
    assert plan.unpopular(random | {"fame": 500_000}, NOW) is None
    film = random | {"category": "entertainment", "top": {"IN": 15}, "top_score": 0.3}
    assert "top-10" in plan.unpopular(film, NOW)
    assert plan.unpopular(film | {"top": {"IN": 3}, "top_score": 0.9}, NOW) is None


def test_the_top_story_outranks_a_bigger_random_one():
    at = NOW
    lead_story = {"id": "kh-1", "kind": "explainer", "fame": 100_000, "news_at": at.isoformat(), "top_score": 1.0}
    other = {"id": "kh-2", "kind": "explainer", "fame": 200_000, "news_at": at.isoformat(), "top_score": 0.0}
    assert plan.priority(lead_story, at) > plan.priority(other, at)


def report(url, owner):
    return {"url": url, "owner": owner, "title": "t", "outlet": owner, "group": "national", "lang": "en",
            "at": NOW.isoformat()}


def test_a_big_story_gets_a_follow_up_part_with_new_reporting_only():
    first = {"id": "kh-20261015-Q1", "published_at": (NOW - timedelta(hours=4)).isoformat(), "title": "भाग एक",
             "report_urls": ["u1", "u2"]}
    cand = {"id": "kh-20261015-Q1", "top_score": 1.2,
            "reports": [report("u1", "A"), report("u2", "B"), report("u3", "C"), report("u4", "D")]}
    part = plan.follow_up(cand, [first], NOW)
    assert part["id"] == "kh-20261015-Q1-p2" and part["earlier"] == ["भाग एक"]
    assert [r["url"] for r in part["reports"]] == ["u3", "u4"]
    assert plan.follow_up(cand | {"top_score": 0.5}, [first], NOW) is None  # not big enough
    soon = first | {"published_at": (NOW - timedelta(hours=1)).isoformat()}
    assert plan.follow_up(cand, [soon], NOW) is None  # too soon after the last part
    old_news = cand | {"reports": [report("u1", "A"), report("u2", "B"), report("u3", "C")]}
    assert plan.follow_up(old_news, [first], NOW) is None  # one owner's new report is not enough
    parts = [first | {"id": f"kh-20261015-Q1-p{n}"} for n in (2, 3)]
    assert plan.follow_up(cand, [first] + parts, NOW) is None  # three parts a day at most
