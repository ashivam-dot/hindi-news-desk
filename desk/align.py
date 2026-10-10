"""Word timings and a listening check for Hindi narration: Whisper large-v3-turbo (MIT, through faster-whisper)
transcribes the take in Hindi with word timestamps, and the script's own words are matched onto what it heard letter
by letter (Hindi spellings vary, so letters match where whole words would not). Captions then show exactly what was
written, at the moment it is spoken.

The share of each line's letters Whisper found is the take's coverage: a skipped or garbled line scores low, and a
take is used only when every line reaches MIN_COVERAGE (the Mool Katha studio's gate for the same voice).
"""
from __future__ import annotations

import difflib
import os
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL = os.environ.get("DESK_ALIGN_MODEL", "large-v3-turbo")
LANGUAGE = "hi"
WHISPER_RATE = 16000
MIN_COVERAGE = 0.75
# More letters than this heard outside the script is speech the voice added (it sometimes reads its direction).
EXTRA_LETTERS = 6
SECONDS_PER_LETTER = 0.15  # generous: Sulafat speaks about 12-15 Devanagari letters a second
_model = None


def letters(text: str) -> str:
    """A text's letters, vowel signs and digits: what a transcript and the script can be matched on."""
    return "".join(ch for ch in unicodedata.normalize("NFC", text).lower() if unicodedata.category(ch)[0] in "LMN")


def _whisper():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(MODEL, device="cpu", compute_type="int8")
    return _model


def samples(wav: Path) -> np.ndarray:
    """A recording as Whisper's 16 kHz mono float32, read with soundfile (faster-whisper 1.2.1's own decoder passes
    PyAV an argument that PyAV 19 no longer accepts) and resampled band-limited, through the FFT."""
    audio, rate = sf.read(str(wav), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if rate == WHISPER_RATE or not len(audio):
        return audio.astype(np.float32)
    n = max(round(len(audio) * WHISPER_RATE / rate), 1)
    spectrum = np.fft.rfft(audio)[: n // 2 + 1]
    return (np.fft.irfft(spectrum, n) * (n / len(audio))).astype(np.float32)


def heard(wav: Path) -> list[tuple[str, float, float]]:
    """[(word, start, end)] that Whisper heard in a Hindi recording."""
    segments, _ = _whisper().transcribe(samples(wav), language=LANGUAGE, word_timestamps=True, temperature=0.0,
                                        condition_on_previous_text=False)
    return [(w.word, float(w.start), float(w.end)) for s in segments for w in (s.words or [])]


def align(tokens: list[tuple[str, int]], spoken: list[tuple[str, float, float]]) -> tuple[list[dict], list[float]]:
    """Time the script's words [(text, beat)] by matching their letters to the ones Whisper heard, and say what share
    of each beat's letters it heard. Words it missed share the time between their neighbours."""
    if not tokens:
        return [], []
    script, owner = "", []
    beats = max(beat for _, beat in tokens) + 1
    total, found = [0] * beats, [0] * beats
    for index, (text, beat) in enumerate(tokens):
        ls = letters(text)
        script += ls
        owner += [index] * len(ls)
        total[beat] += len(ls)
    said, clock = "", []
    for text, start, end in spoken:
        ls = letters(text)
        said += ls
        step = (end - start) / max(len(ls), 1)
        clock += [(start + k * step, start + (k + 1) * step) for k in range(len(ls))]
    first: list[float | None] = [None] * len(tokens)
    last: list[float | None] = [None] * len(tokens)
    for a, b, size in difflib.SequenceMatcher(None, script, said, autojunk=False).get_matching_blocks():
        for k in range(size):
            i = owner[a + k]
            found[tokens[i][1]] += 1
            if first[i] is None:
                first[i] = clock[b + k][0]
            last[i] = clock[b + k][1]
    known = [i for i in range(len(tokens)) if first[i] is not None]
    if not known:
        return [], [0.0] * beats
    words, floor, heard = [], 0.0, set(known)
    for i, (text, beat) in enumerate(tokens):
        if first[i] is None:
            before = max((j for j in known if j < i), default=None)
            after = min((j for j in known if j > i), default=None)
            span = range(before + 1 if before is not None else 0, after if after is not None else len(tokens))
            sizes = [max(len(letters(tokens[j][0])), 1) for j in span]
            # Unheard words at either end may not stretch over extra speech (a read-aloud direction, babble).
            budget = sum(sizes) * SECONDS_PER_LETTER
            lo = last[before] if before is not None else max(spoken[0][1], first[after] - budget)
            hi = first[after] if after is not None else min(spoken[-1][2], last[before] + budget)
            done = sum(sizes[: i - span.start])
            first[i] = lo + (hi - lo) * done / sum(sizes)
            last[i] = lo + (hi - lo) * (done + sizes[i - span.start]) / sum(sizes)
        start = max(first[i], floor)
        words.append({"text": text, "start": round(start, 3), "end": round(max(last[i], start + 0.05), 3),
                      "beat": beat, "heard": i in heard})
        floor = start
    return words, [f / max(t, 1) for f, t in zip(found, total)]


def outside(words: list[dict], spoken: list[tuple[str, float, float]]) -> tuple[int, int]:
    """Letters Whisper heard before the script's first word and after its last, when more than EXTRA_LETTERS."""
    heard = [w for w in words if w.get("heard", True)] or words
    if not heard:
        return 0, 0
    before = sum(len(letters(t)) for t, _, end in spoken if end <= heard[0]["start"] - 0.1)
    after = sum(len(letters(t)) for t, start, _ in spoken if start >= heard[-1]["end"] + 0.1)
    return (before if before > EXTRA_LETTERS else 0), (after if after > EXTRA_LETTERS else 0)
