"""Real, freely licensed photos for a story from Wikimedia Commons, each carrying its author and licence.

Only files hosted on Commons qualify (non-free "fair use" files live on Wikipedia itself and are never touched), and
only CC0, public-domain, CC BY and CC BY-SA licences pass. Logos, maps, signatures and anything whose name suggests
injury or death imagery are skipped. When Commons is short, Openverse (keyless) fills in photos of the places and
things a story links to, CC0, CC BY and CC BY-SA only; news outlets' photos are copyrighted and never used.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import net, wiki

COMMONS = "https://commons.wikimedia.org/w/api.php"
# GODL-India: the Government of India's open licence (commercial use and adaptation allowed, attribution with the
# licence's link, no implied endorsement). It covers PIB's and the PMO's photos, the only free photos of the Prime
# Minister at the events the news is about (Commons, "Narendra Modi Dussehra": twelve, all GODL-India).
FREE = re.compile(r"^(CC0|Public domain|PD\b|CC BY(-SA)? \d(\.\d)?( [a-z]{2,})?$|CC BY(-SA)?$|GODL-India$)", re.I)
GODL_URL = "https://data.gov.in/government-open-data-license-india"
# A likeness is not the person: the Modi Short's first "photo of him" was his Madame Tussauds wax figure.
NOT_PERSON = re.compile(r"\b(wax|tussaud\w*|statue|figurine|figure at|mural|cut-?out|poster|hoarding|billboard|"
                        r"painting|sketch|caricature|effigy|mask|graffiti|sculpture|bust of)\b", re.I)
NOT_PHOTO = re.compile(r"(\.svg$|\.gif$|\.tiff?$|\blogo|signature|autograph|\bmap\b|map\.\w+$|locator|location|\bflag\b|coat of arms|"
                       r"\bicon\b|\bseal\b|emblem|chart|graph|diagram|insignia|\bplan\b|route|blank|wordmark|"
                       r"collage|montage)", re.I)
# Run 40160034587: generic filenames hid a Starlink data plot and a Blender render.
# Credits/categories describe the medium too; neither belongs in the real-photo pool.
NOT_CAMERA = re.compile(r"\b(?:rendered (?:with|using|in)|3[- ]?d render(?:ing)?s?|computer[- ]generated|"
                        r"artist['’]s (?:impression|concept|conception)|(?:line|bar|pie) chart|"
                        r"(?:data|statistical) (?:plot|chart)|plot(?:ted)? data)\b", re.I)
# Dignity: a Short never shows bodies, wounds or grief at a funeral.
GRAPHIC = re.compile(r"(corpse|bodies|\bbody\b|victim|blood|wound|injur|\bdead\b|killed|funeral|cremat|coffin|casket|"
                     r"wreckage|debris|crash site|aftermath)", re.I)
MIN_SIDE = 480


@dataclass
class Photo:
    file: str  # "File:Name.jpg" on Commons
    url: str  # a 1600 px rendition
    page: str  # the Commons file page, for credits
    width: int
    height: int
    author: str
    license: str
    description: str
    date: str
    origin: str  # "wikidata", "article", "category", ... or "openverse"
    path: str = ""
    host: str = "Wikimedia Commons"  # where the file is credited: Commons, or "Openverse (Flickr)"
    # Vetting metadata Commons already sends (extmetadata) and the pool used to throw away (SYNC-AUDIT 4.1 step 1):
    # the file's categories, its Credit line (a watermark's source: "Bollywood Hungama") and the year it was taken.
    # Never a filter at the source; ranking and the gate read them (era_reject, event_kind, branded).
    categories: str = ""
    source_credit: str = ""
    year: int | None = None

    @property
    def credit(self) -> str:
        licence = f"{self.license} ({GODL_URL})" if self.license.upper() == "GODL-INDIA" else self.license
        return f"फ़ोटो: {self.author} / {licence} / {self.host}"


HIDDEN = re.compile(r"<(\w+)[^>]*display:\s*none[^>]*>.*?</\1>", re.I | re.S)


def _text(value: str | None, limit: int = 200) -> str:
    text = re.sub(r"<[^>]+>", " ", HIDDEN.sub("", value or ""))
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit]


def _batches(files: list[str], size: int = 40, chars: int = 2500) -> list[list[str]]:
    """Up to `size` titles a request, and never so many long file names that the URL is refused (HTTP 414)."""
    out, batch, used = [], [], 0
    for f in files:
        if batch and (len(batch) == size or used + len(f) + 1 > chars):
            out.append(batch)
            batch, used = [], 0
        batch.append(f)
        used += len(f) + 1
    return out + ([batch] if batch else [])


def _info(files: list[str]) -> dict[str, dict]:
    out = {}
    for batch in _batches(files):
        d = net.get_json(COMMONS, params={
            "action": "query", "titles": "|".join(batch), "prop": "imageinfo", "iiurlwidth": 1600,
            "iiprop": "url|size|mime|extmetadata|sha1", "format": "json", "formatversion": 2, "redirects": 1})
        for p in d["query"].get("pages", []):
            if p.get("missing") or not p.get("imageinfo"):
                continue
            out[p["title"]] = p["imageinfo"][0]
    return out


def _article_files(title: str) -> list[str]:
    d = net.get_json(wiki.API, params={"action": "parse", "page": title, "prop": "images", "redirects": 1,
                                       "format": "json", "formatversion": 2})
    return ["File:" + f for f in d.get("parse", {}).get("images", [])]


def _search_files(query: str, limit: int = 40) -> list[str]:
    d = net.get_json(COMMONS, params={"action": "query", "list": "search", "srsearch": query, "srnamespace": 6,
                                      "srlimit": limit, "format": "json", "formatversion": 2})
    return [h["title"] for h in d.get("query", {}).get("search", [])]


def _category_files(category: str, limit: int = 60) -> list[str]:
    d = net.get_json(COMMONS, params={"action": "query", "list": "categorymembers", "cmtitle": "Category:" + category,
                                      "cmtype": "file", "cmlimit": limit, "format": "json", "formatversion": 2})
    return [m["title"] for m in d.get("query", {}).get("categorymembers", [])]


GENERIC = {"the", "of", "and", "in", "on", "at", "flight", "hurricane", "cyclone", "typhoon", "storm", "tropical",
           "earthquake", "attack", "bombing", "shooting", "crash", "fire", "flood", "floods", "disaster", "accident",
           "incident", "explosion", "derailment", "collision", "sinking", "airlines", "air", "airways", "season"}


def _keys(title: str) -> set[str]:
    """Distinctive words of a story title: 'Hurricane Isaias (2026)' -> {'isaias'}; 'Nana Patekar' -> both names.

    Long titles keep only their longest word, so 'Air India Flight 171' still matches a photo captioned 'Air India'.
    """
    words = re.findall(r"[^\W\d_]{3,}", re.sub(r"\([^)]*\)", "", title).lower())
    keys = {w for w in words if w not in GENERIC}
    return {max(keys, key=len)} if len(keys) > 3 else keys


def _names(text: str, keys: set[str]) -> bool:
    low = text.lower()
    return bool(keys) and all(k in low for k in keys)


def _shoot(file: str) -> str:
    """Files from one photo shoot share a name up to the numbering: group them so a Short shows variety."""
    stem = re.sub(r"\.[a-z]+$", "", file.lower())
    return re.sub(r"[\s_(-]*(\(?image )?\d+\)?(?=[\s,.]|$).*$", "", stem)[:40]


def find(title: str, ent: dict, limit: int = 8, extra_qids: list[str] | None = None,
         exclude: set[str] | None = None, search: bool = False, places: bool = False,
         words: list[str] | None = None) -> list[Photo]:
    """Up to `limit` usable photos: the Wikidata image first, then the article's own images, then its Commons category.

    Article and category files must name the story (the person's surname, the storm's name) in their file name or
    description, so a festival photo that merely sits in a person's category is not passed off as them.
    extra_qids adds the main image of related items (a birthplace, an aircraft type, an airport) after those.
    exclude: Commons files that may not be used (the ones Orbitwire would pick); search: also search Commons for
    files naming the story. Without both, the ranking is exactly Orbitwire's (desk/orbitwire.py relies on that).
    places: also take photos from each related item's own article whose file name names that item (a city skyline,
    the airport's terminal), for an article so new that Commons has nothing of the event itself.
    words: the story's own words ("Dussehra"): Commons files naming the subject and one of them come first, so a
    Short about the Prime Minister at Dussehra shows him at Dussehra, not at a summit in Kazan.
    """
    keys = _keys(wiki.label(ent) or title) | _keys(title)
    ordered: list[tuple[str, str]] = []
    name = re.sub(r"\s*\([^)]*\)$", "", title)
    for w in words or []:
        try:
            ordered += [(f, "story") for f in _search_files(f"{name} {w}", limit=20)
                        if _names(f, {w.lower()})]
        except Exception:
            pass
    for c in wiki.claims(ent, "P18"):
        ordered.append(("File:" + c["value"], "wikidata"))
    try:
        ordered += [(f, "article") for f in _article_files(title)]
    except Exception:
        pass
    for c in wiki.claims(ent, "P373")[:1]:
        try:
            ordered += [(f, "category") for f in _category_files(c["value"])]
        except Exception:
            pass
    if extra_qids:
        related = wiki.entities(extra_qids)
        for q, e in related.items():
            ordered += [("File:" + c["value"], "related") for c in wiki.claims(e, "P18")[:1]]
        for q, e in related.items() if places else ():
            ordered += _place_files(e)
    if search:
        try:
            ordered += [(f, "search") for f in _search_files(re.sub(r"\s*\([^)]*\)$", "", title))]
        except Exception:
            pass
    return _usable(ordered, keys, limit, exclude=exclude)


def _place_files(e: dict) -> list[tuple[str, str]]:
    """Up to three files from an item's own article whose names name the item (a city skyline, a school's front)."""
    page, own = wiki.sitelink(e, "enwiki"), _keys(wiki.label(e) or "")
    try:
        files = _article_files(page) if page and own else []
    except Exception:
        files = []
    return [(f, "place") for f in files if _names(f.replace("_", " "), own) and not NOT_PHOTO.search(f)][:3]


def context(qids: list[str], limit: int = 6, exclude: set[str] | None = None) -> list[Photo]:
    """Photos of the places and things a story links to (a birthplace, a school, an award, the airport): each item's
    main image, then files from its article that name it. They fill a Short whose own photos are too few, and are
    never of the story's person (the caller drops any that feature a face)."""
    if not qids:
        return []
    ordered = []
    for e in wiki.entities(qids).values():
        ordered += [("File:" + c["value"], "related") for c in wiki.claims(e, "P18")[:1]]
        ordered += _place_files(e)
    return _usable(ordered, set(), limit, exclude=exclude)


