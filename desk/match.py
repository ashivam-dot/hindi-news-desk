"""Anchored pictures: a beat shows only what it names, else an honest text card (SYNC-AUDIT 4.1 step 2).

Three audits of 23 Shorts (2026-10-22) found 98 of 145 beats showing a picture the voice was not talking about: the
Rubio Short (39714003987) opened on his 1989 yearbook photo, put the Vantara map under lines about crude oil and
data centres, and filled 67% of its time with maps. Pictures were attached by name after the script and every gap
was filled with the subject's portrait or any map. Here nothing fills a gap: the main view is the picture of the
first thing the beat names, the cut is the picture of the next different thing, on its word, and a beat that names
nothing gets a card (the subject only on the strict pronoun rule). Pure: no network, so the gate (problems) runs the
same logic on any saved short.json.
"""
from __future__ import annotations

import functools
import re
from collections import Counter

from . import config, hindi, media, things, visuals
from .spec import shot_photos

SUBJECT, POLICE = "@subject", "@police"
# A story photo nothing verifies is of the subject (writer.fill_photos: a school, a factory, an Openverse scene, added
# when the story has too few of its own): no beat names it, so it is never on screen (the JNU admin block stood under
# "जयशंकर ने व्यापार समझौते पर भी बात की", 2026-10-22 review).
CONTEXT = "@context"
CARD = "card"
# A beat that names nothing holds the subject only when it opens on a pronoun AND the previous beat's main picture
# was the subject: "फडणवीस भी उनके साथ" is not a leading pronoun, so it is not about Tiger Shroff (39508637683 b2).
LEAD = re.compile(r"^(उन्होंने|उनके|उनका|उनकी|उन्हें|उनको|उनसे|वे|वह)(?=\s|$)")
CONTINUITY = 2  # such beats a Short may hold, never two in a row
# "दोनों नेताओं ने ..." right after a beat that showed two people: it is about the pair (dry run 39827809002, Tusk and
# Modi, b3 "दोनों नेताओं ने इंडिया और पोलैंड के बीच व्यापार बढ़ाने पर चर्चा की" was a card).
# After "रिपोर्टों के मुताबिक," too (dry run 39833792083 b2 "रिपोर्टों के मुताबिक, दोनों नेताओं ने ... बैठक की").
BOTH = re.compile(r"^(?:(?:रिपोर्टों|रिपोर्ट्स|खबरों|सूत्रों|अधिकारियों) के (?:मुताबिक|अनुसार),?\s*)?(दोनों)(?=\s|$)")
# "दोनों" anywhere in a beat that names one of the pair: "प्रधानमंत्री नरेंद्र मोदी ने ... दोनों नेताओं की बैठक की" (dry
# run 39845458169 b2 showed Modi alone for 5.8 s while the voice said the two leaders met): the pair, cut on "दोनों".
BOTH_ANY = re.compile(r"(?<![\u0900-\u097F])दोनों(?![\u0900-\u097F])")
# Only "दोनों" that means the two people shown: as the subject or with a word for people ("दोनों नेताओं", "दोनों ने",
# "दोनों के बीच"), never "दोनों आरोपियों", "दोनों घायलों", "दोनों बच्चों", "दोनों देशों" or "दोनों पक्षों" (review round 2:
# Tusk and Modi stood under "दोनों आरोपियों को पुलिस ने गिरफ्तार किया"), and never in a harm or accused line.
PAIR_NOUNS = ("नेता", "नेताओं", "मंत्री", "मंत्रियों", "प्रधानमंत्रियों", "राष्ट्राध्यक्षों", "राष्ट्रपतियों", "दिग्गजों",
              "हस्तियों", "अभिनेता", "अभिनेताओं", "सितारों", "स्टार्स", "खिलाड़ी", "खिलाड़ियों")
PAIR_AFTER = ("ने", "के", "की", "का", "से", "को", "में", "पर")
# A leading pronoun that is the speaker of a "... कि" clause naming someone else ("उन्होंने दावा किया कि राहुल गांधी की
# पार्टी ...", dry run 39794659993 b5 about Amit Shah showed only Rahul): the one who claims is not the one claimed
# about, so in a person's Short it is the subject (speaker), wherever the previous beat's picture was.
SPOKE = re.compile(r"(?:कहा|कहना है|दावा किया|दावा करते हुए कहा|बताया|आरोप लगाया|सवाल उठाया|पूछा|ऐलान किया|घोषणा की)"
                   r"\s*,?\s*कि(?=\s|$)")
# Never on a pronoun alone: a harm line (Tiger Shroff smiling under "उनके ड्राइवर और एक फैन को गोली लगी",
# 39505534156 b4) or an actor no picture is of ("मेहमान नेता", "एक व्यक्ति ने इस हमले की जिम्मेदारी ली"). Each is the
# start of a word (says), and the forms in WHOLE whole words: "अमृतसर" is no death, "व्यक्तिगत" no person, "चोटी" no
# injury (2026-10-22 review).
HARM = ("हमल", "फायरिंग", "फ़ायरिंग", "गोली", "घायल", "जख्मी", "ज़ख्मी", "मौत", "मृत", "हत्या", "चोट", "चोटें", "चोटों",
        "चोटिल", "धमकी", "हिंसा", "निधन")
UNNAMED = ("मेहमान", "संगठन", "विपक्ष", "व्यक्ति", "व्यक्तियों", "शख्स", "शख़्स", "बदमाश", "गिरोह", "गैंग")
WHOLE = {"चोट", "चोटें", "चोटों", "चोटिल", "व्यक्ति", "व्यक्तियों"}
# Whom a harm line names as someone's: "फायरिंग में टाइगर के ड्राइवर ... के हाथ में गोली लगी" (39553699482 b3) is
# about the driver, so Tiger Shroff's face does not go under "हाथ में गोली".
OWNED = ("ड्राइवर", "ड्राइवरों", "बॉडीगार्ड", "गार्ड", "सुरक्षाकर्मी", "सुरक्षाकर्मियों", "फैन", "फैंस", "प्रशंसक", "प्रशंसकों",
         "कर्मचारी", "कर्मचारियों", "स्टाफ", "मैनेजर", "साथी", "सहायक", "नौकर", "पिता", "मां", "माँ", "भाई", "बहन", "बेटे",
         "बेटा", "बेटी", "पत्नी", "पति", "दोस्त", "रिश्तेदार")
# Family is someone else in any line: "प्रियंका वाड्रा के बेटे ने कहा ..." is about her son, not a picture of her (review
# round 1: the mother's face under her son's lines, the owner's "where is rehan photo").
KIN = ("पिता", "मां", "माँ", "भाई", "बहन", "बेटे", "बेटा", "बेटी", "बेटियों", "पत्नी", "पति", "पोते", "पोती", "भतीजे", "भतीजी",
       "दामाद", "बहू", "रिश्तेदार")
_DEV = "\u0900-\u097F"
_OWNED = re.compile(rf"\s+(?:के|की|का)\s+(?:एक\s+)?(?:{'|'.join(OWNED)})(?![{_DEV}])")
# Not as a description of whom the line is about: "टाइगर जैकी श्रॉफ के बेटे हैं" names Jackie as Jackie.
_KIN = re.compile(rf"\s+(?:के|की|का)\s+(?:एक\s+)?(?:{'|'.join(KIN)})(?![{_DEV}])(?!\s*(?:हैं|है|थे|था|थीं|थी|हो)(?![\u0900-\u0963\u0966-\u097F]))")
# Paired ceilings (4.0, tightened 2026-10-22 after CAPraPdXvns: a map of New Delhi or Bikaner House under four of
# five beats, under "तिरंगे" and under Raihan, whose photo it had not). Cards at most a third of the beats (at least
# one allowed) and never CARD_RUN in a row; at most MAX_MAP_VIEWS map view a Short (routes are maps), only as the
# whole of a beat that names nothing but places, never under a beat naming a person or thing with a photo, and maps
# at most MAP_SHARE of the picture time (a text card's time not being picture time); no picture under HELD_RUN
# beats in a row or more than half the beats (gate.held, which plan keeps to). The floor: real photos (anchored,
# vetted, not maps) fill at least REAL_SHARE of the Short; it pairs with shown-is-said (a photo counts only where its
# beat names it), so it cannot be met with pictures the voice is not talking about.
CARD_RUN, MAP_SHARE, HELD_RUN = 2, 0.2, 3
MAX_MAP_VIEWS, REAL_SHARE = 1, 0.5
# The floor paired with them in a person's Short: the subject on screen at least SUBJECT_SHARE of it (real pictures
# review round 1, the Amit Shah dry run: Rahul Gandhi as long as Shah, a card over Rahul for a line about Shah).
# A quarter, calibrated on the 44-Short replay: the Tiger Shroff explainers that show him under every beat naming him
# sit at 25-29% beside Shinde, Jackie Shroff and the police; the Tusk Short that names him once in five beats, 20%.
SUBJECT_SHARE = 0.25
# The seconds ceiling paired with HELD_RUN's beats (review round 2): one picture up at most HOLD_MAX seconds in a row,
# a cut to the same photo closer counting as the same picture. Dry run 39871573344 held Neha Bora's portrait 11.7 s
# while 8 s of uncaptioned voice played past the beat's last word; a beat count never saw it. compose.twins cuts a
# longer hold to another photo of the same person or place when there is one. Ten seconds, calibrated on the replay:
# one long beat over its one photo (Rajiv Gandhi, 39747949900) runs 9.6 s; the old Tiger Shroff pools held one
# police photo 10-14 s over three beats.
HOLD_MAX = 10.0
MEMBERS = ("person", "place", "topic", "thing")
PUNCT = "\"',.;:!?।()"
# compose.render_full's hook card (the first HOOK_HOLD seconds) and fact chips (CHIP_HOLD each, never past the cut:
# chip_window), here so the gate reads the same windows off render.json. A chip the cut leaves under CHIP_MIN is
# not shown: half a second of text is a flicker, not a fact.
HOOK_HOLD, CHIP_HOLD, CHIP_MIN = 3.6, 3.0, 1.0
# The harm words that say someone was hurt or died, not that something happened ("जुहू में फायरिंग" over Tiger
# Shroff is his story): a hook with one over the subject's face says the subject was hurt (hook_problems).
HURT = ("गोली", "घायल", "जख्मी", "ज़ख्मी", "मौत", "मृत", "हत्या", "चोट", "चोटें", "चोटों", "चोटिल", "निधन")
OTHER_POLICE = "@another-police"  # a force that is not the one on screen ("राजस्थान पुलिस" over Mumbai Police)


