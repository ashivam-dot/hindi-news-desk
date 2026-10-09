"""The channel's one narrator: Gemini TTS prebuilt voice Sulafat (female), the Mool Katha channel's Hindi voice.

Gemini reads the whole script in one take (the delivery carries from line to line). Whisper large-v3-turbo listens
to every take in Hindi: each line must reach MIN_COVERAGE, the take may not add speech of its own, and its pace must
be near TARGET_WPM, measured from Whisper's word timings. A take a little off pace is gently re-timed (pitch is kept)
and checked again. Up to TAKES takes, best first; otherwise the narration is rejected (fail closed).

When no Gemini TTS model can read (no key, or every free daily quota spent), the fallback keeps the same voice:
Chatterbox Multilingual (MIT) clones tts/voices/sulafat_ref.wav, a reference clip made once from Gemini Sulafat
(tools/make_reference.py). Until that clip exists the run holds (VoiceHold) instead of publishing in another voice.
There is never a fallback to a different voice or gender.

--voice-preview (dry runs and `make` only) reads with Chatterbox's built-in voice so the rest of the pipeline can be
checked end to end; such a Short is marked preview and can never be published (gate.voice_ok, youtube.publish).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import logging
import math
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

from . import align, gemini
from .spec import Short

log = logging.getLogger("desk.voice")
SAMPLE_RATE = 24000
LEAD_IN = 0.35
SPEECH_FLOOR = 0.01
EDGE_KEEP = 0.05
VOICE = "Sulafat"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_INTERACTIONS = "https://generativelanguage.googleapis.com/v1beta/interactions"
# Newest first; each has its own free daily quota.
GEMINI_TTS = ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview",
              "gemini-2.5-flash-preview-tts")
MAX_QUOTA_WAIT = 90.0
UNKNOWN_QUOTA_BACKOFF = (20.0, 40.0)
_BASE = ("Read this Hindi news story aloud as a warm, clear and expressive Hindi news storyteller speaking to one "
         "listener. Natural pauses between sentences and a slightly longer pause between lines. {mood} Never "
         "sensational, never dramatic, no shouting. Pace: about 145 words a minute. Speak only the transcript.")
DIRECTION = {"tribute": _BASE.format(mood="The story is a tribute: gentle, respectful and moving, with quiet warmth."),
             "news": _BASE.format(mood="The story is news: calm, steady and caring, with feeling that fits what "
                                       "happened.")}
TAKES = 3
MIN_COVERAGE = align.MIN_COVERAGE
TARGET_WPM, AIM_WPM, HARD_WPM = (140.0, 155.0), 147.0, (115.0, 185.0)
TEMPO_LIMITS = (0.85, 1.18)
CUT_LEAD = 0.08
TTS_DIR = Path(__file__).resolve().parents[1] / "tts"
REFERENCE = TTS_DIR / "voices" / "sulafat_ref.wav"
STYLE = {"tribute": {"exaggeration": 0.6, "cfg_weight": 0.4}, "news": {"exaggeration": 0.5, "cfg_weight": 0.45}}
_UNSUPPORTED = re.compile(r"\b(?:model|voice|sulafat)\b.{0,100}\b(?:unsupported|not supported|does not support|"
                          r"unavailable|not available|not found|unknown)\b|\b(?:unsupported|not supported|does not "
                          r"support|unavailable|not available|not found|unknown)\b.{0,100}\b(?:model|voice|sulafat)\b",
                          re.I)


class VoiceHold(RuntimeError):
    """No Sulafat voice can read now: hold the story instead of publishing it in another voice."""


class TTSUnavailable(RuntimeError):
    """No Gemini TTS model read the script (no key, or every model out of quota)."""


class TakeRejected(ValueError):
    """Every take failed the listening check."""


def speakable(text: str) -> str:
    """What the voice should read: clock times and symbols spelled the way a Hindi newsreader says them."""
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b(?:\s*बजे)?", lambda m: f"{int(m.group(1))} बजकर {int(m.group(2))} मिनट"
                  if int(m.group(2)) else f"{int(m.group(1))} बजे", text)
    return text.replace("≈", "लगभग ").replace("%", " प्रतिशत")


def reference_ready() -> bool:
    return REFERENCE.exists() and (TTS_DIR / ".venv" / "bin" / "python").exists()


def ready() -> str | None:
    """Why no Sulafat narration can be made this run, or None."""
    if gemini.key() or reference_ready():
        return None
    return ("hold: no Sulafat voice: GEMINI_API_KEY is not set and the Chatterbox fallback has no reference clip "
            "(run tools/make_reference.py with the key)")


def _bounds(audio: np.ndarray) -> tuple[int, int]:
    loud = np.flatnonzero(np.abs(audio) > SPEECH_FLOOR * np.abs(audio).max(initial=0.0))
    if not loud.size:
        return 0, len(audio)
    keep = int(EDGE_KEEP * SAMPLE_RATE)
    return max(int(loud[0]) - keep, 0), min(int(loud[-1]) + keep + 1, len(audio))


def _resample(audio: np.ndarray, rate: int) -> np.ndarray:
    if rate == SAMPLE_RATE:
        return audio.astype(np.float32)
    n = round(len(audio) * SAMPLE_RATE / rate)
    return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)


def _samples(data: bytes, mime: str) -> np.ndarray:
    """Gemini's audio as float samples at SAMPLE_RATE: raw 16-bit PCM from older models, a WAV file from 3.8."""
    if data[:4] == b"RIFF":
        audio, rate = sf.read(io.BytesIO(data), dtype="float32")
        audio = audio.mean(axis=1) if audio.ndim > 1 else audio
    else:
        audio = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
        rate = next((int(p[5:]) for p in mime.replace(" ", "").split(";") if p.startswith("rate=")), SAMPLE_RATE)
    return _resample(audio, rate)


