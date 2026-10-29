"""India explainers (`kh-` ids): the day's biggest Indian stories that are not incidents or deaths, told as neutral
"क्या हुआ और क्यों" Shorts.

Owner, 2026-10-13: the channel should be "active most with high rated topics, most popular topics, trending topics",
and "each and everything should be based on full real authorised facts". What Indian newsrooms lead with is mostly
politics, policy, the economy, diplomacy, defence, the courts' public rulings, science and the weather. A story
qualifies when at least OWNERS independent English-language owners (desk/outlets.py) report it within WINDOW_H and
its centre (the person or institution most of its headlines name) is an Indian Wikidata item with a Wikipedia
article. Its facts come only from what two of those owners' articles state (gate.OWNERS_NEEDED; syndicated agency
copy counts once) and from Wikipedia on the centre, whose Commons photos illustrate it. Elections and campaigns,
gossip, crime, arrests, raids and trials, communal violence, market tips, opinion, roundups and live blogs never
qualify; sport and film qualify only as top stories (TOP_ONLY); incidents, protests and deaths keep their own lanes.
Only stories in Google News India's top stories go out (desk/top.py, plan.unpopular).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import hindi, news, outlets, wiki

IST = timezone(timedelta(hours=5, minutes=30))
# First match wins: a court ruling on a policy is a court story, a parliament session is never the weather.
KINDS = (
    (r"\b(supreme court|high court|SC|HC|CJI|chief justice|constitution bench|verdict|judgm?ents?|plea|petition|PIL|"
     r"contempt)\b", "court"),
    (r"\b(ISRO|NASA|satellites?|gaganyaan|chandrayaan|aditya-l1|NISAR|PSLV|GSLV|LVM3|SSLV|rockets?|space station|"
     r"astronauts?|spacecraft|ICMR|vaccines?|scientists?)\b", "science"),
    (r"\b(army|navy|air force|IAF|DRDO|missile tests?|test-fire\w*|test fire\w*|BrahMos|Agni|Tejas|Rafale|warships?|"
     r"submarines?|military exercise|wargames?|(?-i:Operation [A-Z]\w+)|ceasefire|defence (deal|ministry|minister))\b",
     "defence"),
    (r"\b(RBI|repo rate|inflation|GDP|rupee|forex|sensex|nifty|stock markets?|gold (price|rate)s?|silver "
     r"(price|rate)s?|petrol|diesel|LPG|fuel prices?|crude|IPO|budget|LTCG|STT|tariffs?|trade deal|exports?|"
     r"imports?|unemployment|FDI|SEBI|economy|economic|fiscal|tax relief|disinvestment|strategic sale|stake sale|"
     r"privati[sz]\w*|acquisition|acquires|bonus|salary|wages|bank)\b", "economy"),
    (r"\b(flights?|airlines?|airport|Air India|IndiGo|Akasa|SpiceJet|DGCA|diverted|emergency landing|hijack alert|"
     r"bomb threat|aviation)\b", "aviation"),
    (r"\b(WHO|hospitali[sz]ed|surgery|health|outbreak|virus|disease|vaccination|medical|AIIMS)\b", "health"),
    (r"\b(resign\w*|quits?|steps? down|sworn|oath|cabinet|reshuffle|chief minister|deputy CM|governor|Lok Sabha|"
     r"Rajya Sabha|parliament\w*|(monsoon|winter|budget) session|speaker|no-confidence|opposition|alliance|coalition|"
     r"INDIA bloc|NDA|union minister|defect\w*|merger)\b", "politics"),
    (r"\b(schemes?|yojana|policy|new rules?|deadline|notification|notified|ordinance|bills?|amendment|mandatory|"
     r"guidelines?|pay commission|dearness allowance|DA hike|pension|GST|income tax|ITR|aadhaar|PAN card|UPI|"
     r"railways?|train fares?|fare hike|special trains|vande bharat|metro|expressway|NEET|JEE|CBSE|UPSC|SSC|board "
     r"exams?|census|reservation|quota)\b", "policy"),
    (r"\b(MEA|external affairs|Jaishankar|bilateral|summit|state visit|talks|treaty|agreement|pact|MoU|envoy|"
     r"ambassador|high commission|embassy|advisory|sanctions?|ties|LAC|LoC|Ladakh|Arunachal|border|G20|BRICS|SCO|"
     r"Quad|UN Security Council|UNGA)\b", "diplomacy"),
    (r"\b(IMD|monsoon|heatwave|heat wave|cold wave|rain alert|heavy rain|orange alert|red alert|AQI|air quality|"
     r"pollution|smog|GRAP)\b", "weather"),
    (r"\b(Pope|Vatican|UN|United Nations|White House|Kremlin|Pentagon|NATO|EU|European Union|Trump|Putin|Xi|"
     r"Zelensky|Netanyahu|Houthis?|Israel|Iran|Ukraine|Russia|China|Pakistan|Bangladesh|Nepal|Sri Lanka)\b", "world"),
)
FALLBACK = "news"  # owner, 2026-10-14: the channel must be the most active; a 3-owner story needs no special topic
# Owner, 2026-10-15: "present the highly popular news". Sport and film are what India reads most, so their stories
# qualify, but only while they are among the day's top stories (plan.TOP_ONLY_SCORE); gossip never does.
TOP_ONLY = {"sport": "खेल", "entertainment": "मनोरंजन"}
TOP_ONLY_KINDS = (
    (r"\b(cricket|ipl|t20i?|odi|test match|match|football|fifa|hockey|tennis|olympic\w*|tournament|league|squad|"
     r"world cup|kabaddi|chess|BCCI|IND vs)\b", "sport"),
    (r"\b(actor|actress|film|movie|box office|bollywood|superstar|starrer)\b", "entertainment"),
)
CATEGORY_HI = {"court": "अदालत", "science": "विज्ञान", "defence": "रक्षा", "economy": "अर्थव्यवस्था",
               "policy": "नीति", "diplomacy": "कूटनीति", "weather": "मौसम", "politics": "राजनीति",
               "aviation": "विमानन", "health": "स्वास्थ्य", "world": "दुनिया", FALLBACK: "समाचार"} | TOP_ONLY
# How headlines name the institutions Wikipedia's search misreads ("Supreme Court" finds the US court, "Railway" a
# railway in general): straight to the Indian article.
ALIASES = {
    "railway": "Indian Railways", "railways": "Indian Railways", "indian railways": "Indian Railways",
    "rbi": "Reserve Bank of India", "reserve bank": "Reserve Bank of India",
    "supreme court": "Supreme Court of India", "sc": "Supreme Court of India", "cji": "Chief Justice of India",
    "parliament": "Parliament of India", "imd": "India Meteorological Department",
    "dgca": "Directorate General of Civil Aviation (India)", "air india": "Air India", "indigo": "IndiGo",
    "isro": "Indian Space Research Organisation", "drdo": "Defence Research and Development Organisation",
    "sebi": "Securities and Exchange Board of India", "cbse": "Central Board of Secondary Education",
    "upsc": "Union Public Service Commission", "idbi": "IDBI Bank", "idbi bank": "IDBI Bank",
    "jio": "Jio Platforms", "aiims": "All India Institute of Medical Sciences, New Delhi",
    "mea": "Ministry of External Affairs (India)", "election commission": "Election Commission of India",
    "nhai": "National Highways Authority of India", "lic": "Life Insurance Corporation",
    # Milk brands are their makers' articles: "Nandini" found no centre on 29 Oct and the price hike was told as
    # Karnataka over its map.
    "nandini": "Karnataka Milk Federation", "kmf": "Karnataka Milk Federation", "amul": "Amul",
    "mother dairy": "Mother Dairy",
}
# What a centre must never be: a festival, a holiday, a people, a country, a language, a religion or a date (a story
# about the railways' Diwali bonus is not about Diwali; "October" is in every dated headline).
NOT_A_CENTRE = re.compile(r"\b(festival|holiday|observance|ethnic group|nationality|citizens of|people of|"
                          r"inhabitants of|country in|country of|sovereign state|language|religion|month of|"
                          r"month in|calendars?|day of the week|calendar year)\b", re.I)
SKIP = re.compile(
    # elections and campaigns
    r"\b(elections?|electoral|polls?|polling|bypolls?|by-elections?|exit polls?|voting|vote count\w*|voters?|"
    r"voter list|SIR|campaign\w*|rallies|roadshow|manifesto|seat-sharing|candidates?|"
    # gossip, promotion, lifestyle (sport and film are TOP_ONLY)
    r"trailer|teaser|ott|web series|song|singer|"
    r"bigg boss|celebrity|wedding|marriage|divorce|dating|viral|meme|horoscope|rashifal|astrology|zodiac|lottery|quiz|"
    r"recipe|tips|best deals|deal of the day|discount|movie review|film review|"
    # opinion, roundups, live blogs, service pages
    r"opinion|editorial|column|analysis|explained|explainer|interview|podcast|live|live updates|watch|video|photos|"
    r"in pics|gallery|brief|wrap|roundup|top news|top stories|headlines|newsletter|(rates?|prices?) today|"
    r"check details|in numbers|"
    # crime, investigations, violence, deaths and incidents (their own lanes)
    r"murder\w*|rape\w*|molest\w*|sexual|dowry|suicide|lynch\w*|communal|riots?|clash\w*|stabb\w*|shot|shoots?|"
    r"gunfire|firing|body found|bodies|kidnap\w*|abduct\w*|acid|pocso|gang|gangster|encounter|drugs?|smuggl\w*|"
    r"arrest\w*|detained|raids?|summons|probe|scam|money laundering|ED|CBI|NIA|chargesheet|FIRs?|bail|convicted|"
    r"charged|indicted|trespass\w*|spy|spying|espionage|"
    r"sentenced|acquitted|trial|accused|killed|killings?|kills?|dies|died|dead|death|deaths|demise|passes away|"
    r"funeral|attack\w*|crash\w*|injur\w*|terror\w*|militants?|neutrali[sz]\w*|IED|trapped|missing|protests?|"
    # market tips and company results
    r"stocks? to buy|share price|target price|buy or sell|multibagger|penny stock|dividend|q[1-4] results?|"
    r"quarterly results?|net profit|earnings|"
    # anniversaries and greetings
    r"birthday|anniversary|years? after|on this day|wishes(?! to\b)|greetings)\b|"
    r"^(how|why|what|who|when|where|is|are|can|should|will|inside|explained)\b|बड़ी खबरें|बड़ी ख़बरें|पढ़ें", re.I)
# Institutions, leaders and big places named in too many stories to tell one by: two headlines naming only these must
# share three distinctive words to be one story.
INSTITUTIONS = set("""minister ministry union govt court supreme high chief cm party leader bjp congress aap tmc dmk
rbi modi parliament cabinet opposition centre sebi isro army navy delhi mumbai kolkata chennai bengaluru bangalore
hyderabad pune lucknow patna jaipur kerala keralam tamil nadu punjab bihar gujarat maharashtra karnataka bengal uttar
pradesh rajasthan assam odisha telangana andhra haryana jharkhand madhya kashmir""".split())
OWNERS = 3
WINDOW_H = 24
RESOLVE = 25
CENTRES_TRIED = 2
PERSON_LOOKS = 2  # further names tried for a person when the first centre found is a city or state
LEAD_FEEDS = ("IN", "IN-nation", "IN-hi", "IN-hi-nation")
LEAD_CAP = 8
OWNER_CAP = 8
HUMAN = "Q5"
INDIA = "Q668"
DISAMBIGUATION = "Q4167410"
GIVEN_NAMES = {"Q202444", "Q12308941", "Q11879590", "Q101352"}  # given name (male, female) and family name
# Wikidata items that name a whole country: never the centre of an explainer.
TOO_BROAD = {INDIA, "Q30", "Q148", "Q843", "Q145", "Q159", "Q801", "Q794", "Q458", "Q1028"}
INDIA_PIDS = ("P17", "P27", "P495", "P1001")


def category(title: str) -> str | None:
    """The explainer category a headline names, or None (a skipped topic, an incident, or no category)."""
    if SKIP.search(title) or any(re.search(p, title, re.I) for p, _ in outlets.HEADLINE_KINDS):
        return None
    cat = next((cat for pattern, cat in KINDS if re.search(pattern, title, re.I)), None)
    if cat != "court":
        cat = next((c for pattern, c in TOP_ONLY_KINDS if re.search(pattern, title, re.I)), cat)
    return cat or FALLBACK


def _generic(word: str) -> bool:
    return word in outlets.GENERIC or word in INSTITUTIONS


def keys(title: str) -> tuple[set[str], set[str], set[str]]:
    """A headline's distinctive words, its names, and the words that may be names (its first word too). An all-caps
    first word is a name whatever its position ("RBI keeps repo rate unchanged")."""
    keys_, names_, lead = outlets.headline_keys(title)
    first = re.match(r"\W*([A-Za-z][A-Za-z'’\-]*)", title)
    if lead and first and first.group(1).isupper() and len(first.group(1)) >= 2:
        names_ = names_ | {lead}
    return keys_, names_, names_ | ({lead} if lead else set())


def title_case(title: str) -> bool:
    """Most of the headline's longer words are capitalised ("L Murugan Resigns As Union Minister"): its capitals
    say nothing about which words are names."""
    words = re.findall(r"[A-Za-z][A-Za-z'’\-]{3,}", title)[1:]
    return len(words) >= 3 and sum(w[0].isupper() for w in words) >= 0.6 * len(words)


def _same(a: dict, b: dict) -> bool:
    """Two headlines tell one story: they name the same person, place or institution, and share at least one more
    distinctive word that is not part of a name (two different stories about one person share only the name). A
    title-case headline's names are read from the other headline; two title-case headlines must share 3 words."""
    shared = {k for k in a["keys"] & b["keys"] if not _generic(k)}
    if a.get("title_case") and b.get("title_case"):
        named = a["maybe"] & b["maybe"]
        return bool(named) and any(not _generic(n) for n in named) and len(shared) >= 3
    names = set().union(*(r["names"] for r in (a, b) if not r.get("title_case")))
    maybe = (a["keys"] if a.get("title_case") else a["maybe"]) & (b["keys"] if b.get("title_case") else b["maybe"])
    named = maybe & names
    if not named:
        return False
    other = shared - maybe - names
    if not other:
        return False
    if any(not _generic(n) for n in named):
        return True
    return len(shared | (a["keys"] & b["keys"] & named)) >= 3


