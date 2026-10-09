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
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from . import config, depth, music
from .spec import Short

W, H, FPS = 1080, 1920, 30
MARGIN = 1.16  # the photo plate is larger than the frame so the camera can move
FONTS = Path(__file__).resolve().parent / "fonts"
WEIGHTS = {"ExtraBold": "Mukta-ExtraBold.ttf", "Bold": "Mukta-Bold.ttf", "SemiBold": "Mukta-SemiBold.ttf",
           "Medium": "Mukta-Medium.ttf"}
DISCLOSURE = "असली तस्वीरें: Wikimedia Commons · आवाज़: AI"
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
    """One photo prepared for camera moves: RGB and depth at plate size."""

    def __init__(self, photo: dict, cache: Path):
        img = Image.open(photo["path"]).convert("RGB")
        dep = depth.estimate(img, cache)
        pw, ph = round(W * MARGIN), round(H * MARGIN)
        iw, ih = img.size
        focus = photo.get("focus")
        if focus or iw / ih <= 0.9:
            if focus:
                fx, fy, fw, fh = focus
                cx, cy = fx + fw / 2, fy + fh / 2
                # Face about a sixth of the frame height, but never crop below 900 px (upscaling turns to mush).
                ch = min(ih, max(fh / 0.17, min(ih, 900)))
            else:
                cx, cy, ch = iw / 2, ih * 0.42, ih
            cw = ch * 9 / 16
            if cw > iw:
                cw, ch = iw, iw * 16 / 9
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
    def __init__(self):
        gx, gy = np.meshgrid(np.arange(W, dtype=np.float32) - W / 2, np.arange(H, dtype=np.float32) - H / 2)
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
    def __init__(self, mood: str, seed: int):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)
        vignette = np.clip(1.08 - 0.55 * r ** 2.2, 0.35, 1.0)
        # Darken behind the captions and the top chips so white text always reads.
        band = 1 - 0.32 * np.exp(-((yy - H * CAPTION_Y) / (H * 0.09)) ** 2) - 0.25 * np.exp(-((yy - H * 0.1) / (H * 0.07)) ** 2)
        self.mask = (vignette * band)[..., None].astype(np.float32)
        self.tint = np.array([1.04, 1.0, 0.93] if mood == "tribute" else [0.97, 1.0, 1.04], np.float32)
        self.sat = 0.85 if mood == "tribute" else 0.95
        rng = np.random.default_rng(seed)
        self.grain = [rng.normal(0, 5.0, (H // 2, W // 2, 1)).astype(np.float32) for _ in range(4)]

    def apply(self, frame: np.ndarray, i: int) -> np.ndarray:
        f = frame.astype(np.float32)
        gray = f.mean(axis=2, keepdims=True)
        f = gray + (f - gray) * self.sat
        f = (f - 128) * 1.06 + 128
        f = f * self.tint * self.mask
        g = cv2.resize(self.grain[i % 4], (W, H), interpolation=cv2.INTER_NEAREST)[..., None]
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


def _chunks(words: list[dict], width=None) -> list[list[dict]]:
    """Caption groups of up to three words that fit on one line, ending at punctuation (। included)."""
    width = width or (lambda text: len(text) * CAPTION_SIZE * 0.42)
    out, cur = [], []
    for w in words:
        if cur and width(" ".join(x["text"] for x in cur + [w])) > CAPTION_WIDTH:
            out.append(cur)
            cur = []
        cur.append(w)
        if len(cur) >= 3 or w["text"][-1:] in BREAKS:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


class Captions:
    def __init__(self, words: list[dict], accent: tuple):
        self.font = _font("ExtraBold", CAPTION_SIZE)
        self.accent = accent
        self.groups = []
        for chunk in _chunks(words, lambda text: self.font.getlength(text) + 2 * CAPTION_STROKE):
            texts = [w["text"] for w in chunk]
            variants = [self._render(texts, k) for k in range(len(chunk))]
            self.groups.append({"start": chunk[0]["start"], "end": chunk[-1]["end"], "words": chunk,
                                "variants": variants})

    def _render(self, texts: list[str], active: int) -> tuple[np.ndarray, np.ndarray]:
        stroke = CAPTION_STROKE
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
                _blit(frame, layer, (W - w) // 2, round(H * CAPTION_Y - h / 2))
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
        text = text[:-4] + "…"
    return _rgba(_text_layer([(text, font, (255, 255, 255, 200))], stroke=2))


def _badge_layer() -> tuple[np.ndarray, np.ndarray]:
    return _rgba(_text_layer([(AI_BADGE, _font("Bold", 30), (255, 255, 255, 235))], pad=12, box=(10, 10, 14, 165)))


def _hook_layer(name: str, sub: str, accent: tuple) -> tuple[np.ndarray, np.ndarray]:
    lines = [(name, _fit("ExtraBold", 112, name, W - 120, 60), (255, 255, 255, 255))]
    if sub:
        lines.append((sub, _fit("Bold", 46, sub, W - 140), accent + (255,)))
    return _rgba(_text_layer(lines, stroke=6, gap=18))


def _chip_layer(text: str, accent: tuple) -> tuple[np.ndarray, np.ndarray]:
    font = _fit("ExtraBold", 50, text, W - 220)
    return _rgba(_text_layer([(text, font, (255, 255, 255, 255))], pad=22, box=(10, 10, 14, 175), accent=accent))


def _end_layers(accent: tuple) -> list[tuple[np.ndarray, np.ndarray] | None]:
    """The end card: the channel's name (when it has one), where the sources are, and the disclosure."""
    name = config.NAME_HI or config.NAME
    logo = _rgba(_text_layer([(name, _fit("ExtraBold", 132, name, W - 140), accent + (255,))])) if name else None
    src = _rgba(_text_layer([("सभी स्रोत विवरण में", _font("SemiBold", 52), (255, 255, 255, 240))]))
    disc = _rgba(_text_layer([(DISCLOSURE, _fit("Medium", 34, DISCLOSURE, W - 120), (255, 255, 255, 215))]))
    return [logo, src, disc]


def _mix(narration: Path, short: Short, seconds: float, out: Path) -> Path:
    import soundfile as sf

    bed = music.score(seconds + 0.5, short.scene.get("mood", "tribute"), short.id)
    sf.write(out / "music.wav", bed, music.SR)
    mixed = out / "mix.wav"
    graph = ("[0:a]aresample=48000,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,"
             "volume=1.0,asplit=2[v][key];"
             "[1:a]aresample=48000,volume=0.30[m];"
             "[m][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
             "[v][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9,"
             f"apad,atrim=0:{seconds:.3f}[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(narration), "-i", str(out / "music.wav"),
                    "-filter_complex", graph, "-map", "[out]", "-ar", "48000", "-ac", "2", str(mixed)], check=True)
    return mixed


def render(short: Short, timing: dict, work: Path) -> dict:
    """short.mp4 (1080x1920, 30 fps, H.264 + AAC) and a few stills."""
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
        idx = int(beat.shot.split(":")[1]) if beat.shot.startswith("photo:") else None
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
    hook = _hook_layer(name, sub, accent)
    credits = {i: _credit_layer(p["credit"]) for i, p in enumerate(photos)}
    end = _end_layers(accent)
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
        _blit(frame, badge, 36, round(H * 0.745), 0.95)
        captions.draw(frame, t)
        enc.stdin.write(frame.tobytes())
        if i in still_at:
            Image.fromarray(frame).save(stills / f"t{i // FPS:03d}.png")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the Short")
    return {"duration": round(duration, 2), "frames": n, "template": "story", "photos": len(photos),
            "fps": FPS, "size": [W, H]}
