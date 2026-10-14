"""Hindi story Shorts: real photos of the person or event, and a narrated story with feeling, written in Hindi from
English Wikipedia, Hindi Wikipedia (when it has the article) and the confirmed Wikidata facts.

The model writes; code decides. Gemini (free tier, GEMINI_API_KEY) writes first and the local Gemma 4 model steps in
when Gemini can't answer. Every number in the script must have its value in a source (Devanagari digits and लाख or
करोड़ included), every proper noun must be listed as a {hi, en} pair whose English is in the sources and whose Hindi
is in the script (Wikidata's Hindi label wins when there is one), Latin-script words must be in the English source,
and a second model pass lists anything unsupported. A failing draft is rewritten up to three times (the fact check
runs only on drafts that pass the code gates, so it needs rewrites left), then the story is dropped.
Death and casualty facts still pass the same two-source gates as Orbitwire's.

Trusted outlets (desk/outlets.py) are a second kind of source: the writer gets a REPORTING block of excerpts from 2-4
of their articles about the story, each from a different owner. A number, name or claim that Wikipedia and Wikidata
do not state must be in at least two independent owners' articles (gate.OWNERS_NEEDED); one outlet alone is never
enough, and a death toll from reporting needs two owners giving the same exact number (or Wikidata agreeing).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, explain, faces, gate, gemini, hindi, llm, media, orbitwire, outlets, stories, trends, wiki
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

EXPLAINER_BRIEF = """STORY: {name}, in today's news: the story the first of TODAY'S LEAD HEADLINES points at (a
headline only shows which story; its words are not a source). Write a Hindi "क्यों हुआ" explainer Short: a viewer who
saw only the headline understands, in 45 seconds, what happened, why, and what it means.

Shape:
1. Hook (beat 1, under 14 words): name {name} and either the newest, most striking reported fact, or the story's own
   question with "क्यों" ("... ने इस्तीफ़ा क्यों दिया?"). The next beats answer it.
2. What exactly happened, and when, in order (from REPORTING).
3. Why: the reasons the REPORTING gives, each attributed to whoever gives it ("सरकार के मुताबिक", "पार्टी का कहना है",
   "रिपोर्टों के अनुसार"). If no report gives a reason, say plainly that no official reason has been given.
4. Background the viewer needs: who {name} is or what it does (from the SOURCE).
5. The other side: when the story is one side acting against, accusing or protesting another (a party against the
   government, the opposition against an official), say what the other side said in REPORTING, attributed; if
   REPORTING carries no response from them, say "रिपोर्टों में <them> की प्रतिक्रिया नहीं है" in one short line.