def clusters(items: list[dict], now: datetime) -> list[dict]:
    """English outlet items published within WINDOW_H grouped into stories: {items, names (Counter), cats}."""
    rows = []
    for i in items:
        if i.get("lang") != "en" or (now - datetime.fromisoformat(i["at"])).total_seconds() > WINDOW_H * 3600:
            continue
        cat = category(i["title"])
        if not cat:
            continue
        keys_, names_, maybe = keys(i["title"])
        rows.append({"item": i, "cat": cat, "keys": keys_, "names": names_, "maybe": maybe,
                     "title_case": title_case(i["title"])})
    out: list[dict] = []

    def join(row: dict) -> None:
        # A headline joins the story at least half of its headlines match, so one loose link never chains two stories.
        best, home = 0, None
        for c in out:
            hits = sum(_same(row, other) for other in c["rows"])
            if hits * 2 >= len(c["rows"]) and hits > best:
                best, home = hits, c
        if home is None:
            home = {"rows": [], "items": [], "names": Counter(), "cats": Counter(), "named": set()}
            out.append(home)
        home["rows"].append(row)
        home["items"].append(row["item"])
        home["names"].update(row["maybe"])
        if not row["title_case"]:
            home["named"] |= row["names"]
        home["cats"][row["cat"]] += 1

    for row in sorted(rows, key=lambda r: r["item"]["at"]):
        join(row)
    # A headline left alone because the headline linking it to a story came later gets one more try.
    for c in [c for c in out if len(c["rows"]) == 1]:
        out.remove(c)
        join(c["rows"][0])
    for c in out:
        c["owners"] = outlets.owners(c["items"])
    return sorted(out, key=lambda c: -len(c["owners"]))


