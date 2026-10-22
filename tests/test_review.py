from datetime import datetime, timedelta, timezone

import pytest

from desk import cli, config, learn, ledger, plan, review, voice

AT = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)  # a review day, 17:30 IST


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    return tmp_path


def channel(groups, at=AT):
    """Fixture ledger and performance.json: groups is [(count, row fields, record fields)], one Short every 3 hours
    back from two days before `at`."""
    rows, videos, i = [], {}, 0
    for count, row, rec in groups:
        for _ in range(count):
            published = (at - timedelta(hours=48 + 3 * i)).isoformat()
            rows.append({"id": f"s{i}", "video_id": f"v{i}", "published_at": published} | row)
            views = rec.get("views_24h", 40)
            videos[f"v{i}"] = {"id": f"s{i}", "published_at": published, "views_6h": views / 2, "views_24h": views,
                               "snapshots": [{"age_h": 48.0, "views": rec.get("views", views)}],
                               "plays": 100, "engaged_views": 44, "avg_view_pct": 40.0, "avg_view_s": 18,
                               "subscribers_gained": 0} | rec
            i += 1
    ledger.save("published", sorted(rows, key=lambda r: r["published_at"]))
    ledger.save("performance", {"at": at.isoformat(), "videos": videos})


def card(at=AT, reviews=None):
    return review.scorecard(ledger.load("performance", {}), ledger.published(), at, reviews)


def group(c, name):
    return next(g for g in c["groups"] if g["name"] == name)


def test_each_verdict_against_the_baseline():
    channel([(30, {"lane": "other"}, {}),
             (10, {"lane": "naam-niyam"}, {"views_24h": 100}),  # 2.5x the median: SCALE
             (10, {"lane": "rajneeti"}, {"views_24h": 50, "engaged_views": 60, "subscribers_gained": 1}),
             (10, {"lane": "paisa"}, {"views_24h": 20}),  # half the median, engaged share at baseline: CUT
             (10, {"lane": "breaking"}, {"views_24h": 20, "engaged_views": 70}),  # low views but held: HOLD
             (9, {"lane": "obituary"}, {"views_24h": 900})])
    c = card()
    assert c["base"]["views_24h"] == 40 and c["base"]["n"] == 79
    assert group(c, "lane:naam-niyam")["verdict"].startswith("SCALE (median x2.50")
    assert group(c, "lane:rajneeti")["verdict"] == "SCALE (engaged share and subscriber rate)"
    assert group(c, "lane:paisa")["verdict"].startswith("CUT (median x0.50")
    assert group(c, "lane:breaking")["verdict"].startswith("HOLD (median x0.50")
    assert group(c, "lane:other")["verdict"].startswith("HOLD")
    assert group(c, "lane:obituary")["verdict"] == review.NO_VERDICT == "n<10: no verdict"
    paisa = group(c, "lane:paisa")
    assert (paisa["n"], paisa["views_6h"], paisa["engaged"], paisa["pct"], paisa["secs"]) == (10, 10, 44, 40, 18)
    assert group(c, "lane:rajneeti")["subs_engaged"] == pytest.approx(1000 / 60)
    assert group(c, "lane:rajneeti")["subs_plays"] == pytest.approx(10)


def test_a_second_cut_in_a_row_is_stop():
    channel([(30, {"lane": "other"}, {}), (10, {"lane": "paisa"}, {"views_24h": 20})], at=AT + timedelta(days=14))
    later = AT + timedelta(days=14)
    assert group(card(later), "lane:paisa")["verdict"].startswith("CUT")  # nothing recorded before
    reviews = {"2026-11-05": {"lane:paisa": "CUT (median x0.50, engaged share not above baseline)"}}
    assert group(card(later, reviews), "lane:paisa")["verdict"].startswith("STOP")
    # A HOLD before it, or a cut recorded for this same review day, is not a second cut.
    assert group(card(later, {"2026-11-05": {"lane:paisa": "HOLD"}}), "lane:paisa")["verdict"].startswith("CUT")
    assert group(card(later, {"2026-11-19": {"lane:paisa": "CUT"}}), "lane:paisa")["verdict"].startswith("CUT")


def test_sensitive_cases_are_their_own_line_and_never_scale_a_lane():
    channel([(30, {"lane": "other"}, {}),
             (12, {"case": "tiger-shroff-2026-10-20"}, {"views_24h": 900, "engaged_views": 80,
                                                        "subscribers_gained": 5})])
    c = card()
    sensitive = group(c, "lane:sensitive")  # a case angle with no lane in the ledger is sensitive
    assert sensitive["n"] == 12 and sensitive["verdict"].startswith("HOLD (sensitive: never SCALE")
    assert all(not g["verdict"].startswith("SCALE") for g in c["groups"])
    # The case is the biggest one: the baseline leaves it out, and no other breakdown counts it.
    assert c["big"] == "tiger-shroff-2026-10-20" and c["base"]["n"] == 30 and c["base"]["views_24h"] == 40
    assert sum(g["n"] for g in c["groups"] if g["key"] == "slot") == 30
    assert sum(g["n"] for g in c["groups"] if g["key"] == "rank") == 30
    # A ledger lane wins over the fallback.
    channel([(30, {"lane": "other"}, {}), (12, {"lane": "naam-niyam", "case": "x"}, {"views_24h": 900})])
    assert group(card(), "lane:naam-niyam")["verdict"].startswith("SCALE")


