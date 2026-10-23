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

from . import config, hindi, media, net, things, wiki

log = logging.getLogger(__name__)

MIN_VISUALS = 3  # distinct pictures on screen; a lead story about a person may go with 2 (writer.LEAD_SCORE)
# States are counted apart from towns and landmarks, and a police force is no place: the Tiger Shroff probe's two
# home states, then "Kota Police", filled the places, and Kota's station, where all three were caught, had no picture.
MAX_PEOPLE, MAX_PLACES, MAX_REGIONS = 3, 7, 3
# Four, not two (Matlabnama audit R4, 2026-10-23: one picture, one beat): a person named in three beats needs three
# portraits, and two files are often one look (Modi's official portrait and its 3x4 crop, dry run 39860680187), so
# the replay's Tusk Shorts carded every Modi beat after the first. From the eight _own_photos already downloads.
PERSON_PHOTOS = 4
# A named landmark (a station, a hospital, a beach: a place with no population) shows its own Commons photo, then
# its map: the Tiger Shroff chase named five stations and showed only maps and portraits.
SIGHT_PHOTOS = 1
TOPIC_PHOTOS = 2
MAX_THINGS = things.MAX_THINGS
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
               "हुए", "हैं", "है", "था", "थी", "गया", "बाद", "तक", "पर", "मुताबिक", "अनुसार", "उधर", "इधर", "यहां",
               "यहाँ", "वहां", "वहाँ", "स्थानीय", "उन्हें", "इन्हें", "जिन्हें", "उसे", "इसे", "उनको", "साथ", "लिए", "दी", "दिया",
               "कहा", "बताया", "शहर", "मामले", "फायरिंग", "आरोपी", "आरोपियों", "घटना", "हमले"}
# "X की पुलिस" names another force only when X is a place ("राजस्थान की पुलिस"), never "साजिश की पुलिस जांच" (39333390694
# b6) or "आरोपी के पुलिस हिरासत में": the story's places (the cast's, the script's names) and these states and cities.
FORCE_PLACES = ("राजस्थान", "उत्तर प्रदेश", "मध्य प्रदेश", "बिहार", "गुजरात", "महाराष्ट्र", "पंजाब", "हरियाणा", "दिल्ली",
                "कर्नाटक", "केरल", "तमिलनाडु", "तेलंगाना", "आंध्र प्रदेश", "ओडिशा", "बंगाल", "असम", "झारखंड", "छत्तीसगढ़",
                "उत्तराखंड", "हिमाचल", "गोवा", "कश्मीर", "मुंबई", "मुम्बई", "कोलकाता", "चेन्नई", "बेंगलुरु", "हैदराबाद",
                "पुणे", "अहमदाबाद", "जयपुर", "लखनऊ", "पटना", "भोपाल", "कोटा", "सूरत", "नोएडा", "गुरुग्राम", "चंडीगढ़")
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


def names_place(title: str, ent: dict, en: str) -> bool:
    """The hit is the place the script names: its title, English label or an English alias holds the name as whole
    words ("Kota, Rajasthan" for Kota, Mumbai's alias "Bombay"), not just the story city a "<name> <city>" search
    fell back to."""
    want = re.escape(en.strip().lower())
    names = [title, ((ent.get("labels") or {}).get("en") or {}).get("value", "")] \
        + [a.get("value", "") for a in (ent.get("aliases") or {}).get("en", [])]
    return any(re.search(rf"(?<!\w){want}(?!\w)", n.lower()) for n in names if n)


def _hit(q: str, en: str, india: bool) -> tuple[str, str, dict] | None:
    title = wiki.search(q)
    qid = (wiki.page_info([title]).get(title) or {}).get("qid") if title else None
    ent = wiki.entities([qid]).get(qid) if qid else None
    if not ent or wiki.DISAMBIGUATION in kinds(ent):
        return None
    if wiki.HUMAN in kinds(ent):
        from . import stories

        return (qid, title, ent) if stories.plain_title(title).lower() == en.lower() else None
    if media.place_like(ent) and not kinds(ent) & COUNTRY_KINDS:
        if india and INDIA not in {c["value"] for c in wiki.claims(ent, "P17")}:
            return None
        if not names_place(title, ent, en):
            return None  # "Belonging Delhi" (a book's title next to the story city) found Delhi (39747949900)
        if title.lower().startswith(en.lower() + " "):
            return None  # "Ramlila" (the play) found "Ramlila Maidan", a ground across Delhi from the event
        return qid, title, ent
    return None


# The names resolve could not read (a network or API error), as against found nothing: an unread name is no faceless
# person (writer.faceless, cast_for's fates; review round 2).
UNREAD: set[str] = set()


