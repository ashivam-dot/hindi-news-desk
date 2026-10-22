"""Things a beat names get their own real picture: the tricolour, Parliament, the Supreme Court, a ship, an animal.

Owner, 2026-10-22, on CAPraPdXvns (Raihan Vadra's exhibition): "where is tiranga picture if you are saying about
tiranga". The beat "रेहान ने तिरंगे की तस्वीरें हटाने से साफ मना किया" stood over a map of New Delhi: only people and
places had pictures, so a thing the voice named was never on screen. Here a thing is a cast member (kind "thing")
like a place: a small hand lexicon of everyday Hindi visual nouns, matched as whole words in every inflected form the
lexicon lists (hindi.find, visuals.located), and the script's own English names when their Wikipedia article is a
thing (a ship, an aircraft, a species, a dish, a medal, a monument). Its pictures are free Commons photos only:
Wikidata's image (P18) and the item's Commons category through media's licence, size and credit checks, or files an
editor chose (media.picks) where P18 is a drawing (the Flag of India's is an SVG, and NOT_PHOTO bans "flag").

Never a work (a film, a book cover, a poster, an album, a painting), a logo or trademark (a company, a party, an
app), a social-media screenshot, or a photo with a featured face (someone a beat does not name). A beat shows a
thing only when it names it (match.problems: shown is said).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from . import hindi, media, wiki

log = logging.getLogger(__name__)

THING_PHOTOS = 2
MAX_THINGS = 3
# Hindi forms (whole words; every inflection listed, hindi.find matches whole words only) -> the English Wikipedia
# article, and for an item whose Wikidata image is a drawing, Commons photos checked by eye (2026-10-22, licences
# re-read at runtime by media.picks). india: shown only in an Indian story ("संसद" in a story about Britain is
# Westminster); every form is also refused after a foreign country's name ("अमेरिका के सुप्रीम कोर्ट").
LEXICON = (
    {"hi": "तिरंगा", "forms": ("तिरंगा", "तिरंगे", "तिरंगों", "राष्ट्रीय ध्वज", "राष्ट्रध्वज", "भारतीय ध्वज", "राष्ट्रीय झंडा",
                              "राष्ट्रीय झंडे"),
     "en": "Flag of India", "india": False,
     "files": ("File:Flag of India, New Delhi.jpg", "File:Shiny Indian flag on high rise.jpg",
               "File:Flag of India Kodaikanal Tamil Nadu 20060126.jpg", "File:INS Kadmatt - Indian Flag.jpg")},
    {"hi": "संसद", "forms": ("संसद", "संसद भवन", "नई संसद", "नए संसद भवन", "नया संसद भवन"),
     "en": "Parliament House, New Delhi", "india": True},
    {"hi": "सुप्रीम कोर्ट", "forms": ("सुप्रीम कोर्ट", "सर्वोच्च न्यायालय", "उच्चतम न्यायालय", "शीर्ष अदालत"),
     "en": "Supreme Court of India", "india": True},
    {"hi": "लाल किला", "forms": ("लाल किला", "लाल किले", "लालकिला", "लालकिले"), "en": "Red Fort", "india": True},
    {"hi": "इंडिया गेट", "forms": ("इंडिया गेट",), "en": "India Gate", "india": True},
    {"hi": "राष्ट्रपति भवन", "forms": ("राष्ट्रपति भवन",), "en": "Rashtrapati Bhavan", "india": True},
    {"hi": "ताजमहल", "forms": ("ताजमहल", "ताज महल"), "en": "Taj Mahal", "india": False},
    {"hi": "राम मंदिर", "forms": ("राम मंदिर", "अयोध्या राम मंदिर"), "en": "Ram Mandir", "india": True},
    {"hi": "वंदे भारत", "forms": ("वंदे भारत", "वंदे भारत एक्सप्रेस", "वंदे भारत ट्रेन", "वंदे भारत ट्रेनों"),
     "en": "Vande Bharat Express", "india": True},
    {"hi": "बाघ", "forms": ("बाघ", "बाघों", "बाघिन", "बाघिनों"), "en": "Bengal tiger", "india": False},
    {"hi": "तेंदुआ", "forms": ("तेंदुआ", "तेंदुए", "तेंदुओं"), "en": "Indian leopard", "india": False},
    {"hi": "हाथी", "forms": ("हाथी", "हाथियों"), "en": "Indian elephant", "india": False},
    {"hi": "तेल टैंकर", "forms": ("तेल टैंकर", "तेल टैंकरों", "टैंकर जहाज"), "en": "Oil tanker", "india": False},
    {"hi": "पद्म श्री", "forms": ("पद्म श्री", "पद्मश्री"), "en": "Padma Shri", "india": True},
)
# People the news names in nearly every Indian story, by their full Hindi names (never a bare surname: "ललित मोदी"),
# in case the script's names list leaves them out. Dry run 39817474353 (Donald Tusk in Delhi, 2026-10-22) said
# "प्रधानमंत्री नरेंद्र मोदी" in all five beats, listed only Tusk, Poland and New Delhi, and showed Modi in none.
FIGURES = (
    ("Narendra Modi", ("नरेंद्र मोदी", "नरेन्द्र मोदी", "प्रधानमंत्री मोदी", "पीएम मोदी")),
    ("Amit Shah", ("अमित शाह", "गृह मंत्री शाह")),
    ("Rahul Gandhi", ("राहुल गांधी", "राहुल गाँधी")),
    ("Droupadi Murmu", ("द्रौपदी मुर्मू", "राष्ट्रपति मुर्मू")),
    ("Rajnath Singh", ("राजनाथ सिंह",)),
    ("S. Jaishankar", ("एस जयशंकर", "एस. जयशंकर", "विदेश मंत्री जयशंकर")),
    ("Nirmala Sitharaman", ("निर्मला सीतारमण",)),
    ("Yogi Adityanath", ("योगी आदित्यनाथ",)),
    ("Mallikarjun Kharge", ("मल्लिकार्जुन खड़गे", "मल्लिकार्जुन खरगे")),
    ("Sonia Gandhi", ("सोनिया गांधी", "सोनिया गाँधी")),
    ("Priyanka Gandhi", ("प्रियंका गांधी", "प्रियंका गाँधी")),
    ("Arvind Kejriwal", ("अरविंद केजरीवाल",)),
    ("Mamata Banerjee", ("ममता बनर्जी",)),
    ("Nitish Kumar", ("नीतीश कुमार",)),
    ("Devendra Fadnavis", ("देवेंद्र फडणवीस", "देवेन्द्र फडणवीस")),
)


def figures_said(beats: list[dict]) -> list[dict]:
    """The FIGURES the beats name, as script names: [{"en", "hi", "alias"}], hi the form first said."""
    out = []
    for en, forms in FIGURES:
        hits = sorted((at, w) for w in forms for b in beats if (at := said_at(b.get("say") or "", (w,))) >= 0)
        if hits:
            hi = hits[0][1]
            out.append({"en": en, "hi": hi, "alias": [w for w in forms if w != hi]})
    return out


# A country or its adjective right before a thing ("अमेरिकी सुप्रीम कोर्ट", "ब्रिटेन की संसद"): another country's.
FOREIGN = ("अमेरिका", "अमेरिकी", "यूएस", "US", "पाकिस्तान", "पाकिस्तानी", "ब्रिटेन", "ब्रिटिश", "चीन", "चीनी", "रूस",
           "रूसी", "नेपाल", "नेपाली", "बांग्लादेश", "बांग्लादेशी", "श्रीलंका", "श्रीलंकाई", "इजराइल", "इज़राइल", "इजरायली",
           "ईरान", "ईरानी", "जापान", "जापानी", "कनाडा", "कनाडाई", "फ्रांस", "फ्रांसीसी", "जर्मनी", "जर्मन", "यूक्रेन",
           "अफगानिस्तान", "ऑस्ट्रेलिया", "ऑस्ट्रेलियाई", "दक्षिण अफ्रीका", "ब्राजील", "मालदीव", "भूटान", "म्यांमार")
# What an English article about a thing says it is (its Wikidata description).
THING = re.compile(r"\b(ship|vessel|tanker|aircraft|airliner|helicopter|fighter|jet|submarine|carrier|frigate|"
                   r"destroyer|corvette|warship|train|locomotive|missile|rocket|launch vehicle|rifle|tank|vehicle|"
                   r"automobile|motorcycle|species|subspecies|breed|animal|mammal|bird|reptile|fish|dish|food|sweet|"
                   r"dessert|bread|beverage|award|medal|decoration|honour|honor|flag|monument|memorial|building|"
                   r"bridge|dam|fort|fortress|palace|temple|mosque|church|gurdwara|stadium|statue|tower|parliament|"
                   r"courthouse)\b", re.I)
# Never a thing with a picture: works (their pictures are covers and posters), bodies whose pictures are logos, and
# brands.
WORK = re.compile(r"\b(film|movie|album|song|single|book|novel|series|television|TV|show|painting|magazine|"
                  r"newspaper|journal|company|organi[sz]ation|political party|party|brand|band|video game|game|"
                  r"software|website|app|application|logo|manufacturer|corporation|business|startup|conglomerate|"
                  r"agency|ministry|department|union|association|club|team|league|government|court case|case|"
                  r"election|event|protest|scheme|programme|program|law|act|bill)\b", re.I)
# A file that shows a work, a logo or a screen, never the thing: a book cover, a poster, an app's screenshot.
NOT_THING = re.compile(r"\b(cover|poster|album|screenshot|screen ?shot|logo|wordmark|trademark|paintings?|"
                       r"drawings?|illustrations?|cartoons?|render(?:ing)?|model kit|toy|stamp|coin|banknote|tweet|"
                       r"instagram|facebook|miniature|watercolou?r|engraving|lithograph|artworks?|mughal art|"
                       r"company painting)\b", re.I)
# Before photographs were common, a picture of a thing is a painting or an engraving (the Red Fort's Commons category
# gave a Ghulam Ali Khan painting of 1852): a Short shows a photo of the thing as it is.
PHOTO_YEAR = 1900


def foreign_before(say: str, at: int) -> bool:
    """A country or its adjective stands right before `at` in say, or as "X की/के/का" before it."""
    head = re.sub(r"\s+(?:की|के|का)\s*$", " ", say[:at].rstrip() + " ").rstrip()
    return any(hindi.norm(head).endswith(hindi.norm(w)) and hindi.find(head, w.split()[-1]) >= 0 for w in FOREIGN)


def said_at(say: str, forms) -> int:
    """Where say first names one of forms as whole words, never after a foreign country's name, else -1."""
    from .visuals import _finds

    hits = [a for w in forms for a in _finds(say, w) if not foreign_before(say, a)]
    return min(hits, default=-1)


