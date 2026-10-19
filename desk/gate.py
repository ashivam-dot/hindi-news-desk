"""The checks a Short must pass before it can publish: grounded numbers, decorum (in Hindi and English), title rules,
credited free photos, the AI-voice disclosure, the Sulafat voice, Orbitwire's rules for shared stories, and two
independent owners behind any fact taken from trusted outlets' reporting (desk/outlets.py)."""
from __future__ import annotations

import re

from . import hindi
from .spec import Short

# Gore, sensationalism and clickbait never appear in a title, a card or the narration. A trailing * matches any
# ending ("चौंकाने*" also catches चौंकाने वाला); everything else matches whole words only (so लाश never trips on तलाश).
BANNED = [
    "blood", "bloody", "gore", "gory", "graphic", "corpse", "corpses", "body bag", "bodies", "dismember*", "decapitat*",
    "mutilat*", "charred", "burned alive", "horrific", "horrifying", "gruesome", "shocking", "terrifying", "nightmare",
    "massacre", "slaughter", "carnage", "apocalyp*", "armageddon", "doomed", "you won't believe", "insane", "breaking",
    "must watch", "watch till the end", "omg", "wtf", "rip", "sexy", "nude", "naked", "porn", "kill count",
    "ब्रेकिंग", "बड़ी खबर", "बड़ी ख़बर", "सनसनी*", "चौंका*", "खौफ*", "ख़ौफ़*", "दिल दहला*", "रोंगटे", "होश उड़*",
    "भयावह", "खून", "ख़ून", "खूनी", "ख़ूनी", "लहूलुहान", "लाश", "लाशें", "लाशों", "शव", "शवों", "क्षत-विक्षत",
    "नरसंहार", "कत्लेआम", "क़त्लेआम", "तांडव", "कोहराम", "हड़कंप", "बवाल", "धमाकेदार", "वायरल", "अंत तक देख*",
    "सब्सक्राइब", "लाइक करें", "शेयर करें", "आत्महत्या", "खुदकुशी", "ख़ुदकुशी", "suicide*",
]
ACRONYMS = {"USGS", "UTC", "PAGER", "NASA", "NOAA", "GDACS", "EMSC", "ADS-B", "NTSB", "AAIB", "BEA", "MMI", "ICAO",
            "IATA", "UN", "WHO", "EU", "UK", "US", "USA", "3D", "NHC", "JTWC", "IMD", "JMA", "PTWC", "ISRO", "NDRF",
            "SDRF", "DGCA", "AAIB", "CBI", "NIA", "ICC", "IPL", "BCCI", "AIIMS", "IIT", "UNESCO", "UNICEF", "NATO",
            "BRICS", "SAARC", "ASEAN", "AI", "IDBI", "SEBI", "DRDO", "CBSE", "UPSC", "NEET", "NHAI", "IRCTC", "BSNL"}
# Without a death toll that two sources agree on, an incident Short may not speak of casualties at all.
CASUALTY = ["casualt*", "death toll", "killed", "fatalit*", "wounded", "injured", "मौत", "मौतें", "मौतों", "मारे",
            "मृत", "मृतक", "मृतकों", "मृतकों", "घायल", "घायलों", "हताहत", "जान गई", "जानें", "जान गंवा*",
            "जान गँवा*", "निधन", "शहीद", "जान चली", "मारा", "दम तोड़*", "मरने वाले*", "deaths", "toll"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F000-\U0001F2FF]")
# The voice identities a Short may publish with: Gemini's Sulafat, or Chatterbox cloning Sulafat's reference clip.
PUBLISHABLE_VOICES = {"gemini-sulafat", "chatterbox-sulafat-clone"}
# Outlet reporting (desk/outlets.py) backs a fact only when this many independent owners state it; a fact only one
# outlet reports is never said.
OWNERS_NEEDED = 2
# A title opens with its subject in English letters ("LK Advani: ..."), so a little under half of it may be Latin.
TITLE_HINDI = 0.4
_N = r"\d{1,3}(?:,\d{3})+|\d+"
_HEDGE = r"(?P<hedge>(?:at least|more than|over|nearly|about|around|up to|some|almost|roughly)\s+)?"
TOLLS = [
    re.compile(rf"(?<![\w.,]){_HEDGE}(?P<n>{_N})\s+(?:[A-Za-z-]+\s+){{0,3}}?(?:killed|dead|died|lost their lives)\b",
               re.I),
    re.compile(rf"\b(?:death toll|toll)\s+(?:[A-Za-z-]+\s+){{0,3}}?{_HEDGE}(?P<n>{_N})\b", re.I),
    re.compile(rf"\b(?:killing|killed)\s+{_HEDGE}(?P<n>{_N})\s+(?:people|persons|passengers|civilians|workers)\b",
               re.I),
    re.compile(r"(?P<hedge>(?:कम से कम|करीब|क़रीब|लगभग|तकरीबन)\s+)?(?P<n>\d+)\s+(?:\S+\s+){0,2}?(?:की\s+)?"
               r"(?:मौत|मौतें|जान\s+(?:चली|गई|गंवा|गँवा)|मारे\s+गए)"),
]
# A hedge written after the number ("12 or more killed", "50 से अधिक की मौत", "12 feared dead") is not exact either.
_HEDGE_AFTER = re.compile(r"\b(?:or more|or so|plus|feared|presumed|believed|reportedly)\b|\+|से\s+(?:ज़्|ज्)?यादा|"
                          r"से\s+अधिक|से\s+ऊपर", re.I)


