"""Trend radar: which famous, fresh stories the world is looking at right now.

Fame comes from three public signals: Google News lead stories in India (English and Hindi), the US and the world
(minutes old), Google Trends trending searches in India, the US and the UK (hourly) and English Wikipedia's most-read
articles (daily). Each hit is resolved to a Wikipedia article and its Wikidata item, then classified. Three shapes of story
pass: a recent incident, a protest or public movement that newsrooms are leading with, or the recent death of a
famous person. Sport, celebrity gossip, party politics and crime trials are ignored by design.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from . import net, news, wiki

GEOS = ("IN", "US", "GB")
INDIA = "Q668"
# Protests and movements are ongoing: they qualify while lead stories are about them, unless they have ended or began
# long ago (an ideology or an old movement is not news because a headline mentions it). A war is not: a months-old
# war always has headlines, and its Shorts became generic "human cost" pieces. New strikes and attacks in a war still
# qualify as incidents through their own articles.
ONGOING = ("protest", "movement")
ONGOING_MAX_YEARS = 2
ONGOING_MIN_HEADLINES = 2
TRENDS_RSS = "https://trends.google.com/trending/rss?geo={geo}"
HT = "{https://trends.google.com/trending/rss}"
TOP_N = 400
# A story Wikipedia's editors list on today's or yesterday's Current events page counts like two lead headlines.
PORTAL_FAME = 50000
PORTAL_LEADS = 2
INCIDENT_MAX_DAYS = 30
DEATH_MAX_DAYS = 10
SUICIDE = "Q10737"


def google_trends(geo: str) -> list[dict]:
    root = ET.fromstring(net.get(TRENDS_RSS.format(geo=geo), tries=2))
    out = []
    for item in root.iter("item"):
        traffic = re.sub(r"[^\d]", "", item.findtext(f"{HT}approx_traffic") or "0") or "0"
        news = [n.findtext(f"{HT}news_item_title") or "" for n in item.iter(f"{HT}news_item")]
        out.append({"query": item.findtext("title") or "", "traffic": int(traffic), "geo": geo, "news": news[:3]})
    return out


def _signals() -> tuple[dict[str, dict], list[str]]:
    """title -> {views, traffic, via}; plus any errors (one failed source must not stop the radar)."""
    hits: dict[str, dict] = {}
    errors = []
    try:
        day, top = wiki.top_articles()
        for title, views in top[:TOP_N]:
            hits.setdefault(title, {"views": 0, "traffic": 0, "via": []})
            hits[title]["views"] = views
            hits[title]["via"].append(f"wikipedia-top-{day.isoformat()}")
    except Exception as exc:
        errors.append(f"wikipedia top: {exc}"[:200])
    for geo in GEOS:
        try:
            trends = google_trends(geo)
        except Exception as exc:
            errors.append(f"google trends {geo}: {exc}"[:200])
            continue
        for t in trends:
            if t["traffic"] < 1000:
                continue
            try:
                title = _resolve(t["query"])
            except Exception:
                continue
            if not title:
                continue
            h = hits.setdefault(title, {"views": 0, "traffic": 0, "via": []})
            h["traffic"] += t["traffic"]
            h["via"].append(f"google-trends-{geo}:{t['query']}")
            h.setdefault("geos", set()).add(geo)
    now = datetime.now(timezone.utc)
    for back in (1, 0):
        day = now.date() - timedelta(days=back)
        try:
            listed = wiki.current_events(day)
        except Exception as exc:
            errors.append(f"wikipedia current events {day}: {exc}"[:200])
            continue
        live_at = min(now, datetime.combine(day + timedelta(days=1), datetime.min.time(), timezone.utc)).isoformat()
        for title, india in listed:
            h = hits.setdefault(title, {"views": 0, "traffic": 0, "via": []})
            h["portal"] = h.get("portal", 0) + PORTAL_FAME
            h["portal_at"] = max(h.get("portal_at", live_at), live_at)
            h["via"].append(f"wikipedia-current-events-{day}")
            if india:
                h.setdefault("geos", set()).add("IN")
    try:
        lead, news_errors = news.signals()
        errors += news_errors
    except Exception as exc:
        lead = {}
        errors.append(f"google news: {exc}"[:200])
    for title, n in lead.items():
        h = hits.setdefault(title, {"views": 0, "traffic": 0, "via": []})
        h["news"], h["news_at"], h["headlines"] = n["news"], n["news_at"], n["headlines"][:5]
        h["hindi_news"], h["hindi_headlines"] = n.get("hindi_news", 0), n.get("hindi_headlines", [])[:5]
        h.setdefault("geos", set()).update(n["geos"])
        h["via"] += [f"google-news:{t}" for t in (n["headlines"] + n.get("hindi_headlines", []))[:3]]
    return hits, errors


def _resolve(query: str) -> str | None:
    """The English Wikipedia article a trending search is about; a Devanagari search goes through Hindi Wikipedia."""
    if re.search(r"[\u0900-\u097f]", query):
        hi = wiki.search(query, lang="hi")
        return wiki.hi_to_en([hi]).get(hi) if hi else None
    return wiki.search(query)


def region(ent: dict, geos: set[str]) -> str:
    """'india' for stories about India (Wikidata country or citizenship, or only Indian signals), else 'world'."""
    countries = {c["value"] for pid in ("P17", "P27", "P495") for c in wiki.claims(ent, pid)}
    return "india" if INDIA in countries or (geos and geos <= {"IN"}) else "world"


def india_link(ent: dict, geos: set[str], hindi_news: int = 0) -> bool:
    """A world story with a link to India: Wikidata points at India anywhere in its claims, or Indian newsrooms or
    searches lead with it, or Hindi newsrooms do."""
    linked = any(c["value"] == INDIA for pid in ent.get("claims", {}) for c in wiki.claims(ent, pid))
    return linked or "IN" in geos or hindi_news > 0


def _event_date(ent: dict) -> date | None:
    for pid in ("P585", "P580"):
        for c in wiki.claims(ent, pid):
            d = wiki.wd_time(c["value"])
            if d:
                return d
    return None


def _year(value: str) -> int | None:
    m = re.match(r"\+(\d{4})", value or "")
    return int(m.group(1)) if m else None


def is_current(ent: dict, cat: str, today: date) -> bool:
    """An ongoing story is current unless Wikidata says it ended, or it began more than ONGOING_MAX_YEARS ago.
    A movement or war must have a start date at all, so ideologies and long-standing causes stay out."""
    for c in wiki.claims(ent, "P582") + wiki.claims(ent, "P576"):
        end, year = wiki.wd_time(c["value"]), _year(c["value"])
        if (end and end < today) or (year and year < today.year):
            return False
    started = [y for pid in ("P580", "P571", "P585") for c in wiki.claims(ent, pid) if (y := _year(c["value"]))]
    if not started:
        return cat == "protest"
    return today.year - max(started) <= ONGOING_MAX_YEARS


def story_id(qid: str, cat: str, when: date) -> str:
    """One id per story; an ongoing story may come back once per ISO week while newsrooms keep leading with it."""
    if cat not in ONGOING:
        return f"wk-{qid}"
    year, week, _ = when.isocalendar()
    return f"wk-{qid}-{year}w{week:02d}"


def candidate(title: str) -> dict:
    """One article as a candidate, without the trend and freshness filters (for making a chosen story by hand)."""
    page = wiki.page_info([title]).get(title)
    if not page or not page.get("qid"):
        raise ValueError(f"no Wikidata item for {title!r}")
    cats = wiki.classify([page["qid"]])[page["qid"]]
    ent = wiki.entities([page["qid"]])[page["qid"]]
    base = {"qid": page["qid"], "title": page["title"], "id": f"wk-{page['qid']}", "fame": 0, "via": ["manual"],
            "region": region(ent, set()), "india_link": india_link(ent, set()), "label_hi": wiki.label(ent, "hi")}
    if "human" in cats:
        return base | {"kind": "death", "category": "death"}
    cat = next((c for c in ORDER if c in cats), None)
    if not cat:
        raise ValueError(f"{title!r} is neither an incident nor a person ({sorted(cats)})")
    today = datetime.now(timezone.utc).date()
    return base | {"id": story_id(page["qid"], cat, today), "kind": "incident", "category": cat}


ORDER = ("aviation", "attack", "explosion", "rail", "maritime", "strike", "earthquake", "cyclone", "volcano", "flood",
         "wildfire", "landslide", "tsunami", "conflict", "disaster", "accident", "protest", "movement")

# A brand-new event article often has no Wikidata item (or no instance-of) for its first day, exactly while the story
# is hottest. Such an article still qualifies when its English title names the current year and one of these shapes,
# the way Wikipedia titles events ("2026 Erie shooting", "2026 anti-CEC protests"). Riots, trials and elections stay out.
TITLE_KINDS = (
    (r"\bflight \d+\b|\b(air|plane|aircraft|helicopter|jet) ?crash", "aviation"),
    (r"\b(shootings?|stabbings?|bombings?|massacre|attacks?|airstrikes?|missile strikes?|drone strikes?)\b", "attack"),
    (r"\b(explosions?|blasts?)\b", "explosion"),
    (r"\bderailment\b|\btrain (crash|collision|accident)\b", "rail"),
    (r"\b(ferry|boat|ship) (sinking|capsizing|disaster|accident)\b|\bsinking of\b", "maritime"),
    (r"\bearthquakes?\b", "earthquake"),
    (r"\b(cyclone|hurricane|typhoon|tropical storm)\b", "cyclone"),
    (r"\beruptions?\b", "volcano"),
    (r"\b(floods?|flooding|cloudbursts?)\b", "flood"),
    (r"\b(wild|bush|forest) ?fires?\b", "wildfire"),
    (r"\b(landslides?|mudslides?|avalanches?)\b", "landslide"),
    (r"\b(stampede|crowd crush|(building|bridge|dam) collapse|fire)\b", "disaster"),
    (r"\b(bus|road|boat) (crash|accident)\b", "accident"),
    (r"\b(protests?|demonstrations?)\b", "protest"),
)
TITLE_SKIP = r"\b(riots?|trials?|elections?|by-?elections?|referendum|season|tournament|championship|cup|league|film|series)\b"


def title_kind(title: str, today: date) -> str | None:
    """The category a fresh event article's title names, or None (see TITLE_KINDS)."""
    if not re.search(rf"\b({today.year}|{today.year - 1})\b", title) or re.search(TITLE_SKIP, title, re.I):
        return None
    return next((cat for pattern, cat in TITLE_KINDS if re.search(pattern, title, re.I)), None)


