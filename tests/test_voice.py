import base64
import io
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from desk import align, gemini, voice
from desk.spec import Short

FIXTURE = Path(__file__).parent / "fixtures" / "wk-Q900001.json"
KEY = "test-key-never-shown"


@pytest.fixture
def short() -> Short:
    return Short.load(FIXTURE)


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    voice._tts_spent.clear()
    yield
    voice._tts_spent.clear()


def test_clock_times_and_symbols_are_spoken_in_hindi():
    assert voice.speakable("सुबह 9:30 पर") == "सुबह 9 बजकर 30 मिनट पर"
    assert voice.speakable("रात 11:00 बजे तक") == "रात 11 बजे तक"
    assert voice.speakable("सुबह 9:30 बजे") == "सुबह 9 बजकर 30 मिनट"
    assert voice.speakable("≈5% लोग") == "लगभग 5 प्रतिशत लोग"


def test_no_key_and_no_reference_holds(short, tmp_path, no_key, monkeypatch):
    monkeypatch.setattr(voice, "reference_ready", lambda: False)
    assert voice.ready().startswith("hold: no Sulafat voice")
    with pytest.raises(voice.VoiceHold):
        voice.synthesize(short, tmp_path)


def test_never_falls_back_to_another_voice(short, tmp_path, key, monkeypatch):
    """Gemini cannot read and there is no Sulafat reference: hold, never the built-in Chatterbox voice."""
    def spent(*a, **k):
        raise voice.TTSUnavailable("every model out of quota")
    called = []
    monkeypatch.setattr(voice, "_gemini_story", spent)
    monkeypatch.setattr(voice, "reference_ready", lambda: False)
    monkeypatch.setattr(voice, "_chatterbox_story", lambda *a, **k: called.append(a))
    with pytest.raises(voice.VoiceHold) as exc:
        voice.synthesize(short, tmp_path)
    assert called == [] and "every model out of quota" in str(exc.value)


def test_falls_back_to_the_sulafat_clone_only(short, tmp_path, key, monkeypatch):
    def spent(*a, **k):
        raise voice.TTSUnavailable("quota")
    seen = []
    monkeypatch.setattr(voice, "_gemini_story", spent)
    monkeypatch.setattr(voice, "reference_ready", lambda: True)
    monkeypatch.setattr(voice, "_chatterbox_story", lambda s, d, ref: seen.append(ref) or {"voice": {}})
    voice.synthesize(short, tmp_path)
    assert seen == [voice.REFERENCE]


def test_a_garbled_gemini_take_without_a_clone_is_retried_later(short, tmp_path, key, monkeypatch):
    def garbled(*a, **k):
        raise voice.TakeRejected("voice: every Sulafat take came out garbled")
    monkeypatch.setattr(voice, "_gemini_story", garbled)
    monkeypatch.setattr(voice, "reference_ready", lambda: False)
    with pytest.raises(voice.TakeRejected):
        voice.synthesize(short, tmp_path)


def test_a_good_gemini_take_is_timed_and_recorded(short, tmp_path, key, monkeypatch):
    words = [w for b in short.beats for w in b.text.split()]
    step = 60 / 147
    seconds = len(words) * step
    rng = np.random.default_rng(1)
    take = (0.2 * rng.standard_normal(int(seconds * voice.SAMPLE_RATE))).astype(np.float32)
    record = {"model": "gemini-3.8-flash-tts", "served_model": "gemini-3.8-flash-tts", "api": "interactions",
              "voice": "Sulafat"}
    monkeypatch.setattr(voice, "gemini_take", lambda *a, **k: (take, dict(record)))
    # faster-whisper hands back NumPy floats; every record must still be plain JSON.
    heard = [(w, np.float64(voice.LEAD_IN + i * step), np.float64(voice.LEAD_IN + (i + 0.9) * step))
             for i, w in enumerate(words)]
    monkeypatch.setattr(align, "heard", lambda wav: heard)
    timing = voice._gemini_story(short, tmp_path)
    takes = json.loads((tmp_path / "takes.json").read_text())
    assert takes[0]["ok"] is True and len(takes) == 1
    saved = json.loads((tmp_path / "timing.json").read_text())
    assert saved["voice"]["engine"] == "gemini-sulafat" and saved["voice"]["preview"] is False
    assert 140 <= saved["voice"]["wpm"] <= 155 and min(saved["voice"]["coverage"]) == 1.0
    assert len(timing["beats"]) == len(short.beats) and len(timing["words"]) == len(words)


