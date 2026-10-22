"""Visual direction for a bulletin: every beat shows who or where it is about, and the picture changes every few
seconds.

Owner, 2026-10-20, on the Tiger Shroff Short (one smiling portrait for all 47 seconds of a shooting story): "In a
single image you speakout the full news or story, how audience will stay to see this". After the script is written,
each name it lists is looked up: another person it names gets their own face-matched Commons portraits (with their
name on screen), a place gets an OpenStreetMap locator map (a landmark its own Commons photo first), two places in
one beat get a map of both, and a police
beat in an Indian city gets that city's police (Commons). Photos of the event itself are news agencies' copyright
and are never used; a map shows where, never what happened.
"""
from __future__ import annotations

import io
import logging
import math
import re
from collections import Counter
from collections.abc import Iterator
from itertools import chain
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import hindi, media, net, wiki

log = logging.getLogger(__name__)

MIN_VISUALS = 3  # distinct pictures on screen; a lead story about a person may go with 2 (writer.LEAD_SCORE)
# States are counted apart from towns and landmarks, and a police force is no place: the Tiger Shroff probe's two
# home states, then "Kota Police", filled the places, and Kota's station, where all three were caught, had no picture.
MAX_PEOPLE, MAX_PLACES, MAX_REGIONS = 3, 7, 3
PERSON_PHOTOS = 2
# A named landmark (a station, a hospital, a beach: a place with no population) shows its own Commons photo, then
# its map: the Tiger Shroff chase named five stations and showed only maps and portraits.
SIGHT_PHOTOS = 1
TOPIC_PHOTOS = 2
WORN = 2  # beats a place may stand under before anything else its beat names goes first
PLACE_LABELS = ("स्थल", "स्थान", "जगह", "इलाका", "शहर", "जिला", "ज़िला", "राज्य")
PLACE_WORDS = {"मैदान", "स्टेशन", "अस्पताल", "थाना", "अदालत", "कोर्ट", "बीच", "जंक्शन", "मंदिर", "पार्क", "चौक", "बाजार",
               "बाज़ार", "हवाई", "एयरपोर्ट", "जेल", "मार्ग", "नगर", "कॉलोनी", "गांव", "गाँव"}
TITLE_BEATS = 2
INDIA = "Q668"
COUNTRY_KINDS = {"Q6256", "Q3624078", "Q7275"}
POLICE = ("पुलिस",)
# Words that may stand before "पुलिस" without naming a force ("कोटा से पकड़े गए 3 संदिग्धों को पुलिस ...").
NOT_A_FORCE = {"की", "के", "का", "को", "ने", "और", "में", "से", "कि", "भी", "तो", "व", "एवं", "जब", "अब", "वहीं", "लेकिन",
               "हुए", "हैं", "है", "था", "थी", "गया", "बाद", "तक", "पर", "मुताबिक", "अनुसार"}
# A beat about the accused shows the police, not the story's person.
ACCUSED = ("आरोपी", "आरोपियों", "पूछताछ", "गिरफ्तार", "गिरफ़्तार", "रिमांड", "शूटर", "हमलावर", "संदिग्ध")

# Maps fill the full-screen Short's plate (compose.Plate: the frame times compose.MARGIN).
MAP_W, MAP_H = 1253, 2227
TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
CACHE = Path(__file__).resolve().parents[1] / "work" / "cache" / "osm"
UPSCALE = 2.4  # tile pixels shown at most this much larger, so the map's own labels stay readable
PAGE = "https://www.openstreetmap.org/copyright"
LICENSE = "CC BY-SA 2.0"
CREDIT = "नक्शा: © OpenStreetMap contributors / CC BY-SA 2.0"
WIDE_KM, NEAR_KM, REGION_KM = 900.0, 36.0, 1500.0
# A place inside another the script names (Juhu in Mumbai) is the spot: the city's map marks it, never the city's
# centre, and a street map shows it close; the two are never joined by a route line (owner, 2026-10-20: "use the map
# correctly if you are showing mumbai there").
NESTED_KM, CITY_KM, STREET_KM = 40.0, 30.0, 6.0
MARKER = (220, 30, 44)
INK = (10, 20, 46)


# --- Locator maps -----------------------------------------------------------------------------------------------

def _x(lon: float) -> float:
    return (lon + 180.0) / 360.0