def centres(c: dict) -> list[str]:
    """Stems of the names the story may be about, best first: the most common names across its headlines, people
    and places before institutions; countries never."""
    counts = [(n, k) for k, n in c["names"].items() if k in c["named"] and k not in outlets.GENERIC]
    ranked = sorted(counts, key=lambda nk: (nk[0] - (0.5 if nk[1] in INSTITUTIONS else 0), len(nk[1])), reverse=True)
    return [k for _, k in ranked]


def centre(c: dict) -> str | None:
    return next(iter(centres(c)), None)


def full_name(titles: list[str], key: str) -> str | None:
    """The capitalised 2-3 word run ending on `key` the most headlines write ("Donald Tusk" around "Tusk"), else None."""
    seen: Counter = Counter()
    for t in dict.fromkeys(titles):
        words = re.findall(r"[A-Za-z][A-Za-z'’.\-]*", t)
        for n in (2, 3):
            for s in range(len(words) - n + 1):
                run = words[s:s + n]
                if all(w[0].isupper() for w in run) and outlets._stem(re.sub(r"['’]s$", "", run[-1]).strip(".")) == key:
                    seen[re.sub(r"['’]s$", "", " ".join(run)).strip(".-")] += 1
    return max(seen, key=lambda g: (seen[g], -len(g.split()))) if seen else None


