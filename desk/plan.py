"""The editorial desk: which story to make next, and whether the channel may publish now.

The channel covers what India and the world are already looking at (see CHANNEL.md): incidents, protests and
movements that newsrooms lead with, famous deaths, and big earthquakes. India stories come first, then world stories
with an India connection, then the rest.

Timing is the channel: a story goes out while people are looking at it, not hours later. Priority is fame (Google
News lead stories in English and Hindi, Google Trends traffic, Wikipedia views) decayed by age, times the India boost,
so a fresh story beats a bigger stale one. A story older than STALE_H is dropped unless a live signal (Google Trends
traffic, or a lead headline under LIVE_NEWS_H old) shows it is trending right now; Wikipedia's most-read list is a
day behind and never keeps an old story alive. Regular Shorts go out 07:00-24:00 IST as soon as they are made, at
most MAX_PER_DAY an IST day and MIN_GAP apart. A breaking story (huge fame and under 12 hours old, or a quake USGS
rates orange or red or magnitude 7+) goes out at any hour with no gap, up to BREAKING_EXTRA beyond the cap; wars never
take the breaking lane. An ongoing story comes back at most once in COOLDOWN_DAYS, however its id changes. No more
than two loss stories in any three consecutive uploads. Stories Orbitwire covers are skipped or told differently
(desk/orbitwire.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import ledger, orbitwire, trends, usgs
from .stories import km_between

IST = timezone(timedelta(hours=5, minutes=30))
MAX_PER_DAY = 10
BREAKING_EXTRA = 2  # set to 0 to make MAX_PER_DAY a hard cap even for breaking news
MIN_GAP = timedelta(minutes=30)
BREAKING_GAP = timedelta(0)
BREAKING_FAME = 400_000
BREAKING_MAX_AGE_H = 12
STALE_H = 48
LIVE_NEWS_H = 24
HALF_LIFE_H = {"death": 36, "protest": 18, "movement": 18, "conflict": 12, "earthquake": 18}
DEFAULT_HALF_LIFE_H = 24
WINDOW_IST = (7.0, 24.0)
INDIA_BOOST, LINK_BOOST = 1.6, 1.25
QUAKE_BIG_MAG = 7.0
COOLDOWN_DAYS = {"protest": 6, "movement": 6}


def ist_day(t: datetime) -> str:
    return t.astimezone(IST).date().isoformat()


def can_publish(at: datetime | None = None, breaking: bool = False) -> str | None:
    at = at or datetime.now(timezone.utc)
    rows = ledger.published()
    today = [r for r in rows if ist_day(datetime.fromisoformat(r["published_at"])) == ist_day(at)]
    if len(today) >= MAX_PER_DAY + (BREAKING_EXTRA if breaking else 0):
        return f"already {len(today)} Shorts today (IST)"
    gap = BREAKING_GAP if breaking else MIN_GAP
    times = [datetime.fromisoformat(r["published_at"]) for r in rows]
    past, scheduled = [t for t in times if t <= at], [t for t in times if t > at]
    if past and at - max(past) < gap:
        return f"last Short went out {(at - max(past)).total_seconds() / 3600:.1f} h ago"
    if scheduled and min(scheduled) - at < gap:
        return f"a scheduled Short goes out in {(min(scheduled) - at).total_seconds() / 3600:.1f} h"
    return None


def age_hours(cand: dict, at: datetime) -> float:
    """Hours since the story broke. An ongoing story is as old as its newest lead headline; any other story is as old
    as the event itself, however fresh a follow-up headline is."""
    if cand.get("age_h") is not None:
        return float(cand["age_h"])
    ages = []
    if cand.get("news_at"):
        ages.append((at - datetime.fromisoformat(cand["news_at"])).total_seconds() / 3600)
    if cand.get("date") and cand.get("category") not in trends.ONGOING:
        day = datetime.fromisoformat(cand["date"]).replace(tzinfo=timezone.utc) + timedelta(hours=12)
        ages.append((at - day).total_seconds() / 3600)
    return max([0.0, *ages])


def boost(cand: dict) -> float:
    if cand.get("region") == "india":
        return INDIA_BOOST
    return LINK_BOOST if cand.get("india_link") else 1.0


def priority(cand: dict, at: datetime) -> float:
    """Fame halved every half-life, times the India boost and the channel's own learned lift: what this desk would
    lead with right now."""
    from . import learn

    half = HALF_LIFE_H.get(cand.get("kind"), HALF_LIFE_H.get(cand.get("category"), DEFAULT_HALF_LIFE_H))
    return cand.get("fame", 0) * 0.5 ** (age_hours(cand, at) / half) * boost(cand) * learn.factor(cand)


def is_breaking(cand: dict, at: datetime) -> bool:
    if age_hours(cand, at) > BREAKING_MAX_AGE_H or cand.get("category") == "conflict":
        return False
    if cand.get("category") == "earthquake" and cand.get("mag"):
        return cand.get("mag", 0) >= QUAKE_BIG_MAG or (cand.get("alert") or "") in ("orange", "red")
    return cand.get("fame", 0) >= BREAKING_FAME


def cooling(cand: dict, at: datetime, rows: list[dict]) -> bool:
    """True when this ongoing story already went out within its cool-down, under any id (weekly or series part)."""
    days = COOLDOWN_DAYS.get(cand.get("category"))
    if not days or not cand.get("qid"):
        return False
    stem = f"wk-{cand['qid']}"
    return any(r["id"] == stem or r["id"].startswith(stem + "-")
               for r in rows if at - datetime.fromisoformat(r["published_at"]) < timedelta(days=days))


def in_window(at: datetime) -> bool:
    local = at.astimezone(IST)
    hour = local.hour + local.minute / 60
    return WINDOW_IST[0] <= hour < WINDOW_IST[1]


def trending_live(cand: dict, at: datetime) -> bool:
    if cand.get("traffic", 0) > 0:
        return True
    news_at = cand.get("news_at")
    return bool(news_at) and (at - datetime.fromisoformat(news_at)).total_seconds() / 3600 <= LIVE_NEWS_H


def stale(cand: dict, at: datetime) -> str | None:
    """Why a story has missed its moment, or None while people are still looking at it."""
    age = age_hours(cand, at)
    if age <= STALE_H or trending_live(cand, at):
        return None
    return f"{age:.0f} h old and no longer trending live"


def lineup(cands: list[dict], at: datetime | None = None) -> tuple[list[dict], list[str]]:
    """Candidates the desk would publish now, best first, and a note for each one it is holding back or dropping."""
    at = at or datetime.now(timezone.utc)
    regular, urgent = can_publish(at), can_publish(at, breaking=True)
    ready, notes = [], []
    for c in sorted(cands, key=lambda c: -priority(c, at)):
        if why := stale(c, at):
            notes.append(f"drop {c['id']}: {why}")
            continue
        breaking = is_breaking(c, at)
        wait = urgent if breaking else regular or (None if in_window(at) else "outside 07:00-24:00 IST")
        wait = wait or orbitwire.wait(c.get("orbitwire"), at)
        if wait:
            notes.append(f"hold {c['id']}: {wait}")
        else:
            ready.append(c | {"breaking": breaking, "priority": round(priority(c, at))})
    return ready, notes


def _quake_facts(cands: list[dict]) -> list[str]:
    """Give trending earthquake stories their USGS magnitude and PAGER alert (they decide the breaking lane)."""
    try:
        quakes = [q for q in usgs.recent() if q.mag >= 6.0]
    except Exception as exc:
        return [f"usgs: {type(exc).__name__}: {exc}"[:200]]
    for c in cands:
        if c.get("category") != "earthquake" or not c.get("coords") or not c.get("date"):
            continue
        day = datetime.fromisoformat(c["date"]).date()
        match = [q for q in quakes if abs((q.time.date() - day).days) <= 1
                 and km_between(tuple(c["coords"]), (q.lat, q.lon)) < 300]
        if match:
            q = max(match, key=lambda q: q.mag)
            c.update(mag=q.mag, alert=q.alert, usgs=q.url)
    return []


def apply_orbitwire(cands: list[dict], at: datetime) -> tuple[list[dict], list[str]]:
    """Skip what Orbitwire covers unless it is high-profile; mark the high-profile shared stories for a new angle."""
    try:
        state = orbitwire.fetch()
    except Exception as exc:
        # Without Orbitwire's ledger the desk cannot tell what it would duplicate: hold everything this run.
        return [], [f"hold all: Orbitwire's state is unreadable ({type(exc).__name__}: {exc})"[:300]]
    fame = [c.get("fame", 0) for c in cands]
    kept, notes = [], []
    for c in cands:
        ov = orbitwire.overlap(c.get("qid"), state, at)
        if not ov:
            kept.append(c)
            continue
        why = high_profile(c, fame)
        if not why:
            notes.append(f"skip {c['id']}: Orbitwire {ov['status'].replace('_', ' ')} ({ov['orbitwire_id']}), not "
                         f"high-profile enough to tell again")
            continue
        kind = "protest" if c.get("category") in trends.ONGOING else c.get("kind", "incident")
        ov |= {"high_profile": why, "angle": orbitwire.angle_for(kind, bool(c.get("india_link")))}
        kept.append(c | {"orbitwire": ov})
    return kept, notes


def high_profile(cand: dict, fame: list[float]) -> str | None:
    return orbitwire.high_profile(cand, fame)


def watch(save: bool = True) -> dict:
    """Everything the watcher sees this run, written to state/candidates.json for the record (unless save=False)."""
    found = {"at": ledger.now(), "trending": [], "candidates": [], "notes": []}
    try:
        radar = trends.radar()
        found["trending"] = radar["candidates"]
        if radar["errors"]:
            found["trend_errors"] = radar["errors"]
    except Exception as exc:
        found["trend_errors"] = [f"{type(exc).__name__}: {exc}"[:200]]
    found["notes"] += _quake_facts(found["trending"])
    at = datetime.now(timezone.utc)
    rows = ledger.published()
    stories = [c for c in found["trending"] if not ledger.is_done(c["id"]) and not cooling(c, at, rows)
               and not ledger.is_done(trends.article_id(c["title"]))]
    stories, notes = apply_orbitwire(stories, at)
    found["notes"] += notes
    found["candidates"] = sorted(stories, key=lambda c: -priority(c, at))
    if save:
        ledger.save("candidates", found)
    return found
