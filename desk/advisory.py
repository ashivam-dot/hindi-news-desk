"""Public-service advisories: a hand-checked list (closed stations, cancelled trains, roads to avoid) shown on screen
card by card, narrated in the Sulafat voice. Each advisory is a committed advisories/<name>.json; the scheduled run
publishes it once, before the radar, and never after its `until` time, when the list would be stale.

The narration goes through the same Sulafat takes and speech check as a story, and publishing through the same
identity-pinned uploader; the story gate (Wikipedia facts, photos) does not apply because nothing here is written by
a model.
"""
from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import compose, config, ledger
from .compose import FPS, H, W, _blit, _font, _fit, _rgba, _text_layer
from .spec import Beat, Short

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "advisories"
ACCENT = (255, 196, 64)
TOP, BOTTOM = round(H * 0.07), round(H * 0.61)  # cards sit above the captions (compose.CAPTION_Y)
PANEL = (12, 16, 24, 222)
DISCLOSURE = "सूची: DMRC, रेलवे, पुलिस की सूचनाएँ · आवाज़: AI"


def _until(spec: dict) -> datetime:
    return datetime.fromisoformat(spec["until"].replace("Z", "+00:00"))


def load_all() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SPECS.glob("*.json"))]


def pending(at: datetime | None = None) -> list[dict]:
    """Advisories still current and not yet on the channel."""
    at = at or datetime.now(timezone.utc)
    done = {r["id"] for r in ledger.published()}
    return [s for s in load_all() if s["id"] not in done and at < _until(s)]


def short_of(spec: dict) -> Short:
    beats = [Beat(text=b["say"], shot="outro" if b["card"]["kind"] == "outro" else "card", card=b["card"])
             for b in spec["beats"]]
    return Short(id=spec["id"], kind="advisory", title=spec["title"], beats=beats, facts=[], sources=spec["sources"],
                 loss=False, scene={"mood": "news", "advisory": True}, tags=spec["tags"], summary=spec["summary"],
                 credits=[spec["source_line"]], hashtags=spec["hashtags"])


def _background() -> np.ndarray:
    y = np.linspace(0, 1, H)[:, None, None]
    x = np.linspace(-1, 1, W)[None, :, None]
    top, bottom = np.array([14, 22, 40]), np.array([4, 6, 12])
    img = top * (1 - y) + bottom * y
    glow = np.exp(-((x * 0.9) ** 2 + ((y - 0.22) * 2.6) ** 2)) * np.array([30, 40, 70])
    return np.clip(img + glow, 0, 255).astype(np.uint8)


def _panel(rows: list, height: int) -> tuple[np.ndarray, np.ndarray]:
    img = Image.new("RGBA", (W - 80, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, height - 1), radius=28, fill=PANEL, outline=(255, 255, 255, 40), width=2)
    for draw in rows:
        draw(d)
    return _rgba(img)