6. What happens next, or what is still unclear, said honestly. The last beat answers the hook in one short sentence.
Be strictly neutral: never take a side, never praise or mock any person, party, community or religion, use no loaded
words, and attribute every claim, allegation and criticism to whoever made it. Never guess at motives, never predict,
never give financial, legal or medical advice. Never mention suicide, and never write "जानें" (it reads as "lives
lost"). The title may be the story's own question (ending in "?"), never a teaser that hides the news."""

RULES = """RULES (all mandatory):
- Use ONLY information in CONFIRMED FACTS and the SOURCES. Never add a name, title, number, place, date, quote, award
  or relationship that is not written there. If you are unsure, leave it out.
- Write in Hindi (Devanagari): simple, spoken Hindi of a good Hindi news bulletin, neither heavily Sanskritised nor
  slang. Never translate an English idiom word for word: say what it means as a Hindi bulletin would ("high tea" is
  "चाय पर बैठक", never "उच्च चाय"; "huddle" is "बैठक"). 7 or 8 beats and 95 to 120 Hindi words in total (about 45 seconds spoken). Each beat is one or two spoken
  sentences of 10 to 18 words. Count the words before you answer.
- Every beat must carry a specific fact from the SOURCES (a work, a year, an honour, a choice they made); feeling
  comes from how you tell those facts, not from vague praise.
- Tell it as a story, not a list: vary how beats open, and never start more than 2 beats with the same word.
- Hook: beat 1 must make a scrolling viewer stop within its first 5 words: open on the most striking fact in the
  SOURCES (a decision, a number, a first, a reversal), never on a date, a greeting or a slow introduction.
- Keep them watching: every beat adds one new fact and leads into the next; no recap, no filler, no empty lines such
  as "यह खबर चर्चा में है". The last beat closes what the hook opened.
- Write every number as digits: years (1994), ages (75), dates ("10 अक्टूबर 2026"), and big numbers with लाख or
  करोड़ ("3 लाख", "1.5 करोड़"). A number must be exactly what the SOURCES say (a million is 10 लाख).
- No hype or clickbait (सनसनीखेज, चौंकाने वाला, खौफनाक, ब्रेकिंग, बड़ी खबर), no emoji, no questions put to the viewer
  (an explainer's hook may ask the story's own "क्यों" question, which the Short then answers), no request to like,
  share, subscribe or follow.
- names: list EVERY proper noun you used (people, places, organisations, works, events, awards) as
  {{"hi": the name exactly as written in your Hindi text, "en": the same name exactly as the English SOURCE writes
  it}}. Where HINDI NAMES gives a Hindi spelling, use that spelling.
- photo: the index of the PHOTO that best fits the beat. Beat 1 uses photo {best}. Use every photo at least once if
  you can, and the same photo at most twice.
- caption: 1 to 4 Hindi words shown on screen that carry the beat's key fact: a number with its unit, a decision, the
  work it names with its year, a role, an honour, or a year. Never a place name: viewers read a place over a photo
  as where the photo was taken.
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


REPORTING_RULE = ("a fact that only REPORTING gives may be used only when at least two reports from DIFFERENT owners "
                  "state it; never use a fact that only one report states")


def reporting_block(reports: list[dict] | None) -> str:
    """The REPORTING section: each article's outlet, owner, date and headline, then its excerpt."""
    if not reports:
        return ""
    rows = [f"[{n}] {r['outlet']} (owner: {r['owner']}), {r['at'][:10]}: {r['title']}\n{r['excerpt']}"
            for n, r in enumerate(reports, 1)]
    return f"\n\nREPORTING (trusted outlets; {REPORTING_RULE}):\n" + "\n\n".join(rows)


def _messages(brief: str, facts: list[str], source_en: str, source_hi: str, photos: list[dict], name_hi: str,
              hi_names: dict[str, str], headlines: list[str] | None = None,
              reports: list[dict] | None = None) -> list[dict]:
    listing = "\n".join(f"{i}: {p['description'] or p['file']}" for i, p in enumerate(photos))
    lead = ""
    if headlines:
        lead = ("\n\nTODAY'S LEAD HEADLINES (context only: use them to choose the angle and what to put first, but "
                "state only facts that are in CONFIRMED FACTS or the SOURCES):\n" + "\n".join(f"- {h}" for h in headlines))
    names = "\n".join(f"- {en} = {hi}" for en, hi in hi_names.items()) or "- (none)"
    user = (brief + "\n\nCONFIRMED FACTS:\n" + "\n".join(f"- {f}" for f in facts)
            + ("\n\nSOURCE (English Wikipedia):\n" + source_en if source_en else "")
            + ("\n\nSOURCE (Hindi Wikipedia):\n" + source_hi if source_hi else "")
            + reporting_block(reports)
            + "\n\nHINDI NAMES (Wikidata's Hindi labels; use these spellings):\n" + names
            + lead + "\n\nPHOTOS:\n" + listing + "\n\n" + RULES.format(best=0, name_hi=name_hi)
            + ("\nREPORTING counts as a source under its own rule: " + REPORTING_RULE + "." if reports else ""))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _check_messages(script: str, names: list[dict], facts: list[str], source_en: str, source_hi: str,
                    doubtful: list[dict], reports: list[dict] | None = None) -> list[dict]:
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
            + (" A statement that only REPORTING supports counts as supported only when at least two reports from "
               "different owners state it; list any statement only one report states." if reports else "")
            + "\n\nCONFIRMED FACTS:\n" + "\n".join(f"- {f}" for f in facts) + "\n\nSOURCE (English):\n" + source_en
            + ("\n\nSOURCE (Hindi):\n" + source_hi if source_hi else "") + reporting_block(reports)
            + "\n\nNAMES:\n" + pairs + double + "\n\nSCRIPT:\n" + script)
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
             angle: str | None = None, reports: list[dict] | None = None) -> tuple[list[str], list[dict]]:
    """Problems with a draft, and the name pairs to double-check in the fact-check pass. A number or name the
    Wikipedia/Wikidata ground lacks passes only when at least two independent owners' reports state it."""
    problems, doubtful = [], []
    reports = reports or []
    two = gate.OWNERS_NEEDED
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
    values = hindi.values(ground_en + "\n" + ground_hi) | gate.corroborated_values(reports)
    bad = hindi.unsupported_numbers(text, values)
    if bad:
        single = [n for n in bad if gate.reported_values(reports).get(n)]
        problems.append("these numbers are not in the sources: " + ", ".join(bad)
                        + (f" ({', '.join(single)} only in one outlet's report: one outlet is not enough)"
                           if single else ""))
    wikidata = {en.lower(): hi for en, hi in hi_names.items()}
    for p in names:
        hi, en = (p.get("hi") or "").strip(), (p.get("en") or "").strip()
        if not hi or not en:
            problems.append("every names entry needs both hi and en")
            continue
        if not hindi.contains(text, hi):
            problems.append(f"names lists {hi!r}, but the script never writes it exactly like that")
        en_ok, hi_ok = hindi.contains(ground_en, en), hindi.contains(ground_hi, hi)
        reported = set(gate.reported(en, reports)) | set(gate.reported(hi, reports))
        if not (en_ok or hi_ok) and len(reported) >= two:
            hi_ok = bool(gate.reported(hi, reports))
        elif not (en_ok or hi_ok):
            problems.append(f"{en} ({hi}) is not in the sources" + (" (only one outlet reports it)" if reported else ""))
        label = wikidata.get(en.lower())
        if label and hindi.norm(label) != hindi.norm(hi) and not hindi.contains(text, label):
            problems.append(f"write {en} as {label} (Wikidata's Hindi name), not {hi}")
        elif not label and not hi_ok and not hindi.sounds_alike(hi, en):
            doubtful.append({"hi": hi, "en": en})
    listed = " ".join(p.get("en", "") for p in names).lower()
    for w in sorted(set(hindi.latin_words(text))):
        if w.upper() in gate.ACRONYMS and w.upper() == w:
            continue
        if not hindi.contains(ground_en, w) and len(gate.reported(w, reports)) < two:
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
          today_ok: bool = True, reports: list[dict] | None = None) -> tuple[dict, list[dict], list[str]]:
    """The script as {title, beats: [{say, photo, caption}], names}, the log of rejected drafts (also kept at
    log_path), and the models that answered. kind is "death", "incident" or "protest". reports: trusted outlets'
    articles ({outlet, owner, at, title, excerpt, text}), see the module docstring."""
    obj = {"He": "him", "She": "her"}.get(pronoun, "them")
    brief = {"death": DEATH_BRIEF, "protest": PROTEST_BRIEF, "explainer": EXPLAINER_BRIEF}.get(kind, INCIDENT_BRIEF)
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
    messages = _messages(brief, facts, source_en, source_hi, photos, name_hi, hi_names, headlines, reports)
    # A Commons description is anyone's caption, not a source: the script's facts come from the sources alone.
    ground_en = source_en + "\n" + "\n".join(facts)
    ground_hi = source_hi + "\n" + "\n".join(facts) + "\n" + "\n".join(hi_names.values())
    log = []
    own = pen is None
    pen = pen or Pen()
    try:
        for attempt in range(DRAFTS):
            ignored = []
            draft = pen.chat(messages, SCHEMA, temperature=0.75 if attempt == 0 else 0.6)
            problems, doubtful = validate(draft, photos, subject, ground_en, ground_hi, hi_names, banned_names or [],
                                          kind, agreed_toll, angle, reports)
            if not today_ok:
                problems += not_today(script_text(draft))
            if attempt < DRAFTS - 1:
                problems += monotone(draft)
            if not problems:
                script = "\n".join(b["say"] for b in draft["beats"])
                verdict = pen.chat(_check_messages(script, draft.get("names", []), facts, source_en, source_hi,
                                                   doubtful, reports), CHECK_SCHEMA, temperature=0.0, max_tokens=800)
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


