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
REPORT_PHOTOS = 2  # kh- and nw- bulletins: the fact cards and headline carry the frame, not a photo slideshow
# A kh- story about a person shows only their own photos: their school or birthplace says nothing about today's news
# (Dhruv Rathee, 2026-10-17: seven of twelve frames were buildings). One photo is enough for a story this high in
# Google News India's top stories (Abhijeet Dipke's detention led them for four days and failed 21 times on 1 photo).
LEAD_SCORE = 0.9
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
            "properties": {"say": {"type": "string"}, "photo": {"type": "integer"}, "caption": {"type": "string"},
                           "label": {"type": "string"}},
            "required": ["say", "photo", "caption", "label"]}},
        "names": {"type": "array", "items": {
            "type": "object", "properties": {"hi": {"type": "string"}, "en": {"type": "string"}},
            "required": ["hi", "en"]}},
    },
    "required": ["title", "beats", "names"],
}
CHECK_SCHEMA = {"type": "object", "properties": {"unsupported": {"type": "array", "items": {"type": "string"}}},
                "required": ["unsupported"]}

# Owner, 2026-10-19: "very hard hindi language" in titles and captions. The narration is also the on-screen subtitles,
# so it is written the way Aaj Tak or ABP anchors speak, not the way a government notice reads.
SYSTEM = ("You are the news editor of a Hindi YouTube Shorts news channel for Indian viewers. You write the bulletin "
          "a Hindi TV news anchor reads on air, in Devanagari: a serious, factual news report in the everyday spoken "
          "Hindi of Aaj Tak or ABP News, with the English words Indians use when they talk (डॉक्टर, अस्पताल, कोर्ट, "
          "पुलिस, सरकार, फ्लाइट, रिपोर्ट), never bookish or Sanskritised, never chatty, never a story told to a "
          "friend, never sensational. Terms Hindi news keeps in English (flight numbers, agency names such as NDRF or "
          "NASA) may stay in Latin letters. You never invent anything.")

DEATH_BRIEF = """STORY: {name} has died. Write a respectful Hindi TV news obituary report: what happened, and the
record that made {object} known.

Shape (a news obituary, in this order):
1. Lead (beat 1, under 16 words): say plainly that {name} has died (respectful Hindi such as "का निधन"), with the
   age and the date if the SOURCE gives them, and who {pronoun} was in a few words.
2. Where and how the news was confirmed, attributed, only as the SOURCE states it.
3. The start of the career, with the year.
4. The best-known works or achievements, named with their years.
5. Honours and records from the SOURCE, with years.
6. The reactions or what follows (funeral, tributes) if the SOURCE states them, otherwise one factual line on what
   {pronoun} leaves behind. The last beat is one short, respectful factual sentence.
Do not describe the cause or manner of death unless the SOURCE states it plainly; never mention suicide."""

INCIDENT_BRIEF = """STORY: {name}. Write a Hindi TV news report of what happened, with compassion for everyone
affected.

Shape (a news report, in this order):
1. Lead (beat 1, under 16 words): what happened, where and when, as a plain news sentence with the key number.
2. The details: the sequence of events with times, places and figures, each attributed ("अधिकारियों के मुताबिक").
3. The people affected, with official figures only if the SOURCE gives them.
4. The official response: rescuers, officials, investigators, and what they said.
5. What is still unknown or under investigation, said plainly.
6. आगे क्या: the next step officials have announced. The last beat is one short factual sentence.
Never name or describe any attacker, perpetrator or suspect. Never guess at causes. No graphic detail of injuries or
death."""

PROTEST_BRIEF = """STORY: {name}. Write a Hindi TV news report that explains, fairly and calmly, what this protest
or movement is, why people took to the streets, and where it stands now.

Shape (a news report, in this order):
1. Lead (beat 1, under 16 words): the newest development in the SOURCE, as a plain news sentence.
2. How it began: the trigger, with dates.
3. Who is involved and what they demand, attributed ("आयोजकों का कहना है", "पार्टी का कहना है").
4. How the government, police or courts responded, attributed to them.
5. The turning point or the latest step.
6. What happens next, or what is still unresolved. The last beat is one short, steady sentence.
Be strictly neutral: give each side's position as the SOURCE states it, never take a side, never mock or praise any
person, party, community or religion, and use no loaded words. Attribute every disputed claim and every injury,
arrest or crowd figure to whoever reported it ("पुलिस के मुताबिक", "आयोजकों के अनुसार"). Never urge anyone to join or
avoid a protest. Never mention suicide."""

