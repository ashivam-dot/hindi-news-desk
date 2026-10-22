"""The checks a Short must pass before it can publish: grounded numbers, decorum (in Hindi and English), title rules,
credited free photos, the AI-voice disclosure, the Sulafat voice, Orbitwire's rules for shared stories, and two
independent owners behind any fact taken from trusted outlets' reporting (desk/outlets.py)."""
from __future__ import annotations

import re

from . import config, hindi, match, visuals
from .spec import Short, shot_photos

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
INJURY = {"wounded", "injured", "घायल", "घायलों"}
# A death Short needs a news report whose sentence names the person and says they died: FMKaXjYtmOk (Nana Patekar,
# 2026-10-08; true, but Orbitwire's oSAgE6PbG2k too) went out on Wikidata's P570 and the infobox alone, with
# report_urls: [].
DEATH_SAID = ["died", "dies", "passed away", "passes away", "demise", "is no more", "death of", "dead at",
              "breathed his last", "breathed her last", "निधन", "नहीं रहे", "नहीं रहीं", "देहांत", "अंतिम सांस",
              "आखिरी सांस", "मौत", "दुनिया को अलविदा"]
# A vandalised P570 is when outlets write "X is alive": a sentence that calls the death a hoax, a rumour or false, or
# denies it, never states it, and an article with one never confirms it (the 2026-10-22 on-air review).
DEATH_DENIED = ["hoax*", "fake", "false", "falsely", "rumour*", "rumor*", "is alive", "still alive", "alive and",
                "deny", "denies", "denied", "dismiss*", "not dead", "has not died", "hasn't died", "did not die",
                "didn't die", "never died", "not passed away", "hasn't passed away", "did not pass away", "didn't pass away",
                "incorrect", "reports are wrong", "news is wrong", "is stable", "untrue", "not true", "baseless", "unfounded",
                "misinformation", "is recovering", "doing well", "अफवाह*", "झूठ*", "फर्जी", "खंडन", "जिंदा", "जीवित",
                "स्वस्थ हैं", "स्वस्थ है", "पूरी तरह स्वस्थ", "सलामत", "निधन नहीं", "मौत नहीं", "नहीं हुआ निधन",
                "नहीं हुई मौत", "खबर गलत", "खबरें गलत", "गलत खबर*", "निकली गलत", "खबर*: गलत", "बेबुनियाद", "भ्रामक", "निराधार", "ठीक हैं"]
DEATH_TALK = ["report*", "news", "claim*", "post", "posts", "खबर*", "दावा*", "पोस्ट"]  # what a denial denies
# A denial of an earlier rumour, in an obituary ("Last year, fake reports of his death had circulated"), denies
# nothing now (the 2026-10-22 review: three true obituaries were refused).
DENIED_BEFORE = ["last year", "had circulated", "in the past", "years ago", "पिछले साल", "पिछली बार", "सालों पहले",
                 "साल पहले"]
QUESTION = re.compile(r"\?[\s.\"'’”)\]]*$")  # "X passes away?", also as "X passes away?." in title + ". " + text
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
    return next((w.rstrip("*") for w in words if _at(low, [w])), None)


def _at(low: str, words: list[str]) -> list[tuple[int, int]]:
    """Where words occur in low, a hindi.norm text, as found matches them: (start, end), in order."""
    spans = []
    for w in words:
        stem = hindi.norm(w.rstrip("*"))
        for m in re.finditer(re.escape(stem), low) if stem else ():
            end = m.end()
            while w.endswith("*") and end < len(low) and hindi._letter(low[end]):
                end += 1
            if (m.start() and hindi._letter(low[m.start() - 1])) or (end < len(low) and hindi._letter(low[end])):
                continue
            spans.append((m.start(), end))
    return sorted(spans)


def decorum(text: str, kind: str, agreed_toll: bool, hurt_ok: bool = False) -> list[str]:
    """hurt_ok: the injured are an agreed fact (a case file's `hurt`), so the injury words may be said; deaths may
    still not be."""
    problems = []
    word = found(text, BANNED)
    if word:
        problems.append(f"banned wording {word!r}")
    if EMOJI.search(text):
        problems.append("emoji")
    if kind in ("incident", "explainer") and not agreed_toll:
        word = found(text, [w for w in CASUALTY if not (hurt_ok and w in INJURY)])
        if word:
            problems.append(f"casualties without an agreed toll ({word})")
    return problems


def numbers(text: str) -> list[str]:
    return [v for v, _ in hindi.numbers(text)]