def found(text: str, words: list[str]) -> str | None:
    """The first listed word in text (whole words; a trailing * allows any ending)."""
    low = hindi.norm(text)
    for w in words:
        stem = hindi.norm(w.rstrip("*"))
        for m in re.finditer(re.escape(stem), low):
            before = low[m.start() - 1] if m.start() else " "
            after = low[m.end()] if m.end() < len(low) else " "
            if hindi._letter(before) or (not w.endswith("*") and hindi._letter(after)):
                continue
            return w.rstrip("*")
    return None


def decorum(text: str, kind: str, agreed_toll: bool) -> list[str]:
    problems = []
    word = found(text, BANNED)
    if word:
        problems.append(f"banned wording {word!r}")
    if EMOJI.search(text):
        problems.append("emoji")
    if kind in ("incident", "explainer") and not agreed_toll:
        word = found(text, CASUALTY)
        if word:
            problems.append(f"casualties without an agreed toll ({word})")
    return problems


def numbers(text: str) -> list[str]:
    return [v for v, _ in hindi.numbers(text)]


def reported(needle: str, reports: list[dict]) -> list[str]:
    """The independent owners whose articles write needle (whole words, Hindi spellings normalised)."""
    return sorted({r["owner"] for r in reports if r.get("text") and hindi.contains(r["text"], needle)})


def reported_values(reports: list[dict]) -> dict[str, list[str]]:
    """Every number value the reports state (15 लाख = 1.5 million = 1500000) -> the owners stating it."""
    by: dict[str, set[str]] = {}
    for r in reports:
        for v in hindi.values(r.get("text") or ""):
            by.setdefault(v, set()).add(r["owner"])
    return {v: sorted(o) for v, o in by.items()}


def corroborated_values(reports: list[dict]) -> set[str]:
    """Number values at least OWNERS_NEEDED independent owners state."""
    return {v for v, o in reported_values(reports).items() if len(o) >= OWNERS_NEEDED}


def reported_tolls(reports: list[dict]) -> dict[str, set[int]]:
    """owner -> the exact death tolls its articles state ("12 people were killed", "12 लोगों की मौत"); hedged counts
    ("at least 12") are not exact and are left out."""
    by: dict[str, set[int]] = {}
    for r in reports:
        body = hindi.ascii_digits(r.get("text") or "")
        for pattern in TOLLS:
            for m in pattern.finditer(body):
                n = int(m.group("n").replace(",", ""))
                if m.group("hedge") or _HEDGE_AFTER.search(body[m.end("n"):m.end() + 12]):
                    n = -1  # a hedged count: no exact toll may be said beside it
                by.setdefault(r["owner"], set()).add(n)
    return by


def reported_toll(reports: list[dict], wikidata: set[int] | None = None) -> tuple[int, list[str]] | None:
    """A death toll the reporting agrees on, with the owners stating it: two independent owners give the same exact
    number (or one does and Wikidata's only toll is that number), no outlet gives a different or hedged one (a rising
    toll is not said), and Wikidata, when it has a toll, agrees. None otherwise."""
    by = reported_tolls(reports)
    stated = {n for ns in by.values() for n in ns}
    if len(stated) != 1:
        return None
    n = stated.pop()
    who = sorted(o for o, ns in by.items() if n in ns)
    if wikidata and n not in wikidata:
        return None
    if len(who) >= OWNERS_NEEDED or (who and wikidata == {n}):
        return n, who
    return None


