"""Defence comparison Shorts ("भारत बनाम पाकिस्तान"): two countries' military spending, its share of the economy,
the armed forces and the spending per person, from the World Bank's World Development Indicators (SIPRI's
figures, CC BY 4.0), over each country's own freely licensed Commons photos of its forces. No model writes them:
every line is a template filled with a published number, so a comparison cannot say what the data does not.

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
WB_PAGE = "https://data.worldbank.org/indicator/{code}?locations={iso2}"
SPEND, SHARE, TROOPS, PEOPLE = "MS.MIL.XPND.CD", "MS.MIL.XPND.GD.ZS", "MS.MIL.TOTL.P1", "SP.POP.TOTL"
PREFIX, PER_DAY, PAIR_DAYS, OWNERS, FAME = "cmp-", 1, 14, 3, 1
# Off: the World Bank's military expenditure series are under SIPRI's terms (WDI metadata License_Type), which
# require SIPRI's authorization for commercial use, a monetized channel included (2026-10-24).
ENABLED = False
MIN_PHOTOS = 3  # per country: the Short cuts between its forces on land, in the air and at sea
CREDIT = ("तथ्य: World Bank World Development Indicators (SIPRI के आंकड़े, CC BY 4.0); "
          "तस्वीरें: Wikimedia Commons (लाइसेंस नीचे)")

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
            ["Moscow Victory Day Parade", "Sukhoi Su-57", "Russian Navy ship", "Russian Army T-90"]),
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
                        # Another country's forces beside them: a joint exercise is not one country's.
                        r"alongside|counterparts|multinational|joint (?:exercise|training)|bilateral", re.I)
# A named person's face is someone the voice never names: no ministers, generals or leaders at a parade.
NAMED = re.compile(r"با حضور|از چپ|از راست|\b(?:From left|from right|L-R|pose[sd]? for|Embassy|delegation|Prime Minister|"
                   r"President|Minister|General|Gen\.|Admiral|Marshal|Chief|Secretary|Sgt\.?|Sergeant|Capt\.|Lt\.|"
                   r"Col\.|Maj\.|Pvt\.|Spc\.|Cpl\.|mentor|Modi|"
                   r"Putin|Xi Jinping|Biden|Trump|Netanyahu|Khamenei|Zelensky\w*|Shoigu|Hegseth|Austin|Sharif|"
                   r"Munir|Rajnath|Singh)(?!\w)")


def _iso3(text: str) -> list[str]:
    return [k for k, v in COUNTRIES.items() if re.search(rf"\b(?:{v[1]})(?!\w)", text or "")]


def figures(pair, get=net.get_json) -> dict[str, dict[str, tuple[int, float]]]:
    """{iso3: {indicator: (year, value)}}: each country's latest published value of each indicator."""
    out: dict[str, dict] = {k: {} for k in pair}
    for code in (SPEND, SHARE, TROOPS, PEOPLE):
        d = get(WB.format(codes=";".join(pair), code=code), params={"format": "json", "mrnev": 1, "per_page": 50},
                timeout=60)
        for row in (d[1] if isinstance(d, list) and len(d) > 1 else None) or []:
            if row.get("countryiso3code") in out and row.get("value") is not None:
                out[row["countryiso3code"]][code] = (int(row["date"]), float(row["value"]))
    missing = [f"{k} {c}" for k in pair for c in (SPEND, SHARE, TROOPS, PEOPLE) if c not in out[k]]
    if missing:
        raise ValueError("compare: the World Bank has no figure for " + ", ".join(missing))
    return out


def _one(x: float) -> str:
    """One decimal, without a trailing .0 ("7.8", "12")."""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def money(usd: float) -> str:
    """"92.1 अरब डॉलर", "27.8 करोड़ डॉलर"."""
    return f"{_one(usd / 1e9)} अरब डॉलर" if usd >= 1e9 else f"{_one(usd / 1e7)} करोड़ डॉलर"


def people(n: float) -> str:
    """"30.7 लाख", "94 हज़ार"."""
    return f"{_one(n / 1e5)} लाख" if n >= 1e5 else f"{round(n / 1e3)} हज़ार"