def reported(needle: str, reports: list[dict]) -> list[str]:
    """The independent owners whose articles write needle (whole words, Hindi spellings normalised)."""
    return sorted({r["owner"] for r in reports if r.get("text") and hindi.contains(r["text"], needle)})


SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n+")


# A sentence about the person's relative never states their death: "AR Rahman's mother Kareema Begum passes away",
# "Kamla Advani, wife of ... L.K. Advani, died", "... नायर की पत्नी का निधन" (the 2026-10-22 fifth review).
_KIN = "mother|father|wife|husband|son|daughter|brother|sister|widow|grandmother|grandfather|uncle|aunt|nephew|niece|" \
       "father-in-law|mother-in-law|son-in-law|daughter-in-law|brother-in-law|sister-in-law|grandson|granddaughter"
_KIN_HI = "मां|माँ|माता|पिता|पत्नी|पति|बेटे|बेटा|बेटी|भाई|बहन|दादा|दादी|नाना|नानी|चाचा|चाची|मामा|मामी|ससुर|सास|बहू|दामाद|भतीजे|भतीजा|भतीजी|पोते|पोता|पोती"
RELATIVE = re.compile(rf"['’]s\s+(?:late\s+|elder\s+|younger\s+|step-?)?(?:{_KIN})\b|\b(?:{_KIN})\s+of\b"
                      rf"|(?:की|के|का)\s+(?:दिवंगत\s+)?(?:{_KIN_HI})(?![\u0900-\u097f])", re.I)


def states_death(text: str, names: list[str]) -> str | None:
    """The first sentence of text that names one of names (whole words) and says they died (DEATH_SAID), or None. A
    sentence that also denies it (DEATH_DENIED), or asks it ("X passed away?"), says nothing."""
    for s in SENTENCE.split(text or ""):
        if found(s, DEATH_SAID) and not found(s, DEATH_DENIED) and not QUESTION.search(s) and not RELATIVE.search(s) \
                and any(n and hindi.contains(s, n) for n in names):
            return s.strip()
    return None


def denies_death(text: str, names: list[str]) -> str | None:
    """The first sentence of text that denies (DEATH_DENIED) the person, a death or reports of one (DEATH_TALK), or
    None: the article is about a hoax, whatever its other sentences say ("His manager said the reports are false")."""
    for s in SENTENCE.split(text or ""):
        if QUESTION.search(s) and found(s, DEATH_SAID) and any(n and hindi.contains(s, n) for n in names):
            return s.strip()  # "X passed away? Family says ..." is a hoax headline, never an obituary's
        if found(s, DEATH_DENIED) and not found(s, DENIED_BEFORE) \
                and (found(s, DEATH_SAID + DEATH_TALK) or any(n and hindi.contains(s, n) for n in names)):
            return s.strip()
    return None


# A named person's demand, allegation, words or order are said only as the reporting gives them: YM2dyGiYNJQ ("राउत
# की फडणवीस से इस्तीफे की मांग", 2026-10-20) gave Sanjay Raut the resignation demand Congress's Harshwardhan Sapkal
# made; Raut alleged "jungle raj" and asked for President's Rule. Each claim: its Hindi words, then the other words
# reports back it with.
CLAIMS = {
    "demand": (["मांग", "मांगा", "मांगी", "मांगे"],
               ["demand*", "call for", "calls for", "called for", "calling for", "sought", "seek*", "urg*",
                "asked for", "asks for"]),
    "allegation": (["आरोप", "आरोपों"], ["alleg*", "accus*", "charg*", "blam*"]),  # never आरोपी (the accused)
    # A report's words for saying are many ("claimed", "wrote on X", "बताया"); a Short's are कहा and बोले.
    "statement": (["कहा", "कही", "कहना", "कहते", "बोले", "बोलीं", "बोला"],
                  ["said", "says", "say", "saying", "claim*", "told", "stated", "added", "asserted", "wrote", "posted",
                   "according to", "बताया", "लिखा"]),
    "order": (["आदेश", "आदेशों", "निर्देश", "निर्देशों"], ["order*", "direct*", "instruct*"]),
}
# What a claim is about, when its clause says: the reporting's sentence must say it too.
OBJECTS = {
    "resignation": (["इस्तीफ*"], ["resign*"]),
    "President's Rule": (["राष्ट्रपति शासन"], ["President's Rule", "President’s Rule", "President Rule"]),
    "arrest": (["गिरफ्तार*"], ["arrest*"]),
    "probe": (["जांच"], ["probe*", "investigat*", "inquiry", "enquiry"]),
    "apology": (["माफी"], ["apolog*"]),
    "dismissal": (["बर्खास्त*"], ["dismiss*", "sack*"]),
}
# ने, की, का or के after a name marks who makes the claim ("राउत की ... मांग"); से, को or पर marks who it is put to.
# की, का or के with a ने before the claim word is whose, not who: "इमरान खान के वकील ने कहा" is the lawyer's.
CLAIMANT = re.compile(r"\s*(ने|की|का|के)" + hindi._END)
# Words that end many institutions' names and so never name one alone: "बॉम्बे हाई कोर्ट" is not "Supreme Court".
NOT_A_SURNAME = {"court", "कोर्ट", "अदालत", "ministry", "मंत्रालय", "commission", "आयोग", "government", "सरकार",
                 "police", "पुलिस", "party", "पार्टी", "department", "विभाग", "council", "परिषद", "office", "कार्यालय"}