def resolve(en: str, india: bool, near: dict | None = None) -> tuple[str, str, dict] | None:
    """(QID, title, item) of a person or place the script names: Wikipedia's first hit for the name, or for
    "<name>, India" when that is a disambiguation page or the place is abroad in an Indian story.

    near: where the story is ({"en": its city, "at": (lat, lon)}, writer.story_anchor). A same-name place is then
    also looked up as "<name> <city>" and the hit nearest the story wins (SYNC-AUDIT 4.0): "जंतर मंतर", a Delhi
    protest, resolved to Jaipur's Jantar Mantar and showed its map and a 1928 photo (39708703684). No fixed distance:
    Jaipur is about 240 km from Delhi."""
    from .stories import km_between

    city = (near or {}).get("en") or ""
    UNREAD.discard(en)
    queries = [en] + ([f"{en} {city}"] if city and city.lower() not in en.lower() else []) \
        + ([f"{en}, India"] if india else [])
    places: list[tuple[str, str, dict]] = []
    for q in queries:
        if places and q == f"{en}, India":
            break
        try:
            hit = _hit(q, en, india)
        except Exception as exc:
            log.info("visuals: %s not resolved (%s)", q, exc)
            if not places:
                UNREAD.add(en)
            break
        if not hit:
            continue
        if wiki.HUMAN in kinds(hit[2]):
            return hit
        if all(h[0] != hit[0] for h in places):
            places.append(hit)
        if not city:
            break
    if not places:
        return None
    at = (near or {}).get("at")
    if at:
        places.sort(key=lambda h: km_between(c, at) if (c := wiki.coords(h[2])) else math.inf)
    return places[0]


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
    aside ("मुंबई" for "मुम्बई"). Inside a longer name another member's name does not count: "अंधेरी स्टेशन" names
    the station (its own landmark, cast_for), not Andheri."""
    spans = []
    for c in cast:
        at = [(a, a + len(w)) for w in [c.get("hi") or "", *(c.get("alias") or [])] if w for a in _finds(say, w)]
        en = c.get("en") or ""
        at += [(m.start(), m.end()) for m in re.finditer(rf"\b{re.escape(en)}\b", say, re.I)] if en else []
        spans.append((c, at))
    found = []
    for c, at in spans:
        free = [a for a, z in at if not any(o is not c and a2 <= a < z2 and z2 - a2 > z - a
                                            for o, other in spans for a2, z2 in other)]
        if free:
            found.append((min(free), c))
    return sorted(found, key=lambda x: x[0])


def _finds(say: str, word: str) -> list[int]:
    """Every place in say where word starts as whole words (hindi.find, repeated)."""
    out, pos = [], 0
    while (a := hindi.find(say[pos:], word)) >= 0:
        out.append(pos + a)
        m = re.compile(r"\s").search(say, pos + a)
        if not m:
            break
        pos = m.end()
    return out


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


def card_over(card: dict, shown: list[int], cast: list[dict], photos: list[dict] | None = None,
              spellings=(), plate: str = "", others=()) -> dict:
    """The card with only what its picture shows (SYNC-AUDIT 4.1 step 3): a big line naming a cast member (or the
    subject, by spellings) that no view in shown depicts goes, and so does a small line that is only such a name; the
    other line then stands alone. "वनतारा केंद्र" sat over the Jamnagar refinery (39714003987) and "संजय राउत" over
    Tiger Shroff (39546660530). A place card sits only over its place's own map or photo: the Modi rebuild put
    "उत्सव मैदान" over Delhi's map. Over another place it names the place on screen; over no place it goes. A text
    card (plate match.CARD) is the words alone and is kept as written. others: the script's names (match.others_of),
    never on screen: "संजय राउत" goes even when his lookup failed and he is not in the cast."""
    from . import config, match

    if not card or plate == match.CARD:
        return card
    if config.MATCHER == "legacy":  # the rollback: main's card_over, the place check alone
        return place_over(card, shown, cast)
    if photos is not None:
        on = match.card_on(shown, photos, cast)
    else:
        on = {match.key(c) for c in cast if set(c.get("photos") or []) & set(shown)}
        on |= {match.SUBJECT} if any(not any(i in (c.get("photos") or []) for c in cast) for i in shown) else set()
    big, small = card.get("big", ""), card.get("small", "")
    if match.card_keys(big, "", cast, spellings, others) - on:
        big = ""
    if small and match.card_keys("", small, cast, spellings, others) - on:
        small = ""
    if not big:
        big, small = small, ""
    if not big:
        return {}
    return place_over({**card, "big": big, "small": small}, shown, cast)


def place_over(card: dict, shown: list[int], cast: list[dict]) -> dict:
    """A place card over its own place's picture, else renamed for the place on screen, else gone (card_over)."""
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
    under it instead. And a FIGURE's own title the beats say (things.roles)."""
    first = hindi.norm((subject_hi.split() or [""])[0])
    if not first:
        return []
    seen: Counter = Counter()
    for b in beats:
        words = [hindi.norm(w) for w in re.findall(r"[\u0900-\u097F]+", b.get("say") or "")]
        seen.update({a for a, z in zip(words, words[1:]) if z == first and len(a) >= 3
                     and a not in hindi.FUNCTION_WORDS and a not in NOT_A_FORCE})
    said = " ".join(b.get("say") or "" for b in beats)
    # The subject's own Indian title said alone ("गृह मंत्री ने ...": Amit Shah, things.ROLES), once is enough.
    out = [w for w, n in seen.items() if n >= TITLE_BEATS]
    return out + [r for r in things.roles(subject_hi) if _finds(said, r) and hindi.norm(r) not in map(hindi.norm, out)]