def featured_face(img, seen: list[dict]) -> bool:
    """A face this big would pass whoever it is off as part of the story."""
    return img is None or any(d["box"][2] >= PLACE_FACE * min(img.shape[:2]) for d in seen)


def pick_photos(title: str, ent: dict, folder: Path, person: bool, extra_qids: list[str] | None = None,
                files: list[str] | None = None, exclude: set[str] | None = None, places: bool = False,
                context_qids: list[str] | None = None) -> list[dict]:
    """Downloaded photos as dicts with a "focus" box: for a person, only photos in which their face is matched.
    files: Commons files an editor chose instead of searching; exclude: files that may not be used; places: see
    media.find; context_qids: places and things the story links to, whose photos (with no featured face) fill in
    when the story has fewer than MIN_PHOTOS of its own: Commons first, then Openverse. A person needs at least one
    photo of their own face."""
    kept = _own_photos(title, ent, folder, person, extra_qids, files, exclude, places) if title else []
    if len(kept) >= MIN_PHOTOS or files or not context_qids or (person and not kept):
        return kept
    return (kept + fill_photos(context_qids, folder, (exclude or set()) | {r["file"] for r in kept},
                               MIN_PHOTOS - len(kept)))[:8]


def fill_photos(context_qids: list[str], folder: Path, exclude: set[str], need: int = MIN_PHOTOS) -> list[dict]:
    """Photos of the places and things a story links to that feature no face: Commons (each item's main image and
    files from its article naming it), then, while fewer than `need`, Openverse photos naming the item."""
    import cv2

    def faceless(found: list, sub: str) -> list[dict]:
        out = []
        for r in media.as_dicts(media.download(found, folder / sub)):
            img = cv2.imread(r["path"])
            if featured_face(img, faces.detect(img) if img is not None else []):
                continue
            r["focus"] = None
            out.append(r)
        return out

    kept = faceless(media.context(context_qids, exclude=exclude), "context")
    if len(kept) < need:
        try:
            found = media.openverse_for(context_qids, exclude=exclude | {r["file"] for r in kept})
        except Exception:
            found = []
        kept += faceless(found, "openverse")
    return kept