def _y(lat: float) -> float:
    s = math.sin(math.radians(max(min(lat, 85.0), -85.0)))
    return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def window(points: list[tuple[float, float]], width_km: float) -> dict:
    """The Web Mercator window (z0 units) at the map's aspect, centred on the points, at least width_km wide and
    wide enough to hold every point with a margin."""
    xs, ys = [_x(p[1]) for p in points], [_y(p[0]) for p in points]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    lat = sum(p[0] for p in points) / len(points)
    w = width_km / (40075.0 * math.cos(math.radians(lat)))
    w = max(w, (max(xs) - min(xs)) * 1.7, (max(ys) - min(ys)) * 1.7 * MAP_W / MAP_H)
    h = w * MAP_H / MAP_W
    return {"x0": cx - w / 2, "x1": cx + w / 2, "y0": cy - h / 2, "y1": cy + h / 2}


def project(win: dict, lat: float, lon: float) -> tuple[float, float]:
    return ((_x(lon) - win["x0"]) / (win["x1"] - win["x0"]) * MAP_W,
            (_y(lat) - win["y0"]) / (win["y1"] - win["y0"]) * MAP_H)


def zoom(win: dict) -> int:
    native = (win["x1"] - win["x0"]) * 256
    return max(2, min(17, math.ceil(math.log2(MAP_W / UPSCALE / native))))


def ground(win: dict) -> Image.Image:
    """OpenStreetMap's standard tiles under the window, stitched and scaled to the map (tile policy: a contact
    User-Agent, cached tiles, a few dozen a Short, the credit wherever the map is shown)."""
    z = zoom(win)
    n = 2 ** z
    x0, x1, y0, y1 = (win[k] * n for k in ("x0", "x1", "y0", "y1"))
    tx0, tx1, ty0, ty1 = int(x0), int(x1), int(max(y0, 0)), int(min(y1, n - 1e-9))
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (170, 211, 223))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            raw = net.get(TILES.format(z=z, x=tx % n, y=ty), cache=CACHE, timeout=30, tries=3)
            mosaic.paste(Image.open(io.BytesIO(raw)).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    box = ((x0 - tx0) * 256, (y0 - ty0) * 256, (x1 - tx0) * 256, (y1 - ty0) * 256)
    return mosaic.resize((MAP_W, MAP_H), Image.LANCZOS, box=box)


def _label(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str) -> None:
    from .compose import _font, drawable

    text = drawable(text, "ExtraBold")
    font = _font("ExtraBold", 50)
    box = d.textbbox(xy, text, font=font, anchor="mb")
    d.rounded_rectangle((box[0] - 22, box[1] - 14, box[2] + 22, box[3] + 16), radius=16, fill=INK + (235,))
    d.text(xy, text, font=font, fill=(255, 255, 255, 255), anchor="mb")


def draw(base: Image.Image, win: dict, sites: list[tuple[tuple[float, float], str]]) -> Image.Image:
    """The map a little dimmed, each site a red marker with its Hindi name, two sites joined by a dashed line."""
    img = Image.blend(base.convert("RGB"), Image.new("RGB", (MAP_W, MAP_H), INK), 0.14).convert("RGBA")
    pts = [project(win, *site) for site, _ in sites]
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for sx, sy in pts:
        ImageDraw.Draw(halo).ellipse((sx - 80, sy - 80, sx + 80, sy + 80), fill=MARKER + (120,))
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(26)))
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    if len(pts) == 2:
        (ax, ay), (bx, by) = pts
        steps = max(int(math.hypot(bx - ax, by - ay) / 26), 2)
        for k in range(0, steps, 2):
            p0 = (ax + (bx - ax) * k / steps, ay + (by - ay) * k / steps)
            p1 = (ax + (bx - ax) * (k + 1) / steps, ay + (by - ay) * (k + 1) / steps)
            d.line([p0, p1], fill=INK + (240,), width=16)
            d.line([p0, p1], fill=(255, 255, 255, 255), width=8)
    for (sx, sy), (_, name) in zip(pts, sites):
        d.ellipse((sx - 38, sy - 38, sx + 38, sy + 38), outline=MARKER + (255,), width=10)
        d.ellipse((sx - 15, sy - 15, sx + 15, sy + 15), fill=MARKER + (255,), outline=(255, 255, 255, 255), width=4)
        if name:
            _label(d, (sx, sy - 62), name)
    return Image.alpha_composite(img, over).convert("RGB")


def map_photo(sites: list[tuple[tuple[float, float], str]], width_km: float, path: Path, about: str) -> dict:
    """A locator map as a story photo (role "map"), saved at path."""
    win = window([s for s, _ in sites], width_km)
    path.parent.mkdir(parents=True, exist_ok=True)
    draw(ground(win), win, sites).save(path, quality=92)
    names = " - ".join(n for _, n in sites)
    return {"file": f"OpenStreetMap: {names}", "url": "", "page": PAGE, "width": MAP_W, "height": MAP_H,
            "author": "OpenStreetMap contributors", "license": LICENSE, "description": f"MAP: {about}", "date": "",
            "origin": "map", "path": str(path), "host": "OpenStreetMap", "role": "map", "focus": None,
            "credit": CREDIT, "who": names}


