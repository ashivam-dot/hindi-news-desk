"""Country comparison Shorts ("भारत बनाम पाकिस्तान"): two countries' armed forces, the armed forces' share of the
labour force (IISS, The Military Balance), the size of their economies (national accounts) and their populations
(UN World Population Prospects), all from the World Bank's World Development Indicators under CC BY 4.0, over each
country's own freely licensed Commons photos of its forces. No model writes them: every line is a template filled
with a published number, both countries' figures from one year, each said with its year.

Only data its publisher licenses for commercial use: each indicator's licence is read from the World Bank's own
metadata before every build, and anything but CC BY is refused. SIPRI's military spending (also in the WDI) is
under SIPRI's terms, which need SIPRI's authorization for commercial use (2026-10-24 audit; the first comparison,
cmp-20261024-IND-PAK, used it and was set to private).

A pair runs when the day's news is about both countries (a conflict story with OWNERS outlets naming both), or,
when the channel has been quiet for revisit.IDLE, as an evergreen explainer; at most PER_DAY a day and a pair at
most once in PAIR_DAYS days. Owner, 2026-10-24: "some times you can compare the defences of two countries"."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import hindi, media, net
from .spec import Beat, Fact, Short

WB = "https://api.worldbank.org/v2/country/{codes}/indicator/{code}"
WB_META = "https://api.worldbank.org/v2/sources/2/series/{code}/metadata"
WB_PAGE = "https://data.worldbank.org/indicator/{code}?locations={iso2}"
TROOPS, LABOUR, GDP, PEOPLE = "MS.MIL.TOTL.P1", "MS.MIL.TOTL.TF.ZS", "NY.GDP.MKTP.CD", "SP.POP.TOTL"
INDICATORS = (TROOPS, LABOUR, GDP, PEOPLE)
SOURCES = {TROOPS: "IISS, The Military Balance", LABOUR: "IISS, The Military Balance",
           GDP: "World Bank national accounts data", PEOPLE: "UN World Population Prospects"}
FREE = re.compile(r"^CC BY(?:-| )4\.0$", re.I)
EVEN = 1.2  # a ratio under this is "about equal", never "1.1 गुना"
PREFIX, PER_DAY, PAIR_DAYS, OWNERS, FAME = "cmp-", 1, 14, 3, 1
FORMAT = "forces"  # the id's last part: a format told once under an id is never told again under it
# Shorts taken down: they count for nothing (not today's comparison, not their pair's last).
RETIRED = {"cmp-20261024-IND-PAK"}
# Owner, 2026-10-24: "just modify this india pakistan comparison then stop". The lane stays off; ONE_OFF is the
# corrected India-Pakistan Short, run once in place of the retired one, then nothing.
ENABLED = False
ONE_OFF = ("IND", "PAK")
MIN_PHOTOS = 3  # per country: the Short cuts between its forces on land, in the air and at sea
CREDIT = ("तथ्य: World Bank World Development Indicators (CC BY 4.0): सशस्त्र बल IISS, The Military Balance; "
          "जीडीपी: राष्ट्रीय लेखा; आबादी: UN World Population Prospects; तस्वीरें: Wikimedia Commons (लाइसेंस नीचे)")

# iso3: English name, how a headline names it, Hindi, iso2, and the Commons searches for its forces (newest first).
COUNTRIES = {
    "IND": ("India", r"India|Indian", "भारत", "IN",
            ["Indian Army contingent Republic Day parade", "Indian Air Force Rafale", "Indian Navy INS Vikrant",
             "Indian Army T-90 tank"]),
    "PAK": ("Pakistan", r"Pakistan\w*", "पाकिस्तान", "PK",
            ["Pakistan Day Parade", "Pakistan Air Force JF-17 Thunder", "Pakistan Navy frigate PNS",
             "Pakistan Army Al-Khalid tank", "Pakistan Air Force F-16", "Pakistan Army soldiers exercise"]),
    "CHN": ("China", r"China|Chinese|Beijing", "चीन", "CN",
            ["People's Liberation Army honor guard", "PLA Navy ship", "Chengdu J-20", "PLA soldiers exercise"]),
    "USA": ("United States", r"United States|U\.S\.|U S|US|USS|USNS|America\w*|Pentagon", "अमेरिका", "US",
            ["U.S. Army soldiers exercise", "F-35A Lightning II", "USS Gerald R. Ford", "M1 Abrams tank"]),
    "RUS": ("Russia", r"Russia\w*|Kremlin|Moscow", "रूस", "RU",
            ["Russian Air Force Sukhoi Su-57", "Russian Navy ship", "Russian Army T-90", "Russian Ground Forces",
             "Russian Air Force Tu-160", "Russian Navy frigate"]),
    "UKR": ("Ukraine", r"Ukrain\w*|Kyiv", "यूक्रेन", "UA",
            ["Armed Forces of Ukraine soldiers training", "Ukrainian Air Force MiG-29", "Ukrainian Navy ship",
             "Ukrainian Ground Forces exercise"]),
    "ISR": ("Israel", r"Israel\w*|IDF", "इज़राइल", "IL",
            ["Israel Defense Forces soldiers", "Israeli Air Force F-35I", "Israeli Navy Sa'ar", "Merkava tank"]),
    "IRN": ("Iran", r"Iran\w*|Tehran", "ईरान", "IR",
            ["Iranian army day parade", "Islamic Republic of Iran Navy ship", "Iranian Air Force F-14",
             "IRGC parade"]),
}
# The pairs viewers here search for, in the order the channel runs them when nothing in the news calls for one.
PAIRS = [("IND", "PAK"), ("IND", "CHN"), ("RUS", "UKR"), ("ISR", "IRN"), ("USA", "CHN"), ("USA", "RUS")]
MIN_YEAR = 2010
NOT_FORCES = re.compile(r"insignia|emblem|flag|logo|badge|patch|seal|coat of arms|medal|roundel|ribbon|uniform "
                        r"pattern|camouflage pattern|diagram|chart|map\b|museum|memorial|grave|cemetery|statue|"
                        r"model|toy|stamp|coin|poster|crest|terroris\w*|Gaza|screenshot|RHIB|"
                        # Not the photo as taken: retouched, or several photos in one.
                        r"altered|edited|retouched|photoshop\w*|composite|collage|montage|clockwise|"
                        # Another country's forces beside them: a joint exercise is not one country's.
                        r"alongside|counterparts|multinational|joint (?:exercise|training)|bilateral", re.I)
# A named person's face is someone the voice never names: no ministers, generals or leaders at a parade.
NAMED = re.compile(r"با حضور|از چپ|از راست|\b(?:photo|portrait|picture|image) of [A-Z][a-z]+ [A-Z][a-z]+|"
                   r"\b[Pp]ortrait\b|\b(?:From left|from right|L-R|pose[sd]? for|Embassy|delegation|Prime Minister|"
                   r"President|Minister|General|Gen\.|Admiral|Marshal|Chief|Secretary|Sgt\.?|Sergeant|Capt\.|Lt\.|"
                   r"Col\.|Maj\.|Pvt\.|Spc\.|Cpl\.|mentor|Modi|"
                   r"Putin|Xi Jinping|Biden|Trump|Netanyahu|Khamenei|Zelensky\w*|Shoigu|Hegseth|Austin|Sharif|"
                   r"Munir|Rajnath|Singh)(?!\w)")


def _iso3(text: str) -> list[str]:
    return [k for k, v in COUNTRIES.items() if re.search(rf"\b(?:{v[1]})(?!\w)", text or "")]


def licences(get=net.get_json) -> dict[str, str]:
    """{indicator: its licence}, from the World Bank's own metadata (License_Type)."""
    out = {}
    for code in INDICATORS:
        d = get(WB_META.format(code=code), params={"format": "json"}, timeout=60)
        fields = {m["id"]: m["value"] for c in d["source"][0]["concept"] for v in c["variable"] for m in v["metatype"]}
        out[code] = (fields.get("License_Type") or "").strip()
    return out