def scene(place: str, words: list[str], limit: int = 6, exclude: set[str] | None = None) -> list[Photo]:
    """Commons photos of the kind of scene a story happened at ("Kolkata Durga Puja pandal"): files naming the
    place and the most-reported scene word, for a story so new that Commons has nothing of the event itself."""
    if not words:
        return []
    try:
        files = _search_files(" ".join([place] + words))
    except Exception:
        return []
    keys = _keys(place) | {words[0]}
    return _usable([(f, "search") for f in files], keys, limit, exclude=exclude)


OPENVERSE = "https://api.openverse.org/v1/images/"
# Openverse licence codes a Short may use: CC0, CC BY and CC BY-SA. Non-commercial, no-derivatives and the
# public-domain mark (which asserts no licence) never pass.
OPENVERSE_LICENCES = {"cc0": "CC0", "by": "CC BY", "by-sa": "CC BY-SA"}
OPENVERSE_PER_PLACE = 3


def openverse(query: str, limit: int = OPENVERSE_PER_PLACE, exclude: set[str] | None = None) -> list[Photo]:
    """Freely licensed photos of a place, object or scene from Openverse (keyless): CC0, CC BY or CC BY-SA only,
    from sources other than Wikimedia (Commons is read directly), whose title names the query, at most two by one
    creator. Never asked about a person: callers search only the places and things a story links to, and drop any
    photo that features a face."""
    d = net.get_json(OPENVERSE, params={"q": query, "license_type": "commercial,modification",
                                        "excluded_source": "wikimedia", "page_size": 20}, tries=2, timeout=30)
    keys = _keys(query)
    photos, creators = [], {}
    for r in d.get("results") or []:
        lic, url = OPENVERSE_LICENCES.get((r.get("license") or "").lower()), r.get("url") or ""
        file, title = f"openverse:{r.get('id')}", _text(r.get("title"))
        ext = (r.get("filetype") or url.rsplit(".", 1)[-1]).lower()
        if not lic or r.get("mature") or not url.startswith("https://") or file in (exclude or set()):
            continue
        if ext not in ("jpg", "jpeg", "png", "webp") or NOT_PHOTO.search(title) or NOT_CAMERA.search(title) \
                or GRAPHIC.search(title):
            continue
        if min(r.get("width") or 0, r.get("height") or 0) < MIN_SIDE or not _names(title, keys):
            continue
        author = _text(r.get("creator"), 60) or "unknown author"
        if creators.get(author, 0) >= 2:
            continue
        creators[author] = creators.get(author, 0) + 1
        source = (r.get("source") or r.get("provider") or "").replace("_", " ")
        photos.append(Photo(file=file, url=url, page=r.get("foreign_landing_url") or url, width=r["width"],
                            height=r["height"], author=author, license=f"{lic} {r.get('license_version') or ''}".strip(),
                            description=title, date="", origin="openverse",
                            host="Openverse" + (f" ({source.capitalize()})" if source else "")))
        if len(photos) >= limit:
            break
    return photos


