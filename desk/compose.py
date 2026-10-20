"""Story renderer: real photos brought to life with depth parallax (a slow camera move through the scene), word-by-word
Hindi captions, context chips, photo credits, an always-visible AI-voice label and a scored, loudness-normalised mix.
Pure Python + ffmpeg, about real time.

Devanagari needs complex text shaping (conjuncts such as क्ष and त्र, vowel signs that sit before their consonant), so
every string is laid out with Pillow's RAQM engine (HarfBuzz + FriBiDi) in Mukta (SIL Open Font License, bundled in
desk/fonts). Pillow's basic layout draws Hindi wrongly, so rendering refuses to run without RAQM.
"""
from __future__ import annotations

import functools
import math
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from . import config, depth, hindi, music
from .spec import Short, shot_photos

W, H, FPS = 1080, 1920, 30
MARGIN = 1.16  # the photo plate is larger than the frame so the camera can move
FONTS = Path(__file__).resolve().parent / "fonts"
WEIGHTS = {"ExtraBold": "Mukta-ExtraBold.ttf", "Bold": "Mukta-Bold.ttf", "SemiBold": "Mukta-SemiBold.ttf",
           "Medium": "Mukta-Medium.ttf"}
DISCLOSURE = "असली तस्वीरें: Wikimedia Commons · आवाज़: AI"


def disclosure(photos: list[dict]) -> str:
    """The end card's disclosure, naming Openverse too when a photo comes from it."""
    from . import media

    return DISCLOSURE.replace("Wikimedia Commons", media.hosts(photos))


# On screen for the whole Short (India's IT Rules ask synthetic content to carry a visible label).
AI_BADGE = "AI आवाज़"
ACCENT = {"tribute": (255, 205, 92), "news": (90, 200, 255)}
CROSSFADE = 8  # frames
CAPTION_Y = 0.665
MOTIONS = [
    {"z": (1.00, 1.09), "dz": (0.00, 0.07), "pan": (0, 0, 0, -20), "par": (0, 0)},  # push in
    {"z": (1.05, 1.07), "dz": (0.02, 0.03), "pan": (-45, 45, 0, 0), "par": (34, 0)},  # drift right
    {"z": (1.10, 1.02), "dz": (0.07, 0.01), "pan": (0, 0, 10, -10), "par": (0, 0)},  # pull back
    {"z": (1.05, 1.08), "dz": (0.02, 0.04), "pan": (40, -40, 0, 0), "par": (-34, 0)},  # drift left
    {"z": (1.04, 1.08), "dz": (0.02, 0.05), "pan": (0, 0, 40, -40), "par": (0, 26)},  # rise
]


@functools.lru_cache(maxsize=None)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    if not features.check("raqm"):
        raise RuntimeError("Pillow has no RAQM text layout here; Devanagari would be drawn wrongly")
    return ImageFont.truetype(str(FONTS / WEIGHTS[weight]), size, layout_engine=ImageFont.Layout.RAQM)


@functools.lru_cache(maxsize=None)
def _glyphs(weight: str = "Medium") -> frozenset[int]:
    from fontTools.ttLib import TTFont

    return frozenset(TTFont(str(FONTS / WEIGHTS[weight])).getBestCmap())


def drawable(text: str, weight: str = "Medium") -> str:
    """text without the characters Mukta has no glyph for (a credit may name an author in any script)."""
    have = _glyphs(weight)
    kept = "".join(ch for ch in text if ord(ch) in have or ch in "\u200c\u200d")
    return re.sub(r"\s{2,}", " ", re.sub(r"\(\s*\)", "", kept)).strip()


def _ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class Plate:
    """One photo prepared for camera moves: RGB and depth at plate size (the frame, or a bulletin's photo window)."""

    def __init__(self, photo: dict, cache: Path, size: tuple[int, int] = (W, H), face_share: float = 0.17):
        img = Image.open(photo["path"]).convert("RGB")
        # A map is flat: depth parallax would bend its roads and labels.
        dep = np.full((img.height, img.width), 0.5, np.float32) if photo.get("role") == "map" \
            else depth.estimate(img, cache)
        tw, th = size
        pw, ph = round(tw * MARGIN), round(th * MARGIN)
        iw, ih = img.size
        focus = photo.get("focus")
        # Fill the plate unless the photo is far wider than it (a panorama is shown whole on a blurred copy).
        if focus or iw / ih <= max(0.9, 1.6 * tw / th):
            if focus:
                fx, fy, fw, fh = focus
                cx, cy = fx + fw / 2, fy + fh / 2
                # Face about face_share of the frame height, but never crop below 900 px (upscaling turns to mush).
                ch = min(ih, max(fh / face_share, min(ih, 900 * th / H)))
            else:
                cx, cy, ch = iw / 2, ih * 0.42, ih
            cw = ch * tw / th
            if cw > iw:
                cw, ch = iw, iw * th / tw
            ch = min(ch, ih)
            cw = min(cw, iw)
            x0 = min(max(cx - cw / 2, 0), iw - cw)
            y0 = min(max(cy - ch * 0.36, 0), ih - ch)
            box = (round(x0), round(y0), round(x0 + cw), round(y0 + ch))
            rgb = img.crop(box).resize((pw, ph), Image.LANCZOS)
            d = cv2.resize(dep[box[1]:box[3], box[0]:box[2]], (pw, ph), interpolation=cv2.INTER_LINEAR)
            self.mode = "fill"
        else:
            scale = max(pw / iw, ph / ih)
            bg = img.resize((round(iw * scale), round(ih * scale)), Image.LANCZOS)
            left, top = (bg.width - pw) // 2, (bg.height - ph) // 2
            bg = bg.crop((left, top, left + pw, top + ph)).filter(ImageFilter.GaussianBlur(38))
            bg = Image.eval(bg, lambda v: int(v * 0.45))
            fw = round(pw * 0.94)
            fh = round(ih * fw / iw)
            if fh > ph * 0.62:
                fh = round(ph * 0.62)
                fw = round(iw * fh / ih)
            fg = img.resize((fw, fh), Image.LANCZOS)
            ox, oy = (pw - fw) // 2, round(ph * 0.42 - fh / 2)
            shadow = Image.new("L", (pw, ph), 0)
            ImageDraw.Draw(shadow).rectangle((ox + 6, oy + 14, ox + fw + 6, oy + fh + 14), fill=170)
            bg.paste(Image.new("RGB", (pw, ph), (0, 0, 0)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(22)))
            bg.paste(fg, (ox, oy))
            rgb = bg
            d = np.zeros((ph, pw), np.float32)
            d[oy:oy + fh, ox:ox + fw] = 0.35 + 0.65 * cv2.resize(dep, (fw, fh), interpolation=cv2.INTER_LINEAR)
            self.mode = "fit"
        self.rgb = np.asarray(rgb, dtype=np.uint8)
        self.depth = cv2.GaussianBlur(d.astype(np.float32), (0, 0), 3) - 0.5
        self.pw, self.ph = pw, ph