def _subject(en: str, subject_en: str) -> bool:
    # A story about a place passes "" here: "" is in every name, and the Modi Dussehra Short (2026-10-21) lost
    # Narendra Modi from its pictures that way.
    a, b = en.lower().strip(), subject_en.lower().strip()
    return bool(a and b) and (a == b or a in b or b in a)


# A place word after a place the script names is a landmark of its own: "अंधेरी स्टेशन" showed the Andheri
# flyover, a photo of Andheri (SYNC-AUDIT 4.0). One Wikipedia search for "<en> <word>" finds it.
SUB_PLACES = {"स्टेशन": "railway station", "अस्पताल": "hospital", "कोर्ट": "court", "जंक्शन": "junction"}
# Wikidata P31 kinds that are parts of a town, whose Commons photos are of its landmarks, not of it: "Juhu" showed
# ISKCON temple, Juhu.
LOCALITY = {"Q188509", "Q123705", "Q3257686"}  # suburb, neighbourhood, locality


def sub_place(c: dict, beats: list[dict], india: bool) -> dict | None:
    """The landmark a beat names as "<place> स्टेशन" (SUB_PLACES), resolved as its own cast member, or None."""
    said = " ".join(b.get("say") or "" for b in beats)
    for word, en_word in SUB_PLACES.items():
        hi = f"{c['hi']} {word}"
        if word in c["hi"].split() or en_word.split()[-1] in c["en"].lower() or not hindi.contains(said, hi):
            continue
        try:
            hit = _hit(f"{c['en']} {en_word}", c["en"], india)
        except Exception as exc:
            log.info("visuals: %s not resolved (%s)", hi, exc)
            continue
        if hit and hit[0] != c["qid"] and en_word.split()[-1] in hit[1].lower() and wiki.HUMAN not in kinds(hit[2]):
            return {"en": hit[1], "hi": hi, "kind": "place", "qid": hit[0], "title": hit[1], "ent": hit[2]}
    return None


