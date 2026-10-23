"""India's top stories: where each candidate stands in Google News India's top-stories lists right now.

Owner, 2026-10-15: "it is picking any random news not top most news ... present the highly popular news". Every
3-owner story used to score about the same (fame counted outlets, capped), so a Kenyan Ebola case outranked the
day's lead story. Google News ranks its top stories for India, in English and in Hindi; a story's place in those
lists is the popularity signal this desk publishes by. `mark` gives every candidate `top` ({feed: rank}), `top_score`
(0 for a story in none of the lists) and `top_headlines` (the matching lead headlines, Hindi first: how the biggest
Hindi newsrooms write it). `hindi_outlets` gives every candidate `hindi_owners`: the Hindi newsrooms whose own feeds
(desk/outlets.py) named it in the last HINDI_WINDOW_H hours. plan.unpopular drops a story that is in no list (unless
HINDI_OWNERS Hindi newsrooms lead with it, or it is breaking or very famous), and plan.priority ranks by place.
"""
from __future__ import annotations

import re
from datetime import datetime

from . import explain, hindi, news, outlets

# Each feed's weight: the front pages lead, the Nation sections count less.
FEEDS = {"IN": 1.0, "IN-hi": 1.0, "IN-nation": 0.6, "IN-hi-nation": 0.6}
TOP_N = 20
OTHERS = 0.5  # a second (third...) list naming the story adds half its weight
HINDI_LEAD_SHARE = 0.4  # a Hindi headline names the story by its Hindi label within its first 40%
# 2026-10-23: a story the desk's own outlets found (nw-) has no Hindi label and no Hindi headlines, so no Hindi list
# could ever name it. The Siwan firecracker blast was second in Google News India's Hindi list ("सिवान में अवैध
# पटाखा भंडार में भीषण विस्फोट") and in Aaj Tak, NDTV India and TV9's feeds, and was dropped as "not in Google News
# India's top stories". A Hindi headline now names an incident when it spells one of the incident's names in
# Devanagari (hindi.likeness: सिवान and सीवान are both "Siwan") and says its kind in Hindi (KIND_HI). A name of two
# consonants or fewer never counts (बार is as like "Bihar" as बिहार is), nor a likeness under SPELT_LIKE (पटना is
# 0.67 like "Taiwan").
SPELT_LIKE = 0.8
NAME_CONSONANTS = 3
KIND_HI = {
    "aviation": "विमान|प्लेन|हेलीकॉप्टर|हेलिकॉप्टर|फ्लाइट|क्रैश",
    "attack": "हमल|फायरिंग|गोली|हत्या|आतंक|चाकू|ड्रोन|मिसाइल",
    "explosion": "विस्फोट|धमाक|ब्लास्ट",
    "rail": "ट्रेन|रेल|पटरी",
    "maritime": "नाव|जहाज|डूब",
    "strike": "हमल|स्ट्राइक|मिसाइल|ड्रोन",
    "earthquake": "भूकंप",
    "cyclone": "चक्रवात|तूफान|टाइफून|हरिकेन|साइक्लोन",
    "volcano": "ज्वालामुखी",
    "flood": "बाढ़|बादल फट|सैलाब",
    "wildfire": "आग|दावानल",
    "landslide": "भूस्खलन|लैंडस्लाइड|हिमस्खलन",
    "tsunami": "सुनामी",
    "disaster": "भगदड़|आग|ढह|हादस|दुर्घटना",
    "accident": "हादस|दुर्घटना|टक्कर|खाई",
    "protest": "प्रदर्शन|आंदोलन|विरोध",
    "movement": "आंदोलन|प्रदर्शन",
}
# A story HINDI_OWNERS Hindi newsrooms (a Hindi outlet, or a public broadcaster's Hindi service) name in their own
# feeds within HINDI_WINDOW_H is trending in India, in a list or not: Google News lists only 20 a feed.
HINDI_OWNERS, HINDI_WINDOW_H = 3, 6
HINDI_GROUPS = ("Hindi", "public broadcaster")


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


def _kind_hi(category: str | None) -> re.Pattern | None:
    words = KIND_HI.get(category or "")
    return re.compile(rf"(?<![\u0900-\u097F])({'|'.join(hindi.norm(w) for w in words.split('|'))})") if words else None


def _names_en(cand: dict) -> list[str]:
    """An incident's names a Hindi headline would spell: the capitalised words of its name (an nw- story's "Bihar
    Siwan") or title ("2026 Karak church shooting"), never a country or a short one."""
    words = re.findall(r"[A-Z][A-Za-z'’\-]*", cand.get("name") or cand.get("title") or "")
    return [w for w in dict.fromkeys(re.sub(r"['’]s$", "", w) for w in words)
            if w.lower() not in outlets.GENERIC and len(hindi.skeleton_en(w)) >= NAME_CONSONANTS]


def _spelt(word: str, name: str) -> bool:
    """A Devanagari word spells an English name: as many consonants (a doubled one counted once: तिब्बत is "Tibet")
    and SPELT_LIKE alike. ऑपरेशन is 0.86 like "Paris" by its letters, but has a consonant more."""
    a, b = (re.sub(r"(.)\1", r"\1", k) for k in (hindi.skeleton_hi(word), hindi.skeleton_en(name)))
    return len(a) == len(b) >= NAME_CONSONANTS and hindi.likeness(word, name) >= SPELT_LIKE


def names_incident(title: str, cand: dict) -> bool:
    """The Hindi headline says the incident's kind and, in its first HINDI_LEAD_SHARE, spells one of its names
    (a "फोर्स" late in a headline about the ITBP is no "Paris")."""
    kind = _kind_hi(cand.get("category")) if cand.get("kind") == "incident" else None
    text = hindi.norm(title)
    if not kind or not kind.search(text):
        return False
    lead = [m.group(0) for m in re.finditer(r"[a-z\u0900-\u097F][a-z'’\u0900-\u097F]*", text)
            if m.start() <= HINDI_LEAD_SHARE * len(text)]  # "Siwan News: सिवान में ..." too
    return any(w == n.lower() or _spelt(w, n) for w in lead for n in _names_en(cand))


def matches_hi(cand: dict, title: str) -> bool:
    """A Hindi headline tells the candidate's story: it is one of its Hindi headlines, leads with its Hindi label, or
    names its incident."""
    if title in (cand.get("hindi_headlines") or []):
        return True
    return any(leads_with(title, label) for label in _labels(cand)) or names_incident(title, cand)


def matches(cand: dict, lead: dict) -> bool:
    title = lead["title"]
    if lead["feed"] in news.HINDI_FEEDS:
        return matches_hi(cand, title)
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


def hindi_outlets(cands: list[dict], items: list[dict], now: datetime) -> None:
    """Give every candidate `hindi_owners`: the Hindi newsrooms (HINDI_GROUPS) among the outlets' items whose
    headlines told its story in the last HINDI_WINDOW_H hours (see HINDI_OWNERS)."""
    recent = [i for i in items if i.get("lang") == "hi" and i.get("group") in HINDI_GROUPS and i.get("at")
              and (now - datetime.fromisoformat(i["at"])).total_seconds() <= HINDI_WINDOW_H * 3600]
    for c in cands:
        c["hindi_owners"] = outlets.owners([i for i in recent if matches_hi(c, i["title"])])