def says(say: str, words) -> int:
    """Where say first has one of words as the start of a word (a form in WHOLE as a whole word), else -1."""
    hits = [m.start() for w in words for m in re.finditer(
        rf"(?<![{_DEV}]){re.escape(w)}" + (rf"(?![{_DEV}])" if w in WHOLE else ""), say)]
    return min(hits, default=-1)


def pair_at(say: str) -> int:
    """Where say's "दोनों" means the two people on screen (PAIR_NOUNS, PAIR_AFTER, or ending the clause), else -1;
    never in a harm or accused line."""
    if says(say, HARM + visuals.ACCUSED) >= 0:
        return -1
    for m in BOTH_ANY.finditer(say):
        nxt = re.findall(rf"[{_DEV}]+|[{re.escape(PUNCT)}]", say[m.end():])
        nxt = [w for w in nxt[:2] if w not in ("ही", "भी")][:1] or nxt[2:3]
        if not nxt or nxt[0] in PUNCT or nxt[0] in PAIR_NOUNS or nxt[0] in PAIR_AFTER:
            return m.start()
    return -1


def key(c: dict) -> str:
    """What a cast member is on screen: its Hindi name, spelling differences aside; any police force is POLICE."""
    return POLICE if c.get("kind") == "police" else hindi.norm(c.get("hi") or c.get("en") or "")


def _map_names(photo: dict, cast: list[dict]) -> list[str]:
    """The Hindi names a locator map marks, by its description: "MAP: X in Y" and "where X is" and "X up close"
    mark X (a spot on its city's map is the spot), "X and Y" marks both (a route)."""
    who = photo.get("who") or ""
    about = re.sub(r"^MAP:\s*", "", photo.get("description") or "")
    route = " - " in who or bool(re.fullmatch(r".+ and .+", about))
    parts = [w.strip() for w in re.split(r",| - ", who) if w.strip()]
    if parts:
        return parts if route else parts[:1]
    m = re.fullmatch(r"where (.+) is|(.+) up close|(.+) and (.+)|(.+) in .+", about)
    ens = [g for g in (m.groups() if m else ()) if g]
    by_en = {(c.get("en") or "").lower(): c.get("hi") or c.get("en") for c in cast}
    return [by_en.get(e.lower(), e) for e in ens]


def depicts(i: int, photo: dict, cast: list[dict] = ()) -> set[str]:
    """The keys photo i shows: its stamped label when it has one; for older artifacts, read from its role, its
    on-screen name and a map's description. A story's own photo (no role) is the SUBJECT, unless it is a fill
    (writer.fill_photos, an Openverse photo, or another item's photo with no face matched): CONTEXT."""
    if photo.get("depicts") is not None:
        return set(photo["depicts"])
    role = photo.get("role")
    if not role:
        return {CONTEXT} if fill(photo) else {SUBJECT}
    if role == "police":
        return {POLICE}
    if role == "map":
        return {hindi.norm(n) for n in _map_names(photo, list(cast)) if n}
    if photo.get("who"):
        return {hindi.norm(photo["who"])}
    return {key(c) for c in cast if i in (c.get("photos") or [])}


def fill(photo: dict) -> bool:
    """A story photo that is not verified to show the story's subject: a context fill (writer.fill_photos), an
    Openverse photo, or another item's own photo (media.find's "related" and "place") with no face matched."""
    return bool(photo.get("fill")) or photo.get("origin") == "openverse" or \
        photo.get("origin") in ("related", "place") and photo.get("focus") is None


def held_key(i: int, photos: list[dict], groups: dict[int, str]):
    """What gate.held counts photo i as: a place's maps one picture (match.group), any other map its file, a photo
    one of a look (visuals.looks: one file a crop of another, the same portrait), else i. Dry run 39845458169 held
    Modi's one official portrait, as two files, ~30 of 33 s and no ceiling saw it."""
    p = photos[i] if i < len(photos) else {}
    g = groups.get(i, "")
    if visuals.is_map(p):
        return g if g.startswith("place:") else p.get("file")
    return "look:" + p["look"] if p.get("look") else i


def inside(photos: list[dict], cast: list[dict] = ()) -> dict[str, str]:
    """{spot key: its city's key}: from the cast ("inside") and from maps marked "X, Y" ("MAP: Juhu in Mumbai")."""
    by_en = {c.get("en"): c for c in cast}
    out = {key(c): key(by_en[c["inside"]]) for c in cast if c.get("inside") and c["inside"] in by_en}
    for p in photos:
        parts = [w.strip() for w in (p.get("who") or "").split(",") if w.strip()]
        if visuals.is_map(p) and len(parts) == 2 and " - " not in p["who"]:
            out.setdefault(hindi.norm(parts[0]), hindi.norm(parts[1]))
    return out


def group(photos: list[dict], cast: list[dict] = ()) -> dict[int, str]:
    """{photo index: what it counts as on screen}: a place's maps and its own photo are one place, and a nested
    spot's maps count in its city's group (the Kota court Short held Kota's maps under six of seven beats); every
    other photo counts alone."""
    up = inside(photos, cast)
    out = {}
    for i, p in enumerate(photos):
        d = depicts(i, p, cast)
        if p.get("role") in ("map", "place") and len(d) == 1:
            k = next(iter(d))
            out[i] = "place:" + up.get(k, k)
        else:
            out[i] = f"photo:{i}"
    return out


def _end(say: str, at: int, words: int) -> int:
    m = re.match(rf"(?:\S+\s*){{1,{max(words, 1)}}}", say[at:])
    return at + (len(m.group(0).rstrip()) if m else 0)


def _spelt(c: dict) -> list[str]:
    return [w for w in [c.get("hi") or "", *(c.get("alias") or [])] if w]


# A script name that is an honour, a body, a road or a building, never a person a card could show the wrong face for
# ("पद्म श्री सम्मान" over Jaishankar: the award he received, 39411111185 b6).
NOT_A_PERSON = re.compile(r"\b(Shri|Shree|Bhushan|Vibhushan|Ratna|Award|Prize|Medal|Party|Marg|Road|Street|Hospital|"
                          r"Mantar|Temple|Mandir|Masjid|Ministry|Police|Court|Bank|Council|Committee|Station|Airport|"
                          r"University|College|School|Festival|Mission|Act|Bill|Scheme|Yojana|Group|Limited|Ltd|"
                          r"Industries|Corporation|Company|Association|Union|Foundation|Trust|Army|Force|Gate|Fort)\b",
                          re.I)