def _wb(pair, code, get) -> dict[str, dict[int, float]]:
    d = get(WB.format(codes=";".join(pair), code=code), params={"format": "json", "mrv": 8, "per_page": 100},
            timeout=60)
    out: dict[str, dict[int, float]] = {k: {} for k in pair}
    for row in (d[1] if isinstance(d, list) and len(d) > 1 else None) or []:
        if row.get("countryiso3code") in out and row.get("value") is not None:
            out[row["countryiso3code"]][int(row["date"])] = float(row["value"])
    return out


def figures(pair, get=net.get_json) -> dict:
    """{indicator: (year, {iso3: value})}: for each indicator the latest year both countries have a figure, after
    every indicator's licence is checked to be CC BY 4.0. Refuses rather than mixing years or licences."""
    bad = {c: lic for c, lic in licences(get).items() if not FREE.match(lic)}
    if bad:
        raise ValueError("compare: not licensed for commercial use: " + ", ".join(f"{c} ({v!r})" for c, v in bad.items()))
    out = {}
    for code in INDICATORS:
        rows = _wb(pair, code, get)
        both = sorted(set(rows[pair[0]]) & set(rows[pair[1]]), reverse=True)
        if not both:
            raise ValueError(f"compare: the World Bank has no common year of {code} for {' and '.join(pair)}")
        out[code] = (both[0], {k: rows[k][both[0]] for k in pair})
    return out