def _own_photos(title: str, ent: dict, folder: Path, person: bool, extra_qids: list[str] | None,
                files: list[str] | None, exclude: set[str] | None, places: bool) -> list[dict]:
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
        if r["origin"] == "place" and img is not None and featured_face(img, seen):
            continue  # a place photo that features someone would pass them off as part of the story
        r["focus"] = [round(v) for v in f["box"]] if f else None
        r["others"] = sum(g is not f and g["box"][2] * g["box"][3] >= 0.25 * f["box"][2] * f["box"][3]
                          for g in seen) if f else 0
        kept.append(r)
    # Strangers beside the person would be shown as part of today's story: their own portraits go first.
    return sorted(kept, key=lambda r: r["others"] > 0)[:8]


PERSON_CONTEXT = ("P19", "P69", "P108", "P54", "P463", "P166", "P800")  # birthplace, school, employer, team, ...


def person_context(ent: dict) -> list[str]:
    """The places and things a person's life links to, whose photos may fill a tribute short of portraits."""
    return list(dict.fromkeys(c["value"] for pid in PERSON_CONTEXT for c in wiki.claims(ent, pid)[:1]
                              if isinstance(c["value"], str) and c["value"].startswith("Q")))[:6]


def incident_context(ent: dict, extra: list[str]) -> list[str]:
    """The items an incident's fill photos come from: its related items, then the place it is located in (P131).
    Orbitwire fills from the same items (studio/writer.py), so its fill photos are excluded from a shared story."""
    located = [c["value"] for c in wiki.claims(ent, "P131")[:1] if isinstance(c["value"], str)
               and c["value"].startswith("Q")]
    return list(dict.fromkeys(extra + located))[:4]


def _shared(cand: dict, title: str, ent: dict, extra: list[str] | None,
            context: list[str] | None = None) -> tuple[dict | None, set[str]]:
    """Orbitwire's overlap record for a shared story, with the photo files Orbitwire would use (its fill photos of
    the story's places too)."""
    ov = cand.get("orbitwire")
    if not ov:
        return None, set()
    pool = orbitwire.photo_pool(title, ent, extra, context if context is not None else extra)
    return ov | {"excluded_photos": pool, "photo_pool_checked": True}, set(pool)


SUICIDE_WORDS = ["suicid*", "आत्महत्या", "खुदकुशी", "ख़ुदकुशी"]
# Reports name suspects and attackers; an incident Short never does, so such sentences never reach the writer.
PERPETRATOR = re.compile(r"\b(suspect\w*|accused|attackers?|assailants?|gunm[ae]n|shooters?|perpetrators?|"
                         r"identified as|named as|arrest\w*|detained|charged|held for)\b|आरोपी|संदिग्ध|हमलावर|"
                         r"गिरफ्तार|गिरफ़्तार|हिरासत", re.I)
# Casualty sentences never reach the writer from reports: an agreed toll comes as a confirmed fact, and any other
# count (hedged, earlier, injured) must not be said beside it.
REPORT_CASUALTY = gate.CASUALTY + ["dead", "died", "death", "deaths", "lives", "bodies", "body", "perish*",
                                   "नहीं रहे", "शव", "लाश*"]


def _reporting(cand: dict, title: str, hi: str | None = None, person: bool = False,
               since: datetime | None = None, search: bool = True) -> list[dict]:
    """2-4 trusted outlets' articles about the story, each from a different owner, with their text (outlets.reporting):
    the reports matched to it at discovery, and (search) any recent outlet item that names it. [] when fewer than
    two owners' articles can be read."""
    found = [r for r in cand.get("reports") or [] if r.get("url")]
    if search:
        # Discovery matches a headline by one distinctive word; a report backs facts only when it names the story.
        found = outlets.about(title, found, person=person, hi=hi)
    found = {r["url"]: r for r in found}
    if search:
        try:
            items, _ = outlets.recent()
        except Exception:
            items = []
        for i in outlets.about(title, items, since=since, person=person, hi=hi):
            found.setdefault(i["url"], i)
    rows = [r for r in found.values() if not since or datetime.fromisoformat(r["at"]) >= since]
    try:
        return outlets.reporting(rows)
    except Exception:
        return []


def clean_reports(reports: list[dict], words: list[str], perpetrators: bool) -> list[dict]:
    """The reports as the writer and the checks see them: no sentence about suicide or casualties, none naming a
    suspect or attacker in an incident; each with an excerpt naming the story."""
    out = []
    for r in reports:
        body = _strip(_strip(r["text"], SUICIDE_WORDS), REPORT_CASUALTY)
        if perpetrators:
            body = " ".join(s for s in re.split(r"(?<=[.!?।])\s+", body) if not PERPETRATOR.search(s))
        out.append(r | {"text": body, "excerpt": outlets.excerpt(body, words)})
    return out


def reported_toll(reports: list[dict], ent: dict, listed: str | None = None) -> tuple[int, list[str]] | None:
    """A death toll the reporting agrees on (gate.reported_toll, checked against Wikidata P1120), never one that
    differs from a number the infobox lists."""
    got = gate.reported_toll(reports, {int(c["value"]) for c in wiki.claims(ent, "P1120")})
    shown = wiki.leading_number(listed)
    return got if got and shown in (None, got[0]) else None


