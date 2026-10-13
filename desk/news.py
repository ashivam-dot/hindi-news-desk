"""Breaking-news signal: Google News lead stories for India (English and Hindi), the US and the world.

Wikipedia's most-read list is a day behind and Google Trends shows searches, not stories. The front pages of Google
News show what newsrooms are leading with right now. Each headline is matched to the Wikipedia article about it (a
Hindi headline through Hindi Wikipedia, then the same item's English article); an article's heat is how many lead
stories and outlets point at it, and how recent the newest one is. Hindi lead stories are also counted on their own:
they show how big a story is for this channel's audience. The trusted outlets' own feeds (desk/outlets.py) join the
lead stories the same way, weighted by how many independent owners cover the story.
"""
from __future__ import annotations

import re
import time
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
    "IN-hi-world": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=hi&gl=IN&ceid=IN:hi",
    "US": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "world": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
}
HINDI_FEEDS = ("IN-hi", "IN-hi-nation", "IN-hi-world")
MAX_AGE_H = 36
# One lead story counts like this much Google Trends traffic on the fame scale, times the outlets covering it.
HEADLINE_FAME = 25000
# A trusted outlet's headline (desk/outlets.py) adds one HEADLINE_FAME per independent owner, up to this many owners.
OUTLET_MAX_OWNERS = 6
# Outlet headlines looked up on Wikipedia's search each run (newest first); the rest are matched only to the pool.
OUTLET_SEARCHES = 160
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
    """The Wikipedia article (in lang) a headline is about: among the top search hits edited in the last
    EDITED_WITHIN_H hours whose title shares a distinctive word with the headline, an event article sharing two or
    more words first ("2026 Erie shooting" over "Erie, Pennsylvania"), then the most shared words, then search order.
    None when nothing fits."""
    from .trends import title_kind

    now = now or datetime.now(timezone.utc)
    d = net.get_json(wiki.api(lang), params={"action": "query", "list": "search", "srsearch": headline, "srlimit": 5,
                                             "srprop": "timestamp", "format": "json", "formatversion": 2})
    words = _tokens_hi(headline) if lang == "hi" else _tokens(headline)
    fits = []
    for rank, hit in enumerate(d["query"]["search"]):
        edited = datetime.fromisoformat(hit["timestamp"].replace("Z", "+00:00"))
        if (now - edited).total_seconds() > EDITED_WITHIN_H * 3600:
            continue
        title_words = _tokens_hi(hit["title"]) if lang == "hi" else _tokens(hit["title"]) - GENERIC
        if title_words & words:
            shared = len((_tokens_hi(hit["title"]) if lang == "hi" else _tokens(hit["title"])) & words)
            event = lang == "en" and shared >= 2 and title_kind(hit["title"], now.date()) is not None
            fits.append((not event, -shared, rank, hit["title"]))
    return min(fits)[3] if fits else None


MONTH_WORDS = set("january february march april may june july august september october november december".split())
TITLE_STOP = set("the and for from with into over after near of on in at to by".split())


