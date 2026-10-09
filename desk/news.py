"""Breaking-news signal: Google News lead stories for India (English and Hindi), the US and the world.

Wikipedia's most-read list is a day behind and Google Trends shows searches, not stories. The front pages of Google
News show what newsrooms are leading with right now. Each headline is matched to the Wikipedia article about it (a
Hindi headline through Hindi Wikipedia, then the same item's English article); an article's heat is how many lead
stories and outlets point at it, and how recent the newest one is. Hindi lead stories are also counted on their own:
they show how big a story is for this channel's audience.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from . import net, wiki

FEEDS = {
    "IN": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    "IN-nation": "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en",
    "IN-hi": "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi",
    "IN-hi-nation": "https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi",
    "US": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "world": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
}
HINDI_FEEDS = ("IN-hi", "IN-hi-nation")
MAX_AGE_H = 36
# One lead story counts like this much Google Trends traffic on the fame scale, times the outlets covering it.
HEADLINE_FAME = 25000
NOISE = re.compile(r"^(BREAKING|LIVE|LIVE UPDATES|WATCH|EXCLUSIVE|EXPLAINED|ब्रेकिंग|लाइव|बड़ी खबर|बड़ी ख़बर)\s*[|:\-]\s*",
                   re.I)
EDITED_WITHIN_H = 72
# Title words too common to show that a headline is about this article.
GENERIC = set("""protest protests war party election elections attack attacks crash fire flood floods earthquake
death killing killings shooting bombing riots strike strikes movement march crisis disaster accident explosion
collapse case india indian united states world national government state city south north east west""".split())
GENERIC_HI = set("""भारत भारतीय सरकार हमला हमले हादसा हादसे दुर्घटना मौत निधन बाढ़ भूकंप चुनाव पार्टी राज्य देश दुनिया
खबर ख़बर प्रदर्शन मामला मामले नया नई नए दिल्ली मुंबई शहर जिला ज़िला पुलिस लोग लोगों बड़ा बड़ी आज कल साल""".split())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'’\-]+", text.lower().replace("’", "'")) if len(w) >= 4}


def _tokens_hi(text: str) -> set[str]:
    return {w for w in re.findall(r"[\u0900-\u097f]+", text) if len(w) >= 3 and w not in GENERIC_HI}


def match(headline: str, now: datetime | None = None, lang: str = "en") -> str | None:
    """The Wikipedia article (in lang) a headline is about: one of the top search hits, edited in the last
    EDITED_WITHIN_H hours, whose title shares a distinctive word with the headline. None when nothing fits."""
    now = now or datetime.now(timezone.utc)
    d = net.get_json(wiki.api(lang), params={"action": "query", "list": "search", "srsearch": headline, "srlimit": 5,
                                             "srprop": "timestamp", "format": "json", "formatversion": 2})
    words = _tokens_hi(headline) if lang == "hi" else _tokens(headline)
    for hit in d["query"]["search"]:
        edited = datetime.fromisoformat(hit["timestamp"].replace("Z", "+00:00"))
        if (now - edited).total_seconds() > EDITED_WITHIN_H * 3600:
            continue
        title_words = _tokens_hi(hit["title"]) if lang == "hi" else _tokens(hit["title"]) - GENERIC
        if title_words & words:
            return hit["title"]
    return None


def headlines(feed: str, now: datetime | None = None) -> list[dict]:
    """[{title, outlet, outlets, at, feed}] for lead stories younger than MAX_AGE_H."""
    now = now or datetime.now(timezone.utc)
    root = ET.fromstring(net.get(FEEDS[feed], tries=2))
    out = []
    for item in root.iter("item"):
        raw = item.findtext("title") or ""
        title, _, outlet = raw.rpartition(" - ")
        if not title:
            title, outlet = raw, ""
        title = NOISE.sub("", title).strip()
        try:
            at = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if at is None:
            continue
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        at = at.astimezone(timezone.utc)
        if (now - at).total_seconds() > MAX_AGE_H * 3600:
            continue
        outlets = max(1, (item.findtext("description") or "").count("<li>"))
        out.append({"title": title, "outlet": outlet.strip(), "outlets": outlets, "at": at.isoformat(), "feed": feed})
    return out


def signals(now: datetime | None = None) -> tuple[dict[str, dict], list[str]]:
    """English Wikipedia title -> {news, news_at, headlines, hindi_headlines, hindi_news, geos}; plus feed errors."""
    hits: dict[str, dict] = {}
    errors = []
    items = []
    for feed in FEEDS:
        try:
            items += headlines(feed, now)
        except Exception as exc:
            errors.append(f"google news {feed}: {exc}"[:200])

    def safe_match(h):
        try:
            return match(h["title"], now, "hi" if h["feed"] in HINDI_FEEDS else "en")
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        titles = list(pool.map(safe_match, items))
    hindi = sorted({t for h, t in zip(items, titles) if t and h["feed"] in HINDI_FEEDS})
    try:
        to_en = wiki.hi_to_en(hindi) if hindi else {}
    except Exception as exc:
        to_en = {}
        errors.append(f"hindi wikipedia links: {exc}"[:200])
    for h, title in zip(items, titles):
        is_hindi = h["feed"] in HINDI_FEEDS
        if is_hindi:
            title = to_en.get(title) if title else None
        if not title:
            continue
        row = hits.setdefault(title, {"news": 0, "news_at": h["at"], "headlines": [], "hindi_headlines": [],
                                      "hindi_news": 0, "geos": set()})
        bucket = row["hindi_headlines"] if is_hindi else row["headlines"]
        if h["title"] in bucket:
            continue
        row["news"] += HEADLINE_FAME * min(h["outlets"], 6)
        row["news_at"] = max(row["news_at"], h["at"])
        bucket.append(h["title"])
        row["hindi_news"] += is_hindi
        row["geos"].add(h["feed"].split("-")[0])
    return hits, errors