def cast_for(draft: dict, subject_en: str, india: bool, places_too: bool = True, near: dict | None = None,
             resolver=None, thing_resolver=None, thing_lookup=None, fates: dict | None = None) -> list[dict]:
    """The people, places and things the script names besides its subject, resolved: [{en, hi, kind, qid, title,
    ent}] (a thing also carries alias, its inflected forms, and files, an editor's photos). near: where the story is
    (resolve); resolver, thing_resolver, thing_lookup: cached lookups (showable). A thing is a name of the script whose
    article is one (things.resolve_thing), or a LEXICON noun a beat says ("तिरंगे"), which also takes the place of a
    script name it spells (a map of "संसद" is no picture of Parliament).

    fates: filled with {hindi.norm(hi): what the lookup of each script name said}, for writer.faceless: "unfound"
    (looked up, nothing found), "unread" (the lookup failed), "cap" (a person past MAX_PEOPLE), "cast" (in the cast),
    "other" (a place, firm or work: no face to want). Only an "unfound" name may make a Short faceless (review round
    2: Air India, Delhi Metro and Bharat Mandapam read as faceless people)."""
    fates = {} if fates is None else fates
    resolver = resolver or resolve
    thing_resolver = thing_resolver or things.resolve_thing
    thing_lookup = thing_lookup or things.lookup
    out, people, places, regions, topics, found_things = [], 0, 0, 0, 0, 0
    for n in draft.get("names") or []:
        en, hi = (n.get("en") or "").strip(), (n.get("hi") or "").strip()
        if not en or not hi or _subject(en, subject_en) or any(c["en"] == en for c in out) \
                or re.search(r"\bpolice\b", en, re.I) or any(w in hi for w in POLICE):
            continue
        said = any(hindi.contains(b.get("say", ""), hi) or hi in b.get("say", "") for b in draft.get("beats") or [])
        if not said:
            continue
        found = resolver(en, india, **({"near": near} if near else {}))
        fate = hindi.norm(hi)
        fates[fate] = "other" if found else "unread" if en in UNREAD else "unfound"
        if found and topic_like(found[2]):
            found = None  # Wikipedia's search returns the Ramlila article for "Ramlila, India" on some calls
        if not found and places_too and topics < MAX_TOPICS and (topic := resolve_topic(en)):
            fates[fate] = "other"
            topics += 1
            out.append({"en": en, "hi": hi, "kind": "topic", "qid": topic[0], "title": topic[1],
                        "ent": topic[2], "alias": [hi + "ओं"]})  # "देश भर में राम लीलाओं का मंचन"
            continue
        if not found and found_things < MAX_THINGS and config.MATCHER != "legacy" and (thing := thing_resolver(en)):
            fates[fate] = "other"
            found_things += 1
            out.append({"en": en, "hi": hi, "kind": "thing", "qid": thing[0], "title": thing[1], "ent": thing[2]})
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
            fates[fate] = "cap" if kind == "person" else "other"
            continue
        fates[fate] = "cast" if kind == "person" else "other"
        people += kind == "person"
        regions += region
        places += kind == "place" and not region
        out.append({"en": en, "hi": hi, "kind": kind, "qid": qid, "title": title, "ent": ent})
        if kind == "place" and not region and places < MAX_PLACES and (sub := sub_place(out[-1], draft.get("beats")
                                                                                         or [], india)):
            if not any(c["qid"] == sub["qid"] for c in out):
                places += 1
                out.append(sub)
    # A public figure every beat may name, left out of the script's names (things.FIGURES), is still a person to show.
    for f in [] if config.MATCHER == "legacy" else things.figures_said(draft.get("beats") or []):
        if people >= MAX_PEOPLE or _subject(f["en"], subject_en) or any(c["en"] == f["en"] for c in out):
            continue
        if not (found := resolver(f["en"], india, **({"near": near} if near else {}))) \
                or wiki.HUMAN not in kinds(found[2]) or any(c.get("qid") == found[0] for c in out):
            continue
        people += 1
        out.append({"en": f["en"], "hi": f["hi"], "kind": "person", "qid": found[0], "title": found[1],
                    "ent": found[2], "alias": f["alias"]})
    # The rollback (DESK_MATCHER=legacy) shows people, places and topics only (assign_legacy): a lexicon noun would
    # take a landmark's place and then never be on screen (review round 1: "लाल किले" lost the Red Fort's photo).
    for e in [] if config.MATCHER == "legacy" else things.lexicon_hits(draft.get("beats") or [], india):
        forms = {hindi.norm(w) for w in [e["hi"], *e["alias"]]}
        if any(c["kind"] == "thing" and (c["en"] == e["en"] or hindi.norm(c["hi"]) in forms) for c in out):
            continue
        # The script's own vehicle ("INS Vikrant") takes a stand-in's words ("इस जहाज़ पर"): its own photo, never a
        # container ship's, under them (Matlabnama audit R1, actual first).
        if e.get("stand_in") and e.get("cls") and (own := next(
                (c for c in out if c["kind"] == "thing" and re.search(e["cls"], _description(c.get("ent")), re.I)),
                None)):
            own["alias"] = list(dict.fromkeys([*(own.get("alias") or []), e["hi"], *e["alias"]]))
            continue
        if sum(c["kind"] == "thing" for c in out) >= MAX_THINGS:
            break
        # A stand-in with an editor's photos needs no lookup: its Wikipedia article is the kind, not a picture.
        hit = e | {"qid": "", "ent": {}} if e.get("stand_in") and e["files"] else thing_lookup(e)
        if hit is None and not e["files"]:
            continue
        if e.get("stand_in") and hit:
            hit = hit | {"stand_in": True}
        out = [c for c in out if not (c["kind"] in ("place", "topic") and hindi.norm(c["hi"]) in forms)]
        out.append(hit or e | {"qid": "", "ent": {}})
    return out


def _description(ent: dict | None) -> str:
    return (((ent or {}).get("descriptions") or {}).get("en") or {}).get("value", "")


# --- Assignment -------------------------------------------------------------------------------------------------

def other_force(say: str, police: dict, places=()) -> bool:
    """The beat names some other police force ("राजस्थान पुलिस ने बताया", "राजस्थान की पुलिस" when the photo is
    Mumbai Police). "X की/के पुलिस" counts only when X is a place (places, FORCE_PLACES). A police row with no city
    (writer.anchorless before the city is known) is no force to differ from."""
    own = police.get("hi") or ""
    if not own:
        return False
    for m in re.finditer(r"(\S+)\s+पुलिस", say):
        word = m.group(1).strip(",.;:।'\"()")
        if word and word not in NOT_A_FORCE and not hindi.contains(own, word):
            return True
    for m in re.finditer(r"(?:की|के)\s+पुलिस", say):
        before = say[:m.start()].rstrip()
        place = next((w for w in [*places, *FORCE_PLACES] if w and hindi.norm(before).endswith(hindi.norm(w))
                      and hindi.find(before, w.split()[-1]) >= 0), "")
        if place and not hindi.contains(own, place.split()[-1]):
            return True
    return False