EXPLAINER_BRIEF = """STORY: {name}, in today's news: the story the first of TODAY'S LEAD HEADLINES points at (a
headline only shows which story; its words are not a source). Write a Hindi TV news report: a viewer who saw only
the headline knows, in 45 seconds, what happened, the key numbers, why, and what happens next.

Shape (a news report, in this order):
1. Lead (beat 1, under 16 words): a plain news sentence naming {name}: who did what, where and when, with the key
   number if there is one. Never a question, never a teaser.
2. The details: what exactly happened, with the dates, amounts and figures the REPORTING gives, each attributed
   ("रिपोर्टों के मुताबिक").
3. The official statement: what the government, company, court or person said, attributed to them.
4. क्यों: the reasons the REPORTING gives, each attributed to whoever gives it ("सरकार के मुताबिक", "पार्टी का कहना
   है"). If no report gives a reason, say plainly that no official reason has been given.
5. The other side: when the story is one side acting against, accusing or protesting another, say what the other
   side said in REPORTING, attributed; if REPORTING carries no response from them, say "रिपोर्टों में <them> की
   प्रतिक्रिया नहीं है" in one short line, naming them. Otherwise (a market, economy, science, weather or sports
   story has no other side) one line of background on {name} from the SOURCE, only the part this story needs
   (never a biography).
6. आगे क्या: the next step that is announced or due, or what is still unclear. The last beat is one short factual
   sentence, never a conclusion, a moral or an opinion.
Be strictly neutral: never take a side, never praise or mock any person, party, community or religion, use no loaded
words, and attribute every claim, allegation and criticism to whoever made it. Never guess at motives, never predict,
never give financial, legal or medical advice. Never mention suicide, and never write "जानें" (it reads as "lives
lost"). The title is a declarative news headline that states the news (never a question, never a teaser). A change
measured over several days or sessions names that span in the title ("4 दिन में 3% चढ़ा सेंसेक्स"), never as if it
happened in one day."""

RULES = """RULES (all mandatory):
- Use ONLY information in CONFIRMED FACTS and the SOURCES. Never add a name, title, number, place, date, quote, award
  or relationship that is not written there. If you are unsure, leave it out.
- Write in Hindi (Devanagari): the simple, spoken Hindi of Aaj Tak or ABP News, the words a viewer in Patna or
  Indore uses, neither Sanskritised nor slang: साल के not वर्षीय, डॉक्टर not चिकित्सक, फैसला not
  निर्णय, कोर्ट not न्यायालय, जज not न्यायाधीश, वकील not अधिवक्ता, हफ्ते not सप्ताह, शुरू not प्रारंभ, खत्म not
  समाप्त, कोशिश not प्रयास, बढ़ोतरी not वृद्धि, IMF not अंतरराष्ट्रीय मुद्रा कोष, मौसम विभाग not भारत मौसम विज्ञान
  विभाग, even where HINDI NAMES gives the formal name. Never translate an English idiom word for word: say what it means as a Hindi bulletin would ("high tea" is
  "चाय पर बैठक", never "उच्च चाय"; "huddle" is "बैठक"). 7 or 8 beats and 95 to 120 Hindi words in total (about 45 seconds spoken). Each beat is one or two spoken
  sentences of 10 to 18 words. Count the words before you answer.
- Register: a Hindi TV news bulletin read by an anchor. Third person, complete sentences. A claim, allegation or
  reported figure says who gives it, by name ("अस्पताल ने बताया", "पुलिस का कहना है", "NDTV के मुताबिक"); a fact on
  the record (a past office, a year, a known role) needs no attribution. Use the vague "रिपोर्टों के मुताबिक" in at
  most 2 beats and never "स्रोत के अनुसार". Never address the viewer, never "आइए",
  "दोस्तों", "सोचिए", "क्या आप जानते हैं", never an exclamation, never a rhetorical question.
- Every beat must carry a specific, checkable fact from the SOURCES (a number, a date, a name, a decision, an official
  statement); no vague praise, no feelings, no opinion, no moral or conclusion of your own.
- Vary how beats open, and never start more than 2 beats with the same word.
- Lead: beat 1 states the news itself within its first 5 words (who or what, then what happened), never a date, a
  greeting, a question or a slow introduction.
- Every beat adds one new fact; no recap, no filler, no empty lines such as "यह खबर चर्चा में है" or "यह देखना
  होगा".
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
- caption: the beat's key fact as a news graphic shows it, 1 to 4 Hindi words: a number with its unit ("11.39%",
  "6 लाख घर", "2 घंटे"), a date, a decision ("उड़ान डायवर्ट"), a role or an honour. Prefer a number whenever the beat
  has one. Never a place name alone: viewers read a place over a photo as where the photo was taken.
- label: 1 to 3 Hindi words under the caption that say what the caption measures or who said it ("थोक महंगाई",
  "बिजली गुल", "एयर इंडिया का बयान", "स्क्वॉक कोड", "आगे क्या"). Never a bare section name such as "मुख्य खबर",
  "विवरण", "अन्य पक्ष" or "पृष्ठभूमि". No numbers in a label.
- title: "<who or what, in English letters>: <Hindi headline>", 30 to 75 characters, the way Aaj Tak writes a
  Shorts title ("Rahul Gandhi: ..."), in everyday Hindi (never formal Sanskritised words), that states the news (who,
  what), no clickbait, no capitals for effect.
Return only the JSON."""