def times(a: float, b: float) -> str:
    return _one(a / b)


def script(pair, data) -> dict:
    """The title, the beats ({say, show: [(iso3, slot)], card}) and the facts ({key, phrase, code, iso3s, what})."""
    a, b = sorted(pair, key=lambda k: -data[k][SPEND][1])  # the bigger spender leads
    A, B = COUNTRIES[a][2], COUNTRIES[b][2]
    (ys, sa), (_, sb) = data[a][SPEND], data[b][SPEND]
    (yg, ga), (_, gb) = data[a][SHARE], data[b][SHARE]
    (yt, ta), (_, tb) = data[a][TROOPS], data[b][TROOPS]
    pa, pb = sa / data[a][PEOPLE][1], sb / data[b][PEOPLE][1]
    r = times(sa, sb)
    hi_share, lo_share = (a, b) if ga >= gb else (b, a)
    H, L = COUNTRIES[hi_share][2], COUNTRIES[lo_share][2]
    gh, gl = data[hi_share][SHARE][1], data[lo_share][SHARE][1]
    lead_in = "और जीडीपी के हिस्से में भी" if hi_share == a else "पर जीडीपी के हिस्से में"
    # About 60 words, about 32 s at the narrator's 115 a minute (dry run 40103609151: 70 words ran 38 s). The source
    # is on the cards, in the credits and in the description, not read out.
    beats = [
        {"say": f"रक्षा पर {A} का खर्च {B} से {r} गुना है।", "show": [(a, 0), (b, 0)], "cut": B,
         "card": {"big": f"{r} गुना", "small": "रक्षा खर्च"}},
        {"say": f"{ys} में {A} ने {money(sa)} और {B} ने {money(sb)} खर्च किए।",
         "show": [(a, 1), (b, 1)], "cut": B, "card": {"big": money(sa), "small": f"{A} · {ys} · विश्व बैंक"}},
        {"say": f"{lead_in} {H} आगे है: {_one(gh)} प्रतिशत, {L} {_one(gl)} प्रतिशत।",
         "show": [(hi_share, 2), (lo_share, 2)], "cut": L,
         "card": {"big": f"{_one(gh)}% बनाम {_one(gl)}%", "small": "जीडीपी में हिस्सा"}},
        {"say": f"{yt} में {A} के सशस्त्र बल {people(ta)} और {B} के {people(tb)} थे।",
         "show": [(a, 3), (b, 3)], "cut": B,
         "card": {"big": f"{people(ta)} बनाम {people(tb)}", "small": "सशस्त्र बल, अर्धसैनिक समेत"}},
        {"say": f"हर नागरिक पर {A} {round(pa)} डॉलर और {B} {round(pb)} डॉलर खर्च करता है।",
         "show": [(a, 4), (b, 4)], "cut": B,
         "card": {"big": f"{round(pa)} बनाम {round(pb)} डॉलर", "small": "प्रति नागरिक · विश्व बैंक, सिपरी"}},
    ]
    facts = [
        {"key": "spend-ratio", "phrase": f"{r} गुना", "code": SPEND, "iso3s": (a, b),
         "what": f"{ys}: {sa:,.0f} / {sb:,.0f} US$ = {sa / sb:.2f}"},
        *({"key": f"spend-{k}", "phrase": f"{ys} {money(data[k][SPEND][1])}", "code": SPEND, "iso3s": (k,),
           "what": f"military expenditure {ys}: {data[k][SPEND][1]:,.0f} current US$"} for k in (a, b)),
        *({"key": f"share-{k}", "phrase": f"{yg} {_one(data[k][SHARE][1])} प्रतिशत", "code": SHARE, "iso3s": (k,),
           "what": f"military expenditure {yg}: {data[k][SHARE][1]:.2f}% of GDP"} for k in (a, b)),
        *({"key": f"troops-{k}", "phrase": f"{yt} {people(data[k][TROOPS][1])}", "code": TROOPS, "iso3s": (k,),
           "what": f"armed forces personnel {yt} (paramilitary included): {data[k][TROOPS][1]:,.0f}"}
          for k in (a, b)),
        *({"key": f"per-person-{k}", "phrase": f"{round({a: pa, b: pb}[k])} डॉलर", "code": PEOPLE, "iso3s": (k,),
           "what": f"{ys} spending {data[k][SPEND][1]:,.0f} US$ / population {data[k][PEOPLE][1]:,.0f}"}
          for k in (a, b)),
    ]
    title = f"{A} बनाम {B}: रक्षा खर्च में {r} गुना का फ़र्क"
    return {"lead": a, "other": b, "title": title, "beats": beats, "facts": facts, "year": ys}