def is_map(photo: dict) -> bool:
    return photo.get("role") == "map"


# --- Who and where the script names -----------------------------------------------------------------------------

def kinds(ent: dict) -> set[str]:
    return {c["value"] for c in wiki.claims(ent, "P31")}


def resolve(en: str, india: bool) -> tuple[str, str, dict] | None:
    """(QID, title, item) of a person or place the script names: Wikipedia's first hit for the name, or for
    "<name>, India" when that is a disambiguation page or the place is abroad in an Indian story."""
    queries = [en] + ([f"{en}, India"] if india else [])
    for q in queries:
        try:
            title = wiki.search(q)
            qid = (wiki.page_info([title]).get(title) or {}).get("qid") if title else None
            ent = wiki.entities([qid]).get(qid) if qid else None
        except Exception as exc:
            log.info("visuals: %s not resolved (%s)", q, exc)
            return None
        if not ent or wiki.DISAMBIGUATION in kinds(ent):
            continue
        if wiki.HUMAN in kinds(ent):
            from . import stories

            if stories.plain_title(title).lower() == en.lower():
                return qid, title, ent
            continue
        if media.place_like(ent) and not kinds(ent) & COUNTRY_KINDS:
            if india and INDIA not in {c["value"] for c in wiki.claims(ent, "P17")}:
                continue
            if title.lower().startswith(en.lower() + " "):
                continue  # "Ramlila" (the play) found "Ramlila Maidan", a ground across Delhi from the event
            return qid, title, ent
    return None


# What a "topic" the script names may be: a festival, a rite or a performance, pictured by its own Commons photos
# (a Ramlila stage, Ravan's effigy burning). Never an organisation, a law or a work: their pictures are logos and
# covers.
TOPIC = re.compile(r"\b(festival|celebrat\w*|ritual|rite|folk|re-?enactment|drama\w*|theatre|dance|tradition\w*|"
                   r"ceremony|procession|puja)\b", re.I)
MAX_TOPICS = 2


def resolve_topic(en: str) -> tuple[str, str, dict] | None:
    """(QID, title, item) for the English Wikipedia article titled exactly `en` when it is a festival, rite or
    performance."""
    try:
        page = wiki.page_info([en]).get(en) or {}
        ent = wiki.entities([page["qid"]]).get(page["qid"]) if page.get("qid") else None
    except Exception:
        return None
    return (page["qid"], page.get("title") or en, ent) if ent and topic_like(ent) else None


def topic_like(ent: dict) -> bool:
    """A festival, rite or performance. Ramlila's item carries coordinates; a real place is also located in a
    district or has people."""
    if wiki.HUMAN in kinds(ent) or wiki.DISAMBIGUATION in kinds(ent) or wiki.claims(ent, "P131") \
            or wiki.claims(ent, "P1082"):
        return False
    return bool(TOPIC.search(((ent.get("descriptions") or {}).get("en") or {}).get("value", "")))


def is_region(ent: dict) -> bool:
    """A state or province (it has a capital): shown on a wider map than a town."""
    return bool(wiki.claims(ent, "P36"))


def _population(ent: dict) -> float:
    return max((c["value"] for c in wiki.claims(ent, "P1082") if isinstance(c["value"], float)), default=0.0)


def within(places: list[dict]) -> dict[str, dict]:
    """{inner place's en: the place it lies in} for the places the script names: a place whose Wikidata P131 is the
    other, or the smaller of two non-region places under NESTED_KM apart."""
    from .stories import km_between

    out = {}
    for a in places:
        for b in places:
            if a is b or a["en"] in out or is_region(a["ent"]) or out.get(b["en"]) is a:
                continue
            pa, pb = wiki.coords(a["ent"]), wiki.coords(b["ent"])
            inside = b["qid"] in {c["value"] for c in wiki.claims(a["ent"], "P131")}
            near = bool(pa and pb) and not is_region(b["ent"]) and km_between(pa, pb) < NESTED_KM \
                and _population(a["ent"]) < _population(b["ent"])
            if inside or near:
                out[a["en"]] = b
    return out


def mentions(say: str, cast: list[dict]) -> list[dict]:
    """The cast members a beat names, in the order it names them."""
    return [c for _, c in located(say, cast)]