def others_of(names_: list[dict] | None, cast: list[dict], spellings=()) -> list[dict]:
    """The script's names (scene.names, the draft's) that are neither in the cast nor the subject, nor a police
    force: [{hi, kind: "name"}]. Jackie Shroff is one when his lookup failed or MAX_PEOPLE was reached (the
    government Short 39546660530 has no cast at all), Sanjay Raut when he was not resolved: a beat or card naming
    them is not about the subject (names, problems, visuals.card_over). A name is the subject's own only when it is
    one of its spellings or opens and ends with the subject's first and last words (a middle name): "अमित मालवीय"
    in an Amit Shah Short is not Shah (2026-10-22 review round 2). A one-word name is a country, city or firm far more often than a person (भारत, मुंबई,
    रिलायंस: 39411111185's card "भारत दौरा" over Rubio's arrival is about his visit, not a picture of India)."""
    members = [c for c in cast if c.get("kind") in MEMBERS]
    known = {hindi.norm(w) for c in members for w in _spelt(c)} | {hindi.norm(w) for w in spellings if w}
    known_en = {(c.get("en") or "").lower() for c in members} - {""}
    full = max((w for w in spellings if w), key=lambda w: len(w.split()), default="").split()
    ends = (hindi.norm(full[0]), hindi.norm(full[-1])) if len(full) > 1 else None
    out = []
    for n in names_ or []:
        hi = (n.get("hi") or "").strip()
        if len(hi.split()) < 2 or any(w in hi for w in visuals.POLICE) or hindi.norm(hi) in known \
                or NOT_A_PERSON.search(n.get("en") or "") or (n.get("en") or "").lower() in known_en \
                or ends and (hindi.norm(hi.split()[0]), hindi.norm(hi.split()[-1])) == ends:
            continue
        if all(o["hi"] != hi for o in out):
            out.append({"hi": hi, "kind": "name"})
    return out


def names(say: str, cast: list[dict], subject_spellings=(), others=()) -> list[tuple[int, str]]:
    """(where in say, key) for everything the beat names that a picture could be of, in order: cast members (via
    visuals.located), the story's subject by any of its spellings outside every other person's name, each time it is
    said (a "श्रॉफ" inside "जैकी श्रॉफ" is not Tiger Shroff, nor is the second "जैकी श्रॉफ"), the script's other names
    (others_of: never pictured, so a beat or card naming only them shows no one), and the police for a police or
    accused line when the cast has a police row (never another force's: "राजस्थान पुलिस"; without one no police
    picture exists, so writer.anchorless counts the line as naming nothing). "<city> पुलिस" names the police, not the
    city. A person a harm line names as someone's ("टाइगर के ड्राइवर ... गोली लगी") is not what it is about. A title
    spelling ("प्रधानमंत्री", visuals.titles) is the subject only when no other person's name follows it and no "X के"
    qualifies it: "पाकिस्तान के प्रधानमंत्री शहबाज शरीफ" is not Modi (2026-10-22 review round 2)."""
    members = [c for c in cast if c.get("kind") in MEMBERS]
    extra = others_of(others, cast, subject_spellings)
    police = next((c for c in cast if c.get("kind") == "police"), None)
    places = [w for c in members if c.get("kind") == "place" for w in _spelt(c)] + [o["hi"] for o in extra]
    other = police is None or visuals.other_force(say, police, places)
    harm = says(say, HARM) >= 0

    def owned(at: int, words: int) -> bool:
        rest = say[_end(say, at, words):]
        return bool(_KIN.match(rest)) or harm and bool(_OWNED.match(rest))

    def spans(rows: list[dict]) -> list[tuple[int, int]]:
        return [(a, _end(say, a, len(w.split()))) for c in rows for w in _spelt(c) for a in visuals._finds(say, w)]

    theirs = spans(extra)
    people = spans([m for m in members if m.get("kind") == "person"]) + theirs
    found, masked = [], list(say)
    for a, z in people:
        masked[a:z] = " " * (z - a)
    for at, c in visuals.located(say, members):
        spelt = [w for w in _spelt(c) if hindi.find(say, w) == at]
        n = max((len(w.split()) for w in spelt), default=1)
        end = _end(say, at, n)
        if c.get("kind") == "person" and (owned(at, n) or any(a <= at < z and z - a > end - at for a, z in theirs)):
            continue  # "अनंत अंबानी" is not Mukesh Ambani by his surname
        if c.get("kind") == "thing" and things.blocked(say, at, c.get("en") or ""):
            continue  # "अमेरिका के सुप्रीम कोर्ट" is not India's, "वंदे भारत मिशन" no train (things.blocked)
        if c.get("kind") == "place" and re.match(r"\s*पुलिस", say[end:]):
            if not other:
                found.append((at, POLICE))
            continue
        found.append((at, key(c)))
    for c in extra:
        at = min((a for w in _spelt(c) for a in visuals._finds(say, w)), default=-1)
        if at >= 0:
            found.append((at, key(c)))
    masked = "".join(masked)
    # Each time the subject is said, by its longest spelling there: "टाइगर" in "टाइगर श्रॉफ के बॉडीगार्ड" is the owner too.
    said = [(a, _end(masked, a, len(w.split()))) for w in subject_spellings if w for a in visuals._finds(masked, w)]
    said = [(a, z) for a, z in said if not any(b <= a and z <= y and (b, y) != (a, z) for b, y in said)]
    full = max((w for w in subject_spellings if w), key=lambda w: len(w.split()), default="")
    own = {hindi.norm(w) for w in [full, *full.split()]}

    def titled(a: int, z: int) -> bool:  # a title another name follows, "X के" qualifies, or a foreign or past one
        if hindi.norm(say[a:z]) in own:
            return False
        q = re.search(r"(\S+)\s+(?:के|की|का)\s+$", say[:a])
        before = re.findall(rf"[{_DEV}]+", say[:a])[-1:]
        # A state's or a town's ("कर्नाटक गृह मंत्री", review round 2: Amit Shah under a state minister's resignation).
        head = hindi.norm(say[:a].rstrip())
        local = any(w and head.endswith(hindi.norm(w)) for w in [*places, *visuals.FORCE_PLACES])
        return any(z < b <= z + 2 for b, _ in people) or bool(q) and q.group(1) not in ("देश", "भारत") \
            or bool(before) and (before[0] in ("पूर्व", "तत्कालीन") or things._foreign(before[0])) or local

    at = [a for a, z in said if not (_KIN.match(say[z:]) or harm and _OWNED.match(say[z:])) and not titled(a, z)]
    if at:
        found.append((min(at), SUBJECT))
    if not other:
        hits = [m.start() for m in re.finditer("पुलिस", say)] + [a for a in [says(say, visuals.ACCUSED)] if a >= 0]
        if hits:
            found.append((min(hits), POLICE))
    first: dict[str, int] = {}
    for a, k in sorted(found):
        first.setdefault(k, a)
    return sorted(((a, k) for k, a in first.items()), key=lambda x: x[0])


def chip_window(at: float, view_end: float) -> tuple[float, float] | None:
    """When a chip that comes up at `at` over a view ending at view_end is on screen, or None (under CHIP_MIN)."""
    until = min(at + CHIP_HOLD, view_end)
    return (at, until) if until - at >= CHIP_MIN else None


def _police_said(text: str, cast: list[dict], others=()) -> str | None:
    """Which police a card or hook line names: POLICE (the cast's force, or any when the cast has none, so it is
    never on screen), OTHER_POLICE (another force), or None."""
    if not any(w in text for w in visuals.POLICE):
        return None
    police = next((c for c in cast if c.get("kind") == "police"), None)
    places = [w for c in cast if c.get("kind") == "place" for w in _spelt(c)] + [o["hi"] for o in others]
    return OTHER_POLICE if police is not None and visuals.other_force(text, police, places) else POLICE


def card_keys(big: str, small: str, cast: list[dict], spellings=(), others=()) -> set[str]:
    """What a card says "this is X" about: everything its big line names, and its small line when that is only a
    name (the strap "जामनगर", "मुंबई पुलिस"); a small phrase ("मुम्बई में बैठक") is a caption, not a label. Any name
    the script lists counts, in the cast or not ("संजय राउत" over Tiger Shroff, 2026-10-22 review). The police count
    only when the line says पुलिस (an accused word says what they did: "3 आरोपी गिरफ्तार"), and another force is
    never what is on screen. A title alone ("प्रधानमंत्री") labels whoever is shown, not the subject."""
    extra = others_of(others, cast, spellings)
    out = {x for _, x in names(big, cast, spellings, others) if x != POLICE}
    out |= {p} if (p := _police_said(big, cast, extra)) else set()
    if small:
        out |= {key(c) for c in cast + extra if c.get("kind") != "police" and hindi.norm(small) in
                {hindi.norm(w) for w in _spelt(c)}}
        full = max((w for w in spellings if w), key=lambda w: len(w.split()), default="")
        out |= {SUBJECT} if full and hindi.norm(small) in {hindi.norm(w) for w in [full, *full.split()]} else set()
        if re.fullmatch(r"(?:\S+\s+)?पुलिस", small.strip()):
            out.add(_police_said(small, cast, extra))
    return out


def card_on(shown: list[int], photos: list[dict], cast: list[dict]) -> set[str]:
    """What a card over these pictures may name: what they depict, and the police over their own city's picture
    ("मुंबई पुलिस" over Mumbai's map: where the force is; never over a route or another place)."""
    on = set().union(set(), *(depicts(i, photos[i], cast) for i in shown if i < len(photos)))
    police = next((c for c in cast if c.get("kind") == "police"), None)
    return on | ({POLICE} if police and police.get("hi") and hindi.norm(police["hi"]) in on else set())


