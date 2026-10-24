"""Hindi text the gates can compare: Devanagari digits, Indian number words (हज़ार, लाख, करोड़), name spellings that
differ only by a nukta or a chandrabindu, and Hindi dates.

A number in a script is checked by its value, so "15 लाख" must match 1,500,000 (or "1.5 million") in a source; the
bare "15" is not enough. Plain number words ("दो दिन बाद") are left alone, as Orbitwire leaves "two" alone.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import date

DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर",
          "दिसंबर")
SCALES = {
    "हज़ार": 1e3, "हजार": 1e3, "लाख": 1e5, "करोड़": 1e7, "करोड": 1e7, "अरब": 1e9, "खरब": 1e11,
    "मिलियन": 1e6, "बिलियन": 1e9, "ट्रिलियन": 1e12,
    "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7,
    "crores": 1e7, "mn": 1e6, "bn": 1e9,
}
WORDS = {"एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9,
         "दस": 10, "बीस": 20, "पचास": 50, "सौ": 100, "डेढ़": 1.5, "डेढ": 1.5, "ढाई": 2.5}
_END = r"(?=$|[\s.,;:!?()\"'’“”\-–—।|/])"
_SCALE = "|".join(sorted(map(re.escape, SCALES), key=len, reverse=True))
_WORD = "|".join(sorted(map(re.escape, WORDS), key=len, reverse=True))
_NUM = r"\d+(?:,\d{2,3})*(?:\.\d+)?"
# "साढ़े 3 लाख", "1.5 करोड़", "दो लाख", "15,00,000", "9:30", "6.3"
TOKEN = re.compile(
    rf"(?<![\w.])(?:(?P<half>साढ़े|साढे)\s+)?(?:(?P<num>{_NUM})(?::(?P<min>\d{{2}}))?|(?P<word>{_WORD}){_END})"
    rf"(?:\s*(?P<scale>{_SCALE}){_END})?", re.I)
NUKTA, CHANDRABINDU, ANUSVARA = "\u093c", "\u0901", "\u0902"


def ascii_digits(text: str) -> str:
    return (text or "").translate(DIGITS)


# One spelling per famous name in what viewers read: the channel wrote एलोन मस्क (bbx5XceX0sI) and एलन मस्क
# (QT1s3ANaodI) a day apart. Each entry is a whole word, mapped to Wikidata's Hindi label (एलन मस्क, व्लादिमीर पुतिन)
# or, where Hindi newsrooms all write another one, theirs (ट्रंप in Aaj Tak, ABP and NDTV India; the channel's own
# titles say ट्रंप).
SPELLINGS = {"एलोन": "एलन", "ट्रम्प": "ट्रंप", "डॉनल्ड": "डोनाल्ड", "डोनल्ड": "डोनाल्ड", "पुतीन": "पुतिन",
             "नरेन्द्र": "नरेंद्र"}
_WORD_EDGE = r"(?<![\w\u0900-\u097F])({})(?![\w\u0900-\u097F])"


def respell(text: str, spellings: dict[str, str] | None = None) -> str:
    """text with Latin digits for Devanagari ones (पोप लियो १४, T7EVpcOu8ME, next to "14" in other titles) and each
    whole word of SPELLINGS (and of spellings, e.g. the subject's Wikidata label) in its one spelling."""
    text = ascii_digits(text)
    table = {unicodedata.normalize("NFC", k): v for k, v in (SPELLINGS | (spellings or {})).items() if k and k != v}
    if not table:
        return text
    pattern = re.compile(_WORD_EDGE.format("|".join(sorted(map(re.escape, table), key=len, reverse=True))))
    return pattern.sub(lambda m: table[m.group(1)], unicodedata.normalize("NFC", text))


def _canon(value: float) -> str:
    return str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:.6f}".rstrip("0").rstrip(".")