def located(say: str, cast: list[dict]) -> list[tuple[int, dict]]:
    """(where in say, member) for each cast member the beat names, in the order it names them: the matcher cuts on
    the word that names the second picture (SYNC-AUDIT 4.1 step 2), so the offset is kept, spelling differences
    aside ("मुंबई" for "मुम्बई")."""
    found = []
    for c in cast:
        hi, en = c.get("hi") or "", c.get("en") or ""
        at = [hindi.find(say, w) for w in [hi, *(c.get("alias") or [])] if w]
        at = [a for a in at if a >= 0]
        m = re.search(rf"\b{re.escape(en)}\b", say, re.I) if en else None
        if at or m:
            found.append((min(at) if at else m.start(), c))
    return sorted(found, key=lambda x: x[0])


def surnames(cast: list[dict], subject_hi: str = "") -> None:
    """Give each person their Hindi surname as an alias when no one else in the story carries it: scripts say
    "फडणवीस" after "देवेंद्र फडणवीस", and two beats about him showed the Juhu map (2026-10-21). Shared surnames
    (टाइगर, जैकी and कृष्णा श्रॉफ) stay full names only."""
    last = [((c.get("hi") or "").split() or [""])[-1] for c in cast]
    taken = Counter(w for c, w in zip(cast, last) if c.get("kind") == "person")
    own = set(subject_hi.split())
    for c, w in zip(cast, last):
        if c.get("kind") == "person" and len(hindi.norm(w)) >= 3 and taken[w] == 1 and w not in own \
                and len((c.get("hi") or "").split()) > 1:
            c["alias"] = [w]


def place_card(card: dict) -> bool:
    """A card that names where something happened ("उत्सव मैदान / कार्यक्रम स्थल")."""
    big, small = (card or {}).get("big", ""), (card or {}).get("small", "")
    return bool(big) and (any(w in small for w in PLACE_LABELS) or big.split()[-1] in PLACE_WORDS)


def card_over(card: dict, shown: list[int], cast: list[dict]) -> dict:
    """A place card sits only over its place's own map or photo: the Modi rebuild put "उत्सव मैदान" over Delhi's
    map. Over another place it names the place on screen; over no place it goes."""
    if not place_card(card):
        return card
    places = [c for c in cast if c.get("kind") == "place" and set(c.get("photos") or []) & set(shown)]
    if any(hindi.contains(card["big"], c["hi"]) or any(hindi.contains(card["big"], a) for a in c.get("alias") or [])
           for c in places):
        return card
    return {**card, "big": places[0]["hi"]} if places else {}


def titles(beats: list[dict], subject_hi: str) -> list[str]:
    """The word the script puts before the story's person in TITLE_BEATS beats ("प्रधानमंत्री नरेन्द्र मोदी", "अभिनेता
    टाइगर श्रॉफ"): a later "विजयदशमी पर प्रधानमंत्री ने ..." is about them, and the Modi rebuild showed Delhi's map
    under it instead."""
    first = hindi.norm((subject_hi.split() or [""])[0])
    if not first:
        return []
    seen: Counter = Counter()
    for b in beats:
        words = [hindi.norm(w) for w in re.findall(r"[\u0900-\u097F]+", b.get("say") or "")]
        seen.update({a for a, z in zip(words, words[1:]) if z == first and len(a) >= 3
                     and a not in hindi.FUNCTION_WORDS and a not in NOT_A_FORCE})
    return [w for w, n in seen.items() if n >= TITLE_BEATS]


def _subject(en: str, subject_en: str) -> bool:
    # A story about a place passes "" here: "" is in every name, and the Modi Dussehra Short (2026-10-21) lost
    # Narendra Modi from its pictures that way.
    a, b = en.lower().strip(), subject_en.lower().strip()
    return bool(a and b) and (a == b or a in b or b in a)


def cast_for(draft: dict, subject_en: str, india: bool, places_too: bool = True) -> list[dict]:
    """The people and places the script names besides its subject, resolved: [{en, hi, kind, qid, title, ent}]."""
    out, people, places, regions, topics = [], 0, 0, 0, 0
    for n in draft.get("names") or []:
        en, hi = (n.get("en") or "").strip(), (n.get("hi") or "").strip()
        if not en or not hi or _subject(en, subject_en) or any(c["en"] == en for c in out) \
                or re.search(r"\bpolice\b", en, re.I) or any(w in hi for w in POLICE):
            continue
        said = any(hindi.contains(b.get("say", ""), hi) or hi in b.get("say", "") for b in draft.get("beats") or [])
        if not said:
            continue
        found = resolve(en, india)
        if found and topic_like(found[2]):
            found = None  # Wikipedia's search returns the Ramlila article for "Ramlila, India" on some calls
        if not found and places_too and topics < MAX_TOPICS:
            if found := resolve_topic(en):
                topics += 1
                out.append({"en": en, "hi": hi, "kind": "topic", "qid": found[0], "title": found[1],
                            "ent": found[2], "alias": [hi + "ओं"]})  # "देश भर में राम लीलाओं का मंचन"
            continue
        if not found:
            continue
        qid, title, ent = found
        if any(c["qid"] == qid for c in out):
            continue
        kind = "person" if wiki.HUMAN in kinds(ent) else "place"
        region = kind == "place" and is_region(ent)
        if kind == "place" and not places_too or kind == "person" and people >= MAX_PEOPLE \
                or region and regions >= MAX_REGIONS or kind == "place" and not region and places >= MAX_PLACES:
            continue
        people += kind == "person"
        regions += region
        places += kind == "place" and not region
        out.append({"en": en, "hi": hi, "kind": kind, "qid": qid, "title": title, "ent": ent})
    return out