def place_like(ent: dict) -> bool:
    """A Wikidata item that is somewhere: it has coordinates and is not a person."""
    kinds = {c["value"] for c in wiki.claims(ent, "P31")}
    return wiki.HUMAN not in kinds and bool(wiki.claims(ent, "P625"))


def openverse_for(qids: list[str], limit: int = 6, exclude: set[str] | None = None) -> list[Photo]:
    """Openverse photos of the places a story links to (by their English Wikidata labels), in order; never of a
    person, a group or a work (an item without coordinates)."""
    if not qids:
        return []
    out, seen = [], set(exclude or ())
    for e in wiki.entities(qids).values():
        name = wiki.label(e)
        if not name or not place_like(e):
            continue
        try:
            found = openverse(name, exclude=seen)
        except Exception:
            continue
        for p in found:
            seen.add(p.file)
            out.append(p)
        if len(out) >= limit:
            break
    return out[:limit]


def picks(files: list[str], limit: int = 8) -> list[Photo]:
    """Photos an editor chose for a story, in order, under the same licence, size and decency checks as find()."""
    return _usable([(f if f.startswith("File:") else "File:" + f, "editor") for f in files], set(), limit,
                   shoot_cap=limit)


def _usable(ordered: list[tuple[str, str]], keys: set[str], limit: int, shoot_cap: int = 2,
            exclude: set[str] | None = None) -> list[Photo]:
    seen, files = set(), []
    banned = {e.replace("_", " ") for e in exclude or ()}
    for f, origin in ordered:
        f = f.replace("_", " ")
        if f in banned:
            continue
        if f not in seen and not GRAPHIC.search(f) and (origin == "editor" or not NOT_PHOTO.search(f)):
            seen.add(f)
            files.append((f, origin))
    info = _info([f for f, _ in files])
    photos, hashes, shoots = [], set(), {}
    for f, origin in files:
        ii = info.get(f)
        if not ii or ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        meta = ii.get("extmetadata", {})
        lic = _text(meta.get("LicenseShortName", {}).get("value"), 40)
        desc = _text(meta.get("ImageDescription", {}).get("value"))
        if not FREE.match(lic) or meta.get("NonFree", {}).get("value") or GRAPHIC.search(desc):
            continue
        medium = " ".join((f, desc, _text(meta.get("Credit", {}).get("value"), 1000),
                           _text(meta.get("Categories", {}).get("value"), 1000)))
        if NOT_CAMERA.search(medium):
            continue
        if min(ii["width"], ii["height"]) < MIN_SIDE or ii.get("sha1") in hashes:
            continue
        if origin in ("article", "category", "search", "story") and not _names(f"{f} {desc}", keys):
            continue
        shoot = _shoot(f)
        if shoots.get(shoot, 0) >= shoot_cap:
            continue
        shoots[shoot] = shoots.get(shoot, 0) + 1
        hashes.add(ii.get("sha1"))
        author = _text(meta.get("Artist", {}).get("value"), 60) or "unknown author"
        date = _text(meta.get("DateTimeOriginal", {}).get("value"), 40)
        photos.append(Photo(file=f, url=ii.get("thumburl") or ii["url"], page=ii["descriptionurl"], width=ii["width"],
                            height=ii["height"], author=author, license=lic, description=desc, date=date,
                            origin=origin, categories=_text(meta.get("Categories", {}).get("value"), 400),
                            source_credit=_text(meta.get("Credit", {}).get("value"), 120), year=parse_year(date)))
        if len(photos) >= limit:
            break
    return photos