# Owner, 2026-10-15: titles were "too much difficult hindi and not interesting". The title is what people read
# before they decide to watch, and the headline bar on screen: a Hindi news website's headline, not a gazette's.
TITLE_BRIEF = """Write 5 different YouTube Shorts titles for the Hindi news Short whose SCRIPT is below.

- Shape: "<Kicker>: <headline>", the way Aaj Tak, ABP News and NDTV India title their Shorts ("Tiger Shroff Firing:
  कहां से गिरफ्तार हुए तीनों शूटर्स?", "Akhilesh Yadav की रैली में नहीं पहुंचे लोग"). The kicker is 1 to 4 words in
  English letters, spelled the way Indians type it into YouTube search: the famous person's name ("Rahul Gandhi",
  "LK Advani", "Imran Khan") or the topic ("Supreme Court", "Air India", "Sensex", "Delhi Metro", "Chennai Rain").
  Only words the English sources use.
- The headline is everyday Hindi, the words people say, the way Aaj Tak, Dainik Bhaskar or Navbharat Times write a
  web headline. Keep the English words Hindi news keeps (IMF, GDP, IPO, RBI, सुप्रीम कोर्ट, शेयर बाजार, फ्लाइट,
  एयरपोर्ट, बैंक). Never formal Sanskritised words: महंगाई not मुद्रास्फीति, अपील not आह्वान, सुप्रीम कोर्ट not सर्वोच्च
  न्यायालय, IMF not अंतर्राष्ट्रीय मुद्रा कोष, मौसम विभाग not भारत मौसम विज्ञान विभाग, तरीका not पद्धति, के बाद not
  उपरांत, हफ्ते not सप्ताह, बेंच not पीठ, साल के not वर्षीय.
- 35 to 75 characters in all. After the kicker, the most striking concrete fact: the number, the decision, or what
  it means for people. Never open with an official's title or an institution's full name ("जस्टिस ... की पीठ",
  "सॉलिसिटर जनरल ...", "भारत मौसम विज्ञान विभाग"): viewers stop for a name they know or for what changes for them.
- When the name could mean someone else, the headline gives the role the SCRIPT gives ("Imran Khan: अभिनेता को ...",
  "केंद्रीय मंत्री ..."), so no one mistakes them for someone else with that name.
- A headline's active voice ("सरकार बेचेगी IDBI बैंक में हिस्सेदारी", "सेंसेक्स 1100 अंक उछला"), never a stiff passive
  ("...किया गया").
- It may end with a short reason hook that this Short answers (", वजह क्या है?", ", क्यों?"), but only after a part
  that states the news. Never a question alone, never a teaser that hides the news.
- Only facts the SCRIPT states, every number exactly as the SCRIPT gives it. No clickbait (चौंकाने वाला, सनसनीखेज,
  बड़ी खबर, ब्रेकिंग, जानिए, जानें), no exclamation mark, no emoji, no words in capitals for effect.
{earlier}
The kind of change wanted (old title -> better title):
- "अन्तर्राष्ट्रीय मुद्रा कोष ने भारत की जीडीपी गणना पद्धति का समर्थन किया" -> "IMF: भारत का GDP गिनने का नया तरीका सही"
- "राजनाथ सिंह ने भारत-आसियान रक्षा सहयोग बढ़ाने का आह्वान किया" -> "Rajnath Singh: आसियान देशों से अपील, रक्षा में साथ बढ़ाएं"
- "एअर इंडिया की उड़ान को जयपुर डायवर्ट किया गया" -> "Air India: फ्लाइट अचानक जयपुर उतारी गई, क्या थी वजह?"
- "जस्टिस जेबी पारदीवाला की पीठ ने इंटरनेट को मौलिक अधिकार माना" -> "Supreme Court: इंटरनेट अब मौलिक अधिकार, कोर्ट ने माना"
- "लालकृष्ण आडवाणी अपोलो अस्पताल में भर्ती, सीने में संक्रमण" -> "LK Advani: 98 साल के आडवाणी अस्पताल में भर्ती, सीने में इन्फेक्शन"

SCRIPT:
{script}

HINDI HEADLINES (how Hindi newsrooms write this story; style only, never a source):
{hints}

Return {{"titles": [5 titles]}}."""
TITLE_SCHEMA = {"type": "object", "properties": {"titles": {"type": "array", "items": {"type": "string"}}},
                "required": ["titles"]}
