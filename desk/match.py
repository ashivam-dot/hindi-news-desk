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

import re
from collections import Counter

from . import hindi, media, visuals
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
_DEV = "\u0900-\u097F"
_OWNED = re.compile(rf"\s+(?:के|की|का)\s+(?:एक\s+)?(?:{'|'.join(OWNED)})(?![{_DEV}])")
# Paired ceilings (4.0): cards at most half the beats and never CARD_RUN in a row; maps and routes at most MAP_SHARE
# of the picture time (Rubio: 67%), a text card's time not being picture time; no picture under HELD_RUN beats in a
# row or more than half the beats (gate.held, which plan keeps to).
CARD_RUN, MAP_SHARE, HELD_RUN = 3, 0.4, 3
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
    """What gate.held counts photo i as: a place's maps one picture (match.group), any other map its file, else i."""
    p = photos[i] if i < len(photos) else {}
    g = groups.get(i, "")
    return (g if g.startswith("place:") else p.get("file")) if visuals.is_map(p) else i


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
    members = [c for c in cast if c.get("kind") in ("person", "place", "topic")]
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
    members = [c for c in cast if c.get("kind") in ("person", "place", "topic")]
    extra = others_of(others, cast, subject_spellings)
    police = next((c for c in cast if c.get("kind") == "police"), None)
    places = [w for c in members if c.get("kind") == "place" for w in _spelt(c)] + [o["hi"] for o in extra]
    other = police is None or visuals.other_force(say, police, places)
    harm = says(say, HARM) >= 0

    def owned(at: int, words: int) -> bool:
        return harm and bool(_OWNED.match(say[_end(say, at, words):]))

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

    def titled(a: int, z: int) -> bool:  # a title another name follows, or "X के" qualifies
        if hindi.norm(say[a:z]) in own:
            return False
        q = re.search(r"(\S+)\s+(?:के|की|का)\s+$", say[:a])
        return any(z < b <= z + 2 for b, _ in people) or bool(q) and q.group(1) != "देश"

    at = [a for a, z in said if not (harm and _OWNED.match(say[z:])) and not titled(a, z)]
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
    strict pronoun rule). A city named next to its spot gives way to the spot's map, which marks both; two places
    with a route map show the route. The gate's ceilings hold by construction: no picture goes under a HELD_RUN-th
    beat in a row or over half the beats (the next picture of the key, else the next key, else a card: the chase
    Shorts' one police photo stood under 3 of 5 beats), and map cuts said again go, latest first, while maps fill
    more than MAP_SHARE of the picture beats."""
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

    def free(i: int, taken: set) -> bool:
        h = held_key(i, photos, groups)
        return h in taken or runs.get(h, 0) + 1 < HELD_RUN and not (len(beats) >= 5 and (counts[h] + 1) * 2 >
                                                                     len(beats))

    out, prev, last, backdrop, prev_key, prev_held, held = [], [], None, None, None, False, 0
    for k, b in enumerate(beats):
        say = b.get("say") or b.get("text") or ""
        found = names(say, cast, spellings, others)
        found = [(a, x) for a, x in found if not any(up.get(y) == x for _, y in found)]
        text = " ".join(_card_text(b))
        on_card = {x for _, x in names(text, cast, spellings, others)} if text.strip() else set()
        big = {x for _, x in names(_card_text(b)[0], cast, spellings, others)}
        picks: list[tuple[int, str, int]] = []
        skip: set[str] = set()

        def choose(n: int, a: int, x: str) -> None:
            route = next((routes[frozenset((x, y))] for _, y in found[n + 1:] if frozenset((x, y)) in routes), None)
            cands = [route] if route is not None else pools.get(x) or []
            taken = {p for p, _, _ in picks}
            keys = {held_key(p, photos, groups) for p in taken}
            cands = [i for i in cands if i not in taken and free(i, keys)]
            if cands:
                picks.append((min(cands, key=lambda i: (i in prev, used[i], cands.index(i))), x, a))
                skip.update(depict[route] if route is not None else ())

        rest = list(enumerate(found))
        while rest and not picks:  # the main view: the first key said that has a picture
            n, (a, x) = rest.pop(0)
            choose(n, a, x)
        # Three names, two views: of those said after the main view's, the one the card names takes the cut
        # (39411111185 b1, "मार्को रुबियो से मुलाकात" under subject, Mumbai, Rubio), so the card sits over its own
        # picture; a key said before the main view's never cuts in after it.
        rest.sort(key=lambda r: (r[1][1] not in big, r[1][1] not in on_card))
        for n, (a, x) in rest:
            if len(picks) == 2:
                break
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
                picks = [(min(pool, key=lambda i: (i in prev, used[i], pool.index(i))), SUBJECT, 0)]
        if picks:
            row["views"] = [p for p, _, _ in picks]
            if len(picks) > 1:
                row["cut_word"], row["cut_at"] = word_at(say, picks[1][2]), picks[1][2]
            row["card_view"] = next((j for j, i in enumerate(row["views"]) if depict[i] & on_card), 0)
            last, prev_key = row["views"][-1], picks[0][1]
            backdrop = next((i for i in reversed(row["views"]) if not visuals.is_map(photos[i])), backdrop)
        else:
            row["plate"] = CARD
            pick = backdrop if backdrop is not None else last
            row["views"] = [pick] if pick is not None else pools[SUBJECT][:1]
            prev_key = None
        held += this_held
        prev_held = this_held
        shown = {held_key(i, photos, groups) for i in row["views"]} if row["plate"] != CARD else set()
        runs = {h: runs.get(h, 0) + 1 for h in shown}
        counts.update(shown)
        for i in row["views"] if row["plate"] != CARD else ():
            used[i] += 1
        prev = row["views"] if row["plate"] != CARD else prev
        out.append(row)
    return _map_cuts(out, photos, [b.get("say") or b.get("text") or "" for b in beats])


def _map_cuts(rows: list[dict], photos: list[dict], says_: list[str] = ()) -> list[dict]:
    """Drop map cuts while maps fill over MAP_SHARE of the picture beats, by problems' per-beat weights or by the
    time the voice will give them (a beat's length in letters, a cut from its cut_at on; a card's time counted in
    neither): first a map already shown in an earlier beat, latest first. The hand-fixed Rubio cut to the Jamnagar
    map in beats 1 and 2, and maps filled half its pictures; 39411041538 cut to Juhu's map on its fourth word."""
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
            if role in ("person", "place", "topic"):
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


def vet_photo(i: int, photos: list[dict], cast: list[dict], year: int, person: bool, incident: bool,
              born: int | None = None) -> str:
    """Why photo i may not be on screen whatever the beat says, or "": the wrong time of life (media.era_reject),
    another event (for a cast person, or any photo in an incident story), or a landmark that is not its place.
    visuals.direct stamps it before planning and the gate reads the same reasons off the saved photos."""
    p = photos[i]
    role = p.get("role")
    if role == "map" or role == "topic":
        return ""
    if not role:
        pool = [q for q in photos if not q.get("role")]
        why = media.era_reject(p, year, born, "person" if person else "place", pool)
        event = media.event_kind(p) if incident else ""
    elif role == "person":
        pool = [q for q in photos if q.get("role") == "person" and q.get("who") == p.get("who")]
        why, event = media.era_reject(p, year, None, "person", pool), media.event_kind(p)
    else:
        why, event = media.era_reject(p, year, None, "place"), ""
        own = next((c.get("en") for c in cast if c.get("en") and key(c) in depicts(i, p, cast)), "")
        if role == "place" and own and media.not_itself(p, own):
            why = f"a landmark at {own}, not {own} itself"
    return why or (f"a photo from another event ({event})" if event else "")


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
    for v in views or []:
        if v.get("plate") != CARD:
            timed.setdefault(v["beat_k"], []).append((v["photo"], max(v["end"] - v["start"], 0.0)))
    beat_time = {}
    for v in views or []:
        beat_time[v["beat_k"]] = beat_time.get(v["beat_k"], 0.0) + max(v["end"] - v["start"], 0.0)
    out: list[str] = []
    total = map_time = 0.0
    cards = run = held = 0
    pictures: list[int] = []
    prev_key, prev_held, ran = None, False, False
    shown_beats = [(k, b) for k, b in enumerate(short.beats) if b.shot.startswith("photo:")]
    for k, b in shown_beats:
        say, n = b.text, k + 1
        if b.plate == CARD:
            cards, run = cards + 1, run + 1  # a card's time is not picture time: cards never dilute the maps
            if run >= CARD_RUN and not ran:
                out.append(f"text cards: {run} beats in a row from beat {n - run + 1}")
                ran = True
            prev_key, prev_held = None, False
            continue
        run = 0
        named = canon({x for _, x in names(say, cast, spell, others)})
        shown = shot_photos(b.shot)
        weights = timed.get(k) if views else [(i, 1.0 / len(shown)) for i in shown]
        this_held, main = False, None
        # The pronoun rule holds the subject for the whole beat: a cut to another of their photos stays about them.
        may_hold = k > 0 and not named and continues(say, prev_key, prev_held, held, person)
        for j, (i, w) in enumerate(weights or []):
            if i >= len(photos):
                continue
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
            if why := vet(i, photos, short, cast):
                out.append(f"pictures: beat {n} shows {_label(i, photos)}: {why}")
            if j == 0:
                main = SUBJECT if SUBJECT in d and ok else next(iter(d & named), None)
        held += this_held
        prev_key, prev_held = main, this_held
        big, small = (b.card or {}).get("big", ""), (b.card or {}).get("small", "")
        # A police name too: "मुंबई पुलिस" over Tiger Shroff passed for any picture (39427875643 replan, 2026-10-22
        # review round 2). With render.json's views, the chip's own window (_chip_overrun).
        said = canon(card_keys(big, small, cast, spell, others))
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
        speaker = hook.split(":", 1)[0].strip() if ":" in hook else ""
        if speaker and not hindi.quotes(speaker, narration):
            out.append(f"pictures: the hook names {speaker}, whom the narration never says")
        for who in dict.fromkeys(n.get("hi") for n in sc.get("names") or [] if n.get("hi")):
            if hindi.contains(hook, who) and not hindi.contains(narration, who) and not hindi.contains(speaker, who):
                out.append(f"pictures: the hook names {who}, whom the narration never says")
    if total and map_time / total > MAP_SHARE:
        out.append(f"pictures: maps fill {map_time / total:.0%} of the picture time (at most {MAP_SHARE:.0%})")
    if cards * 2 > len(shown_beats):
        out.append(f"text cards: {cards} of {len(shown_beats)} beats (at most half)")
    want = min(sc.get("min_visuals", visuals.MIN_VISUALS), len(shown_beats) - cards)
    distinct, grouped = len(set(pictures)), len({groups.get(i, i) for i in pictures})
    if distinct >= want > grouped:
        out.append(f"pictures: only {grouped} different pictures once a place's maps count as one (want {want})")
    return out


def _chip_overrun(n: int, k: int, pic, views: list[dict], photos: list[dict], hooked: bool) -> list[str]:
    """A chip up over a picture it is not on: render.json's stamped window (compose.chip_spans), or for a render
    saved before chips were stamped, CHIP_HOLD from its picture's start (after the hook card on beat 1), over
    whatever came after the cut ("बेगूसराय" over Tiger Shroff at the airport, 39418354883)."""
    mine = [v for v in views if v["beat_k"] == k and v.get("plate") != CARD]
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


def plain(say: str, loss: bool = False) -> bool:
    """A card for this line goes on the plain channel background, not a blur of a face (4.0): "दो घायल / अस्पताल"
    sat over a blurred Tiger Shroff."""
    return loss or says(say, HARM + visuals.ACCUSED) >= 0