# --- Vetting: what a photo shows besides who ------------------------------------------------------------------
# The Rubio Short (39714003987, 2026-10-22) opened on his 1989 high-school yearbook photo under "रिफाइनरी दौरा"; its
# pool also held "Marco Rubio in 6th Grade". The Jantar Mantar Short showed a 1928 photo of the place.
# "baby" only as the person's age ("as a baby", "baby photo"), never a title: "Baby John" is a 2024 film.
CHILD = re.compile(r"yearbook|\b\d+(st|nd|rd|th) grade\b|childhood|\bas an? (child|boy|girl|baby|teen\w*)\b|"
                   r"\bschool photo|\bbaby (photo|picture|pic)s?\b", re.I)
PERSON_YEARS, PLACE_YEARS, ADULT = 20, 40, 18
# Another event's photo: Mukesh Ambani at the 2023 NMACC gala under "welcomed him at Jamnagar", Tiger Shroff with his
# mother at the 2015 Filmfare awards under "the court handed the accused to Mumbai Police". "party" only as a social
# one (a birthday, wedding or launch party, a party at a home): a politician's photos name his party in every case
# and order ("BJP party workers", "Congress party leader", "Bharatiya Janata Party").
EVENT = re.compile(r"\bgala\b|\bawards?\b|premiere|red carpet|screening|wedding|filmfare|\biifa\b|\bspotted\b",
                   re.I)