def _one(x: float) -> str:
    """One decimal, without a trailing .0 ("7.8", "12")."""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def people(n: float) -> str:
    """"30.7 लाख", "94 हज़ार"."""
    return f"{_one(n / 1e5)} लाख" if n >= 1e5 else f"{round(n / 1e3)} हज़ार"


def crore(n: float) -> str:
    """"146.4 करोड़", "98 लाख"."""
    return f"{_one(n / 1e7)} करोड़" if n >= 1e7 else people(n)


def times(a: float, b: float) -> str:
    return _one(a / b)


def script(pair, data) -> dict:
    """The title, the beats ({say, show: [(iso3, slot)], cut, card}) and the facts ({key, phrase, source, what})."""
    (yt, troops), (yl, labour), (yg, gdp), (yp, pop) = (data[c] for c in INDICATORS)
    a, b = sorted(pair, key=lambda k: -troops[k])  # the bigger armed forces lead
    A, B = COUNTRIES[a][2], COUNTRIES[b][2]

    def bigger(values: dict) -> tuple[str, str, str, bool]:
        """(bigger, smaller, ratio, about equal) for an indicator."""
        hi, lo = sorted(pair, key=lambda k: -values[k])
        r = values[hi] / values[lo]
        return hi, lo, times(values[hi], values[lo]), r < EVEN

    _, _, rt, even_t = bigger(troops)
    gh, gl, rg, even_g = bigger(gdp)
    lh, ll, _, _ = bigger(labour)
    G, Gl = COUNTRIES[gh][2], COUNTRIES[gl][2]
    hook = (f"{yt} के आंकड़ों में {A} और {B} के सशस्त्र बल लगभग बराबर थे।" if even_t else
            f"{yt} के आंकड़ों में {A} के सशस्त्र बल {B} से {rt} गुना बड़े थे।")
    labour_lead = "और कामकाजी आबादी के हिस्से में भी" if lh == a else "पर कामकाजी आबादी के हिस्से में"
    economy = (f"{yg} में {A} और {B} की अर्थव्यवस्थाएं लगभग बराबर हैं।" if even_g else
               f"{'' if gh == a else 'पर '}{yg} में अर्थव्यवस्था में {G} {Gl} से {rg} गुना बड़ा है।")
    # About 60 words, under 35 s at the narrator's 115 a minute.
    beats = [
        {"say": hook, "show": [(a, 0), (b, 0)], "cut": B,
         "card": {"big": "लगभग बराबर" if even_t else f"{rt} गुना", "small": f"सशस्त्र बल · आईआईएसएस · {yt}"}},
        {"say": f"{A} के {people(troops[a])} और {B} के {people(troops[b])}, अर्धसैनिक बल मिलाकर।",
         "show": [(a, 1), (b, 1)], "cut": B,
         "card": {"big": f"{people(troops[a])} बनाम {people(troops[b])}", "small": f"अर्धसैनिक बल समेत · {yt}"}},
        {"say": f"{labour_lead} {COUNTRIES[lh][2]} आगे था: {_one(labour[lh])} प्रतिशत, "
                f"{COUNTRIES[ll][2]} {_one(labour[ll])} प्रतिशत।", "show": [(lh, 2), (ll, 2)], "cut": COUNTRIES[ll][2],
         "card": {"big": f"{_one(labour[lh])}% बनाम {_one(labour[ll])}%", "small": f"श्रम बल में सैनिक · {yl}"}},
        {"say": economy, "show": [(gh, 3), (gl, 3)], "cut": Gl,
         "card": {"big": "लगभग बराबर" if even_g else f"{rg} गुना", "small": f"जीडीपी · विश्व बैंक · {yg}"}},
        {"say": f"आबादी: {A} {crore(pop[a])}, {B} {crore(pop[b])}।", "show": [(a, 4), (b, 4)], "cut": B,
         "card": {"big": f"{crore(pop[a])} बनाम {crore(pop[b])}", "small": f"आबादी · संयुक्त राष्ट्र · {yp}"}},
    ]

    def fact(key, code, phrase, what, ks=pair):
        iso2 = ",".join(COUNTRIES[k][3] for k in ks)
        return {"key": key, "phrase": phrase, "source": WB_PAGE.format(code=code, iso2=iso2),
                "what": f"{SOURCES[code]} (World Bank WDI {code}, CC BY 4.0): {what}"}

    facts = [
        fact("troops-ratio", TROOPS, f"{yt} {rt} गुना", f"{yt}: {troops[a]:,.0f} / {troops[b]:,.0f}"),
        *(fact(f"troops-{k}", TROOPS, f"{yt} {people(troops[k])}", f"{yt}: {troops[k]:,.0f} armed forces personnel, "
               "paramilitary included", (k,)) for k in pair),
        *(fact(f"labour-{k}", LABOUR, f"{yl} {_one(labour[k])} प्रतिशत", f"{yl}: {labour[k]:.2f}% of the labour force",
               (k,)) for k in pair),
        fact("gdp-ratio", GDP, f"{yg} {rg} गुना", f"{yg}: {gdp[gh]:,.0f} / {gdp[gl]:,.0f} current US$"),
        *(fact(f"people-{k}", PEOPLE, f"{yp} {crore(pop[k])}", f"{yp}: {pop[k]:,.0f}", (k,)) for k in pair),
    ]
    # Each count names whose it is: "बराबर सेनाएं, अर्थव्यवस्था 12 गुना" read as Russia's economy being America's
    # twelve times over (it is the other way round).
    forces = "सेनाएं लगभग बराबर" if even_t else f"सेना में {A} {rt} गुना"
    economy_t = "अर्थव्यवस्थाएं लगभग बराबर" if even_g else f"अर्थव्यवस्था में {G} {rg} गुना"
    title = f"{A} बनाम {B}: {forces}, {economy_t}"
    return {"lead": a, "other": b, "title": title, "beats": beats, "facts": facts, "year": yg,
            "years": {c: data[c][0] for c in INDICATORS}}


