"""The scorecard: the one file the 14-day reviews read (state/REVIEW.md), written once per IST day.

It joins state/performance.json (desk/learn.py's frozen 6- and 24-hour reads and the YouTube Analytics numbers) to
the ledger's rows and breaks the last WINDOW of scored Shorts down by lane, variant, posting slot (IST) and rank in
the IST day: n, median views at 6 h and 24 h, engaged share (engaged views over plays, pooled), median percentage
viewed and seconds watched, subscribers per 1K plays and per 1K engaged views, the traffic mix, and the share of
Shorts over 1K and 10K views. Each group gets a verdict against the channel's baseline (the median views at 24 h of
the same Shorts, the biggest case left out, and their pooled engaged share and subscriber rate):

- SCALE: median at least SCALE_VIEWS x baseline, or engaged share SCALE_ENGAGED_PTS points above baseline with
  subscribers per 1K engaged views at least SCALE_SUBS x the channel's;
- CUT: median under CUT_VIEWS x baseline and engaged share at or below baseline;
- STOP: a CUT when the last recorded review day's verdict was CUT too ("two cuts in a row");
- HOLD otherwise, and "n<10: no verdict" under MIN_N scored Shorts.

Sensitive cases (lane SENSITIVE; until the ledger carries lanes, any case angle) have their own line, are left out of
every other breakdown, and never get SCALE. Variants are also judged by the variant rule against the window's other
Shorts (KEEP: +5 points of engaged share or 1.5x the subscriber rate, with the median down no more than 30%).

Read-only: it reads the state files and writes only state/REVIEW.md and state/review.json (the IST day it last wrote,
and each review day's verdicts, so a second cut in a row can be told). It changes no constant, ledger row or upload,
and the run calls it after learn.refresh where an error is one health line, never a failed run.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from . import ledger, plan

REVIEW_DAYS = ("2026-11-05", "2026-11-19", "2026-12-03", "2026-12-17", "2026-12-31", "2027-01-14", "2027-01-20")
WINDOW = timedelta(days=28)
MIN_N = 10
SCALE_VIEWS = 1.5
CUT_VIEWS = 0.7
SCALE_ENGAGED_PTS = 5.0
SCALE_SUBS = 1.5
KEEP_VIEWS_DOWN = 0.7  # a variant may cost at most 30% of the median views
SENSITIVE = "sensitive"
UNLABELLED = "unlabelled"
# Posting slots, IST hours [from, to): the buckets of the strategy's hour table, plus the night.
SLOTS = ((0, 6), (6, 8), (8, 9), (9, 12), (12, 14), (14, 18), (18, 20), (20, 24))
RANKS = 4  # rank in the IST day: 1st to 4th, then "5+"
BREAKDOWNS = ("lane", "variant", "slot", "rank")
NO_VERDICT = f"n<{MIN_N}: no verdict"


def lane_of(row: dict) -> str:
    """The row's lane; a row without one (the ledger before lanes) is SENSITIVE if it is a case angle, else
    UNLABELLED. A case left unlabelled can then never scale a lane."""
    return row.get("lane") or (SENSITIVE if row.get("case") else UNLABELLED)


def slot_of(at: datetime) -> str:
    hour = at.astimezone(plan.IST).hour
    lo, hi = next(s for s in SLOTS if s[0] <= hour < s[1])
    return f"{lo:02d}-{hi:02d}"


def shorts(perf: dict, rows: list[dict]) -> list[dict]:
    """Each published Short that performance.json has read, with its breakdown keys and numbers."""
    videos = perf.get("videos", {})
    days: dict[str, int] = {}
    out = []
    for row in sorted(rows, key=lambda r: r["published_at"]):
        at = datetime.fromisoformat(row["published_at"])
        day = plan.ist_day(at)
        days[day] = days.get(day, 0) + 1  # every upload of the day counts, retired or not
        rec = videos.get(row.get("video_id") or "")
        if rec is None:
            continue
        snaps = rec.get("snapshots") or []
        out.append({
            "id": row["id"], "video_id": row["video_id"], "at": at, "case": row.get("case"),
            "lane": lane_of(row), "variant": row.get("variant") or "none", "slot": slot_of(at),
            "rank": str(days[day]) if days[day] <= RANKS else f"{RANKS + 1}+",
            "views_6h": rec.get("views_6h"), "views_24h": rec.get("views_24h"),
            "views": snaps[-1]["views"] if snaps else None, "plays": rec.get("plays"),
            "engaged": rec.get("engaged_views"), "pct": rec.get("avg_view_pct"), "secs": rec.get("avg_view_s"),
            "subs": rec.get("subscribers_gained"), "traffic": rec.get("traffic") or {}})
    return out


def _median(values: list) -> float | None:
    values = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(values) if values else None


def _rate(num: str, den: str, group: list[dict], per: float = 1.0) -> float | None:
    both = [s for s in group if isinstance(s[num], (int, float)) and isinstance(s[den], (int, float))]
    total = sum(s[den] for s in both)
    return sum(s[num] for s in both) / total * per if total else None


def stats(group: list[dict]) -> dict:
    traffic: dict[str, int] = {}
    for s in group:
        for source, views in s["traffic"].items():
            traffic[source] = traffic.get(source, 0) + views
    seen = [s for s in group if isinstance(s["views"], (int, float))]
    return {"n": len(group), "views_6h": _median([s["views_6h"] for s in group]),
            "views_24h": _median([s["views_24h"] for s in group]),
            "engaged": _rate("engaged", "plays", group, 100), "pct": _median([s["pct"] for s in group]),
            "secs": _median([s["secs"] for s in group]), "subs_plays": _rate("subs", "plays", group, 1000),
            "subs_engaged": _rate("subs", "engaged", group, 1000), "traffic": traffic,
            "over_1k": sum(s["views"] >= 1_000 for s in seen) / len(seen) if seen else None,
            "over_10k": sum(s["views"] >= 10_000 for s in seen) / len(seen) if seen else None}


def biggest_case(window: list[dict]) -> str | None:
    """The case whose angles drew the most views in the window: the baseline leaves it out."""
    totals: dict[str, float] = {}
    for s in window:
        if s["case"]:
            totals[s["case"]] = totals.get(s["case"], 0) + (s["views"] or 0)
    return max(totals, key=totals.get) if totals else None


def verdict(g: dict, base: dict, prior: str | None = None, sensitive: bool = False) -> str:
    if g["n"] < MIN_N:
        return NO_VERDICT
    if not base.get("views_24h"):
        return "HOLD (no baseline yet)"
    ratio = g["views_24h"] / base["views_24h"]
    known = g["engaged"] is not None and base["engaged"] is not None
    cut = ratio < CUT_VIEWS and known and g["engaged"] <= base["engaged"]
    held = (known and g["engaged"] >= base["engaged"] + SCALE_ENGAGED_PTS and g["subs_engaged"] is not None
            and base["subs_engaged"] is not None and g["subs_engaged"] > 0
            and g["subs_engaged"] >= SCALE_SUBS * base["subs_engaged"])
    if cut:
        return f"STOP (second cut in a row, median x{ratio:.2f})" if prior in ("CUT", "STOP") \
            else f"CUT (median x{ratio:.2f}, engaged share not above baseline)"
    if ratio >= SCALE_VIEWS or held:
        why = f"median x{ratio:.2f}" if ratio >= SCALE_VIEWS else "engaged share and subscriber rate"
        return f"HOLD (sensitive: never SCALE; {why})" if sensitive else f"SCALE ({why})"
    return f"HOLD (median x{ratio:.2f})"


def keep_variant(g: dict, base: dict) -> str:
    """The variant rule against `base` (the other arm): KEEP with +SCALE_ENGAGED_PTS of engaged share or SCALE_SUBS x
    the subscriber rate, and the median views down no more than 30%. Both arms need MIN_N Shorts."""
    if g["n"] < MIN_N or base["n"] < MIN_N or not base.get("views_24h"):
        return ""
    gain = ((g["engaged"] is not None and base["engaged"] is not None
             and g["engaged"] >= base["engaged"] + SCALE_ENGAGED_PTS)
            or (g["subs_engaged"] is not None and base["subs_engaged"] is not None and g["subs_engaged"] > 0
                and g["subs_engaged"] >= SCALE_SUBS * base["subs_engaged"]))
    return "; KEEP" if gain and g["views_24h"] >= KEEP_VIEWS_DOWN * base["views_24h"] else "; no variant gain"


def period_of(today: str) -> str | None:
    """The latest review day on or before `today` (an IST date), or None before the first."""
    return next((d for d in reversed(REVIEW_DAYS) if d <= today), None)


def scorecard(perf: dict, rows: list[dict], at: datetime, reviews: dict | None = None) -> dict:
    """Every group's numbers and verdict over the WINDOW before `at`. reviews: {review day: {group: verdict}}."""
    reviews = reviews or {}
    today = plan.ist_day(at)
    period = period_of(today)
    before = [d for d in sorted(reviews) if period is None or d < period]
    prior = reviews[before[-1]] if before else {}
    window = [s for s in shorts(perf, rows) if at - WINDOW <= s["at"] <= at and s["views_24h"] is not None]
    big = biggest_case(window)
    base = stats([s for s in window if not (big and s["case"] == big)])
    groups = []
    for key in BREAKDOWNS:
        values: dict[str, list[dict]] = {}
        for s in window:
            if key == "lane" or s["lane"] != SENSITIVE:  # sensitive Shorts are counted on their own line only
                values.setdefault(s[key], []).append(s)
        for value, group in sorted(values.items()):
            g = stats(group)
            name = f"{key}:{value}"
            sensitive = key == "lane" and value == SENSITIVE
            v = verdict(g, base, (prior.get(name) or "").split(" ")[0] or None, sensitive)
            # A variant is weighed against the other Shorts of the window, the arm it is tested against.
            keep = keep_variant(g, stats([s for s in window if s["lane"] != SENSITIVE and s["variant"] != value])) \
                if key == "variant" and value != "none" else ""
            groups.append({"key": key, "value": value, "name": name, "verdict": v, "keep": keep} | g)
    over = sorted((s for s in window if (s["views"] or 0) >= 10_000), key=lambda s: -s["views"])
    return {"at": at, "today": today, "period": period, "prior": before[-1] if before else None, "window": window,
            "big": big, "base": base, "groups": groups, "over_10k": over,
            "dropped": perf.get("analytics_dropped") or [], "note": perf.get("retention_note")}


