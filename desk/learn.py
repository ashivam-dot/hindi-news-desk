"""What the channel's own numbers say, fed back into the desk.

Every REFRESH the scheduled run reads each published Short's views, likes and comments, scores it by its views at
SCORE_AT_H hours, and compares story categories and regions with the channel's baseline. The desk multiplies a
candidate's priority by the learned lift of its category and region. A lift needs MIN_SAMPLES scored Shorts, is
shrunk toward 1 by n / (n + PRIOR) and stays within LIFT_RANGE, so a couple of lucky uploads cannot steer the desk.
Everything lands in state/performance.json, with a readable state/LEARNINGS.md.

Views say who clicked; how much of the Short they watched says whether the story held them. A video record that
carries RETENTION_FIELD (YouTube Analytics' averageViewPercentage, 0-100+) adds a second score: a group's mean
retention against the channel's, shrunk the same way by its own count, blended in at RETENTION_WEIGHT before the
same LIFT_RANGE bounds. read_retention fills it (and engaged_views) from YouTube Analytics v2 for Shorts at least
RETENTION_MIN_AGE old, through the desk's own sign-in. That needs the yt-analytics.readonly scope: without it (HTTP
403, or a token that lists its scopes without it) nothing is filled, one health note says so, and lifts are views
alone. The same query reads the gating numbers the scorecard (desk/review.py) judges by: plays, seconds watched,
subscribers gained, likes and shares (ANALYTICS_FIELDS); a metric the report refuses (HTTP 400) is dropped alone and
listed in perf["analytics_dropped"]. read_traffic adds where the views came from (insightTrafficSourceType) for at
most TRAFFIC_MAX Shorts a run.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

from . import ledger

REFRESH = timedelta(hours=3)
SCORE_AT_H = 24.0
MIN_SAMPLES = 4
PRIOR = 4.0
LIFT_RANGE = (0.75, 1.35)
FEATURES = ("category", "region")
RETENTION_FIELD = "avg_view_pct"
RETENTION_WEIGHT = 0.5
KEEP_SNAPSHOTS = 16
ENGAGED_FIELD = "engaged_views"
RETENTION_MIN_AGE = timedelta(days=3)  # YouTube Analytics' numbers settle about two days after the day they count
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
ANALYTICS_METRICS = "views,engagedViews,averageViewPercentage,averageViewDuration,subscribersGained,likes,shares"
ANALYTICS_CORE = ("views", "averageViewPercentage")  # never dropped: without them there is no retention to read
# Where each Analytics column lands on a video's record. Analytics' views count plays; engagedViews the old views.
ANALYTICS_FIELDS = {"views": "plays", "engagedViews": ENGAGED_FIELD, "averageViewPercentage": RETENTION_FIELD,
                    "averageViewDuration": "avg_view_s", "subscribersGained": "subscribers_gained",
                    "likes": "likes", "shares": "shares"}
ANALYTICS_MAX = 200
TRAFFIC_FIELD = "traffic"
TRAFFIC_MAX = 30  # one Analytics query a Short: a run reads where the views came from for at most this many
TRAFFIC_EVERY = timedelta(days=1)
TRAFFIC_WINDOW = timedelta(days=28)  # the scorecard's window: an older Short keeps its last read

_cache: dict = {}


def _age_h(row: dict, at: datetime) -> float:
    return (at - datetime.fromisoformat(row["published_at"])).total_seconds() / 3600


def views_at(snapshots: list[dict], hours: float) -> float | None:
    """Views at `hours` after publishing: interpolated between snapshots, or scaled back from the first later one
    (views grow roughly with the square root of age once a Short's first push is over). None while too young."""
    snaps = sorted(snapshots, key=lambda s: s["age_h"])
    if not snaps or snaps[-1]["age_h"] < hours:
        return None
    later = next(s for s in snaps if s["age_h"] >= hours)
    earlier = [s for s in snaps if s["age_h"] < hours]
    if not earlier:
        return later["views"] * math.sqrt(hours / later["age_h"]) if later["age_h"] > 0 else float(later["views"])
    a = earlier[-1]
    span = later["age_h"] - a["age_h"]
    return a["views"] + (later["views"] - a["views"]) * ((hours - a["age_h"]) / span if span else 1.0)


def _thin(snapshots: list[dict]) -> list[dict]:
    """Every snapshot of the first two days (they set the score), then the newest few."""
    early = [s for s in snapshots if s["age_h"] <= 2 * SCORE_AT_H]
    late = [s for s in snapshots if s["age_h"] > 2 * SCORE_AT_H]
    return (early + late[-4:])[-KEEP_SNAPSHOTS:]


def learn(videos: list[dict]) -> dict:
    scored = [v for v in videos if v.get("views_24h") is not None]
    out = {"scored": len(scored), "min_samples": MIN_SAMPLES, "lifts": {}}
    if len(scored) < MIN_SAMPLES:
        return out
    logs = [math.log1p(v["views_24h"]) for v in scored]
    base = sum(logs) / len(logs)
    out["baseline_views_24h"] = round(math.expm1(base))
    held_base, retention = _retention(scored)
    if held_base is not None:
        out["baseline_view_pct"] = round(math.expm1(held_base), 1)
    for feature in FEATURES:
        groups: dict[str, list[float]] = {}
        for v, score in zip(scored, logs):
            if v.get(feature):
                groups.setdefault(str(v[feature]), []).append(score)
        for value, scores in groups.items():
            n = len(scores)
            if n < MIN_SAMPLES:
                continue
            diff = (sum(scores) / n - base) * n / (n + PRIOR)
            entry = {"n": n, "typical_views_24h": round(math.expm1(sum(scores) / n))}
            if (held := retention.get(f"{feature}:{value}")) is not None:
                diff = (1 - RETENTION_WEIGHT) * diff + RETENTION_WEIGHT * held["diff"]
                entry |= {"n_retention": held["n"], "typical_view_pct": held["typical"]}
            lift = min(max(math.exp(diff), LIFT_RANGE[0]), LIFT_RANGE[1])
            out["lifts"][f"{feature}:{value}"] = {"n": n, "lift": round(lift, 3)} | entry
    return out


def _retention(scored: list[dict]) -> tuple[float | None, dict]:
    """The channel's mean log retention and, per feature value with MIN_SAMPLES records carrying it, the shrunk
    log-ratio of its mean to the channel's."""
    held = [v for v in scored if isinstance(v.get(RETENTION_FIELD), (int, float)) and v[RETENTION_FIELD] >= 0]
    if len(held) < MIN_SAMPLES:
        return None, {}
    logs = [math.log1p(v[RETENTION_FIELD]) for v in held]
    base = sum(logs) / len(logs)
    out = {}
    for feature in FEATURES:
        groups: dict[str, list[float]] = {}
        for v, score in zip(held, logs):
            if v.get(feature):
                groups.setdefault(str(v[feature]), []).append(score)
        for value, scores in groups.items():
            n = len(scores)
            if n >= MIN_SAMPLES:
                out[f"{feature}:{value}"] = {"n": n, "diff": (sum(scores) / n - base) * n / (n + PRIOR),
                                             "typical": round(math.expm1(sum(scores) / n), 1)}
    return base, out


def factor(cand: dict) -> float:
    """The learned multiplier for a candidate's category and region (1.0 until there is evidence)."""
    perf = ledger.load("performance", {})
    if "lifts" not in _cache or _cache.get("at") != perf.get("at"):
        _cache.update(at=perf.get("at"), lifts=(perf.get("learned") or {}).get("lifts", {}))
    f = 1.0
    for feature in FEATURES:
        f *= _cache["lifts"].get(f"{feature}:{cand.get(feature)}", {}).get("lift", 1.0)
    return min(max(f, LIFT_RANGE[0]), LIFT_RANGE[1])


def report(perf: dict) -> str:
    learned = perf.get("learned") or {}
    lines = ["# What this channel's own numbers say", "",
             f"Updated {perf.get('at')}. Scored Shorts (views at {SCORE_AT_H:.0f} h): {learned.get('scored', 0)}. "
             f"A lift needs {MIN_SAMPLES} scored Shorts in a group; it is shrunk toward 1 and kept within "
             f"{LIFT_RANGE[0]}-{LIFT_RANGE[1]}.", ""]
    if learned.get("baseline_views_24h") is not None:
        lines.append(f"Baseline: a typical Short has {learned['baseline_views_24h']} views at 24 h.")
    if learned.get("baseline_view_pct") is not None:
        lines.append(f"Retention: a typical Short is watched {learned['baseline_view_pct']}% through; a group's "
                     f"retention is blended into its lift at {RETENTION_WEIGHT}.")
    for key, v in sorted(learned.get("lifts", {}).items(), key=lambda kv: -kv[1]["lift"]):
        held = (f"; {v['n_retention']} with retention, typically {v['typical_view_pct']}% watched"
                if v.get("n_retention") else "")
        lines.append(f"- {key}: x{v['lift']} ranking lift ({v['n']} Shorts, typical {v['typical_views_24h']} views"
                     f"{held})")
    if not learned.get("lifts"):
        lines.append("- No lift yet: not enough scored Shorts per group. The desk ranks on fame and freshness alone.")
    lines += ["", "| Short | published | " + " | ".join(FEATURES) + " | views now | views at 24 h |",
              "|---" * (len(FEATURES) + 4) + "|"]
    for v in sorted(perf.get("videos", {}).values(), key=lambda v: v["published_at"], reverse=True)[:30]:
        now = v["snapshots"][-1]["views"] if v.get("snapshots") else ""
        at24 = "" if v.get("views_24h") is None else round(v["views_24h"])
        cells = " | ".join(str(v.get(f) or "") for f in FEATURES)
        lines.append(f"| {v['id']} | {v['published_at'][:16]} | {cells} | {now} | {at24} |")
    return "\n".join(lines) + "\n"


def _status(exc: Exception) -> int | None:
    status = getattr(getattr(exc, "resp", None), "status", None)
    return int(status) if status is not None else None


def _old(perf: dict, at: datetime) -> dict:
    return {vid: rec for vid, rec in perf.get("videos", {}).items()
            if at - datetime.fromisoformat(rec["published_at"]) >= RETENTION_MIN_AGE}


def _window(published: list[str], at: datetime) -> tuple[str, str]:
    # Analytics days are US Pacific: a Short out 00:00-07:00 UTC has its first day on the UTC date before. The last
    # RETENTION_MIN_AGE of days is still settling, so the window ends before it.
    start = (min(datetime.fromisoformat(p) for p in published) - timedelta(days=1)).date().isoformat()
    return start, (at - RETENTION_MIN_AGE).date().isoformat()


def _refused(exc: Exception, metrics: list[str]) -> str:
    """The metric a 400 names ("Unknown identifier (shares) given in field parameters.metrics"), else the last one
    that may go. The message, not str(exc): a googleapiclient error's text also carries the request URL."""
    text = str(getattr(exc, "reason", None) or exc)
    optional = [m for m in metrics if m not in ANALYTICS_CORE]
    return next((m for m in optional if re.search(rf"\b{m}\b", text)), optional[-1])


def read_retention(perf: dict, at: datetime, analytics=None) -> str | None:
    """Fill the ANALYTICS_FIELDS (retention, engaged views, plays, seconds watched, subscribers gained, likes,
    shares) for each video at least RETENTION_MIN_AGE old from YouTube Analytics (dimensions=video). A metric the
    report refuses (HTTP 400) is dropped alone and named in perf["analytics_dropped"]. Returns one health note when
    it cannot read at all (no scope, HTTP 403, an error), else None."""
    from . import youtube

    old = _old(perf, at)
    if not old:
        return None
    if analytics is None:
        scopes = youtube.scopes()
        if scopes is not None and ANALYTICS_SCOPE not in scopes:
            return "retention: the YouTube sign-in has no yt-analytics.readonly scope; avg_view_pct stays empty"
        analytics = youtube.client("youtubeAnalytics", "v2")
    ids = sorted(old, key=lambda v: old[v]["published_at"], reverse=True)[:ANALYTICS_MAX]
    start, end = _window([old[v]["published_at"] for v in ids], at)
    metrics = ANALYTICS_METRICS.split(",")
    while True:
        try:
            answer = analytics.reports().query(
                ids="channel==MINE", startDate=start, endDate=end, metrics=",".join(metrics),
                dimensions="video", filters="video==" + ",".join(ids), sort="-views", maxResults=len(ids)).execute()
            break
        except Exception as exc:
            if _status(exc) == 400 and any(m not in ANALYTICS_CORE for m in metrics):
                metrics.remove(_refused(exc, metrics))  # a metric this channel's report does not offer
                continue
            if _status(exc) == 403:
                return "retention: YouTube Analytics refused (HTTP 403, no yt-analytics.readonly scope); avg_view_pct stays empty"
            return f"retention: {type(exc).__name__}: {exc}"[:300]
    perf["analytics_dropped"] = [m for m in ANALYTICS_METRICS.split(",") if m not in metrics]
    cols = [c["name"] for c in answer.get("columnHeaders", [])]
    for row in answer.get("rows") or []:
        got = dict(zip(cols, row))
        rec = old.get(got.get("video"))
        if rec is None:
            continue
        for metric, field in ANALYTICS_FIELDS.items():
            if isinstance(got.get(metric), (int, float)):
                rec[field] = round(float(got[metric]), 2) if metric == "averageViewPercentage" else int(got[metric])
    return None


def read_traffic(perf: dict, at: datetime, analytics=None) -> str | None:
    """Where each Short's views came from (YouTube Analytics, dimensions=insightTrafficSourceType, one query a
    Short), into rec[TRAFFIC_FIELD] as {source: views}. Only Shorts at least RETENTION_MIN_AGE old and under
    TRAFFIC_WINDOW, each at most once per TRAFFIC_EVERY, never-read first, at most TRAFFIC_MAX a run. A Short the
    report refuses (HTTP 400) waits TRAFFIC_EVERY; any other error stops the reads and is the one health note."""
    from . import youtube

    due = [(vid, rec) for vid, rec in _old(perf, at).items()
           if at - datetime.fromisoformat(rec["published_at"]) < TRAFFIC_WINDOW
           and (not rec.get("traffic_at") or at - datetime.fromisoformat(rec["traffic_at"]) >= TRAFFIC_EVERY)]
    due.sort(key=lambda d: d[1]["published_at"], reverse=True)
    due.sort(key=lambda d: d[1].get("traffic_at") or "")
    if not due:
        return None
    if analytics is None:
        analytics = youtube.client("youtubeAnalytics", "v2")
    for vid, rec in due[:TRAFFIC_MAX]:
        start, end = _window([rec["published_at"]], at)
        try:
            answer = analytics.reports().query(
                ids="channel==MINE", startDate=start, endDate=end, metrics="views",
                dimensions="insightTrafficSourceType", filters="video==" + vid, sort="-views").execute()
        except Exception as exc:
            if _status(exc) == 400:
                rec["traffic_at"] = at.isoformat(timespec="seconds")
                continue
            return f"traffic: {type(exc).__name__}: {exc}"[:300]
        cols = [c["name"] for c in answer.get("columnHeaders", [])]
        rows = [dict(zip(cols, row)) for row in answer.get("rows") or []]
        rec[TRAFFIC_FIELD] = {str(r["insightTrafficSourceType"]): int(r["views"]) for r in rows
                              if r.get("insightTrafficSourceType") and isinstance(r.get("views"), (int, float))}
        rec["traffic_at"] = at.isoformat(timespec="seconds")
    return None


def refresh(at: datetime | None = None, force: bool = False, api=None, analytics=None) -> dict | None:
    """Read the channel's numbers and relearn, at most once per REFRESH. Returns what was learned, or None if the
    last read is still fresh. analytics: a YouTube Analytics v2 client (default: one from the desk's sign-in)."""
    from . import youtube

    at = at or datetime.now(timezone.utc)
    perf = ledger.load("performance", {"at": None, "videos": {}})
    if not force and perf.get("at") and at - datetime.fromisoformat(perf["at"]) < REFRESH:
        return None
    if api is None:
        api = youtube.client()
    stats = {v["id"]: v.get("statistics", {}) for v in youtube.recent(api, youtube.identity(api))}
    for row in ledger.published():
        vid = row.get("video_id")
        if not vid or vid not in stats or _age_h(row, at) < 0:
            continue
        s = stats[vid]
        rec = perf["videos"].setdefault(vid, {"id": row["id"], "published_at": row["published_at"], "snapshots": []})
        rec.update({f: row.get(f) or rec.get(f) for f in ("kind",) + FEATURES})
        rec["snapshots"] = _thin(rec["snapshots"] + [{
            "age_h": round(_age_h(row, at), 2), "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0))}])
        rec["views_24h"] = views_at(rec["snapshots"], SCORE_AT_H)
    try:
        note = read_retention(perf, at, analytics)
        if note is None:  # the same sign-in and scope: a refused retention read would refuse these too
            note = read_traffic(perf, at, analytics)
    except Exception as exc:  # retention steers the ranking; reading it must never stop the views
        note = f"retention: {type(exc).__name__}: {exc}"[:300]
    perf["at"] = at.isoformat(timespec="seconds")
    perf["learned"] = learn(list(perf["videos"].values()))
    perf["retention_note"] = note
    if note:
        perf["learned"]["retention_note"] = note
    ledger.save("performance", perf)
    (ledger.STATE / "LEARNINGS.md").write_text(report(perf), encoding="utf-8")
    return perf["learned"]