# --- Assignment -------------------------------------------------------------------------------------------------

def other_force(say: str, police: dict) -> bool:
    """The beat names some other police force ("राजस्थान पुलिस ने बताया" when the photo is Mumbai Police)."""
    for m in re.finditer(r"(\S+)\s+पुलिस", say):
        word = m.group(1).strip(",.;:।'\"()")
        if word and word not in NOT_A_FORCE and not (police.get("hi") and hindi.contains(police["hi"], word)):
            return True
    return False


def assign(beats: list[dict], subject: list[int], cast: list[dict], first: int | None = None,
           person: list[str] | None = None) -> list[list[int]]:
    """[main, cut] photo indices for each beat ([main] when there is no second view).

    person: the spellings of the story's person when its own photos are their portraits. A beat that does not name
    them shows the police (a beat about the accused) or the story's places instead, never their portrait: the
    chase dry run put a smiling Tiger Shroff over the injured and the interrogation.

    beats: [{"say", "photo"}] as the writer wrote them; subject: indices of the story's own photos (ranked); cast:
    [{"hi", "en", "kind", "photos": [...], "near": [...]}] with photo indices, plus {"kind": "route", "pair":
    (en, en), "photos": [i]} and {"kind": "police", "photos": [...]}. Beat 1 opens on the writer's choice (the story's
    best photo). A beat that names someone shows them; two places, the map of both; a police beat, the police; a
    place, its map (the wide one first). Otherwise the story's own photos, least shown first and never the previous
    beat's. Each beat's cut is another picture it names, else another of the story's own photos."""
    used: dict[int, int] = {}
    shown_place: set[str] = set()
    routes = {tuple(c["pair"]): c for c in cast if c["kind"] == "route"}
    police = next((c for c in cast if c["kind"] == "police" and c["photos"]), None)
    members = [c for c in cast if c["kind"] in ("person", "place", "topic") and c["photos"]]
    scene = [c for c in members if c["kind"] == "place"]
    out: list[list[int]] = []
    prev: list[int] = []
    # A place's wide map, close map and photo are one place on screen: the Kota court Short held Kota for six beats.
    group = {i: id(c) for c in scene for i in c["photos"] + (c.get("near") or []) + (c.get("sight") or [])}

    def stale(i: int) -> bool:
        g = group.get(i)
        return g is not None and len(out) >= 2 and all(g in {group.get(j) for j in v} for v in out[-2:])

    def worn(c: dict) -> bool:
        return sum(id(c) in {group.get(j) for j in v} for v in out) >= WORN

    def take(c: dict) -> int:
        pool = c["photos"]
        if c["kind"] == "place" and c["en"] in shown_place and c.get("near"):
            pool = c["near"] + pool
        pick = min(pool, key=lambda i: (i in prev, used.get(i, 0), pool.index(i)))
        if c["kind"] == "place":
            shown_place.add(c["en"])
        return pick

    def sight(c: dict) -> int | None:
        pool = c.get("sight") or []
        return min(pool, key=lambda i: (i in prev, used.get(i, 0))) if pool else None

    def scenery(places: list[dict], main: int) -> int | None:
        # A place beat cuts to another picture of its places or the story's route, never to the story's person:
        # the chase dry run put "रेलवे स्टेशन" over Tiger Shroff's portrait.
        pool = [i for c in places for i in c["photos"] + (c.get("near") or []) + (c.get("sight") or [])]
        pool += [i for r in routes.values() for i in r["photos"]]
        pool = [i for i in dict.fromkeys(pool) if i != main and i not in prev]
        return min(pool, key=lambda i: (stale(i), used.get(i, 0))) if pool else None

    def own(avoid: set[int], wish: int | None = None) -> int | None:
        pool = [i for i in subject if i not in avoid] or [i for i in subject if i not in prev] or subject
        if not pool:
            return None
        if wish in pool and not used.get(wish):
            return wish
        return min(pool, key=lambda i: (used.get(i, 0), subject.index(i)))

    for k, beat in enumerate(beats):
        say = beat.get("say", "")
        named = mentions(say, members)
        people = [c for c in named if c["kind"] == "person"]
        places = [c for c in named if c["kind"] == "place"]
        # "मुम्बई के जुहू": the spot, on its city's map, not the city's centre first.
        places = [c for c in places if not any(s.get("inside") == c["en"] for s in places)]
        options: list[int] = []
        if k == 0:
            options.append(first if first is not None else (beat.get("photo") if beat.get("photo") in subject
                                                            else subject[0] if subject else None))
        pair = tuple(c["en"] for c in places[:2])
        route = (routes.get(pair) or routes.get(pair[::-1])) if len(places) >= 2 else None
        if route:
            options.append(route["photos"][0])
        options += [take(c) for c in people]
        if k > 0 and person and not people and any(hindi.contains(say, w) for w in person) \
                and (mine := own(set(prev), beat.get("photo"))) is not None:
            # "प्रधानमंत्री नरेन्द्र मोदी ने दिल्ली में ..." shows him, with Delhi as the cut, not Delhi alone.
            options.append(mine)
        options += [take(c) for c in named if c["kind"] == "topic"]
        if police and any(w in say for w in POLICE) and not people and not other_force(say, police):
            # "पुलिस के अनुसार, ... सूरत" is the place's beat: the dry run put Mumbai Police under Surat and Kota.
            if not places or (police.get("hi") and hindi.contains(say, f"{police['hi']} पुलिस")):
                options.append(take(police))
        # A place already under WORN beats gives way to anything else the beat names: the Modi Dussehra rebuild put
        # Delhi's map under five of six beats because every line said "दिल्ली में".
        tired = [c for c in places if worn(c)] if [i for i in options if i is not None] else []
        places = [c for c in places if c not in tired]
        for c in places:
            options += [sight(c)] + ([] if route else [take(c)])
        options = [i for i in dict.fromkeys(options) if i is not None]
        about = k == 0 or not person or bool(people) or any(hindi.contains(say, w) for w in person)
        # The police photo is kept for the police beat that follows: the Tiger Shroff security Short's AICWA beat
        # took it and then stood with two police beats under one picture.
        police_next = k + 1 < len(beats) and any(w in beats[k + 1].get("say", "") for w in POLICE + ACCUSED)
        if options and k > 0 and options[0] in prev[-1:]:
            # The picture that just closed the last beat never opens this one: it moves to the cut.
            other = own(set(prev), beat.get("photo")) if about else scenery(places or scene, options[0])
            fresh = [i for i in options if i not in prev[-1:]] or [other]
            options = [i for i in fresh if i is not None] + [i for i in options if i not in fresh]
        if not options and not about:
            if police and any(w in say for w in ACCUSED) and not other_force(say, police):
                options.append(take(police))
            elif (i := scenery(scene, -1)) is not None and not stale(i):
                options.append(i)
            elif police and not other_force(say, police) and not police_next:
                options.append(take(police))
            elif i is not None:
                options.append(i)
        main = options[0] if options else own(set(prev), beat.get("photo"))
        if main is None:
            out.append([])
            continue
        rest = [i for i in options[1:] if i != main]
        cut = rest[0] if rest else (scenery(places or ([] if about else scene), main) if not people else None)
        if cut is not None and not places and stale(cut):
            cut = None
        if cut is None and about:
            cut = own({main})
        views = [main] + ([cut] if cut is not None and cut != main else [])
        for i in views:
            used[i] = used.get(i, 0) + 1
        out.append(views)
        prev = views
    return out


