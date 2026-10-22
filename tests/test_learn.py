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
    report = learn.report({"at": "x", "learned": out, "videos": {}})
    assert "Retention: a typical Short" in report
    assert f"category:earthquake: x{quake['lift']} ranking lift (4 Shorts, typical 100 views; 4 with retention, " \
           "typically 80.0% watched)" in report
    # A lift learned from views alone says nothing about retention.
    assert "with retention" not in learn.report({"at": "x", "learned": learn.learn(same), "videos": {}})


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


class FakeHttpError(Exception):
    def __init__(self, status, reason=""):
        super().__init__(f"HTTP {status}")
        self.resp = type("Resp", (), {"status": status})()
        self.reason = reason


class FakeAnalytics:
    """reports().query(...).execute() as YouTube Analytics v2 answers it, recording every query. fail: statuses, or
    (status, message) pairs, raised in turn; traffic: {video id: {source: views}} for the traffic-source queries."""

    def __init__(self, rows=(), fail=(), traffic=None):
        self.rows, self.fail, self.queries, self.traffic = list(rows), list(fail), [], traffic or {}

    def reports(self):
        return self

    def query(self, **kw):
        self.queries.append(kw)
        return self

    def execute(self):
        if self.fail:
            fail = self.fail.pop(0)
            raise FakeHttpError(*fail) if isinstance(fail, tuple) else FakeHttpError(fail)
        q = self.queries[-1]
        if q["dimensions"] == "insightTrafficSourceType":
            got = self.traffic.get(q["filters"][len("video=="):], {})
            return {"columnHeaders": [{"name": "insightTrafficSourceType"}, {"name": "views"}],
                    "rows": [[source, views] for source, views in got.items()]}
        names = q["metrics"].split(",")
        return {"columnHeaders": [{"name": "video"}] + [{"name": n} for n in names],
                "rows": [[r["video"]] + [r.get(n) for n in names] for r in self.rows]}


def channel_of(monkeypatch, ages_h):
    rows = [{"id": f"s{i}", "video_id": f"v{i}", "category": "death", "region": "world",
             "published_at": (AT - timedelta(hours=h)).isoformat()} for i, h in enumerate(ages_h)]
    ledger.save("published", rows)
    monkeypatch.setattr(youtube, "identity", lambda api: {})
    monkeypatch.setattr(youtube, "recent", lambda api, ch: [{"id": r["video_id"], "statistics": {"viewCount": "50"}}
                                                           for r in rows])


def test_retention_is_read_from_youtube_analytics_for_shorts_three_days_old(monkeypatch):
    channel_of(monkeypatch, [100, 80, 30])  # v2 is only 30 hours old
    fake = FakeAnalytics([{"video": f"v{i}", "views": 50, "engagedViews": 40 - i, "averageViewPercentage": 61.25 + i}
                          for i in range(3)])
    learned = learn.refresh(at=AT, api=object(), analytics=fake)
    q = fake.queries[0]
    assert q["dimensions"] == "video" and q["metrics"] == learn.ANALYTICS_METRICS
    assert q["ids"] == "channel==MINE" and set(q["filters"][len("video=="):].split(",")) == {"v0", "v1"}
    # Analytics days are US Pacific (v0 went out 2026-10-06 08:00 UTC, 01:00 Pacific): the window opens a day
    # early, and ends RETENTION_MIN_AGE back, before the days whose numbers are still settling.
    assert (q["startDate"], q["endDate"]) == ("2026-10-05", "2026-10-07")
    videos = ledger.load("performance", {})["videos"]
    assert videos["v0"][learn.RETENTION_FIELD] == 61.25 and videos["v1"][learn.ENGAGED_FIELD] == 39
    assert learn.RETENTION_FIELD not in videos["v2"]  # too young to count
    assert "retention_note" not in learned


