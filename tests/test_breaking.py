"""Big incidents go out while people are looking: told from the reporting while the article is brand new, and
breaking as soon as many independent outlets lead with them."""
from datetime import datetime, timedelta, timezone

from desk import outlets, plan, trends
from tests.test_outlets import NOW, _cluster


def test_a_big_story_with_a_brand_new_article_is_told_from_the_reporting_at_once(monkeypatch):
    rows = [i | {"matched": "2026 Chamoli cloudburst"} for i in _cluster()]
    known = ["2026 Chamoli cloudburst"]
    assert outlets.stories(rows, NOW, known=known) == []  # the article is settled: it is told from Wikipedia
    [story] = outlets.stories(rows, NOW, known=known, young=known)
    assert story["id"].startswith("nw-") and story["article"] == "2026 Chamoli cloudburst"

    cand = {"id": "wk-Q99", "kind": "incident", "title": "2026 Chamoli cloudburst", "owners": ["BBC", "A", "B"]}
    hours = {"2026 Chamoli cloudburst": 2, "Settled": 9, "Quiet": 1}
    monkeypatch.setattr(trends.wiki, "created", lambda title: datetime.now(timezone.utc) - timedelta(hours=hours[title]))
    cands = [cand, cand | {"title": "Settled"}, cand | {"title": "Quiet", "owners": ["BBC"]}]
    assert trends.young_articles(cands) == ["2026 Chamoli cloudburst"]
    told = [{"id": story["id"], "published_at": NOW.isoformat(), "article": "2026 Chamoli cloudburst"}]
    assert plan.told_before(cand, told, NOW)


def test_five_outlets_on_one_incident_make_it_breaking():
    crash = {"kind": "incident", "category": "rail", "fame": 50_000, "news_at": NOW.isoformat(),
             "owners": ["BBC", "Government of India", "HT Media", "NDTV", "The Hindu Group"]}
    assert plan.is_breaking(crash, NOW)
    assert not plan.is_breaking(crash | {"owners": crash["owners"][1:]}, NOW)  # four outlets
    assert not plan.is_breaking(crash | {"owners": ["BBC", "HT Media", "NDTV", "The Hindu Group", "Zee Media"]},
                                NOW)  # one strong outlet
    assert not plan.is_breaking(crash | {"category": "protest"}, NOW)
