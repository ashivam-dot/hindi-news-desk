import math
from datetime import datetime, timedelta, timezone

import pytest

from desk import learn, ledger, plan, youtube

AT = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    learn._cache.clear()
    return tmp_path


def test_views_at_interpolates_and_waits_for_age():
    snaps = [{"age_h": 12, "views": 100}, {"age_h": 36, "views": 300}]
    assert learn.views_at(snaps, 24) == pytest.approx(200)
    assert learn.views_at([{"age_h": 10, "views": 50}], 24) is None
    assert learn.views_at([{"age_h": 96, "views": 400}], 24) == pytest.approx(200)


def _video(i, views, category="death", region="world"):
    return {"id": f"s{i}", "published_at": AT.isoformat(), "category": category, "region": region,
            "views_24h": views, "snapshots": []}


def test_no_lift_below_min_samples():
    out = learn.learn([_video(i, 100) for i in range(learn.MIN_SAMPLES - 1)])
    assert out["lifts"] == {}


def test_lifts_are_shrunk_and_bounded():
    vids = [_video(i, 10_000, "earthquake") for i in range(4)] + [_video(10 + i, 10, "death") for i in range(4)]
    lifts = learn.learn(vids)["lifts"]
    assert lifts["category:earthquake"]["lift"] == learn.LIFT_RANGE[1]
    assert lifts["category:death"]["lift"] == learn.LIFT_RANGE[0]
    assert "region:world" in lifts and lifts["region:world"]["lift"] == pytest.approx(1.0)
    mild = [_video(i, 130, "earthquake") for i in range(4)] + [_video(10 + i, 100, "death") for i in range(4)]
    gap = math.log(131 / 101) / 2
    assert learn.learn(mild)["lifts"]["category:earthquake"]["lift"] == pytest.approx(math.exp(gap * 0.5), abs=1e-3)


def test_factor_defaults_to_one_and_steers_priority():
    cand = {"category": "earthquake", "region": "india", "fame": 1000, "kind": "earthquake",
            "date": AT.isoformat()}
    base = plan.priority(cand, AT)
    assert learn.factor(cand) == 1.0
    ledger.save("performance", {"at": "x", "learned": {"lifts": {"category:earthquake": {"lift": 1.2}}}})
    assert learn.factor(cand) == pytest.approx(1.2)
    assert plan.priority(cand, AT) == pytest.approx(base * 1.2)


def test_refresh_snapshots_scores_and_throttles(monkeypatch, state):
    rows = [{"id": f"s{i}", "video_id": f"v{i}", "kind": "story", "category": "death", "region": "world",
             "published_at": (AT - timedelta(hours=30)).isoformat()} for i in range(5)]
    rows.append({"id": "later", "video_id": "vf", "published_at": (AT + timedelta(hours=2)).isoformat()})
    ledger.save("published", rows)
    monkeypatch.setattr(youtube, "identity", lambda api: {})
    monkeypatch.setattr(youtube, "recent", lambda api, ch: [
        {"id": f"v{i}", "statistics": {"viewCount": str(100 * (i + 1)), "likeCount": "3"}} for i in range(5)]
        + [{"id": "vf", "statistics": {"viewCount": "0"}}])
    learned = learn.refresh(at=AT, api=object())
    assert learned["scored"] == 5 and "category:death" in learned["lifts"]
    perf = ledger.load("performance", {})
    assert set(perf["videos"]) == {f"v{i}" for i in range(5)}
    assert perf["videos"]["v0"]["snapshots"][0]["likes"] == 3
    assert (state / "LEARNINGS.md").read_text().startswith("# What this channel's own numbers say")
    assert learn.refresh(at=AT + timedelta(hours=1), api=object()) is None
    assert learn.refresh(at=AT + learn.REFRESH, api=object()) is not None
    assert len(ledger.load("performance", {})["videos"]["v0"]["snapshots"]) == 2


def test_without_retention_data_lifts_are_views_alone():
    vids = [_video(i, 130, "earthquake") for i in range(4)] + [_video(10 + i, 100, "death") for i in range(4)]
    out = learn.learn(vids)
    assert "baseline_view_pct" not in out and "n_retention" not in out["lifts"]["category:earthquake"]
    # Too few records with the field: still views alone.
    few = [v | {learn.RETENTION_FIELD: 90} for v in vids[:3]] + vids[3:]
    assert learn.learn(few)["lifts"] == out["lifts"]


def test_retention_is_blended_into_lifts_shrunk_and_bounded():
    same = [_video(i, 100, "earthquake") for i in range(4)] + [_video(10 + i, 100, "death") for i in range(4)]
    held = [v | {learn.RETENTION_FIELD: 80 if v["category"] == "earthquake" else 40} for v in same]
    out = learn.learn(held)
    assert out["baseline_view_pct"] == pytest.approx(math.expm1((math.log(81) + math.log(41)) / 2), abs=0.1)
    quake, death = out["lifts"]["category:earthquake"], out["lifts"]["category:death"]
    gap = (math.log(81) - math.log(41)) / 2 * 0.5  # each side's distance from the channel's mean, shrunk by 4/8
    assert quake["lift"] == pytest.approx(math.exp(learn.RETENTION_WEIGHT * gap), abs=1e-3)
    assert death["lift"] == pytest.approx(math.exp(-learn.RETENTION_WEIGHT * gap), abs=1e-3)
    assert quake["n_retention"] == 4 and quake["typical_view_pct"] == pytest.approx(80, abs=0.1)
    # Equal views, wildly different retention: the lift stays within LIFT_RANGE.
    wild = [v | {learn.RETENTION_FIELD: 10_000 if v["category"] == "earthquake" else 0} for v in same]
    lifts = learn.learn(wild)["lifts"]
    assert lifts["category:earthquake"]["lift"] == learn.LIFT_RANGE[1]
    assert lifts["category:death"]["lift"] == learn.LIFT_RANGE[0]
    assert "Retention: a typical Short" in learn.report({"at": "x", "learned": out, "videos": {}})


def test_refresh_keeps_a_records_retention(monkeypatch):
    published = (AT - timedelta(hours=30)).isoformat()
    ledger.save("published", [{"id": "s0", "video_id": "v0", "category": "death", "region": "world",
                               "published_at": published}])
    ledger.save("performance", {"at": None, "videos": {"v0": {"id": "s0", "published_at": published,
                                                              "snapshots": [], learn.RETENTION_FIELD: 55.0}}})
    monkeypatch.setattr(youtube, "identity", lambda api: {})
    monkeypatch.setattr(youtube, "recent", lambda api, ch: [{"id": "v0", "statistics": {"viewCount": "9"}}])
    learn.refresh(at=AT, api=object())
    assert ledger.load("performance", {})["videos"]["v0"][learn.RETENTION_FIELD] == 55.0