# --- Direction --------------------------------------------------------------------------------------------------

def fresh_first(rows: list[dict], recent: set[str] | None) -> list[dict]:
    """rows with the files the channel's last Shorts did not show first (a stable sort: the order is kept within
    each group). Seven Tiger Shroff Shorts in a day opened on the same portraits."""
    return sorted(rows, key=lambda r: r.get("file") in (recent or ()))


def _person_photos(c: dict, folder: Path, exclude: set[str], recent: set[str] | None = None) -> list[dict]:
    from . import writer

    rows = writer._own_photos(c["title"], c["ent"], folder, True, None, None, exclude, False, limit=8,
                              recent=recent)
    rows = [r for r in rows if not r.get("others")][:PERSON_PHOTOS] or rows[:1]
    return [r | {"who": c["hi"], "role": "person"} for r in rows]


def _cities_around(places: list[dict]) -> Iterator[dict]:
    """The town each place lies in (Wikidata "located in", with a population), whose police come next when the
    places have none: "जुहू" has no police page, and the Tiger Shroff security Short put his portrait over
    "आरोपियों से पूछताछ" instead of Mumbai Police (2026-10-21). Looked up only when asked for."""
    seen = {p.get("qid") for p in places}
    for c in places:
        up = next((v for v in (x.get("value") for x in wiki.claims(c["ent"], "P131")) if isinstance(v, str)), None)
        if not up or up in seen:
            continue
        seen.add(up)
        try:
            ent = wiki.entities([up]).get(up)
        except Exception:
            continue
        en = ((ent or {}).get("labels", {}).get("en") or {}).get("value")
        if ent and en and wiki.claims(ent, "P1082"):
            yield {"en": en, "hi": wiki.common_hindi(ent) or en, "qid": up, "ent": ent}


