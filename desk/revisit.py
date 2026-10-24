"""आगे क्या हुआ: when the channel has gone quiet, the latest on a story it already told that viewers watched.

Owner, 2026-10-24: "if no new news is trending then pick the last recent news, example Tiger Shroff, and show what
is the progress, what is happening in that case; similarly other most viral last cases ... I don't want my channel
to be idle for longer time". The channel's most watched Shorts of the last LOOKBACK_DAYS (performance.json) were
the Tiger Shroff case (1,070, 840 and 732 views against a median near 45), Rahul Gandhi (596) and Om Birla (538).

A story comes back only with news: at least gate.OWNERS_NEEDED independent owners' reports published after the
channel's last Short on it, which no earlier Short used, whose headlines name the story's person and share one of
its own words. It is told as a kh- explainer about the same person (`<kh id>-update`), written to lead with what
is new (writer FOLLOW-UP, the earlier titles), and faces every gate a new story does, the photo-freshness gate
included. Revisits rank below every fresh story (REVISIT_FAME) and take regular slots, at most PER_DAY an IST day
and one per story a day.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from collections import Counter

from . import gate, ledger, outlets, stories, wiki

IST = timezone(timedelta(hours=5, minutes=30))
IDLE = timedelta(hours=2)
LOOKBACK_DAYS = 10
# A hit: its best Short has at least MIN_VIEWS views and HIT_TIMES the channel's median over the lookback.
MIN_VIEWS, HIT_TIMES = 100, 2.0
HITS = 6  # stories looked at a run, most watched first
PER_DAY = 2
# The story's own regular follow-up parts (plan.follow_up) cover the hours right after it.
AFTER_LAST = timedelta(hours=12)
SUFFIX = "-update"
REVISIT_FAME = 1  # below every fresh candidate: plan.lineup sorts by priority
INCIDENT_CATS = ("attack", "accident", "disaster", "explosion", "crime", "fire", "flood", "rail", "aviation")
# Words every headline of any story uses: sharing one says nothing about being the same story.
COMMON = set("""news latest update updates says said after before over amid with what when where how will would
about first video watch live today year years month days week report reports new big know here this that their
from into have has been case""".split())
HUMAN = "Q5"


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ist_day(t: datetime) -> str:
    return t.astimezone(IST).date().isoformat()


def views_by_video() -> dict[str, int]:
    """Each published video's latest view count, from performance.json."""
    videos = (ledger.load("performance", {}) or {}).get("videos") or {}
    out = {}
    for vid, v in videos.items():
        snaps = v.get("snapshots") or []
        if snaps:
            out[vid] = int(snaps[-1].get("views") or 0)
    return out


def story_key(row: dict) -> str | None:
    """Rows of one story: a case's Shorts, or explainers about one person or institution."""
    return row.get("case") or row.get("qid")