def _name_forms(p: dict) -> list[str]:
    """A names entry as reports write it: in full, or by its last word (Raut for Sanjay Raut), unless that word ends
    many names (NOT_A_SURNAME)."""
    forms = [f for f in (p.get("hi"), p.get("en")) if f]
    return forms + [f.split()[-1] for f in forms if len(f.split()) > 1 and len(f.split()[-1]) >= 3
                    and hindi.norm(f.split()[-1]) not in {hindi.norm(w) for w in NOT_A_SURNAME}]


def claims(text: str, names: list[dict]) -> list[tuple[dict, str, str | None, str]]:
    """(names entry, claim, its OBJECTS key or None, the sentence) for each Hindi claim word in text that a listed name
    makes. Within a sentence the claimant is the nearest name before the word that ने/की/का/के marks, skipping one
    whose की/का/के an object or another ने follows (फडणवीस के इस्तीफे: whose resignation, not who asks; इमरान खान के
    वकील ने: the lawyer), or else a name right before it ("राउत बोले"). The object is the first OBJECTS word between
    the claimant and the claim word, and after the sentence's previous claim word."""
    out = []
    for s in SENTENCE.split(text or ""):
        low = hindi.norm(s)
        heard = []
        for p in names:
            heard += [(a, b, p) for a, b in _at(low, _name_forms(p))]
        objects = [(a, b, k) for k, (hi, _) in OBJECTS.items() for a, b in _at(low, hi)]
        last = 0
        for start, end, claim in sorted((a, b, c) for c, (hi, _) in CLAIMS.items() for a, b in _at(low, hi)):
            who = None
            for a, b, p in sorted((h for h in heard if h[1] <= start), key=lambda h: -h[1]):
                m = CLAIMANT.match(low, b)
                whose = m and m.group(1) != "ने"
                if whose and _at(low[m.end():start], ["ने"]):
                    continue
                if m and not (whose and any(o[0] == m.end() + 1 or o[0] == m.end() for o in objects)):
                    who = (b, p)
                    break
                if not low[b:start].strip(" ,:'\"‘’“”"):
                    who = (b, p)
                    break
            if who:
                what = next((k for a, _, k in objects if max(who[0], last) <= a < start), None)
                out.append((who[1], claim, what, s[:200].strip()))
            last = end
    return out


def _says(sentence: str, forms: list[str]) -> bool:
    return bool(_at(hindi.norm(sentence), forms))


PRONOUN_START = re.compile(r"\s*(?:he|she|उन्होंने)(?![\wऀ-ॿ])", re.I)
FUZZY_SURNAME = 6  # letters: a shorter surname sounds like ordinary words (रात ~ Raut) and other names (रावत)