def phrase(titles: list[str], key: str) -> str | None:
    """The capitalised run of 1-3 words around `key` the most headlines write ("Rahul Gandhi"); the full name beats a
    bare surname that a few headlines use alone ("L Murugan" over "Murugan")."""
    seen: Counter = Counter()
    for t in dict.fromkeys([t for t in titles if not title_case(t)] or titles):
        words = re.findall(r"[A-Za-z][A-Za-z'’.\-]*", t)
        grams = set()
        for n in (1, 2, 3):
            for s in range(len(words) - n + 1):
                run = words[s:s + n]
                if not all(w[0].isupper() for w in run) or not any(outlets._stem(w.strip(".")) == key for w in run):
                    continue
                grams.add(re.sub(r"['’]s$", "", " ".join(run)).strip(".-"))
        seen.update(grams)
    if not seen:
        return None
    top = max(seen.values())
    return max(((g, n) for g, n in seen.items() if n * 2 >= top), key=lambda gn: (len(gn[0].split()), gn[1]))[0]


def lead_row(c: dict) -> dict:
    """The headline that best tells the story: the one sharing the most distinctive words with the others."""
    def score(row):
        return sum(len({k for k in row["keys"] & o["keys"] if not _generic(k)}) for o in c["rows"] if o is not row)
    return max(c["rows"], key=lambda r: (score(r), r["item"]["group"] in outlets.STRONG))