def toll_basis(owners: list[str]) -> str:
    return " and ".join(owners) if len(owners) >= gate.OWNERS_NEEDED else f"{owners[0]} and Wikidata P1120"


def toll_fact(deaths: int, owners: list[str], reports: list[dict], item: str | None) -> Fact:
    """The deaths fact for a reported toll: the owners' reports, or Wikidata when only one owner states it."""
    if len(owners) >= gate.OWNERS_NEEDED:
        url = next(r["url"] for r in reports if r["owner"] in owners)
        return Fact("deaths", str(deaths), url, [str(deaths)], f"reported alike by {toll_basis(owners)}",
                    owners=owners)
    return Fact("deaths", str(deaths), item or reports[0]["url"], [str(deaths)], f"{toll_basis(owners)} agree")


def _since(day: date, back_days: int = 1) -> datetime:
    return datetime.combine(day, datetime.min.time(), timezone.utc) - timedelta(days=back_days)


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
    context = person_context(ent)
    ov, exclude = _shared(cand, title, ent, None, context)
    photos = pick_photos(title, ent, work / "photos", person=True, exclude=exclude, context_qids=context)
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
    reports = clean_reports(_reporting(cand, name, name_hi, person=True, since=_since(died)),
                            [name] + ([name_hi] if name_hi else []), perpetrators=False)
    draft, log, used = write("death", subject, she, facts_text, source, source_hi, photos, hi_names,
                             log_path=work / "writer_log.json", angle=angle, today_ok=days == 0, reports=reports)
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
                  hashtags=[name_hi, job_hi or "श्रद्धांजलि", "हिंदीसमाचार"], ov=ov, reports=reports)


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
    span = date_src == "Wikipedia infobox date" and stories.infobox_span(ib)
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
    context = incident_context(ent, extra)
    ov, exclude = _shared(cand, article, ent, extra, context)
    photos = pick_photos(article, ent, work / "photos", person=False, extra_qids=extra, files=cand.get("photo_files"),
                         exclude=exclude, places=not qid, context_qids=context)
    if len(photos) < MIN_PHOTOS:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} on Wikimedia Commons (want {MIN_PHOTOS})"
                         + (" not used by Orbitwire" if ov else ""))
    listed = stories._first(ib, "total_fatalities", "fatalities", "deaths")
    deaths = stories.agreed(listed, ent, "P1120", True)
    hurt = stories.agreed(stories._first(ib, "total_injuries", "injuries", "injured"), ent, "P1339", True)
    name_hi = wiki.label(ent, "hi")
    kind = "protest" if cat in ("protest", "movement") else "incident"
    reports = _reporting(cand, name, name_hi, since=None if ongoing else _since(when))
    toll = None
    if deaths is None and (toll := reported_toll(reports, ent, listed)):
        deaths = toll[0]
    reports = clean_reports(reports, [name] + ([name_hi] if name_hi else []), perpetrators=kind == "incident")
    facts_text = [f"Today's date: {stories.date_words(when)}." if ongoing
                  else f"{name} {'began' if span else 'happened'} on {stories.date_words(when)}.",
                  f"आज की तारीख: {hindi.date_hi(when)}।" if ongoing
                  else f"{'शुरुआत की तारीख' if span else 'तारीख'}: {hindi.date_hi(when)}।"]
    where = stories._first(ib, "site", "location", "place", "areas affected", "areas")
    if where:
        facts_text.append(f"Location: {where}.")
    if toll:
        facts_text.append(f"Death toll ({toll_basis(toll[1])} agree): {deaths:,}.")
    elif deaths is not None:
        facts_text.append(f"Official death toll (Wikipedia and Wikidata agree): {deaths:,}.")
    if hurt:
        facts_text.append(f"Injured (Wikipedia and Wikidata agree): {hurt:,}.")
    banned = [v for k, v in ib.items() if re.match(r"(perpetrators?|assailants?|attackers?|suspects?|accused)$", k)]
    source = wiki.article_text(article)
    source_hi, hi_title = _hindi_source(ent)
    if deaths is None or toll:
        # Casualty numbers only when both sources agree (or, failing that, the reporting does): strip the other
        # tolls from what the writer may use.
        source = re.sub(r"[^.]*\b(killed|dead|deaths?|died|toll|fatalit\w*|casualt\w*|injured|wounded)\b[^.]*\.", "",
                        source, flags=re.I)
        source_hi = _strip(source_hi, gate.CASUALTY)
    source = re.sub(r"[^.]*\bsuicid\w*[^.]*\.", "", source, flags=re.I)
    source_hi = _strip(source_hi, ["आत्महत्या", "खुदकुशी", "ख़ुदकुशी"])
    values = hindi.values(source)
    headlines = [h for h in cand.get("headlines") or [] if _headline_ok(h, values, source)]
    hi_names = wiki.hindi_names(ent)
    subject = {"en": name, "hi": name_hi, "person": False}
    angle = ov["angle"] if ov else None
    draft, log, used = write(kind, subject, "It", facts_text, source, source_hi, photos, hi_names,
                             banned_names=banned, agreed_toll=deaths is not None, log_path=work / "writer_log.json",
                             headlines=headlines, angle=angle, today_ok=ongoing or when == _today_ist(),
                             reports=reports)
    name_hi = name_hi or _pair_for(draft, name) or name
    loss = bool(deaths) or cat in ("attack", "strike", "conflict")
    facts = [Fact("name", name, page, stories.numbers_in(name), "Wikipedia article title"),
             Fact("date", hindi.date_hi(when), item, [str(when.day), str(when.year)],
                  f"Google News lead story on {when}" if ongoing else f"{date_src} {when}")]
    if toll:
        facts.append(toll_fact(deaths, toll[1], reports, item if qid else None))
    elif deaths is not None:
        facts.append(Fact("deaths", str(deaths), page, [str(deaths)], "infobox and Wikidata P1120 agree"))
    region = stories.city_of(where) if where else None
    sources = list(dict.fromkeys([page, item])) + ([wiki.url(hi_title, "hi")] if hi_title and source_hi else [])
    return _short(sid, "incident", name, name_hi, draft, log, used, facts, facts_text, source + "\n" + source_hi,
                  photos, sources, when.isoformat(), loss=loss, mood="news", region=cand.get("region", "world"),
                  tags=[name, name_hi, cat, "हिंदी समाचार", "hindi news",
                        "india news" if cand.get("region") == "india" else "world news"] + ([region] if region else []),
                  summary=f"{name_hi}, {hindi.date_hi(when)}: क्या हुआ, "
                          f"{'Wikipedia और Wikidata' if qid else 'Wikipedia'} के तथ्यों से।",
                  hashtags=[name_hi, "हिंदीसमाचार", "news"], ov=ov, reports=reports)


