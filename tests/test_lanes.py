"""Each story's lane and audience (2026-10-22, audit/kyun-hua-shorts-strategy.md §2 and P0-6)."""
import json
from datetime import datetime, timezone
from pathlib import Path

from desk import ledger, plan

ROWS = Path(__file__).parent / "fixtures" / "published-2026-10-21.json"  # the state branch's 74 rows, trimmed
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc)


def rows():
    return json.loads(ROWS.read_text(encoding="utf-8"))


def row(story_id):
    return next(r for r in rows() if r["id"] == story_id)


def test_the_actor_imran_khan_led_by_india_s_nation_section_is_for_india():
    # The radar called him "world" (his Wikidata centre); Google News India's Nation section led with him.
    imran = {"id": "kh-20261019-Q312781", "kind": "explainer", "category": "entertainment", "region": "world",
             "person": True, "qid": "Q312781", "title": "Imran Khan",
             "story": "Imran Khan challenges notice, court to hear plea on Oct 26", "top": {"IN-nation": 4}}
    assert plan.audience_of(imran) == "india" and plan.lane_of(imran) == "naam-niyam"
    assert imran["region"] == "world"  # region is left as it was
    # A front page leads with the Pope too: that alone is no India audience.
    assert plan.audience_of(imran | {"top": {"IN": 3, "IN-hi": 5}}) == "world"
    assert plan.audience_of(imran | {"top": None}) == "world" and plan.lane_of(imran | {"top": None}) == "other"
    assert plan.audience_of(imran | {"top": {"IN-hi-nation": 9}}) == "india"
    assert plan.audience_of(imran | {"top": None, "india_link": True}) == "india"


def test_an_rbi_repo_story_is_paisa_and_macro_numbers_are_not():
    repo = {"kind": "explainer", "category": "economy", "region": "india", "person": False, "qid": "Q1",
            "story": "RBI keeps repo rate unchanged at 5.5%; home loan EMIs stay the same"}
    assert plan.lane_of(repo) == "paisa"
    assert plan.lane_of({"kind": "explainer", "category": "economy", "region": "india",
                         "story": "आरबीआई ने रेपो रेट घटाया, सस्ती होगी ईएमआई"}) == "paisa"
    # WPI, IMF and Sensex are macro: not what changes for the viewer.
    for story_id in ("kh-20261014-Q123", "kh-20261015-Q7804", "kh-20261016-Q796994"):
        assert plan.lane_of(row(story_id)) == "other", story_id
    assert plan.lane_of(row("kh-20261016-Q213380")) == "paisa"  # airfare rules, told as a court story


def test_rahul_gandhi_against_the_mea_is_rajneeti_and_a_cricket_slam_is_not():
    assert plan.lane_of(row("kh-20261016-Q10218")) == "rajneeti"
    assert plan.lane_of({"kind": "incident", "category": "politics", "region": "india", "title": "x"}) == "rajneeti"
    kohli = {"kind": "explainer", "category": "sport", "region": "india", "person": True,
             "story": "Kohli slams a century as India beat Australia"}
    assert plan.lane_of(kohli) == "naam-niyam"


def test_the_tiger_firing_case_is_sensitive_and_a_film_shoot_is_not():
    tiger = [r for r in rows() if "tiger-shroff" in r["id"]]
    assert len(tiger) == 11 and {plan.lane_of(r) for r in tiger} == {"sensitive"}
    # The person-centred angles too: a sensitive case stays one, whatever the angle.
    assert plan.lane_of(row("nw-20261019-tiger-shroff-attack-family")) == "sensitive"
    shoot = {"kind": "explainer", "category": "entertainment", "region": "india", "person": True,
             "story": "Tiger Shroff resumes film shooting in Bombay after a break"}
    assert plan.lane_of(shoot) == "naam-niyam"
    assert plan.lane_of({"kind": "incident", "category": "protest", "region": "world",
                         "title": "Riot police disperse students"}) == "other"


def test_deaths_incidents_and_breaking_news_have_their_lanes():
    assert plan.lane_of(row("wk-Q2475741")) == plan.lane_of(row("wk-Q228928")) == "obituary"
    for story_id in ("wk-Q141670823", "wk-Q141605182", "nw-20261017-kolkata-disaster"):
        assert plan.lane_of(row(story_id)) == "breaking", story_id
    assert plan.lane_of(row("wp-2026_anti-CEC_protests")) == "other"  # a protest is not breaking news
    assert plan.lane_of(row("adv-delhi-cjp-2026-10-10")) == "other"
    big = {"kind": "explainer", "category": "court", "region": "india", "person": False, "fame": 900_000,
           "news_at": NOW.isoformat()}
    assert plan.lane_of(big) == "naam-niyam"
    assert plan.lane_of(big | {"kind": "incident", "category": "fire"}, NOW) == "breaking"
    assert plan.lane_of(big | {"breaking": True}) == "breaking"


def test_the_backfill_labels_all_74_rows_and_changes_nothing_else():
    before = rows()
    done = plan.backfill_lanes(before)
    assert len(done) == 74 and all(r["lane"] in plan.LANES and r["audience"] in ("india", "world") for r in done)
    assert before == rows()  # pure: the rows it was given are untouched
    assert [{k: v for k, v in r.items() if k not in ("lane", "audience")} for r in done] == before
    lanes = {lane: sum(1 for r in done if r["lane"] == lane) for lane in plan.LANES}
    assert all(lanes[lane] for lane in plan.LANES), lanes
    # A row that already has its lane keeps it.
    assert plan.backfill_lanes([before[0] | {"lane": "paisa", "audience": "india"}])[0]["lane"] == "paisa"


def test_the_one_shot_backfill_rewrites_only_the_local_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    import backfill_lanes

    monkeypatch.setattr(ledger, "STATE", tmp_path)
    ledger.save("published", rows())
    before = (tmp_path / "published.json").read_text(encoding="utf-8")
    assert backfill_lanes.main([]) == 0
    assert (tmp_path / "published.json").read_text(encoding="utf-8") == before  # counting writes nothing
    assert "74 rows, 74 without a lane" in capsys.readouterr().out
    assert backfill_lanes.main(["--write"]) == 0
    assert [r["lane"] for r in ledger.published()] == [r["lane"] for r in plan.backfill_lanes(rows())]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["published.json"]


def test_watch_labels_every_candidate_before_ranking(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(plan, "REMAKES", tmp_path / "remakes")
    monkeypatch.setattr(plan, "CASES", tmp_path / "cases")
    monkeypatch.setattr(plan, "_quake_facts", lambda cands: [])
    monkeypatch.setattr(plan.orbitwire, "fetch", lambda: {"published": [], "candidates": []})
    tiger = {"id": "nw-20261019-tiger-shroff-attack", "title": "Tiger Shroff attack", "category": "attack",
             "kind": "incident", "region": "world", "fame": 1, "headlines": ["Shots fired at actor in Mumbai"]}
    death = {"id": "wk-Q2475741", "title": "Nana Patekar", "kind": "death", "category": "death", "region": "india",
             "fame": 1}
    monkeypatch.setattr(plan.trends, "radar", lambda: {"candidates": [tiger, death], "errors": []})
    found = {c["id"]: c for c in plan.watch(save=False)["candidates"]}
    assert (found[tiger["id"]]["lane"], found[tiger["id"]]["audience"]) == ("sensitive", "india")
    assert (found[death["id"]]["lane"], found[death["id"]]["audience"]) == ("obituary", "india")
    assert found[tiger["id"]]["region"] == "world"
