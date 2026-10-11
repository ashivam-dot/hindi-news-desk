"""Hindi story Shorts: real photos of the person or event, and a narrated story with feeling, written in Hindi from
English Wikipedia, Hindi Wikipedia (when it has the article) and the confirmed Wikidata facts.

The model writes; code decides. Gemini (free tier, GEMINI_API_KEY) writes first and the local Gemma 4 model steps in
when Gemini can't answer. Every number in the script must have its value in a source (Devanagari digits and लाख or
करोड़ included), every proper noun must be listed as a {hi, en} pair whose English is in the sources and whose Hindi
is in the script (Wikidata's Hindi label wins when there is one), Latin-script words must be in the English source,
and a second model pass lists anything unsupported. A failing draft is rewritten up to three times (the fact check
runs only on drafts that pass the code gates, so it needs rewrites left), then the story is dropped.
Death and casualty facts still pass the same two-source gates as Orbitwire's.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, faces, gate, gemini, hindi, llm, media, orbitwire, stories, trends, wiki
from .spec import Beat, Fact, Short

WORK = Path(__file__).resolve().parents[1] / "work"
MIN_PHOTOS = 3
MAX_DEATH_DAYS = 7
IST = timezone(timedelta(hours=5, minutes=30))
OUTRO = "पूरी जानकारी और सभी स्रोत विवरण में दिए गए हैं।"
CREDIT = "तथ्य: Wikipedia (CC BY-SA 4.0) और Wikidata (CC0); तस्वीरें: Wikimedia Commons (लाइसेंस नीचे)"
MIN_WORDS, MAX_WORDS = 80, 135
DRAFTS = 4
PLACE_FACE = 0.06  # a face this share of a place photo's shorter side features a person
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "beats": {"type": "array", "minItems": 6, "maxItems": 9, "items": {
            "type": "object",
            "properties": {"say": {"type": "string"}, "photo": {"type": "integer"}, "caption": {"type": "string"}},
            "required": ["say", "photo", "caption"]}},
        "names": {"type": "array", "items": {
            "type": "object", "properties": {"hi": {"type": "string"}, "en": {"type": "string"}},
            "required": ["hi", "en"]}},
    },
    "required": ["title", "beats", "names"],
}
CHECK_SCHEMA = {"type": "object", "properties": {"unsupported": {"type": "array", "items": {"type": "string"}}},
                "required": ["unsupported"]}

SYSTEM = ("You are the head writer of a Hindi YouTube Shorts news channel for Indian viewers. You tell the biggest "
          "stories in India and the world in natural, spoken Hindi written in Devanagari, the way a respected Hindi "
          "news anchor tells a story to one listener: warm, clear and human, with feeling that fits the story, never "
          "sensational. Terms Hindi news keeps in English (flight numbers, agency names such as NDRF or NASA) may stay "
          "in Latin letters. You never invent anything.")

DEATH_BRIEF = """STORY: {name} has died. Write a Hindi tribute Short that makes a viewer who barely knew {name} feel the
loss, and makes a fan feel {pronoun} was honoured.

Shape:
1. Hook (beat 1, under 14 words): say plainly that {name} has died (use respectful Hindi such as "नहीं रहे" or
   "का निधन"), with the one detail that makes it matter.
2. Where {pronoun} began, or the struggle before success.
3. The turning point or breakthrough, naming the specific work from the SOURCE.
4. The work people loved most, and what made {object} different from everyone else.
5. A human detail from the SOURCE that shows who {pronoun} was off screen or off stage.
6. Legacy: what {pronoun} leaves behind. The last beat is one short, moving sentence.
Do not describe the cause or manner of death unless the SOURCE states it plainly; never mention suicide."""

INCIDENT_BRIEF = """STORY: {name}. Write a Hindi news Short that helps a viewer understand what happened and why
everyone is watching, with compassion for everyone affected.

Shape:
1. Hook (beat 1, under 14 words): what happened and where, stated plainly, with the detail that makes it matter.
2. The moment it began, in order, as a story.
3. The people involved and what they faced, with official figures only if the SOURCE gives them.
4. The response: rescuers, officials, investigators.
5. What is still unknown or under investigation, said honestly.
6. Why it matters now. The last beat is one short, steady sentence.
Never name or describe any attacker, perpetrator or suspect. Never guess at causes. No graphic detail of injuries or
death."""

PROTEST_BRIEF = """STORY: {name}. Write a Hindi news Short that explains, fairly and calmly, what this protest or
movement is, why people took to the streets, and where it stands now.