# How a photo's file or description names the country's own forces. A city or a parade is not enough: "2010 Moscow
# Victory Day Parade-9.jpeg" (a Russian caption) shows Belarus's contingent and flag (dry run 40115521331).
FORCES = {
    "IND": r"Indian (?:Army|Air Force|Navy|Coast Guard)|\bIAF\b|\bINS [A-Z]|Indian Army",
    "PAK": r"Pakistan (?:Army|Air Force|Navy)|\bPAF\b|\bPNS [A-Z]|Pakistan Day Parade",
    "CHN": r"People's Liberation Army|\bPLA(?:\b|N)|Chinese (?:Army|Navy|Air ?Force)|PLA\(N\)|Chengdu J-20",
    "USA": r"U\.? ?S\.? (?:Army|Navy|Air Force|Marine Corps|Marines|Space Force)|\bUSS [A-Z]|United States (?:Army|"
           r"Navy|Air Force|Marine Corps)",
    "RUS": r"Russian (?:Army|Air Force|Navy|navy|Aerospace Forces|Ground Forces|Armed Forces)|Russian Federation "
           r"(?:Army|Navy|Air Force)",
    "UKR": r"Ukrainian (?:Army|Air Force|Navy|navy|Ground Forces)|Armed Forces of Ukraine|Ukraine - Air Force|"
           r"Ukrainian (?:soldiers|military)",
    "ISR": r"Israel(?:i)? (?:Defense Forces|Air Force|Navy)|\bIDF\b|IAF-F-35I|Israeli Sa'ar|Saar-\d|Merkava",
    "IRN": r"Iranian (?:army|Army|Air Force|air force|navy|Navy)|Islamic Republic of Iran (?:Navy|Air Force|Army)|"
           r"\bIRGC\b|Army of Iran",
}