def _pair_for(draft: dict, name: str) -> str | None:
    return next((p["hi"] for p in draft.get("names", []) if p.get("en", "").lower() == name.lower()), None)


def _short(sid, kind, name, name_hi, draft, log, used, facts, facts_text, source, photos, sources, event_time, loss,
           mood, tags, summary, hashtags, region="world", ov=None, reports=None, credit=CREDIT) -> Short:
    reports = reports or []
    beats = [Beat(b["say"].strip(), f"photo:{b['photo']}", {"big": b["caption"].strip(), "small": ""})
             for b in draft["beats"]]
    beats.append(Beat(OUTRO, "outro", {"big": config.NAME_HI or config.NAME or "", "small": "स्रोत विवरण में"},
                      pause_after=0.5))
    ground = source + "\n" + "\n".join(facts_text)
    in_ground, by_owner = hindi.values(ground), gate.reported_values(reports)
    allowed = {n for f in facts for n in f.numbers}
    shown = " ".join(b.text + " " + (b.card or {}).get("big", "") for b in beats) + " " + draft["title"]
    for n in sorted({v for v, _ in hindi.numbers(shown)}):
        if n not in allowed:
            who = by_owner.get(n, [])
            if who and n not in in_ground:
                url = next(r["url"] for r in reports if r["owner"] in who)
                facts.append(Fact(f"source-{n}", n, url, [n], "reported by " + ", ".join(who), owners=who))
            else:
                facts.append(Fact(f"source-{n}", n, sources[0], [n], _sentence_with(n, ground)))
            allowed.add(n)
    title = draft["title"].strip().strip('"')
    if not 15 <= len(title) <= 90:
        title = f"{name_hi} को श्रद्धांजलि" if kind == "death" else f"{name_hi}: पूरा मामला"
        if ov:
            title = f"{name_hi}: {orbitwire.ANGLES[ov['angle']]['label']}"
    if any(media.from_openverse(p) for p in photos):
        credit = credit.replace("Wikimedia Commons", "Wikimedia Commons और Openverse")
    if reports:
        credit += "; रिपोर्टिंग: " + ", ".join(outlets.names(reports))
    credits = [credit] + sorted({p["credit"] + " " + p["page"] for p in photos})
    scene = {"template": "story", "mood": mood, "voice": "sulafat", "region": region, "photos": photos,
             "name_hi": name_hi, "names": draft.get("names", []), "writer": {"models": used, "rejected": log}}
    if ov:
        scene["orbitwire"] = ov
    if reports:
        scene["reporting"] = [outlets.compact(r) for r in reports]
        scene["outlets"] = outlets.names(reports)
        sources = list(dict.fromkeys(sources + [r["url"] for r in reports]))
    return Short(id=sid, kind=kind, title=title[:90], beats=beats, facts=facts, sources=sources, loss=loss,
                 scene=scene, event_time=event_time, tags=[t for t in dict.fromkeys(tags) if t], summary=summary,
                 credits=credits, hashtags=[h for h in hashtags if h])