def claim_backers(p: dict, claim: str, what: str | None, reports: list[dict], ground: str = "",
                  others: list[dict] | None = None) -> list[str]:
    """The owners whose reports have one sentence naming p, the claim and its object ("ground" when the
    Wikipedia/Wikidata ground has it). others: the other listed names, none of whom a pronoun's sentence before may
    name."""
    words = CLAIMS[claim][0] + CLAIMS[claim][1]
    objs = OBJECTS[what][0] + OBJECTS[what][1] if what else None
    names = _name_forms(p)
    last = (p.get("en") or "").split()[-1:]
    fuzzy = last[0] if last and len(last[0]) >= FUZZY_SURNAME else None
    other_forms = [f for o in others or [] if o is not p for f in _name_forms(o)]

    def named(s: str) -> bool:  # also in another Hindi spelling of a long surname (फडनवीस, फड़नवीस for फडणवीस)
        return _says(s, names) or bool(fuzzy) and any(hindi.likeness(w.replace("़", ""), fuzzy) >= 0.8
                                                      for w in re.findall(r"[ऀ-ॿ]{4,}", s))

    def backs(s: str, before: str = "") -> bool:
        # "Fadnavis visited the site. He said ...": a pronoun speaks for the one person the sentence before names.
        who = named(s) or bool(PRONOUN_START.match(s)) and named(before) and not _says(before, other_forms)
        return who and _says(s, words) and (objs is None or _says(s, objs))

    def backed(text: str) -> bool:
        parts = SENTENCE.split(text)
        return any(backs(s, parts[i - 1] if i else "") for i, s in enumerate(parts))

    who = {r["owner"] for r in reports if backed(f"{r.get('title') or ''}. {r.get('text') or ''}")}
    return sorted(who) + (["ground"] if backed(ground or "") else [])


def unattributed(text: str, names: list[dict], reports: list[dict], ground: str = "") -> list[str]:
    """Each claim in text (claims) no OWNERS_NEEDED owners' reports (nor the ground) give to the same person, as a
    problem that shows the retry what the reporting does say."""
    problems = []
    for p, claim, what, clause in claims(text, names):
        backers = claim_backers(p, claim, what, reports, ground, names)
        if "ground" in backers or len(backers) >= OWNERS_NEEDED:
            continue
        about = f" ({what})" if what else ""
        words = CLAIMS[claim][0] + CLAIMS[claim][1]
        objs = OBJECTS[what][0] + OBJECTS[what][1] if what else []
        said = next((s.strip() for r in reports for s in SENTENCE.split(r.get("text") or "")
                     if _says(s, words) and (not objs or _says(s, objs))), None)
        problems.append(f"\"{clause}\" gives {p.get('en') or p.get('hi')} a {claim}{about} that no {OWNERS_NEEDED} "
                        f"outlets' reports give them ({len(backers)} do): say who made it as the reporting does"
                        + (f" (\"{said[:160]}\")" if said else "") + ", or leave it out")
    return problems


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
    hurt_ok = any(f.key == "injured" for f in short.facts)
    texts = [("title", short.title)] + [(f"beat {i + 1}", b.text) for i, b in enumerate(short.beats)]
    for i, b in enumerate(short.beats):
        if b.card:
            texts.append((f"card {i + 1}", f"{b.card.get('big', '')} {b.card.get('small', '')}"))
    for where, text in texts:
        for num in numbers(text.replace("≈", "")):
            if num not in allowed:
                problems.append(f"{where}: the number {num} isn't backed by any sourced fact")
        problems += [f"{where}: {p}" for p in decorum(text, short.kind, has_toll, hurt_ok)]
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
    problems += _death_reported(short)
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
    shown = [shot_photos(b.shot) for b in short.beats if b.shot.startswith("photo:")]
    if any(not s or max(s) >= len(photos) for s in shown):
        problems.append("beats: a beat points at a photo that does not exist")
    # One portrait for a whole Short loses the viewer (Tiger Shroff, 2026-10-20: one photo for 47 s). A text card's
    # blurred backdrop is not a picture on screen (match.problems counts the cards against their own ceiling).
    shown = [shot_photos(b.shot) for b in short.beats if b.shot.startswith("photo:") and b.plate != match.CARD]
    want = short.scene.get("min_visuals", visuals.MIN_VISUALS)
    if len({i for s in shown for i in s}) < min(want, len(shown)):
        problems.append(f"pictures: only {len({i for s in shown for i in s})} different ones on screen (want {want})")
    if "आवाज़: AI" not in compose.DISCLOSURE or "AI" not in compose.AI_BADGE:
        problems.append("end card: the AI-voice disclosure is missing")
    return problems + said_is_shown(short)