def hook_problems(hook: str, on: set[str], cast: list[dict], spellings=(), others=(), death: bool = False,
                  named: bool = True, own: str = "") -> list[str]:
    """What is wrong with a hook card over pictures depicting `on` (the views up in its HOOK_HOLD seconds): a name
    it says or quotes that no picture on screen is of ("शिंदे: गोली का जवाब गोली से" over Tiger Shroff, 39546660530),
    or a line that someone was hurt over the subject when it does not say the subject was ("ड्राइवर और एक फैन को
    लगी गोली" over Tiger, 39553699482; 2026-10-22 review round 2). A death Short's death is its subject's. named:
    False for beat 1's own card standing in as the hook, whose names the card check already reads; own: a place
    story's own name, which is its SUBJECT."""
    speaker, body = (hook.split(":", 1) if ":" in hook else ("", hook))
    speaker = speaker.strip()
    keys = {SUBJECT if x == own else x for x in card_keys(body, "", cast, spellings, others)}
    out = []
    if speaker and named:
        full = max((w for w in spellings if w), key=lambda w: len(w.split()), default="")
        rows = [c for c in cast + others_of(others, cast, spellings) if c.get("kind") != "police"]
        who = SUBJECT if full and hindi.contains(full, speaker) else \
            next((key(c) for c in rows if any(hindi.contains(w, speaker) for w in _spelt(c))), None)
        if who not in on:
            out.append(f"pictures: the hook quotes {speaker} over a picture of someone else")
        if who:
            keys.add(who)
    for x in sorted(keys - on) if named else ():
        out.append(f"pictures: the hook names {'another police force' if x == OTHER_POLICE else x} over a picture "
                   f"of something else")
    if not death and says(body, HURT) >= 0 and SUBJECT in on and SUBJECT not in keys:
        out.append("pictures: the hook says someone was hurt over the subject's photo")
    return out


def opening(short, views: list[dict] | None = None) -> list[str]:
    """hook_problems for what compose.render_full shows as the hook (the story's hook line, else beat 1's card when it
    comes up over picture 1) over the pictures up in its HOOK_HOLD seconds: render.json's views, else beat 1's. A
    text card's backdrop is no picture. writer._short drops a hook line this refuses."""
    photos, sc = short.scene.get("photos") or [], short.scene
    first = short.beats[0] if short.beats else None
    if first is None or not first.shot.startswith("photo:") or first.plate == CARD:
        return []
    cast, spell, hook = cast_of(short), spellings_of(short), sc.get("hook") or ""
    start = shot_photos(first.shot)
    opens = bool(start) and start[min(first.card_view, len(start) - 1)] == start[0]
    if not (hook or opens and (first.card or {}).get("big")):
        return []
    if views:
        up = {v["photo"] for v in views if v.get("plate") != CARD and v["start"] < HOOK_HOLD}
    else:
        up = set(start)
    own = hindi.norm(sc.get("name_hi") or "")
    on = {SUBJECT if x == own else x for x in card_on(sorted(up), photos, cast)}
    return hook_problems(hook or first.card["big"], on, cast, spell, sc.get("names"), short.kind == "death",
                         named=bool(hook), own=own)


def word_at(say: str, at: int) -> str:
    """The word of say starting at `at`, without punctuation: what compose cuts on."""
    w = (say[at:].split() or [""])[0]
    return w.strip(PUNCT)


def continues(say: str, prev: str | None, prev_held: bool, held: int, person: bool) -> bool:
    """The strict continuity rule (4.0): a person's Short, a leading pronoun, the previous main picture the subject,
    not after another such beat, at most CONTINUITY, and no harm, accused or unnamed actor in the line."""
    return person and prev == SUBJECT and not prev_held and held < CONTINUITY and bool(LEAD.match(say.strip())) \
        and says(say, HARM + UNNAMED + visuals.ACCUSED) < 0


def _card_text(beat: dict) -> tuple[str, str]:
    card = beat.get("card") or {}
    return card.get("big") or beat.get("caption") or "", card.get("small") or beat.get("label") or ""


def plan(beats: list[dict], photos: list[dict], cast: list[dict], subject: list[int], kind: str = "",
         spellings=(), person: bool = True, others=()) -> list[dict]:
    """Per beat {views, cut_word, cut_at, plate, card_view}. beats: [{"say", "card"|"caption"/"label"}]; photos: every
    picture (a photo stamped "vet" with a reason is never shown); cast: visuals.direct's cast, with "route" and
    "police" rows; subject: the story's own photos, ranked (only those that depict the SUBJECT are shown as them);
    spellings: how the script names the subject; others: the script's names (others_of).

    The main view is the picture of the first key the beat names, the cut the picture of a later different key on
    its word (cut_at: where in say, for compose.cut_time); one key, no cut; no key, a card over the last anchored
    picture that is not a map (beat 1 opens on the subject, and a person's explainer may hold the subject on the
    strict pronoun rule). A place shows its own photo (a landmark, its sight) before any map. A map (a route is one)
    is rare: at most MAX_MAP_VIEWS a Short, only as the whole of a beat that names nothing but places with no photo
    of their own, never as a cut and never as a card's backdrop; a beat that names a person or thing shows their
    photo, else a card, never a map (CAPraPdXvns put New Delhi's map under "रेहान ने तिरंगे की तस्वीरें ..."). A city
    named next to its spot gives way to the spot, and two places with a route map may show the route. The gate's
    ceilings hold by construction: no picture goes under a HELD_RUN-th beat in a row or over half the beats (the
    next picture of the key, else the next key, else a card: the chase Shorts' one police photo stood under 3 of 5
    beats), and a map beat that would put maps over MAP_SHARE of the picture time becomes a card."""
    depict = {i: depicts(i, p, cast) for i, p in enumerate(photos)}
    up = inside(photos, cast)
    groups = group(photos, cast)
    ok = [i for i, p in enumerate(photos) if not p.get("vet")]
    pools = {SUBJECT: [i for i in subject if i in ok and SUBJECT in depict[i]]}
    for i in ok:
        if len(depict[i]) == 1 and i not in subject:
            pools.setdefault(next(iter(depict[i])), []).append(i)
    routes = {frozenset(depict[i]): i for i in ok if len(depict[i]) == 2}
    person = person and kind in ("", "explainer")
    used, counts, runs = Counter(), Counter(), {}
    kind_of = {key(c): c.get("kind") for c in cast if c.get("kind") in MEMBERS}
    letters = sum(max(len(b.get("say") or b.get("text") or ""), 1) for b in beats) or 1
    maps_left = [MAX_MAP_VIEWS]

    def free(i: int, taken: set) -> bool:
        h = held_key(i, photos, groups)
        return h in taken or runs.get(h, 0) + 1 < HELD_RUN and not (len(beats) >= 5 and (counts[h] + 1) * 2 >
                                                                     len(beats))

    def rank(i: int, among: list[int]):  # a look not on screen in the last beat, the least used, then as ranked
        h = held_key(i, photos, groups)
        return h in {held_key(j, photos, groups) for j in prev}, used[h], among.index(i)

    out, prev, last, backdrop, prev_key, prev_held, held = [], [], None, None, None, False, 0
    for k, b in enumerate(beats):
        say = b.get("say") or b.get("text") or ""
        found = names(say, cast, spellings, others)
        found = [(a, x) for a, x in found if not any(up.get(y) == x for _, y in found)]
        if person and k > 0 and speaker(say, found, prev_key):
            found = [(0, SUBJECT), *found]
        text = " ".join(_card_text(b))
        on_card = {x for _, x in names(text, cast, spellings, others)} if text.strip() else set()
        big = {x for _, x in names(_card_text(b)[0], cast, spellings, others)}
        picks: list[tuple[int, str, int]] = []
        skip: set[str] = set()
        # Where it happened is the beat's whole point: it names places and nothing else (no person, thing, subject,
        # police or other name), and its share of the voice leaves the maps under MAP_SHARE.
        where = bool(found) and all(kind_of.get(x) == "place" for _, x in found) \
            and max(len(say), 1) / letters <= MAP_SHARE

        def choose(n: int, a: int, x: str, mapped: bool = True) -> None:
            route = next((routes[frozenset((x, y))] for _, y in found[n + 1:] if frozenset((x, y)) in routes), None)
            taken = {p for p, _, _ in picks}
            keys = {held_key(p, photos, groups) for p in taken}
            real = [i for i in pools.get(x) or [] if not visuals.is_map(photos[i]) and i not in taken
                    and free(i, keys)]
            cands = real
            if not real and not picks and mapped and where and maps_left[0] > 0:
                maps = [route] if route is not None else pools.get(x) or []
                cands = [i for i in maps if i not in taken and free(i, keys)]
            else:
                route = None
            if cands:
                picks.append((min(cands, key=lambda i: rank(i, cands)), x, a))
                skip.update(depict[route] if route is not None else ())

        # Places alone beside it ("दोनों नेताओं ने नई दिल्ली के हैदराबाद हाउस में बैठक की") leave it about the pair, and
        # so does one of the pair named with "दोनों" later in the line (cut to the other on "दोनों").
        both = pair_at(say) if k > 0 else -1
        pair = (_pair(out[-1], photos, depict, kind_of) or _recent_pair(out, photos, depict, kind_of)) \
            if both >= 0 else []
        if len(pair) == 2 and all(kind_of.get(x) == "place" or x in pair for _, x in found):
            order, at = _pair_order(say, found, pair, both)
            for n, x in enumerate(order):
                real = [i for i in pools.get(x) or [] if not visuals.is_map(photos[i]) and free(i, set())]
                if real:
                    picks.append((min(real, key=lambda i: rank(i, real)), x, at if n else 0))
            if len(picks) < 2:
                picks = []
        rest = list(enumerate(found))
        # The main view: the first key said that has a real photo; only when none has one, a map. Dry run 39789422139
        # b2 "नई दिल्ली में ... यमुना प्रोजेक्ट": New Delhi's map, cut to a card by the map ceiling, hid the Yamuna's photo.
        if picks:
            rest = []
        first = None if picks else next((r for r in rest if (choose(r[0], *r[1], mapped=False), picks)[1]), None)
        if first is not None:
            rest.remove(first)
        while rest and not picks:
            n, (a, x) = rest.pop(0)
            choose(n, a, x)
        # Three names, two views: of those said after the main view's, the one the card names takes the cut
        # (39411111185 b1, "मार्को रुबियो से मुलाकात" under subject, Mumbai, Rubio), so the card sits over its own
        # picture; a key said before the main view's never cuts in after it.
        rest.sort(key=lambda r: (r[1][1] not in big, r[1][1] not in on_card))
        for n, (a, x) in rest:
            if len(picks) == 2 or visuals.is_map(photos[picks[0][0]]):
                break  # a map is the whole of its beat
            if x not in skip and x != picks[0][1]:
                choose(n, a, x)
        row = {"views": [], "cut_word": "", "cut_at": -1, "plate": "", "card_view": 0}
        this_held = False
        # Never under a beat that names someone or something else with no usable picture: "उनके पिता जैकी श्रॉफ ने
        # कहा" with Jackie's photo vetted out is a card, not Tiger (39508637683, 2026-10-22 review round 2).
        if not picks and (k == 0 or not found and continues(say, prev_key, prev_held, held, person)):
            pool = [i for i in pools[SUBJECT] if free(i, set())]
            if pool:
                this_held = k > 0
                picks = [(min(pool, key=lambda i: rank(i, pool)), SUBJECT, 0)]
        if picks:
            row["views"] = [p for p, _, _ in picks]
            if len(picks) > 1:
                row["cut_word"], row["cut_at"] = word_at(say, picks[1][2]), picks[1][2]
            row["card_view"] = next((j for j, i in enumerate(row["views"]) if depict[i] & on_card), 0)
            last, prev_key = row["views"][-1], picks[0][1]
            backdrop = next((i for i in reversed(row["views"]) if not visuals.is_map(photos[i])), backdrop)
            maps_left[0] -= sum(visuals.is_map(photos[i]) for i in row["views"])
        else:
            # A card's backdrop is of something the beat or its card names (shown is said: dry run 39794659993 put
            # Rahul Gandhi's blurred face behind "गृह मंत्री ने यमुना सफाई ..."); else compose draws it plain
            # (card_plain), whatever picture the shot keeps.
            fits = {x for _, x in found} | on_card | ({SUBJECT} if person and prev_key == SUBJECT and LEAD.match(say.strip()) else set())
            mine = [i for x in fits for i in pools.get(x) or [] if not visuals.is_map(photos[i])]
            row["plate"] = CARD
            row["views"] = [min(mine, key=lambda i: rank(i, mine))] if mine else \
                _backdrop(backdrop, last, pools[SUBJECT], photos, ok)
            prev_key = None
        held += this_held
        prev_held = this_held
        shown = {held_key(i, photos, groups) for i in row["views"]} if row["plate"] != CARD else set()
        runs = {h: runs.get(h, 0) + 1 for h in shown}
        counts.update(shown)
        for i in row["views"] if row["plate"] != CARD else ():
            used[held_key(i, photos, groups)] += 1
        prev = row["views"] if row["plate"] != CARD else prev
        out.append(row)
    return _map_cuts(out, photos, [b.get("say") or b.get("text") or "" for b in beats], subject=pools[SUBJECT],
                     ok=ok)