# Formal words a Hindi web headline never uses, and what it says instead.
HARD_WORDS = {
    "मुद्रास्फीति": "महंगाई", "अन्तर्राष्ट्रीय मुद्रा कोष": "IMF", "अंतर्राष्ट्रीय मुद्रा कोष": "IMF",
    "अंतरराष्ट्रीय मुद्रा कोष": "IMF", "अन्तर्राष्ट्रीय": "अंतरराष्ट्रीय", "अंतर्राष्ट्रीय": "अंतरराष्ट्रीय",
    "सर्वोच्च न्यायालय": "सुप्रीम कोर्ट", "उच्च न्यायालय": "हाई कोर्ट", "आह्वान": "अपील", "रक्तस्रावी": "(leave it out)",
    "पद्धति": "तरीका", "सूचकांक": "(leave it out)", "मौसम विज्ञान विभाग": "मौसम विभाग", "हेतु": "के लिए",
    "उपरांत": "के बाद", "उपरान्त": "के बाद", "पश्चात": "के बाद", "अधिसूचना": "नोटिफिकेशन", "निर्वाचन आयोग": "चुनाव आयोग",
    "प्रक्षेपण": "लॉन्च", "प्रक्षेपित": "लॉन्च", "विमानपत्तन": "एयरपोर्ट", "चालक दल": "क्रू", "सम्बन्धी": "से जुड़ा",
    "संबंधी": "से जुड़ा", "आधारित": "(leave it out)", "द्वारा": "ने", "वित्तीय वर्ष": "वित्त वर्ष", "प्रतिशत": "%",
    "वर्षीय": "साल के", "परामर्शदाता": "डॉक्टर", "चिकित्सक": "डॉक्टर", "चिकित्सा": "इलाज",
    "न्यायालय": "कोर्ट", "न्यायाधीश": "जज", "न्यायमूर्ति": "जस्टिस", "अधिवक्ता": "वकील", "की पीठ": "की बेंच",
    "सप्ताह": "हफ्ते", "निर्णय": "फैसला", "प्रारंभ": "शुरू", "प्रारम्भ": "शुरू", "आरंभ": "शुरू", "आरम्भ": "शुरू",
    "समाप्त": "खत्म", "प्रयास": "कोशिश", "वृद्धि": "बढ़ोतरी", "आवश्यक": "ज़रूरी", "प्रदान": "दिया",
    "अंतर्गत": "के तहत", "अन्तर्गत": "के तहत", "तत्काल": "तुरंत", "यथाशीघ्र": "जल्द", "उपरोक्त": "(leave it out)",
    "वार्ता": "बातचीत", "आग्रह": "अपील", "दुर्घटनाग्रस्त": "हादसे का शिकार", "भारत मौसम विज्ञान": "मौसम विभाग",
    "संयुक्त राज्य": "अमेरिका", "यूनाइटेड किंगडम": "ब्रिटेन",
}
# Spoken narration says "प्रतिशत"; only a title or a card writes "%".
SAID_OK = {"प्रतिशत"}
# "LK Advani: ..." — the name or topic in English letters, as Hindi news channels title their Shorts and as viewers
# search for them.
KICKER = re.compile(r"^[A-Za-z][A-Za-z0-9.&'’\- ]{1,34}:\s")
GENERIC_SOURCE = re.compile(r"(रिपोर्टों|रिपोर्ट|सूत्रों) के (मुताबिक|अनुसार)")
NAMELESS_SOURCE = re.compile(r"स्रोत(ों)? के (मुताबिक|अनुसार)")
TITLE_MAX = 80
TITLE_HINDI = gate.TITLE_HINDI
WHY_HOOK = re.compile(r"^[^?]{12,}[,:।\-–]\s*[^,:?]{0,20}(क्यों|वजह|कारण)[^,:?]{0,20}\?$")
CLICKBAIT = re.compile(r"सनसनीखेज|चौंकाने|खौफनाक|ख़ौफ़नाक|ब्रेकिंग|बड़ी खबर|बड़ी ख़बर|जानिए|जानिये|जानें|देखिए|!")
# A title may give a cause only with whoever gives it: "आयोजकों की घोषणा बनी वजह" (Kolkata dry run, 2026-10-18)
# stated as fact what the script attributed to the chief minister.
STATED_CAUSE = re.compile(r"(बनी|बना|बने|थी|था|है) (वजह|कारण)|(वजह|कारण) (बनी|बना|बने)")
ATTRIBUTED = re.compile(r"मुताबिक|अनुसार|बोले|बोलीं|बोला|ने कहा|का कहना|का दावा|का आरोप|ने बताया|ने बताई")


