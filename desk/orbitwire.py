"""Not duplicating Orbitwire, the English sister channel (repo ashivam-dot/rebuilt-in-3d).

Orbitwire's ledger is public on its `state` branch. Its story ids look like `wk-<Wikidata QID>` with optional
suffixes (`wk-Q123-2026w41`, `wk-Q123-p2`), so stories are matched on the QID. A story is shared when Orbitwire
published that QID in the last SHARED_DAYS days (or has it scheduled), or when it is Orbitwire's current top
candidate. A shared story is skipped unless it is high-profile; a high-profile one is told differently: another
angle, other photos, a Hindi hook and title of its own, and at least GAP after Orbitwire's release.

Orbitwire ranks photos deterministically (media.find(title, ent, limit=10, extra_qids=...) on its HEAD); the same
ranking is run here with a margin (POOL > 10) and every file in it is excluded.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from . import config, net

SHARED_DAYS = 7
GAP = timedelta(hours=3)
HIGH_FAME = 400_000
HIGH_PERCENTILE = 0.9
PERCENTILE_FLOOR = 100_000
HINDI_LEADS = 3
INDIA_FAME = 25_000
POOL = 12
QID = re.compile(r"^wk-(Q\d+)(?:-|$)")

ANGLES = {
    "india": {"label": "भारत से कनेक्शन", "title": ("भारत",),
              "brief": "Tell this story through its connection to India and what it means for India: the Indian "
                       "people, places, organisations or reactions that the SOURCE names. Beat 1 hooks with that India "
                       "link, and the title names India (भारत)."},
    "timeline": {"label": "कब क्या हुआ", "title": ("कब क्या", "टाइमलाइन", "सफ़र", "सफर", "पड़ाव"),
                 "brief": "Tell it as a clear timeline: each beat is one dated step from the SOURCE, in order, and its "
                          "caption is that date or year. The title says it is a timeline (कब क्या हुआ, सफ़र or "
                          "पड़ाव)."},
    "explainer": {"label": "पूरा मामला", "title": ("क्यों", "पूरा मामला", "समझिए", "मामला"),
                  "brief": "Explain the background a viewer needs and why it happened, only as the SOURCE states it "
                           "(never guess at a cause). The title promises the full story (पूरा मामला) or asks why "
                           "(क्यों)."},
    "next": {"label": "आगे क्या", "title": ("आगे क्या", "आगे"),
             "brief": "Focus on what happens next: investigations, decisions, deadlines and open questions that the "
                      "SOURCE names. The title says आगे क्या."},
}
# The angles each kind of story may take, in order of preference after the India angle.
BY_KIND = {"death": ("timeline",), "incident": ("explainer", "timeline", "next"),
           "protest": ("explainer", "next", "timeline")}


def qid_of(story_id: str) -> str | None:
    m = QID.match(story_id or "")
    return m.group(1) if m else None


def fetch() -> dict:
    """Orbitwire's published.json and candidates.json. Raises when they can't be read: the desk then fails closed."""
    published = json.loads(net.get(f"{config.ORBITWIRE_STATE}/published.json", tries=3, timeout=30))
    candidates = json.loads(net.get(f"{config.ORBITWIRE_STATE}/candidates.json", tries=3, timeout=30))
    if not isinstance(published, list):
        raise ValueError("Orbitwire's published.json is not a list")
    if not isinstance(candidates, dict):
        raise ValueError("Orbitwire's candidates.json is not an object")
    return {"published": published, "candidates": candidates}


def _at(value: str) -> datetime:
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _same(row: dict, qid: str | None, ids: set[str], urls: set[str] | None = None) -> bool:
    """One story: the same Wikidata item, or the same article id (a story told before Wikidata knew it is `wp-<title>`
    on both channels, and Orbitwire records the article it told), or the same outlet story (nw- ids naming one place
    and kind, or a trusted outlet's report URL both used)."""
    from .outlets import same_story

    rid = row.get("id", "")
    outlet_story = rid.startswith("nw-") or any(i.startswith("nw-") for i in ids)
    return bool((qid and (row.get("qid") or qid_of(rid)) == qid) or rid in ids
                or (row.get("article") and article_id(row["article"]) in ids)
                or any(same_story(rid, i) for i in ids)
                or (outlet_story and urls and urls & set(row.get("report_urls") or [])))


def article_id(title: str) -> str:
    from .trends import article_id as aid

    return aid(title)


def overlap(qid: str | None, state: dict, at: datetime, title: str | None = None,
            story_id: str | None = None, reports: list[str] | None = None) -> dict | None:
    """What Orbitwire did with this story (by QID, by article for a story Wikidata did not know yet, or by outlet story
    for one Wikipedia has no article for: an nw- id or a report URL): its newest release in the last SHARED_DAYS days
    (or a scheduled one), else whether it is Orbitwire's current top candidate; None when the story is not shared."""
    ids = {i for i in (story_id, article_id(title) if title else None) if i and i.startswith(("wp-", "nw-"))}
    urls = set(reports or [])
    if not qid and not ids and not urls:
        return None
    rows = []
    for r in state.get("published", []):
        try:
            when = _at(r["published_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if _same(r, qid, ids, urls) and at - when < timedelta(days=SHARED_DAYS):
            rows.append((when, r))
    if rows:
        when, r = max(rows, key=lambda x: x[0])
        return {"qid": qid, "status": "scheduled" if when > at else "published", "orbitwire_id": r.get("id"),
                "orbitwire_published_at": when.isoformat(timespec="seconds"), "orbitwire_url": r.get("url"),
                "orbitwire_title": r.get("title")}
    top = (state.get("candidates", {}).get("candidates") or [None])[0]
    if top and _same({"id": top.get("id", ""), "qid": top.get("qid"), "article": top.get("title"),
                      "report_urls": [r.get("url") for r in top.get("reports") or []]}, qid, ids, urls):
        return {"qid": qid, "status": "top_candidate", "orbitwire_id": top.get("id"), "orbitwire_published_at": None,
                "orbitwire_url": None, "orbitwire_title": top.get("title"),
                "orbitwire_seen_at": state["candidates"].get("at")}
    return None


def high_profile(cand: dict, all_fame: list[float]) -> str | None:
    """Why a shared story is big enough to be told again in Hindi, or None."""
    fame = cand.get("fame", 0)
    if fame >= HIGH_FAME:
        return f"fame {fame:,.0f} >= {HIGH_FAME:,}"
    if len(all_fame) >= 10 and fame >= PERCENTILE_FLOOR:
        ranked = sorted(all_fame)
        cut = ranked[min(len(ranked) - 1, int(HIGH_PERCENTILE * len(ranked)))]
        if fame >= cut:
            return f"fame {fame:,.0f} in the top {100 - int(HIGH_PERCENTILE * 100)}% of this run"
    if cand.get("region") == "india" and cand.get("hindi_news", 0) >= HINDI_LEADS:
        return f"an India story with {cand['hindi_news']} Hindi lead headlines"
    if cand.get("region") == "india" and fame >= INDIA_FAME:
        return f"an India story (fame {fame:,.0f}): Hindi viewers are not Orbitwire's English audience"
    return None


def angle_for(kind: str, india_link: bool) -> str:
    if india_link:
        return "india"
    return BY_KIND.get(kind, BY_KIND["incident"])[0]


def title_fits(title: str, angle: str) -> bool:
    from .hindi import norm

    return any(norm(w) in norm(title) for w in ANGLES[angle]["title"])


def wait(ov: dict | None, at: datetime) -> str | None:
    """Why a shared story must wait before this desk publishes it, or None."""
    if not ov:
        return None
    if ov["status"] == "top_candidate":
        return "Orbitwire's top candidate: waiting for its release, then 3 h"
    released = _at(ov["orbitwire_published_at"])
    if at - released < GAP:
        return f"Orbitwire released it at {ov['orbitwire_published_at']}; the Hindi Short waits until 3 h after"
    return None


def photo_pool(title: str, ent: dict, extra_qids: list[str] | None = None,
               context_qids: list[str] | None = None) -> list[str]:
    """The Commons files Orbitwire's own ranking would draw from for this story (with a margin), and the photos of
    the story's places it may fill in with when its own are too few."""
    from . import media

    pool = [p.file for p in media.find(title, ent, limit=POOL, extra_qids=extra_qids, places=not ent)] if title else []
    pool += [p.file for p in media.context(context_qids or [], limit=POOL) if p.file not in pool]
    try:
        pool += [p.file for p in media.openverse_for(context_qids or [], limit=POOL) if p.file not in pool]
    except Exception:
        pass
    return pool