# A person Wikidata gives no citizenship is still India's through an Indian party, office, birthplace or employer.
PERSON_LINKS = ("P102", "P39", "P19", "P108", "P463")


def indian(ent: dict) -> bool:
    """The item is India's: an Indian place, institution or law, or an Indian citizen (or, without a citizenship on
    Wikidata, a person whose party, office, birthplace or employer is Indian)."""
    if any(x["value"] == INDIA for pid in INDIA_PIDS for x in wiki.claims(ent, pid)):
        return True
    if wiki.claims(ent, "P27") or not any(x["value"] == HUMAN for x in wiki.claims(ent, "P31")):
        return False
    linked = list(dict.fromkeys(x["value"] for pid in PERSON_LINKS for x in wiki.claims(ent, pid)[:3]
                                if isinstance(x["value"], str) and x["value"].startswith("Q")))[:12]
    return bool(linked) and any(x["value"] == INDIA for e in wiki.entities(linked).values()
                                for pid in INDIA_PIDS for x in wiki.claims(e, pid))


def names_article(article: str, key: str, name: str) -> bool:
    """The article is about the name the headlines use: it contains the name's stem, or the name is the article's
    acronym ("RBI" for "Reserve Bank of India")."""
    words = re.findall(r"[A-Za-z]+", article)
    if key in {outlets._stem(w) for w in words}:
        return True
    initials = "".join(w[0] for w in words if w.lower() not in ("of", "the", "and", "for"))
    return name.isupper() and initials.upper() == name.upper()


def _item(article: str) -> tuple[str, str, dict] | None:
    """(title, qid, entity) for an article that can be a story's centre."""
    page = wiki.page_info([article]).get(article)
    if not page or not page.get("qid") or page["qid"] in TOO_BROAD:
        return None
    ent = wiki.entities([page["qid"]]).get(page["qid"]) or {}
    kinds = {x["value"] for x in wiki.claims(ent, "P31")}
    about = ((ent.get("descriptions") or {}).get("en") or {}).get("value", "")
    if DISAMBIGUATION in kinds or GIVEN_NAMES & kinds or NOT_A_CENTRE.search(about):
        return None
    return page["title"], page["qid"], ent


def resolve(name: str, key: str) -> tuple[str, str, dict, bool] | None:
    """(article, qid, entity, indian) for the centre. A name in ALIASES goes straight to its Indian article; otherwise
    Wikipedia's search for the name, then for "<name> of India" when that article is "<name> of India" itself or the
    name's acronym ("Supreme Court" alone finds the US court; "Greece of India" finds "Greece–India relations", a
    different subject), keeping the first Indian item. With no Indian item, the name's own article tells a world
    story (owner, 2026-10-14: the channel covers the world's big news too)."""
    if name.lower() in ALIASES:
        found = _item(ALIASES[name.lower()])
        return found + (True,) if found else None
    world = None
    for n, query in enumerate((name, f"{name} of India")):
        article = wiki.search(query)
        if not article or not names_article(article, key, name):
            continue
        indian_title = re.match(re.escape(name) + r"( of India|\s*\(India\)|, India)$", article, re.I)
        if n and not indian_title and not names_article(article, "", name):
            continue
        found = _item(article)
        if not found:
            continue
        if indian(found[2]):
            return found + (True,)
        world = world or (found if not n else None)
    return world + (False,) if world else None