def test_without_the_analytics_scope_retention_is_a_single_note_and_nothing_else(monkeypatch):
    channel_of(monkeypatch, [100, 80])
    fake = FakeAnalytics(fail=[403])
    learned = learn.refresh(at=AT, api=object(), analytics=fake)
    assert "403" in learned["retention_note"] and len(fake.queries) == 1
    assert all(learn.RETENTION_FIELD not in v for v in ledger.load("performance", {})["videos"].values())
    # A token that lists its scopes without the Analytics one is never sent to YouTube Analytics.
    monkeypatch.setattr(youtube, "scopes", lambda: {"https://www.googleapis.com/auth/youtube.upload"})
    monkeypatch.setattr(youtube, "client", lambda *a: pytest.fail("built an Analytics client"))
    learned = learn.refresh(at=AT + learn.REFRESH, api=object())
    assert "no yt-analytics.readonly scope" in learned["retention_note"]


def test_a_report_without_engaged_views_still_gives_retention(monkeypatch):
    channel_of(monkeypatch, [100])
    refused = (400, "Unknown identifier (engagedViews) given in field parameters.metrics.")
    fake = FakeAnalytics([{"video": "v0", "views": 50, "averageViewPercentage": 48.0, "shares": 2}], fail=[refused])
    learn.refresh(at=AT, api=object(), analytics=fake)
    retention = [q for q in fake.queries if q["dimensions"] == "video"]
    assert retention[-1]["metrics"] == learn.ANALYTICS_METRICS.replace("engagedViews,", "")
    perf = ledger.load("performance", {})
    rec = perf["videos"]["v0"]
    assert rec[learn.RETENTION_FIELD] == 48.0 and learn.ENGAGED_FIELD not in rec and rec["shares"] == 2
    assert perf["analytics_dropped"] == ["engagedViews"]


def test_the_gating_metrics_are_stored_and_a_refused_one_is_dropped_alone(monkeypatch):
    channel_of(monkeypatch, [100, 90])
    full = {"views": 120, "engagedViews": 50, "averageViewPercentage": 41.256, "averageViewDuration": 23,
            "subscribersGained": 1, "likes": 4, "shares": 2}
    fake = FakeAnalytics([{"video": "v0"} | full, {"video": "v1"} | full | {"subscribersGained": 0}],
                         fail=[(400, "Unknown identifier (subscribersGained) given in field parameters.metrics.")])
    learn.refresh(at=AT, api=object(), analytics=fake)
    retention = [q["metrics"].split(",") for q in fake.queries if q["dimensions"] == "video"]
    assert len(retention) == 2 and set(retention[0]) - set(retention[1]) == {"subscribersGained"}
    perf = ledger.load("performance", {})
    rec = perf["videos"]["v0"]
    assert (rec["plays"], rec[learn.ENGAGED_FIELD], rec[learn.RETENTION_FIELD]) == (120, 50, 41.26)
    assert (rec["avg_view_s"], rec["likes"], rec["shares"]) == (23, 4, 2) and "subscribers_gained" not in rec
    assert perf["analytics_dropped"] == ["subscribersGained"]
    # Read again with nothing refused: every column lands, and nothing is listed as dropped.
    learn.refresh(at=AT + learn.REFRESH, api=object(), analytics=FakeAnalytics([{"video": "v0"} | full]))
    perf = ledger.load("performance", {})
    assert perf["videos"]["v0"]["subscribers_gained"] == 1 and perf["analytics_dropped"] == []


def test_the_refused_metric_is_read_from_the_message_not_the_request_url():
    import json

    import httplib2
    from googleapiclient.errors import HttpError

    body = {"error": {"code": 400, "message": "Unknown identifier (likes) given in field parameters.metrics."}}
    exc = HttpError(httplib2.Response({"status": 400}), json.dumps(body).encode(),
                    uri="https://youtubeanalytics.googleapis.com/v2/reports?metrics=views,engagedViews,likes")
    assert "engagedViews" in str(exc)
    assert learn._refused(exc, learn.ANALYTICS_METRICS.split(",")) == "likes"