def _n(v, fmt: str = "{:.0f}") -> str:
    return "-" if v is None else fmt.format(v)


def _mix(traffic: dict) -> str:
    total = sum(traffic.values())
    if not total:
        return "-"
    top = sorted(traffic.items(), key=lambda kv: -kv[1])[:3]
    return ", ".join(f"{k} {v / total:.0%}" for k, v in top)


def render(card: dict) -> str:
    base = card["base"]
    nxt = next((d for d in REVIEW_DAYS if d >= card["today"]), None)
    lines = ["# Scorecard", "",
             f"Written {card['at'].isoformat(timespec='minutes')} for IST day {card['today']}. "
             + (f"Review day today ({nxt}). " if nxt == card["today"] else
                f"Next review day: {nxt}. " if nxt else "The review days are over. ")
             + f"Window: Shorts published in the last {WINDOW.days} days with a 24-hour read ({len(card['window'])}).",
             "",
             f"Baseline ({base['n']} Shorts"
             + (f", the biggest case \"{card['big']}\" left out" if card["big"] else "") + "): "
             f"median {_n(base['views_24h'])} views at 24 h, engaged share {_n(base['engaged'], '{:.1f}')}%, "
             f"{_n(base['subs_engaged'], '{:.2f}')} subscribers per 1K engaged views.",
             "",
             f"Verdicts need {MIN_N} Shorts. SCALE: median at least x{SCALE_VIEWS}, or engaged share "
             f"+{SCALE_ENGAGED_PTS:.0f} points with x{SCALE_SUBS} the subscriber rate. CUT: median under x{CUT_VIEWS} "
             "and engaged share at or below baseline. STOP: a second CUT in a row (against the last recorded review "
             f"day{', ' + card['prior'] if card['prior'] else ''}). Sensitive cases have their own line, are left out "
             "of the other breakdowns and never SCALE. This file changes nothing: the review acts on it.", ""]
    if card["dropped"]:
        lines += [f"YouTube Analytics refused {', '.join(card['dropped'])}: those columns stay empty.", ""]
    if card["note"]:
        lines += [f"Analytics note: {card['note']}", ""]
    head = ("| {} | n | views 6 h | views 24 h | engaged | % viewed | s watched | subs/1K plays | subs/1K engaged "
            "| traffic | >1K | >10K | verdict |")
    for key in BREAKDOWNS:
        lines += [f"## By {key}", "", head.format(key), "|---" * 13 + "|"]
        for g in (g for g in card["groups"] if g["key"] == key):
            lines.append(
                f"| {g['value']} | {g['n']} | {_n(g['views_6h'])} | {_n(g['views_24h'])} "
                f"| {_n(g['engaged'], '{:.1f}%')} | {_n(g['pct'], '{:.1f}%')} | {_n(g['secs'])} "
                f"| {_n(g['subs_plays'], '{:.2f}')} | {_n(g['subs_engaged'], '{:.2f}')} | {_mix(g['traffic'])} "
                f"| {_n(g['over_1k'], '{:.0%}')} | {_n(g['over_10k'], '{:.0%}')} | {g['verdict']}{g['keep']} |")
        lines.append("")
    lines += ["## Over 10K views: check the traffic source and the lane (sensitive cases are never escalated)", ""]
    lines += [f"- {s['id']} ({s['video_id']}): {s['views']} views, lane {s['lane']}, traffic {_mix(s['traffic'])}"
              for s in card["over_10k"]] or ["- none"]
    return "\n".join(lines) + "\n"


def daily(at: datetime | None = None, force: bool = False) -> str | None:
    """Write state/REVIEW.md once per IST day (and record a review day's verdicts the first time it is written on
    or after that day). Returns one health line, or None when today's is already written."""
    at = at or datetime.now(timezone.utc)
    memo = ledger.load("review", {})
    today = plan.ist_day(at)
    if not force and memo.get("day") == today:
        return None
    reviews = memo.get("reviews") or {}
    card = scorecard(ledger.load("performance", {}), ledger.published(), at, reviews)
    ledger.STATE.mkdir(parents=True, exist_ok=True)
    (ledger.STATE / "REVIEW.md").write_text(render(card), encoding="utf-8")
    recorded = bool(card["period"]) and card["period"] not in reviews
    if recorded:
        reviews[card["period"]] = {g["name"]: g["verdict"] for g in card["groups"]}
    ledger.save("review", {"day": today, "reviews": reviews})
    judged = [g for g in card["groups"] if g["verdict"] != NO_VERDICT]
    return (f"review: state/REVIEW.md for {today}, {len(card['window'])} scored Shorts, {len(judged)} groups judged"
            + (f"; review day {card['period']} recorded" if recorded else ""))[:300]