def assign_legacy(beats: list[dict], subject: list[int], cast: list[dict], first: int | None = None,
                  person: list[str] | None = None) -> list[list[int]]:
    """[main, cut] photo indices for each beat ([main] when there is no second view): the old name-then-fill
    assignment, used only under config.MATCHER == "legacy" (SYNC-AUDIT 4.1 step 3). Its fallbacks (scenery, the
    story's own photos, the police for an unnamed beat) put a picture under 98 of 145 audited beats that the voice
    was not talking about; the anchored path (match.plan) never fills.

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


# A cast person's photo must be of them at an adult age and at no other event, their face big enough to be them:
# the Rubio Short put Mukesh Ambani at the 2023 NMACC gala under "welcomed him at Jamnagar" (39714003987 p9).
FACE_SHARE = 0.10


def has_p18(ent: dict) -> bool:
    """Whether a Wikidata item has an image (P18) that is a photo."""
    return any(isinstance(v["value"], str) and not media.NOT_PHOTO.search(v["value"]) for v in wiki.claims(ent, "P18"))


def _person_photos(c: dict, folder: Path, exclude: set[str], recent: set[str] | None = None,
                   year: int | None = None) -> list[dict]:
    """A cast person's own portraits, vetted (media.era_reject, media.event_kind, FACE_SHARE): [] when none passes,
    so their beat gets a card, never someone else's picture."""
    from . import writer

    rows = writer._own_photos(c["title"], c["ent"], folder, True, None, None, exclude, False, limit=8,
                              recent=recent)
    # Nothing downloaded though Wikidata has their photo: a failed download, retried next run (writer.faceless).
    c["miss"] = not rows and has_p18(c.get("ent") or {})
    year = year or writer._today_ist().year
    born = next((d.year for d in (wiki.wd_time(v["value"]) for v in wiki.claims(c["ent"], "P569")) if d), None)
    rows = [r for r in rows if not media.era_reject(r, year, born, "person", rows) and not media.event_kind(r)
            and (r.get("face") is None or r["face"] >= FACE_SHARE)]
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

    if c.get("kind") != "topic" and kinds(c["ent"]) & LOCALITY:
        return []  # a part of a town is shown on its map, never by one of its landmarks (LOCALITY)
    found = media.download(media.find(c["title"], c["ent"], limit=keep + 2, exclude=exclude,
                                      search=c.get("kind") == "topic"), folder)
    out = []
    for r in fresh_first(media.as_dicts(found), recent):
        if c.get("kind") != "topic" and media.not_itself(r, c["en"]):
            continue  # "Andheri flyover" is not Andheri, nor its station
        img = cv2.imread(r["path"])
        if img is None or writer.featured_face(img, faces.detect(img)):
            continue
        out.append(r | {"focus": None, "role": "place", "who": c["hi"]})
    return out[:keep]


LOOK_MATCHES = 100  # ORB matches (Hamming < LOOK_DISTANCE) that make two photos one picture: a crop, a re-encode
LOOK_DISTANCE = 40
LOOK_SIDE = 512


def _orb(path: str):
    import cv2

    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE) if path else None
    if img is None:
        return None
    scale = LOOK_SIDE / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.ORB_create(nfeatures=1500).detectAndCompute(img, None)[1]


def same_look(a, b) -> bool:
    """Whether two ORB descriptor sets are one picture: "Shri Narendra Modi ... (3x4 cropped)" is a crop of the
    official portrait (693 matches; two Amit Shah files 185; different portraits of one person 38 at most)."""
    import cv2

    if a is None or b is None or not len(a) or not len(b):
        return False
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(a, b)
    return sum(m.distance < LOOK_DISTANCE for m in pairs) >= LOOK_MATCHES


def looks(photos: list[dict]) -> None:
    """Stamp each photo that is one picture with another of the same person or place ("look": the first's file):
    match.held_key counts them as one, so the ceilings and the rotation see it. Dry run 39845458169 held Modi's one
    official portrait, as two files, ~30 of 33 s. Maps never; a photo with no file on disk never."""
    def owner(p: dict):
        return (p.get("role") or "", p.get("who") or "", tuple(p.get("depicts") or ()))

    by: dict = {}
    for i, p in enumerate(photos):
        p.pop("look", None)
        if p.get("role") != "map" and p.get("path") and p.get("file"):
            by.setdefault(owner(p), []).append(i)
    for idx in by.values():
        if len(idx) < 2:
            continue
        try:
            desc = {i: _orb(photos[i]["path"]) for i in idx}
        except Exception as exc:  # a broken file is its own picture
            log.warning("visuals: no look check (%s)", exc)
            continue
        for n, i in enumerate(idx):
            if photos[i].get("look"):
                continue
            for j in idx[n + 1:]:
                if not photos[j].get("look") and same_look(desc[i], desc[j]):
                    photos[i]["look"] = photos[j]["look"] = photos[i]["file"]