def own(p, iso3: str) -> bool:
    """The photo is of this country's forces by its own words: its file or description names the country's forces
    (FORCES) and no other listed country. A "Pakistan Army parade" search returned an Indian Army regiment's
    bicentenary (2026-10-24)."""
    named = f"{p.file} {p.description or ''}"
    text = f"{named} {' '.join(p.categories or [])}"
    return bool(re.search(FORCES[iso3], named)) and set(_iso3(text)) <= {iso3}


def forces_photos(iso3: str, folder: Path, taken: set[str], recent: set[str] = frozenset(),
                  want: int = 5) -> list[dict]:
    """Up to `want` free Commons photos of a country's forces, one search after another, MIN_YEAR or newer, none of
    an emblem or a named person, preferring photos the channel has not shown lately."""
    pools: list[list] = []
    for q in COUNTRIES[iso3][4]:
        try:
            files = media._search_files(q, 25)
        except Exception:
            continue
        picked = [p for p in media.picks(files, 12)
                  if (media.year_of(p) or 0) >= MIN_YEAR and own(p, iso3)
                  and not NOT_FORCES.search(f"{p.file} {p.description}") and not NAMED.search(p.description or "")]
        pools.append(sorted(picked, key=lambda p: p.file in recent))
    # One from each search in turn (a parade, a jet, a ship, a tank), not two looks at one jet.
    found: list = []
    for rank in range(max(map(len, pools), default=0)):
        for pool in pools:
            if len(found) < want and rank < len(pool) and pool[rank].file not in taken:
                found.append(pool[rank])
                taken.add(pool[rank].file)
    return media.as_dicts(media.download(found, folder))