def hard_words(text: str, allowed: set[str] = frozenset()) -> list[str]:
    return [f"write {w!r} as {easy}" for w, easy in HARD_WORDS.items() if w in text and w not in allowed]


def everyday_names(hi_names: dict[str, str]) -> dict[str, str]:
    """Wikidata's Hindi labels minus the formal ones (IMF is "अन्तर्राष्ट्रीय मुद्रा कोष" there, IMD "भारत मौसम विज्ञान
    विभाग"): a formal label must never be the spelling the writer is held to."""
    return {en: hi for en, hi in hi_names.items() if not hard_words(hi)}


def plain_name(name_hi: str | None, draft: dict, name: str) -> str:
    """The story's Hindi name for the description and hashtags: Wikidata's, unless formal, else the writer's."""
    if name_hi and not hard_words(name_hi):
        return name_hi
    return _pair_for(draft, name) or name_hi or name


def bookish(draft: dict) -> list[str]:
    """Narration and cards in a government notice's Hindi, or attributed to nobody in particular."""
    beats = draft.get("beats") or []
    shown = " ".join(b.get("say", "") + " " + b.get("caption", "") + " " + b.get("label", "") for b in beats)
    problems = [f"in the narration and cards, {p}" for p in hard_words(shown, SAID_OK)]
    if any(NAMELESS_SOURCE.search(b.get("say", "")) for b in beats):
        problems.append("never write \"स्रोत के अनुसार\": name who says it, or give an on-the-record fact plainly")
    vague = sum(bool(GENERIC_SOURCE.search(b.get("say", ""))) for b in beats)
    if vague > 2:
        problems.append(f"{vague} beats say \"रिपोर्टों के मुताबिक\"; at most 2: name who says it (the hospital, the "
                        "police, the court, the outlet), and give on-the-record facts plainly")
    return problems


def question_title(title: str) -> bool:
    """A title that asks instead of telling: a "?" that is not a reason hook after the news."""
    title = title.strip()
    return "?" in title and not WHY_HOOK.match(title)


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
    return " ".join(b.get("say", "") + " " + b.get("caption", "") + " " + b.get("label", "")
                    for b in draft.get("beats", [])) + " " + \
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
    problems += casual(draft)
    problems += [f"beat {i + 1} says no reply from an unnamed side; name who did not respond, or give background "
                 "instead when the story has no other side" for i, b in enumerate(beats)
                 if NOBODY_REPLIED.search(b.get("say", ""))]
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


CASUAL = re.compile(r"आइए|आइये|दोस्तों|सोचिए|सोचिये|क्या आप|आपको बता दें|जानिए|जानिये|!")
# "रिपोर्टों में अन्य पक्षों की प्रतिक्रिया नहीं है" in a Sensex Short (2026-10-16): filler, since a market has no side.
NOBODY_REPLIED = re.compile(r"(अन्य|दूसरे|दूसरा|किसी|विपक्षी) पक्ष\S*( की| का| से)? (कोई )?प्रतिक्रिया")


def casual(draft: dict) -> list[str]:
    """A bulletin is read, not chatted: no viewer address, no exclamation, no question headline or lead."""
    beats = draft.get("beats") or []
    problems = [f"beat {i + 1} talks to the viewer or exclaims ({m.group(0)}); report it in the third person"
                for i, b in enumerate(beats) if (m := CASUAL.search(b.get("say", "")))]
    if question_title(draft.get("title") or ""):
        problems.append("the title must be a news headline that states the news, not a question")
    if beats and "?" in beats[0].get("say", ""):
        problems.append("beat 1 must state the news, not ask a question")
    return problems


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


def hindi_hints(cand: dict) -> list[str]:
    """The story's Hindi lead headlines, the top-ranked first."""
    heads = (cand.get("top_headlines") or []) + (cand.get("hindi_headlines") or [])
    return [h for h in dict.fromkeys(heads) if hindi.devanagari_share(h) > 0.3][:5]