# A beat that tells a journey between the two places it names (R3): "दिल्ली से लंदन जा रही फ्लाइट", "तुस्क नई दिल्ली
# पहुंचे", "... के लिए रवाना हुए". Only with two places in the one beat, so "दिल्ली और मुंबई में बारिश" is no journey.
TRAVEL = re.compile(r"(?<![\u0900-\u097F])(?:जा रह[ीेा]|आ रह[ीेा]|रवाना|उड़ान|उड़ानें|फ्लाइट|फ़्लाइट|यात्रा|दौरे|दौरा|"
                    r"पहुंच\w*|पहुँच\w*|लौट\w*|डायवर्ट|तक)(?![\u0900-\u097F])")


def map_scope(beats: list[dict], cast: list[dict], photos: list[dict], near: dict | None = None) -> None:
    """Stamps which maps may be shown, in place (Matlabnama audit R3, the owner's rule of 2026-10-23: "Map should be
    shown at the time of some story where the incident happen, if you are covering any travel story then both
    destination and origine"). A journey (a beat naming two places with a TRAVEL word, and their route map made):
    the route map is stamped "travel" and every other map "away". Otherwise only the maps of where it happened stay:
    the story's dateline city (near) when the cast has it, a spot in it the script names first, else the place the
    beats name most (first said on a tie); every other map, and every route, is stamped "away" with why.
    match.vet_photo reads the stamp, so plan never shows such a map and the gate refuses one shown."""
    from . import match

    places = [c for c in cast if c.get("kind") == "place"]
    maps = [i for i, p in enumerate(photos) if is_map(p)]
    keys = {i: match.depicts(i, photos[i], cast) for i in maps}
    for b in beats:
        say = b.get("say") or ""
        named = [match.key(c) for c in mentions(say, places)]
        if len(set(named)) >= 2 and TRAVEL.search(say):
            trip = next((i for i in maps if len(keys[i]) == 2 and keys[i] == set(named[:2])), None)
            if trip is not None:
                photos[trip]["travel"] = True
                for i in maps:
                    if i != trip:
                        photos[i]["away"] = "a one-ended map in a journey's story (its route map shows both ends)"
                return
    home = None
    if near and near.get("en"):
        want = near["en"].lower()
        home = next((c for c in places if (c.get("en") or "").lower() == want), None) or \
            next((c for c in places if want in (c.get("en") or "").lower() or (c.get("en") or "x").lower() in want),
                 None)
    said = [(n, a, c) for n, b in enumerate(beats) for a, c in located(b.get("say") or "", places)]
    if home is not None:
        spot = next((c for _, _, c in said if c.get("inside") == home.get("en")), None)
        home = spot or home
    elif said:
        times = {}
        for n, a, c in said:
            times.setdefault(match.key(c), [0, (n, a), c])[0] += 1
        home = min(times.values(), key=lambda t: (-t[0], t[1]))[2]
    mine = match.key(home) if home is not None else None
    for i in maps:
        if keys[i] != {mine}:
            who = photos[i].get("who") or photos[i].get("file") or ""
            photos[i]["away"] = f"a map of {who}, not where the story happened"