Shape:
1. Hook (beat 1, under 14 words): the newest development in the SOURCE, stated plainly.
2. How it began: the trigger, in order, as a story.
3. Who is involved and what they demand, attributed ("आयोजकों का कहना है", "पार्टी का कहना है").
4. How the government, police or courts responded, attributed to them.
5. The turning point or the latest step.
6. What happens next, or what is still unresolved. The last beat is one short, steady sentence.
Be strictly neutral: give each side's position as the SOURCE states it, never take a side, never mock or praise any
person, party, community or religion, and use no loaded words. Attribute every disputed claim and every injury,
arrest or crowd figure to whoever reported it ("पुलिस के मुताबिक", "आयोजकों के अनुसार"). Never urge anyone to join or
avoid a protest. Never mention suicide."""

RULES = """RULES (all mandatory):
- Use ONLY information in CONFIRMED FACTS and the SOURCES. Never add a name, title, number, place, date, quote, award
  or relationship that is not written there. If you are unsure, leave it out.
- Write in Hindi (Devanagari): simple, spoken Hindi of a good Hindi news bulletin, neither heavily Sanskritised nor
  slang. 7 or 8 beats and 95 to 120 Hindi words in total (about 45 seconds spoken). Each beat is one or two spoken
  sentences of 10 to 18 words. Count the words before you answer.
- Every beat must carry a specific fact from the SOURCES (a work, a year, an honour, a choice they made); feeling
  comes from how you tell those facts, not from vague praise.
- Tell it as a story, not a list: vary how beats open, and never start more than 2 beats with the same word.
- Write every number as digits: years (1994), ages (75), dates ("10 अक्टूबर 2026"), and big numbers with लाख or
  करोड़ ("3 लाख", "1.5 करोड़"). A number must be exactly what the SOURCES say (a million is 10 लाख).
- No hype or clickbait (सनसनीखेज, चौंकाने वाला, खौफनाक, ब्रेकिंग, बड़ी खबर), no emoji, no questions to the viewer, no
  request to like, share, subscribe or follow.
- names: list EVERY proper noun you used (people, places, organisations, works, events, awards) as
  {{"hi": the name exactly as written in your Hindi text, "en": the same name exactly as the English SOURCE writes
  it}}. Where HINDI NAMES gives a Hindi spelling, use that spelling.
- photo: the index of the PHOTO that best fits the beat. Beat 1 uses photo {best}. Use every photo at least once if
  you can, and the same photo at most twice.
- caption: 1 to 4 Hindi words shown on screen that match what the beat says: the work it names with its year, a
  role, an honour, or a year. Never a place name: viewers read a place over a photo as where the photo was taken.