def gemini_request(text: str, model: str, direction: str) -> tuple[str, dict, str]:
    """The model-specific request: Gemini 3.8 takes the direction as speech_metadata.style and its text verbatim;
    older models get the direction before a TRANSCRIPT label."""
    if model.startswith("gemini-3.8-"):
        return (GEMINI_INTERACTIONS,
                {"model": model,
                 "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                           "annotations": [{"type": "speech_metadata", "style": direction}]}]}],
                 "response_format": {"type": "audio", "mime_type": "audio/wav"},
                 "generation_config": {"speech_config": [{"voice": VOICE}]},
                 "store": False},
                "interactions")
    return (f"{GEMINI_API}/{model}:generateContent",
            {"contents": [{"parts": [{"text": f"{direction}\n\nTRANSCRIPT:\n{text}"}]}],
             "generationConfig": {"responseModalities": ["AUDIO"],
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}},
            "generateContent")


def gemini_audio(data: dict, api: str) -> tuple[bytes, str]:
    """The single full audio block; a partial interaction or a missing segment is an error, never dropped."""
    if api == "interactions":
        if data.get("status") != "completed":
            raise ValueError(f"interaction status is {data.get('status') or 'missing'}")
        blocks = [part for step in data.get("steps", []) if step.get("type") == "model_output"
                  for part in step.get("content", []) if part.get("type") == "audio"]
        if len(blocks) != 1 or not blocks[0].get("data"):
            raise ValueError(f"expected one audio block, got {len(blocks)}")
        audio = base64.b64decode(blocks[0]["data"], validate=True)
        mime = blocks[0].get("mime_type", "audio/wav")
        if mime != "audio/wav" or not audio.startswith(b"RIFF"):
            raise ValueError(f"expected a WAV response, got {mime}")
    else:
        part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
        audio = base64.b64decode(part["data"], validate=True)
        mime = part.get("mimeType", "")
    if not audio:
        raise ValueError("empty audio response")
    return audio, mime


def quota(resp: requests.Response) -> tuple[str, float | None]:
    """The quotas a 429 names (id=limit), and how many seconds Google asks us to wait, if it says."""
    try:
        details = resp.json()["error"].get("details", [])
    except (ValueError, KeyError, AttributeError):
        return "", None
    names, delay = "", None
    for detail in details:
        kind = detail.get("@type", "")
        if kind.endswith("QuotaFailure"):
            names = ", ".join(f"{v.get('quotaId', '?')}={v.get('quotaValue', '?')}" for v in detail.get("violations", []))
        elif kind.endswith("RetryInfo"):
            try:
                seconds = float(str(detail.get("retryDelay", "")).rstrip("s"))
                delay = seconds if math.isfinite(seconds) and seconds >= 0 else None
            except ValueError:
                pass
    return names, delay


def _unsupported(resp: requests.Response) -> bool:
    try:
        error = resp.json().get("error", {})
    except (ValueError, AttributeError):
        return False
    message = error.get("message", "") if isinstance(error, dict) else ""
    return isinstance(message, str) and bool(_UNSUPPORTED.search(message))


_tts_spent: set[str] = set()