def _pair(row: dict, photos: list[dict], depict: dict, kind_of: dict) -> list[str]:
    """The two people a beat's views showed (the subject counts as one), in order, else []."""
    if row["plate"] == CARD or len(row["views"]) != 2 or any(visuals.is_map(photos[i]) for i in row["views"]):
        return []
    keys = [next(iter(depict[i])) if len(depict[i]) == 1 else None for i in row["views"]]
    ok = all(x is not None and (x == SUBJECT or kind_of.get(x) == "person") for x in keys)
    return keys if ok and keys[0] != keys[1] else []


def _one(row: dict, photos: list[dict], depict: dict, kind_of: dict) -> str | None:
    """The one person a beat's single real photo showed (the subject counts), else None."""
    if row["plate"] == CARD or len(row["views"]) != 1 or visuals.is_map(photos[row["views"][0]]):
        return None
    d = depict[row["views"][0]]
    x = next(iter(d)) if len(d) == 1 else None
    return x if x is not None and (x == SUBJECT or kind_of.get(x) == "person") else None


def _recent_pair(out: list[dict], photos: list[dict], depict: dict, kind_of: dict) -> list[str]:
    """"दोनों" after two beats that each showed one of two people ("तुस्क नई दिल्ली में मिले।", "मोदी ने ... चर्चा
    की।", "दोनों नेताओं ने ..."): those two, in the order shown (dry run 39860680187 put a card there)."""
    if len(out) < 2:
        return []
    keys = [_one(r, photos, depict, kind_of) for r in out[-2:]]
    return keys if None not in keys and keys[0] != keys[1] else []


def _pair_order(say: str, found: list[tuple[int, str]], pair: list[str], both: int) -> tuple[list[str], int]:
    """(the pair in screen order, where in say the cut is): one of them named first ("मोदी ने ... दोनों नेताओं"), then
    the other on "दोनों"; both named, in the order said; neither, as the last beat showed them, cut mid-line."""
    said = [(a, x) for a, x in found if x in pair]
    if len({x for _, x in said}) == 2:
        (a0, x0), (a1, x1) = said[0], next(r for r in said if r[1] != said[0][1])
        return [x0, x1], a1
    if said and both > said[0][0]:
        x0 = said[0][1]
        return [x0, next(x for x in pair if x != x0)], both
    return list(pair), _second_word(say)


def speaker(say: str, found: list[tuple[int, str]], prev: str | None) -> bool:
    """A leading pronoun that says what the subject said (SPOKE): no one is named before the "कि", and the one the
    last beat showed is the subject or is named after the "कि" (they are what is claimed about, not who claims)."""
    m = SPOKE.search(say)
    if not LEAD.match(say.strip()) or not m or says(say, HARM) >= 0 or any(a < m.start() for a, _ in found):
        return False
    return prev == SUBJECT or prev is not None and any(x == prev for a, x in found if a > m.start())


