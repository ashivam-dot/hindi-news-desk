"""Real news footage in the full-screen Short (owner, 2026-10-29: "add the original video or image based on news in
your videos and that is super important. Seeing the original content is really fascinating").

footage.py (the Chaukanna kit's step) finds CC BY YouTube videos of the story's own event from channels big enough to
own what they film, has Gemma judge their shots, and cuts each clip muted to the full frame. Here a Short gets them:
the most relevant on the hook beat, then on the beats that stand over a map, a stand-in or a repeated photo, one clip a
beat. A beat keeps its photo (every picture check of gate.py and match.py still holds); its clip plays over it from the
beat's start for the clip's length, with the clip's own credit. No clip, or any failure, and the Short goes on with
its photos. Off with DESK_FOOTAGE=off.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import match, visuals
from .spec import Short, shot_photos

log = logging.getLogger(__name__)

QUERY_WORDS = 7
LEAST_BEAT = 1.6  # seconds: a shorter beat keeps its photo


def enabled() -> bool:
    return os.environ.get("DESK_FOOTAGE", "on").strip().lower() not in {"off", "false", "0", "no"}


def query(story: str) -> str:
    """The English headline's lead, as a YouTube search: before a ": minister says" tail, no figures or symbols."""
    head = re.split(r"\s*[:|–—]\s+", story or "", maxsplit=1)[0]
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'.-]*", head) if w.lower() not in {"by", "per", "from", "to", "the", "a", "an"}]
    return " ".join(words[:QUERY_WORDS])


def package(short: Short) -> dict:
    """What footage.for_story reads of a story."""
    scene = short.scene
    lead = query(scene.get("story") or "")
    subjects = [{"name": c["en"], "anchor": c.get("hi", "")} for c in scene.get("cast") or []
                if isinstance(c, dict) and c.get("en") and c.get("kind") != "thing"] or \
               [{"name": p["en"], "anchor": p.get("hi", "")} for p in scene.get("names") or []
                if isinstance(p, dict) and isinstance(p.get("en"), str)][:2]
    places = [c["en"] for c in scene.get("cast") or [] if isinstance(c, dict) and c.get("kind") == "place"]
    return {"title": f"{lead}: {short.title}" if lead else short.title, "headline": short.title,
            "script": short.narration, "location": ", ".join(places[:2]), "subjects": subjects[:3]}


def order(short: Short, spans: list[tuple[float, float]] | None = None) -> list[int]:
    """The beats a clip may stand on, the first to fill first: the hook, then those over a map, a stand-in or a photo
    an earlier beat showed, then the rest; never a text card, the outro, or a beat shorter than LEAST_BEAT."""
    photos = short.scene.get("photos") or []
    shown: set[int] = set()
    ranked = []
    for k, b in enumerate(short.beats):
        mine = [i for i in shot_photos(b.shot) if i < len(photos)]
        if b.shot == "outro" or b.plate == match.CARD or not b.shot.startswith("photo:"):
            continue
        if spans and spans[k][1] - spans[k][0] < LEAST_BEAT:
            shown.update(mine)
            continue
        weak = any(visuals.is_map(photos[i]) or photos[i].get("stand_in") or i in shown for i in mine)
        ranked.append((0 if k == 0 else 1 if weak else 2, k))
        shown.update(mine)
    return [k for _, k in sorted(ranked)]


def assign(short: Short, clips: list[dict], spans: list[tuple[float, float]] | None = None) -> list[dict]:
    """The clips, most relevant first, each on its beat ("beat"); clips past the free beats are dropped."""
    best = sorted(clips, key=lambda c: -float(c.get("relevance") or 0))
    return [c | {"beat": k} for k, c in zip(order(short, spans), best)]


def attach(short: Short, work: Path, now: datetime | None = None,
           spans: list[tuple[float, float]] | None = None) -> list[dict]:
    """Finds the story's footage and records it in short.scene["clips"] (also when none: []). Never raises."""
    if short.scene.get("template") != "full" or not enabled():
        return []
    from . import compose, footage

    try:
        found = footage.for_story(package(short), work / "footage", now or datetime.now(timezone.utc),
                                  media={"full": (compose.W, compose.H)})
    except Exception as exc:  # noqa: BLE001 - footage is a bonus; the Short goes on with its photos
        log.warning("footage failed, photos only: %s", exc)
        found = []
    placed = assign(short, found, spans)
    short.scene["clips"] = [{k: c[k] for k in ("path", "seconds", "video", "channel", "title", "start", "what",
                                               "relevance", "credit", "cite", "beat") if k in c} for c in placed]
    log.info("footage: %d of %d clips placed on beats %s", len(placed), len(found), [c["beat"] for c in placed])
    return short.scene["clips"]


def credits(short: Short) -> list[str]:
    """The description's attribution lines, as CC BY asks (footage.attribution)."""
    from . import footage

    return footage.attribution(short.scene.get("clips") or [])