- title: Hindi, 25 to 70 characters, factual and moving, includes {name_hi}, no clickbait, no capitals for effect.
Return only the JSON."""


class Pen:
    """Gemini first, then the local Gemma model (started only if needed). Records which model answered each call."""

    def __init__(self, local: str | None = None):
        self.local_name = local or llm.DEFAULT
        self.local = None
        self.used: list[str] = []

    def chat(self, messages: list[dict], schema: dict | None = None, temperature: float = 0.7,
             max_tokens: int = 2400) -> dict | str:
        if gemini.available():
            try:
                answer, model = gemini.chat(messages, schema, temperature, max_tokens)
                self.used.append(model)
                return answer
            except gemini.Unavailable:
                pass
        if self.local is None:
            self.local = llm.Model(self.local_name).__enter__()
        self.used.append(self.local_name)
        return self.local.chat(messages, schema, temperature=temperature, max_tokens=max_tokens)

    def close(self) -> None:
        if self.local is not None:
            self.local.__exit__(None, None, None)
            self.local = None

    def __enter__(self) -> "Pen":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _headline_ok(headline: str, values: set[str], ground: str) -> bool:
    """A headline whose numbers and names the article confirms (others may be about another event, or unverified)."""
    if hindi.devanagari_share(headline) > 0.3 or hindi.unsupported_numbers(headline, values):
        return False
    low = ground.lower()
    words = re.findall(r"\b[A-Z][\w'’\-]+", headline)[1:]
    return all(re.sub(r"['’]s$", "", w).lower().strip("'’-") in low for w in words)


def _messages(brief: str, facts: list[str], source_en: str, source_hi: str, photos: list[dict], name_hi: str,
              hi_names: dict[str, str], headlines: list[str] | None = None) -> list[dict]:
    listing = "\n".join(f"{i}: {p['description'] or p['file']}" for i, p in enumerate(photos))
    lead = ""
    if headlines:
        lead = ("\n\nTODAY'S LEAD HEADLINES (context only: use them to choose the angle and what to put first, but "
                "state only facts that are in CONFIRMED FACTS or the SOURCES):\n" + "\n".join(f"- {h}" for h in headlines))
    names = "\n".join(f"- {en} = {hi}" for en, hi in hi_names.items()) or "- (none)"
    user = (brief + "\n\nCONFIRMED FACTS:\n" + "\n".join(f"- {f}" for f in facts)
            + "\n\nSOURCE (English Wikipedia):\n" + source_en
            + ("\n\nSOURCE (Hindi Wikipedia):\n" + source_hi if source_hi else "")
            + "\n\nHINDI NAMES (Wikidata's Hindi labels; use these spellings):\n" + names
            + lead + "\n\nPHOTOS:\n" + listing + "\n\n" + RULES.format(best=0, name_hi=name_hi))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _check_messages(script: str, names: list[dict], facts: list[str], source_en: str, source_hi: str,
                    doubtful: list[dict]) -> list[dict]:
    pairs = "\n".join(f"- {p['hi']} = {p['en']}" for p in names) or "- (none)"
    double = ""
    if doubtful:
        double = ("\n\nPAIRS TO DOUBLE-CHECK (their spellings differ a lot; list any whose Hindi does not name the same "
                  "thing as its English):\n" + "\n".join(f"- {p['hi']} = {p['en']}" for p in doubtful))
    user = ("SCRIPT is a Hindi narration. List every statement in SCRIPT that is not directly supported by CONFIRMED "
            "FACTS or the SOURCES (English or Hindi): any name, title, number, date, place, award, relationship, "
            "quote, cause or superlative that the sources do not state, and any number that differs from the "
            "sources' (10 लाख is one million, 1 करोड़ is ten million). Also list any person, place, organisation or "
            "work named in SCRIPT that is missing from NAMES. Emotional or figurative phrasing that asserts no new "
            "fact (\"एक युग का अंत\", \"हमेशा याद रहेंगे\") is fine. Check only what SCRIPT says: never list a fact "
            "that only the SOURCES mention. Write each item in English, quoting the exact Hindi words from SCRIPT. "
            "Return {\"unsupported\": []} when everything is supported."
            "\n\nCONFIRMED FACTS:\n" + "\n".join(f"- {f}" for f in facts) + "\n\nSOURCE (English):\n" + source_en
            + ("\n\nSOURCE (Hindi):\n" + source_hi if source_hi else "") + "\n\nNAMES:\n" + pairs + double
            + "\n\nSCRIPT:\n" + script)
    return [{"role": "system", "content": "You are a meticulous, bilingual (Hindi and English) fact-checker for a "
                                          "news channel."},
            {"role": "user", "content": user}]


def _today_ist() -> date:
    return datetime.now(IST).date()


def not_today(text: str) -> list[str]:
    """Problems for wording that dates an older event to today."""
    hits = re.findall(r"(?<![\u0900-\u097F])(आज|अभी)(?!\s*भी)(?![\u0900-\u097F])", text)
    return ["this did not happen today: remove आज/अभी and give the date"] if hits else []


def script_text(draft: dict) -> str:
    return " ".join(b.get("say", "") + " " + b.get("caption", "") for b in draft.get("beats", [])) + " " + \
        draft.get("title", "")


def subject_in(text: str, subject: dict, names: list[dict]) -> bool:
    """The story's own name is said: its Wikidata Hindi label (or a person's surname in it), or the Hindi the writer
    gave for its English name."""
    options = []
    if subject.get("hi"):
        options.append(subject["hi"])
        if subject.get("person") and len(subject["hi"].split()) > 1:
            options.append(subject["hi"].split()[-1])
    en = subject["en"].lower()
    last = en.split()[-1] if en.split() else en
    for p in names:
        pe = (p.get("en") or "").lower()
        if pe and (pe == en or en in pe or (subject.get("person") and last in pe.split())
                   or (len(pe.split()) >= 2 and pe in en)):
            options.append(p.get("hi", ""))
    return any(o and hindi.contains(text, o) for o in options)


def validate(draft: dict, photos: list[dict], subject: dict, ground_en: str, ground_hi: str,
             hi_names: dict[str, str], banned_names: list[str], kind: str, agreed_toll: bool,
             angle: str | None = None) -> tuple[list[str], list[dict]]:
    """Problems with a draft, and the name pairs to double-check in the fact-check pass."""
    problems, doubtful = [], []
    beats = draft.get("beats") or []
    says = " ".join(b.get("say", "") for b in beats)
    words = len(says.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"the script has {words} words; it must have 95 to 120")
    if hindi.devanagari_share(says) < 0.85:
        problems.append("write the narration in Hindi (Devanagari)")
    names = [p for p in draft.get("names") or [] if isinstance(p, dict)]
    if not beats or not subject_in(beats[0].get("say", ""), subject, names):
        problems.append(f"beat 1 must name {subject.get('hi') or subject['en']} in Hindi, and list it in names")
    for b in beats:
        if not isinstance(b.get("photo"), int) or not 0 <= b["photo"] < len(photos):
            problems.append(f"photo {b.get('photo')} does not exist")
    text = script_text(draft)
    values = hindi.values(ground_en + "\n" + ground_hi)
    bad = hindi.unsupported_numbers(text, values)
    if bad:
        problems.append("these numbers are not in the sources: " + ", ".join(bad))
    wikidata = {en.lower(): hi for en, hi in hi_names.items()}
    for p in names:
        hi, en = (p.get("hi") or "").strip(), (p.get("en") or "").strip()
        if not hi or not en:
            problems.append("every names entry needs both hi and en")
            continue
        if not hindi.contains(text, hi):
            problems.append(f"names lists {hi!r}, but the script never writes it exactly like that")
        en_ok, hi_ok = hindi.contains(ground_en, en), hindi.contains(ground_hi, hi)
        if not (en_ok or hi_ok):
            problems.append(f"{en} ({hi}) is not in the sources")
        label = wikidata.get(en.lower())
        if label and hindi.norm(label) != hindi.norm(hi) and not hindi.contains(text, label):
            problems.append(f"write {en} as {label} (Wikidata's Hindi name), not {hi}")
        elif not label and not hi_ok and not hindi.sounds_alike(hi, en):
            doubtful.append({"hi": hi, "en": en})
    listed = " ".join(p.get("en", "") for p in names).lower()
    for w in sorted(set(hindi.latin_words(text))):
        if w.upper() in gate.ACRONYMS and w.upper() == w:
            continue
        if not hindi.contains(ground_en, w):
            problems.append(f"{w!r} is not in the English source")
    for person in banned_names:
        for token in re.findall(r"[A-Z][a-z]{2,}", person):
            if re.search(r"\b" + token + r"\b", text) or token.lower() in listed.split():
                problems.append(f"never name a perpetrator ({token})")
    problems += gate.decorum(text, "incident" if kind in ("incident", "protest") else kind, agreed_toll)
    if angle and not orbitwire.title_fits(draft.get("title", ""), angle):
        problems.append(f"the title must show this Short's angle ({orbitwire.ANGLES[angle]['label']})")
    return problems, doubtful


def unlisted_but_sourced(item: str, ground_en: str) -> bool:
    """A fact-check item that only says a name is missing from NAMES, for a name the English source does state."""
    if not re.search(r"missing from (the )?NAMES", item, re.I) or re.search(r"\bnot (directly )?(supported|in)\b", item,
                                                                            re.I):
        return False
    english = re.findall(r"\(([A-Z][^()\u0900-\u097F]{2,60})\)|['\"‘“]([A-Z][^'\"’”\u0900-\u097F]{2,60})['\"’”]", item)
    return any(hindi.contains(ground_en, a or b) for a, b in english)


def monotone(draft: dict) -> list[str]:
    """Openings repeated so often that the script reads as a list."""
    openers = [re.sub(r"[^\w\u0900-\u097f]", "", b["say"].split()[0]).lower() for b in draft.get("beats", [])
               if b.get("say", "").split()]
    return [f"{openers.count(w)} beats start with \"{w}\"; start at most 2 beats with the same word"
            for w in sorted(set(openers)) if openers.count(w) > 2]


def write(kind: str, subject: dict, pronoun: str, facts: list[str], source_en: str, source_hi: str,
          photos: list[dict], hi_names: dict[str, str], banned_names: list[str] | None = None,
          agreed_toll: bool = False, log_path: Path | None = None, headlines: list[str] | None = None,
          angle: str | None = None, pen: Pen | None = None,
          today_ok: bool = True) -> tuple[dict, list[dict], list[str]]:
    """The script as {title, beats: [{say, photo, caption}], names}, the log of rejected drafts (also kept at
    log_path), and the models that answered. kind is "death", "incident" or "protest"."""
    obj = {"He": "him", "She": "her"}.get(pronoun, "them")
    brief = {"death": DEATH_BRIEF, "protest": PROTEST_BRIEF}.get(kind, INCIDENT_BRIEF)
    brief = brief.format(name=subject["en"], pronoun=pronoun.lower(), object=obj)
    if angle:
        brief += (f"\n\nANGLE ({orbitwire.ANGLES[angle]['label']}): the channel's English sister channel already told "
                  f"this story its usual way, so this Hindi Short must be different. {orbitwire.ANGLES[angle]['brief']} "
                  "Use a different hook from a plain retelling.")
    if not today_ok:
        brief += ("\n\nThis did not happen today: never write आज or अभी about it (आज भी for a lasting legacy is "
                  "fine); give the date instead.")
    name_hi = (f'"{subject["hi"]}"' if subject.get("hi")
               else f"the Hindi (Devanagari) name you give {subject['en']} in names, not the English title")
    messages = _messages(brief, facts, source_en, source_hi, photos, name_hi, hi_names, headlines)
    ground_en = source_en + "\n" + "\n".join(facts) + "\n" + "\n".join(p["description"] for p in photos)
    ground_hi = source_hi + "\n" + "\n".join(facts) + "\n" + "\n".join(hi_names.values())
    log = []
    own = pen is None
    pen = pen or Pen()
    try:
        for attempt in range(DRAFTS):
            ignored = []
            draft = pen.chat(messages, SCHEMA, temperature=0.75 if attempt == 0 else 0.6)
            problems, doubtful = validate(draft, photos, subject, ground_en, ground_hi, hi_names, banned_names or [],
                                          kind, agreed_toll, angle)
            if not today_ok:
                problems += not_today(script_text(draft))
            if attempt < DRAFTS - 1:
                problems += monotone(draft)
            if not problems:
                script = "\n".join(b["say"] for b in draft["beats"])
                verdict = pen.chat(_check_messages(script, draft.get("names", []), facts, source_en, source_hi,
                                                   doubtful), CHECK_SCHEMA, temperature=0.0, max_tokens=800)
                items = [str(u).strip() for u in verdict.get("unsupported", []) if str(u).strip()]
                ignored = [u for u in items if not hindi.quotes(u, script_text(draft))
                           or unlisted_but_sourced(u, ground_en)]
                problems = [f"unsupported: {u}" for u in items if u not in ignored]
            if not problems:
                return draft, log, pen.used
            log.append({"attempt": attempt + 1, "problems": problems, "draft": draft, "models": list(pen.used),
                        "ignored": ignored})
            if log_path:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
            messages = messages + [{"role": "assistant", "content": json.dumps(draft, ensure_ascii=False)},
                                   {"role": "user", "content": "Rewrite the whole JSON. Fix these problems and change "
                                    "nothing else that is supported:\n- " + "\n- ".join(problems)}]
    finally:
        if own:
            pen.close()
    raise ValueError("gate: no draft passed the fact checks: " + "; ".join(log[-1]["problems"])[:400])


def _sentence_with(number: str, text: str) -> str:
    for s in re.split(r"(?<=[.!?।])\s+", text):
        if number in hindi.values(s):
            return s[:240]
    return ""


def _strip(text: str, words: list[str]) -> str:
    """text without the sentences that use any of words (Hindi or English)."""
    parts = re.split(r"(?<=[.!?।])\s+", text)
    return " ".join(p for p in parts if not gate.found(p, words))


def pick_photos(title: str, ent: dict, folder: Path, person: bool, extra_qids: list[str] | None = None,
                files: list[str] | None = None, exclude: set[str] | None = None, places: bool = False) -> list[dict]:
    """Downloaded photos as dicts with a "focus" box: for a person, only photos in which their face is matched.
    files: Commons files an editor chose instead of searching; exclude: files that may not be used; places: see
    media.find."""
    import cv2

    if files:
        found = media.picks([f for f in files if f not in (exclude or set())])
    else:
        found = media.find(title, ent, limit=10, extra_qids=extra_qids, exclude=exclude, search=bool(exclude),
                           places=places)
    found = media.download(found, folder)
    rows = media.as_dicts(found)
    images = [cv2.imread(r["path"]) for r in rows]
    detected = [faces.detect(img) if img is not None else [] for img in images]
    picks = faces.subject(detected) if person else [None] * len(rows)
    kept = []
    for r, f, img, seen in zip(rows, picks, images, detected):
        if person and f is None:
            continue
        if r["origin"] == "place" and img is not None and any(d["box"][2] >= PLACE_FACE * min(img.shape[:2])
                                                              for d in seen):
            continue  # a place photo that features someone would pass them off as part of the story
        r["focus"] = [round(v) for v in f["box"]] if f else None
        kept.append(r)
    return kept[:8]


def _shared(cand: dict, title: str, ent: dict, extra: list[str] | None) -> tuple[dict | None, set[str]]:
    """Orbitwire's overlap record for a shared story, with the photo files Orbitwire would use."""
    ov = cand.get("orbitwire")
    if not ov:
        return None, set()
    pool = orbitwire.photo_pool(title, ent, extra)
    return ov | {"excluded_photos": pool, "photo_pool_checked": True}, set(pool)