def _second_word(say: str) -> int:
    """Where say's word after the middle starts: the cut of a beat about a pair (no name to cut on)."""
    starts = [m.start() for m in re.finditer(r"\S+", say)]
    later = [a for a in starts if a >= len(say) // 2]
    return later[0] if later else starts[-1]


def _backdrop(backdrop, last, subject: list[int], photos: list[dict], ok: list[int]) -> list[int]:
    """A text card's backdrop: the last picture shown that is not a map, else the subject's, else any photo that is
    not a map; a map only when there is nothing else (a blurred map under a card is one more map on screen)."""
    for i in [backdrop, *subject[:1], *(j for j in ok if not visuals.is_map(photos[j]))]:
        if i is not None and not visuals.is_map(photos[i]):
            return [i]
    return [last] if last is not None else subject[:1]


def _map_cuts(rows: list[dict], photos: list[dict], says_: list[str] = (), subject=(), ok=()) -> list[dict]:
    """The map ceilings, by problems' per-beat weights or by the time the voice will give them (a beat's length in
    letters, a cut from its cut_at on; a card's time counted in neither): map cuts go first (latest first: the
    hand-fixed Rubio cut to the Jamnagar map in beats 1 and 2; 39411041538 cut to Juhu's map on its fourth word),
    then a beat whose only view is a map becomes a card, latest first, while there are more than MAX_MAP_VIEWS map
    views or maps fill over MAP_SHARE of the picture time."""
    pics = [(r, max(len(says_[k]), 1) if k < len(says_) else 1) for k, r in enumerate(rows)
            if r["plate"] != CARD and r["views"]]

    def maps(r: dict, n: int, timed: bool) -> float:
        v = r["views"]
        if len(v) == 1 or not timed or r.get("cut_at", -1) < 0:
            return sum(visuals.is_map(photos[i]) for i in v) / len(v)
        f = min(r["cut_at"] / n, 1.0)
        return visuals.is_map(photos[v[0]]) * f + visuals.is_map(photos[v[1]]) * (1 - f)

    def share() -> float:
        if not pics:
            return 0.0
        beat = sum(maps(r, n, False) for r, n in pics) / len(pics)
        return max(beat, sum(maps(r, n, True) * n for r, n in pics) / sum(n for _, n in pics))

    seen, cuts = set(), []
    for n, (r, _) in enumerate(pics):
        v = r["views"]
        if len(v) == 2 and visuals.is_map(photos[v[1]]) and not visuals.is_map(photos[v[0]]):
            cuts.append((v[1] not in seen, -n, r))
        seen.update(v)
    for _, _, r in sorted(cuts, key=lambda c: c[:2]):
        if share() <= MAP_SHARE:
            break
        r.update(views=r["views"][:1], cut_word="", cut_at=-1, card_view=0)

    def views() -> int:
        return sum(visuals.is_map(photos[i]) for r, _ in pics for i in r["views"])

    for k in range(len(pics) - 1, -1, -1):
        if share() <= MAP_SHARE and views() <= MAX_MAP_VIEWS:
            break
        r = pics[k][0]
        if all(visuals.is_map(photos[i]) for i in r["views"]):
            back = next((i for q, _ in pics[:k][::-1] for i in q["views"][::-1] if not visuals.is_map(photos[i])),
                        None)
            r.update(plate=CARD, views=_backdrop(back, r["views"][0], list(subject), photos, list(ok)), cut_word="",
                     cut_at=-1, card_view=0)
            pics.pop(k)
    return rows


# --- The shared gate ----------------------------------------------------------------------------------------------

def cast_of(short) -> list[dict]:
    """The short's cast (scene.cast), with any police photo as a police row; for artifacts saved without a cast,
    one is read off the photos' on-screen names, each person with their unshared surname (visuals.surnames)."""
    sc, photos = short.scene, short.scene.get("photos") or []
    cast = [dict(c) for c in sc.get("cast") or []]
    if sc.get("cast") is None:
        seen: dict[str, dict] = {}
        for i, p in enumerate(photos):
            role = p.get("role")
            if role in MEMBERS:
                names_ = [p.get("who")] if p.get("who") else []
            elif role == "map":
                names_ = _map_names(p, [])
                role = "place"
            else:
                continue
            for n in names_:
                c = seen.setdefault(hindi.norm(n), {"hi": n, "kind": role, "photos": []})
                c["photos"].append(i)
        cast = list(seen.values())
        visuals.surnames(cast, sc.get("name_hi") or "")
    # The script's English name for a member saved without one: vet_photo's not-itself check needs it ("Andheri
    # flyover" under "अंधेरी वेस्ट" passed the replay for want of it).
    by_hi = {hindi.norm(n.get("hi") or ""): n["en"] for n in sc.get("names") or [] if n.get("en") and n.get("hi")}
    by_en = {n["en"].lower(): n["en"] for n in sc.get("names") or [] if n.get("en")}
    for c in cast:
        if not c.get("en") and (en := by_hi.get(hindi.norm(c.get("hi") or "")) or by_en.get((c.get("hi") or "").lower())):
            c["en"] = en
    police = [i for i, p in enumerate(photos) if p.get("role") == "police"]
    if police and not any(c.get("kind") == "police" for c in cast):
        cast.append({"kind": "police", "hi": photos[police[0]].get("who") or "", "photos": police})
    return cast


def spellings_of(short) -> list[str]:
    """How the narration names the story's subject: the full Hindi name, its first and last words, and a title the
    script puts before it twice ("प्रधानमंत्री", visuals.titles)."""
    name = (short.scene.get("name_hi") or "").strip()
    words = name.split()
    beats = [{"say": b.text} for b in short.beats]
    return [w for w in dict.fromkeys([name, *words[:1], *words[-1:], *visuals.titles(beats, name)])
            if len(hindi.norm(w)) >= 3]


def story_year(short) -> int:
    m = re.search(r"-(20\d\d)\d{4}(?:-|$)", short.id) or re.match(r"(20\d\d)", short.event_time or "")
    return int(m.group(1)) if m else 2026


def _person(short) -> bool:
    # Shorts saved before scene.subject_person existed (the Jaishankar ones) carry None: a person unless stated.
    return short.scene.get("subject_person") is not False


def _incident(short) -> bool:
    return short.kind in ("incident", "protest", "death") or bool(short.loss or short.scene.get("case"))


def vet(i: int, photos: list[dict], short, cast: list[dict]) -> str:
    """Why photo i of a saved short may not be on screen whatever the beat says, or "" (vet_photo)."""
    return vet_photo(i, photos, cast, story_year(short), _person(short), _incident(short), short.scene.get("born"))


# A subject's photo whose file names a second person beside them ("Donald Tusk and Jonas Gahr Støre at the Polish
# KPRM", dry run 39827809002): a face the voice never names, under "दोनों नेताओं" (Tusk and Modi) worst of all. Also
# "A, B" and "A & B" (two names, not a name and a title: "Narendra Modi, Prime Minister of India" is one person).
_NAME = r"[A-Z][a-zà-ÿ]+(?:\s+(?:[A-Z][\w-]+|de|der|den|van|von|al|bin|la|le|du|da|di))*\s+[A-Z][\w-]+"
_TITLE = r"(?:Prime|President|Minister|Chief|Vice|Deputy|Governor|Chancellor|Secretary|Speaker|Leader|Member|Union|"\
    r"Home|Foreign|Finance|Defence|Defense|Ambassador|Former|Official|Portrait|India|Indian|Delhi|New|Government|Office)"
WITH_OTHER = re.compile(r"\b(?:and|with|meets?|meeting|greets?|greeting)\s+(?:(?:Prime Minister|President|PM|Mr|Mrs|"
                        r"Ms|Dr|Shri|Smt)\.?\s+)?[A-Z][a-zà-ÿ]+(?:\s+(?:[A-Z][\w-]+|de|van|von|al|bin))*\s+[A-Z][\w-]+"
                        rf"|\b[A-Z][a-zà-ÿ]+\s+[A-Z][\w-]+\s*(?:,|&)\s*(?!{_TITLE}\b){_NAME}")
# A photo from somewhere else than the story: a summit's stage, a foreign government's lectern ("Government of
# Sweden" behind Tusk at the 2024 NB8 summit, dry run 39833792083 b2, for a meeting in New Delhi). Soft: only while
# cleaner portraits remain.
ELSEWHERE = re.compile(r"\b(?:summit|conference|NB8|G7|G-7|G20|G-20|BRICS|ASEAN|plenary|state visit|"
                       r"Government of [A-Z]\w+|Oval Office|White House)\b", re.I)  # not "Congress" (an official US portrait) or "Forum"
SOFT_FLOOR = 2  # clean photos of the person that must remain for a soft reason to vet one out
# A place's photo of people at it, not of it (review round 2, dry run 39871573344: "File:Delhi HC.jpg" is "Nancy Erbe
# giving lecture to 300+ Judges ... of Delhi High Court", a foreign woman at a podium under "दिल्ली हाई कोर्ट ने ...",
# four times): its words say someone speaks, is honoured or meets there, or a category is a person's initialled
# name. Its face is too small for writer.featured_face. A card is better than someone else's face.
PEOPLE_AT = re.compile(r"\b(?:lectures?|lecturing|speech|speaking|speaks|addressing|addresses|giving (?:a )?talk|"
                       r"seminar|conference|ceremony|felicitat\w*|inaugurat\w*|press meet|meeting|selfie|posing|"
                       r"poses|portrait|delegation|interview|rally|protest(?:ers|ors)?|dharna)\b", re.I)
INITIALLED = re.compile(r"[A-Z][a-z]+\s+(?:[A-Z]\.\s*)+[A-Z][a-z]+")


def known_people(cast: list[dict]) -> list[str]:
    """The English names of every person the story may name: its cast's people and things.FIGURES."""
    return list(dict.fromkeys([c["en"] for c in cast if c.get("kind") == "person" and c.get("en")]
                              + [en for en, _ in things.FIGURES]))


def _named_in(p: dict, people: list[str]) -> set[str]:
    """The known people a photo's file name or description names, by full name or by a surname no other has."""
    return set(_named(" ".join(str(p.get(k) or "") for k in ("file", "description")), tuple(people)))


@functools.lru_cache(maxsize=4096)
def _named(about: str, people: tuple[str, ...]) -> tuple[str, ...]:
    text = re.sub(r"^File:|\.\w+$|_", " ", about)
    last = Counter(n.split()[-1] for n in people)
    return tuple(n for n in people if re.search(rf"\b{re.escape(n)}\b", text) or last[n.split()[-1]] == 1
                 and len(n.split()[-1]) >= 4 and re.search(rf"\b{re.escape(n.split()[-1])}\b", text))


def _with_someone(p: dict, pool: list[dict], people: list[str], own: str = "", role: str = "") -> tuple[str, bool]:
    """(why the photo shows someone beside its person, hard): hard when it names a known person who is not its own
    (own: the cast row's name; for the story's own photos, the name most of them carry); soft for a generic second
    name (WITH_OTHER) or a summit or foreign stage (ELSEWHERE)."""
    named = _named_in(p, people)
    if not own:  # the name over half the story's own photos carry is theirs
        seen = Counter(n for q in pool for n in _named_in(q, people))
        own = next((n for n, c in seen.most_common(1) if c * 2 > len(pool)), "")
    others = sorted(named - {own})
    if others and (own or len(named) > 1):
        return f"a photo with someone else ({others[0]})", True
    text = re.sub(r"^File:|\.\w+$|_", " ", p.get("file") or "")
    if m := WITH_OTHER.search(text):
        return f"a photo with someone else ({m.group(0)[:40]})", False
    # The story's own photos (they open it), by file name: categories ("World Economic Forum ...") tag portraits too.
    if not role and (m := ELSEWHERE.search(text)):
        return f"a photo from somewhere else ({m.group(0)[:40]})", False
    return "", False


def vet_photo(i: int, photos: list[dict], cast: list[dict], year: int, person: bool, incident: bool,
              born: int | None = None) -> str:
    """Why photo i may not be on screen whatever the beat says, or "": the wrong time of life (media.era_reject),
    another event (for a cast person, or any photo in an incident story), someone else beside its person (hard when a
    known person, soft for a generic name or a summit stage, and never a person's last clean photos: SOFT_FLOOR), or
    a landmark that is not its place. visuals.direct stamps it before planning and the gate reads the same reasons
    off the saved photos."""
    p = photos[i]
    role = p.get("role")
    if role in ("map", "topic", "thing"):
        return ""
    if not role or role == "person":
        if role:
            pool = [q for q in photos if q.get("role") == "person" and q.get("who") == p.get("who")]
            own = next((c.get("en") or "" for c in cast if c.get("kind") == "person" and c.get("en")
                        and i in (c.get("photos") or [])), "")
            why, event = media.era_reject(p, year, None, "person", pool), media.event_kind(p)
        else:
            pool, own = [q for q in photos if not q.get("role")], ""
            why = media.era_reject(p, year, born, "person" if person else "place", pool)
            event = media.event_kind(p) if incident else ""
        if not why and (person or role):
            people = known_people(cast)
            other, hard = _with_someone(p, pool, people, own, role)
            if other:
                clean = sum(1 for q in pool if q is not p and not _with_someone(q, pool, people, own, role)[0])
                if clean >= (1 if hard else SOFT_FLOOR):
                    why = other
    else:
        why, event = media.era_reject(p, year, None, "place"), ""
        own = next((c.get("en") for c in cast if c.get("en") and key(c) in depicts(i, p, cast)), "")
        if role == "place" and own and media.not_itself(p, own):
            why = f"a landmark at {own}, not {own} itself"
        if role == "place" and not why:
            why = _people_at(p, cast)
            event = media.event_kind(p)
    return why or (f"a photo from another event ({event})" if event else "")


def _people_at(p: dict, cast: list[dict]) -> str:
    """Why a place's photo shows people at it rather than the place (PEOPLE_AT, a known person, an initialled
    person's category), or ""."""
    if named := sorted(_named_in(p, known_people(cast))):
        return f"a photo of {named[0]}, not of the place"
    text = re.sub(r"^File:|\.\w+$|_", " ", " ".join(str(p.get(k) or "") for k in ("file", "description")))
    if m := PEOPLE_AT.search(text):
        return f"people at the place, not the place ({m.group(0)})"
    cats = [c.strip() for c in str(p.get("categories") or "").split("|")]
    if who := next((c for c in cats if INITIALLED.fullmatch(c)), ""):
        return f"a photo of {who}, not of the place"
    return ""


def _label(i: int, photos: list[dict]) -> str:
    p = photos[i] if i < len(photos) else {}
    return f"photo {i} ({p.get('who') or (p.get('file') or '')[:50]})"


def problems(short, views: list[dict] | None = None) -> list[str]:
    """What the screen shows that the voice does not say ("shown is said"), for a short as saved; views: render.json's
    [{start, end, photo, beat_k, plate}] when the render is done, for the time shares. Strings start "pictures:" or
    "text cards:" (cli.RETRYABLE)."""
    photos, sc = short.scene.get("photos") or [], short.scene
    cast, spell = cast_of(short), spellings_of(short)
    others = others_of(sc.get("names"), cast, spell)
    person = _person(short) and short.kind in ("", "explainer")
    groups = group(photos, cast)
    # A place's own Short (Jantar Mantar) also has it in its cast: the two keys are one.
    own = hindi.norm(sc.get("name_hi") or "")

    def canon(keys: set[str]) -> set[str]:
        return {SUBJECT if x == own else x for x in keys}

    hook = sc.get("hook") or ""
    timed: dict[int, list[tuple[int, float]]] = {}
    # The opening flash (compose.burst, stamped "burst") after the beat's own views: it is shown and must be said,
    # but beat 1's lead picture is the view after it.
    for v in sorted(views or [], key=lambda v: bool(v.get("burst"))):
        if v.get("plate") != CARD:
            timed.setdefault(v["beat_k"], []).append((v["photo"], max(v["end"] - v["start"], 0.0)))
    beat_time = {}
    for v in views or []:
        beat_time[v["beat_k"]] = beat_time.get(v["beat_k"], 0.0) + max(v["end"] - v["start"], 0.0)
    out: list[str] = []
    total = map_time = real_time = card_time = subject_time = 0.0
    cards = run = held = 0
    pictures: list[int] = []
    prev_key, prev_held, ran, pair, alone = None, False, False, set(), []
    shown_beats = [(k, b) for k, b in enumerate(short.beats) if b.shot.startswith("photo:")]
    # What has a real photo (not a map, not vetted out): a beat naming it never stands over a map.
    pictured = {x for i, p in enumerate(photos) if not visuals.is_map(p) and not vet(i, photos, short, cast)
                for x in canon(depicts(i, p, cast)) if x != CONTEXT}
    kind_of = {SUBJECT: "person" if person else "place", **{key(c): c.get("kind") for c in cast}}
    map_views = _map_views(short, views)
    for k, b in shown_beats:
        say, n = b.text, k + 1
        if b.plate == CARD:
            card_time += beat_time.get(k, 0.0) if views else 1.0
            cards, run = cards + 1, run + 1  # a card's time is not picture time: cards never dilute the maps
            if run >= CARD_RUN and not ran:
                out.append(f"text cards: {run} beats in a row from beat {n - run + 1}")
                ran = True
            prev_key, prev_held, pair, alone = None, False, set(), []
            continue
        run = 0
        found = names(say, cast, spell, others)
        named = canon({x for _, x in found})
        # A leading pronoun that says what the subject said (plan's speaker).
        if person and k > 0 and speaker(say, found, prev_key):
            named.add(SUBJECT)
        # "दोनों" anywhere right after a beat that showed two people, or two beats that showed one each, the beat
        # naming no one else (plan's _pair / _recent_pair).
        if not pair and len(alone) == 2 and None not in alone and alone[0] != alone[1]:
            pair = set(alone)
        if k > 0 and len(pair) == 2 and pair_at(say) >= 0 and all(kind_of.get(x) == "place" or x in pair
                                                                    for x in named):
            named = named | pair
        these = []
        shown = shot_photos(b.shot)
        weights = timed.get(k) if views else [(i, 1.0 / len(shown)) for i in shown]
        this_held, main = False, None
        # The pronoun rule holds the subject for the whole beat: a cut to another of their photos stays about them.
        may_hold = k > 0 and not named and continues(say, prev_key, prev_held, held, person)
        flashed = sum(bool(v.get("burst")) for v in views or [] if v["beat_k"] == k)
        for j, (i, w) in enumerate(weights or []):
            if i >= len(photos):
                continue
            lead = j < len(weights) - flashed
            p, d = photos[i], canon(depicts(i, photos[i], cast))
            total += w
            map_time += w if visuals.is_map(p) else 0.0
            pictures.append(i)
            ok = bool(d & named)
            if not ok and SUBJECT in d and may_hold:
                ok = this_held = True
            ok = ok or (SUBJECT in d and k == 0)
            if not ok:
                out.append(f"pictures: beat {n} shows {_label(i, photos)}, which the beat does not name")
            why = vet(i, photos, short, cast)
            if why:
                out.append(f"pictures: beat {n} shows {_label(i, photos)}: {why}")
            real_time += w if ok and not why and not visuals.is_map(p) else 0.0
            subject_time += w if ok and not why and SUBJECT in d else 0.0
            if visuals.is_map(p):
                for x in sorted(x for x in named & pictured if kind_of.get(x) in ("person", "thing", "topic")
                                or x == SUBJECT):
                    out.append(f"pictures: beat {n} shows a map though it names {x}, who has a photo")
            if j == 0:
                main = SUBJECT if SUBJECT in d and ok else next(iter(d & named), None)
            if lead and len(d) == 1 and d <= named and not visuals.is_map(p) and (d <= {SUBJECT} or kind_of.get(
                    next(iter(d))) == "person"):
                these.append(next(iter(d)))
        pair = set(these) if len(these) == 2 and len(set(these)) == 2 else set()
        alone = [*alone, these[0] if len(set(shown)) == 1 and len(set(these)) == 1 else None][-2:]
        held += this_held
        prev_key, prev_held = main, this_held
        big, small = (b.card or {}).get("big", ""), (b.card or {}).get("small", "")
        # A police name too: "मुंबई पुलिस" over Tiger Shroff passed for any picture (39427875643 replan, 2026-10-22
        # review round 2). With render.json's views, the chip's own window (_chip_overrun).
        said = canon(card_keys(big, small, cast, spell, others))
        # A town with no photo of its own, only a map, on a chip is a dateline ("जामनगर में बैठक" over Rubio): the
        # beat may not cut to its map when it names a person (2026-10-22), so the chip stands over who is there.
        said -= {x for x in said if kind_of.get(x) == "place" and x not in pictured}
        pic = shown[min(b.card_view, len(shown) - 1)] if shown else None
        on = canon(card_on(shown, photos, cast))
        for x in sorted(said - on):
            out.append(f"pictures: card {n} names {'another police force' if x == OTHER_POLICE else x} over a "
                       f"picture of something else")
        if views and big and (k == 0 or big != (short.beats[k - 1].card or {}).get("big")
                              or short.beats[k - 1].plate == CARD):
            out += _chip_overrun(n, k, pic, views, photos, bool(hook) or k == 0)
    out += opening(short, views)
    if hook:
        narration = " ".join(b.text for b in short.beats)
        # "शिंदे: गोली का जवाब गोली से" over Tiger Shroff, and Shinde is never named (39546660530).
        voice = hook.split(":", 1)[0].strip() if ":" in hook else ""
        if voice and not hindi.quotes(voice, narration):
            out.append(f"pictures: the hook names {voice}, whom the narration never says")
        for who in dict.fromkeys(n.get("hi") for n in sc.get("names") or [] if n.get("hi")):
            if hindi.contains(hook, who) and not hindi.contains(narration, who) and not hindi.contains(voice, who):
                out.append(f"pictures: the hook names {who}, whom the narration never says")
    if total and map_time / total > MAP_SHARE:
        out.append(f"pictures: maps fill {map_time / total:.0%} of the picture time (at most {MAP_SHARE:.0%})")
    if views and (hold := longest_hold(views))[0] > HOLD_MAX:
        out.append(f"pictures: {_label(hold[1], photos)} stays up {hold[0]:.1f} s in a row from {hold[2]:.1f} s (at "
                   f"most {HOLD_MAX:.0f} s)")
    if map_views > MAX_MAP_VIEWS:
        out.append(f"pictures: {map_views} map views (at most {MAX_MAP_VIEWS})")
    if cards > card_limit(len(shown_beats)):
        out.append(f"text cards: {cards} of {len(shown_beats)} beats (at most {card_limit(len(shown_beats))})")
    if total + card_time and real_time / (total + card_time) < REAL_SHARE:
        out.append(f"pictures: real photos fill only {real_time / (total + card_time):.0%} of the Short (want at "
                   f"least {REAL_SHARE:.0%})")
    # The floor paired with the held ceilings: a person's Short is about them (dry run 39794659993, "Amit Shah",
    # showed Rahul Gandhi as long as Shah). Not for a Short that names no subject (a place's own, an incident).
    if person and pictured & {SUBJECT} and total + card_time and subject_time / (total + card_time) < SUBJECT_SHARE:
        out.append(f"pictures: the story's person fills only {subject_time / (total + card_time):.0%} of the Short "
                   f"(want at least {SUBJECT_SHARE:.0%})")
    want = min(sc.get("min_visuals", visuals.MIN_VISUALS), len(shown_beats) - cards)
    distinct, grouped = len(set(pictures)), len({groups.get(i, i) for i in pictures})
    if distinct >= want > grouped:
        out.append(f"pictures: only {grouped} different pictures once a place's maps count as one (want {want})")
    return out


def card_limit(beats: int) -> int:
    """The most text cards a Short of this many beats may have: a third, and one in any Short."""
    return max(1, beats // 3)


def _map_views(short, views: list[dict] | None = None) -> int:
    """How many times a map comes on screen: render.json's views (one map held across a cut counts once), else one
    per map in each picture beat's shot. A card's backdrop is not counted (plan never puts a map there)."""
    photos = short.scene.get("photos") or []
    if views:
        seq = [v["photo"] for v in sorted(views, key=lambda v: v["start"]) if v.get("plate") != CARD
               and not v.get("outro")]
        return sum(1 for j, i in enumerate(seq) if i < len(photos) and visuals.is_map(photos[i])
                   and (j == 0 or seq[j - 1] != i))
    return sum(visuals.is_map(photos[i]) for b in short.beats if b.shot.startswith("photo:") and b.plate != CARD
               for i in shot_photos(b.shot) if i < len(photos))


def longest_hold(views: list[dict]) -> tuple[float, int, float]:
    """(seconds, photo, start) of the longest stretch one picture stays on screen in render.json's views: views of the
    same photo back to back are one (compose's closer cut keeps the photo); a text card, the outro and the opening
    flash are not a picture held."""
    best, cur = (0.0, -1, 0.0), None
    for v in sorted(views, key=lambda v: v["start"]):
        if v.get("plate") == CARD or v.get("outro") or v.get("burst"):
            cur = None
            continue
        if cur and cur[1] == v["photo"] and v["start"] - cur[3] < 0.05:
            cur = (cur[0] + v["end"] - v["start"], cur[1], cur[2], v["end"])
        else:
            cur = (v["end"] - v["start"], v["photo"], v["start"], v["end"])
        if cur[0] > best[0]:
            best = cur[:3]
    return best


def _chip_overrun(n: int, k: int, pic, views: list[dict], photos: list[dict], hooked: bool) -> list[str]:
    """A chip up over a picture it is not on: render.json's stamped window (compose.chip_spans), or for a render
    saved before chips were stamped, CHIP_HOLD from its picture's start (after the hook card on beat 1), over
    whatever came after the cut ("बेगूसराय" over Tiger Shroff at the airport, 39418354883)."""
    mine = [v for v in views if v["beat_k"] == k and v.get("plate") != CARD and not v.get("burst")]
    if any(v.get("chip") for v in views):
        spans = [tuple(v["chip"]) for v in mine if v.get("chip")]
    else:
        at = next((v["start"] for v in mine if v["photo"] == pic), None)
        spans = [] if at is None else [(max(at, HOOK_HOLD) if k == 0 and hooked else at, at + CHIP_HOLD)]
    for a, z in spans:
        for v in mine:
            if v["photo"] != pic and min(z, v["end"]) - max(a, v["start"]) > 0.2:
                return [f"pictures: card {n} stays up over {_label(v['photo'], photos)} after the cut"]
    return []


def card_plain(short, k: int) -> bool:
    """Whether beat k's text card goes on the plain background: plain() says so, or its backdrop is of nothing the
    beat or its card names (beat 1 or a leading pronoun count the subject). Dry run 39794659993 blurred Rahul
    Gandhi's face behind "गृह मंत्री ने यमुना सफाई ...", a line about Amit Shah: shown is said holds for a blur too."""
    b = short.beats[k]
    if plain(b.text, bool(short.loss)) or config.MATCHER == "legacy":  # the rollback: main's plain() alone
        return plain(b.text, bool(short.loss))
    photos, sc = short.scene.get("photos") or [], short.scene
    shown = [i for i in shot_photos(b.shot) if i < len(photos)] if b.shot.startswith("photo:") else []
    if not shown:
        return True
    cast, spell = cast_of(short), spellings_of(short)
    others = others_of(sc.get("names"), cast, spell)
    own = hindi.norm(sc.get("name_hi") or "")
    big, small = (b.card or {}).get("big", ""), (b.card or {}).get("small", "")
    fits = {x for _, x in names(b.text, cast, spell, others)} | card_keys(big, small, cast, spell, others)
    if k == 0 or _person(short) and LEAD.match(b.text.strip()):
        fits.add(SUBJECT)
    fits = {SUBJECT if x == own else x for x in fits}
    i = shown[0]
    return visuals.is_map(photos[i]) or bool(vet(i, photos, short, cast)) or \
        not {SUBJECT if x == own else x for x in depicts(i, photos[i], cast)} & fits


def plain(say: str, loss: bool = False) -> bool:
    """A card for this line goes on the plain channel background, not a blur of a face (4.0): "दो घायल / अस्पताल"
    sat over a blurred Tiger Shroff."""
    return loss or says(say, HARM + visuals.ACCUSED) >= 0