def test_a_400_that_names_no_metric_drops_one_at_a_time_and_never_the_core(monkeypatch):
    channel_of(monkeypatch, [100])
    fake = FakeAnalytics([{"video": "v0", "views": 50, "averageViewPercentage": 30.0}], fail=[400, 400])
    learn.refresh(at=AT, api=object(), analytics=fake)
    retention = [q["metrics"] for q in fake.queries if q["dimensions"] == "video"]
    assert retention[1:] == [learn.ANALYTICS_METRICS.removesuffix(",shares"),
                             learn.ANALYTICS_METRICS.removesuffix(",likes,shares")]
    assert ledger.load("performance", {})["analytics_dropped"] == ["likes", "shares"]
    # Refused down to the core: one note, and no endless retry.
    channel_of(monkeypatch, [100])
    optional = len(learn.ANALYTICS_METRICS.split(",")) - len(learn.ANALYTICS_CORE)
    fake = FakeAnalytics(fail=[400] * (optional + 1))
    learned = learn.refresh(at=AT + learn.REFRESH, api=object(), analytics=fake)
    assert len(fake.queries) == optional + 1 and fake.queries[-1]["metrics"] == ",".join(learn.ANALYTICS_CORE)
    assert "HTTP 400" in learned["retention_note"]


def test_traffic_sources_are_read_for_at_most_thirty_shorts_three_days_old(monkeypatch):
    ages = [30, 50] + [80 + i for i in range(40)]  # the first two are under three days old
    channel_of(monkeypatch, ages)
    fake = FakeAnalytics(traffic={"v2": {"SHORTS": 40, "YT_SEARCH": 5}})
    learn.refresh(at=AT, api=object(), analytics=fake)
    traffic = [q for q in fake.queries if q["dimensions"] == "insightTrafficSourceType"]
    asked = [q["filters"][len("video=="):] for q in traffic]
    assert len(traffic) == learn.TRAFFIC_MAX and not {"v0", "v1"} & set(asked)
    assert asked[0] == "v2"  # newest first
    assert all(q["metrics"] == "views" and q["ids"] == "channel==MINE" for q in traffic)
    assert (traffic[0]["startDate"], traffic[0]["endDate"]) == ("2026-10-06", "2026-10-07")  # its own window
    videos = ledger.load("performance", {})["videos"]
    assert videos["v2"][learn.TRAFFIC_FIELD] == {"SHORTS": 40, "YT_SEARCH": 5}
    assert learn.TRAFFIC_FIELD not in videos["v0"] and learn.TRAFFIC_FIELD not in videos["v40"]
    # The next read takes the ones not read yet, and a Short read today is not asked again.
    fake = FakeAnalytics()
    learn.refresh(at=AT + learn.REFRESH, api=object(), analytics=fake)
    asked = [q["filters"][len("video=="):] for q in fake.queries if q["dimensions"] == "insightTrafficSourceType"]
    assert asked == [f"v{i}" for i in range(32, 42)]


def test_a_traffic_error_is_one_note_and_keeps_the_retention(monkeypatch):
    channel_of(monkeypatch, [100, 90])
    fake = FakeAnalytics([{"video": "v0", "views": 50, "averageViewPercentage": 48.0}])
    real = fake.execute

    def flaky():
        if fake.queries[-1]["dimensions"] == "insightTrafficSourceType":
            raise FakeHttpError(500)
        return real()

    fake.execute = flaky
    learned = learn.refresh(at=AT, api=object(), analytics=fake)
    assert learned["retention_note"].startswith("traffic: ")
    assert sum(q["dimensions"] == "insightTrafficSourceType" for q in fake.queries) == 1
    assert ledger.load("performance", {})["videos"]["v0"][learn.RETENTION_FIELD] == 48.0


def test_token_scopes_are_read_when_the_token_lists_them(monkeypatch):
    monkeypatch.setenv("YOUTUBE_OAUTH_JSON", '{"scopes": ["a", "b"]}')
    assert youtube.scopes() == {"a", "b"}
    monkeypatch.setenv("YOUTUBE_OAUTH_JSON", '{"scopes": "a b"}')
    assert youtube.scopes() == {"a", "b"}
    monkeypatch.setenv("YOUTUBE_OAUTH_JSON", '{"refresh_token": "x"}')
    assert youtube.scopes() is None