def _hindi_source(ent: dict, limit: int = 5000) -> tuple[str, str | None]:
    hi_title = wiki.sitelink(ent, "hiwiki")
    if not hi_title:
        return "", None
    try:
        return wiki.article_text(hi_title, limit=limit, per_section=1200, lang="hi"), hi_title
    except Exception:
        return "", None


def build_death(cand: dict) -> Short:
    title, qid = cand["title"], cand["qid"]
    ent = wiki.entities([qid])[qid]
    _, ib, raw = wiki.infobox(title)
    if not raw:
        raise ValueError("gate: the article has no infobox to confirm the death")
    born = next((wiki.wd_time(c["value"]) for c in wiki.claims(ent, "P569")), None)
    died = next((wiki.wd_time(c["value"]) for c in wiki.claims(ent, "P570")), None)
    if not born or not died:
        raise ValueError("gate: Wikidata lacks an exact birth or death date")
    if str(died.year) not in raw.get("death_date", ""):
        raise ValueError("gate: Wikipedia's infobox does not confirm the death yet")
    days = (_today_ist() - died).days
    if days > MAX_DEATH_DAYS:
        raise ValueError(f"gate: the death was {days} days ago; the desk covers deaths of the last {MAX_DEATH_DAYS} "
                         "days only (an old death must never read as news)")
    page, item = wiki.url(title), f"https://www.wikidata.org/wiki/{qid}"
    name = stories.plain_title(wiki.label(ent) or title)
    name_hi = wiki.label(ent, "hi")
    she, _ = stories._pronouns(ent)
    age = died.year - born.year - ((died.month, died.day) < (born.month, born.day))
    job = (ib.get("occupation") or "").split(",")[0].strip()
    if not job:
        job = next(iter(wiki.labels([c["value"] for c in wiki.claims(ent, "P106")[:1]]).values()), "")
    job_hi = next(iter(wiki.labels([c["value"] for c in wiki.claims(ent, "P106")[:1]], "hi").values()), "")
    sid = cand.get("id") or f"wk-{qid}"
    work = WORK / sid
    ov, exclude = _shared(cand, title, ent, None)
    photos = pick_photos(title, ent, work / "photos", person=True, exclude=exclude)
    if len(photos) < MIN_PHOTOS:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} on Wikimedia Commons (want {MIN_PHOTOS})"
                         + (" not used by Orbitwire" if ov else ""))
    facts_text = [f"{name} died on {stories.date_words(died)}, aged {age}.",
                  f"{name_hi or name} का निधन {hindi.date_hi(died)} को {age} वर्ष की उम्र में हुआ।",
                  f"Born {stories.date_words(born)}" + (f" in {ib['birth_place']}." if ib.get("birth_place") else "."),
                  f"जन्म: {hindi.date_hi(born)}।",
                  f"Died in {ib['death_place']}." if ib.get("death_place") else "",
                  f"Occupation: {ib.get('occupation')}." if ib.get("occupation") else "",
                  f"Years active: {ib.get('years_active')}." if ib.get("years_active") else ""]
    facts_text = [f for f in facts_text if f]
    source = wiki.article_text(title)
    source = _strip(source, ["suicid*", "आत्महत्या", "खुदकुशी"])
    source_hi, hi_title = _hindi_source(ent)
    source_hi = _strip(source_hi, ["suicid*", "आत्महत्या", "खुदकुशी"])
    hi_names = wiki.hindi_names(ent)
    subject = {"en": name, "hi": name_hi, "person": True}
    angle = ov["angle"] if ov else None
    draft, log, used = write("death", subject, she, facts_text, source, source_hi, photos, hi_names,
                             log_path=work / "writer_log.json", angle=angle, today_ok=days == 0)
    name_hi = name_hi or _pair_for(draft, name) or name
    facts = [Fact("name", name, page, stories.numbers_in(name), "Wikipedia article title"),
             Fact("died", hindi.date_hi(died), item, [str(died.day), str(died.year)],
                  f"Wikidata P570 = {died.isoformat()}; infobox death_date present"),
             Fact("born", hindi.date_hi(born), item, [str(born.day), str(born.year)], f"Wikidata P569 = {born}"),
             Fact("age", str(age), item, [str(age)], "computed from P569 and P570")]
    sources = [page, item] + ([wiki.url(hi_title, "hi")] if hi_title and source_hi else [])
    return _short(sid, "death", name, name_hi, draft, log, used, facts, facts_text, source + "\n" + source_hi, photos,
                  sources, died.isoformat(), loss=False, mood="tribute", region=cand.get("region", "world"),
                  tags=[name, name_hi, job, job_hi, "श्रद्धांजलि", "tribute", "hindi news", "हिंदी समाचार"],
                  summary=f"{name_hi} ({born.year}–{died.year}) को श्रद्धांजलि: उनकी कहानी, Wikipedia और Wikidata के "
                          f"तथ्यों से।",
                  hashtags=[name_hi, job_hi or "श्रद्धांजलि", "हिंदीसमाचार"], ov=ov)