def article_id(title: str) -> str:
    """The id of a story told from an article Wikidata did not know yet; kept so it never comes back as wk-<QID>."""
    return "wp-" + re.sub(r"[^\w-]+", "_", title).strip("_")


def radar(today: date | None = None) -> dict:
    """Trending candidates, ranked by fame. Written to state/trends.json by the caller."""
    today = today or datetime.now(timezone.utc).date()
    hits, errors = _signals()
    try:
        info = wiki.page_info(list(hits))
        qids = sorted({i["qid"] for i in info.values() if i.get("qid")})
        kinds = wiki.classify(qids) if qids else {}
        for page in info.values():
            if page.get("qid") and not kinds.get(page["qid"]) and (cat := title_kind(page["title"], today)):
                kinds[page["qid"]] = {cat, "by-title"}
        relevant = [q for q in qids if kinds.get(q)]
        ents = wiki.entities(relevant) if relevant else {}
    except Exception as exc:
        errors.append(f"wikidata: {exc}"[:200])
        return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "candidates": [], "errors": errors,
                "scanned": len(hits)}
    out, seen = [], set()
    for title, h in hits.items():
        page = info.get(title)
        if not page:
            continue
        if not page.get("qid"):
            cat = title_kind(page["title"], today)
            if not cat or page["title"] in seen:
                continue
            qid, cats, ent = None, {cat, "by-title"}, {}
            seen.add(page["title"])
        else:
            qid, cats = page["qid"], kinds.get(page["qid"], set())
            ent = ents.get(qid)
            if qid in seen or not cats or not ent:
                continue
            seen.add(qid)
        fame = h["views"] + h["traffic"] + h.get("news", 0) + h.get("portal", 0)
        geos = h.get("geos", set())
        news_at = max(filter(None, (h.get("news_at"), h.get("portal_at"))), default=None)
        base = {"qid": qid, "title": page["title"], "fame": fame, "views": h["views"], "traffic": h["traffic"],
                "news": h.get("news", 0), "news_at": news_at, "headlines": h.get("headlines", []),
                "hindi_news": h.get("hindi_news", 0), "hindi_headlines": h.get("hindi_headlines", []),
                "region": region(ent, geos), "india_link": india_link(ent, geos, h.get("hindi_news", 0)),
                "geos": sorted(geos), "label_hi": wiki.label(ent, "hi"), "via": h["via"]}
        if "human" in cats:
            died = next((wiki.wd_time(c["value"]) for c in wiki.claims(ent, "P570")), None)
            if not died or not 0 <= (today - died).days <= DEATH_MAX_DAYS:
                continue
            if wiki.claims(ent, "P1399"):
                continue  # people convicted of crimes are not eulogised on this channel
            if any(c["value"] == SUICIDE for c in wiki.claims(ent, "P1196")):
                continue
            out.append(base | {"id": f"wk-{qid}", "kind": "death", "category": "death", "date": died.isoformat()})
            continue
        cat = next((c for c in ORDER if c in cats), None)
        if not cat:
            continue
        when = _event_date(ent)
        if cat in ONGOING:
            leads = (len(h.get("headlines", [])) + len(h.get("hindi_headlines", []))
                     + (PORTAL_LEADS if h.get("portal") else 0))
            if leads < ONGOING_MIN_HEADLINES or not is_current(ent, cat, today):
                continue  # only news while several lead stories are about it, and while it is still going on
            when = date.fromisoformat(news_at[:10])
        if not when:
            made = wiki.created(page["title"])
            when = made.date() if made else None
        if not when or not 0 <= (today - when).days <= INCIDENT_MAX_DAYS:
            continue
        coords = (page["lat"], page["lon"]) if page.get("lat") is not None else wiki.coords(ent)
        sid = story_id(qid, cat, when) if qid else article_id(page["title"])
        out.append(base | {"id": sid, "kind": "incident", "category": cat, "date": when.isoformat(),
                           "coords": coords,
                           "has_coords": bool(coords or wiki.claims(ent, "P276") or wiki.claims(ent, "P1427"))})
    out.sort(key=lambda c: -c["fame"])
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "candidates": out, "errors": errors,
            "scanned": len(hits)}