def title_problems(title: str, draft: dict, subject: dict, ground_en: str, kind: str, agreed_toll: bool,
                   reports: list[dict] | None = None, earlier: list[str] | None = None) -> list[str]:
    """What keeps a title from going out: hard words, length, a bare question, clickbait, capitals, a number the
    script does not give, a Latin word the sources lack, no name from the story, or an earlier part's title."""
    title = title.strip().strip('"')
    names = [p for p in draft.get("names") or [] if isinstance(p, dict)]
    problems = hard_words(title)
    if not 20 <= len(title) <= TITLE_MAX:
        problems.append(f"{len(title)} characters (want 20-{TITLE_MAX})")
    if hindi.devanagari_share(title) < TITLE_HINDI:
        problems.append("not in Hindi")
    if question_title(title):
        problems.append("a question alone: state the news first")
    if m := CLICKBAIT.search(title):
        problems.append(f"clickbait ({m.group(0)})")
    problems += [f"capitals for effect ({w})" for w in re.findall(r"\b[A-Z][A-Z\-]{3,}\b", title)
                 if w not in gate.ACRONYMS]
    bad = hindi.unsupported_numbers(title, hindi.values(script_text(draft)))
    if bad:
        problems.append("numbers the script does not give: " + ", ".join(bad))
    for w in sorted(set(hindi.latin_words(title))):
        if not (w.upper() in gate.ACRONYMS and w.upper() == w) and not hindi.contains(ground_en, w) \
                and len(gate.reported(w, reports or [])) < gate.OWNERS_NEEDED:
            problems.append(f"{w!r} is not in the sources")
    latin = {w.lower() for w in hindi.latin_words(title)}
    named = subject_in(title, subject, names) or any(hindi.contains(title, p.get("hi", "")) for p in names if p.get("hi")) \
        or any(w in (p.get("en") or "").lower().split() for p in names for w in latin)
    if not named:
        problems.append("it names no one and nothing from the story")
    problems += gate.decorum(title, "incident" if kind in ("incident", "protest") else kind, agreed_toll)
    if STATED_CAUSE.search(title) and not ATTRIBUTED.search(title) and "?" not in title:
        problems.append("it states a cause as fact: say who gives it (\"... के मुताबिक\", \"... बोले\") or leave the "
                        "cause out")
    if any(hindi.norm(title) == hindi.norm(e) for e in earlier or [] if e):
        problems.append("an earlier part already has this title")
    return problems