def numbers(text: str) -> list[tuple[str, bool]]:
    """[(canonical value, scaled)] for every number in text: "15 लाख" -> ("1500000", True), "2026" -> ("2026", False).

    Spelled numbers count only before a scale word ("दो लाख"), and "3D" is a format, not a claim.
    """
    text = re.sub(r"\b3D\b", "", ascii_digits(text))
    out = []
    for m in TOKEN.finditer(text):
        if m.group("word") and not m.group("scale"):
            continue
        if m.group("min"):
            out.append((f"{int(m.group('num'))}:{m.group('min')}", False))
            continue
        value = float(m.group("num").replace(",", "")) if m.group("num") else float(WORDS[m.group("word")])
        if m.group("half"):
            value += 0.5
        scale = m.group("scale")
        if scale:
            value *= SCALES[scale.lower()] if scale.lower() in SCALES else SCALES[scale]
        out.append((_canon(value), bool(scale)))
    return out


_UNITS = "one two three four five six seven eight nine".split()
_TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
ENGLISH = {w: i + 1 for i, w in enumerate(_UNITS)} | {w: i + 10 for i, w in enumerate(_TEENS)}
ENGLISH_WORD = re.compile(rf"\b(?:(?P<tens>{'|'.join(_TENS)})(?:[\s-](?P<unit>{'|'.join(_UNITS)}))?"
                          rf"|(?P<small>{'|'.join(_TEENS + _UNITS)}))\b", re.I)


def english_numbers(text: str) -> set[str]:
    """Numbers an English source spells out below 100 ("over thirty-six languages" -> 36)."""
    found = set()
    for m in ENGLISH_WORD.finditer(text or ""):
        if m.group("tens"):
            found.add(str((_TENS.index(m.group("tens").lower()) + 2) * 10
                          + (ENGLISH[m.group("unit").lower()] if m.group("unit") else 0)))
        else:
            found.add(str(ENGLISH[m.group("small").lower()]))
    return found


