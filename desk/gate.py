"""The checks a Short must pass before it can publish: grounded numbers, decorum (in Hindi and English), title rules,
credited free photos, the AI-voice disclosure, the Sulafat voice, and Orbitwire's rules for shared stories."""
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
            "BRICS", "SAARC", "ASEAN", "AI"}
# Without a death toll that two sources agree on, an incident Short may not speak of casualties at all.
CASUALTY = ["casualt*", "death toll", "killed", "fatalit*", "wounded", "injured", "मौत", "मौतें", "मौतों", "मारे",
            "मृत", "मृतक", "मृतकों", "मृतकों", "घायल", "घायलों", "हताहत", "जान गई", "जानें", "जान गंवा*",
            "जान गँवा*", "निधन", "शहीद"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F000-\U0001F2FF]")
# The voice identities a Short may publish with: Gemini's Sulafat, or Chatterbox cloning Sulafat's reference clip.
PUBLISHABLE_VOICES = {"gemini-sulafat", "chatterbox-sulafat-clone"}


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
    if kind == "incident" and not agreed_toll:
        word = found(text, CASUALTY)
        if word:
            problems.append(f"casualties without an agreed toll ({word})")
    return problems


def numbers(text: str) -> list[str]:
    return [v for v, _ in hindi.numbers(text)]


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
    if hindi.devanagari_share(short.title) < 0.6:
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
    if len(photos) < 3:
        problems.append(f"photos: only {len(photos)} (want 3 or more)")
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