def retitle(pen: "Pen", draft: dict, subject: dict, ground_en: str, kind: str, agreed_toll: bool,
            reports: list[dict] | None = None, hints: list[str] | None = None,
            earlier: list[str] | None = None) -> tuple[str, dict]:
    """The best title for a draft that passed every check: the first of the headline editor's options with no
    problem (two rounds), else the draft's own title when it has none, else the draft's title anyway. Also the
    record of what was tried."""
    script = "\n".join(b.get("say", "") for b in draft.get("beats") or [])
    past = ("EARLIER TITLES (earlier parts of this story; this title must tell what is new):\n"
            + "\n".join(f"- {e}" for e in earlier) + "\n") if earlier else ""
    messages = [{"role": "system", "content": "You are the headline editor of a popular Hindi news website."},
                {"role": "user", "content": TITLE_BRIEF.format(script=script, earlier=past,
                                                               hints="\n".join(f"- {h}" for h in hints or [])
                                                               or "- (none)")}]
    record = {"options": [], "own": draft.get("title", "")}
    for _ in range(2):
        try:
            answer = pen.chat(messages, TITLE_SCHEMA, temperature=0.8, max_tokens=600)
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"[:200]
            break
        options = [str(t).strip().strip('"') for t in (answer.get("titles") or []) if str(t).strip()]
        tried = [(t, title_problems(t, draft, subject, ground_en, kind, agreed_toll, reports, earlier))
                 for t in options]
        record["options"] += [{"title": t, "problems": p} for t, p in tried]
        usable = [t for t, p in tried if not p]
        good = next((t for t in usable if KICKER.match(t)), usable[0] if usable else None)
        if good:
            record["chosen"] = good
            return good, record
        messages = messages + [{"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
                               {"role": "user", "content": "None of these can be used:\n" + "\n".join(
                                   f"- {t}: {'; '.join(p)}" for t, p in tried) + "\nWrite 5 new titles."}]
    own = draft.get("title", "")
    record["chosen"] = own
    record["own_problems"] = title_problems(own, draft, subject, ground_en, kind, agreed_toll, reports, earlier)
    return own, record


def write(kind: str, subject: dict, pronoun: str, facts: list[str], source_en: str, source_hi: str,
          photos: list[dict], hi_names: dict[str, str], banned_names: list[str] | None = None,
          agreed_toll: bool = False, log_path: Path | None = None, headlines: list[str] | None = None,
          angle: str | None = None, pen: Pen | None = None,
          today_ok: bool = True, reports: list[dict] | None = None, title_hints: list[str] | None = None,
          earlier: list[str] | None = None) -> tuple[dict, list[dict], list[str]]:
    """The script as {title, beats: [{say, photo, caption}], names}, the log of rejected drafts (also kept at
    log_path), and the models that answered. kind is "death", "incident" or "protest". reports: trusted outlets'
    articles ({outlet, owner, at, title, excerpt, text}), see the module docstring. title_hints: the story's Hindi
    lead headlines (the title's style); earlier: the titles of this story's earlier parts today (a follow-up part)."""
    obj = {"He": "him", "She": "her"}.get(pronoun, "them")
    hi_names = everyday_names(hi_names)
    if subject.get("hi") and hard_words(subject["hi"]):
        subject = subject | {"hi": None}
    brief = {"death": DEATH_BRIEF, "protest": PROTEST_BRIEF, "explainer": EXPLAINER_BRIEF}.get(kind, INCIDENT_BRIEF)
    brief = brief.format(name=subject["en"], pronoun=pronoun.lower(), object=obj)
    if earlier:
        brief += ("\n\nFOLLOW-UP: this channel already published " + str(len(earlier)) + " Short(s) on this story "
                  "today, titled: " + "; ".join(f'"{e}"' for e in earlier) + ". The REPORTING below is newer. Lead "
                  "with what is new in it (a new development, decision, reaction or figure), give at most one short "
                  "line of what was already told, and never repeat the earlier Short beat by beat.")
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
                problems += monotone(draft) + bookish(draft)
            if not problems:
                script = "\n".join(b["say"] for b in draft["beats"])
                verdict = pen.chat(_check_messages(script, draft.get("names", []), facts, source_en, source_hi,
                                                   doubtful, reports), CHECK_SCHEMA, temperature=0.0, max_tokens=800)
                items = [str(u).strip() for u in verdict.get("unsupported", []) if str(u).strip()]
                ignored = [u for u in items if not hindi.quotes(u, script_text(draft))
                           or unlisted_but_sourced(u, ground_en)]
                problems = [f"unsupported: {u}" for u in items if u not in ignored]
            if not problems:
                draft["title"], draft["titles"] = retitle(pen, draft, subject, ground_en, kind, agreed_toll,
                                                          reports, title_hints, earlier)
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


def fill_photos(context_qids: list[str], folder: Path, exclude: set[str], need: int = MIN_PHOTOS,
                scene: tuple[str, list[str]] | None = None) -> list[dict]:
    """Photos of the places and things a story links to that feature no face: Commons (each item's main image and
    files from its article naming it), then, while fewer than `need`, Openverse photos naming the item. scene (the
    place and the scene words its headlines share) puts Commons photos of that kind of scene first, so a stampede at
    a puja pandal opens on a pandal, not on the city's landmarks."""
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

    kept = faceless(media.scene(*scene, exclude=exclude), "scene") if scene and scene[1] else []
    kept += faceless(media.context(context_qids, exclude=exclude | {r["file"] for r in kept}), "context")
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
                             log_path=work / "writer_log.json", angle=angle, today_ok=days == 0, reports=reports,
                             title_hints=hindi_hints(cand))
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
                  cat="death", ov=ov, reports=reports)


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
                             reports=reports, title_hints=hindi_hints(cand))
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
                  cat=cat, ov=ov, reports=reports)


def _pair_for(draft: dict, name: str) -> str | None:
    return next((p["hi"] for p in draft.get("names", []) if p.get("en", "").lower() == name.lower()), None)


# How Aaj Tak, ABP News and NDTV India tag their Shorts (read 2026-10-19): the subject in English letters, its "news"
# form, then the broad tags Hindi news viewers search. Joined-up Devanagari tags alone (#लालकृष्णआडवाणी) are what
# almost nobody types.
TOPIC_TAGS = {"court": "courtnews", "economy": "businessnews", "weather": "weatherupdate", "aviation": "aviationnews",
              "entertainment": "entertainmentnews", "health": "healthnews", "disaster": "disasternews",
              "cyclone": "cyclone", "death": "tribute", "world": "worldnews"}
TEXT_TAGS = (("सुप्रीम कोर्ट", "supremecourt"), ("हाई कोर्ट", "highcourt"), ("सेंसेक्स", "sensex"),
             ("शेयर बाजार", "sharemarket"))
BROAD_TAGS = ["latestnews", "newsinhindi", "hindisamachar"]


