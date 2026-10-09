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


def values(text: str) -> set[str]:
    """Every value a source states, scaled ("1.5 million" -> 1500000) and as written ("1.5")."""
    text = ascii_digits(text)
    found = {v for v, _ in numbers(text)}
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
    """For comparing spellings: NFC, no nukta, chandrabindu as anusvara, no joiners, Latin in lower case."""
    text = unicodedata.normalize("NFC", text or "")
    text = unicodedata.normalize("NFD", text).replace(NUKTA, "")
    text = unicodedata.normalize("NFC", text).replace(CHANDRABINDU, ANUSVARA)
    text = re.sub("[\u200c\u200d]", "", text)
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


def _letter(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LM" or ch.isdigit()


def devanagari_share(text: str) -> float:
    """Share of the letters in text that are Devanagari."""
    letters = [ch for ch in text if unicodedata.category(ch)[0] in "LM"]
    return sum("\u0900" <= ch <= "\u097f" for ch in letters) / max(len(letters), 1)


def latin_words(text: str) -> list[str]:
    """Words in Latin script inside a Hindi text (agency names, flight numbers): they must come from a source."""
    return re.findall(r"[A-Za-z][A-Za-z0-9'’\-]*", text)


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


def sounds_alike(hi: str, en: str) -> bool:
    """A rough check that a Hindi spelling transliterates an English name ("चेन्नई" ~ "Chennai")."""
    a, b = skeleton_hi(hi), skeleton_en(en)
    a, b = a.replace("c", "k"), b.replace("c", "k")
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.6