def test_a_spent_pinned_model_hands_the_next_take_to_the_next_model(short, tmp_path, key, monkeypatch):
    words = [w for b in short.beats for w in b.text.split()]
    step = 60 / 147
    take = np.full(int(len(words) * step * voice.SAMPLE_RATE), 0.2, np.float32)
    asked = []

    def gemini_take(text, direction, models=None):
        asked.append(models)
        if models == ["gemini-3.8-flash-tts"]:
            raise voice.TTSUnavailable("gemini-3.8-flash-tts: HTTP 429")
        model = "gemini-3.8-flash-tts" if len(asked) == 1 else "gemini-3.8-flash-lite-tts"
        return take, {"model": model, "served_model": model, "api": "interactions", "voice": "Sulafat"}

    monkeypatch.setattr(voice, "gemini_take", gemini_take)
    good = [(w, voice.LEAD_IN + i * step, voice.LEAD_IN + (i + 0.9) * step) for i, w in enumerate(words)]
    heard = iter([good[: len(good) // 3]] + [good] * 10)
    monkeypatch.setattr(align, "heard", lambda wav: next(heard))
    timing = voice._gemini_story(short, tmp_path)
    assert asked == [None, ["gemini-3.8-flash-tts"], None]
    assert timing["voice"]["model"] == "gemini-3.8-flash-lite-tts"


def test_lines_are_read_one_by_one_and_only_a_garbled_line_is_retried(short, tmp_path, key, monkeypatch):
    line = np.full(voice.SAMPLE_RATE, 0.2, np.float32)
    asked = []
    monkeypatch.setattr(voice, "gemini_take", lambda text, d, models=None: asked.append(text) or (
        line, {"model": "gemini-3.8-flash-lite-tts", "served_model": "gemini-3.8-flash-lite-tts", "api": "x"}))
    first = iter([0.3, 1.0])

    def listen(wav, tokens):
        if wav.name == "line.wav":
            cover = next(first, 1.0) if len(asked) <= 2 else 1.0
            return [{"text": t, "start": 0.1, "end": 0.2, "beat": 0} for t, _ in tokens], [cover], [], None
        words = [{"text": t, "start": 0.4 + k * 0.3, "end": 0.6 + k * 0.3, "beat": b} for k, (t, b) in enumerate(tokens)]
        return words, [1.0] * len(short.beats), [], 150.0

    monkeypatch.setattr(voice, "_listen", listen)
    monkeypatch.setattr(align, "outside", lambda w, s: (0, 0))
    timing = voice.synthesize_lines(short, tmp_path)
    assert len(asked) == len(short.beats) + 1 and asked[0] == asked[1]
    assert timing["voice"]["identity"] == "sulafat" and timing["voice"]["by_line"] is True
    assert len(timing["beats"]) == len(short.beats) and (tmp_path / "narration.wav").exists()


def test_preview_uses_the_builtin_voice_and_is_marked(short, tmp_path, no_key, monkeypatch):
    seen = []
    monkeypatch.setattr(voice, "_chatterbox_story", lambda s, d, ref: seen.append(ref) or {})
    voice.synthesize(short, tmp_path, preview=True)
    assert seen == [None]


def test_gemini_request_shapes():
    url, body, api = voice.gemini_request("नमस्ते", "gemini-3.8-flash-tts", "warm")
    assert url.endswith("/interactions") and api == "interactions" and body["store"] is False
    assert body["generation_config"]["speech_config"] == [{"voice": "Sulafat"}]
    assert body["input"][0]["content"][0]["annotations"][0] == {"type": "speech_metadata", "style": "warm"}
    url, body, api = voice.gemini_request("नमस्ते", "gemini-2.5-flash-preview-tts", "warm")
    assert url.endswith(":generateContent") and api == "generateContent"
    assert body["contents"][0]["parts"][0]["text"] == "warm\n\nTRANSCRIPT:\nनमस्ते"
    assert body["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Sulafat"


def _wav(seconds=1.0, rate=24000) -> bytes:
    buf = io.BytesIO()
    t = np.arange(int(seconds * rate)) / rate
    sf.write(buf, (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32), rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_gemini_audio_is_validated():
    wav = base64.b64encode(_wav()).decode()
    good = {"status": "completed", "steps": [{"type": "model_output", "content": [
        {"type": "audio", "data": wav, "mime_type": "audio/wav"}]}]}
    audio, mime = voice.gemini_audio(good, "interactions")
    assert audio.startswith(b"RIFF") and len(voice._samples(audio, mime)) == 24000
    with pytest.raises(ValueError):
        voice.gemini_audio(good | {"status": "incomplete"}, "interactions")
    two = {"status": "completed", "steps": [{"type": "model_output", "content": good["steps"][0]["content"] * 2}]}
    with pytest.raises(ValueError):
        voice.gemini_audio(two, "interactions")
    pcm = base64.b64encode((np.zeros(2400, "<i2")).tobytes()).decode()
    old = {"candidates": [{"content": {"parts": [{"inlineData": {"data": pcm, "mimeType": "audio/L16;rate=24000"}}]}}]}
    audio, mime = voice.gemini_audio(old, "generateContent")
    assert len(voice._samples(audio, mime)) == 2400


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def test_a_spent_daily_quota_moves_to_the_next_model(key, monkeypatch):
    wav = base64.b64encode(_wav()).decode()
    calls = []

    def post(url, headers, json, timeout):
        calls.append((url, headers))
        if "3.8-flash-tts" in url or json.get("model") == "gemini-3.8-flash-tts":
            return Resp(429, {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                                     "violations": [{"quotaId": "GenerateRequestsPerDayPerProject",
                                                                     "quotaValue": "10"}]}]}})
        return Resp(200, {"status": "completed", "model": json.get("model"), "steps": [{"type": "model_output",
                          "content": [{"type": "audio", "data": wav, "mime_type": "audio/wav"}]}]})
    monkeypatch.setattr(voice.requests, "post", post)
    audio, record = voice.gemini_take("नमस्ते", "warm")
    assert record["model"] == "gemini-3.8-flash-lite-tts" and len(calls) == 2
    assert all(h == {"x-goog-api-key": KEY} for _, h in calls)
    assert "gemini-3.8-flash-tts" in voice._tts_spent


def test_a_refused_key_is_unavailable_and_never_echoed(key, monkeypatch):
    monkeypatch.setattr(voice.requests, "post", lambda *a, **k: Resp(403, {"error": {"message": f"bad key {KEY}"}}))
    with pytest.raises(voice.TTSUnavailable) as exc:
        voice.gemini_take("नमस्ते", "warm")
    assert KEY not in str(exc.value)


def test_no_key_is_unavailable(no_key):
    with pytest.raises(voice.TTSUnavailable):
        voice.gemini_take("नमस्ते", "warm")
    assert gemini.key() is None


def test_quota_parsing():
    r = Resp(429, {"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "PerMinute", "quotaValue": "3"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}]}})
    assert voice.quota(r) == ("PerMinute=3", 17.0)
    assert voice.quota(Resp(429, {})) == ("", None)


def test_hindi_alignment_keeps_script_words_and_scores_each_line():
    tokens = [("रमेश", 0), ("प्रसाद", 0), ("नहीं", 0), ("रहे।", 0), ("उनकी", 1), ("आवाज़", 1), ("अमर", 1), ("है।", 1)]
    spoken = [("रमेश", 0.0, 0.4), ("प्रसाद", 0.4, 0.8), ("नहीं", 0.8, 1.0), ("रहे", 1.0, 1.3),
              ("उनकी", 1.6, 1.9), ("आवाज", 1.9, 2.3)]
    words, coverage = align.align(tokens, spoken)
    assert [w["text"] for w in words] == [t for t, _ in tokens]
    assert coverage[0] == 1.0 and 0.4 < coverage[1] < 0.75
    assert words[6]["start"] >= words[5]["start"] and [w["beat"] for w in words] == [b for _, b in tokens]
    assert all(b["start"] >= a["start"] for a, b in zip(words, words[1:]))


def test_whisper_hears_16khz_mono_without_aliasing(tmp_path, monkeypatch):
    t = np.arange(24000) / 24000
    tone = 0.4 * np.sin(2 * np.pi * 1000 * t) + 0.4 * np.sin(2 * np.pi * 10000 * t)
    sf.write(tmp_path / "take.wav", np.stack([tone, tone], axis=1), 24000, subtype="PCM_16")
    audio = align.samples(tmp_path / "take.wav")
    assert audio.dtype == np.float32 and audio.shape == (16000,)
    spectrum = np.abs(np.fft.rfft(audio))
    # 1 kHz survives; 10 kHz is above the new Nyquist and must not fold back to 6 kHz.
    assert spectrum[1000] > 100 * spectrum[6000]

    seen = {}

    class Model:
        def transcribe(self, audio, **kw):
            seen["audio"], seen["language"] = audio, kw["language"]

            class Word:
                word, start, end = "नमस्ते", np.float64(0.1), np.float64(0.5)

            class Segment:
                words = [Word]
            return [Segment], None

    monkeypatch.setattr(align, "_whisper", Model)
    assert align.heard(tmp_path / "take.wav") == [("नमस्ते", 0.1, 0.5)]
    assert all(type(x) is float for x in align.heard(tmp_path / "take.wav")[0][1:])
    assert isinstance(seen["audio"], np.ndarray) and seen["language"] == "hi"


def test_extra_speech_outside_the_script_is_found():
    words = [{"text": "रमेश", "start": 2.0, "end": 2.4, "beat": 0}]
    spoken = [("कृपया गर्मजोशी से पढ़ें", 0.0, 1.5), ("रमेश", 2.0, 2.4)]
    before, after = align.outside(words, spoken)
    assert before > 0 and after == 0


def test_spans_cover_every_beat():
    words = [{"text": "a", "start": 0.4, "end": 0.8, "beat": 0}, {"text": "b", "start": 1.5, "end": 2.0, "beat": 1},
             {"text": "c", "start": 2.6, "end": 3.0, "beat": 2}]
    spans = voice._spans(words, 3, 3.5, 0.35)
    assert spans[0][0] == 0.35 and spans[-1][1] == 3.5 and len(spans) == 3
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))


def test_timing_records_the_voice(tmp_path):
    t = voice._timing(tmp_path, [], [], 1.0, {"engine": "gemini-sulafat", "identity": "sulafat", "preview": False})
    assert json.loads((tmp_path / "timing.json").read_text())["voice"]["engine"] == "gemini-sulafat"
    assert t["voice"]["identity"] == "sulafat"
