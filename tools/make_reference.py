"""Make tts/voices/sulafat_ref.wav: the Gemini Sulafat reference clip that Chatterbox clones when no Gemini TTS model
can read (the desk's only fallback; without this clip it holds instead).

    GEMINI_API_KEY=... uv run python tools/make_reference.py

Run once (the reference workflow does it in GitHub Actions with the `youtube` environment's key). The take must pass
the same Whisper listening check as a narration; the key is sent only in a request header and never printed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desk import align, gemini, voice  # noqa: E402

TEXT = ("नमस्कार। आज की कहानी एक ऐसे दिन की है जिसे बहुत लोग याद रखेंगे। हम आपको वही बताएँगे जो भरोसेमंद स्रोत "
        "कहते हैं, साफ़ और सीधे शब्दों में, ताकि आप पूरी बात समझ सकें।")
DIRECTION = ("Read this Hindi passage aloud as a warm, clear and expressive Hindi news storyteller speaking to one "
             "listener: calm, caring and natural, never dramatic. Pace: about 145 words a minute. Speak only the "
             "transcript.")
MIN_COVERAGE = 0.85
SECONDS = (7.0, 20.0)
PEAK = 10 ** (-1.0 / 20)


def main() -> int:
    if not gemini.key():
        print("GEMINI_API_KEY is not set: no reference clip made")
        return 2
    out = voice.REFERENCE
    out.parent.mkdir(parents=True, exist_ok=True)
    tokens = [(w, 0) for w in TEXT.split()]
    trial = out.with_name("sulafat_ref.trial.wav")
    for take in range(1, 4):
        audio, record = voice.gemini_take(TEXT, DIRECTION)
        head, tail = voice._bounds(audio)
        audio = audio[head:tail]
        audio = (audio * (PEAK / max(float(np.abs(audio).max()), 1e-6))).astype(np.float32)
        sf.write(trial, audio, voice.SAMPLE_RATE, subtype="PCM_16")
        spoken = align.heard(trial)
        words, coverage = align.align(tokens, spoken)
        extra = align.outside(words, spoken)
        seconds = len(audio) / voice.SAMPLE_RATE
        wpm = voice._wpm(tokens, spoken)
        print(f"take {take} ({record['served_model']}): {coverage[0]:.0%} heard, {seconds:.1f} s, {wpm} wpm"
              + (", extra speech" if any(extra) else ""))
        if coverage[0] >= MIN_COVERAGE and not any(extra) and SECONDS[0] <= seconds <= SECONDS[1]:
            trial.replace(out)
            meta = {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "voice": voice.VOICE,
                    "model": record["model"], "served_model": record["served_model"], "text": TEXT,
                    "direction": DIRECTION, "coverage": round(coverage[0], 3), "seconds": round(seconds, 2),
                    "wpm": wpm, "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
            out.with_suffix(".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
            print(f"wrote {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
            return 0
    trial.unlink(missing_ok=True)
    print("no take passed the listening check: no reference clip made")
    return 1


if __name__ == "__main__":
    sys.exit(main())