def direct(draft: dict, photos: list[dict], subject_en: str, india: bool, folder: Path,
           exclude: set[str] | None = None, tribute: bool = False, recent: set[str] | None = None,
           kind: str = "", year: int | None = None, born: int | None = None, incident: bool = False,
           near: dict | None = None, subject_hi: str = "", looked: dict | None = None
           ) -> tuple[list[dict], list[dict], list[dict]]:
    """(photos with the cast's pictures added, one row per beat {views, cut_word, plate, card_view} (match.plan),
    the cast as {en, hi, kind, photos}). Network failures leave a beat with what it could find, else a card. A
    tribute adds only the people it names: a life's places are not today's news (Dhruv Rathee, 2026-10-17: seven of
    twelve frames were his school and birthplace). recent: Commons files the channel's last Shorts showed, used only
    when nothing fresh is left; year, born, incident: for vetting (match.vet_photo); near: the story's place
    (resolve); subject_hi: the subject's Hindi name, for a place's story too; looked: filled with cast_for's fates
    of the script's names (writer.faceless).

    Every picture is stamped with what it depicts and why it may not be shown ("vet"), then config.MATCHER picks
    the views: "anchored" (match.plan) or "legacy" (assign_legacy)."""
    from . import config, match, writer

    exclude = set(exclude or ()) | {p["file"] for p in photos if p.get("file")}
    photos = [dict(p) for p in photos]
    subject = list(range(len(photos)))
    beats = draft.get("beats") or []
    year = year or writer._today_ist().year
    legacy = config.MATCHER == "legacy"
    try:
        cast = cast_for(draft, subject_en, india, places_too=not tribute, **({"near": near} if near else {}),
                        **({"fates": looked} if looked is not None else {}))
    except Exception as exc:
        log.warning("visuals: cast lookup failed (%s)", exc)
        cast = []
    hi = subject_hi or next((n.get("hi") or "" for n in draft.get("names") or [] if n.get("en") == subject_en), "")
    if subject_en and not subject_hi:
        subject_hi = hi
    surnames(cast, hi if subject_en else "")

    def add(rows: list[dict], *keys: str) -> list[int]:
        start = len(photos)
        photos.extend(r | {"depicts": list(keys)} for r in rows)
        exclude.update(r["file"] for r in rows if r.get("file"))
        return list(range(start, len(photos)))

    for p in photos:  # a context fill is the story's, never the subject's (the JNU fills stood as the subject)
        p["depicts"] = [match.CONTEXT if match.fill(p) else match.SUBJECT]
    try:
        inside = within([c for c in cast if c["kind"] == "place"])
    except Exception as exc:
        log.warning("visuals: places not compared (%s)", exc)
        inside = {}
    holds = {o["en"] for o in inside.values()}
    for c in cast:
        c["photos"], c["near"], c["sight"] = [], [], []
        me = match.key(c)
        try:
            if c["kind"] == "person":
                c["photos"] = add(_person_photos(c, folder / f"cast-{c['qid']}", exclude, recent, year), me)
                continue
            if c["kind"] == "topic":
                rows = _sight_photos(c, folder / f"topic-{c['qid']}", exclude, recent, keep=TOPIC_PHOTOS)
                c["photos"] = add([r | {"role": "topic"} for r in rows], me)
                continue
            if c["kind"] == "thing":
                slug = c.get("qid") or re.sub(r"\W+", "-", c["en"]).strip("-").lower()
                c["photos"] = add(things.photos(c, folder / f"thing-{slug}", exclude, recent), me)
                continue
            site = wiki.coords(c["ent"])
            if not site:
                continue
            if not is_region(c["ent"]) and not _population(c["ent"]):
                try:
                    c["sight"] = add(_sight_photos(c, folder / f"sight-{c['qid']}", exclude, recent), me)
                except Exception as exc:
                    log.warning("visuals: no photo of %s (%s)", c["en"], exc)
            if outer := inside.get(c["en"]):
                c["inside"] = outer["en"]
                c["photos"] = add([map_photo([(site, f"{c['hi']}, {outer['hi']}")], CITY_KM,
                                             folder / f"map-{c['qid']}-city.jpg", f"{c['en']} in {outer['en']}")], me)
                c["near"] = add([map_photo([(site, c["hi"])], STREET_KM, folder / f"map-{c['qid']}-street.jpg",
                                           f"{c['en']} up close")], me)
                continue
            span = REGION_KM if is_region(c["ent"]) else WIDE_KM
            c["photos"] = add([map_photo([(site, c["hi"])], span, folder / f"map-{c['qid']}-wide.jpg",
                                         f"where {c['en']} is")], me)
            times = sum(c in mentions(b.get("say", ""), [c]) for b in beats)
            # A city's own close map, also when a spot in it is named: the spot's map is the spot's, never the
            # city's (the Juhu map stood under "मुम्बई", 2026-10-20; SYNC-AUDIT 4.1 step 3).
            if times > 1 and not is_region(c["ent"]) and (not legacy or c["en"] not in holds):
                c["near"] = add([map_photo([(site, c["hi"])], NEAR_KM, folder / f"map-{c['qid']}-near.jpg",
                                           f"{c['en']} up close")], me)
        except Exception as exc:
            log.warning("visuals: no picture for %s (%s)", c["en"], exc)
            c["miss"] = True  # a network failure, not a subject with no photo: retried (writer.faceless)
    if legacy:
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
                extra.append({"kind": "route", "pair": pair, "photos": add([row], match.key(a), match.key(z))})
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
                extra.append({"kind": "police", "hi": city["hi"], "photos": add(rows, match.POLICE)})
                break
        except Exception as exc:
            log.warning("visuals: no police photo for %s (%s)", city["en"], exc)
    person = bool(subject_en) and not tribute
    if not legacy:  # the rollback (DESK_MATCHER=legacy) as main: no look stamps (review round 2)
        looks(photos)
        map_scope(beats, cast, photos, near)
    for i, p in enumerate(photos):
        why = match.vet_photo(i, photos, cast, year, bool(subject_en), incident, born)
        if why:
            p["vet"] = why
        else:
            p.pop("vet", None)
    # A place's own photo (its sight) before its maps: a picture first, a map only when there is none.
    # The rollback keeps main's order (maps, then the sight).
    told = [{"en": c["en"], "hi": c["hi"], "kind": c["kind"],
             "photos": c["photos"] + [i for i in c.get("near") or [] if i not in c["photos"]] + c.get("sight", [])
             if legacy else c.get("sight", []) + c["photos"] + [i for i in c.get("near") or [] if i not in c["photos"]],
             **({"alias": c["alias"]} if c.get("alias") else {}), **({"inside": c["inside"]} if c.get("inside")
                                                                      else {}),
             **({"miss": True} if c.get("miss") else {})} for c in cast]
    if legacy:
        first = beats[0].get("photo") if beats and beats[0].get("photo") in subject else None
        words = [subject_en, *hi.split()[:1], *hi.split()[-1:]] if person else None
        words = words and words + titles(beats, hi)
        views = assign_legacy(beats, subject, cast + extra, first, [w for w in words or [] if w] or None)
        rows = [{"views": v, "cut_word": "", "plate": "", "card_view": 0} for v in views]
    else:
        name = subject_hi.strip()
        parts = name.split()
        spell = [name, *parts[:1], *parts[-1:], *titles(beats, name)] if subject_en else [name]
        spell = [w for w in dict.fromkeys(spell) if len(hindi.norm(w)) >= 3]
        # The story's best photo opens beat 1 (the writer's pick), then the rest in their ranked order.
        lead = beats[0].get("photo") if beats else None
        ranked = ([lead] if lead in subject else []) + [i for i in subject if i != lead]
        cards = [{"say": b.get("say", ""), "card": {"big": b.get("caption") or "", "small": b.get("label") or ""}}
                 for b in beats]
        rows = match.plan(cards, photos, told + extra, ranked, kind, spell, person, draft.get("names") or [])
    log.info("visuals: %d pictures, %d distinct on screen, %d cards, cast %s", len(photos),
             len({i for r in rows if r["plate"] != match.CARD for i in r["views"]}),
             sum(r["plate"] == match.CARD for r in rows), [c["en"] for c in cast if c.get("photos")])
    return photos, rows, told