def own(p, iso3: str) -> bool:
    """The photo is of this country's forces by its own words: its file or description names the country and no
    other listed one. A "Pakistan Army parade" search returned an Indian Army regiment's bicentenary (2026-10-24)."""
    text = f"{p.file} {p.description or ''} {' '.join(p.categories or [])}"
    return iso3 in _iso3(f"{p.file} {p.description or ''}") and set(_iso3(text)) <= {iso3}


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
        iso2 = ",".join(COUNTRIES[k][3] for k in f["iso3s"])
        url = WB_PAGE.format(code=f["code"], iso2=iso2)
        facts.append(Fact(f["key"], f["phrase"], url, [v for v, _ in hindi.numbers(f["phrase"])],
                          f"World Bank WDI {f['code']} (SIPRI), {f['what']}"))
    sources = list(dict.fromkeys(f.source for f in facts))
    A, B = COUNTRIES[s["lead"]][2], COUNTRIES[s["other"]][2]
    en = f"{COUNTRIES[s['lead']][0]} vs {COUNTRIES[s['other']][0]}"
    credits = [CREDIT] + sorted({p["credit"] + " " + p["page"] for p in photos})
    region = "india" if "IND" in pair else "world"
    scene = {"template": "full", "mood": "news", "voice": "sulafat", "region": region, "photos": photos,
             "name_hi": "", "subject_person": False, "names": [], "cast": cast, "category": "defence",
             "category_hi": "रक्षा तुलना", "lane": "compare", "pair": list(pair), "min_photos": 2 * MIN_PHOTOS,
             "hook": "", "writer": {"models": ["template"], "rejected": [], "titles": [s["title"]]}}
    tags = [f"{en} military", f"{en} defence budget", f"{COUNTRIES[s['lead']][0]} military spending",
            f"{COUNTRIES[s['other']][0]} military spending", "defence comparison", "hindi news", "news in hindi"]
    slug = lambda k: re.sub(r"[^a-z]", "", COUNTRIES[k][0].lower())  # noqa: E731
    hashtags = [f"{slug(s['lead'])}vs{slug(s['other'])}", "defence", "military", "hindinews", "shorts",
                slug(s["lead"]), slug(s["other"]), "worldnews" if region == "world" else "indianews", "रक्षा"]
    summary = (f"{A} और {B} की सेनाओं की तुलना: रक्षा खर्च, जीडीपी में हिस्सा, सशस्त्र बल और प्रति नागरिक खर्च। "
               f"आंकड़े: विश्व बैंक (SIPRI)।")
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
    a, b = pair
    title = f"{COUNTRIES[a][0]} and {COUNTRIES[b][0]} military comparison"
    return {"id": f"{PREFIX}{_day(at)}-{a}-{b}", "kind": "compare", "compare": True, "pair": [a, b], "title": title,
            "name": title, "category": "defence", "region": "india" if "IND" in pair else "world",
            "date": at.date().isoformat(), "news_at": at.isoformat(), "fame": FAME, "owners": [],
            "headlines": [], "top": None, "why": why, "story": (story or {}).get("id")}


def candidates(stories: list[dict], rows: list[dict], at: datetime) -> tuple[list[dict], list[str]]:
    """Today's comparison, if one is due: a pair in the news first, else the next evergreen pair while the channel is
    quiet (nothing published for revisit.IDLE); none when PER_DAY ran today, none for a pair told within
    PAIR_DAYS."""
    from . import revisit

    if not ENABLED:
        return [], []
    day = _day(at)
    mine = [r for r in rows if (r.get("id") or "").startswith(PREFIX)]
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