class Camera:
    def __init__(self, size: tuple[int, int] = (W, H)):
        tw, th = size
        gx, gy = np.meshgrid(np.arange(tw, dtype=np.float32) - tw / 2, np.arange(th, dtype=np.float32) - th / 2)
        self.gx, self.gy = gx, gy

    def shoot(self, plate: Plate, u: float, motion: dict, punch: float = 0.0) -> np.ndarray:
        e = _ease(u)
        z = (motion["z"][0] + (motion["z"][1] - motion["z"][0]) * e) * (1 + punch)
        dz = motion["dz"][0] + (motion["dz"][1] - motion["dz"][0]) * e
        px0, px1, py0, py1 = motion["pan"]
        cx = plate.pw / 2 + px0 + (px1 - px0) * e
        cy = plate.ph / 2 + py0 + (py1 - py0) * e
        parx, pary = motion["par"][0] * (e - 0.5), motion["par"][1] * (e - 0.5)
        # OpenCV 5 remaps only float32 maps, and a NumPy scalar (a float64 u, an int64 plate size) promotes to float64.
        f32 = np.float32
        bx = (cx + self.gx / z).astype(f32, copy=False)
        by = (cy + self.gy / z).astype(f32, copy=False)
        d = cv2.remap(plate.depth, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        zz = 1 + dz * d * 2
        mx = (cx + self.gx / (z * zz) - parx * d * 2).astype(f32, copy=False)
        my = (cy + self.gy / (z * zz) - pary * d * 2).astype(f32, copy=False)
        return cv2.remap(plate.rgb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


class Grade:
    def __init__(self, mood: str, seed: int, size: tuple[int, int] = (W, H), bands: bool = True):
        tw, th = size
        yy, xx = np.mgrid[0:th, 0:tw].astype(np.float32)
        r = np.sqrt(((xx - tw / 2) / (tw * 0.75)) ** 2 + ((yy - th * 0.45) / (th * 0.7)) ** 2)
        vignette = np.clip(1.08 - 0.55 * r ** 2.2, 0.35, 1.0)
        # Darken behind the captions and the top chips so white text always reads.
        band = 1 - 0.32 * np.exp(-((yy - th * CAPTION_Y) / (th * 0.09)) ** 2) - 0.25 * np.exp(-((yy - th * 0.1) / (th * 0.07)) ** 2)
        self.mask = (vignette * (band if bands else 1.0))[..., None].astype(np.float32)
        self.tint = np.array([1.04, 1.0, 0.93] if mood == "tribute" else [0.97, 1.0, 1.04], np.float32)
        self.sat = 0.85 if mood == "tribute" else 0.95
        self.size = size
        rng = np.random.default_rng(seed)
        self.grain = [rng.normal(0, 5.0, (th // 2, tw // 2, 1)).astype(np.float32) for _ in range(4)]

    def apply(self, frame: np.ndarray, i: int) -> np.ndarray:
        f = frame.astype(np.float32)
        gray = f.mean(axis=2, keepdims=True)
        f = gray + (f - gray) * self.sat
        f = (f - 128) * 1.06 + 128
        f = f * self.tint * self.mask
        g = cv2.resize(self.grain[i % 4], self.size, interpolation=cv2.INTER_NEAREST)[..., None]
        return np.clip(f + g, 0, 255).astype(np.uint8)


def _rgba(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(img, dtype=np.float32)
    return a[..., :3], a[..., 3:4] / 255.0


def _blit(frame: np.ndarray, layer: tuple[np.ndarray, np.ndarray], x: int, y: int, alpha: float = 1.0) -> None:
    rgb, a = layer
    h, w = a.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    sub = frame[y0:y1, x0:x1].astype(np.float32)
    la = a[y0 - y:y1 - y, x0 - x:x1 - x] * alpha
    frame[y0:y1, x0:x1] = (sub * (1 - la) + rgb[y0 - y:y1 - y, x0 - x:x1 - x] * la).astype(np.uint8)


def _text_layer(lines: list[tuple[str, ImageFont.FreeTypeFont, tuple]], stroke: int = 0, gap: int = 8,
                pad: int = 0, box: tuple | None = None, accent: tuple | None = None) -> Image.Image:
    sizes = [f.getbbox(t, stroke_width=stroke) for t, f, _ in lines]
    w = max(b[2] - b[0] for b in sizes) + 2 * pad + (14 if accent else 0)
    h = sum(b[3] - b[1] for b in sizes) + gap * (len(lines) - 1) + 2 * pad
    img = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if box:
        d.rounded_rectangle((0, 0, w, h), radius=18, fill=box)
    if accent:
        d.rounded_rectangle((pad // 2, pad, pad // 2 + 7, h - pad), radius=3, fill=accent + (255,))
    y = pad
    for (t, f, color), b in zip(lines, sizes):
        x = pad + (14 if accent else 0) + (0 if box else (w - 2 * pad - (b[2] - b[0])) // 2)
        d.text((x - b[0], y - b[1]), t, font=f, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        y += b[3] - b[1] + gap
    return img


CAPTION_SIZE, CAPTION_STROKE = 92, 9
CAPTION_WIDTH = W - 160
BREAKS = ".,;:!?—।॥"
# An abbreviated initial: one or two letters with no vowel sign, then a dot ("एल.", "डी.", "J.").
INITIAL = re.compile(r"(?:[\u0900-\u0939\u0958-\u0961]{1,2}|[A-Za-z]{1,2})\.")


def _chunks(words: list[dict], width=None) -> list[list[dict]]:
    """Caption groups of up to three words that fit on one line, ending at punctuation (। included)."""
    width = width or (lambda text: len(text) * CAPTION_SIZE * 0.42)
    out, cur = [], []
    for w in words:
        if cur and width(" ".join(x["text"] for x in cur + [w])) > CAPTION_WIDTH:
            out.append(cur)
            cur = []
        cur.append(w)
        initial = bool(INITIAL.fullmatch(w["text"]))  # "एल." in "एल. मुरुगन" ends no sentence; "है." does
        if len(cur) >= 3 or (w["text"][-1:] in BREAKS and not initial):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


class Captions:
    def __init__(self, words: list[dict], accent: tuple, size: int = CAPTION_SIZE, y: float = CAPTION_Y,
                 stroke: int = CAPTION_STROKE):
        self.font = _font("ExtraBold", size)
        self.accent = accent
        self.y, self.stroke = y, stroke
        self.groups = []
        for chunk in _chunks(words, lambda text: self.font.getlength(text) + 2 * stroke):
            texts = [w["text"] for w in chunk]
            variants = [self._render(texts, k) for k in range(len(chunk))]
            self.groups.append({"start": chunk[0]["start"], "end": chunk[-1]["end"], "words": chunk,
                                "variants": variants})

    def _render(self, texts: list[str], active: int) -> tuple[np.ndarray, np.ndarray]:
        stroke = self.stroke
        space = self.font.getlength(" ")
        widths = [self.font.getlength(t) + 2 * stroke for t in texts]
        ascent, descent = self.font.getmetrics()
        total = int(sum(widths) + space * (len(texts) - 1)) + 24
        img = Image.new("RGBA", (total, ascent + descent + 2 * stroke + 16), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 12
        for i, (t, w) in enumerate(zip(texts, widths)):
            color = self.accent + (255,) if i == active else (255, 255, 255, 255)
            d.text((x + stroke, 8 + stroke), t, font=self.font, fill=color, stroke_width=stroke,
                   stroke_fill=(0, 0, 0, 255))
            x += w + space
        if img.width > W - 80:
            img = img.resize((W - 80, round(img.height * (W - 80) / img.width)), Image.LANCZOS)
        return _rgba(img)

    def draw(self, frame: np.ndarray, t: float) -> None:
        for g in self.groups:
            if g["start"] - 0.05 <= t < g["end"] + 0.12:
                k = max([i for i, w in enumerate(g["words"]) if w["start"] <= t + 0.03] or [0])
                layer = g["variants"][k]
                h, w = layer[1].shape[:2]
                pop = min(1.0, (t - g["start"] + 0.05) / 0.09)
                if pop < 1:
                    s = 0.9 + 0.1 * pop
                    rgb = cv2.resize(layer[0], (max(1, round(w * s)), max(1, round(h * s))))
                    a = cv2.resize(layer[1], (max(1, round(w * s)), max(1, round(h * s))))[..., None]
                    layer, (h, w) = (rgb, a), a.shape[:2]
                _blit(frame, layer, (W - w) // 2, round(H * self.y - h / 2))
                return


def _fit(weight: str, size: int, text: str, width: int, floor: int = 24) -> ImageFont.FreeTypeFont:
    font = _font(weight, size)
    while font.getlength(text) > width and font.size > floor:
        font = _font(weight, font.size - 3)
    return font


def _credit_layer(text: str) -> tuple[np.ndarray, np.ndarray]:
    font = _font("Medium", 26)
    text = drawable(text)
    while font.getlength(text) > W - 260 and len(text) > 20:
        cut = text.rstrip("…").rstrip()
        text = (cut.rsplit(" ", 1)[0] if " " in cut[10:] else cut[:-4]) + "…"
    return _rgba(_text_layer([(text, font, (255, 255, 255, 200))], stroke=2))


def _badge_layer() -> tuple[np.ndarray, np.ndarray]:
    return _rgba(_text_layer([(AI_BADGE, _font("Bold", 42), (255, 255, 255, 245))], pad=16, box=(10, 10, 14, 200)))


def _hook_layer(name: str, sub: str, accent: tuple) -> tuple[np.ndarray, np.ndarray]:
    lines = [(name, _fit("ExtraBold", 112, name, W - 120, 60), (255, 255, 255, 255))]
    if sub:
        lines.append((sub, _fit("Bold", 46, sub, W - 140), accent + (255,)))
    return _rgba(_text_layer(lines, stroke=6, gap=18))


def _question_layer(title: str, accent: tuple) -> tuple[np.ndarray, np.ndarray]:
    """The explainer's question as its opening card: big, on at most two lines, its last line in the accent."""
    rows = wrap2(title, "ExtraBold", 86, W - 120)
    lines = [(r, _fit("ExtraBold", 86, r, W - 120, 48), (255, 255, 255, 255) if n < len(rows) - 1 or len(rows) == 1
              else accent + (255,)) for n, r in enumerate(rows)]
    return _rgba(_text_layer(lines, stroke=6, gap=16))


def wrap2(text: str, weight: str, size: int, width: int) -> list[str]:
    """text on one line when it fits at `size`, else split into the two most even lines at a space."""
    font = _font(weight, size)
    if font.getlength(text) <= width or " " not in text:
        return [text]
    words = text.split()
    cuts = [(" ".join(words[:k]), " ".join(words[k:])) for k in range(1, len(words))]
    return list(min(cuts, key=lambda ab: max(font.getlength(ab[0]), font.getlength(ab[1]))))


# The kind of story, shown in the channel strip; an explainer shows its own category (राजनीति, अर्थव्यवस्था ...).
LABELS = {"death": "श्रद्धांजलि", "incident": "घटना", "protest": "प्रदर्शन", "advisory": "ज़रूरी सूचना",
          "explainer": "क्या और क्यों"}


def label_for(short: Short) -> str:
    if short.scene.get("category_hi"):
        return short.scene["category_hi"]
    if short.scene.get("category") in ("protest", "movement"):
        return LABELS["protest"]
    return LABELS.get(short.kind, "")


def _strip_layer(label: str, accent: tuple) -> tuple[np.ndarray, np.ndarray] | None:
    """The channel strip on every frame, the way a news channel brands its screen: name, then the story's kind."""
    name = config.NAME_HI or config.NAME
    if not name:
        return None
    lines = [(drawable(f"{name}  ·  {label}" if label else name, "ExtraBold"), _font("ExtraBold", 40),
              (255, 255, 255, 250))]
    return _rgba(_text_layer(lines, pad=14, box=(10, 10, 14, 190), accent=accent))


def sources_line(short: Short) -> str:
    """Where the facts come from, said on screen: the outlets whose reports back them, then Wikipedia."""
    names = list(dict.fromkeys((r.get("outlet_hi") or r.get("outlet")) for r in short.scene.get("reporting") or []
                               if r.get("outlet") or r.get("outlet_hi")))[:3]
    if any("wikipedia.org" in s for s in short.sources):
        names.append("Wikipedia")
    return "स्रोत: " + " · ".join(names) if names else ""


def _sources_layer(text: str) -> tuple[np.ndarray, np.ndarray]:
    text = drawable(text, "SemiBold")
    font = _fit("SemiBold", 38, text, W - 160)
    return _rgba(_text_layer([(text, font, (255, 255, 255, 240))], pad=14, box=(10, 10, 14, 175)))


PROGRESS_H = 9


def _progress(frame: np.ndarray, u: float, accent: tuple) -> None:
    """A thin bar along the top edge that fills as the Short plays."""
    frame[:PROGRESS_H] = (frame[:PROGRESS_H].astype(np.float32) * 0.45).astype(np.uint8)
    frame[:PROGRESS_H, :max(1, round(W * min(max(u, 0.0), 1.0)))] = accent


def _chip_layer(text: str, accent: tuple) -> tuple[np.ndarray, np.ndarray]:
    font = _fit("ExtraBold", 50, text, W - 220)
    return _rgba(_text_layer([(text, font, (255, 255, 255, 255))], pad=22, box=(10, 10, 14, 175), accent=accent))


def _end_layers(accent: tuple, disclosure: str = DISCLOSURE) -> list[tuple[np.ndarray, np.ndarray] | None]:
    """The end card: the channel's name (when it has one), where the sources are, and the disclosure."""
    name = config.NAME_HI or config.NAME
    logo = _rgba(_text_layer([(name, _fit("ExtraBold", 132, name, W - 140), accent + (255,))])) if name else None
    src = _rgba(_text_layer([("सभी स्रोत विवरण में", _font("SemiBold", 52), (255, 255, 255, 240))]))
    disc = _rgba(_text_layer([(disclosure, _fit("Medium", 34, disclosure, W - 120), (255, 255, 255, 215))]))
    return [logo, src, disc]


def _mix(narration: Path, short: Short, seconds: float, out: Path, accents: list[float] | None = None) -> Path:
    import soundfile as sf

    bed = music.score(seconds + 0.5, short.scene.get("mood", "tribute"), short.id)
    sf.write(out / "music.wav", bed, music.SR)
    inputs = ["-i", str(narration), "-i", str(out / "music.wav")]
    fx, layers = "", "[v][duck]"
    if accents is not None:
        sf.write(out / "accents.wav", music.accents(seconds + 0.5, accents, short.id), music.SR)
        inputs += ["-i", str(out / "accents.wav")]
        fx, layers = "[2:a]aresample=48000,volume=0.14[fx];", "[v][duck][fx]"
    mixed = out / "mix.wav"
    graph = ("[0:a]aresample=48000,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,"
             "volume=1.0,asplit=2[v][key];"
             "[1:a]aresample=48000,volume=0.30[m];"
             "[m][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];" + fx +
             f"{layers}amix=inputs={len(inputs) // 2}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9,"
             f"apad,atrim=0:{seconds:.3f}[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]",
                    "-ar", "48000", "-ac", "2", str(mixed)], check=True)
    return mixed


def render(short: Short, timing: dict, work: Path) -> dict:
    """short.mp4 (1080x1920, 30 fps, H.264 + AAC) and a few stills."""
    if short.scene.get("template") == "bulletin":
        return render_bulletin(short, timing, work)
    mood = short.scene.get("mood", "tribute")
    accent = ACCENT.get(mood, ACCENT["tribute"])
    photos = short.scene["photos"]
    plates = {}
    for i, p in enumerate(photos):
        plates[i] = Plate(p, Path(p["path"]).with_suffix(".depth.npy"))
    cam, grade = Camera(), Grade(mood, seed=len(short.id))
    captions = Captions(timing["words"], accent)
    duration = timing["duration"] + 0.6
    spans = timing["beats"]
    shots = []
    for i, (beat, (s, e)) in enumerate(zip(short.beats, spans)):
        idx = (shot_photos(beat.shot) or [None])[0]
        if idx is None or idx not in plates:
            idx = shots[-1]["photo"] if shots else 0
        shots.append({"photo": idx, "start": s if i else 0.0, "end": e if i < len(spans) - 1 else duration,
                      "motion": MOTIONS[i % len(MOTIONS)], "beat": beat, "outro": beat.shot == "outro"})
    chips = [_chip_layer(b["beat"].card["big"], accent) if b["beat"].card and b["beat"].card.get("big") and i > 0
             and not b["outro"] else None for i, b in enumerate(shots)]
    name = short.scene.get("name_hi") or next((f.value for f in short.facts if f.key == "name"), short.title)
    if short.kind == "death":
        years = {f.key: f.value[-4:] for f in short.facts if f.key in ("born", "died")}
        sub = f"{years['born']} – {years['died']}" if len(years) == 2 else ""
    else:
        sub = shots[0]["beat"].card.get("big", "") if shots[0]["beat"].card else ""
    # An explainer's hook is its own question, which already names its centre.
    hook = _question_layer(short.title, accent) if short.kind == "explainer" else _hook_layer(name, sub, accent)
    strip = _strip_layer(label_for(short), accent)
    said = sources_line(short)
    sources = _sources_layer(said) if said else None
    credits = {i: _credit_layer(p["credit"]) for i, p in enumerate(photos)}
    end = _end_layers(accent, disclosure(photos))
    badge = _badge_layer()
    work.mkdir(parents=True, exist_ok=True)
    mixed = _mix(work / "narration.wav", short, duration, work)
    out = work / "short.mp4"
    stills = work / "stills"
    stills.mkdir(exist_ok=True)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(mixed), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    n = int(math.ceil(duration * FPS))
    still_at = {int(n * k / 5) for k in range(5)}
    for i in range(n):
        t = i / FPS
        k = next(j for j, s in enumerate(shots) if t < s["end"] or j == len(shots) - 1)
        shot = shots[k]
        u = (t - shot["start"]) / max(shot["end"] - shot["start"], 0.1)
        punch = 0.035 * max(0.0, 1 - (t - shot["start"]) / 0.35) if k else 0.06 * max(0.0, 1 - t / 0.6)
        frame = cam.shoot(plates[shot["photo"]], u, shot["motion"], punch)
        if k and (t - shot["start"]) * FPS < CROSSFADE:
            prev = shots[k - 1]
            pu = (t - prev["start"]) / max(prev["end"] - prev["start"], 0.1)
            a = (t - shot["start"]) * FPS / CROSSFADE
            frame = cv2.addWeighted(frame, a, cam.shoot(plates[prev["photo"]], pu, prev["motion"]), 1 - a, 0)
        if shot["outro"]:
            fade = min(1.0, (t - shot["start"]) / 0.5)
            frame = cv2.addWeighted(cv2.GaussianBlur(frame, (0, 0), 18), 0.55 * fade, frame, 1 - 0.55 * fade - 0.25 * fade, 0)
        frame = grade.apply(frame, i)
        if k == 0:
            # Fully visible from the first frame: YouTube may use it as the cover.
            _blit(frame, hook, (W - hook[1].shape[1]) // 2, round(H * 0.085))
            if sources is not None:
                _blit(frame, sources, (W - sources[1].shape[1]) // 2,
                      round(H * 0.085) + hook[1].shape[0] + 26, min(1.0, t / 0.3))
        elif chips[k] is not None:
            a = min(1.0, (t - shot["start"]) / 0.25)
            _blit(frame, chips[k], 48, round(H * 0.095), a)
        if shot["outro"]:
            a = min(1.0, (t - shot["start"]) / 0.4)
            logo, src, disc = end
            if logo is not None:
                _blit(frame, logo, (W - logo[1].shape[1]) // 2, round(H * 0.29), a)
            _blit(frame, src, (W - src[1].shape[1]) // 2, round(H * 0.40), a)
            _blit(frame, disc, (W - disc[1].shape[1]) // 2, round(H * 0.45), a)
        else:
            cr = credits[shot["photo"]]
            _blit(frame, cr, 36, round(H * 0.785), 0.9)
        _blit(frame, badge, 36, round(H * 0.732), 0.97)
        if strip is not None and not shot["outro"]:
            _blit(frame, strip, 36, round(H * 0.022), 0.96)
        _progress(frame, t / duration, accent)
        captions.draw(frame, t)
        enc.stdin.write(frame.tobytes())
        if i in still_at:
            Image.fromarray(frame).save(stills / f"t{i // FPS:03d}.png")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the Short")
    return {"duration": round(duration, 2), "frames": n, "template": "story", "photos": len(photos),
            "fps": FPS, "size": [W, H]}


# The news bulletin (owner, 2026-10-14: "it really doesn't look like a news report, no facts nothing is shown"): a TV
# news screen. A channel bar with the date, the photo in a window over a blurred copy of itself, a headline bar naming
# the sources, a fact card for every beat (its sourced number or decision, what it is, and who reports it), subtitles,
# a ticker of the story's facts, and a "मुख्य तथ्य" recap at the end. Every word on screen is the gated title, a gated
# card or the narration itself.
NEWS_RED = (200, 28, 44)
NEWS_NAVY = (10, 20, 46)
NEWS_GOLD = (255, 200, 70)
WIN_Y, WIN_H = 140, 880
HEAD_Y = WIN_Y + WIN_H
CARD_X, CARD_GAP = 40, 34
SUB_Y = 0.842
BADGE_Y = 1700
TICKER_H = 72
TICKER_Y = H - TICKER_H - 14
TICKER_SPEED = 150  # px a second
NEWS_LABEL = "समाचार"
FILE_PHOTO = "फ़ाइल फ़ोटो"
RECAP = "मुख्य तथ्य"
IST = timezone(timedelta(hours=5, minutes=30))


def _center(d: ImageDraw.ImageDraw, box: tuple, text: str, font: ImageFont.FreeTypeFont, fill: tuple) -> None:
    x0, y0, x1, y1 = box
    b = font.getbbox(text)
    d.text((x0 + (x1 - x0 - (b[2] - b[0])) / 2 - b[0], y0 + (y1 - y0 - (b[3] - b[1])) / 2 - b[1]), text, font=font,
           fill=fill)


def _pill(text: str, font: ImageFont.FreeTypeFont, fill: tuple, color=(255, 255, 255, 255), pad: int = 18,
          height: int = 72) -> Image.Image:
    text = drawable(text, "ExtraBold")
    img = Image.new("RGBA", (round(font.getlength(text)) + 2 * pad, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, height - 1), radius=10, fill=fill)
    _center(d, (0, 0, img.width, height), text, font, color)
    return img


def event_day(short: Short) -> date | None:
    try:
        return date.fromisoformat((short.event_time or "")[:10])
    except ValueError:
        return None


def _topbar_layer(label: str, when: date | None, fresh: bool) -> tuple[np.ndarray, np.ndarray]:
    """The channel bar: the story's kind in red, the channel's name, ताज़ा for today's news, and the date."""
    name = config.NAME_HI or config.NAME or ""
    bar = Image.new("RGBA", (W - 72, 76), (0, 0, 0, 0))
    x = 0
    for text, fill, color in ((label or NEWS_LABEL, NEWS_RED + (255,), (255, 255, 255, 255)),
                              (name, NEWS_NAVY + (235,), (255, 255, 255, 255)),
                              ("ताज़ा" if fresh else "", NEWS_GOLD + (255,), NEWS_NAVY + (255,))):
        if not text:
            continue
        pill = _pill(text, _font("ExtraBold", 40), fill, color, height=76)
        bar.alpha_composite(pill, (x, 0))
        x += pill.width + 14
    if when:
        pill = _pill(hindi.date_hi(when), _font("SemiBold", 34), (0, 0, 0, 165), height=64)
        if x + pill.width <= bar.width:
            bar.alpha_composite(pill, (bar.width - pill.width, 6))
    return _rgba(bar)


def _headline_layer(title: str, sources: str) -> tuple[np.ndarray, np.ndarray]:
    """The headline bar under the photo: the title on at most two lines, then where the facts come from."""
    title = drawable(title, "ExtraBold")
    rows = wrap2(title, "ExtraBold", 64, W - 110)
    fonts = [_fit("ExtraBold", 64, r, W - 110, 38) for r in rows]
    src = drawable(sources, "SemiBold") if sources else ""
    f_src = _fit("SemiBold", 34, src, W - 110, 24) if src else None
    tall = [f.getbbox(r)[3] - f.getbbox(r)[1] for f, r in zip(fonts, rows)]
    h = 36 + sum(tall) + 18 * (len(rows) - 1) + (26 + 38 if src else 0) + 30
    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, h), fill=NEWS_NAVY + (240,))
    d.rectangle((0, 0, W, 8), fill=NEWS_RED + (255,))
    d.rectangle((0, 8, 12, h), fill=NEWS_GOLD + (255,))
    y = 36
    for r, f, t in zip(rows, fonts, tall):
        b = f.getbbox(r)
        d.text((48 - b[0], y - b[1]), r, font=f, fill=(255, 255, 255, 255))
        y += t + 18
    if src:
        b = f_src.getbbox(src)
        d.text((48 - b[0], y + 8 - b[1]), src, font=f_src, fill=NEWS_GOLD + (255,))
    return _rgba(img)


def card_sources(short: Short, card: dict) -> str:
    """The outlets whose reports state the card's number ("स्रोत: बीबीसी · द हिंदू"), or '' when no outlet fact backs
    it (the headline bar already names the Short's sources)."""
    outlet = {}
    for r in short.scene.get("reporting") or []:
        outlet.setdefault(r.get("owner"), r.get("outlet_hi") or r.get("outlet"))
    nums = {v for v, _ in hindi.numbers(f"{card.get('big', '')} {card.get('small', '')}")}
    owners = [o for f in short.facts if f.owners and set(f.numbers) & nums for o in f.owners]
    names = [outlet[o] for o in dict.fromkeys(owners) if outlet.get(o)][:3]
    return "स्रोत: " + " · ".join(names) if names else ""


def _fact_layer(value: str, label: str, who: str) -> tuple[np.ndarray, np.ndarray]:
    """A beat's fact card: the sourced value large, what it is, and who reports it."""
    value, label, who = drawable(value, "ExtraBold"), drawable(label, "Bold"), drawable(who, "Medium")
    width = W - 2 * CARD_X - 90
    parts = [(value, _fit("ExtraBold", 92, value, width, 44), NEWS_GOLD)]
    if label:
        parts.append((label, _fit("Bold", 46, label, width, 28), (255, 255, 255)))
    if who:
        parts.append((who, _fit("Medium", 30, who, width, 22), (196, 208, 232)))
    tall = [f.getbbox(t)[3] - f.getbbox(t)[1] for t, f, _ in parts]
    w = round(max(f.getlength(t) for t, f, _ in parts)) + 92
    h = 30 + sum(tall) + 16 * (len(parts) - 1) + 30
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=22, fill=(8, 14, 32, 228))
    d.rounded_rectangle((0, 0, 14, h - 1), radius=7, fill=NEWS_RED + (255,))
    y = 30
    for (t, f, c), th in zip(parts, tall):
        b = f.getbbox(t)
        d.text((50 - b[0], y - b[1]), t, font=f, fill=c + (255,))
        y += th + 16
    return _rgba(img)


def facts_on_screen(short: Short) -> list[tuple[str, str]]:
    """(value, label) of every beat's card, in order, each value once."""
    rows = [((b.card or {}).get("big", "").strip(), (b.card or {}).get("small", "").strip()) for b in short.beats
            if b.shot != "outro"]
    first = {}
    for value, label in rows:
        if value:
            first.setdefault(value, label)
    return list(first.items())


class Ticker:
    """The bottom strip: "मुख्य तथ्य" in red, then the story's facts scrolling right to left."""

    def __init__(self, facts: list[tuple[str, str]]):
        self.label = _rgba(_pill(RECAP, _font("ExtraBold", 36), NEWS_RED + (255,), height=TICKER_H))
        text = "     •     ".join(f"{label}: {value}" if label else value for value, label in facts)
        self.text = None
        if text:
            font = _font("SemiBold", 38)
            text = drawable(text + "     •     ", "SemiBold")
            img = Image.new("RGBA", (round(font.getlength(text)) + 8, TICKER_H), (0, 0, 0, 0))
            _center(ImageDraw.Draw(img), (0, 0, img.width, TICKER_H), text, font, (255, 255, 255, 255))
            self.text = _rgba(img)

    def draw(self, frame: np.ndarray, t: float) -> None:
        band = frame[TICKER_Y:TICKER_Y + TICKER_H].astype(np.float32)
        frame[TICKER_Y:TICKER_Y + TICKER_H] = (band * 0.12 + np.array(NEWS_NAVY, np.float32) * 0.88).astype(np.uint8)
        x0 = self.label[1].shape[1] + 16
        if self.text is not None:
            period = self.text[1].shape[1]
            x = x0 - (t * TICKER_SPEED) % period
            while x < W:
                _blit(frame, self.text, round(x), TICKER_Y)
                x += period
        _blit(frame, self.label, 0, TICKER_Y)


def _recap_layer(facts: list[tuple[str, str]]) -> tuple[np.ndarray, np.ndarray] | None:
    """The end card's "मुख्य तथ्य": up to four of the Short's facts, value over label."""
    facts = facts[:4]
    if not facts:
        return None
    width = W - 160
    head = _font("ExtraBold", 62)
    rows = [(drawable(v, "ExtraBold"), drawable(lbl, "SemiBold")) for v, lbl in facts]
    fonts = [(_fit("ExtraBold", 58, v, width - 60, 34), _fit("SemiBold", 38, lbl, width - 60, 24) if lbl else None)
             for v, lbl in rows]
    tall = [(fv.getbbox(v)[3] - fv.getbbox(v)[1], (fl.getbbox(lbl)[3] - fl.getbbox(lbl)[1]) if fl else 0)
            for (v, lbl), (fv, fl) in zip(rows, fonts)]
    h = 60 + 70 + sum(a + b + (12 if b else 0) + 40 for a, b in tall) + 20
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, width - 1, h - 1), radius=26, fill=(8, 14, 32, 232))
    d.rectangle((0, 0, width, 10), fill=NEWS_RED + (255,))
    b = head.getbbox(RECAP)
    d.text((44 - b[0], 44 - b[1]), RECAP, font=head, fill=NEWS_GOLD + (255,))
    y = 60 + 70
    for (v, lbl), (fv, fl), (a, bb) in zip(rows, fonts, tall):
        d.ellipse((44, y + a / 2 - 8, 60, y + a / 2 + 8), fill=NEWS_RED + (255,))
        g = fv.getbbox(v)
        d.text((84 - g[0], y - g[1]), v, font=fv, fill=(255, 255, 255, 255))
        y += a
        if fl:
            g = fl.getbbox(lbl)
            d.text((84 - g[0], y + 12 - g[1]), lbl, font=fl, fill=(196, 208, 232, 255))
            y += bb + 12
        y += 40
    return _rgba(img)


def _backdrop(window: np.ndarray) -> np.ndarray:
    """The whole frame behind the window: a dark, blurred copy of the photo."""
    small = cv2.resize(window, (W // 8, WIN_H // 8), interpolation=cv2.INTER_AREA)
    cw = round(small.shape[0] * W / H)
    x0 = (small.shape[1] - cw) // 2
    small = cv2.GaussianBlur(cv2.resize(small[:, x0:x0 + cw], (W // 8, H // 8)), (0, 0), 5)
    big = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    return (big * 0.34 + np.array(NEWS_NAVY, np.float32) * 0.4).astype(np.uint8)


def _slide(t: float, start: float, dur: float = 0.3) -> float:
    return _ease((t - start) / dur)


CUT_AFTER = 3.4  # seconds: a longer beat cuts to its second picture, so the picture changes every few seconds
TIGHT = {"z": (1.24, 1.32), "dz": (0.02, 0.03), "pan": (0, 0, 0, -12), "par": (0, 0)}  # the same photo, closer
MAP_TAG = "नक्शा"


def views(shots: list[dict], words: list[dict]) -> list[dict]:
    """The pictures on screen in order. A beat longer than CUT_AFTER cuts, at the word nearest its middle, to its
    second picture (shot["views"]), or to the same photo closer when it has none."""
    out = []
    for k, shot in enumerate(shots):
        if shot["outro"] or shot["end"] - shot["start"] < CUT_AFTER:
            out.append(shot | {"beat_k": k, "cut": False})
            continue
        mid = (shot["start"] + shot["end"]) / 2
        starts = [w["start"] for w in words if shot["start"] + 1.2 < w["start"] < shot["end"] - 1.2]
        at = min(starts, key=lambda s: abs(s - mid)) if starts else mid
        alt = (shot.get("views") or [])[1:2]
        photo = alt[0] if alt else shot["photo"]
        motion = TIGHT if photo == shot["photo"] else MOTIONS[(k + 2) % len(MOTIONS)]
        out += [shot | {"end": at, "beat_k": k, "cut": False},
                shot | {"photo": photo, "start": at, "motion": motion, "beat_k": k, "cut": True}]
    return out


def _name_layer(name: str) -> tuple[np.ndarray, np.ndarray]:
    """Who a photo shows, on it: viewers must never take someone else for the story's person."""
    return _rgba(_pill(name, _font("ExtraBold", 40), NEWS_RED + (240,), height=62, pad=20))


# From the study of successful news Shorts (2026-10-20: BBC Hindi, DW Hindi, Al Jazeera, AJ+, RealLifeLore and 11
# more; owner: "take reference of famous AI news channels ... add some positive skills while video editing"). A
# hook card over the picture from the first frame (10 of 16 channels; a statement, never a question: the bulletin
# asks none), a place stamp in the picture's corner (BBC Hindi, DW, Al Jazeera), a one-second flash of the Short's
# pictures (AJ+, VisualPolitik bursts), and an end card that asks the viewer to follow (Al Jazeera, DW).
HOOK_HOLD = 3.6  # seconds the hook card stays over the picture (the study: 4-7 s, read before the first cut)
BURST_STEP, BURST_MAX, BURST_MIN = 0.18, 5, 3  # the opening flash: up to five pictures, a fifth of a second each
FOLLOW = "हर अपडेट के लिए चैनल फ़ॉलो करें"


def _hookcard_layer(text: str) -> tuple[np.ndarray, np.ndarray]:
    """The opening line over the picture: dark text on a white box with a solid red offset shadow (BBC)."""
    text = drawable(text, "ExtraBold")
    width = W - 260
    rows = wrap2(text, "ExtraBold", 70, width)
    fonts = [_fit("ExtraBold", 70, r, width, 40) for r in rows]
    tall = [f.getbbox(r)[3] - f.getbbox(r)[1] for f, r in zip(fonts, rows)]
    bw = max(round(f.getlength(r)) for f, r in zip(fonts, rows)) + 64
    bh = sum(tall) + 22 * (len(rows) - 1) + 60
    off = 14
    img = Image.new("RGBA", (bw + off, bh + off), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((off, off, bw + off - 1, bh + off - 1), fill=NEWS_RED + (255,))
    d.rectangle((0, 0, bw - 1, bh - 1), fill=(255, 255, 255, 250))
    y = 30
    for r, f, t in zip(rows, fonts, tall):
        b = f.getbbox(r)
        d.text((32 - b[0], y - b[1]), r, font=f, fill=NEWS_NAVY + (255,))
        y += t + 22
    return _rgba(img)


def _place_layer(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Where the story is, pinned in the picture's top corner."""
    text = drawable(text, "ExtraBold")
    font, h, pad, dot = _font("ExtraBold", 36), 60, 18, 18
    img = Image.new("RGBA", (round(font.getlength(text)) + 2 * pad + dot + 14, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, h - 1), radius=10, fill=NEWS_RED + (240,))
    cy = h // 2
    d.ellipse((pad, cy - dot // 2, pad + dot, cy + dot // 2), fill=(255, 255, 255, 255))
    d.ellipse((pad + 6, cy - 3, pad + dot - 6, cy + 3), fill=NEWS_RED + (255,))
    b = font.getbbox(text)
    d.text((pad + dot + 14 - b[0], (h - (b[3] - b[1])) / 2 - b[1]), text, font=font, fill=(255, 255, 255, 255))
    return _rgba(img)


def places_on(seen: list[dict], photos: list[dict]) -> list[tuple[float, str]]:
    """[(from when, place)] for the place stamp: the first place a map or landmark photo shows, from the start, then
    each new one as it comes on screen (a route's stamp is where it ends). "जुहू, मुंबई" never gives way to the
    "मुंबई" or "जुहू" it already names."""
    out: list[tuple[float, str]] = []
    for v in seen:
        p = photos[v["photo"]]
        where = (p.get("who") or "").split(" - ")[-1].strip() if p.get("role") in ("map", "place") else ""
        if where and (not out or where not in [s.strip() for s in out[-1][1].split(",")] + [out[-1][1]]):
            out.append((v["start"], where))
    return [(0.0, out[0][1])] + out[1:] if out else []


def burst(seen: list[dict], photos: list[dict]) -> list[int]:
    """The opening flash: the Short's other pictures in the order they come, maps and portraits alike, or [] when
    there are too few to make one."""
    first = seen[0]["photo"] if seen else None
    pics = [i for i in dict.fromkeys(v["photo"] for v in seen if not v.get("outro")) if i != first and i in
            range(len(photos))][:BURST_MAX]
    return pics if len(pics) >= BURST_MIN else []


def render_bulletin(short: Short, timing: dict, work: Path) -> dict:
    """The news-bulletin Short (see the comment above NEWS_RED)."""
    mood = short.scene.get("mood", "news")
    accent = NEWS_GOLD
    photos = short.scene["photos"]
    size = (W, WIN_H)
    plates = {i: Plate(p, Path(p["path"]).with_suffix(".depth.npy"), size=size, face_share=0.3)
              for i, p in enumerate(photos)}
    cam, grade = Camera(size), Grade(mood, seed=len(short.id), size=size, bands=False)
    captions = Captions(timing["words"], accent, size=66, y=SUB_Y, stroke=7)
    duration = timing["duration"] + 0.6
    spans = timing["beats"]
    shots = []
    for i, (beat, (s, e)) in enumerate(zip(short.beats, spans)):
        shown = [p for p in shot_photos(beat.shot) if p in plates]
        idx = shown[0] if shown else (shots[-1]["photo"] if shots else 0)
        shots.append({"photo": idx, "views": shown or [idx], "start": s if i else 0.0,
                      "end": e if i < len(spans) - 1 else duration, "motion": MOTIONS[i % len(MOTIONS)],
                      "beat": beat, "outro": beat.shot == "outro"})
    seen = views(shots, timing["words"])
    cards = [_fact_layer(b["beat"].card["big"], b["beat"].card.get("small", ""), card_sources(short, b["beat"].card))
             if b["beat"].card and b["beat"].card.get("big") and not b["outro"] else None for b in shots]
    big = [(b["beat"].card or {}).get("big", "").strip() for b in shots]
    held = [k > 0 and cards[k] is not None and cards[k - 1] is not None and big[k] == big[k - 1]
            for k in range(len(shots))]
    for k in range(1, len(shots)):
        if held[k]:
            cards[k] = cards[k - 1]
    day = event_day(short)
    fresh = day is not None and day == datetime.now(IST).date()
    top = _topbar_layer(label_for(short) or NEWS_LABEL, day, fresh)
    headline = _headline_layer(short.title, sources_line(short))
    facts = facts_on_screen(short)
    ticker = Ticker(facts)
    recap = _recap_layer(facts)
    credits = {i: _credit_layer(p["credit"]) for i, p in enumerate(photos)}
    file_tag, map_tag = (_rgba(_pill(t, _font("Bold", 30), (0, 0, 0, 170), height=48, pad=14))
                         for t in (FILE_PHOTO, MAP_TAG))
    tags = {i: map_tag if p.get("role") == "map" else file_tag for i, p in enumerate(photos)}
    names = {i: _name_layer(p["who"]) for i, p in enumerate(photos) if p.get("who") and p.get("role") != "map"}
    end = _end_layers(accent, disclosure(photos))
    follow = _rgba(_pill(FOLLOW, _font("ExtraBold", 46), NEWS_GOLD + (255,), NEWS_NAVY + (255,), height=80, pad=26))
    badge = _badge_layer()
    card_y = HEAD_Y + headline[1].shape[0] + CARD_GAP
    hook = _hookcard_layer(short.scene["hook"]) if short.scene.get("hook") else None
    stamps = [(at, _place_layer(where)) for at, where in places_on(seen, photos)]
    flash = [] if short.loss else burst(seen, photos)
    flash_end = len(flash) * BURST_STEP
    work.mkdir(parents=True, exist_ok=True)
    accents = None if short.loss else [s["start"] for s in shots[1:]] + ([flash_end] if flash else [])
    mixed = _mix(work / "narration.wav", short, duration, work, accents)
    out = work / "short.mp4"
    stills = work / "stills"
    stills.mkdir(exist_ok=True)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(mixed), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    n = int(math.ceil(duration * FPS))
    still_at = {int(n * k / 5) for k in range(5)}
    for i in range(n):
        t = i / FPS
        v = next(j for j, s in enumerate(seen) if t < s["end"] or j == len(seen) - 1)
        view = seen[v]
        k = view["beat_k"]
        shot = shots[k]
        u = (t - view["start"]) / max(view["end"] - view["start"], 0.1)
        punch = 0.03 * max(0.0, 1 - (t - view["start"]) / 0.35) if v else 0.06 * max(0.0, 1 - (t - flash_end) / 0.6)
        if t < flash_end:
            on = flash[int(t / BURST_STEP)]
            win = cam.shoot(plates[on], 0.0, MOTIONS[on % len(MOTIONS)], 0.05)
        else:
            win = cam.shoot(plates[view["photo"]], u, view["motion"], punch)
            on = view["photo"]  # the picture the tag, name and credit belong to
        if v and not view["cut"] and (t - view["start"]) * FPS < CROSSFADE:
            prev = seen[v - 1]
            pu = (t - prev["start"]) / max(prev["end"] - prev["start"], 0.1)
            a = (t - view["start"]) * FPS / CROSSFADE
            win = cv2.addWeighted(win, a, cam.shoot(plates[prev["photo"]], pu, prev["motion"]), 1 - a, 0)
            on = view["photo"] if a >= 0.5 else prev["photo"]
        win = grade.apply(win, i)
        frame = _backdrop(win)
        if shot["outro"]:
            fade = min(1.0, (t - shot["start"]) / 0.5)
            frame = cv2.addWeighted(frame, 1 - 0.4 * fade, np.zeros_like(frame), 0.4 * fade, 0)
            a = min(1.0, (t - shot["start"]) / 0.4)
            logo, src, disc = end
            block = ((recap[1].shape[0] + 70) if recap is not None else 0) + \
                ((logo[1].shape[0] + 30) if logo is not None else 0) + src[1].shape[0] + 24 + disc[1].shape[0] + \
                40 + follow[1].shape[0]
            y = max(WIN_Y + 40, (TICKER_Y - block) // 2)
            if recap is not None:
                _blit(frame, recap, (W - recap[1].shape[1]) // 2, y, a)
                y += recap[1].shape[0] + 70
            if logo is not None:
                _blit(frame, logo, (W - logo[1].shape[1]) // 2, y, a)
                y += logo[1].shape[0] + 30
            _blit(frame, follow, (W - follow[1].shape[1]) // 2, y, a)
            y += follow[1].shape[0] + 40
            _blit(frame, src, (W - src[1].shape[1]) // 2, y, a)
            _blit(frame, disc, (W - disc[1].shape[1]) // 2, y + src[1].shape[0] + 24, a)
        else:
            frame[WIN_Y:WIN_Y + WIN_H] = win
            tag = tags[on]
            _blit(frame, tag, W - tag[1].shape[1] - 24, WIN_Y + 20, 0.95)
            if on in names:
                _blit(frame, names[on], 24, WIN_Y + WIN_H - 128)
            _blit(frame, credits[on], 24, WIN_Y + WIN_H - 50, 0.9)
            # Only over a map or a place's photo: over a portrait it would put Tiger Shroff in Begusarai.
            stamp = next((s for at, s in reversed(stamps) if t >= at), None)
            if stamp is not None and t >= flash_end and photos[on].get("role") in ("map", "place"):
                _blit(frame, stamp, 24, WIN_Y + 20, min(0.97, (t - max(flash_end, view["start"])) / 0.3))
            if hook is not None and t < HOOK_HOLD:
                a = min(1.0, t / 0.2, (HOOK_HOLD - t) / 0.3)
                _blit(frame, hook, (W - hook[1].shape[1]) // 2, WIN_Y + WIN_H - hook[1].shape[0] - 160, a)
            _blit(frame, headline, 0, HEAD_Y)
            if cards[k] is not None:
                e = _slide(t, shot["start"]) if k and not held[k] else 1.0
                cw = cards[k][1].shape[1]
                _blit(frame, cards[k], round(CARD_X - (1 - e) * (cw + CARD_X)), card_y, e)
        _blit(frame, top, 36, 40, 0.97)
        _blit(frame, badge, 36, BADGE_Y, 0.97)
        ticker.draw(frame, t)
        _progress(frame, t / duration, NEWS_RED)
        captions.draw(frame, t)
        enc.stdin.write(frame.tobytes())
        if i in still_at:
            Image.fromarray(frame).save(stills / f"t{i // FPS:03d}.png")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the Short")
    return {"duration": round(duration, 2), "frames": n, "template": "bulletin", "photos": len(photos),
            "fps": FPS, "size": [W, H]}
