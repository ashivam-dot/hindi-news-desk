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
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import (config, explain, faces, gate, gemini, hindi, ledger, llm, media, orbitwire, outlets, stories, trends,
               visuals, wiki)
from .spec import Beat, Fact, Short

WORK = Path(__file__).resolve().parents[1] / "work"
MIN_PHOTOS = 3
REPORT_PHOTOS = 2  # the story's own photos for a kh- or nw- bulletin; desk/visuals.py adds who and where each beat names
SETTING_PHOTOS = 1  # a story centred on a city or state keeps one of its photos
# A kh- story about a person shows only their own photos: their school or birthplace says nothing about today's news
# (Dhruv Rathee, 2026-10-17: seven of twelve frames were buildings). One photo is enough for a story this high in
# Google News India's top stories (Abhijeet Dipke's detention led them for four days and failed 21 times on 1 photo).
LEAD_SCORE = 0.9
MAX_DEATH_DAYS = 7
IST = timezone(timedelta(hours=5, minutes=30))
CREDIT = "तथ्य: Wikipedia (CC BY-SA 4.0) और Wikidata (CC0); तस्वीरें: Wikimedia Commons (लाइसेंस नीचे)"
# About 25-35 s at the narrator's 2.4 words a second. Shorts of 15-30 s get 14% more views than a 10K-100K channel's
# median and those over 60 s fewer (TrendReport, 3.48M Shorts, 2025-26); the 45-50 s Kyun Hua Shorts padded the
# news with biography and "no response" lines to fill 95-120 words (owner, 2026-10-21).
# The first dry run of the full template (2026-10-21) passed 90 words in five 18-word beats: 40 s.
MIN_WORDS, MAX_WORDS, MAX_BEAT_WORDS = 52, 82, 18
WORDS_ASKED = "60 to 80"
DRAFTS = 4
HOOK_WORDS = 4  # "मुम्बई में बॉलीवुड अभिनेता टाइगर श्रॉफ की कार पर..." made viewers wait for the name (2026-10-20)
PLACE_FACE = 0.06  # a face this share of a place photo's shorter side features a person
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "beats": {"type": "array", "minItems": 5, "maxItems": 8, "items": {
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
1. Hook (beat 1, 8 to 14 words): the most striking verified fact, what happened and to whom or how many, said
   with gravity, never for shock.
2. Where and when, then the sequence of events with times, places and figures, each attributed ("अधिकारियों के
   मुताबिक").
3. The people affected, with official figures only if the SOURCE gives them.
4. The official response: rescuers, officials, investigators, and what they said.
5. What is still unknown or under investigation, said plainly.
6. आगे क्या / काम की बात: the last beat says what happens next (the next step officials announced, a hearing, a
   deadline) or what it means for people (a road or a service closed, a helpline, compensation), only as the SOURCE
   states it, in one short factual sentence.
Never name or describe any attacker, perpetrator or suspect. Never guess at causes. No graphic detail of injuries or
death."""

PROTEST_BRIEF = """STORY: {name}. Write a Hindi TV news report that explains, fairly and calmly, what this protest
or movement is, why people took to the streets, and where it stands now.

Shape (a news report, in this order):
1. Hook (beat 1, 8 to 14 words): the newest and most striking development in the SOURCE, as a plain news sentence.
2. Where and when, and how it began: the trigger, with dates.
3. Who is involved and what they demand, attributed ("आयोजकों का कहना है", "पार्टी का कहना है").
4. How the government, police or courts responded, attributed to them.
5. The turning point or the latest step.
6. आगे क्या / काम की बात: what happens next (a talk, a hearing, a deadline) or what it means for people (roads,
   exams, services), or what is still unresolved, only as the SOURCE states it. The last beat is one short, steady
   sentence.
Be strictly neutral: give each side's position as the SOURCE states it, never take a side, never mock or praise any
person, party, community or religion, and use no loaded words. Attribute every disputed claim and every injury,
arrest or crowd figure to whoever reported it ("पुलिस के मुताबिक", "आयोजकों के अनुसार"). Never urge anyone to join or
avoid a protest. Never mention suicide."""

EXPLAINER_BRIEF = """STORY: {name}, in today's news: the story the first of TODAY'S LEAD HEADLINES points at (a
headline only shows which story; its words are not a source). Write a Hindi TV news report: a viewer who saw only
the headline knows, in 45 seconds, what happened, the key numbers, why, and what happens next.

Shape (a news report, in this order):
1. Hook (beat 1, 8 to 14 words): a plain news sentence naming {name} and the most striking fact of the story, who
   did what, with the key number if there is one. Never a question, never a teaser.
2. Where and when, then the details: what exactly happened, with the dates, amounts and figures the REPORTING gives,
   each attributed ("रिपोर्टों के मुताबिक").
3. The official statement: what the government, company, court or person said, attributed to them.
4. क्यों: the reasons the REPORTING gives, each attributed to whoever gives it ("सरकार के मुताबिक", "पार्टी का कहना
   है"). If no report gives a reason, say plainly that no official reason has been given.
5. The other side, only when the story is a dispute between two named sides (a party against a party, a government
   against a court, a company against a regulator): what the other side said in REPORTING, attributed. Leave this
   step out when REPORTING carries no reply, and always for a crime or an attack (attackers and accused are not a
   side). Never a line that someone has not responded, and never a biography of {name}.
6. आगे क्या / काम की बात: what the news means for people (a price, a rule, a date, a service that changes for
   them) or the next step that is announced or due, or what is still unclear, only as the REPORTING states it and
   attributed. The last beat is one short factual sentence, never a conclusion, a moral, an opinion or advice.
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
  "चाय पर बैठक", never "उच्च चाय"; "huddle" is "बैठक"). 6 or 7 beats and {words} Hindi words in total (about 30
  seconds spoken). Each beat is one spoken sentence, or two short ones, 8 to 14 words in all. Count the words before
  you answer.
- Names: call every person by the name the public knows and Hindi newsrooms print (जैकी श्रॉफ, never his birth name
  जय किशन श्रॉफ; लालकृष्ण आडवाणी), the spelling HINDI NAMES gives. A short, well-known form is fine after the first
  mention (आडवाणी, फडणवीस). A name HINDI NAMES does not give is written by its own sound, never as the Hindi
  spelling of a better-known name (Chennai's Parrys is not पैरिस, which every Hindi reader takes for Paris).
- News only: every beat is about today's story. No biography of anyone (their films, debut, career, parents,
  awards) unless the story is their death or that fact is part of today's news. No line saying someone has not
  responded or that reports carry no reaction.
- Register: a Hindi TV news bulletin read by an anchor. Third person, complete sentences. A claim, allegation or
  reported figure says who gives it, by name ("अस्पताल ने बताया", "पुलिस का कहना है", "NDTV के मुताबिक"); a fact on
  the record (a past office, a year, a known role) needs no attribution. Use the vague "रिपोर्टों के मुताबिक" in at
  most 2 beats and never "स्रोत के अनुसार". Never address the viewer, never "आइए",
  "दोस्तों", "सोचिए", "क्या आप जानते हैं", never an exclamation, never a rhetorical question.
- Never give advice (what to buy, invest in, take or file), and never put it in an unnamed expert's mouth
  (विशेषज्ञों की सलाह, एक्सपर्ट्स का कहना): what changes for viewers is said as the SOURCES state it, with who says it
  ("RBI के मुताबिक", "रेलवे ने बताया").
- Every beat must carry a specific, checkable fact from the SOURCES (a number, a date, a name, a decision, an official
  statement); no vague praise, no feelings, no opinion, no moral or conclusion of your own.
- Vary how beats open, and never start more than 2 beats with the same word.
- Hook: half the viewers decide in the first second. Beat 1 opens on the single most striking verified fact, who or
  what and what happened, with the key number if there is one ("बस खाई में गिरी, 12 यात्रियों की मौत", not
  "सोमवार को उत्तराखंड में एक हादसा हुआ"). Where and when can wait for beat 2. Never a date, a greeting, a
  question, a slow introduction or a teaser that hides the news.
- Pull: beat 2 or 3 may name the open question the rest of the Short answers, as a plain statement the SOURCES
  support ("हमला किसने करवाया, पुलिस इसकी जांच कर रही है"), and a later beat answers it or says plainly that it is
  still unknown.
- Rhythm: write for the ear, the way an anchor speaks. Put the new fact first and who said it after ("..., पुलिस ने
  बताया"); active verbs; mix one very short sentence (5 to 8 words) with longer ones, never three beats of the same
  length in a row.
- Completeness: cover every key point the SOURCES give: what happened, who, where, when, how many, what officials
  or the people involved said, why (or that no reason is given), and what happens next. Leave out only what the
  SOURCES do not support.
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
  has one. Never a place name alone: viewers read a place over a photo as where the photo was taken. Beat 1's
  caption is the event itself ("कार पर फायरिंग", "12 की मौत"), never a time or a date.
- label: 1 to 3 Hindi words under the caption that say what the caption measures or who said it ("थोक महंगाई",
  "बिजली गुल", "एयर इंडिया का बयान", "स्क्वॉक कोड", "आगे क्या"). Never a bare section name such as "मुख्य खबर",
  "विवरण", "अन्य पक्ष" or "पृष्ठभूमि". No numbers in a label.
- title: one natural Hindi headline, 37 to 55 characters (never over 65), with the name or topic people search for in
  its first three words ("टाइगर श्रॉफ की कार पर फायरिंग, ..."), in everyday Hindi (never formal Sanskritised words),
  that states the news (who, what) as a concrete claim; no "Name:" label before it, no "वजह क्या है" tail, no
  clickbait, no capitals for effect.
Return only the JSON."""

# Owner, 2026-10-15: titles were "too much difficult hindi and not interesting". The title is what people read
# before they decide to watch, and the headline bar on screen: a Hindi news website's headline, not a gazette's.
TITLE_BRIEF = """Write 5 different YouTube Shorts titles for the Hindi news Short whose SCRIPT is below.

- Shape: one natural Hindi headline, the way Dainik Bhaskar, Navbharat Times or BBC Hindi write a web headline, with
  the name or topic people search for within its first three words, spelled as the SCRIPT spells it ("टाइगर श्रॉफ की
  कार पर फायरिंग, 3 आरोपी कोटा से पकड़े गए", "सेंसेक्स 1100 अंक उछला"). No "Name:" label in front of the headline.
  English letters only for what Hindi news keeps in English (IMF, GDP, IPO, RBI, Air India) and only words the
  English sources use.
- It makes one concrete claim (the number, the decision, or what changes for people), or asks the one specific
  question this Short answers after a part that states the news ("..., कोर्ट क्यों पहुंचे इमरान खान?"). Never the
  stock tails "वजह क्या है?", "क्या थी वजह?" or a bare ", क्यों?", never a question alone, never a teaser that hides
  the news.
- Everyday Hindi, the words people say. Keep the English words Hindi news keeps (IMF, GDP, IPO, RBI, सुप्रीम कोर्ट,
  शेयर बाजार, फ्लाइट, एयरपोर्ट, बैंक). Never formal Sanskritised words: महंगाई not मुद्रास्फीति, अपील not आह्वान,
  सुप्रीम कोर्ट not सर्वोच्च न्यायालय, IMF not अंतर्राष्ट्रीय मुद्रा कोष, मौसम विभाग not भारत मौसम विज्ञान विभाग, तरीका
  not पद्धति, के बाद not उपरांत, हफ्ते not सप्ताह, बेंच not पीठ, साल के not वर्षीय.
- 37 to 55 characters in all, never over 65. Never open with an official's title or an institution's full name ("जस्टिस ... की
  पीठ", "सॉलिसिटर जनरल ...", "भारत मौसम विज्ञान विभाग"): viewers stop for a name they know or for what changes for
  them.
- When the name could mean someone else, give the role the SCRIPT gives ("अभिनेता इमरान खान को ...", "केंद्रीय मंत्री
  ..."), so no one mistakes them for someone else with that name.
- A headline's active voice ("सरकार बेचेगी IDBI बैंक में हिस्सेदारी"), never a stiff passive ("...किया गया").
- Never open with the same three words as a RECENT TITLE below: each Short's title is its own.
- Only facts the SCRIPT states, every number exactly as the SCRIPT gives it. No clickbait (चौंकाने वाला, सनसनीखेज,
  बड़ी खबर, ब्रेकिंग, जानिए, जानें), no exclamation mark, no emoji, no words in capitals for effect.
{earlier}
The kind of change wanted (old title -> better title):
- "अन्तर्राष्ट्रीय मुद्रा कोष ने भारत की जीडीपी गणना पद्धति का समर्थन किया" -> "IMF ने माना, भारत का GDP गिनने का नया तरीका सही"
- "Rajnath Singh: आसियान देशों से अपील, रक्षा में साथ बढ़ाएं" -> "राजनाथ सिंह की आसियान देशों से अपील, रक्षा में साथ बढ़ाएं"
- "Air India: फ्लाइट अचानक जयपुर उतारी गई, क्या थी वजह?" -> "Air India की फ्लाइट अचानक जयपुर उतारी गई"
- "जस्टिस जेबी पारदीवाला की पीठ ने इंटरनेट को मौलिक अधिकार माना" -> "सुप्रीम कोर्ट ने माना, इंटरनेट अब मौलिक अधिकार"
- "Imran Khan: 28 अक्टूबर तक भारत छोड़ने का आदेश, वजह क्या है?" -> "अभिनेता इमरान खान को 28 अक्टूबर तक भारत छोड़ने का आदेश"

SCRIPT:
{script}

HINDI HEADLINES (how Hindi newsrooms write this story; style only, never a source):
{hints}

RECENT TITLES (other stories on this channel):
{recent}

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
    # Words in the Tiger Shroff and Nana Patekar Shorts (2026-10-20) that Aaj Tak and ABP say otherwise.
    "गोलीबारी": "फायरिंग", "अभियुक्त": "आरोपी", "प्राथमिकी": "FIR", "चिकित्सालय": "अस्पताल", "उपचार": "इलाज",
    "वाहन": "गाड़ी", "उपस्थित": "मौजूद", "उपस्थिति": "मौजूदगी", "वक्तव्य": "बयान", "सम्मिलित": "शामिल",
    "रेलगाड़ी": "ट्रेन", "अन्वेषण": "जांच", "चलचित्र": "फिल्म", "अभिनीत": "वाली",
    "पुलिस अधीक्षक": "SP", "पुलिस आयुक्त": "पुलिस कमिश्नर", "आग्नेयास्त्र": "हथियार",
    "क्षतिग्रस्त": "टूट गया", "यात्रीगण": "यात्री", "तत्पश्चात": "इसके बाद", "किन्तु": "लेकिन", "परन्तु": "लेकिन",
}
# Spoken narration says "प्रतिशत"; only a title or a card writes "%".
SAID_OK = {"प्रतिशत"}
# Titles (2026-10-22): "Name: headline" Shorts drew a median 35.5 views (20 Shorts) against 55 for the rest (54), and
# the five with a "वजह क्या है" tail 17; one template on every title also reads as mass-produced. So a title is one
# natural Hindi headline with the searchable name in its first TITLE_CORE_WORDS words, and never opens like one of
# the channel's last RECENT_TITLES titles. These are style rules (title_style): advisory on the last round. The
# "Name:" Shorts also carried hashtags and dates in their titles, so those figures cannot tell the label's effect
# from theirs (the revenue-push audit, kyun-hua-shorts-strategy.md, 2026-10-22).
KICKER = re.compile(r"^[A-Za-z][A-Za-z0-9.&'’\- ]{1,34}:\s")
STOCK_TAIL = re.compile(r"((वजह|कारण) क्या (है|थी|रही)|क्या (है|थी|रही) (वजह|कारण)|[,:।\-–]\s*क्यों)\s*\?\s*$")
TITLE_CORE_WORDS = 3
RECENT_TITLES = 20
GENERIC_SOURCE = re.compile(r"(रिपोर्टों|रिपोर्ट|सूत्रों) के (मुताबिक|अनुसार)")
NAMELESS_SOURCE = re.compile(r"स्रोत(ों)? के (मुताबिक|अनुसार)")
# Length (audit, 2026-10-22): RULES asked 30-75 characters and TITLE_BRIEF 35-75, and a title up to 80 passed. The
# aim is TITLE_AIM, advisory (title_style, and only its top: nothing under 37 has been tried on the channel);
# TITLE_MAX is hard, for the headline editor's titles and for the draft's own, which is retitle's fallback.
TITLE_AIM = (37, 55)
TITLE_MAX = 65
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
            + lead + "\n\nPHOTOS:\n" + listing + "\n\n" + RULES.format(best=0, name_hi=name_hi, words=WORDS_ASKED)
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
    """Problems for wording that dates an older event to today. आज भी, आज तक and अभी तक (so far) say what is still
    true, not when it happened."""
    hits = re.findall(r"(?<![\u0900-\u097F])(आज|अभी)(?!\s*(?:भी|तक)(?![\u0900-\u097F]))(?![\u0900-\u097F])", text)
    return ["this did not happen today: remove आज/अभी and give the date"] if hits else []


def off_case(draft: dict, names_ok: list[str], never: list[str] | None = None) -> list[str]:
    """Problems for a name the case file does not list, and for any of its never-say words (an accused's or a
    gang's name in English and Hindi) anywhere in the script: in a case Short that is how they are kept out."""
    ok = {n.strip().lower() for n in names_ok}
    text = script_text(draft) + " " + " ".join(f"{p.get('en', '')} {p.get('hi', '')}" for p in draft.get("names") or []
                                               if isinstance(p, dict))
    return [f"{p['en']} is not on this case's list of names: leave them out" for p in draft.get("names") or []
            if isinstance(p, dict) and isinstance(p.get("en"), str) and p["en"].strip()
            and p["en"].strip().lower() not in ok] + \
        [f"never name {w} (an accused or a gang): leave them out" for w in never or [] if hindi.contains(text, w)]


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
             angle: str | None = None, reports: list[dict] | None = None,
             hurt_ok: bool = False, attribution: bool = True) -> tuple[list[str], list[dict]]:
    """Problems with a draft, and the name pairs to double-check in the fact-check pass. A number or name the
    Wikipedia/Wikidata ground lacks passes only when at least two independent owners' reports state it. attribution:
    whether the attribution lint (gate.unattributed) counts; the draft loop leaves it out of the last draft."""
    problems, doubtful = [], []
    reports = reports or []
    two = gate.OWNERS_NEEDED
    beats = draft.get("beats") or []
    says = " ".join(b.get("say", "") for b in beats)
    words = len(says.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"the script has {words} words; it must have {WORDS_ASKED}")
    problems += [f"beat {i + 1} has {n} words; keep each beat to 8 to 14 words (make it two beats)"
                 for i, b in enumerate(beats) if (n := len(b.get("say", "").split())) > MAX_BEAT_WORDS]
    problems += [f"beat {i + 1} ends on filler ({m.group(0)}); end on a fact of the news" for i, b in enumerate(beats)
                 if (m := VAGUE.search(b.get("say", "")))]
    if hindi.devanagari_share(says) < 0.85:
        problems.append("write the narration in Hindi (Devanagari)")
    problems += casual(draft)
    problems += [f"beat {i + 1} says someone has not responded; leave that line out and give a fact of today's news "
                 "instead" for i, b in enumerate(beats) if NOBODY_REPLIED.search(b.get("say", ""))]
    if kind != "death":
        problems += [f"beat {i + 1} is biography ({m.group(0)}); keep to today's news" for i, b in enumerate(beats)
                     if (m := BIOGRAPHY.search(b.get("say", "")))]
    names = [p for p in draft.get("names") or [] if isinstance(p, dict)]
    if not beats or not subject_in(beats[0].get("say", ""), subject, names):
        problems.append(f"beat 1 must name {subject.get('hi') or subject['en']} in Hindi, and list it in names")
    elif subject.get("person") and not subject_in(
            " ".join(beats[0]["say"].split()[:HOOK_WORDS - 1 + max(1, len((subject.get("hi") or "").split()))]),
            subject, names):
        problems.append(f"beat 1 must open on {subject.get('hi') or subject['en']}: the name starting within its "
                        f"first {HOOK_WORDS} words, the place and time after it")
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
        newsroom = hindi.contains(ground_hi, hi) or len(gate.reported(hi, reports)) >= two
        if label and hindi.norm(label) != hindi.norm(hi) and not hindi.contains(text, label) and not newsroom:
            problems.append(f"write {en} as {label} (the Hindi name people know), not {hi}")
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
    problems += gate.decorum(text, "incident" if kind in ("incident", "protest") else kind, agreed_toll, hurt_ok)
    if attribution:
        problems += gate.unattributed(text, names, reports, ground_en + "\n" + ground_hi)
    own =(draft.get("title") or "").strip().strip('"')
    if len(own) > TITLE_MAX:  # the draft's own title is retitle's fallback
        problems.append(f"the title has {len(own)} characters; keep it to {TITLE_AIM[0]}-{TITLE_AIM[1]} (never over "
                        f"{TITLE_MAX})")
    if angle and not orbitwire.title_fits(draft.get("title", ""), angle):
        problems.append(f"the title must show this Short's angle ({orbitwire.ANGLES[angle]['label']})")
    return problems, doubtful


CASUAL = re.compile(r"आइए|आइये|दोस्तों|सोचिए|सोचिये|क्या आप|आपको बता दें|जानिए|जानिये|!")
# "रिपोर्टों में अन्य पक्षों की प्रतिक्रिया नहीं है" in a Sensex Short (2026-10-16) and "रिपोर्टों में हमलावरों की
# प्रतिक्रिया नहीं है" in a Tiger Shroff Short (2026-10-20): filler, and attackers are no side to hear from.
NOBODY_REPLIED = re.compile(r"(अन्य|दूसरे|दूसरा|किसी|विपक्षी) पक्ष\S*( की| का| से)? (कोई )?प्रतिक्रिया|"
                            r"रिपोर्ट\S* में .{0,40}प्रतिक्रिया (अभी )?(तक )?(नहीं|सामने नहीं)|"
                            r"(हमलावर|आरोपि|आरोपी|अभियुक्त|शूटर)\S* (की|का|से) (कोई )?प्रतिक्रिया")
# "टाइगर एक्टर जैकी श्रॉफ के बेटे हैं और उन्होंने 2014 में फिल्म हीरोपंती से करियर शुरू किया" (2026-10-20): a news
# Short spent a beat on who someone is instead of what happened.
BIOGRAPHY = re.compile(r"करियर (की )?(शुरू|शुरुआत)|से डेब्यू|डेब्यू किया|के बेटे हैं|की बेटी हैं|जाने-माने अभिनेता|"
                       r"मशहूर अभिनेता हैं|अपनी (फिल्मों|फ़िल्मों) के लिए (जाने|मशहूर)")
# "मामले की आगे की कानूनी कार्रवाई जारी है" closed two Tiger Shroff drafts (2026-10-21): it says nothing.
VAGUE = re.compile(r"आगे की (कानूनी )?(कार्रवाई|कार्यवाही) जारी|आगे की जांच जारी|कार्रवाई की जा रही है")


# The last beat tells the viewer what the news means for them or what happens next (2026-10-22, for YouTube's
# Partner Programme: every Short must add value, not just retell). A light, advisory check on its words.
NEXT_OR_IMPACT = re.compile(r"आगे|अगल|अब |अभी तक|सुनवाई|तारीख|तक |लागू|असर|लोगों|यात्रियों|ग्राहकों|छात्रों|"
                            r"उम्मीदवारों|किसानों|मरीजों|परिवार|मुआवज|हेल्पलाइन|बंद रहेग|जारी रहेग|साफ नहीं|पता नहीं|"
                            r"इंतज़ार|इंतजार|बाकी|फैसला|\S+(एगा|एगी|एंगे|ेगा|ेगी|ेंगे|ोगा|ोगी|ोंगे)(?=[\s।,.?]|$)")
# Advice, or advice put in an unnamed expert's mouth: never on a news channel, least of all on money, health or law.
# Reporting is not advice: "विशेषज्ञों की सलाह पर स्कूल बंद किए" says why something was done, and a quoted,
# attributed appeal ("मोदी ने कहा, "आप सब मतदान करें"") is the news; quotes are left out of the check (QUOTED).
ADVICE = re.compile(r"(विशेषज्ञ|एक्सपर्ट|जानकार)\S* (की|ने|का) (सलाह|सुझाव)(?! पर)|"
                    r"(विशेषज्ञ|एक्सपर्ट|जानकार)\S* सलाह दे|"
                    r"(निवेश|खरीदारी|खरीद) (करें|करना चाहिए)|पैसा लगाएं|(शेयर|सोना) (खरीदें|बेचें)|दवा (लें|न लें)|"
                    r"आपको .{0,30}चाहिए|(आप|आपको) .{0,20}(करें|बचें|लें)(?=[\s।,.]|$)")
QUOTED = re.compile(r'"[^"]*"|“[^”]*”|‘[^’]*’')
# ...but a quote is still advice when its speaker is an unnamed expert ("विशेषज्ञों ने कहा, "सोना खरीदें"").
EXPERT_SAYS = re.compile(r"(विशेषज्ञ|एक्सपर्ट|जानकार)\S* (ने|का) (कहा|कहना)")


def value_beat(draft: dict, kind: str) -> list[str]:
    """An advisory: the last beat should say what happens next or what the news means for people (not a death,
    whose last beat is the funeral or the tributes)."""
    beats = draft.get("beats") or []
    if kind == "death" or not beats or NEXT_OR_IMPACT.search(beats[-1].get("say", "")):
        return []
    return ["the last beat must say what happens next or what this means for people (आगे क्या / काम की बात), only "
            "as the sources state it"]


def advice(draft: dict) -> list[str]:
    """An advisory (never on the last draft, so it never costs a story): a beat that gives advice outside quotes."""
    def found(say: str):
        bare = QUOTED.sub(" ", say)
        return ADVICE.search(bare) or (EXPERT_SAYS.search(bare) and ADVICE.search(say))

    return [f"beat {i + 1} gives advice ({m.group(0)}); report what the sources say, attributed, and give no advice"
            for i, b in enumerate(draft.get("beats") or []) if (m := found(b.get("say", "")))]


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
    problems += gate.unattributed(title, names, reports or [], ground_en)
    if STATED_CAUSE.search(title) and not ATTRIBUTED.search(title) and "?" not in title:
        problems.append("it states a cause as fact: say who gives it (\"... के मुताबिक\", \"... बोले\") or leave the "
                        "cause out")
    if any(hindi.norm(title) == hindi.norm(e) for e in earlier or [] if e):
        problems.append("an earlier part already has this title")
    return problems


def opening(title: str, n: int = TITLE_CORE_WORDS) -> str:
    return " ".join(hindi.norm(re.sub(r"[^\w\u0900-\u097f]", "", w)) for w in title.split()[:n])


def recent_titles(limit: int = RECENT_TITLES) -> list[str]:
    """The channel's last published titles."""
    return [r["title"] for r in ledger.published()[-limit:] if r.get("title")]


def title_style(title: str, draft: dict, subject: dict, recent: list[str] | None = None,
                earlier: list[str] | None = None) -> list[str]:
    """Style problems of a title (see KICKER): more than TITLE_AIM's characters, a "Name:" label, a stock "वजह क्या है" tail, the searchable name
    later than its first words, or the same first words as another story's recent title."""
    title = title.strip().strip('"')
    names = [p for p in draft.get("names") or [] if isinstance(p, dict)]
    problems = []
    if len(title) > TITLE_AIM[1]:
        problems.append(f"{len(title)} characters: keep the title to {TITLE_AIM[0]}-{TITLE_AIM[1]}")
    if KICKER.match(title):
        problems.append("drop the \"Name:\" label: write one natural Hindi headline that starts with the name")
    if m := STOCK_TAIL.search(title):
        problems.append(f"a stock tail ({m.group(0).strip(' ,:')}): end on the concrete fact, or ask the one specific "
                        "question this Short answers")
    words = title.split()
    core = [subject.get("hi") or ""] + [p.get("hi", "") for p in names
                                        if p.get("en") and p["en"].lower() in subject["en"].lower()]
    span = TITLE_CORE_WORDS - 1 + max([1] + [len(c.split()) for c in core if c])
    head = " ".join(words[:span])
    if not (subject_in(head, subject, names) or any(c and hindi.contains(head, c) for c in core)
            or (not KICKER.match(title) and hindi.contains(head, subject["en"]))):
        problems.append(f"put {subject.get('hi') or subject['en']} within the first {TITLE_CORE_WORDS} words: it is "
                        "what viewers search for")
    mine = {hindi.norm(e) for e in earlier or [] if e}
    start = opening(title)
    if len(words) >= TITLE_CORE_WORDS and any(opening(r) == start for r in recent or [] if hindi.norm(r) not in mine):
        problems.append(f"another recent Short's title also opens \"{' '.join(words[:TITLE_CORE_WORDS])}\": open "
                        "differently")
    return problems


def retitle(pen: "Pen", draft: dict, subject: dict, ground_en: str, kind: str, agreed_toll: bool,
            reports: list[dict] | None = None, hints: list[str] | None = None,
            earlier: list[str] | None = None, recent: list[str] | None = None) -> tuple[str, dict]:
    """The best title for a draft that passed every check: the first of the headline editor's options with no
    problem and no style problem; in the last of two rounds the first with no problem; else the draft's own title.
    Also the record of what was tried. recent: the channel's last titles (default: the ledger's)."""
    recent = recent_titles() if recent is None else recent
    script = "\n".join(b.get("say", "") for b in draft.get("beats") or [])
    past = ("EARLIER TITLES (earlier parts of this story; this title must tell what is new):\n"
            + "\n".join(f"- {e}" for e in earlier) + "\n") if earlier else ""
    messages = [{"role": "system", "content": "You are the headline editor of a popular Hindi news website."},
                {"role": "user", "content": TITLE_BRIEF.format(
                    script=script, earlier=past, hints="\n".join(f"- {h}" for h in hints or []) or "- (none)",
                    recent="\n".join(f"- {t}" for t in recent[-RECENT_TITLES:]) or "- (none)")}]
    record = {"options": [], "own": draft.get("title", "")}
    rounds = 2
    for round_ in range(rounds):
        try:
            answer = pen.chat(messages, TITLE_SCHEMA, temperature=0.8, max_tokens=600)
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"[:200]
            break
        options = [str(t).strip().strip('"') for t in (answer.get("titles") or []) if str(t).strip()]
        tried = [(t, title_problems(t, draft, subject, ground_en, kind, agreed_toll, reports, earlier),
                  title_style(t, draft, subject, recent, earlier)) for t in options]
        record["options"] += [{"title": t, "problems": p, "style": st} for t, p, st in tried]
        good = next((t for t, p, st in tried if not p and not st), None)
        if good is None and round_ == rounds - 1:
            good = next((t for t, p, _ in tried if not p), None)  # style is advisory on the last round
        if good:
            record["chosen"] = good
            return good, record
        messages = messages + [{"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
                               {"role": "user", "content": "None of these can be used:\n" + "\n".join(
                                   f"- {t}: {'; '.join(p + st)}" for t, p, st in tried) + "\nWrite 5 new titles."}]
    own = draft.get("title", "")
    record["chosen"] = own
    record["own_problems"] = title_problems(own, draft, subject, ground_en, kind, agreed_toll, reports, earlier)
    if len(own.strip().strip('"')) > TITLE_MAX:  # validate refuses such a draft: the fallback never goes out over it
        raise ValueError(f"gate: no title of at most {TITLE_MAX} characters ({own[:80]})")
    return own, record


def write(kind: str, subject: dict, pronoun: str, facts: list[str], source_en: str, source_hi: str,
          photos: list[dict], hi_names: dict[str, str], banned_names: list[str] | None = None,
          agreed_toll: bool = False, log_path: Path | None = None, headlines: list[str] | None = None,
          angle: str | None = None, pen: Pen | None = None,
          today_ok: bool = True, reports: list[dict] | None = None, title_hints: list[str] | None = None,
          earlier: list[str] | None = None, start: dict | None = None, focus: str | None = None,
          names_ok: list[str] | None = None, never: list[str] | None = None,
          status: str | None = None, hurt_ok: bool = False) -> tuple[dict, list[dict], list[str]]:
    """The script as {title, beats: [{say, photo, caption}], names}, the log of rejected drafts (also kept at
    log_path), and the models that answered. kind is "death", "incident" or "protest". reports: trusted outlets'
    articles ({outlet, owner, at, title, excerpt, text}), see the module docstring. title_hints: the story's Hindi
    lead headlines (the title's style); earlier: the titles of this story's earlier parts today (a follow-up part).
    start: a draft to check first (a remake's reviewed script); it faces every check a written draft does. focus: one
    angle of a case (plan.cases) this Short is about; names_ok: then the only people, places and bodies it may name;
    never: words (an accused's or a gang's name) the script may not contain at all; status: where the case stands
    now (an angle's reports may be older than the arrests)."""
    obj = {"He": "him", "She": "her"}.get(pronoun, "them")
    hi_names = everyday_names(hi_names)
    if subject.get("hi") and hard_words(subject["hi"]):
        subject = subject | {"hi": None}
    brief = {"death": DEATH_BRIEF, "protest": PROTEST_BRIEF, "explainer": EXPLAINER_BRIEF}.get(kind, INCIDENT_BRIEF)
    brief = brief.format(name=subject["en"], pronoun=pronoun.lower(), object=obj)
    if earlier:
        brief += ("\n\nFOLLOW-UP: this channel already published " + str(len(earlier)) + " Short(s) on this story, "
                  "titled: " + "; ".join(f'"{e}"' for e in earlier) + ". The REPORTING below is newer. Lead "
                  "with what is new in it (a new development, decision, reaction or figure), give at most one short "
                  "line of what was already told, and never repeat the earlier Short beat by beat.")
    if angle:
        brief += (f"\n\nANGLE ({orbitwire.ANGLES[angle]['label']}): the channel's English sister channel already told "
                  f"this story its usual way, so this Hindi Short must be different. {orbitwire.ANGLES[angle]['brief']} "
                  "Use a different hook from a plain retelling.")
    if focus:
        brief += ("\n\nTHIS SHORT'S ANGLE: " + focus + " Open with this angle and keep every beat on it; the case "
                  "itself gets one short line of context at most. Every fact comes from the REPORTING below. Name the "
                  "exact places (the station, the hospital, the police station, the street): the video shows each "
                  "place it names.")
    if status:
        brief += ("\n\nWHERE THE CASE STANDS NOW (some REPORTING was written before this): " + status + " Never say "
                  "anything that contradicts it, and where reports disagree on a figure, give it as who says it.")
    if names_ok:
        brief += ("\n\nName only these people, places and bodies (list each in names with its English name exactly "
                  "as written here): " + ", ".join(names_ok) + ". Never "
                  "name an accused, a suspect or a shooter: say how many, where they are from and what police say "
                  "about them. A gang on this list is named only as police or the REPORTING put it (\"पुलिस ... गैंग "
                  "से जुड़े होने की जांच कर रही है\", \"सोशल मीडिया पर ... गैंग के नाम से दावा, पुलिस ने पुष्टि नहीं "
                  "की\"), never as a fact of its own.")
    if not today_ok:
        brief += ("\n\nThis did not happen today: never write आज or अभी about it (आज भी for a lasting legacy, and "
                  "अभी तक or आज तक for what the REPORTING says is still unknown, are fine). Say when it happened "
                  "only as the FACTS or the REPORTING state it (their date, or their day such as रविवार रात); never "
                  "work a date out yourself, and leave the time out when neither gives one.")
    name_hi = (f'"{subject["hi"]}"' if subject.get("hi")
               else f"the Hindi (Devanagari) name you give {subject['en']} in names, not the English title")
    messages = _messages(brief, facts, source_en, source_hi, photos, name_hi, hi_names, headlines, reports)
    # A Commons description is anyone's caption, not a source: the script's facts come from the sources alone.
    ground_en = source_en + "\n" + "\n".join(facts)
    ground_hi = source_hi + "\n" + "\n".join(facts) + "\n" + "\n".join(hi_names.values())
    log = []
    looked: dict[str, str | None] = {}
    own = pen is None
    pen = pen or Pen()
    try:
        for attempt in range(DRAFTS):
            ignored = []
            draft = json.loads(json.dumps(start)) if start and attempt == 0 else \
                pen.chat(messages, SCHEMA, temperature=0.75 if attempt == 0 else 0.6)
            problems, doubtful = validate(draft, photos, subject, ground_en, ground_hi,
                                          spellings(draft, hi_names, looked), banned_names or [],
                                          kind, agreed_toll, angle, reports, hurt_ok,
                                          # The lint misses spellings and generic "police said"; on the last draft
                                          # it never costs the story (2026-10-22 review).
                                          attribution=attempt < DRAFTS - 1)
            if not today_ok:
                problems += not_today(script_text(draft))
            if names_ok:
                problems += off_case(draft, names_ok, never)
            if attempt < DRAFTS - 1:
                problems += (monotone(draft) + bookish(draft) + value_beat(draft, kind) + advice(draft)
                             + misread(draft, spellings(draft, hi_names, looked), ground_hi, reports))
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


MISREAD_NAMES = 8  # names a draft checks against what their Hindi spelling already means


def misread(draft: dict, hi_names: dict[str, str], ground_hi: str, reports: list[dict] | None = None) -> list[str]:
    """Hindi spellings that viewers read as another, better-known name: Parrys (Chennai) written पैरिस is Paris to
    every Hindi reader (2026-10-19). Only names with no Wikidata label and no Hindi source spelling are checked; a
    word is misread when a Wikidata item's Hindi label writes it and its English sounds more like that item than
    like the story's name."""
    labelled = {en.lower() for en in hi_names}
    pairs = [(p["hi"].strip(), p["en"].strip()) for p in draft.get("names") or []
             if isinstance(p, dict) and isinstance(p.get("hi"), str) and isinstance(p.get("en"), str)
             and p["hi"].strip() and p["en"].strip() and p["en"].strip().lower() not in labelled
             and not hindi.contains(ground_hi, p["hi"]) and len(gate.reported(p["hi"], reports or [])) < gate.OWNERS_NEEDED]
    pairs = pairs[:MISREAD_NAMES]
    words = [w for hi, _ in pairs for w in hi.split() if len(w) > 2]
    if not words:
        return []
    try:
        readings = wiki.hindi_readings(words)
    except Exception:
        return []
    problems = []
    for hi, en in pairs:
        own = [re.sub(r"[^a-z]", "", w.lower()) for w in en.split()]
        for word in hi.split():
            other = [w for label in readings.get(word, []) for w in re.findall(r"[A-Za-z][A-Za-z'’]+", label)
                     if re.sub(r"[^a-z]", "", w.lower()) not in own]
            best = max(other, key=lambda w: hindi.likeness(word, w), default=None)
            if best and hindi.likeness(word, best) >= 0.6 and \
                    hindi.likeness(word, best) > max(hindi.likeness(word, w) for w in en.split()):
                problems.append(f"{hi} reads as {best} in Hindi, not {en}: spell {en} by its own sound, or say what "
                                f"it is (इलाका, शहर) as the Hindi sources would")
                break
    return problems


def spellings(draft: dict, hi_names: dict[str, str], looked: dict[str, str | None]) -> dict[str, str]:
    """hi_names plus Wikidata's everyday Hindi spelling of each other name the draft lists; looked caches lookups."""
    known = {en.lower() for en in hi_names}
    new = list(dict.fromkeys(p["en"].strip() for p in draft.get("names") or []
                             if isinstance(p, dict) and isinstance(p.get("en"), str) and p["en"].strip()
                             and p["en"].strip().lower() not in known and p["en"].strip() not in looked))
    if new:
        try:
            found = wiki.hindi_spellings(new)
        except Exception:
            found = {}
        looked.update({n: found.get(n) for n in new})
    return hi_names | everyday_names({n: hi for n, hi in looked.items() if hi})


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
                context_qids: list[str] | None = None, recent: set[str] | None = None,
                words: list[str] | None = None) -> list[dict]:
    """Downloaded photos as dicts with a "focus" box: for a person, only photos in which their face is matched.
    files: Commons files an editor chose instead of searching; exclude: files that may not be used; places: see
    media.find; context_qids: places and things the story links to, whose photos (with no featured face) fill in
    when the story has fewer than MIN_PHOTOS of its own: Commons first, then Openverse. A person needs at least one
    photo of their own face. recent: files the channel's last Shorts showed, taken last; words: the story's own
    words, whose photos of the person come first (media.find)."""
    kept = _own_photos(title, ent, folder, person, extra_qids, files, exclude, places,
                       recent=recent, words=words) if title else []
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


def caption_side(description: str | None, title: str) -> str | None:
    """"left" or "right" when a photo's caption places the person ("Tiger Shroff (left) and ..."), else None."""
    name = re.escape(stories.plain_title(title))
    m = re.search(rf"{name}\s*\((?:on the |at )?(left|right)\)", description or "", re.I)
    return m.group(1).lower() if m else None


def story_words(headlines: list[str], name: str, most: int = 2) -> list[str]:
    """The capitalised words at least two of the story's headlines share, besides the person's name and the big
    names every story carries (Delhi, BJP): "Dussehra" for "PM Modi attends Dussehra celebrations in Delhi"."""
    own = {w.lower() for w in re.findall(r"[A-Za-z]+", name)} | {"pm", "cm", "shri"}
    seen = Counter()
    for h in dict.fromkeys(headlines):
        seen.update({w for w in re.findall(r"\b[A-Z][a-z]{3,}\b", h)
                     if w.lower() not in own and w.lower() not in explain.INSTITUTIONS
                     and w.lower() not in outlets.GENERIC and w.lower() not in media.GENERIC})
    return [w for w, n in seen.most_common() if n >= 2][:most]


def recent_photos() -> set[str]:
    try:
        from . import ledger

        return ledger.recent_photos()
    except Exception:
        return set()


def _own_photos(title: str, ent: dict, folder: Path, person: bool, extra_qids: list[str] | None,
                files: list[str] | None, exclude: set[str] | None, places: bool, limit: int = 10,
                recent: set[str] | None = None, words: list[str] | None = None) -> list[dict]:
    import cv2

    if files:
        found = media.picks([f for f in files if f not in (exclude or set())])
    else:
        # A person is always searched for: Tiger Shroff's Wikidata image and category gave one photo (of someone
        # else), a Commons search for his name gave nine of him (2026-10-20).
        found = media.find(title, ent, limit=limit + (len(recent or ()) and 6), extra_qids=extra_qids,
                           exclude=exclude, search=bool(exclude) or person or bool(recent), places=places,
                           words=words if person else None)
        found = sorted(found, key=lambda f: (f.origin != "story", f.file in (recent or ())))
    if person:
        found = [f for f in found if not media.NOT_PERSON.search(f"{f.file} {f.description}")]
    found = media.download(found, folder)
    rows = media.as_dicts(found)
    images = [cv2.imread(r["path"]) for r in rows]
    detected = [faces.detect(img) if img is not None else [] for img in images]
    picks = faces.subject(detected, [caption_side(r.get("description"), title) for r in rows]) if person \
        else [None] * len(rows)
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
    # Photos of the person at the story's own occasion go first; then strangers beside the person would be shown as
    # part of today's story, so their own portraits come before group photos; photos the channel's last Shorts
    # showed go last.
    return sorted(kept, key=lambda r: (r.get("origin") != "story", r["others"] > 0,
                                       r.get("file") in (recent or ())))[:8]


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
                         r"identified as|named as|arrest\w*|detained|charged|held for|gangs?|gangsters?)\b|आरोपी|"
                         r"संदिग्ध|हमलावर|गिरफ्तार|गिरफ़्तार|हिरासत|गैंग|गिरोह", re.I)
# Casualty sentences never reach the writer from reports: an agreed toll comes as a confirmed fact, and any other
# count (hedged, earlier, injured) must not be said beside it.
REPORT_CASUALTY = gate.CASUALTY + ["dead", "died", "death", "deaths", "lives", "bodies", "body", "perish*",
                                   "नहीं रहे", "शव", "लाश*"]


def _reporting(cand: dict, title: str, hi: str | None = None, person: bool = False,
               since: datetime | None = None, search: bool = True) -> list[dict]:
    """2-4 trusted outlets' articles about the story, each from a different owner, with their text (outlets.reporting):
    the reports matched to it at discovery, and (search) any recent outlet item that names it. [] when fewer than
    two owners' articles can be read."""
    try:
        return outlets.reporting(_report_rows(cand, title, hi, person, since, search))
    except Exception:
        return []


def _report_rows(cand: dict, title: str, hi: str | None = None, person: bool = False,
                 since: datetime | None = None, search: bool = True) -> list[dict]:
    """The outlet items about the story (_reporting), not yet read."""
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
    return [r for r in found.values() if not since or datetime.fromisoformat(r["at"]) >= since]


DEATH_READS = 6  # best-ranked other outlet items read a run for a death the story's reports do not state


def death_reports(cand: dict, reports: list[dict], name: str, name_hi: str | None, since: datetime) -> list[dict]:
    """The news reports that state the death (gate.states_death), each as an outlet item plus the name it gives and
    the sentence that says it: the story's reporting (read before clean_reports takes death sentences out), else the
    first of DEATH_READS other outlet items about the person whose article says it. One is enough: the writer's facts
    still need gate.OWNERS_NEEDED owners. An article that calls the death a hoax or denies it (gate.denies_death)
    never is."""
    names = [name] + (explain.hindi_names_of(name_hi) or ([name_hi] if name_hi else []))

    def confirmed(r: dict, body: str | None) -> dict | None:
        text = f"{r.get('title', '')}. {body}"
        says = gate.states_death(text, names) if body else None
        if not says or gate.denies_death(text, names):
            return None
        return outlets.compact(r) | {"name": next(n for n in names if hindi.contains(says, n)), "says": says}

    found = [row for r in reports if (row := confirmed(r, r.get("text")))]
    if found:
        return found
    seen = {r["url"] for r in reports}
    try:
        rows = _report_rows(cand, name, name_hi, person=True, since=since)
    except Exception:
        rows = []
    for r in sorted((r for r in rows if r["url"] not in seen), key=outlets._rank)[:DEATH_READS]:
        if row := confirmed(r, outlets.text(r["url"])):
            return [row]
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


def case_hurt(hurt: dict | None, reports: list[dict]) -> dict | None:
    """A case file's agreed injured, only when this Short's own reports include OWNERS_NEEDED of its owners: the
    publish gate counts them there (the family angle read one, as Indian Express answered 403, and was refused)."""
    if hurt and len(set(hurt["owners"]) & {r.get("owner") for r in reports}) >= gate.OWNERS_NEEDED:
        return hurt
    return None


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
    name_hi = wiki.common_hindi(ent)
    raw = _reporting(cand, name, name_hi, person=True, since=_since(died))
    confirming = death_reports(cand, raw, name, name_hi, _since(died))
    if not confirming:
        raise ValueError(f"gate: no news report states the death of {name} (Wikidata and Wikipedia alone are not "
                         "enough)")
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
    reports = clean_reports(raw, [name] + ([name_hi] if name_hi else []), perpetrators=False)
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
    sources = list(dict.fromkeys(sources + [r["url"] for r in confirming]))
    short = _short(sid, "death", name, name_hi, draft, log, used, facts, facts_text, source + "\n" + source_hi, photos,
                   sources, died.isoformat(), loss=False, mood="tribute", region=cand.get("region", "world"),
                   person=True, tags=[name, name_hi, job, job_hi, "श्रद्धांजलि", "tribute", "hindi news", "हिंदी समाचार"],
                   summary=f"{name_hi} ({born.year}–{died.year}) को श्रद्धांजलि: उनकी कहानी, Wikipedia और Wikidata के "
                           f"तथ्यों से।",
                   cat="death", ov=ov, reports=reports)
    short.scene["death_reports"] = confirming
    return short


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
    name_hi = wiki.common_hindi(ent)
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


def respelled(draft: dict, name: str, name_hi: str) -> dict:
    """The draft as viewers will read it: Latin digits, one spelling per famous name (hindi.SPELLINGS) and the
    subject in the spelling the description and hashtags use (name_hi), wherever the writer spelled it otherwise.
    The writer's checks have passed by now; this only evens out what they allow."""
    own = (_pair_for(draft, name) or "").strip()
    # Only a same-length variant (नरेन्द्र मोदी -> नरेंद्र मोदी). A surname-only ट्रंप mapped to डोनाल्ड ट्रंप would
    # double every full name already written ("डोनाल्ड डोनाल्ड ट्रंप") and glue the subject's first name onto anyone
    # who shares the surname ("सोनिया राहुल गांधी").
    same_length = own and name_hi and len(own.split()) == len(name_hi.split())
    subject = {own: name_hi} if same_length and own != name_hi else {}

    def fix(text):
        return hindi.respell(text, subject) if isinstance(text, str) else text

    out = dict(draft, title=fix(draft.get("title", "")))
    out["beats"] = [{k: fix(v) if k in ("say", "caption", "label") else v for k, v in b.items()}
                    for b in draft.get("beats") or []]
    out["names"] = [dict(p, hi=fix(p.get("hi"))) if isinstance(p, dict) else p for p in draft.get("names") or []]
    return out


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


SECTION_LABELS = {"मुख्य खबर", "ताजा जानकारी", "ताज़ा जानकारी", "विवरण", "अन्य पक्ष", "पृष्ठभूमि", "जानकारी"}


def card_label(label) -> str:
    """The writer's label, unless it is a bare section name that tells the viewer nothing."""
    label = label.strip() if isinstance(label, str) else ""
    return "" if label in SECTION_LABELS else label


FRESH_PICTURES = 2


def stale_pictures(photos: list[dict], views: list[list[int]], recent: set[str]) -> str | None:
    """Why a Short would mostly repeat the channel's last Shorts: fewer than half (and fewer than FRESH_PICTURES) of
    the photos on screen are new to the last ledger.RECENT_PHOTOS_H hours of Shorts (maps aside). The tenth Tiger
    Shroff Short (2026-10-21) showed photos nine earlier ones had; Commons has about nine of him."""
    from . import ledger

    shown = {photos[i]["file"] for v in views for i in v
             if i < len(photos) and photos[i].get("file") and not visuals.is_map(photos[i])}
    fresh, want = shown - recent, max(FRESH_PICTURES, (len(shown) + 1) // 2)
    if recent and len(fresh) < want:
        return (f"gate: only {len(fresh)} of {len(shown)} photos on screen are new to the last "
                f"{ledger.RECENT_PHOTOS_H} hours of Shorts (want {want})")
    return None


def _short(sid, kind, name, name_hi, draft, log, used, facts, facts_text, source, photos, sources, event_time, loss,
           mood, tags, summary, cat="", region="world", ov=None, reports=None, credit=CREDIT, person=False) -> Short:
    reports = reports or []
    name_hi = hindi.respell(plain_name(name_hi, draft, name))
    draft = respelled(draft, name, name_hi)
    hashtags = hashtags_for(name, name_hi, cat, region, script_text(draft))
    tags = tags + search_tags(name)
    recent = recent_photos()
    photos, views, cast = visuals.direct(draft, photos, name if person else "", region == "india",
                                         WORK / sid / "photos" / "cast",
                                         set((ov or {}).get("excluded_photos") or []), tribute=kind == "death",
                                         recent=recent)
    if kind != "death" and (stale := stale_pictures(photos, views, recent)):
        raise ValueError(stale)
    beats = [Beat(b["say"].strip(), "photo:" + "/".join(str(i) for i in (v or [b["photo"]])),
                  visuals.card_over({"big": b["caption"].strip(), "small": card_label(b.get("label"))},
                                    v or [b["photo"]], cast))
             for b, v in zip(draft["beats"], views)]
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
    if any(visuals.is_map(p) for p in photos):
        credit += "; नक्शे: © OpenStreetMap contributors (CC BY-SA 2.0)"
    if reports:
        credit += "; रिपोर्टिंग: " + ", ".join(outlets.names(reports))
    credits = [credit] + sorted({p["credit"] + " " + p["page"] for p in photos})
    scene = {"template": "full", "mood": mood, "voice": "sulafat", "region": region, "photos": photos,
             "name_hi": name_hi, "subject_person": bool(person), "names": draft.get("names", []), "cast": cast,
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


def story_person(name: str) -> tuple[str | None, str | None, dict]:
    """(QID, Wikipedia title, Wikidata item) of the person an nw- story names ("Attack on Tiger Shroff"): Wikipedia's
    first search hit, when its plain title is the name and the item is a human."""
    try:
        title = wiki.search(name)
    except Exception:
        return None, None, {}
    if not title or stories.plain_title(title).lower() != name.lower():
        return None, None, {}
    qid = (wiki.page_info([title]).get(title) or {}).get("qid")
    ent = wiki.entities([qid]).get(qid) if qid else None
    if not ent or wiki.HUMAN not in {c["value"] for c in wiki.claims(ent, "P31")}:
        return None, None, {}
    return qid, title, ent


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
    if not place:
        # An attack on a famous person is told about the person, over their own face-matched portraits.
        pid, title, person = story_person(name)
        if person:
            return build_explainer(cand | {"qid": pid, "title": title, "person": True, "phrase": name,
                                           "story": cand["title"], "category_hi": "घटना",
                                           "story_keys": sorted(outlets.headline_keys(cand["title"])[0])})
    name_hi = wiki.common_hindi(place) if place else None
    context = list(dict.fromkeys(([qid] if qid else []) + incident_context(place, [])))[:4] if place else []
    ov, exclude = _shared(cand, "", {}, None, context)
    photos = visuals.fresh_first(
        fill_photos(context, work / "photos", exclude,
                    scene=(name, outlets.scene_words(cand.get("headlines") or [cand["title"]], name))),
        recent_photos())[:8] if context else []
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
                             reports=reports, title_hints=hindi_hints(cand), earlier=cand.get("earlier"),
                             start=cand.get("draft"))
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
    name_hi = wiki.common_hindi(ent)
    phrase = cand.get("phrase") or name
    work = WORK / sid
    mine = [r for r in cand.get("reports") or []
            if cand.get("case") or explain.about_story(r, phrase, cand.get("story_keys") or [])]
    reports = _reporting(cand | {"reports": mine}, phrase, hi=name_hi, person=person, search=False)
    if len(outlets.owners(reports)) < gate.OWNERS_NEEDED:
        raise ValueError(f"gate: fewer than {gate.OWNERS_NEEDED} independent outlets' articles about {name} could "
                         "be read")
    named = sorted(set(gate.reported(phrase, reports)) | set(gate.reported(name, reports)))
    if len(named) < gate.OWNERS_NEEDED:
        raise ValueError(f"gate: fewer than {gate.OWNERS_NEEDED} independent outlets' articles name {name}")
    context = person_context(ent) if person else incident_context(ent, [])
    ov, exclude = _shared(cand, title, ent, None, context)
    words = story_words([cand.get("story") or ""] + list(cand.get("headlines") or []), name) if person else None
    photos = pick_photos(title, ent, work / "photos", person=person, exclude=exclude, places=not person,
                         context_qids=None if person else context, recent=recent_photos(), words=words)
    setting = not person and bool(wiki.claims(ent, "P1082"))
    if setting:
        # A city's or state's article photos are its sights (a temple, a market, a rickshaw for the Modi Dussehra
        # Short, 2026-10-21): never the news. One of them sets the scene; the people and places the script names
        # fill the beats, and the gate still wants MIN_VISUALS different pictures.
        photos = photos[:SETTING_PHOTOS]
    lead = person and (cand.get("top_score") or 0) >= LEAD_SCORE
    need = 1 if lead or setting else REPORT_PHOTOS
    if len(photos) < need:
        raise ValueError(f"gate: only {len(photos)} usable photos of {name} on Wikimedia Commons (want {need})"
                         + (" not used by Orbitwire" if ov else ""))
    story = cand.get("story") or (cand.get("headlines") or [title])[0]
    words = ([phrase, name] + ([name_hi] if name_hi else []) + sorted(outlets.headline_keys(story)[0])
             + list(cand.get("case_words") or []))
    # A case's arrests angle keeps what police say about the accused; off_case keeps their names out.
    reports = clean_reports(reports, words, perpetrators=not (cand.get("arrests") and cand.get("names_ok")))
    source = _strip(wiki.article_text(title, limit=EXPLAIN_SOURCE, per_section=900), SUICIDE_WORDS)
    source_hi, hi_title = _hindi_source(ent, limit=2500)
    source_hi = _strip(source_hi, SUICIDE_WORDS)
    # A headline is context, never a source (one outlet's words): it goes to the writer only as a lead headline.
    facts_text = [f"Centre of the story: {name}" + (f" ({name_hi})" if name_hi else "") + ".",
                  "What happened, and why, may come only from the REPORTING; the Wikipedia SOURCE is background on "
                  f"{name} and is never today's news."]
    hurt = case_hurt(cand.get("case_hurt"), reports)
    if hurt:
        facts_text.append(f"Injured ({', '.join(hurt['owners'])} agree): {hurt['count']}. {hurt['en']}")
    she, _ = stories._pronouns(ent) if person else ("It", None)
    subject = {"en": name, "hi": name_hi, "person": person}
    when = date.fromisoformat(cand["date"])
    draft, log, used = write("explainer", subject, she, facts_text, source, source_hi, photos, wiki.hindi_names(ent),
                             log_path=work / "writer_log.json",
                             headlines=list(dict.fromkeys([story] + (cand.get("headlines") or [])))[:6],
                             angle=ov["angle"] if ov else None, today_ok=when == _today_ist(), reports=reports,
                             title_hints=hindi_hints(cand), earlier=cand.get("earlier"), start=cand.get("draft"),
                             focus=cand.get("focus"), names_ok=cand.get("names_ok"), never=cand.get("never"),
                             status=cand.get("case_status"), hurt_ok=bool(hurt))
    name_hi = name_hi or _pair_for(draft, name) or name
    page = wiki.url(title)
    facts = [Fact("name", name, page, stories.numbers_in(name), "Wikipedia article title; named in the reports of "
                  + ", ".join(named), owners=named)]
    if hurt:
        facts.append(Fact("injured", str(hurt["count"]), hurt["url"], [str(hurt["count"])], hurt["en"],
                          owners=hurt["owners"]))
    sources = [page, f"https://www.wikidata.org/wiki/{qid}"] + ([wiki.url(hi_title, "hi")] if hi_title and source_hi
                                                                 else [])
    label = cand.get("category_hi") or cat
    short = _short(sid, "explainer", name, name_hi, draft, log, used, facts, facts_text, source + "\n" + source_hi,
                   photos, sources, when.isoformat(), loss=False, mood="news", region=cand.get("region", "india"),
                   tags=[name, name_hi, label, cat, "मतलबनामा", "हिंदी समाचार", "hindi news", "india news"],
                   summary=f"{name_hi}: क्या हुआ और क्यों, {', '.join(outlets.names(reports))} की रिपोर्टों और "
                           "Wikipedia से।",
                   cat=cat, ov=ov, reports=reports, credit=EXPLAIN_CREDIT, person=person)
    short.scene.update(qid=qid, category=cat, category_hi=label, headlines=cand.get("headlines") or [], story=story,
                       min_photos=need, min_visuals=visuals.MIN_VISUALS - lead)
    return short


def build(cand: dict) -> Short:
    if (cand.get("id") or "").startswith("kh-"):
        return build_explainer(cand)
    if (cand.get("id") or "").startswith("nw-"):
        return build_report(cand)
    return build_death(cand) if cand["kind"] == "death" else build_incident(cand)