def gemini_take(text: str, direction: str, models: list[str] | None = None) -> tuple[np.ndarray, dict]:
    """One Sulafat reading of text and its record. Walks the TTS models on 429 (waiting out short RetryInfo delays);
    raises TTSUnavailable when none can read."""
    key = gemini.key()
    if not key:
        raise TTSUnavailable("GEMINI_API_KEY is not set")
    errors = []
    for model in models or [m for m in GEMINI_TTS if m not in _tts_spent]:
        endpoint, body, api = gemini_request(text, model, direction)
        for attempt in range(3):
            requested = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                resp = requests.post(endpoint, headers={"x-goog-api-key": key}, json=body, timeout=300)
            except requests.RequestException as exc:
                errors.append(f"{model}: {type(exc).__name__}")
                time.sleep(10 * (attempt + 1))
                continue
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    audio, mime = gemini_audio(data, api)
                except (KeyError, IndexError, TypeError, ValueError, binascii.Error) as exc:
                    errors.append(f"{model}: unusable audio ({exc})"[:160])
                    break
                served = data.get("model") if api == "interactions" else data.get("modelVersion")
                return _samples(audio, mime), {
                    "model": model, "served_model": served or model, "api": api, "voice": VOICE,
                    "requested_at": requested, "direction_sha256": hashlib.sha256(direction.encode()).hexdigest(),
                    "transcript_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "audio_sha256": hashlib.sha256(audio).hexdigest()}
            if resp.status_code == 429:
                names, delay = quota(resp)
                errors.append(f"{model}: HTTP 429 {names}".rstrip())
                if attempt < 2 and "perday" not in names.lower():
                    wait = UNKNOWN_QUOTA_BACKOFF[attempt] if delay is None else (delay + 1 if delay <= MAX_QUOTA_WAIT
                                                                                  else None)
                    if wait is not None:
                        log.info("%s: HTTP 429; waiting %.0f s", model, wait)
                        time.sleep(wait)
                        continue
                _tts_spent.add(model)
                break
            if resp.status_code in (400, 404) and (resp.status_code == 404 or _unsupported(resp)):
                errors.append(f"{model}: HTTP {resp.status_code} (unavailable)")
                _tts_spent.add(model)
                break
            if resp.status_code in (401, 403):
                raise TTSUnavailable(f"Gemini refused the key (HTTP {resp.status_code})")
            errors.append(f"{model}: HTTP {resp.status_code}")
            if resp.status_code < 500:
                break
            time.sleep(10 * (attempt + 1))
    raise TTSUnavailable("no Gemini TTS model read the script: " + "; ".join(errors[-6:]))


def _wpm(tokens: list, spoken: list[tuple[str, float, float]]) -> float | None:
    seconds = spoken[-1][2] - spoken[0][1] if spoken else 0.0
    return round(len(tokens) * 60 / seconds, 1) if seconds > 0 else None


def _tempo(path: Path, factor: float, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-af", f"atempo={factor:.4f}",
                    "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out)], check=True)
    return out


def _listen(wav: Path, tokens: list[tuple[str, int]]) -> tuple[list[dict], list[float], list, float | None]:
    spoken = align.heard(wav)
    words, coverage = align.align(tokens, spoken)
    return words, coverage, spoken, _wpm(tokens, spoken)


def _spans(words: list[dict], beats: int, duration: float, lead: float) -> list[list[float]]:
    starts = [min((w["start"] for w in words if w["beat"] == i), default=None) for i in range(beats)]
    for i in range(beats):
        if starts[i] is None:
            starts[i] = starts[i - 1] if i else lead
    cuts = [lead] + [max(s - CUT_LEAD, prev + 0.2) for prev, s in zip(starts, starts[1:])] + [duration]
    return [[round(a, 3), round(b, 3)] for a, b in zip(cuts, cuts[1:])]


def _paced(wav: Path, tokens, words, coverage, spoken, wpm, out_dir: Path) -> tuple[list, list, float | None, float]:
    """Gently re-time a take that is off TARGET_WPM, then listen again; the original stays if the re-timed one fails."""
    if wpm is None or TARGET_WPM[0] <= wpm <= TARGET_WPM[1]:
        return words, coverage, wpm, 1.0
    factor = min(max(AIM_WPM / wpm, TEMPO_LIMITS[0]), TEMPO_LIMITS[1])
    paced = _tempo(wav, factor, out_dir / "narration-paced.wav")
    w2, c2, _, wpm2 = _listen(paced, tokens)
    if c2 and min(c2) >= MIN_COVERAGE:
        paced.replace(wav)
        return w2, c2, wpm2, round(factor, 4)
    paced.unlink(missing_ok=True)
    return words, coverage, wpm, 1.0


def _gemini_story(short: Short, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    mood = short.scene.get("mood", "news")
    direction = DIRECTION.get(mood, DIRECTION["news"])
    transcript = "\n".join(speakable(b.text) for b in short.beats)
    tokens = [(w, i) for i, b in enumerate(short.beats) for w in b.text.split()]
    wav = out_dir / "narration.wav"
    best, takes, pinned = None, [], None
    for take in range(1, TAKES + 1):
        raw, record = gemini_take(transcript, direction, [pinned] if pinned else None)
        pinned = record["model"]
        head, tail = _bounds(raw)
        raw = raw[head:tail]
        clean = False
        for _ in range(3):
            audio = np.concatenate([np.zeros(int(LEAD_IN * SAMPLE_RATE), np.float32), raw])
            sf.write(wav, audio, SAMPLE_RATE)
            words, coverage, spoken, wpm = _listen(wav, tokens)
            before, after = align.outside(words, spoken)
            if not (before or after):
                clean = True
                break
            # Gemini sometimes reads its direction aloud too; keep only the script's own reading.
            start = int(max(words[0]["start"] - LEAD_IN - 0.12, 0) * SAMPLE_RATE) if before else 0
            end = int((words[-1]["end"] - LEAD_IN + 0.12) * SAMPLE_RATE) if after else len(raw)
            raw = raw[start:end]
        low = min(coverage) if coverage else 0.0
        ok = clean and low >= MIN_COVERAGE and wpm is not None and HARD_WPM[0] <= wpm <= HARD_WPM[1]
        takes.append({"take": take, "model": record["served_model"], "coverage": [round(c, 3) for c in coverage],
                      "wpm": wpm, "clean": clean, "ok": ok})
        log.info("take %d (%s): coverage %s, %s wpm%s", take, record["served_model"],
                 " ".join(f"{c:.0%}" for c in coverage), wpm, "" if clean else ", extra speech")
        if ok and (best is None or abs(wpm - AIM_WPM) < abs(best[3] - AIM_WPM)):
            best = (audio, record, (words, coverage, spoken), wpm)
        if ok and TARGET_WPM[0] - 5 <= wpm <= TARGET_WPM[1] + 5:
            break
    (out_dir / "takes.json").write_text(json.dumps(takes, indent=1), encoding="utf-8")
    if best is None:
        raise TakeRejected(f"voice: every Sulafat take came out garbled or off pace: {takes}"[:400])
    audio, record, (words, coverage, spoken), wpm = best
    sf.write(wav, audio, SAMPLE_RATE)
    words, coverage, wpm, factor = _paced(wav, tokens, words, coverage, spoken, wpm, out_dir)
    duration = sf.info(str(wav)).duration
    lead = LEAD_IN / factor
    words = [w | {"start": max(w["start"], lead), "end": max(w["end"], lead + 0.05)} for w in words]
    return _timing(out_dir, words, _spans(words, len(short.beats), duration, lead), duration,
                   {"engine": "gemini-sulafat", "identity": "sulafat", "preview": False, **record,
                    "coverage": [round(c, 3) for c in coverage], "wpm": wpm, "tempo": factor, "takes": len(takes)})


def _chatterbox(lines: list[str], out: Path, style: dict, seed: int, voice: Path | None) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    job = out / "job.json"
    job.write_text(json.dumps({"lines": lines, "out": str(out), "seed": seed, "language": "hi",
                               "voice": str(voice) if voice else None, **style}, ensure_ascii=False), encoding="utf-8")
    python = TTS_DIR / ".venv" / "bin" / "python"
    subprocess.run([str(python), str(TTS_DIR / "speak.py"), str(job)], check=True, stdout=subprocess.DEVNULL)
    return json.loads((out / "lines.json").read_text(encoding="utf-8"))


def _chatterbox_story(short: Short, out_dir: Path, reference: Path | None) -> dict:
    """Chatterbox Multilingual in Hindi, one take per beat, each checked by Whisper. reference None is the preview."""
    out_dir.mkdir(parents=True, exist_ok=True)
    mood = short.scene.get("mood", "news")
    style = STYLE.get(mood, STYLE["news"])
    texts = [speakable(b.text) for b in short.beats]
    takes = _chatterbox(texts, out_dir / "takes", style, 7, reference)
    clips = []
    for i, (beat, take) in enumerate(zip(short.beats, takes)):
        tokens = [(w, 0) for w in beat.text.split()]
        best = None
        for attempt in range(3):
            if attempt:
                take = _chatterbox([texts[i]], out_dir / f"retake{i:02d}-{attempt}", style, 100 + 31 * attempt + i,
                                   reference)[0]
            audio, sr = sf.read(take["file"], dtype="float32")
            audio = _resample(audio if audio.ndim == 1 else audio.mean(axis=1), sr)
            head, tail = _bounds(audio)
            audio = audio[head:tail]
            clip = out_dir / f"beat{i:02d}.wav"
            sf.write(clip, audio, SAMPLE_RATE)
            words, coverage, _, _ = _listen(clip, tokens)
            match = coverage[0] if coverage else 0.0
            if best is None or match > best[2]:
                best = (audio, words, match)
            if match >= MIN_COVERAGE:
                break
        if best[2] < MIN_COVERAGE:
            raise TakeRejected(f"voice: beat {i + 1} came out garbled ({best[2]:.0%} of its letters heard)")
        clips.append(best)
    pieces = [np.zeros(int(LEAD_IN * SAMPLE_RATE), np.float32)]
    t, words = LEAD_IN, []
    for index, (beat, (audio, beat_words, _)) in enumerate(zip(short.beats, clips)):
        words += [{"text": w["text"], "start": round(t + w["start"], 3), "end": round(t + w["end"], 3), "beat": index}
                  for w in beat_words]
        pieces += [audio, np.zeros(int(beat.pause_after * SAMPLE_RATE), np.float32)]
        t += len(audio) / SAMPLE_RATE + beat.pause_after
    wav = out_dir / "narration.wav"
    sf.write(wav, np.concatenate(pieces), SAMPLE_RATE)
    spoken = [(w["text"], w["start"], w["end"]) for w in words]
    wpm = _wpm(words, spoken)
    factor = 1.0
    if wpm and not TARGET_WPM[0] <= wpm <= TARGET_WPM[1]:
        factor = round(min(max(AIM_WPM / wpm, TEMPO_LIMITS[0]), TEMPO_LIMITS[1]), 4)
        _tempo(wav, factor, out_dir / "narration-paced.wav").replace(wav)
        # atempo stretches time uniformly, so every timing scales by the same factor.
        words = [w | {"start": round(w["start"] / factor, 3), "end": round(w["end"] / factor, 3)} for w in words]
        wpm = round(wpm * factor, 1)
    duration = sf.info(str(wav)).duration
    preview = reference is None
    record = {"engine": "chatterbox-preview" if preview else "chatterbox-sulafat-clone",
              "identity": "preview" if preview else "sulafat", "preview": preview,
              "reference": None if preview else str(reference.relative_to(TTS_DIR.parent)),
              "reference_sha256": None if preview else hashlib.sha256(reference.read_bytes()).hexdigest(),
              "coverage": [round(c[2], 3) for c in clips], "wpm": wpm, "tempo": factor, **style}
    return _timing(out_dir, words, _spans(words, len(short.beats), duration, LEAD_IN / factor), duration, record)


def _timing(out_dir: Path, words: list[dict], spans: list, duration: float, voice: dict) -> dict:
    timing = {"duration": round(duration, 3), "words": words, "beats": spans, "voice": voice,
              "sample_rate": SAMPLE_RATE}
    (out_dir / "timing.json").write_text(json.dumps(timing, indent=1, ensure_ascii=False), encoding="utf-8")
    return timing


def synthesize(short: Short, out_dir: Path, preview: bool = False) -> dict:
    """narration.wav plus timing.json: {duration, words, beats: [[start, end], ...], voice}."""
    if preview:
        return _chatterbox_story(short, out_dir, None)
    reason = None
    if gemini.key():
        try:
            return _gemini_story(short, out_dir)
        except TTSUnavailable as exc:
            reason = str(exc)
        except TakeRejected as exc:
            if not reference_ready():
                raise
            reason = str(exc)
        log.warning("no Gemini Sulafat narration (%s); trying the Sulafat clone", reason)
    if reference_ready():
        return _chatterbox_story(short, out_dir, REFERENCE)
    raise VoiceHold(f"hold: no Sulafat voice: {reason or 'GEMINI_API_KEY is not set'}, and the Chatterbox fallback "
                    "has no reference clip (tools/make_reference.py)")