def build(cand: dict, get=net.get_json, photos_for=forces_photos) -> Short:
    pair = tuple(cand["pair"])
    data = figures(pair, get)
    s = script(pair, data)
    from . import writer

    recent, taken = writer.recent_photos(), set()
    folder = writer.WORK / cand["id"] / "photos"
    photos, own = [], {}
    for k in (s["lead"], s["other"]):
        mine = photos_for(k, folder / k, taken, recent)
        if len(mine) < MIN_PHOTOS:
            raise ValueError(f"compare: only {len(mine)} free photos of {COUNTRIES[k][0]}'s forces")
        own[k] = list(range(len(photos), len(photos) + len(mine)))
        for p in mine:
            # tag: the country stamped on every view of it (compose.places_on); no "who", whose one-off name strap
            # would repeat it.
            p.update(role="thing", tag=COUNTRIES[k][2], depicts=[hindi.norm(COUNTRIES[k][2])])
        photos += mine
    cast = [{"en": COUNTRIES[k][0], "hi": COUNTRIES[k][2], "kind": "thing", "photos": own[k]} for k in own]
    beats = []
    for b in s["beats"]:
        shown = [own[k][slot % len(own[k])] for k, slot in b["show"]]
        cut = b.get("cut") or ""
        at = b["say"].rfind(cut) if cut else -1
        beats.append(Beat(b["say"], "photo:" + "/".join(map(str, shown)), b["card"], cut_word=cut, cut_at=at))
    facts = []
    for f in s["facts"]:
        facts.append(Fact(f["key"], f["phrase"], f["source"], [v for v, _ in hindi.numbers(f["phrase"])], f["what"]))
    sources = list(dict.fromkeys(f.source for f in facts))
    A, B = COUNTRIES[s["lead"]][2], COUNTRIES[s["other"]][2]
    en = f"{COUNTRIES[s['lead']][0]} vs {COUNTRIES[s['other']][0]}"
    credits = [CREDIT] + sorted({p["credit"] + " " + p["page"] for p in photos})
    region = "india" if "IND" in pair else "world"
    scene = {"template": "full", "mood": "news", "voice": "sulafat", "region": region, "photos": photos,
             "name_hi": "", "subject_person": False, "names": [], "cast": cast, "category": "defence",
             "category_hi": "देशों की तुलना", "lane": "compare", "pair": list(pair), "min_photos": 2 * MIN_PHOTOS,
             "hook": "", "writer": {"models": ["template"], "rejected": [], "titles": [s["title"]]}}
    tags = [f"{en} military", f"{en} army comparison", f"{en} economy", f"{COUNTRIES[s['lead']][0]} armed forces",
            f"{COUNTRIES[s['other']][0]} armed forces", "country comparison", "hindi news", "news in hindi"]
    slug = lambda k: re.sub(r"[^a-z]", "", COUNTRIES[k][0].lower())  # noqa: E731
    hashtags = [f"{slug(s['lead'])}vs{slug(s['other'])}", "defence", "military", "hindinews", "shorts",
                slug(s["lead"]), slug(s["other"]), "worldnews" if region == "world" else "indianews", "रक्षा"]
    y = s["years"]
    summary = (f"{A} और {B} की तुलना: सशस्त्र बल, श्रम बल में सैनिकों का हिस्सा, अर्थव्यवस्था और आबादी। "
               f"स्रोत, World Bank World Development Indicators (CC BY 4.0) के ज़रिये: सशस्त्र बल और श्रम बल में "
               f"हिस्सा ({y[TROOPS]}, अर्धसैनिक बल समेत): IISS, The Military Balance; जीडीपी ({y[GDP]}): राष्ट्रीय लेखा; "
               f"आबादी ({y[PEOPLE]}): UN World Population Prospects। हर आंकड़े का साल वीडियो में बताया गया है।")
    return Short(id=cand["id"], kind="compare", title=s["title"], beats=beats, facts=facts, sources=sources,
                 loss=False, scene=scene, event_time=f"{s['year']}", tags=tags, summary=summary, credits=credits,
                 hashtags=hashtags)


def _day(at: datetime) -> str:
    return (at + timedelta(hours=5, minutes=30)).strftime("%Y%m%d")


def _pair_of(sid: str) -> tuple[str, str] | None:
    m = re.match(rf"{PREFIX}\d{{8}}-([A-Z]{{3}})-([A-Z]{{3}})", sid or "")
    return (m.group(1), m.group(2)) if m else None


