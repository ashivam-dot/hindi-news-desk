"""India explainers (`kh-` ids): the day's biggest Indian stories that are not incidents or deaths, told as neutral
"क्या हुआ और क्यों" Shorts.

Owner, 2026-10-13: the channel should be "active most with high rated topics, most popular topics, trending topics",
and "each and everything should be based on full real authorised facts". What Indian newsrooms lead with is mostly
politics, policy, the economy, diplomacy, defence, the courts' public rulings, science and the weather. A story
qualifies when at least OWNERS independent English-language owners (desk/outlets.py) report it within WINDOW_H and
its centre (the person or institution most of its headlines name) is an Indian Wikidata item with a Wikipedia
article. Its facts come only from what two of those owners' articles state (gate.OWNERS_NEEDED; syndicated agency
copy counts once) and from Wikipedia on the centre, whose Commons photos illustrate it. Elections and campaigns,
sport, entertainment, gossip, crime, arrests, raids and trials, communal violence, market tips, opinion, roundups and
live blogs never qualify; incidents, protests and deaths keep their own lanes.
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
     r"imports?|unemployment|FDI|SEBI|economy|economic|fiscal|tax relief)\b", "economy"),
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
)
CATEGORY_HI = {"court": "अदालत", "science": "विज्ञान", "defence": "रक्षा", "economy": "अर्थव्यवस्था",
               "policy": "नीति", "diplomacy": "कूटनीति", "weather": "मौसम", "politics": "राजनीति"}
SKIP = re.compile(
    # elections and campaigns
    r"\b(elections?|electoral|polls?|polling|bypolls?|by-elections?|exit polls?|voting|vote count\w*|voters?|"
    r"voter list|SIR|campaign\w*|rallies|roadshow|manifesto|seat-sharing|candidates?|"
    # sport, entertainment, gossip, lifestyle
    r"cricket|ipl|t20|odi|test match|match|football|fifa|hockey|tennis|olympic\w*|tournament|league|squad|world cup|"
    r"kabaddi|chess|actor|actress|film|movie|box office|bollywood|trailer|teaser|ott|web series|song|singer|"
    r"bigg boss|celebrity|wedding|marriage|divorce|dating|viral|meme|horoscope|rashifal|astrology|zodiac|lottery|quiz|"
    r"recipe|tips|best deals|deal of the day|discount|movie review|film review|"
    # opinion, roundups, live blogs, service pages
    r"opinion|editorial|column|analysis|explained|explainer|interview|podcast|live|live updates|watch|video|photos|"
    r"in pics|gallery|brief|wrap|roundup|top news|top stories|headlines|newsletter|(rates?|prices?) today|"
    r"check details|in numbers|"
    # crime, investigations, violence, deaths and incidents (their own lanes)
    r"murder\w*|rape\w*|molest\w*|sexual|dowry|suicide|lynch\w*|communal|riots?|clash\w*|stabb\w*|shot|shoots?|"
    r"gunfire|firing|body found|bodies|kidnap\w*|abduct\w*|acid|pocso|gang|gangster|encounter|drugs?|smuggl\w*|"
    r"arrest\w*|detained|raids?|summons|probe|scam|money laundering|ED|CBI|NIA|chargesheet|FIR|bail|convicted|"
    r"sentenced|acquitted|trial|accused|killed|killings?|kills?|dies|died|dead|death|deaths|demise|passes away|"
    r"funeral|attack\w*|crash\w*|injur\w*|terror\w*|militants?|neutrali[sz]\w*|IED|trapped|missing|protests?|"
    # market tips and company results
    r"stocks? to buy|share price|target price|buy or sell|multibagger|penny stock|dividend|q[1-4] results?|"
    r"quarterly results?|net profit|earnings|"
    # anniversaries and greetings
    r"birthday|anniversary|years? after|on this day|wishes|greetings)\b|"
    r"^(how|why|what|who|when|where|is|are|can|should|will|inside|explained)\b|बड़ी खबरें|बड़ी ख़बरें|पढ़ें", re.I)
# Institutions, leaders and big places named in too many stories to tell one by: two headlines naming only these must
# share three distinctive words to be one story.
INSTITUTIONS = set("""minister ministry union govt court supreme high chief cm party leader bjp congress aap tmc dmk
rbi modi parliament cabinet opposition centre sebi isro army navy delhi mumbai kolkata chennai bengaluru bangalore
hyderabad pune lucknow patna jaipur kerala keralam tamil nadu punjab bihar gujarat maharashtra karnataka bengal uttar
pradesh rajasthan assam odisha telangana andhra haryana jharkhand madhya kashmir""".split())
OWNERS = 3
WINDOW_H = 24
RESOLVE = 10
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
    return next((cat for pattern, cat in KINDS if re.search(pattern, title, re.I)), None)


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


def _same(a: dict, b: dict) -> bool:
    """Two headlines tell one story: they name the same person, place or institution, and share at least one more
    distinctive word that is not part of a name (two different stories about one person share only the name)."""
    named = a["maybe"] & b["maybe"] & (a["names"] | b["names"])
    if not named:
        return False
    shared = {k for k in a["keys"] & b["keys"] if not _generic(k)}
    other = shared - (a["maybe"] & b["maybe"]) - a["names"] - b["names"]
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
        rows.append({"item": i, "cat": cat, "keys": keys_, "names": names_, "maybe": maybe})
    out: list[dict] = []
    for row in sorted(rows, key=lambda r: r["item"]["at"]):
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
        home["named"] |= row["names"]
        home["cats"][row["cat"]] += 1
    for c in out:
        c["owners"] = outlets.owners(c["items"])
    return sorted(out, key=lambda c: -len(c["owners"]))


def centre(c: dict) -> str | None:
    """The stem of the name the story is about: the most common name across its headlines, people and places before
    institutions; countries never."""
    counts = [(n, k) for k, n in c["names"].items() if k in c["named"] and k not in outlets.GENERIC]
    if not counts:
        return None
    return max(counts, key=lambda nk: (nk[0] - (0.5 if nk[1] in INSTITUTIONS else 0), len(nk[1])))[1]


def phrase(titles: list[str], key: str) -> str | None:
    """The capitalised run of 1-3 words around `key` the most headlines write ("Rahul Gandhi"); the full name beats a
    bare surname that a few headlines use alone ("L Murugan" over "Murugan")."""
    seen: Counter = Counter()
    for t in dict.fromkeys(titles):
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


def resolve(name: str, key: str) -> tuple[str, str, dict] | None:
    """(article, qid, entity) for the centre: Wikipedia's search for the name, then for "<name> of India" when
    that article is "<name> of India" itself or the name's acronym ("Supreme Court" alone finds the US court;
    "Greece of India" finds "Greece–India relations", a different subject), keeping the first match that is an
    Indian item and not a disambiguation page or a given name."""
    for n, query in enumerate((name, f"{name} of India")):
        article = wiki.search(query)
        if not article or not names_article(article, key, name):
            continue
        indian_title = re.match(re.escape(name) + r"( of India|\s*\(India\)|, India)$", article, re.I)
        if n and not indian_title and not names_article(article, "", name):
            continue
        page = wiki.page_info([article]).get(article)
        if not page or not page.get("qid") or page["qid"] in TOO_BROAD:
            continue
        ent = wiki.entities([page["qid"]]).get(page["qid"]) or {}
        kinds = {x["value"] for x in wiki.claims(ent, "P31")}
        if DISAMBIGUATION in kinds or GIVEN_NAMES & kinds or not indian(ent):
            continue
        return page["title"], page["qid"], ent
    return None


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
        key = centre(c)
        titles = [i["title"] for i in c["items"]]
        name = phrase(titles, key) if key else None
        if not name or (" " not in name and not name.isupper() and name.lower() in common):
            notes.append(f"explainer {titles[0][:60]!r}: no name to tell it by")
            continue
        looked += 1
        try:
            found = resolve(name, key)
        except Exception as exc:
            notes.append(f"explainer {name}: wikipedia lookup failed ({type(exc).__name__})")
            continue
        if not found:
            notes.append(f"explainer {name}: no Indian Wikipedia article about it")
            continue
        article, qid, ent = found
        if qid in skip_qids or qid in seen:
            continue
        kinds = {x["value"] for x in wiki.claims(ent, "P31")}
        person = HUMAN in kinds
        if person and (wiki.claims(ent, "P570") or wiki.claims(ent, "P1399")):
            continue  # deaths have their own lane; people convicted of crimes are never the centre of a Short
        seen.add(qid)
        label_hi = wiki.label(ent, "hi")
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
                    "hindi_news": len(hi_rows) + len(lead_hi), "geos": ["IN"], "region": "india",
                    "india_link": True, "label_hi": label_hi,
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