def _police_photos(city: dict, folder: Path, exclude: set[str], recent: set[str] | None = None) -> list[dict]:
    """Commons photos of the police of the story's Indian city (its main image first), with no featured face."""
    import cv2

    from . import faces, writer

    try:
        title = wiki.search(f"{city['en']} Police")
        qid = (wiki.page_info([title]).get(title) or {}).get("qid") if title else None
        ent = wiki.entities([qid]).get(qid) if qid else None
    except Exception:
        return []
    if not ent or "police" not in (title or "").lower() or INDIA not in {c["value"] for c in wiki.claims(ent, "P17")}:
        return []
    found = media.download(media.find(title, ent, limit=5, exclude=exclude), folder)
    out = []
    for r in fresh_first(media.as_dicts(found), recent):
        img = cv2.imread(r["path"])
        if img is None or writer.featured_face(img, faces.detect(img)):
            continue
        out.append(r | {"focus": None, "role": "police", "who": wiki.common_hindi(ent) or f"{city['hi']} पुलिस"})
    return out[:2]


def _sight_photos(c: dict, folder: Path, exclude: set[str], recent: set[str] | None = None,
                  keep: int = SIGHT_PHOTOS) -> list[dict]:
    """A landmark's (or a festival's) own Commons photos (its Wikidata image first), with no featured face, its name
    on screen."""
    import cv2

    from . import faces, writer

    found = media.download(media.find(c["title"], c["ent"], limit=keep + 2, exclude=exclude,
                                      search=c.get("kind") == "topic"), folder)
    out = []
    for r in fresh_first(media.as_dicts(found), recent):
        img = cv2.imread(r["path"])
        if img is None or writer.featured_face(img, faces.detect(img)):
            continue
        out.append(r | {"focus": None, "role": "place", "who": c["hi"]})
    return out[:keep]


