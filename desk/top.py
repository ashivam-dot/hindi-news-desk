"""India's top stories: where each candidate stands in Google News India's top-stories lists right now.

Owner, 2026-10-15: "it is picking any random news not top most news ... present the highly popular news". Every
3-owner story used to score about the same (fame counted outlets, capped), so a Kenyan Ebola case outranked the
day's lead story. Google News ranks its top stories for India, in English and in Hindi; a story's place in those
lists is the popularity signal this desk publishes by. `mark` gives every candidate `top` ({feed: rank}), `top_score`
(0 for a story in none of the lists) and `top_headlines` (the matching lead headlines, Hindi first: how the biggest
Hindi newsrooms write it). plan.unpopular drops a story that is in no list (unless breaking or very famous), and
plan.priority ranks by place.
"""
from __future__ import annotations

from datetime import datetime

from . import explain, hindi, news, outlets

# Each feed's weight: the front pages lead, the Nation sections count less.
FEEDS = {"IN": 1.0, "IN-hi": 1.0, "IN-nation": 0.6, "IN-hi-nation": 0.6}
TOP_N = 20
OTHERS = 0.5  # a second (third...) list naming the story adds half its weight
HINDI_LEAD_SHARE = 0.4  # a Hindi headline names the story by its Hindi label within its first 40%


def read(now: datetime) -> dict[str, list[dict]] | None:
    """Each list's top TOP_N lead stories; None when no list could be read (then no story is marked)."""
    out, ok = {}, False
    for feed in FEEDS:
        try:
            out[feed] = [h for h in news.headlines(feed, now) if h.get("rank", TOP_N + 1) <= TOP_N]
            ok = True
        except Exception:
            out[feed] = []
    return out if ok else None


def weight(feed: str, rank: int) -> float:
    return FEEDS.get(feed, 0.5) * max(0.0, (TOP_N + 1 - rank) / TOP_N)


def score(ranks: dict[str, int]) -> float:
    ws = sorted((weight(f, r) for f, r in ranks.items()), reverse=True)
    return round(ws[0] + OTHERS * sum(ws[1:]), 3) if ws else 0.0


def _distinct(word: str) -> bool:
    return word not in outlets.GENERIC and word not in explain.INSTITUTIONS


def same_en(a: str, b: str) -> bool:
    """Two English headlines tell one story: they share two distinctive words (not countries, institutions or
    leaders named in many stories), one of them a name, or four words of any kind."""
    ka, na, la = outlets.headline_keys(a)
    kb, nb, lb = outlets.headline_keys(b)
    shared = {k for k in ka & kb if k not in outlets.GENERIC}
    distinct = {k for k in shared if _distinct(k)}
    names = na | nb | {x for x in (la, lb) if x}
    return (len(distinct) >= 2 and bool(distinct & names)) or len(shared) >= 4


def _labels(cand: dict) -> list[str]:
    """Hindi names that point at the candidate on their own: a person's or event's label, never an institution's
    (सुप्रीम कोर्ट is in many stories a day)."""
    phrase = (cand.get("phrase") or "").lower()
    if phrase in explain.ALIASES or phrase in explain.INSTITUTIONS:
        return []
    return explain.hindi_names_of(cand.get("label_hi"))


def leads_with(headline: str, label: str) -> bool:
    """The Hindi headline names label early: it is about label, not just mentioning it ("... राहुल गांधी ने कहा")."""
    if not hindi.contains(headline, label):
        return False
    at = hindi.norm(headline).find(hindi.norm(label))
    return 0 <= at <= HINDI_LEAD_SHARE * len(hindi.norm(headline))


def matches(cand: dict, lead: dict) -> bool:
    title = lead["title"]
    if lead["feed"] in news.HINDI_FEEDS:
        if title in (cand.get("hindi_headlines") or []):
            return True
        return any(leads_with(title, label) for label in _labels(cand))
    own = [t for t in [cand.get("story"), cand.get("title"), *(cand.get("headlines") or [])] if t]
    return title in own or any(same_en(title, t) for t in own)


def mark(cands: list[dict], lists: dict[str, list[dict]] | None) -> None:
    """Give every candidate its place in today's top-stories lists (see the module docstring)."""
    for c in cands:
        if lists is None:
            c["top"], c["top_score"], c["top_headlines"] = None, None, []
            continue
        ranks, heads = {}, []
        for feed, rows in lists.items():
            for h in rows:
                if matches(c, h):
                    ranks[feed] = min(ranks.get(feed, h["rank"]), h["rank"])
                    heads.append((feed not in news.HINDI_FEEDS, h["rank"], h["title"]))
        c["top"], c["top_score"] = ranks, score(ranks)
        c["top_headlines"] = list(dict.fromkeys(t for _, _, t in sorted(heads)))[:4]