def search_name(name: str) -> str:
    """The subject the way viewers type it ("L. K. Advani" -> "LK Advani"), or "" when it is no short name (an event
    title such as "2026 anti-CEC protests")."""
    plain = re.sub(r"\s*\(.*?\)", "", name or "").strip()
    plain = re.sub(r"\b([A-Z])\.\s*(?=[A-Z]\.)", r"\1", plain)
    plain = re.sub(r"(?<![a-z])([A-Z])\.\s*", r"\1 ", plain).strip()
    words = plain.split()
    if not 1 <= len(words) <= 3 or len(plain) > 25 or not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]*", plain):
        return ""
    return plain


def hashtags_for(name: str, name_hi: str, cat: str, region: str, text: str) -> list[str]:
    tag = re.sub(r"[^A-Za-z0-9]", "", search_name(name)).lower()
    out = [tag, "hindinews", "shorts", tag + "news" if tag else ""]
    out += [t for word, t in TEXT_TAGS if word in text] + [TOPIC_TAGS.get(cat, "")] + BROAD_TAGS
    out += ["indianews" if region == "india" else "worldnews", name_hi]
    return [t for t in dict.fromkeys(out) if t][:14]


def search_tags(name: str) -> list[str]:
    who = search_name(name).lower()
    return ([who, f"{who} news", f"{who} latest news"] if who else []) + [
        "hindi news", "latest news", "news in hindi", "today news", "hindi samachar"]


def _short(sid, kind, name, name_hi, draft, log, used, facts, facts_text, source, photos, sources, event_time, loss,
           mood, tags, summary, cat="", region="world", ov=None, reports=None, credit=CREDIT) -> Short:
    reports = reports or []
    name_hi = plain_name(name_hi, draft, name)
    hashtags = hashtags_for(name, name_hi, cat, region, script_text(draft))
    tags = tags + search_tags(name)
    beats = [Beat(b["say"].strip(), f"photo:{b['photo']}",
                  {"big": b["caption"].strip(), "small": (b.get("label") or "").strip()}) for b in draft["beats"]]
    beats.append(Beat(OUTRO, "outro", {"big": config.NAME_HI or config.NAME or "", "small": "स्रोत विवरण में"},
                      pause_after=0.5))
    ground = source + "\n" + "\n".join(facts_text)
    in_ground, by_owner = hindi.values(ground), gate.reported_values(reports)
    allowed = {n for f in facts for n in f.numbers}
    shown = " ".join(b.text + " " + (b.card or {}).get("big", "") + " " + (b.card or {}).get("small", "")
                     for b in beats) + " " + draft["title"]
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
        title = f"{name_hi} का निधन" if kind == "death" else f"{name_hi}: पूरा मामला"
        if ov:
            title = f"{name_hi}: {orbitwire.ANGLES[ov['angle']]['label']}"
    if any(media.from_openverse(p) for p in photos):
        credit = credit.replace("Wikimedia Commons", "Wikimedia Commons और Openverse")
    if reports:
        credit += "; रिपोर्टिंग: " + ", ".join(outlets.names(reports))
    credits = [credit] + sorted({p["credit"] + " " + p["page"] for p in photos})
    scene = {"template": "bulletin", "mood": mood, "voice": "sulafat", "region": region, "photos": photos,
             "name_hi": name_hi, "names": draft.get("names", []),
             "writer": {"models": used, "rejected": log, "titles": draft.get("titles")}}
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
    photos = fill_photos(context, work / "photos", exclude,
                         scene=(name, outlets.scene_words(cand.get("headlines") or [cand["title"]], name)))[:8] \
        if context else []
    if len(photos) < REPORT_PHOTOS:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} (want {REPORT_PHOTOS})"
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
                             reports=reports, title_hints=hindi_hints(cand))
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
                   cat=cat, ov=ov, reports=reports, credit=REPORT_CREDIT)
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
                         context_qids=None if person else context)
    need = 1 if person and (cand.get("top_score") or 0) >= LEAD_SCORE else REPORT_PHOTOS
    if len(photos) < need:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} on Wikimedia Commons (want {need})"
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
                             angle=ov["angle"] if ov else None, today_ok=when == _today_ist(), reports=reports,
                             title_hints=hindi_hints(cand), earlier=cand.get("earlier"))
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
                   cat=cat, ov=ov, reports=reports, credit=EXPLAIN_CREDIT)
    short.scene.update(qid=qid, category=cat, category_hi=label, headlines=cand.get("headlines") or [], story=story,
                       min_photos=need)
    return short


def build(cand: dict) -> Short:
    if (cand.get("id") or "").startswith("kh-"):
        return build_explainer(cand)
    if (cand.get("id") or "").startswith("nw-"):
        return build_report(cand)
    return build_death(cand) if cand["kind"] == "death" else build_incident(cand)