def lexicon_hits(beats: list[dict], india: bool) -> list[dict]:
    """The LEXICON entries the beats name: [{"en", "hi", "kind": "thing", "alias", "files"}]."""
    out = []
    for e in LEXICON:
        if e["india"] and not india:
            continue
        if any(said_at(b.get("say") or "", e["forms"]) >= 0 for b in beats):
            out.append({"en": e["en"], "hi": e["hi"], "kind": "thing", "title": e["en"],
                        "alias": [f for f in e["forms"] if f != e["hi"]], "files": list(e.get("files") or ())})
    return out


def thing_like(ent: dict) -> bool:
    """A thing with a picture of its own (THING), never a work, a body or a brand (WORK), a person, a place a map
    shows (coordinates with people) or a disambiguation page."""
    kinds = {c["value"] for c in wiki.claims(ent, "P31")}
    if wiki.HUMAN in kinds or wiki.DISAMBIGUATION in kinds or wiki.claims(ent, "P1082"):
        return False
    desc = ((ent.get("descriptions") or {}).get("en") or {}).get("value", "")
    return bool(THING.search(desc)) and not WORK.search(desc)


def resolve_thing(en: str) -> tuple[str, str, dict] | None:
    """(QID, title, item) for the English Wikipedia article titled exactly `en` when it is a thing (thing_like)."""
    try:
        page = wiki.page_info([en]).get(en) or {}
        ent = wiki.entities([page["qid"]]).get(page["qid"]) if page.get("qid") else None
    except Exception:
        return None
    return (page["qid"], page.get("title") or en, ent) if ent and thing_like(ent) else None