def news_pairs(stories: list[dict]) -> list[tuple[tuple[str, str], dict]]:
    """The listed pairs today's well-reported stories name both countries of: (pair, story), best covered first."""
    out = []
    for c in stories:
        if len(c.get("owners") or []) < OWNERS:
            continue
        text = " ".join([c.get("title") or ""] + [h if isinstance(h, str) else h.get("title", "")
                                                   for h in c.get("headlines") or []])
        named = set(_iso3(text))
        out += [(p, c) for p in PAIRS if set(p) <= named]
    return sorted(out, key=lambda pc: -len(pc[1].get("owners") or []))


def candidate(pair, at: datetime, why: str, story: dict | None = None) -> dict:
    # One id per pair whichever way it is asked for (PAK-IND is IND-PAK): the cooldown reads ids.
    a, b = next((p for p in PAIRS if set(p) == set(pair)), tuple(pair))
    title = f"{COUNTRIES[a][0]} and {COUNTRIES[b][0]} military comparison"
    return {"id": f"{PREFIX}{_day(at)}-{a}-{b}-{FORMAT}", "kind": "compare", "compare": True, "pair": [a, b], "title": title,
            "name": title, "category": "defence", "region": "india" if "IND" in pair else "world",
            "date": at.date().isoformat(), "news_at": at.isoformat(), "fame": FAME, "owners": [],
            "headlines": [], "top": None, "why": why, "story": (story or {}).get("id")}


def candidates(stories: list[dict], rows: list[dict], at: datetime) -> tuple[list[dict], list[str]]:
    """Today's comparison, if one is due: a pair in the news first, else the next evergreen pair while the channel is
    quiet (nothing published for revisit.IDLE); none when PER_DAY ran today, none for a pair told within
    PAIR_DAYS."""
    from . import revisit

    if not ENABLED:
        if ONE_OFF and not any(_pair_of(r.get("id") or "") == ONE_OFF and r["id"] not in RETIRED for r in rows):
            return [candidate(ONE_OFF, at, "the corrected India-Pakistan comparison")], []
        return [], []
    day = _day(at)
    mine = [r for r in rows if (r.get("id") or "").startswith(PREFIX) and r["id"] not in RETIRED]
    if sum(_day(_at(r) or at) == day for r in mine) >= PER_DAY:
        return [], ["compare: one ran today"]
    since = at - timedelta(days=PAIR_DAYS)
    told = {frozenset(p) for r in mine if (p := _pair_of(r["id"])) and (_at(r) or at) >= since}
    for pair, story in news_pairs(stories):
        if frozenset(pair) not in told:
            return [candidate(pair, at, "in the news", story)], []
    last_any = max((t for r in rows if (t := _at(r))), default=None)
    if last_any is None or at - last_any < revisit.IDLE:
        return [], []
    last = {frozenset(p): _at(r) for r in mine if (p := _pair_of(r["id"]))}
    fresh = [p for p in PAIRS if frozenset(p) not in told]
    if not fresh:
        return [], ["compare: every pair ran in the last 14 days"]
    fresh.sort(key=lambda p: last.get(frozenset(p)) or datetime.min.replace(tzinfo=timezone.utc))
    return [candidate(fresh[0], at, "the channel is quiet")], []


def _at(row: dict) -> datetime | None:
    for key in ("published_at", "at", "made_at"):
        if v := row.get(key):
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def from_target(target: str, at: datetime | None = None) -> dict:
    """"compare:IND-PAK" (desk make) as a candidate."""
    a, b = target.split(":", 1)[1].upper().split("-")
    if a not in COUNTRIES or b not in COUNTRIES:
        raise ValueError(f"compare: no data list for {a} or {b} (have {', '.join(COUNTRIES)})")
    return candidate((a, b), at or datetime.now(timezone.utc), "asked for")