REPORT_CREDIT = "तथ्य: विश्वसनीय समाचार संस्थानों की रिपोर्टें; तस्वीरें: Wikimedia Commons (लाइसेंस नीचे)"
EXPLAIN_CREDIT = ("तथ्य: विश्वसनीय समाचार संस्थानों की रिपोर्टें, Wikipedia (CC BY-SA 4.0) और Wikidata (CC0); "
                  "तस्वीरें: Wikimedia Commons (लाइसेंस नीचे)")


def story_place(name: str) -> tuple[str | None, dict]:
    """The Wikidata item of the place an nw- story names: Wikipedia's first search hit, when its title names it and
    it is a place (it has coordinates and is not a person)."""
    try:
        title = wiki.search(name)
    except Exception:
        return None, {}
    if not title or name.lower() not in title.lower():
        return None, {}
    qid = (wiki.page_info([title]).get(title) or {}).get("qid")
    ent = wiki.entities([qid]).get(qid) if qid else None
    if not ent or not media.place_like(ent):
        return None, {}
    return qid, ent


def build_report(cand: dict) -> Short:
    """A story Wikipedia has no article for yet (an nw- id, desk/outlets.py stories): told only from what at least
    two independent owners' articles say, with photos of the place it happened (Commons, then Openverse), and no
    casualty count unless the reports agree on one. Once Wikipedia writes the article, plan.told_before keeps the
    story from being told again."""
    sid, name, cat = cand["id"], cand["name"], cand["category"]
    if not config.NEW_STORIES:
        raise ValueError("gate: stories without a Wikipedia article are off (DESK_NEW_STORIES)")
    when = date.fromisoformat(cand["date"])
    work = WORK / sid
    reports = _reporting(cand, name, search=False)
    if len(outlets.owners(reports)) < gate.OWNERS_NEEDED:
        raise ValueError(f"gate: fewer than {gate.OWNERS_NEEDED} independent outlets' articles about {name} could "
                         "be read")
    named = gate.reported(name, reports)
    if len(named) < gate.OWNERS_NEEDED:
        raise ValueError(f"gate: fewer than {gate.OWNERS_NEEDED} independent outlets' articles name {name}")
    qid, place = story_place(name)
    name_hi = wiki.label(place, "hi") if place else None
    context = list(dict.fromkeys(([qid] if qid else []) + incident_context(place, [])))[:4] if place else []
    ov, exclude = _shared(cand, "", {}, None, context)
    photos = fill_photos(context, work / "photos", exclude)[:8] if context else []
    if len(photos) < MIN_PHOTOS:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} (want {MIN_PHOTOS})"
                         + (" not used by Orbitwire" if ov else ""))
    kind = "protest" if cat in ("protest", "movement") else "incident"
    toll = gate.reported_toll(reports)
    words = [name] + ([name_hi] if name_hi else []) + sorted(outlets.headline_keys(cand["title"])[0])
    reports = clean_reports(reports, words, perpetrators=kind == "incident")
    facts_text = [f"Place: {name}.", "Wikipedia's article on this is only hours old: only the reporting below may be "
                  "used." if cand.get("article") else "Wikipedia has no article on this yet: only the reporting below "
                  "may be used."]
    if toll:
        facts_text.append(f"Death toll ({toll_basis(toll[1])} agree): {toll[0]:,}.")
    hi_names = wiki.hindi_names(place) if place else {}
    subject = {"en": name, "hi": name_hi, "person": False}
    angle = ov["angle"] if ov else None
    draft, log, used = write(kind, subject, "It", facts_text, "", "", photos, hi_names, agreed_toll=toll is not None,
                             log_path=work / "writer_log.json", angle=angle, today_ok=when == _today_ist(),
                             reports=reports)
    name_hi = name_hi or _pair_for(draft, name) or name
    facts = [Fact("name", name, next((r["url"] for r in reports if r["owner"] in named), reports[0]["url"]),
                  stories.numbers_in(name), "named in the reports of " + ", ".join(named), owners=named)]
    if toll:
        facts.append(toll_fact(toll[0], toll[1], reports, None))
    short = _short(sid, "incident", name, name_hi, draft, log, used, facts, facts_text, "", photos,
                   [r["url"] for r in reports], when.isoformat(), loss=bool(toll) or cat in ("attack", "conflict"),
                   mood="news", region=cand.get("region", "world"),
                   tags=[name, name_hi, cat, "हिंदी समाचार", "hindi news",
                         "india news" if cand.get("region") == "india" else "world news"],
                   summary=f"{name_hi}: क्या हुआ, {', '.join(outlets.names(reports))} की रिपोर्टों से।",
                   hashtags=[name_hi, "हिंदीसमाचार", "news"], ov=ov, reports=reports, credit=REPORT_CREDIT)
    short.scene["article"] = cand.get("article")
    short.scene["headlines"] = cand.get("headlines") or []
    return short