def card_layer(card: dict) -> tuple[np.ndarray, np.ndarray] | None:
    kind = card["kind"]
    inner = W - 80 - 2 * 48
    if kind == "outro":
        return None
    head = _fit("ExtraBold", 96 if kind == "title" else 78, card["big"], inner, 44)
    rows, y = [], 44

    def text(xy, s, font, fill):
        rows.append(lambda d, xy=xy, s=s, font=font, fill=fill: d.text(xy, s, font=font, fill=fill))

    def dot(x, y, size):  # drawn, not a glyph: Mukta has no bullet characters
        rows.append(lambda d: d.ellipse((x, y + size * 0.42, x + 16, y + size * 0.42 + 16), fill=ACCENT + (255,)))

    text((48, y), card["big"], head, (255, 255, 255, 255))
    y += head.size + 38
    rows.append(lambda d, y=y: d.rounded_rectangle((48, y - 14, 48 + 120, y - 6), radius=4, fill=ACCENT + (255,)))
    if kind == "title":
        sub = _fit("Bold", 54, card["sub"], inner)
        text((48, y + 6), card["sub"], sub, ACCENT + (255,))
        y += sub.size + 56
        for line in card["lines"]:
            f = _fit("SemiBold", 64, line, inner - 34)
            dot(48, y, f.size)
            text((48 + 34, y), line, f, (255, 255, 255, 245))
            y += f.size + 36
    elif kind == "list":
        items = card["items"]
        col = (inner - 30) // 2
        size = 56
        per = math.ceil(len(items) / 2)
        step = size + 30
        for i, s in enumerate(items):
            cx, cy = 48 + (i // per) * (col + 30), y + 6 + (i % per) * step
            f = _fit("SemiBold", size, s, col - 34, 34)
            dot(cx, cy + (size - f.size) // 2, f.size)
            text((cx + 30, cy + (size - f.size) // 2), s, f, (255, 255, 255, 245))
        y += 6 + per * step + 18
        if card.get("foot"):
            f = _fit("Bold", 44, card["foot"], inner)
            text((48, y), card["foot"], f, ACCENT + (255,))
            y += f.size + 30
    else:
        for line in card["lines"]:
            f = _fit("SemiBold", 56, line, inner - 34, 34)
            dot(48, y, f.size)
            text((48 + 34, y), line, f, (255, 255, 255, 245))
            y += f.size + 34
    height = y + 22
    if height > BOTTOM - TOP:
        raise ValueError(f"card '{card['big']}' is {height} px tall; it must fit in {BOTTOM - TOP}")
    return _panel(rows, height)


def render(short: Short, timing: dict, work: Path) -> dict:
    """short.mp4 like compose.render, but on a plain backdrop with one card per beat."""
    background = _background()
    captions = compose.Captions(timing["words"], ACCENT)
    duration = timing["duration"] + 0.6
    spans = timing["beats"]
    cards = [card_layer(b.card) for b in short.beats]
    shots = [{"start": s if i else 0.0, "end": e if i < len(spans) - 1 else duration}
             for i, (s, e) in enumerate(spans)]
    source = compose._credit_layer(short.credits[0])
    badge = compose._badge_layer()
    end = compose._end_layers(ACCENT, DISCLOSURE)
    work.mkdir(parents=True, exist_ok=True)
    mixed = compose._mix(work / "narration.wav", short, duration, work)
    out = work / "short.mp4"
    stills = work / "stills"
    stills.mkdir(exist_ok=True)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(mixed), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    n = int(math.ceil(duration * FPS))
    for i in range(n):
        t = i / FPS
        frame = frame_at(t, shots, cards, background, end)
        _blit(frame, badge, 36, round(H * 0.732), 0.97)
        if cards[_shot(t, shots)] is not None:
            _blit(frame, source, 36, round(H * 0.785), 0.9)
        captions.draw(frame, t)
        enc.stdin.write(frame.tobytes())
        if i in {int(s["start"] * FPS) + 20 for s in shots}:
            Image.fromarray(frame).save(stills / f"t{i // FPS:03d}.png")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the advisory")
    return {"duration": round(duration, 2), "frames": n, "template": "advisory", "cards": len(cards), "fps": FPS,
            "size": [W, H]}


def _shot(t: float, shots: list[dict]) -> int:
    return next(j for j, s in enumerate(shots) if t < s["end"] or j == len(shots) - 1)


def frame_at(t: float, shots: list[dict], cards: list, background: np.ndarray, end: list) -> np.ndarray:
    k = _shot(t, shots)
    frame = background.copy()
    since = t - shots[k]["start"]
    card = cards[k]
    if card is not None:
        a = min(1.0, since / 0.25) if k else 1.0  # the first card is whole from frame 0: it may be the cover
        rise = round(24 * (1 - a))
        _blit(frame, card, 40, TOP + rise, a)
    else:
        a = min(1.0, since / 0.4)
        logo, src, disc = end
        if logo is not None:
            _blit(frame, logo, (W - logo[1].shape[1]) // 2, round(H * 0.29), a)
        _blit(frame, src, (W - src[1].shape[1]) // 2, round(H * 0.40), a)
        _blit(frame, disc, (W - disc[1].shape[1]) // 2, round(H * 0.45), a)
    if k and since * FPS < compose.CROSSFADE and cards[k - 1] is not None:
        prev = background.copy()
        _blit(prev, cards[k - 1], 40, TOP)
        frame = cv2.addWeighted(frame, since * FPS / compose.CROSSFADE, prev, 1 - since * FPS / compose.CROSSFADE, 0)
    return frame


def make(spec: dict, work_root: Path) -> tuple[Short, dict]:
    from . import voice

    short = short_of(spec)
    for b in short.beats:
        card_layer(b.card)  # a card that does not fit fails before any voice quota is spent
    work = work_root / short.id
    work.mkdir(parents=True, exist_ok=True)
    short.save(work / "short.json")
    timing = voice.synthesize_lines(short, work)
    stats = render(short, timing, work)
    stats["voice"] = {k: timing["voice"].get(k) for k in ("engine", "identity", "preview", "served_model", "wpm",
                                                          "coverage", "tempo")}
    (work / "render.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    return short, stats


def publish(short: Short, work: Path) -> dict:
    from . import youtube

    if not config.channel_id_ready():
        raise ValueError("channel: DESK_CHANNEL_ID is not configured")
    voice = json.loads((work / "timing.json").read_text(encoding="utf-8"))["voice"]
    result = youtube.publish(short, work / "short.mp4", voice)
    ledger.record_publish({"id": short.id, "kind": short.kind, "title": short.title, "loss": False,
                           "published_at": ledger.now(), "event_time": "", "voice": voice.get("engine"),
                           "voice_model": voice.get("served_model"), "orbitwire_overlap": None, **result})
    return result
