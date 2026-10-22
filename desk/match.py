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
CARD = "card"
# A beat that names nothing holds the subject only when it opens on a pronoun AND the previous beat's main picture
# was the subject: "फडणवीस भी उनके साथ" is not a leading pronoun, so it is not about Tiger Shroff (39508637683 b2).
LEAD = re.compile(r"^(उन्होंने|उनके|उनका|उनकी|उन्हें|उनको|उनसे|वे|वह)(?=\s|$)")
CONTINUITY = 2  # such beats a Short may hold, never two in a row
# Never on a pronoun alone: a harm line (Tiger Shroff smiling under "उनके ड्राइवर और एक फैन को गोली लगी",
# 39505534156 b4) or an actor no picture is of ("मेहमान नेता", "एक व्यक्ति ने इस हमले की जिम्मेदारी ली").
HARM = ("हमल", "फायरिंग", "फ़ायरिंग", "गोली", "घायल", "जख्मी", "ज़ख्मी", "मौत", "मृत", "हत्या", "चोट", "धमकी", "हिंसा",
        "निधन")
UNNAMED = ("मेहमान", "संगठन", "विपक्ष", "व्यक्ति", "शख्स", "शख़्स", "बदमाश", "गिरोह", "गैंग")
# Paired ceilings (4.0): cards at most half the beats and never CARD_RUN in a row; maps and routes at most MAP_SHARE
# of the picture time (Rubio: 67%).
CARD_RUN, MAP_SHARE = 3, 0.4
PUNCT = "\"',.;:!?।()"


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
    on-screen name and a map's description. A story's own photo (no role) is the SUBJECT."""
    if photo.get("depicts") is not None:
        return set(photo["depicts"])
    role = photo.get("role")
    if not role:
        return {SUBJECT}
    if role == "police":
        return {POLICE}
    if role == "map":
        return {hindi.norm(n) for n in _map_names(photo, list(cast)) if n}
    if photo.get("who"):
        return {hindi.norm(photo["who"])}
    return {key(c) for c in cast if i in (c.get("photos") or [])}


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


def names(say: str, cast: list[dict], subject_spellings=()) -> list[tuple[int, str]]:
    """(where in say, key) for everything the beat names that a picture could be of, in order: cast members (via
    visuals.located), the story's subject by any of its spellings outside another person's name (a "श्रॉफ" inside
    "जैकी श्रॉफ" is not Tiger Shroff), and the police for a police or accused line (never another force's:
    "राजस्थान पुलिस"). "<city> पुलिस" names the police, not the city."""
    members = [c for c in cast if c.get("kind") in ("person", "place", "topic")]
    police = next((c for c in cast if c.get("kind") == "police"), None)
    other = bool(police) and visuals.other_force(say, police)
    found, masked = [], list(say)
    for at, c in visuals.located(say, members):
        spelt = [w for w in [c.get("hi") or "", *(c.get("alias") or [])] if w and hindi.find(say, w) == at]
        end = _end(say, at, max((len(w.split()) for w in spelt), default=1))
        if c.get("kind") == "person":
            masked[at:end] = " " * (end - at)
        if c.get("kind") == "place" and re.match(r"\s*पुलिस", say[end:]):
            if not other:
                found.append((at, POLICE))
            continue
        found.append((at, key(c)))
    masked = "".join(masked)
    at = [a for a in (hindi.find(masked, w) for w in subject_spellings if w) if a >= 0]
    if at:
        found.append((min(at), SUBJECT))
    if not other:
        hits = [m.start() for m in re.finditer("पुलिस", say)] + [say.find(w) for w in visuals.ACCUSED if w in say]
        if hits:
            found.append((min(hits), POLICE))
    first: dict[str, int] = {}
    for a, k in sorted(found):
        first.setdefault(k, a)
    return sorted(((a, k) for k, a in first.items()), key=lambda x: x[0])


def word_at(say: str, at: int) -> str:
    """The word of say starting at `at`, without punctuation: what compose cuts on."""
    w = (say[at:].split() or [""])[0]
    return w.strip(PUNCT)


def continues(say: str, prev: str | None, prev_held: bool, held: int, person: bool) -> bool:
    """The strict continuity rule (4.0): a person's Short, a leading pronoun, the previous main picture the subject,
    not after another such beat, at most CONTINUITY, and no harm, accused or unnamed actor in the line."""
    return person and prev == SUBJECT and not prev_held and held < CONTINUITY and bool(LEAD.match(say.strip())) \
        and not any(w in say for w in HARM + UNNAMED + visuals.ACCUSED)


def _card_text(beat: dict) -> tuple[str, str]:
    card = beat.get("card") or {}
    return card.get("big") or beat.get("caption") or "", card.get("small") or beat.get("label") or ""


def plan(beats: list[dict], photos: list[dict], cast: list[dict], subject: list[int], kind: str = "",
         spellings=(), person: bool = True) -> list[dict]:
    """Per beat {views, cut_word, plate, card_view}. beats: [{"say", "card"|"caption"/"label"}]; photos: every
    picture (a photo stamped "vet" with a reason is never shown); cast: visuals.direct's cast, with "route" and
    "police" rows; subject: the story's own photos, ranked; spellings: how the script names the subject.

    The main view is the picture of the first key the beat names, the cut the picture of the next different key on
    its word; one key, no cut; no key, a card over the last anchored picture (beat 1 opens on the subject, and a
    person's explainer may hold the subject on the strict pronoun rule). A city named next to its spot gives way to
    the spot's map, which marks both; two places with a route map show the route."""
    depict = {i: depicts(i, p, cast) for i, p in enumerate(photos)}
    up = inside(photos, cast)
    ok = [i for i, p in enumerate(photos) if not p.get("vet")]
    pools = {SUBJECT: [i for i in subject if i in ok]}
    for i in ok:
        if len(depict[i]) == 1 and i not in subject:
            pools.setdefault(next(iter(depict[i])), []).append(i)
    routes = {frozenset(depict[i]): i for i in ok if len(depict[i]) == 2}
    person = person and kind in ("", "explainer")
    used: Counter = Counter()
    out, prev, last, prev_key, prev_held, held = [], [], None, None, False, 0
    for k, b in enumerate(beats):
        say = b.get("say") or b.get("text") or ""
        found = names(say, cast, spellings)
        found = [(a, x) for a, x in found if not any(up.get(y) == x for _, y in found)]
        text = " ".join(_card_text(b))
        on_card = {x for _, x in names(text, cast, spellings)} if text.strip() else set()
        # Three names, two views: the one the card names takes the cut (39411111185 b1, "मार्को रुबियो से मुलाकात"
        # under subject, Mumbai, Rubio), so the card sits over its own picture.
        if len(found) > 2:
            big = {x for _, x in names(_card_text(b)[0], cast, spellings)}
            found = found[:1] + sorted(found[1:], key=lambda f: (f[1] not in big, f[1] not in on_card))
        picks: list[tuple[int, str, int]] = []
        skip: set[str] = set()
        for n, (a, x) in enumerate(found):
            if x in skip or len(picks) == 2:
                continue
            route = next((routes[frozenset((x, y))] for _, y in found[n + 1:] if frozenset((x, y)) in routes), None)
            if route is not None:
                skip |= depict[route]
                cands = [route]
            else:
                cands = pools.get(x) or []
            cands = [i for i in cands if i not in {p for p, _, _ in picks}]
            if cands:
                pick = min(cands, key=lambda i: (i in prev, used[i], cands.index(i)))
                picks.append((pick, x, a))
        row = {"views": [], "cut_word": "", "plate": "", "card_view": 0}
        this_held = False
        if not picks and pools[SUBJECT] and (k == 0 or continues(say, prev_key, prev_held, held, person)):
            this_held = k > 0
            pool = pools[SUBJECT]
            picks = [(min(pool, key=lambda i: (i in prev, used[i], pool.index(i))), SUBJECT, 0)]
        if picks:
            row["views"] = [p for p, _, _ in picks]
            if len(picks) > 1:
                row["cut_word"] = word_at(say, picks[1][2])
            row["card_view"] = next((j for j, i in enumerate(row["views"]) if depict[i] & on_card), 0)
            last, prev_key = row["views"][-1], picks[0][1]
        else:
            row["plate"] = CARD
            row["views"] = [last] if last is not None else pools[SUBJECT][:1]
            prev_key = None
        held += this_held
        prev_held = this_held
        for i in row["views"] if row["plate"] != CARD else ():
            used[i] += 1
        prev = row["views"] if row["plate"] != CARD else prev
        out.append(row)
    return out


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
    person = _person(short) and short.kind in ("", "explainer")
    groups = group(photos, cast)
    # A place's own Short (Jantar Mantar) also has it in its cast: the two keys are one.
    own = hindi.norm(sc.get("name_hi") or "")

    def canon(keys: set[str]) -> set[str]:
        return {SUBJECT if x == own else x for x in keys}

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
            cards, run = cards + 1, run + 1
            total += beat_time.get(k, 1.0) if views else 1.0
            if run >= CARD_RUN and not ran:
                out.append(f"text cards: {run} beats in a row from beat {n - run + 1}")
                ran = True
            prev_key, prev_held = None, False
            continue
        run = 0
        named = canon({x for _, x in names(say, cast, spell)})
        shown = shot_photos(b.shot)
        weights = timed.get(k) if views else [(i, 1.0 / len(shown)) for i in shown]
        this_held, main = False, None
        # The pronoun rule holds the subject for the whole beat: a cut to another of their photos stays about them.
        may_hold = k > 0 and SUBJECT not in named and continues(say, prev_key, prev_held, held, person)
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
        # A card's big line, or a small line that is only a name (the strap "जामनगर"), says "this is X"; a small
        # phrase ("मुम्बई में बैठक") is a caption, not a label.
        said = {x for _, x in names(big, cast, spell)}
        said |= {key(c) for c in cast if c.get("kind") != "police" and hindi.norm(small) in
                 {hindi.norm(w) for w in [c.get("hi") or "", *(c.get("alias") or [])] if w}}
        said |= {SUBJECT} if small and hindi.norm(small) in {hindi.norm(w) for w in spell} else set()
        on = canon(set().union(*(depicts(i, photos[i], cast) for i in shown if i < len(photos))))
        for x in canon(said) - on - {POLICE}:
            out.append(f"pictures: card {n} names {x} over a picture of something else")
    hook = sc.get("hook") or ""
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


def plain(say: str, loss: bool = False) -> bool:
    """A card for this line goes on the plain channel background, not a blur of a face (4.0): "दो घायल / अस्पताल"
    sat over a blurred Tiger Shroff."""
    return loss or any(w in say for w in HARM + visuals.ACCUSED)
