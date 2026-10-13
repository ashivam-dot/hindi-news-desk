"""Facts a story may state, read from Wikidata (CC0) and Wikipedia infobox fields, and the rules that keep them
honest: a count is used only when both sources agree, and anything uncertain is left out rather than guessed."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone

from . import wiki

# Summaries that guess at motive or cause are never read out; the Short says the cause is under investigation.
SPECULATIVE = re.compile(r"\b(suspect\w*|alleged\w*|possibl\w*|reported\w*|believed|likely|apparent\w*|suicid\w*|"
                         r"terror\w*|murder\w*|hijack\w*|sabotage|unknown|disputed)\b", re.I)
FEMALE, MALE = "Q6581072", "Q6581097"
MIN_ARTICLE_AGE = timedelta(hours=6)


def date_words(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = math.radians
    h = math.sin(r(b[0] - a[0]) / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(r(b[1] - a[1]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def city_of(text: str | None) -> str | None:
    """'Dubai International Airport, Dubai, United Arab Emirates' -> 'Dubai'; 'Newark, New Jersey, U.S.' -> 'Newark'."""
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 3 and re.search(r"\b(Airport|Station|Port|Harbou?r|Terminal)\b", parts[0]):
        return parts[1]
    return parts[0] if parts else None


def plain_title(title: str) -> str:
    """'Margaret Hamilton (software engineer)' -> 'Margaret Hamilton': disambiguation is for search, not speech."""
    return re.sub(r"\s*\([^)]*\)$", "", title).strip()


def numbers_in(text: str) -> list[str]:
    return re.findall(r"\d{1,3}(?:,\d{3})+|\d+", text or "")


def agreed(text: str | None, ent: dict, pid: str, need_wikidata: bool) -> int | None:
    """A count both sources give: the infobox's exact leading number, matching a Wikidata value of the property.

    Without Wikidata values, the infobox alone counts only when need_wikidata is False (never for deaths).
    """
    n = wiki.leading_number(text)
    if n is None or re.search(r"\d\s*\+|\bat least\b|\bover\b|\bmore than\b|\bup to\b", text or "", re.I):
        return None
    values = {int(c["value"]) for c in wiki.claims(ent, pid)}
    if not values:
        return None if need_wikidata else n
    return n if n in values else None


def _first(fields: dict, *keys: str) -> str | None:
    return next((fields[k] for k in keys if fields.get(k)), None)


def _event_date(ent: dict) -> date | None:
    for pid in ("P585", "P580"):
        for c in wiki.claims(ent, pid):
            d = wiki.wd_time(c["value"])
            if d:
                return d
    return None


MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")


def infobox_date(fields: dict) -> date | None:
    """The first full date in the infobox's date field, or a storm's 'formed' field ('9 October 2026',
    'October 9, 2026', '9–10 October 2026')."""
    text = (fields.get("date") or fields.get("formed") or "").lower()
    m = re.search(r"(\d{1,2})(?:\s*[–-]\s*\d{1,2})?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", text)
    if m:
        day, month, year = int(m.group(1)), MONTHS.index(m.group(2)) + 1, int(m.group(3))
    else:
        m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:\s*[–-]\s*\d{1,2})?,?\s+(\d{4})", text)
        if not m:
            return None
        day, month, year = int(m.group(2)), MONTHS.index(m.group(1)) + 1, int(m.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _check_age(title: str) -> None:
    made = wiki.created(title)
    if made and (age := datetime.now(timezone.utc) - made) < MIN_ARTICLE_AGE:
        left = (MIN_ARTICLE_AGE - age).total_seconds() / 3600
        raise ValueError(f"gate: the article is under {MIN_ARTICLE_AGE.seconds // 3600} hours old; facts may still "
                         f"move (ready in {left:.1f} h)")


def _pronouns(ent: dict) -> tuple[str, str]:
    sex = next((c["value"] for c in wiki.claims(ent, "P21")), None)
    return ("She", "Her") if sex == FEMALE else ("He", "His") if sex == MALE else ("They", "Their")