# What headlines call a person, and the words Wikidata's description uses for it. One name is often many people
# (the actor Imran Khan is not Pakistan's former prime minister): the centre must be what the headlines say it is.
ROLES = {"actor": ("actor", "actress"), "actress": ("actress", "actor"), "singer": ("singer",),
         "cricketer": ("cricketer",), "footballer": ("footballer", "football"), "director": ("director", "filmmaker"),
         "filmmaker": ("filmmaker", "director"), "activist": ("activist",), "journalist": ("journalist",),
         "businessman": ("businessman", "businessperson", "industrialist", "entrepreneur"),
         "minister": ("minister", "politician"), "politician": ("politician", "minister"),
         "pm": ("minister", "politician")}
_ROLE = "|".join(ROLES)
# After the name, "PM" is nearly always the next person's title in a list ("Elon Musk, PM Modi discuss Starlink"),
# which had dropped a businessman's story as "not the pm the headlines name"; it counts only before the name.
_AFTER_ROLE = "|".join(r for r in ROLES if r != "pm")
# The same roles in Hindi headlines, whole words only (मंत्री is never read inside प्रधानमंत्री or मुख्यमंत्री, which
# are listed as words of their own): dNGHjXMe1ng (2026-10-21) said "अभिनेता इमरान खान" while no English headline said
# "actor", and was told with Pakistan's former prime minister's photos (Q155164, not the actor Q312781). "पूर्व पीएम
# इमरान खान" is the other one, and says so.
HINDI_ROLES = {"अभिनेता": "actor", "अभिनेत्री": "actress", "एक्टर": "actor", "एक्ट्रेस": "actress", "गायक": "singer",
               "गायिका": "singer", "क्रिकेटर": "cricketer", "मंत्री": "minister", "प्रधानमंत्री": "pm", "पीएम": "pm",
               "मुख्यमंत्री": "minister"}
_HINDI_ROLE = re.compile(r"(?<![\wऀ-ॿ])(" + "|".join(HINDI_ROLES) + r")(?![\wऀ-ॿ])")


def headline_role(titles: list[str], name: str) -> str | None:
    """The role most of the story's own headlines put right before or after the name ("actor Imran Khan")."""
    n = re.escape(name)
    seen = Counter()
    for t in titles:
        m = re.search(rf"\b({_ROLE})\s+{n}\b|\b{n},?\s+(?:the\s+|an?\s+)?({_AFTER_ROLE})\b", t, re.I)
        if m:
            seen[(m.group(1) or m.group(2)).lower()] += 1
    return seen.most_common(1)[0][0] if seen else None


def hindi_role(name: str, hindi_titles: list[str]) -> str | None:
    """The one role this run's Hindi headlines give the name with a HINDI_ROLES word right before a close Hindi
    spelling of it ("अभिनेता इमरान खान"; आमिर or इरफान खान is never Imran Khan), or None when they give none or
    disagree. These headlines are the run's, not only the story's, so the role only ever holds a story back
    (explain.find), never chooses its person."""
    seen = set()
    for t in dict.fromkeys(hindi_titles):
        for m in _HINDI_ROLE.finditer(t):
            after = re.findall(r"[ऀ-ॿ]+", t[m.end():])[:len(name.split())]
            if len(after) == len(name.split()) and all(hindi.likeness(h, e) >= 0.9 for h, e in zip(after, name.split())):
                seen.add(HINDI_ROLES[m.group(1)])
                break
    return next(iter(seen)) if len(seen) == 1 else None


def fits_role(ent: dict, role: str) -> bool:
    """Wikidata's description fits the role, or there is no description to contradict it. Only then, as an extra,
    the occupations (P106): with no description, listed occupations that never fit the role contradict it."""
    about = ((ent.get("descriptions") or {}).get("en") or {}).get("value", "").lower()
    if about:
        return any(w in about for w in ROLES[role])
    jobs = [x["value"] for x in wiki.claims(ent, "P106")[:5] if isinstance(x["value"], str)]
    labels = " ".join(wiki.labels(jobs).values()).lower() if jobs else ""
    return not labels or any(w in labels for w in ROLES[role])


def resolve_as(name: str, key: str, role: str) -> tuple[str, str, dict, bool] | None:
    """The person named `name` whose Wikidata description fits `role` (Wikipedia's search for "<name> <role>")."""
    article = wiki.search(f"{name} {role}")
    if not article or not names_article(article, key, name):
        return None
    found = _item(article)
    if not found or not fits_role(found[2], role):
        return None
    return found + (indian(found[2]),)


def hindi_names_of(label_hi: str | None) -> list[str]:
    """How Hindi headlines write the centre: its Wikidata label, and the label without abbreviation dots
    ("एल मुरुगन"). Never a surname alone: गांधी or कुमार name many people."""
    if not label_hi:
        return []
    plain = re.sub(r"\s+", " ", re.sub(r"\.\s*", " ", label_hi)).strip()
    return [n for n in dict.fromkeys([label_hi, plain]) if len(hindi.norm(n)) >= 4]