EXPLAIN_SOURCE = 3500  # characters of the centre's Wikipedia article: background, never the news itself


def build_explainer(cand: dict) -> Short:
    """A kh- story (desk/explain.py): today's Indian story about one person or institution, told as a neutral "क्यों
    हुआ" explainer. What happened comes only from at least two independent owners' articles; Wikipedia gives the
    background; the photos are Commons photos of the centre (a person's own face-matched portraits)."""
    sid, cat, qid = cand["id"], cand["category"], cand["qid"]
    if not config.EXPLAINERS:
        raise ValueError("gate: India explainers are off (DESK_EXPLAINERS)")
    title = cand["title"]
    ent = wiki.entities([qid])[qid]
    person = bool(cand.get("person"))
    name = stories.plain_title(wiki.label(ent) or title)
    name_hi = wiki.label(ent, "hi")
    phrase = cand.get("phrase") or name
    work = WORK / sid
    mine = [r for r in cand.get("reports") or [] if explain.about_story(r, phrase, cand.get("story_keys") or [])]
    reports = _reporting(cand | {"reports": mine}, phrase, hi=name_hi, person=person, search=False)
    if len(outlets.owners(reports)) < gate.OWNERS_NEEDED:
        raise ValueError(f"gate: fewer than {gate.OWNERS_NEEDED} independent outlets' articles about {name} could "
                         "be read")
    named = sorted(set(gate.reported(phrase, reports)) | set(gate.reported(name, reports)))
    if len(named) < gate.OWNERS_NEEDED:
        raise ValueError(f"gate: fewer than {gate.OWNERS_NEEDED} independent outlets' articles name {name}")
    context = person_context(ent) if person else incident_context(ent, [])
    ov, exclude = _shared(cand, title, ent, None, context)
    photos = pick_photos(title, ent, work / "photos", person=person, exclude=exclude, places=not person,
                         context_qids=context)
    if len(photos) < MIN_PHOTOS:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} on Wikimedia Commons (want {MIN_PHOTOS})"
                         + (" not used by Orbitwire" if ov else ""))
    story = cand.get("story") or (cand.get("headlines") or [title])[0]
    words = [phrase, name] + ([name_hi] if name_hi else []) + sorted(outlets.headline_keys(story)[0])
    reports = clean_reports(reports, words, perpetrators=True)
    source = _strip(wiki.article_text(title, limit=EXPLAIN_SOURCE, per_section=900), SUICIDE_WORDS)
    source_hi, hi_title = _hindi_source(ent, limit=2500)
    source_hi = _strip(source_hi, SUICIDE_WORDS)
    # A headline is context, never a source (one outlet's words): it goes to the writer only as a lead headline.
    facts_text = [f"Centre of the story: {name}" + (f" ({name_hi})" if name_hi else "") + ".",
                  "What happened, and why, may come only from the REPORTING; the Wikipedia SOURCE is background on "
                  f"{name} and is never today's news."]
    she, _ = stories._pronouns(ent) if person else ("It", None)
    subject = {"en": name, "hi": name_hi, "person": person}
    when = date.fromisoformat(cand["date"])
    draft, log, used = write("explainer", subject, she, facts_text, source, source_hi, photos, wiki.hindi_names(ent),
                             log_path=work / "writer_log.json",
                             headlines=list(dict.fromkeys([story] + (cand.get("headlines") or [])))[:6],
                             angle=ov["angle"] if ov else None, today_ok=when == _today_ist(), reports=reports)
    name_hi = name_hi or _pair_for(draft, name) or name
    page = wiki.url(title)
    facts = [Fact("name", name, page, stories.numbers_in(name), "Wikipedia article title; named in the reports of "
                  + ", ".join(named), owners=named)]
    sources = [page, f"https://www.wikidata.org/wiki/{qid}"] + ([wiki.url(hi_title, "hi")] if hi_title and source_hi
                                                                 else [])
    label = cand.get("category_hi") or cat
    short = _short(sid, "explainer", name, name_hi, draft, log, used, facts, facts_text, source + "\n" + source_hi,
                   photos, sources, when.isoformat(), loss=False, mood="news", region=cand.get("region", "india"),
                   tags=[name, name_hi, label, cat, "क्यों हुआ", "हिंदी समाचार", "hindi news", "india news"],
                   summary=f"{name_hi}: क्या हुआ और क्यों, {', '.join(outlets.names(reports))} की रिपोर्टों और "
                           "Wikipedia से।",
                   hashtags=[name_hi, label, "हिंदीसमाचार"], ov=ov, reports=reports, credit=EXPLAIN_CREDIT)
    short.scene.update(qid=qid, category=cat, category_hi=label, headlines=cand.get("headlines") or [], story=story)
    return short


def build(cand: dict) -> Short:
    if (cand.get("id") or "").startswith("kh-"):
        return build_explainer(cand)
    if (cand.get("id") or "").startswith("nw-"):
        return build_report(cand)
    return build_death(cand) if cand["kind"] == "death" else build_incident(cand)
