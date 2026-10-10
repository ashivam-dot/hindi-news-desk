"""Public-service advisories: a hand-checked list (closed stations, cancelled trains, roads to avoid) shown on screen
card by card, narrated in the Sulafat voice. Each advisory is a committed advisories/<name>.json; the scheduled run
publishes it once, before the radar, and never after its `until` time, when the list would be stale.

Each beat names the real place it is about with a `photo` (a Commons file an editor chose: the closed station, the
cancelled trains' terminus, the road under diversion). The photo fills the frame with the same depth-parallax camera
move as a story, so the background changes with the topic; the card sits on frosted glass over it and unrolls line
by line. Photos go through the story's licence and decency checks (media.picks) and are credited on screen and in
the description. A beat without a usable photo falls back to the plain backdrop. A spec may name the video it
`replaces`; once the new one is public, the old one is made private.

The narration goes through the same Sulafat takes and speech check as a story, and publishing through the same
identity-pinned uploader; the story gate (Wikipedia facts) does not apply because nothing here is written by a model.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from . import compose, config, ledger, media
from .compose import FPS, H, W, _blit, _font, _fit, _rgba, _text_layer
from .spec import Beat, Short

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "advisories"
ACCENT = (255, 196, 64)
TOP, BOTTOM = round(H * 0.07), round(H * 0.61)  # cards sit above the captions (compose.CAPTION_Y)
PANEL = (12, 16, 24, 222)
GLASS = (10, 14, 22, 150)  # over a photo: the frosted backdrop carries the contrast
DISCLOSURE = "सूची: DMRC, रेलवे, पुलिस की सूचनाएँ · आवाज़: AI"
DISCLOSURE_PHOTOS = "सूची: DMRC, रेलवे, पुलिस · तस्वीरें: Wikimedia Commons · आवाज़: AI"
UNROLL = 0.7  # seconds for a card to unroll top to bottom
DIM = 0.72  # the photo under a card is dimmed so the card always reads
ORIGINAL_MAX = 6400  # larger originals keep Commons' rendition
ORIGINALS = "https://upload.wikimedia.org/wikipedia/commons/"


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
    scene = {"mood": "news", "advisory": True}
    if spec.get("replaces"):
        scene["replaces"] = spec["replaces"]
    return Short(id=spec["id"], kind="advisory", title=spec["title"], beats=beats, facts=[], sources=spec["sources"],
                 loss=False, scene=scene, tags=spec["tags"], summary=spec["summary"],
                 credits=[spec["source_line"]], hashtags=spec["hashtags"])


def attach_photos(short: Short, spec: dict, folder: Path) -> list[str]:
    """Download each beat's photo into the scene (scene["photos"], scene["beat_photo"]); returns the files that
    failed the licence or decency checks (their beats keep the plain backdrop)."""
    wanted = [b.get("photo") for b in spec["beats"]]
    names = list(dict.fromkeys(f.replace("_", " ") for f in wanted if f))
    if not names:
        return []
    names = [f if f.startswith("File:") else "File:" + f for f in names]
    picked = media.picks(names, limit=len(names))
    for p in picked:
        # A background is cropped to the full 9:16 height, so the 1600 px rendition would be upscaled to mush.
        m = re.search(r"/commons/thumb/([0-9a-f]/[0-9a-f]{2}/[^/?]+)/", p.url)
        if m and max(p.width, p.height) <= ORIGINAL_MAX:
            p.url = ORIGINALS + m.group(1)
    found = {p.file: p for p in media.download(picked, folder)}
    photos = [found[f] for f in names if f in found]
    index = {p.file: i for i, p in enumerate(photos)}
    short.scene["photos"] = media.as_dicts(photos)
    for d in short.scene["photos"]:
        img = Image.open(d["path"])
        upright = ImageOps.exif_transpose(img)  # originals, unlike renditions, may still carry an EXIF rotation
        if upright.size != img.size:
            upright.convert("RGB").save(d["path"], quality=94)
        w, h = upright.size
        d["focus"] = [0, 0, w, h]  # fill the frame: compose.Plate crops to the photo's full height
    short.scene["beat_photo"] = [index.get(("File:" + f.removeprefix("File:")).replace("_", " ")) if f else None
                                 for f in wanted]
    for p in photos:
        if p.credit not in short.credits:
            short.credits.append(p.credit)
    return [f for f in names if f not in found]


def _background() -> np.ndarray:
    y = np.linspace(0, 1, H)[:, None, None]
    x = np.linspace(-1, 1, W)[None, :, None]
    top, bottom = np.array([14, 22, 40]), np.array([4, 6, 12])
    img = top * (1 - y) + bottom * y
    glow = np.exp(-((x * 0.9) ** 2 + ((y - 0.22) * 2.6) ** 2)) * np.array([30, 40, 70])
    return np.clip(img + glow, 0, 255).astype(np.uint8)


def _panel(rows: list, height: int, fill: tuple = PANEL) -> tuple[np.ndarray, np.ndarray]:
    img = Image.new("RGBA", (W - 80, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, height - 1), radius=28, fill=fill, outline=(255, 255, 255, 40), width=2)
    for draw in rows:
        draw(d)
    return _rgba(img)


def card_layer(card: dict, fill: tuple = PANEL) -> tuple[np.ndarray, np.ndarray] | None:
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
    return _panel(rows, height, fill)


class Backdrops:
    """The background of each beat at time t: its photo under a slow camera move, graded and dimmed, or the plain
    backdrop when the beat has no photo."""

    def __init__(self, short: Short):
        photos = short.scene.get("photos") or []
        self.plates = [compose.Plate(p, Path(p["path"]).with_suffix(".depth.npy")) for p in photos]
        self.cam = compose.Camera()
        self.grade = compose.Grade("news", seed=len(short.id))
        self.plain = _background()

    def frame(self, shot: dict, t: float, i: int) -> np.ndarray:
        if shot["photo"] is None:
            return self.plain.copy()
        u = (t - shot["start"]) / max(shot["end"] - shot["start"], 0.1)
        img = self.cam.shoot(self.plates[shot["photo"]], u, shot["motion"])
        if shot["card"] is None:
            img = cv2.GaussianBlur(img, (0, 0), 14)
        return (self.grade.apply(img, i).astype(np.float32) * DIM).astype(np.uint8)


def _frost(frame: np.ndarray, card: tuple[np.ndarray, np.ndarray], x: int, y: int) -> None:
    """Blur what lies under the card's panel, so the card reads like frosted glass over the photo."""
    a = card[1]
    h, w = a.shape[:2]
    h = min(h, H - y)
    region = frame[y:y + h, x:x + w]
    small = cv2.resize(region, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    soft = cv2.resize(cv2.GaussianBlur(small, (0, 0), 5), (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    m = np.clip(a[:h] * 4, 0, 1)
    frame[y:y + h, x:x + w] = (region * (1 - m) + soft * 0.8 * m).astype(np.uint8)


def _unrolled(card: tuple[np.ndarray, np.ndarray], u: float) -> tuple[np.ndarray, np.ndarray]:
    rgb, a = card
    if u >= 1:
        return card
    h = a.shape[0]
    edge = compose._ease(u) * (h + 90)
    ramp = np.clip((edge - np.arange(h, dtype=np.float32)) / 90, 0, 1)[:, None, None]
    return rgb, a * ramp


def render(short: Short, timing: dict, work: Path) -> dict:
    """short.mp4 like compose.render: each beat's card over that beat's photo (or the plain backdrop)."""
    backdrops = Backdrops(short)
    captions = compose.Captions(timing["words"], ACCENT)
    duration = timing["duration"] + 0.6
    spans = timing["beats"]
    beat_photo = short.scene.get("beat_photo") or [None] * len(short.beats)
    cards = [card_layer(b.card, PANEL if beat_photo[i] is None else GLASS) for i, b in enumerate(short.beats)]
    shots = [{"start": s if i else 0.0, "end": e if i < len(spans) - 1 else duration, "photo": beat_photo[i],
              "card": cards[i], "motion": compose.MOTIONS[i % len(compose.MOTIONS)]}
             for i, (s, e) in enumerate(spans)]
    source = compose._credit_layer(short.credits[0])
    photo_credits = [compose._credit_layer(p["credit"]) for p in short.scene.get("photos") or []]
    badge = compose._badge_layer()
    end = compose._end_layers(ACCENT, DISCLOSURE_PHOTOS if photo_credits else DISCLOSURE)
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
        frame = frame_at(t, shots, backdrops, end, i)
        _blit(frame, badge, 36, round(H * 0.732), 0.97)
        shot = shots[_shot(t, shots)]
        if shot["card"] is not None:
            _blit(frame, source, 36, round(H * 0.785), 0.9)
            if shot["photo"] is not None:
                _blit(frame, photo_credits[shot["photo"]], 36, round(H * 0.808), 0.9)
        captions.draw(frame, t)
        enc.stdin.write(frame.tobytes())
        if i in {int(s["start"] * FPS) + 20 for s in shots}:
            Image.fromarray(frame).save(stills / f"t{i // FPS:03d}.png")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the advisory")
    return {"duration": round(duration, 2), "frames": n, "template": "advisory", "cards": len(cards), "fps": FPS,
            "size": [W, H], "photos": len(photo_credits)}


def _shot(t: float, shots: list[dict]) -> int:
    return next(j for j, s in enumerate(shots) if t < s["end"] or j == len(shots) - 1)


def _with_card(frame: np.ndarray, shot: dict, card: tuple, since: float, first: bool) -> None:
    # The first card is whole from frame 0: it may be the cover.
    a = 1.0 if first else min(1.0, since / 0.25)
    y = TOP + round(24 * (1 - a))
    if shot["photo"] is not None:
        _frost(frame, card, 40, y)
    _blit(frame, card if first else _unrolled(card, since / UNROLL), 40, y, a)


def frame_at(t: float, shots: list[dict], backdrops: Backdrops, end: list, i: int = 0) -> np.ndarray:
    k = _shot(t, shots)
    shot = shots[k]
    frame = backdrops.frame(shot, t, i)
    since = t - shot["start"]
    card = shot["card"]
    if card is not None:
        _with_card(frame, shot, card, since, k == 0)
    else:
        a = min(1.0, since / 0.4)
        logo, src, disc = end
        if logo is not None:
            _blit(frame, logo, (W - logo[1].shape[1]) // 2, round(H * 0.29), a)
        _blit(frame, src, (W - src[1].shape[1]) // 2, round(H * 0.40), a)
        _blit(frame, disc, (W - disc[1].shape[1]) // 2, round(H * 0.45), a)
    if k and since * FPS < compose.CROSSFADE:
        before = shots[k - 1]
        prev = backdrops.frame(before, t, i)
        if before["card"] is not None:
            _with_card(prev, before, before["card"], t - before["start"], k - 1 == 0)
        frame = cv2.addWeighted(frame, since * FPS / compose.CROSSFADE, prev, 1 - since * FPS / compose.CROSSFADE, 0)
    return frame


def make(spec: dict, work_root: Path) -> tuple[Short, dict]:
    from . import voice

    short = short_of(spec)
    for b in short.beats:
        card_layer(b.card)  # a card that does not fit fails before any voice quota is spent
    work = work_root / short.id
    work.mkdir(parents=True, exist_ok=True)
    unusable = attach_photos(short, spec, work / "photos")
    from . import youtube

    for engine in youtube.VOICE_LINE:  # an over-long description fails before any voice quota is spent
        youtube.description(short, {"engine": engine})
    short.save(work / "short.json")
    timing = voice.synthesize_lines(short, work)
    stats = render(short, timing, work)
    stats["unusable_photos"] = unusable
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
    row = {"id": short.id, "kind": short.kind, "title": short.title, "loss": False, "published_at": ledger.now(),
           "event_time": "", "voice": voice.get("engine"), "voice_model": voice.get("served_model"),
           "orbitwire_overlap": None, **result}
    if old := short.scene.get("replaces"):
        try:
            youtube.retire(old)
            row["replaced"] = old
        except Exception as exc:  # the new advisory is already public: record it, and say why the old one stayed
            row["replace_error"] = f"{old}: {type(exc).__name__}: {exc}"[:300]
    ledger.record_publish(row)
    return result