def lead_items(now: datetime) -> dict[str, list[dict]]:
    """Google News India lead stories, read once a run."""
    out = {}
    for feed in LEAD_FEEDS:
        try:
            out[feed] = news.headlines(feed, now)
        except Exception:
            out[feed] = []
    return out


def _leads(phrase_: str, spellings: list[str], leads: dict[str, list[dict]]) -> tuple[int, list[str], list[str]]:
    """Google News India lead stories naming the story's centre: their outlet count (capped) and headlines."""
    total, en, hi = 0, [], []
    for feed, rows in leads.items():
        for h in rows:
            title = h["title"]
            if feed in news.HINDI_FEEDS:
                if not any(hindi.contains(title, s) for s in spellings):
                    continue
                bucket = hi
            elif re.search(r"\b" + re.escape(phrase_) + r"\b", title, re.I):
                bucket = en
            else:
                continue
            if title not in bucket:
                bucket.append(title)
                total += min(h.get("outlets", 1), 6)
    return min(total, LEAD_CAP), en, hi


def story_id(now: datetime, qid: str) -> str:
    """One id per centre per IST day: stable across runs however the headlines shift, so a story given up stays
    given up (plan.told_before keeps one centre from being explained twice within a day)."""
    return f"kh-{now.astimezone(IST):%Y%m%d}-{qid}"