def showable(draft: dict, subject_en: str, india: bool, cache: dict | None = None, near: dict | None = None,
             tribute: bool = False) -> list[str]:
    """The Hindi names the script lists that a vetted picture could show (SYNC-AUDIT 4.1 step 4, the writer's
    SHOWABLE list): a person with a Wikidata image (P18), a place with coordinates, a festival or rite, a thing with
    a photo (things: "तिरंगा"), and the police of an Indian city it names. Wikidata only, no Commons download; cache
    keeps the lookups across drafts."""
    return list(dict.fromkeys(r["hi"] for r in showable_rows(draft, subject_en, india, cache, near, tribute)))


def showable_rows(draft: dict, subject_en: str, india: bool, cache: dict | None = None, near: dict | None = None,
                  tribute: bool = False) -> list[dict]:
    """showable as cast rows {hi, kind, alias, map_only}: map_only for a town or region, which direct shows by its
    map alone (no sight photo: it has people or a capital), so a beat naming only such places is a map beat, and a
    Short may have one (match.MAX_MAP_VIEWS)."""
    cache = {} if cache is None else cache

    def cached(en, india_, **kw):
        k = (en, india_, (kw.get("near") or {}).get("en"))
        if k not in cache:
            cache[k] = resolve(en, india_, **kw)
        return cache[k]

    def thing(en):
        if ("thing", en) not in cache:
            cache[("thing", en)] = things.resolve_thing(en)
        return cache[("thing", en)]

    def entry(e):
        if ("lexicon", e["en"]) not in cache:
            cache[("lexicon", e["en"])] = things.lookup(e)
        return cache[("lexicon", e["en"])]

    try:
        cast = cast_for(draft, subject_en, india, places_too=not tribute, near=near, resolver=cached,
                        thing_resolver=thing, thing_lookup=entry)
    except Exception as exc:
        log.info("visuals: showable not looked up (%s)", exc)
        return []
    out = [{"hi": c["hi"], "kind": c["kind"], "alias": list(c.get("alias") or []),
            "map_only": c["kind"] == "place" and (is_region(c["ent"]) or bool(_population(c["ent"])))}
           for c in cast if c["kind"] == "topic" or c["kind"] == "person" and wiki.claims(c["ent"], "P18")
           or c["kind"] == "place" and wiki.coords(c["ent"]) or c["kind"] == "thing" and things.has_picture(c)]
    if india and any(c["kind"] == "place" and not is_region(c["ent"]) for c in cast):
        out.append({"hi": "पुलिस", "kind": "police", "alias": [], "map_only": False})
    return out


def distinct(shots: list[str]) -> int:
    from .spec import shot_photos

    return len({i for s in shots for i in shot_photos(s)})