def _stem(word: str) -> str:
    word = re.sub(r"['’]s$", "", word.lower())
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def _seq(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'’\-]*", text)]


def _words(text: str) -> set[str]:
    return set(_seq(text))


def _has_run(seq: list[str], run: list[str]) -> bool:
    return bool(run) and any(seq[i:i + len(run)] == run for i in range(len(seq) - len(run) + 1))


def pool_item(title: str, person: bool = False, qid: str | None = None, hi: str | None = None) -> dict:
    """A story article headlines may be matched to by their words: its distinctive title words (stemmed) and which of
    them are names ('2026 Aubagne school shooting' -> {aubagne, school}, names {aubagne}); a person's whole name."""
    plain = re.sub(r"\s*\([^)]*\)", "", title)
    raw = re.findall(r"[A-Za-z][A-Za-z'’\-]*", plain)
    if person:
        words = [w for w in raw if len(w) >= 2]
    else:
        words = [w for w in raw if len(w) >= 3 and w.lower() not in GENERIC | MONTH_WORDS | TITLE_STOP]
    return {"title": title, "person": person, "qid": qid, "hi": hi, "keys": sorted({_stem(w) for w in words}),
            "names": sorted({_stem(w) for w in words if w[0].isupper()}),
            "run": [_stem(w) for w in words] if person else []}


def reverse(headline: str, pool: list[dict]) -> str | None:
    """The pool article a headline names, or None. Wikipedia's search ranks long-standing articles first, so a
    headline about a brand-new event rarely finds that event's article; the pool (fresh event articles, people who
    just died) is matched by words instead. An English headline must name a person's whole name in order, or an
    event's place or other name plus one more of its title words; a Hindi one must contain the item's Hindi label.
    A headline two different items fit matches nothing."""
    from . import hindi

    seq, best = _seq(headline), []
    words = set(seq)
    devanagari = hindi.devanagari_share(headline) > 0.3
    for item in pool:
        if devanagari:
            label = item.get("hi") or ""
            ok = len(hindi.norm(label)) >= 4 and hindi.contains(headline, label)
            score = len(label) if ok else 0
        elif item["person"]:
            keys = set(item["keys"])
            ok = len(keys) >= 2 or (len(keys) == 1 and len(next(iter(keys))) >= 5)
            score = len(keys) if ok and _has_run(seq, item.get("run") or []) else 0
        else:
            keys, names = set(item["keys"]), set(item["names"])
            hit = keys & words
            score = len(hit) if names & words and len(hit) >= min(2, len(keys)) else 0
        if score:
            best.append((score, item["title"]))
    titles = {t for _, t in best}
    return titles.pop() if len(titles) == 1 else None


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


def _from_outlet(item: dict) -> dict:
    return {"title": NOISE.sub("", item["title"]).strip(), "outlet": item["outlet"], "outlets": 1, "at": item["at"],
            "feed": "outlet:" + item["feed"], "lang": item["lang"], "owner": item["owner"], "geo": item["geo"],
            "src": item}


def signals(now: datetime | None = None, pool: list[dict] | None = None,
            outlet_items: list[dict] | None = None) -> tuple[dict[str, dict], list[str]]:
    """English Wikipedia title -> {news, news_at, headlines, hindi_headlines, hindi_news, geos, owners, reports}; plus
    feed errors. A headline Wikipedia's search does not resolve is matched against pool (see reverse).

    outlet_items (desk/outlets.py) join the Google News lead stories: each independent owner covering an article adds
    one HEADLINE_FAME, a Hindi outlet's headline is a Hindi headline, and the items are kept as the story's reports.
    Each outlet item matched to an article is marked with it ("matched"); the newest OUTLET_SEARCHES are looked up on
    Wikipedia's search, the rest only in pool."""
    hits: dict[str, dict] = {}
    errors = []
    items = []
    for feed in FEEDS:
        try:
            items += headlines(feed, now)
        except Exception as exc:
            errors.append(f"google news {feed}: {exc}"[:200])
    searchable = len(items) + OUTLET_SEARCHES
    items += [_from_outlet(i) for i in outlet_items or []]

    failed = []

    def hindi_item(h: dict) -> bool:
        return h["feed"] in HINDI_FEEDS or h.get("lang") == "hi"

    def safe_match(numbered):
        n, h = numbered
        if n >= searchable:
            return None
        for attempt in range(2):
            try:
                return match(h["title"], now, "hi" if hindi_item(h) else "en")
            except Exception as exc:
                if attempt:
                    failed.append(type(exc).__name__ + (f" {exc}" if str(exc).startswith("HTTP") else ""))
                else:
                    time.sleep(2)
        return None

    with ThreadPoolExecutor(max_workers=4) as workers:
        titles = list(workers.map(safe_match, enumerate(items)))
    if failed:
        errors.append(f"wikipedia search failed for {len(failed)} of {len(items)} headlines ({failed[0]})"[:200])
    hindi = sorted({t for h, t in zip(items, titles) if t and hindi_item(h)})
    try:
        to_en = wiki.hi_to_en(hindi) if hindi else {}
    except Exception as exc:
        to_en = {}
        errors.append(f"hindi wikipedia links: {exc}"[:200])
    pooled = {p["title"] for p in pool or []}
    for h, title in zip(items, titles):
        is_hindi = hindi_item(h)
        if is_hindi:
            title = to_en.get(title) if title else None
        if pool and title not in pooled:
            # A story article the headline names beats whatever older article the search ranked first.
            title = reverse(h["title"], pool) or title
        if not title:
            continue
        row = hits.setdefault(title, {"news": 0, "news_at": h["at"], "headlines": [], "hindi_headlines": [],
                                      "hindi_news": 0, "geos": set(), "owners": [], "reports": []})
        bucket = row["hindi_headlines"] if is_hindi else row["headlines"]
        if "src" in h:
            h["src"]["matched"] = title
            row["reports"].append(h["src"])
            if h["owner"] in row["owners"]:
                continue  # sister brands and a second headline from one newsroom count once
            row["owners"].append(h["owner"])
            if len(row["owners"]) <= OUTLET_MAX_OWNERS:
                row["news"] += HEADLINE_FAME
        elif h["title"] in bucket:
            continue
        else:
            row["news"] += HEADLINE_FAME * min(h["outlets"], 6)
        row["news_at"] = max(row["news_at"], h["at"])
        if h["title"] not in bucket:
            bucket.append(h["title"])
        row["hindi_news"] += is_hindi
        # A world section is not an Indian signal, whatever its edition (it must not make a story an India story).
        geo = h.get("geo") if "src" in h else (
            h.get("geo") or ("world" if h["feed"].endswith("world") else h["feed"].split("-")[0]))
        if geo:
            row["geos"].add(geo)
    return hits, errors
