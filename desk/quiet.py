"""A quiet channel publishes: after QUIET_AFTER with no Short, presentation ceilings stop refusing stories.

Owner, 2026-10-26: "start publishing top news ... don't stop publishing". From 25 Oct 04:06 UTC the channel went
36 h without a Short while every run was green: the day's top stories (Rahul Gandhi, the Andhra cyclone, the Supreme
Court, Kharge, the Tiger Shroff update) were refused 71 times, almost all for presentation (a 45-58-word budget the
flash-lite writer misses with 64-74 words, at most two text cards, photo time shares, photos new to the last 96 h),
not for facts. While the channel is quiet those checks are waived; every check of truth stays: numbers, names,
sources and outlets, decorum, dates, a photo of someone the beat does not name, the wrong face, licences.

DESK_QUIET=on|off forces the mode; unset (auto) reads the ledger's last publish.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

QUIET_AFTER = timedelta(hours=3)
# The budget the format had before 2026-10-23 (60-80 words, 31-35 s at 2.3 words a second).
MAX_WORDS, MAX_BEAT_WORDS = 80, 18
FRESH_PICTURES = 1
# Presentation refusals, matched by their wording in writer, match and gate. A card over another picture, a
# photo its beat does not name and the wrong face are not here: they say something untrue.
SOFT = re.compile(
    r"^(?:gate: )?(?:text cards: |pictures: (?:real photos fill only|the story's person fills only|maps fill "
    r"|\d+ map views \(at most|only \d+ different (?:pictures once|ones on screen)|.+ fills \d+% of the Short "
    r"\(at most|.+ stays up [\d.]+ s in a row|.+ stays on screen for \d+ beats in a row|.+ is under \d+ of \d+ "
    r"beats$))|^beats [\d,]+ name nothing that can be shown|^the story is about .+ beats name them")
_state: dict = {}


def _at(value: str) -> datetime:
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def active(at: datetime | None = None) -> bool:
    """Whether the channel has gone QUIET_AFTER without a public Short (once per process: a run's prepare, render
    and publish gates must agree)."""
    forced = os.environ.get("DESK_QUIET", "").strip().lower()
    if forced in ("on", "off"):
        return forced == "on"
    if "on" not in _state:
        from . import ledger

        now = at or datetime.now(timezone.utc)
        times = []
        for r in ledger.published():
            try:
                t = _at(r["published_at"])
            except (KeyError, ValueError, TypeError):
                continue
            if t <= now and not r.get("retired_at"):
                times.append(t)
        _state["on"] = not times or now - max(times) >= QUIET_AFTER
    return _state["on"]


def reset() -> None:
    _state.clear()


def soft(problem: str) -> bool:
    return bool(SOFT.search(problem.strip()))


def keep(problems: list[str]) -> list[str]:
    """The problems that still refuse a Short: all of them, or while the channel is quiet only the hard ones."""
    if not problems or not active():
        return problems
    return [p for p in problems if not soft(p)]