def build_incident(cand: dict) -> Short:
    article, qid, cat = cand["title"], cand.get("qid"), cand["category"]
    name = stories.plain_title(article)
    stories._check_age(article)
    ent = wiki.entities([qid])[qid] if qid else {}
    _, ib, raw = wiki.infobox(article)
    ongoing = cat in trends.ONGOING
    when, date_src = stories._event_date(ent), "Wikidata date"
    if not when and (when := stories.infobox_date(ib)):
        date_src = "Wikipedia infobox date"
    if ongoing:
        when = date.fromisoformat((cand.get("news_at") or datetime.now(timezone.utc).isoformat())[:10])
    if not when:
        raise ValueError("gate: neither Wikidata nor the infobox gives a date for this event")
    page = wiki.url(article)
    item = f"https://www.wikidata.org/wiki/{qid}" if qid else page
    # The same related items Orbitwire adds, so its photo ranking can be reproduced exactly.
    extra = [c["value"] for pid in ("P276", "P1427", "P1444", "P121", "P137") for c in wiki.claims(ent, pid)[:1]
             if isinstance(c["value"], str) and c["value"].startswith("Q")]
    if not extra:
        # An article Wikidata does not describe yet: the places its infobox links to give the location photos.
        links = re.findall(r"\[\[([^\]|#]+)", " ".join(raw.get(k, "") for k in ("target", "location", "site", "place",
                                                                                "areas affected", "areas", "country")))
        found = wiki.page_info(list(dict.fromkeys(links))[:6]) if links else {}
        extra = list(dict.fromkeys(p["qid"] for p in found.values() if p.get("qid")))[:3]
    sid = cand.get("id") or f"wk-{qid}"
    work = WORK / sid
    ov, exclude = _shared(cand, article, ent, extra)
    photos = pick_photos(article, ent, work / "photos", person=False, extra_qids=extra, files=cand.get("photo_files"),
                         exclude=exclude, places=not qid)
    if len(photos) < MIN_PHOTOS:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} on Wikimedia Commons (want {MIN_PHOTOS})"
                         + (" not used by Orbitwire" if ov else ""))
    deaths = stories.agreed(stories._first(ib, "total_fatalities", "fatalities", "deaths"), ent, "P1120", True)
    hurt = stories.agreed(stories._first(ib, "total_injuries", "injuries", "injured"), ent, "P1339", True)
    facts_text = [f"Today's date: {stories.date_words(when)}." if ongoing
                  else f"{name} happened on {stories.date_words(when)}.",
                  f"आज की तारीख: {hindi.date_hi(when)}।" if ongoing else f"तारीख: {hindi.date_hi(when)}।"]
    where = stories._first(ib, "site", "location", "place", "areas affected", "areas")
    if where:
        facts_text.append(f"Location: {where}.")
    if deaths is not None:
        facts_text.append(f"Official death toll (Wikipedia and Wikidata agree): {deaths:,}.")
    if hurt:
        facts_text.append(f"Injured (Wikipedia and Wikidata agree): {hurt:,}.")
    banned = [v for k, v in ib.items() if re.match(r"(perpetrators?|assailants?|attackers?|suspects?|accused)$", k)]
    source = wiki.article_text(article)
    source_hi, hi_title = _hindi_source(ent)
    if deaths is None:
        # Casualty numbers only when both sources agree: strip unconfirmed tolls from what the writer may use.
        source = re.sub(r"[^.]*\b(killed|dead|deaths?|died|toll|fatalit\w*|casualt\w*|injured|wounded)\b[^.]*\.", "",
                        source, flags=re.I)
        source_hi = _strip(source_hi, gate.CASUALTY)
    source = re.sub(r"[^.]*\bsuicid\w*[^.]*\.", "", source, flags=re.I)
    source_hi = _strip(source_hi, ["आत्महत्या", "खुदकुशी", "ख़ुदकुशी"])
    values = hindi.values(source)
    headlines = [h for h in cand.get("headlines") or [] if _headline_ok(h, values, source)]
    hi_names = wiki.hindi_names(ent)
    name_hi = wiki.label(ent, "hi")
    subject = {"en": name, "hi": name_hi, "person": False}
    kind = "protest" if cat in ("protest", "movement") else "incident"
    angle = ov["angle"] if ov else None
    draft, log, used = write(kind, subject, "It", facts_text, source, source_hi, photos, hi_names,
                             banned_names=banned, agreed_toll=deaths is not None, log_path=work / "writer_log.json",
                             headlines=headlines, angle=angle, today_ok=ongoing or when == _today_ist())
    name_hi = name_hi or _pair_for(draft, name) or name
    loss = bool(deaths) or cat in ("attack", "strike", "conflict")
    facts = [Fact("name", name, page, stories.numbers_in(name), "Wikipedia article title"),
             Fact("date", hindi.date_hi(when), item, [str(when.day), str(when.year)],
                  f"Google News lead story on {when}" if ongoing else f"{date_src} {when}")]
    if deaths is not None:
        facts.append(Fact("deaths", str(deaths), page, [str(deaths)], "infobox and Wikidata P1120 agree"))
    region = stories.city_of(where) if where else None
    sources = list(dict.fromkeys([page, item])) + ([wiki.url(hi_title, "hi")] if hi_title and source_hi else [])
    return _short(sid, "incident", name, name_hi, draft, log, used, facts, facts_text, source + "\n" + source_hi,
                  photos, sources, when.isoformat(), loss=loss, mood="news", region=cand.get("region", "world"),
                  tags=[name, name_hi, cat, "हिंदी समाचार", "hindi news",
                        "india news" if cand.get("region") == "india" else "world news"] + ([region] if region else []),
                  summary=f"{name_hi}, {hindi.date_hi(when)}: क्या हुआ, "
                          f"{'Wikipedia और Wikidata' if qid else 'Wikipedia'} के तथ्यों से।",
                  hashtags=[name_hi, "हिंदीसमाचार", "news"], ov=ov)