def find(items: list[dict], now: datetime | None = None, skip_qids: set[str] | None = None) -> tuple[list[dict], list[str]]:
    """Explainer candidates (best first) from this run's outlet items, and a note per cluster dropped after lookup."""
    now = now or datetime.now(timezone.utc)
    skip_qids = skip_qids or set()
    notes, out, seen = [], [], set()
    hindi_items = [i for i in items if i.get("lang") == "hi"
                   and (now - datetime.fromisoformat(i["at"])).total_seconds() <= WINDOW_H * 3600]
    # Words headlines also write in lower case are ordinary words ("special"), never a name on their own.
    common = {w for i in items if i.get("lang") == "en" for w in re.findall(r"\b[a-z]{3,}\b", i["title"])}
    leads = None
    looked = 0
    for c in clusters(items, now):
        if len(c["owners"]) < OWNERS or looked >= RESOLVE:
            break
        titles = [i["title"] for i in c["items"]]
        found, name, tried, setting = None, None, [], None
        for n, key in enumerate(centres(c)[:CENTRES_TRIED + PERSON_LOOKS]):
            if n >= CENTRES_TRIED and not setting:
                break
            name = phrase(titles, key)
            if not name or (" " not in name and not name.isupper() and name.lower() in common
                            and name.lower() not in ALIASES):
                continue
            tried.append(name)
            looked += 1
            if leads is None:
                leads = lead_items(now)
            # The role is read before the centre is looked up, from the story's own headlines; this run's Hindi items
            # and Google News India's Hindi lead headlines can only hold the story back (hindi_role).
            lead_hi_ = [h["title"] for f, rows in leads.items() if f in news.HINDI_FEEDS for h in rows]
            try:
                found = resolve(name, key)
                role = headline_role(titles, name)
                hi_role = None if role else hindi_role(name, [i["title"] for i in hindi_items] + lead_hi_)
                human = found and HUMAN in {x["value"] for x in wiki.claims(found[2], "P31")}
                if human and role and not fits_role(found[2], role):
                    found = resolve_as(name, key, role)
                    if not found:
                        notes.append(f"explainer {name}: Wikipedia's {name} is not the {role} the headlines name")
                elif human and hi_role and not fits_role(found[2], hi_role):
                    # dNGHjXMe1ng told the actor's notice with Pakistan's former PM; the reverse (a Pakistan jail
                    # story told as the actor, 2026-10-22 review) is as wrong. Two people may own the name: skip.
                    notes.append(f"explainer {name}: Hindi headlines name a {hi_role} {name}, Wikipedia's {name} is "
                                 "not one; whose story it is stays unknown, so it is skipped")
                    found = None
            except Exception as exc:
                notes.append(f"explainer {name}: wikipedia lookup failed ({type(exc).__name__})")
                continue
            if found and " " not in name and HUMAN not in {x["value"] for x in wiki.claims(found[2], "P31")} \
                    and not wiki.claims(found[2], "P1082") and (full := full_name(titles, key)):
                # A bare surname that is also a word: "Tusk" (most headlines) is the tooth's article, खाँग, and dry
                # run 39827813691 told Donald Tusk's visit as it (2026-10-22). A headline's full name is the person.
                other = resolve(full, key)
                if other and HUMAN in {x["value"] for x in wiki.claims(other[2], "P31")}:
                    found, name = other, full
                    tried.append(full)
            if found and not setting and wiki.claims(found[2], "P1082"):
                # A city named in most headlines is where, not who: "PM Modi attends Dussehra in Delhi" was told
                # about Delhi over its temples and markets (2026-10-21). A person the headlines name comes first.
                setting, found = (found, name), None
                continue
            if found and setting and HUMAN not in {x["value"] for x in wiki.claims(found[2], "P31")}:
                found = None
                continue
            if found:
                break
        if not found and setting:
            found, name = setting
        if not tried:
            notes.append(f"explainer {titles[0][:60]!r}: no name to tell it by")
            continue
        if not found:
            notes.append(f"explainer {' / '.join(tried)}: no Wikipedia article that can be its centre")
            continue
        article, qid, ent, home = found
        if qid in skip_qids or qid in seen:
            continue
        kinds = {x["value"] for x in wiki.claims(ent, "P31")}
        person = HUMAN in kinds
        if person and (wiki.claims(ent, "P570") or wiki.claims(ent, "P1399")):
            continue  # deaths have their own lane; people convicted of crimes are never the centre of a Short
        seen.add(qid)
        label_hi = wiki.common_hindi(ent)
        spellings = hindi_names_of(label_hi)
        hi_rows = [i for i in hindi_items if any(hindi.contains(i["title"], s) for s in spellings)]
        if leads is None:
            leads = lead_items(now)
        lead_n, lead_en, lead_hi = _leads(name, spellings, leads)
        core = sorted(core_keys(c))
        own = [i for i in c["items"] if about_story(i, name, core)]
        if len(outlets.owners(own)) < OWNERS:
            notes.append(f"explainer {name}: fewer than {OWNERS} owners' headlines name it and the story")
            continue
        who = list(dict.fromkeys(outlets.owners(own) + outlets.owners(hi_rows)))
        fame = news.HEADLINE_FAME * (min(len(who), OWNER_CAP) + lead_n)
        cat = c["cats"].most_common(1)[0][0]
        first = min(datetime.fromisoformat(i["at"]) for i in c["items"])
        newest = max(i["at"] for i in c["items"])
        ranked = sorted(own, key=outlets._rank)
        story = lead_row(c)["item"]["title"]
        out.append({"id": story_id(now, qid), "qid": qid, "title": article, "name": wiki.label(ent) or name,
                    "phrase": name, "person": person, "kind": "explainer", "category": cat,
                    "category_hi": CATEGORY_HI[cat], "story": story, "story_keys": core,
                    "date": first.date().isoformat(), "news_at": newest, "owners": who, "fame": fame, "news": fame,
                    "views": 0, "traffic": 0,
                    "headlines": list(dict.fromkeys([story] + [i["title"] for i in own] + lead_en))[:6],
                    "hindi_headlines": list(dict.fromkeys([i["title"] for i in hi_rows] + lead_hi))[:5],
                    "hindi_news": len(hi_rows) + len(lead_hi), "geos": ["IN"] if home else [],
                    "region": "india" if home else "world", "india_link": home or bool(hi_rows or lead_hi),
                    "label_hi": label_hi,
                    "reports": [outlets.compact(i) for i in ranked][:8],
                    "via": [f"outlet:{o}" for o in who] + [f"google-news:{t}" for t in (lead_en + lead_hi)[:3]]})
    return sorted(out, key=lambda c: -c["fame"]), notes


def core_keys(c: dict) -> set[str]:
    """The story's own words: distinctive words other than names that at least two of its headlines share (the lead
    headline's when none is shared). A report must say one of them to be about this story."""
    counts = Counter(w for row in c["rows"] for w in row["keys"] - c["named"] if not _generic(w))
    core = {w for w, n in counts.items() if n >= 2}
    return core or {w for w in lead_row(c)["keys"] - c["named"] if not _generic(w)}


def about_story(report: dict, phrase_: str, story_keys: list[str]) -> bool:
    """A report is about the explainer's story: its headline names the centre and shares one of the story's own
    words, the way two headlines of one story do."""
    title = report.get("title") or ""
    if not re.search(r"\b" + re.escape(phrase_.split()[-1]) + r"\b", title, re.I) and not \
            re.search(r"\b" + re.escape(phrase_) + r"\b", title, re.I):
        return False
    k, _, _ = keys(title)
    return bool(k & set(story_keys))