def hits(rows: list[dict], views: dict[str, int], at: datetime) -> list[dict]:
    """The stories whose Shorts viewers watched most, most watched first: {"key", "qid", "views", "rows"}."""
    recent = [r for r in rows if r.get("video_id") and not r.get("retired_at")
              and at - _at(r["published_at"]) <= timedelta(days=LOOKBACK_DAYS)]
    seen = sorted(views.get(r["video_id"], 0) for r in recent)
    if not seen:
        return []
    median = seen[len(seen) // 2]
    groups: dict[str, list[dict]] = {}
    for r in recent:
        if (k := story_key(r)) and r.get("qid"):
            groups.setdefault(k, []).append(r)
    out = []
    for k, rs in groups.items():
        best = max(views.get(r["video_id"], 0) for r in rs)
        if best >= max(MIN_VIEWS, HIT_TIMES * median):
            out.append({"key": k, "qid": rs[-1]["qid"], "views": best,
                        "rows": sorted(rs, key=lambda r: r["published_at"])})
    return sorted(out, key=lambda h: -h["views"])[:HITS]


def _keys(text: str) -> set[str]:
    """A headline's words as explain.about_story compares them (build_explainer filters the reports with it)."""
    from . import explain

    return explain.keys(text)[0]


def story_words(rows: list[dict], name: str, case: dict | None = None) -> set[str]:
    """The story's own words: its case file's angle words, and words at least two of its earlier Shorts' headlines
    and articles share (one headline's passing words, "morning", "help", are not the story's), less its name and
    words any story uses."""
    texts = list(dict.fromkeys([r.get("article") or "" for r in rows] + [h for r in rows for h in r.get("headlines") or []]))
    shared = Counter(w for t in texts for w in _keys(t))
    words = {w for w, n in shared.items() if n >= 2}
    words |= {k for a in (case or {}).get("angles", []) for w in a.get("words", []) if re.match(r"[A-Za-z]", w)
              for k in _keys(w)}
    return {w for w in words if len(w) >= 4} - _keys(name) - {outlets._stem(w) for w in COMMON}


def fresh_reports(items: list[dict], name: str, words: set[str], since: datetime, used: set[str]) -> list[dict]:
    """Outlet items after `since`, not used before, whose headline names the person (surname at least) and shares
    one of the story's words."""
    last = name.split()[-1]
    out = []
    for i in items:
        if i["url"] in used or _at(i["at"]) <= since:
            continue
        title = i.get("title") or ""
        if not re.search(r"\b" + re.escape(last) + r"\b", title, re.I):
            continue
        if _keys(title) & words:
            out.append(i)
    return out


def due(rows: list[dict], at: datetime) -> bool:
    """The channel has been quiet IDLE and today's revisits are not used up."""
    if not rows:
        return False
    last = max(_at(r["published_at"]) for r in rows)
    today = [r for r in rows if r["id"].endswith(SUFFIX) and ist_day(_at(r["published_at"])) == ist_day(at)]
    return at - last >= IDLE and len(today) < PER_DAY


def candidates(rows: list[dict], at: datetime | None = None, items: list[dict] | None = None,
               views: dict[str, int] | None = None) -> tuple[list[dict], list[str]]:
    """Revisit candidates for this run and a note on each hit story looked at."""
    from . import explain, plan

    at = at or datetime.now(timezone.utc)
    if not due(rows, at):
        return [], []
    found = hits(rows, views if views is not None else views_by_video(), at)
    if not found:
        return [], ["revisit: no story of the last 10 days drew enough views"]
    if items is None:
        items, _ = outlets.recent()
    day = at.astimezone(IST).strftime("%Y%m%d")
    ents = wiki.entities([h["qid"] for h in found])
    out, notes = [], []
    for h in found:
        qid, told = h["qid"], h["rows"]
        sid = f"kh-{day}-{qid}{SUFFIX}"
        ent = ents.get(qid)
        if not ent or ledger.is_done(sid):
            notes.append(f"revisit {h['key']}: " + ("already revisited today" if ent else "no Wikidata item"))
            continue
        last = _at(told[-1]["published_at"])
        if at - last < AFTER_LAST:
            notes.append(f"revisit {h['key']}: last Short {(at - last).total_seconds() / 3600:.0f} h ago")
            continue
        title = wiki.sitelink(ent, "enwiki")
        if not title:
            notes.append(f"revisit {h['key']}: no English Wikipedia article")
            continue
        name = stories.plain_title(wiki.label(ent) or title)
        case = next((c for c in plan.cases(datetime.min.replace(tzinfo=timezone.utc))
                     if c["name"] == told[-1].get("case")), None)
        used = {u for r in told for u in r.get("report_urls") or []}
        words = story_words(told, name, case)
        fresh = fresh_reports(items, name, words, last, used)
        who = outlets.owners(fresh)
        if len(who) < gate.OWNERS_NEEDED:
            notes.append(f"revisit {h['key']} ({h['views']} views): {len(who)} owners reported new news on "
                         f"{name} since its last Short")
            continue
        person = HUMAN in {c["value"] for c in wiki.claims(ent, "P31")}
        cat = told[-1].get("category") or explain.FALLBACK
        ranked = sorted(fresh, key=outlets._rank)
        cand = {"id": sid, "qid": qid, "title": title, "name": name, "phrase": name, "person": person,
                "kind": "explainer", "category": cat,
                "category_hi": "घटना" if cat in INCIDENT_CATS else explain.CATEGORY_HI.get(cat, "समाचार"),
                "story": ranked[0]["title"], "story_keys": sorted(words), "date": at.astimezone(IST).date().isoformat(),
                "news_at": max(i["at"] for i in fresh), "owners": who, "fame": REVISIT_FAME, "news": 0, "views": 0,
                "traffic": 0, "headlines": [i["title"] for i in ranked][:6], "hindi_headlines": [],
                "region": told[-1].get("region") or "india", "india_link": True,
                "label_hi": wiki.common_hindi(ent), "reports": [outlets.compact(i) for i in ranked][:8],
                "via": [f"revisit:{h['key']}"], "top": None, "top_score": 0.0,
                "revisit_of": told[-1]["id"], "earlier": [r.get("title") or "" for r in told][-6:],
                "focus": (f"WHAT HAS HAPPENED SINCE: the channel last told this story on "
                          f"{last.astimezone(IST):%d %B}. Tell only what the REPORTING says is new since then "
                          "(the progress of the case or story: arrests, court, police, statements, a decision), "
                          "and one short line of what it is about. The earlier Shorts' titles are only what was "
                          "already told, never a source: say nothing from them the REPORTING does not say.")}
        if case and case.get("never"):
            cand["never"] = case["never"]
        out.append(cand)
        notes.append(f"revisit {sid}: {len(who)} owners' new reports on {name} ({h['views']} views before)")
    return out, notes