def _pair_for(draft: dict, name: str) -> str | None:
    return next((p["hi"] for p in draft.get("names", []) if p.get("en", "").lower() == name.lower()), None)


def _short(sid, kind, name, name_hi, draft, log, used, facts, facts_text, source, photos, sources, event_time, loss,
           mood, tags, summary, hashtags, region="world", ov=None) -> Short:
    beats = [Beat(b["say"].strip(), f"photo:{b['photo']}", {"big": b["caption"].strip(), "small": ""})
             for b in draft["beats"]]
    beats.append(Beat(OUTRO, "outro", {"big": config.NAME_HI or config.NAME or "", "small": "स्रोत विवरण में"},
                      pause_after=0.5))
    ground = source + "\n" + "\n".join(facts_text)
    allowed = {n for f in facts for n in f.numbers}
    shown = " ".join(b.text + " " + (b.card or {}).get("big", "") for b in beats) + " " + draft["title"]
    for n in sorted({v for v, _ in hindi.numbers(shown)}):
        if n not in allowed:
            facts.append(Fact(f"source-{n}", n, sources[0], [n], _sentence_with(n, ground)))
            allowed.add(n)
    title = draft["title"].strip().strip('"')
    if not 15 <= len(title) <= 90:
        title = f"{name_hi} को श्रद्धांजलि" if kind == "death" else f"{name_hi}: पूरा मामला"
        if ov:
            title = f"{name_hi}: {orbitwire.ANGLES[ov['angle']]['label']}"
    credits = [CREDIT] + sorted({p["credit"] + " " + p["page"] for p in photos})
    scene = {"template": "story", "mood": mood, "voice": "sulafat", "region": region, "photos": photos,
             "name_hi": name_hi, "names": draft.get("names", []), "writer": {"models": used, "rejected": log}}
    if ov:
        scene["orbitwire"] = ov
    return Short(id=sid, kind=kind, title=title[:90], beats=beats, facts=facts, sources=sources, loss=loss,
                 scene=scene, event_time=event_time, tags=[t for t in dict.fromkeys(tags) if t], summary=summary,
                 credits=credits, hashtags=[h for h in hashtags if h])


def build(cand: dict) -> Short:
    return build_death(cand) if cand["kind"] == "death" else build_incident(cand)