def values(text: str) -> set[str]:
    """Every value a source states, scaled ("1.5 million" -> 1500000), as written ("1.5") and spelled out in English
    ("thirty-six")."""
    text = ascii_digits(text)
    found = {v for v, _ in numbers(text)} | english_numbers(text)
    found |= {n.replace(",", "") for n in re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", text)}
    return {_canon(float(v)) if ":" not in v else v for v in found}


def unsupported_numbers(text: str, source_values: set[str]) -> list[str]:
    """Numbers in text whose value no source states. A scaled amount may round its source by up to 1%."""
    floats = [float(s) for s in source_values if ":" not in s]
    bad = []
    for value, scaled in numbers(text):
        if value in source_values:
            continue
        if scaled and ":" not in value:
            v = float(value)
            if any(s >= 1000 and abs(v - s) / s <= 0.01 for s in floats):
                continue
        bad.append(value)
    return sorted(set(bad))


def norm(text: str) -> str:
    """For comparing spellings: NFC, no nukta, chandrabindu as anusvara, a half nasal before a consonant as anusvara
    (मुम्बई = मुंबई), no joiners, Latin in lower case."""
    text = unicodedata.normalize("NFC", text or "")
    text = unicodedata.normalize("NFD", text).replace(NUKTA, "")
    text = unicodedata.normalize("NFC", text).replace(CHANDRABINDU, ANUSVARA)
    text = re.sub("[\u200c\u200d]", "", text)
    text = re.sub("[\u0919\u091e\u0923\u0928\u092e]\u094d(?=[\u0915-\u0939])", ANUSVARA, text)
    return re.sub(r"\s+", " ", text).strip().lower()


def contains(haystack: str, needle: str) -> bool:
    """needle appears in haystack as whole words (Devanagari-aware), spelling differences aside."""
    h, n = norm(haystack), norm(needle)
    if not n:
        return False
    for m in re.finditer(re.escape(n), h):
        before = h[m.start() - 1] if m.start() else " "
        after = h[m.end()] if m.end() < len(h) else " "
        if not _letter(before) and not _letter(after):
            return True
    return False


def find(haystack: str, needle: str) -> int:
    """Where in haystack (its own characters) needle first starts as whole words, spelling differences aside, or
    -1: a cut lands on the word that names its picture, and norm() changes lengths (मुम्बई is मुंबई)."""
    n = norm(needle)
    if not n:
        return -1
    h = haystack or ""
    starts = [i for i in range(len(h)) if _letter(h[i]) and (i == 0 or not _letter(h[i - 1]))]
    ends = [j for j in range(1, len(h) + 1) if _letter(h[j - 1]) and (j == len(h) or not _letter(h[j]))]
    for i in starts:
        for j in ends:
            if j > i and norm(h[i:j]) == n:
                return i
    return -1


FUNCTION_WORDS = {norm(w) for w in (
    "और का की के को ने में से पर है हैं था थी थे ही भी तो यह वह वे वो इस उस इन उन उन्हें उनके उनकी उनका उन्होंने "
    "किया गया गई गए हो कर लिए जो बहुत साथ बाद").split()}


def quotes(item: str, text: str) -> bool:
    """Whether a checker's item quotes text: True when it quotes no Hindi, when its Hindi appears in text, or when
    at least half of its quoted Hindi words do. False means it quotes Hindi that text never says."""
    runs = re.findall(r"[\u0900-\u0963\u0966-\u097f]+(?:\s+[\u0900-\u0963\u0966-\u097f]+)*", item or "")
    words = [w for r in runs for w in r.split() if len(norm(w)) >= 3 and norm(w) not in FUNCTION_WORDS]
    return sum(contains(text, w) for w in words) * 2 >= len(words)


def _letter(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LM" or ch.isdigit()


def devanagari_share(text: str) -> float:
    """Share of the letters in text that are Devanagari."""
    letters = [ch for ch in text if unicodedata.category(ch)[0] in "LM"]
    return sum("\u0900" <= ch <= "\u097f" for ch in letters) / max(len(letters), 1)


def latin_words(text: str) -> list[str]:
    """Words in Latin script inside a Hindi text (agency names, flight numbers): they must come from a source. Accented
    letters belong to the word ("La Verrière" was read as "Verri" and "re", neither in the source)."""
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’\-]*", text)


def date_hi(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


_DEV = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
                "kkggnccjjnttddnttddnppbbmyrlvsssh", strict=True))
_DEV.update({unicodedata.normalize("NFC", k): v for k, v in {
    "ज़": "j", "फ़": "f", "क़": "k", "ख़": "k", "ग़": "g", "ड़": "r", "ढ़": "r", "ऋ": "r", "ृ": "r", "ं": "n",
    "ँ": "n"}.items()})
_EN = [("ph", "f"), ("sh", "s"), ("ch", "c"), ("th", "t"), ("kh", "k"), ("gh", "g"), ("bh", "b"), ("dh", "d"),
       ("jh", "j"), ("ck", "k"), ("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks")]


def skeleton_hi(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    out, i = [], 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair in _DEV:
            out.append(_DEV[pair])
            i += 2
            continue
        ch = text[i]
        if ch in _DEV:
            out.append(_DEV[ch])
        elif "a" <= ch.lower() <= "z":
            out.append(ch.lower())
        i += 1
    return re.sub(r"[aeiouyh]", "", "".join(out))


def skeleton_en(text: str) -> str:
    t = re.sub(r"[^a-z]", "", text.lower())
    for a, b in _EN:
        t = t.replace(a, b)
    return re.sub(r"[aeiouyh]", "", t)


def likeness(hi: str, en: str) -> float:
    """How closely a Hindi spelling transliterates an English name, 0 to 1 ("जैकी श्रॉफ" 0.73, "जय किशन श्राफ" 0.62
    for "Jackie Shroff")."""
    a, b = skeleton_hi(hi).replace("c", "k"), skeleton_en(en).replace("c", "k")
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def sounds_alike(hi: str, en: str) -> bool:
    """A rough check that a Hindi spelling transliterates an English name ("चेन्नई" ~ "Chennai")."""
    return likeness(hi, en) >= 0.6