def said_is_shown(short: Short, views: list[dict] | None = None) -> list[str]:
    """What the voice says is what the screen shows: a beat that names a person the Short has a photo of shows
    them, and a person the title names is on screen. The Modi Dussehra Short (2026-10-21) named Narendra Modi in its
    title and three beats and showed Delhi's temples and markets. And the other way round (shown_is_said)."""
    problems = held(short) + shown_is_said(short, views)
    beats = [(b.text, set(shot_photos(b.shot))) for b in short.beats if b.shot.startswith("photo:")]
    on_screen = set().union(*(s for _, s in beats)) if beats else set()
    for c in short.scene.get("cast") or []:
        if c.get("kind") != "person":
            continue
        theirs = set(c.get("photos") or [])
        in_title = bool(c.get("hi") and hindi.contains(short.title, c["hi"])) or \
            bool(c.get("en") and re.search(rf"\b{re.escape(c['en'])}\b", short.title, re.I))
        if in_title and not theirs & on_screen:
            problems.append(f"pictures: the title names {c.get('en')} but no photo of them is on screen")
        if not theirs:
            continue
        for n, (say, shown) in enumerate(beats, 1):
            if visuals.mentions(say, [c]) and not theirs & shown and not _names_other_shown(say, shown, short):
                problems.append(f"pictures: beat {n} names {c.get('en')} but shows someone or something else")
    cast = short.scene.get("cast")
    for n, b in enumerate(short.beats, 1):
        # A text card (match.CARD) is the words alone, over no place: never trimmed (card_over), never flagged here.
        if cast is not None and b.shot.startswith("photo:") and b.plate != match.CARD and \
                visuals.place_card(b.card) and visuals.card_over(b.card, shot_photos(b.shot), cast) != b.card:
            problems.append(f"pictures: card {n} names the place {b.card['big']} over another picture")
    return problems


def shown_is_said(short: Short, views: list[dict] | None = None) -> list[str]:
    """What the screen shows is what the voice says (SYNC-AUDIT 4.1 step 7, match.problems): every picture is of
    something its beat names, on screen at the right time of life and the right event, every card over its own
    picture, a hook whose names the narration says, and the paired ceilings (maps at most 40% of the picture time,
    cards at most half the beats and never three in a row, at most two pronoun beats, a place's maps one picture).
    Three audits (2026-10-22) found 98 of 145 beats showing something the voice was not talking about; the gate
    passed all of them. Run on the saved Short (cli.prepare, publish) and on render.json's views after the render.
    The legacy matcher (config.MATCHER, the rollback) fills beats the old way, which this gate would refuse."""
    if config.MATCHER == "legacy":
        return []
    return match.problems(short, views)


HELD_RUN = match.HELD_RUN  # beats in a row one picture may not fill (match.plan keeps under it by construction)


def held(short: Short) -> list[str]:
    """No picture stands under HELD_RUN beats in a row or under more than half of a Short's beats. A place's wide
    and close maps count as one picture: the Kota court Short (2026-10-21) showed Kota's maps under six of seven
    beats, the injured and the recovered motorcycle included. The grouping is match.group's (a spot's maps count with
    its city's), and a text card's backdrop is not a picture held: the card ends the run."""
    photos = short.scene.get("photos") or []
    groups = match.group(photos, match.cast_of(short))

    beats = [{match.held_key(i, photos, groups) for i in shot_photos(b.shot)} if b.plate != match.CARD else set() for b in short.beats
             if b.shot.startswith("photo:")]
    problems, counts, run = [], {}, {}
    for n, keys in enumerate(beats):
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
        run = {k: run.get(k, 0) + 1 for k in keys}
        for k, r in run.items():
            if r == HELD_RUN:
                problems.append(f"pictures: {_label(k, photos)} stays on screen for {HELD_RUN} beats in a row")
    for k, c in counts.items():
        if len(beats) >= 5 and c * 2 > len(beats):
            problems.append(f"pictures: {_label(k, photos)} is under {c} of {len(beats)} beats")
    return problems


def _label(k, photos: list[dict]) -> str:
    return k if isinstance(k, str) else (photos[k].get("file") or f"photo {k}")


def _names_other_shown(say: str, shown: set[int], short: Short) -> bool:
    """The beat also names another person whose photo it shows (two people in one beat: one of them is enough)."""
    for c in short.scene.get("cast") or []:
        if c.get("kind") == "person" and set(c.get("photos") or []) & shown and visuals.mentions(say, [c]):
            return True
    return False


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


def _death_reported(short: Short) -> list[str]:
    """A death Short (Wikidata P570 and the infobox) also needs at least one news report that states the death: its
    scene's death_reports, each an https article with the sentence that names the person and says they died."""
    if short.kind != "death":
        return []
    rows = [r for r in short.scene.get("death_reports") or []
            if (r.get("url") or "").startswith("https://") and states_death(r.get("says", ""), [r.get("name", "")])]
    return [] if rows else ["sources: no news report states the death (Wikidata alone is not enough)"]


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