def direct(draft: dict, photos: list[dict], subject_en: str, india: bool, folder: Path,
           exclude: set[str] | None = None, tribute: bool = False, recent: set[str] | None = None
           ) -> tuple[list[dict], list[list[int]], list[dict]]:
    """(photos with the cast's pictures added, [main, cut] indices per beat, the cast as {en, hi, kind, photos}).
    Network failures leave a beat on the story's own photos. A tribute adds only the people it names: a life's
    places are not today's news (Dhruv Rathee, 2026-10-17: seven of twelve frames were his school and birthplace).
    recent: Commons files the channel's last Shorts showed, used only when nothing fresh is left."""
    exclude = set(exclude or ()) | {p["file"] for p in photos if p.get("file")}
    photos = list(photos)
    subject = list(range(len(photos)))
    beats = draft.get("beats") or []
    try:
        cast = cast_for(draft, subject_en, india, places_too=not tribute)
    except Exception as exc:
        log.warning("visuals: cast lookup failed (%s)", exc)
        cast = []
    hi = next((n.get("hi") or "" for n in draft.get("names") or [] if n.get("en") == subject_en), "")
    surnames(cast, hi)

    def add(rows: list[dict]) -> list[int]:
        start = len(photos)
        photos.extend(rows)
        exclude.update(r["file"] for r in rows)
        return list(range(start, len(photos)))

    try:
        inside = within([c for c in cast if c["kind"] == "place"])
    except Exception as exc:
        log.warning("visuals: places not compared (%s)", exc)
        inside = {}
    holds = {o["en"] for o in inside.values()}
    for c in cast:
        c["photos"], c["near"], c["sight"] = [], [], []
        try:
            if c["kind"] == "person":
                c["photos"] = add(_person_photos(c, folder / f"cast-{c['qid']}", exclude, recent))
                continue
            if c["kind"] == "topic":
                rows = _sight_photos(c, folder / f"topic-{c['qid']}", exclude, recent, keep=TOPIC_PHOTOS)
                c["photos"] = add([r | {"role": "topic"} for r in rows])
                continue
            site = wiki.coords(c["ent"])
            if not site:
                continue
            if not is_region(c["ent"]) and not _population(c["ent"]):
                try:
                    c["sight"] = add(_sight_photos(c, folder / f"sight-{c['qid']}", exclude, recent))
                except Exception as exc:
                    log.warning("visuals: no photo of %s (%s)", c["en"], exc)
            if outer := inside.get(c["en"]):
                c["inside"] = outer["en"]
                c["photos"] = add([map_photo([(site, f"{c['hi']}, {outer['hi']}")], CITY_KM,
                                             folder / f"map-{c['qid']}-city.jpg", f"{c['en']} in {outer['en']}")])
                c["near"] = add([map_photo([(site, c["hi"])], STREET_KM, folder / f"map-{c['qid']}-street.jpg",
                                           f"{c['en']} up close")])
                continue
            span = REGION_KM if is_region(c["ent"]) else WIDE_KM
            c["photos"] = add([map_photo([(site, c["hi"])], span, folder / f"map-{c['qid']}-wide.jpg",
                                         f"where {c['en']} is")])
            times = sum(c in mentions(b.get("say", ""), [c]) for b in beats)
            if times > 1 and not is_region(c["ent"]) and c["en"] not in holds:
                c["near"] = add([map_photo([(site, c["hi"])], NEAR_KM, folder / f"map-{c['qid']}-near.jpg",
                                           f"{c['en']} up close")])
        except Exception as exc:
            log.warning("visuals: no picture for %s (%s)", c["en"], exc)
    for c in cast:
        spot = next((s for s in cast if s.get("inside") == c["en"] and s["photos"]), None)
        if spot and c["photos"]:
            c["near"] = spot["photos"][:1]  # a city named again shows where in it, not its centre
    places = [c for c in cast if c["kind"] == "place" and c["photos"]]
    extra = []
    for b in beats:
        named = [c for c in mentions(b.get("say", ""), places)][:2]
        pair = tuple(c["en"] for c in named)
        nested = any(c.get("inside") in pair for c in named)
        if len(named) == 2 and not nested and not any(tuple(e["pair"]) in (pair, pair[::-1]) for e in extra):
            try:
                a, z = named
                row = map_photo([(wiki.coords(a["ent"]), a["hi"]), (wiki.coords(z["ent"]), z["hi"])], 300.0,
                                folder / f"map-{a['qid']}-{z['qid']}.jpg", f"{a['en']} and {z['en']}")
                extra.append({"kind": "route", "pair": pair, "photos": add([row])})
            except Exception as exc:
                log.warning("visuals: no map of %s (%s)", pair, exc)
    said = " ".join(b.get("say", "") for b in beats)
    cities = [c for c in places if not is_region(c["ent"])]
    # The police the script names first: the probe's first city was a home district with no police page.
    named = {(n.get("en") or "").lower() for n in draft.get("names") or []}
    cities.sort(key=lambda c: f"{c['en']} police".lower() not in named and not hindi.contains(said, f"{c['hi']} पुलिस"))
    policed = india and any(w in said for w in POLICE)
    for city in chain(cities[:2], _cities_around(cities[:2])) if policed else []:
        try:
            if rows := _police_photos(city, folder / f"police-{city['qid']}", exclude, recent):
                extra.append({"kind": "police", "hi": city["hi"], "photos": add(rows)})
                break
        except Exception as exc:
            log.warning("visuals: no police photo for %s (%s)", city["en"], exc)
    first = beats[0].get("photo") if beats and beats[0].get("photo") in subject else None
    person = [subject_en, *hi.split()[:1], *hi.split()[-1:]] if subject_en and not tribute else None
    person = person and person + titles(beats, hi)
    views = assign(beats, subject, cast + extra, first, [w for w in person or [] if w] or None)
    log.info("visuals: %d pictures, %d distinct on screen, cast %s", len(photos),
             len({i for v in views for i in v}), [c["en"] for c in cast if c.get("photos")])
    told = [{"en": c["en"], "hi": c["hi"], "kind": c["kind"],
             "photos": c["photos"] + [i for i in c.get("near") or [] if i not in c["photos"]] + c.get("sight", []),
             **({"alias": c["alias"]} if c.get("alias") else {})} for c in cast]
    return photos, views, told


def distinct(shots: list[str]) -> int:
    from .spec import shot_photos

    return len({i for s in shots for i in shot_photos(s)})