def lookup(entry: dict) -> dict | None:
    """A lexicon entry with its Wikidata item ({qid, ent} added), or None when Wikipedia has no such article."""
    try:
        page = wiki.page_info([entry["en"]]).get(entry["en"]) or {}
        ent = wiki.entities([page["qid"]]).get(page["qid"]) if page.get("qid") else None
    except Exception as exc:
        log.info("things: %s not looked up (%s)", entry["en"], exc)
        return None
    if not ent:
        return None
    return entry | {"qid": page["qid"], "title": page.get("title") or entry["en"], "ent": ent}


def has_picture(c: dict) -> bool:
    """Whether a thing could be shown, without a Commons download (visuals.showable): an editor's photos, or a
    Wikidata image that is a photo (P18 not a drawing)."""
    if c.get("files"):
        return True
    return any(not media.NOT_PHOTO.search(v["value"]) for v in wiki.claims(c.get("ent") or {}, "P18"))


def photos(c: dict, folder: Path, exclude: set[str], recent: set[str] | None = None,
           keep: int = THING_PHOTOS) -> list[dict]:
    """A thing's own free Commons photos: the editor's files, then its Wikidata image and Commons category (media's
    licence, size and decency checks, each with its author's credit), never a work, a logo or a screen (NOT_THING),
    never one with a featured face. Its Hindi name on screen; role "thing"."""
    import cv2

    from . import faces, visuals, writer

    found = media.picks(c["files"], limit=keep + 2) if c.get("files") else []
    if len(found) < keep and c.get("ent"):
        found += [p for p in media.find(c["title"], c["ent"], limit=keep + 2, exclude=exclude)
                  if p.file not in {f.file for f in found}]
    found = [p for p in found if p.file not in (exclude or set())
             and not NOT_THING.search(f"{p.file} {p.description} {p.categories}")
             and not (p.year and p.year < PHOTO_YEAR) and not media.NOT_PERSON.search(p.file)
             and not media.branded(p)]
    out = []
    for r in visuals.fresh_first(media.as_dicts(media.download(found, folder)), recent):
        img = cv2.imread(r["path"])
        if img is None or writer.featured_face(img, faces.detect(img)):
            continue
        out.append(r | {"focus": None, "role": "thing", "who": c["hi"]})
    return out[:keep]