PARTY = re.compile(r"\b(birthday|wedding|house|launch|success|wrap|farewell|engagement|cocktail|dinner|pool|after|"
                   r"christmas|diwali|holi|new year'?s?|bachelor(ette)?|reception|theme|costume|tea|garden|dance|"
                   r"release|anniversary|kitty|private|star-?studded) part(y|ies)\b|\bpart(y|ies) (at|hosted)\b|"
                   r"\bpartying\b", re.I)
# Paparazzi agencies whose watermark sits on the photo: 7-10 of the 8-11 Tiger Shroff pool photos carry one, so this
# only ranks a photo lower and never drops it (the pool would empty).
BRANDED = re.compile(r"bollywood ?hungama|pinkvilla|filmibeat|viral ?bhayani", re.I)
# A landmark noun the place's own name lacks: "Juhu" showed ISKCON temple, Juhu; "अंधेरी स्टेशन" the Andheri flyover.
LANDMARK = re.compile(r"\b(temple|flyover|bridge|mall|hotel|station|stadium)s?\b", re.I)


def _field(p, name: str):
    return (p.get(name) if isinstance(p, dict) else getattr(p, name, None)) or ""


def _about(p) -> str:
    """A photo's own words: its file name, description and Commons categories."""
    return " ".join(str(_field(p, k)) for k in ("file", "description", "categories")).replace("_", " ")