def check(short: Short) -> list[str]:
    problems = []
    allowed = {n.replace(",", "") for f in short.facts for n in f.numbers}
    has_toll = any(f.key == "deaths" for f in short.facts)
    texts = [("title", short.title)] + [(f"beat {i + 1}", b.text) for i, b in enumerate(short.beats)]
    for i, b in enumerate(short.beats):
        if b.card:
            texts.append((f"card {i + 1}", f"{b.card.get('big', '')} {b.card.get('small', '')}"))
    for where, text in texts:
        for num in numbers(text.replace("≈", "")):
            if num not in allowed:
                problems.append(f"{where}: the number {num} isn't backed by any sourced fact")
        problems += [f"{where}: {p}" for p in decorum(text, short.kind, has_toll)]
    for word in re.findall(r"\b[A-Z][A-Z\-]{3,}\b", short.title):
        if word not in ACRONYMS:
            problems.append(f"title: shouting in capitals ({word})")
    if not 15 <= len(short.title) <= 90:
        problems.append(f"title: {len(short.title)} characters (want 15-90)")
    if hindi.devanagari_share(short.title) < TITLE_HINDI:
        problems.append("title: not in Hindi")
    words = len(short.narration.split())
    if not 50 <= words <= 200:
        problems.append(f"narration: {words} words (want 50-200)")
    if hindi.devanagari_share(short.narration) < 0.8:
        problems.append("narration: not in Hindi (Devanagari)")
    if not short.sources or any(not s.startswith("https://") for s in short.sources):
        problems.append("sources: every Short needs https primary sources")
    for f in short.facts:
        if not f.source.startswith("https://"):
            problems.append(f"fact {f.key}: no https source")
    problems += _story(short)
    problems += _shared(short)
    problems += _reported(short)
    if short.scene.get("voice_preview"):
        problems.append("voice: made with the preview voice; it can never be published")
    return problems


def voice_ok(voice: dict | None) -> str | None:
    """Why a narration may not be published (anything but the Sulafat identity), or None."""
    if not voice:
        return "voice: no narration record"
    if voice.get("preview"):
        return "voice: preview voice; never published"
    if voice.get("identity") != "sulafat" or voice.get("engine") not in PUBLISHABLE_VOICES:
        return f"voice: {voice.get('engine')!r} is not the channel's Sulafat voice"
    return None


def _story(short: Short) -> list[str]:
    """Photo Shorts: enough real photos, every one freely licensed, and each one's author credited."""
    from . import compose, media

    problems = []
    photos = short.scene.get("photos", [])
    need = short.scene.get("min_photos") or (2 if short.id.startswith(("kh-", "nw-")) else 3)
    if len(photos) < need:
        problems.append(f"photos: only {len(photos)} (want {need} or more)")
    credits = " ".join(short.credits)
    for p in photos:
        if not media.FREE.match(p.get("license", "")):
            problems.append(f"photo {p.get('file')}: licence {p.get('license')!r} is not free")
        if p.get("page", "") not in credits:
            problems.append(f"photo {p.get('file')}: not credited")
    used = {b.shot for b in short.beats if b.shot.startswith("photo:")}
    if any(int(s.split(":")[1]) >= len(photos) for s in used):
        problems.append("beats: a beat points at a photo that does not exist")
    if "आवाज़: AI" not in compose.DISCLOSURE or "AI" not in compose.AI_BADGE:
        problems.append("end card: the AI-voice disclosure is missing")
    return problems


def _reported(short: Short) -> list[str]:
    """A fact taken from outlet reporting needs OWNERS_NEEDED independent owners among the Short's reports, and the
    outlets it comes from are named in the description."""
    reports = short.scene.get("reporting") or []
    known = {r["owner"] for r in reports}
    urls = {r["url"] for r in reports}
    problems = []
    for f in short.facts:
        if f.owners or f.source in urls:
            who = set(f.owners) & known
            if len(who) < OWNERS_NEEDED:
                problems.append(f"fact {f.key}: {len(who)} independent outlet(s) report it (want {OWNERS_NEEDED})")
    if reports and not short.scene.get("outlets"):
        problems.append("sources: the outlets the facts come from are not named")
    return problems


def _shared(short: Short) -> list[str]:
    """A story Orbitwire also covers needs its own angle, title and photos."""
    from . import orbitwire

    ov = short.scene.get("orbitwire")
    if not ov:
        return []
    problems = []
    angle = ov.get("angle")
    if angle not in orbitwire.ANGLES:
        problems.append("orbitwire: a shared story needs an angle")
    elif not orbitwire.title_fits(short.title, angle):
        problems.append(f"orbitwire: the title must show the {orbitwire.ANGLES[angle]['label']!r} angle")
    taken = set(ov.get("excluded_photos") or [])
    if not ov.get("photo_pool_checked"):
        problems.append("orbitwire: Orbitwire's photos were not checked")
    for p in short.scene.get("photos", []):
        if p.get("file") in taken:
            problems.append(f"orbitwire: photo {p.get('file')} is one Orbitwire would use")
    return problems


def channel_mix(recent_loss_flags: list[bool], loss: bool) -> str | None:
    """At most 2 of any 3 consecutive uploads may be loss stories (YouTube's 2026 'disturbing themes' rule)."""
    window = (recent_loss_flags[-2:] + [loss])
    if loss and sum(window) > 2:
        return "two of the last uploads were loss stories; this one waits for a non-loss Short"
    return None