def test_breakdowns_by_variant_slot_and_rank_with_traffic_and_view_shares():
    channel([(10, {"lane": "other", "variant": "long"}, {"views": 12_000, "traffic": {"SHORTS": 90, "YT_SEARCH": 10},
                                                         "engaged_views": 52}),
             (10, {"lane": "other", "variant": "short"}, {"views": 500})])
    c = card()
    long = group(c, "variant:long")
    assert long["over_1k"] == 1 and long["over_10k"] == 1 and group(c, "variant:short")["over_1k"] == 0
    assert review._mix(long["traffic"]) == "SHORTS 90%, YT_SEARCH 10%"
    assert long["keep"] == "; KEEP" and group(c, "variant:short")["keep"] == "; no variant gain"
    # One Short every 3 hours: eight a day, so ranks 1-4 and 5+, and the IST slots they fell in.
    ranks = {g["value"]: g["n"] for g in c["groups"] if g["key"] == "rank"}
    assert set(ranks) <= {"1", "2", "3", "4", "5+"} and sum(ranks.values()) == 20 and ranks.get("5+")
    assert review.slot_of(datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc)) == "18-20"  # 18:30 IST
    assert review.slot_of(datetime(2026, 11, 5, 20, 0, tzinfo=timezone.utc)) == "00-06"  # 01:30 IST
    text = review.render(c)
    assert "## By variant" in text and "| long | 10 |" in text and "s0 (v0): 12000 views" in text


def test_shorts_without_a_24_hour_read_or_outside_the_window_are_not_counted():
    channel([(12, {"lane": "other"}, {})])
    videos = ledger.load("performance", {})["videos"]
    videos["v0"]["views_24h"] = None
    ledger.save("performance", {"at": AT.isoformat(), "videos": videos})
    assert group(card(), "lane:other")["n"] == 11
    assert card(AT + timedelta(days=40))["window"] == []
    assert "Baseline (0 Shorts)" in review.render(card(AT + timedelta(days=40)))


def test_daily_writes_once_per_ist_day_and_records_the_review_day(state):
    channel([(30, {"lane": "other"}, {}), (10, {"lane": "paisa"}, {"views_24h": 20})])
    note = review.daily(at=AT)
    assert note.startswith("review: state/REVIEW.md for 2026-11-05") and "review day 2026-11-05 recorded" in note
    text = (state / "REVIEW.md").read_text()
    assert text.startswith("# Scorecard") and "Review day today (2026-11-05)" in text
    memo = ledger.load("review", {})
    assert memo["day"] == "2026-11-05" and memo["reviews"]["2026-11-05"]["lane:paisa"].startswith("CUT")
    assert review.daily(at=AT + timedelta(hours=6)) is None  # 23:30 IST, the same IST day
    # 00:30 IST the next day: written again, the review day not recorded twice.
    note = review.daily(at=AT + timedelta(hours=7))
    assert "2026-11-06" in note and "recorded" not in note
    assert set(ledger.load("review", {})["reviews"]) == {"2026-11-05"}
    # Two weeks on, still cut: STOP, recorded for the new review day.
    channel([(30, {"lane": "other"}, {}), (10, {"lane": "paisa"}, {"views_24h": 20})], at=AT + timedelta(days=14))
    review.daily(at=AT + timedelta(days=14))
    assert ledger.load("review", {})["reviews"]["2026-11-19"]["lane:paisa"].startswith("STOP")


def test_daily_reads_only_and_changes_no_constant(state):
    channel([(30, {"lane": "other"}, {})])
    before = {p.name: p.read_bytes() for p in state.iterdir()}
    constants = (plan.MAX_PER_DAY, plan.MIN_GAP, learn.LIFT_RANGE)
    review.daily(at=AT)
    assert {p.name: p.read_bytes() for p in state.iterdir() if p.name in before} == before
    assert {p.name for p in state.iterdir()} - set(before) == {"REVIEW.md", "review.json"}
    assert (plan.MAX_PER_DAY, plan.MIN_GAP, learn.LIFT_RANGE) == constants


def test_an_empty_state_still_writes_a_scorecard(state):
    assert review.daily(at=AT).startswith("review: state/REVIEW.md")
    assert "Baseline (0 Shorts)" in (state / "REVIEW.md").read_text()


@pytest.fixture
def live_run(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "CHANNEL_ID", "UC" + "a" * 22)
    monkeypatch.setattr(config, "UNTAG", False)
    monkeypatch.setattr(config, "CHANNEL_JOBS", ())
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(learn, "refresh", lambda: calls.append("learn"))
    monkeypatch.setattr(cli, "retire_listed", lambda health: calls.append("retire"))
    monkeypatch.setattr(cli, "_advisory", lambda health, dry: None)
    monkeypatch.setattr(plan, "watch", lambda save=True: {"candidates": [], "trending": [], "notes": []})
    return calls


def test_the_run_writes_the_scorecard_after_learning(live_run, monkeypatch, state):
    monkeypatch.setattr(review, "daily", lambda: live_run.append("review") or "review: written")
    health = cli.run()
    assert health["ok"] and live_run == ["learn", "review", "retire"] and "review: written" in health["steps"]


def test_a_scorecard_error_never_fails_the_run(live_run, monkeypatch):
    def broken():
        raise ValueError("bad performance.json")

    monkeypatch.setattr(review, "daily", broken)
    health = cli.run()
    assert health["ok"] and "review: ValueError: bad performance.json" in health["steps"]
    assert live_run == ["learn", "retire"]


def test_a_dry_run_never_writes_the_scorecard(live_run, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "WORK", tmp_path / "work")
    monkeypatch.setattr(review, "daily", lambda: pytest.fail("a dry run wrote the scorecard"))
    assert cli.run(dry=True)["ok"]