def parse_year(date: str | None) -> int | None:
    """The year a photo was taken from Commons' DateTimeOriginal: "circa 1988-1989" is 1988, "circa 1980's" 1980."""
    m = re.search(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", date or "")
    return int(m.group(1)) if m else None


def year_of(p) -> int | None:
    """A photo's year: the stamped one, else parsed from its date (artifacts written before the field existed)."""
    y = _field(p, "year")
    return y if isinstance(y, int) else parse_year(_field(p, "date"))


def era_reject(p, story_year: int, born: int | None = None, role: str = "person", pool=()) -> str:
    """Why a photo is from the wrong time of its subject's life, or "" when it is fine: a child (a yearbook, a school
    photo, "in 6th Grade"), the person under ADULT (Wikidata P569 born), a person photo over PERSON_YEARS old while
    a newer one of the same pool passes, a place photo over PLACE_YEARS old (1928; a 2002 heritage photo stays)."""
    text, y = _about(p), year_of(p)
    if role == "person":
        if m := CHILD.search(text):
            return f"a childhood photo ({m.group(0)})"
        if y and born and y - born < ADULT:
            return f"taken at {y - born}, before adulthood"
        if y and story_year - y > PERSON_YEARS:
            newer = [q for q in pool if q is not p and (year_of(q) or 0) > y and story_year - (year_of(q) or 0)
                     <= PERSON_YEARS and not CHILD.search(_about(q))]
            if newer:
                return f"{story_year - y} years old ({y}) while a newer photo exists"
        return ""
    if y and story_year - y > PLACE_YEARS:
        return f"{story_year - y} years old ({y})"
    return ""


def event_kind(p) -> str:
    """The unrelated event a photo was taken at (a gala, an award night, a premiere, a sighting), or ""."""
    text = _about(p)
    if m := EVENT.search(text):
        return m.group(0).lower()
    return "party" if PARTY.search(text) else ""


def branded(p) -> bool:
    """A paparazzi agency's photo (its watermark): a ranking signal only, never a ban."""
    return bool(BRANDED.search(" ".join([_about(p), str(_field(p, "author")), str(_field(p, "source_credit"))])))


def not_itself(p, place_en: str) -> bool:
    """The photo is of a landmark at the place, not the place: its words name a temple, flyover, bridge, mall,
    hotel, station or stadium that the place's own name does not."""
    own = (place_en or "").lower()
    text = " ".join(str(_field(p, k)) for k in ("file", "description")).replace("_", " ")
    return any(m.group(1).lower() not in own for m in LANDMARK.finditer(text))


def download(photos: list[Photo], folder: Path) -> list[Photo]:
    folder.mkdir(parents=True, exist_ok=True)
    kept = []
    for i, p in enumerate(photos):
        ext = ".png" if p.url.lower().endswith(".png") else ".jpg"
        # Named by the photo's URL too: a retry whose photo order changed never reuses another photo's file.
        path = folder / f"photo{i:02d}-{hashlib.sha1(p.url.encode()).hexdigest()[:10]}{ext}"
        try:
            if not path.exists():
                path.write_bytes(net.get(p.url, timeout=60))
        except Exception:
            continue
        p.path = str(path)
        kept.append(p)
    return kept


def as_dicts(photos: list[Photo]) -> list[dict]:
    return [asdict(p) | {"credit": p.credit} for p in photos]


def from_openverse(photo: dict) -> bool:
    return (photo.get("host") or "").startswith("Openverse")


def hosts(photos: list[dict]) -> str:
    """Where a Short's photos come from, as its end card and description name them."""
    names = "Wikimedia Commons, Openverse" if any(from_openverse(p) for p in photos) else "Wikimedia Commons"
    return names + (", OpenStreetMap" if any(p.get("host") == "OpenStreetMap" for p in photos) else "")
