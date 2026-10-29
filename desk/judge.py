"""The footage step's judge: Gemma 4 on the desk's Gemini key (GEMINI_API_KEY), from the Chaukanna kit's
news/gemini.py. Only text_json is used here; the desk's own writer and voice keep desk/gemini.py."""


from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import requests
import soundfile as sf

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models"
# Each model has its own free daily quota, so later ones carry on when earlier ones run out.
TEXT_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash-preview",
               "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview"]
# Gemini 3.0 and 3.1 models can loop below their default temperature of 1.0, as Google warns: a fact check at 0.0
# on gemini-3-flash-preview ran past the 120 s timeout three times in four, and took 10 s at 1.0.
LOOP_WHEN_COLD = ("gemini-3-", "gemini-3.1-")
TTS_MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview",
              "gemini-2.5-flash-preview-tts"]
# After the Gemini text models, models with quotas of their own: Gemma 4 on the same key (it takes a system
# instruction, but not JSON mode beside it), then each provider's below while its key is set. They write weaker Hindi
# than Gemini, so editor.py never lets one of them fact-check alone.
GEMMA_MODELS = ["gemma-4-26b-a4b-it", "gemma-4-31b-it"]
# provider: (OpenAI-style chat URL, key variable, models, extra request fields). Cloudflare's URL carries the account
# from NEWS_CLOUDFLARE_ACCOUNT_ID. Its answers stop at 256 tokens unless asked for more, which gpt-oss spends on
# reasoning before any JSON; low effort wrote as well in a test, 2.4 times faster and on a fifth fewer of its daily
# 10,000 free neurons (about 150 for a short write). Mistral, on the studio's key, comes last: its free plan only
# serves the Ministral models (Small and Magistral have a limit of 0 a minute), and in a test Ministral 14B kept the
# desk's JSON but added a line its source didn't have.
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "NEWS_GROQ_API_KEY",
             ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"], {"response_format": {"type": "json_object"}}),
    "cloudflare": ("https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
                   "NEWS_CLOUDFLARE_API_TOKEN", ["@cf/openai/gpt-oss-120b"],
                   {"max_tokens": 6000, "reasoning_effort": "low"}),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "YTC_MISTRAL_API_KEY", ["ministral-14b-2512"],
                {"response_format": {"type": "json_object"}, "max_tokens": 4096}),
}
JSON_ONLY = "\n\nAnswer with one JSON object and nothing else."
# The voice when every Gemini voice model is out: Sarvam's Hindi news anchor, whose audio may be monetised.
SARVAM = "sarvam:bulbul:v4-flash"
SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_SPEAKER = "anand_hi_news"
VOICE = "Orus"
PREBUILT = {"Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus",
            "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
            "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia",
            "Sadaltager", "Sulafat"}


class Exhausted(RuntimeError):
    """Every model refused: daily quotas are used up or the service is down."""


_COOL: dict[str, float] = {}  # model -> unix time until which it is passed over


def cooldowns() -> dict[str, float]:
    """The models currently passed over and until when, to carry into the next cycle."""
    now = time.time()
    return {m: t for m, t in _COOL.items() if t > now}


def restore(saved: dict | None) -> None:
    now = time.time()
    _COOL.update({m: float(t) for m, t in (saved or {}).items() if float(t) > now})


def _order(models: list[str]) -> list[str]:
    """`models` without the ones cooling down, unless every one is."""
    now = time.time()
    return [m for m in models if _COOL.get(m, 0) <= now] or list(models)


def ready_at(models: list[str]) -> float:
    """When the first of `models` may be asked again: now, unless every one is cooling down."""
    return min(_COOL.get(m, 0.0) for m in models)


def _quota_reset() -> float:
    """Five minutes after the next midnight Pacific time, when Gemini's per-day quotas reset."""
    tomorrow = datetime.now(ZoneInfo("America/Los_Angeles")) + timedelta(days=1)
    return tomorrow.replace(hour=0, minute=5, second=0, microsecond=0).timestamp()


def fallback_models() -> list[str]:
    """The text models after Gemini's: Gemma, then each provider's ("provider:model") while its key is set."""
    return GEMMA_MODELS + [f"{name}:{model}" for name, (_, key, models, _) in PROVIDERS.items()
                           if os.environ.get(key) for model in models]


def voice_models(models: list[str] | None = None) -> list[str]:
    """The voice models to try in turn: `models`, else Gemini's and then Sarvam while its key is set."""
    if models:
        return list(models)
    return TTS_MODELS + ([SARVAM] if os.environ.get("NEWS_SARVAM_API_KEY") else [])


def _wait(resp: requests.Response) -> float | None:
    """Seconds a refusal asks for: its Retry-After, or "try again in 7m12.5s" in its text."""
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        pass
    found = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", resp.text)
    if not found or not any(found.groups()):
        return None
    hours, minutes, seconds = (float(g or 0) for g in found.groups())
    return hours * 3600 + minutes * 60 + seconds


def _cool_other(model: str, resp: requests.Response) -> None:
    """Another provider's refusal: a used-up daily allowance until it renews (Cloudflare's at 00:00 UTC), a rate
    limit for as long as it asks, a refused key or exhausted credit for six hours. A request too large for the
    model's minute is only that request's problem."""
    code, text = resp.status_code, resp.text
    if code == 429 and re.search(r"neurons|per day|daily", text, re.I):
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        until = time.time() + w if (w := _wait(resp)) else \
            tomorrow.replace(hour=0, minute=5, second=0, microsecond=0).timestamp()
    elif code == 429 and "insufficient_quota" not in text:
        until = time.time() + max(60.0, _wait(resp) or 60.0)
    elif code in (401, 402, 403, 429):
        until = time.time() + 6 * 3600
    elif code == 404:
        until = time.time() + 30 * 86400
    elif code >= 500:
        until = time.time() + 600
    else:
        return
    _COOL[model] = until


def _cool(model: str, resp: requests.Response) -> None:
    if ":" in model:
        _cool_other(model, resp)
        return
    if resp.status_code >= 500 and model.startswith("gemma-"):
        return  # Gemma 4's 500s come at random, or from the one request: the next request may well get through
    if resp.status_code >= 500:
        until = time.time() + 600
    elif resp.status_code == 429 and "PerDay" in resp.text:
        # Models refused this way at 06:00 IST answered a stray request or two around 09:00 and were refused again
        # by 10:00, so retrying before the reset only spends requests on picking and writing.
        until = _quota_reset()
    elif resp.status_code == 429:
        until = time.time() + (90 if "PerMinute" in resp.text else 24 * 3600)
    elif resp.status_code == 404:
        until = time.time() + 30 * 86400
    else:
        return
    _COOL[model] = until


def _refusal(resp: requests.Response) -> str:
    """The quota a 429 names, or the start of the error."""
    quota = re.search(r'"quotaId":\s*"([^"]+)"', resp.text)
    return quota.group(1) if quota else resp.text[:160]


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return key


def _post(model: str, body: dict, timeout: int) -> requests.Response:
    """One request, asked again once after a dropped connection, a per-minute 429, a busy 503 or a quick 500; a request
    that ran past its timeout, a per-day 429, or a model still busy, goes back for the caller to move on to the next
    model: news can't wait. (Asking a timed-out Gemma again cost a fact check four minutes. Gemma 4 answers about a
    third of its requests, text or image, with a 500 within seconds, and a second try mostly gets through.)"""
    for attempt in range(2):
        started = time.monotonic()
        try:
            resp = requests.post(f"{API}/{model}:generateContent", headers={"x-goog-api-key": _key()}, json=body,
                                 timeout=timeout)
        except requests.ConnectionError as exc:
            if attempt == 1:
                raise
            log.warning("gemini %s: %s; asking again", model, exc)
            continue
        quick_500 = resp.status_code == 500 and time.monotonic() - started < 20
        if (resp.status_code not in (429, 503) and not quick_500) or attempt == 1:
            return resp
        delay = re.search(r'"retryDelay":\s*"(\d+)(?:\.\d+)?s"', resp.text)
        if resp.status_code == 429 and ("PerDay" in resp.text or not delay):
            return resp
        time.sleep(min(30, int(delay.group(1)) + 1) if delay else 3)
    return resp


def _gemini_body(model: str, system: str, prompt: str, temperature: float, media: list[dict] | None) -> dict:
    config: dict = {"temperature": 1.0 if model.startswith(LOOP_WHEN_COLD) else temperature}
    if model.startswith("gemma-"):
        system += JSON_ONLY
    else:
        config["responseMimeType"] = "application/json"
    return {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [*(media or []), {"text": prompt}]}], "generationConfig": config}


def _chat(model: str, system: str, prompt: str, temperature: float) -> requests.Response:
    """One request to another provider's OpenAI-style chat API; `model` is "provider:model"."""
    name, _, model_id = model.partition(":")
    url, key, _, extra = PROVIDERS[name]
    body = {"model": model_id, "temperature": temperature,
            "messages": [{"role": "system", "content": system + JSON_ONLY}, {"role": "user", "content": prompt}], **extra}
    return requests.post(url.format(account=os.environ.get("NEWS_CLOUDFLARE_ACCOUNT_ID", "")), json=body,
                         headers={"Authorization": f"Bearer {os.environ.get(key, '')}"}, timeout=120)


def _answer_text(model: str, resp: requests.Response) -> str:
    if ":" in model:
        choice = resp.json()["choices"][0]
        if not choice["message"].get("content"):
            raise ValueError(f"no answer, finish reason {choice.get('finish_reason')}")
        return choice["message"]["content"]
    parts = resp.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _json_answer(raw: str):
    """The JSON in an answer, without a Markdown fence or words around it."""
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise
        return json.loads(text[start:end + 1])


def text_json(system: str, prompt: str, temperature: float = 0.5, models: list[str] | None = None,
              media: list[dict] | None = None, fallback: bool = True, timeout: int = 120) -> dict:
    """A JSON answer from the first text model that gives one. `media` parts (audio, say) go before the prompt and
    keep the request on Gemini; without them the fallback models follow `models`, unless `fallback` is off.
    `timeout`: seconds each Gemini or Gemma request may take."""
    chain = list(models or TEXT_MODELS)
    if fallback and not media:
        chain += [m for m in fallback_models() if m not in chain]
    errors = []
    for model in _order(chain):
        try:
            resp = _chat(model, system, prompt, temperature) if ":" in model else \
                _post(model, _gemini_body(model, system, prompt, temperature, media), timeout)
        except requests.RequestException as exc:
            _COOL[model] = time.time() + 600
            errors.append(f"{model}: {exc}")
            log.warning("%s failed: %s", model, errors[-1])
            continue
        if resp.status_code != 200:
            _cool(model, resp)
            errors.append(f"{model}: HTTP {resp.status_code} {_refusal(resp)}")
            log.warning("%s refused: %s", model, errors[-1])
            continue
        try:
            data = _json_answer(_answer_text(model, resp))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            errors.append(f"{model}: unreadable answer ({exc})")
            log.warning("%s", errors[-1])
            continue
        log.info("text answered by %s", model)
        return {"_model": model, **data} if isinstance(data, dict) else {"_model": model, "items": data}
    raise Exhausted("; ".join(errors))


def _samples(data: bytes, mime: str) -> tuple[np.ndarray, int]:
    if data[:4] == b"RIFF":
        audio, rate = sf.read(io.BytesIO(data), dtype="float32")
        return (audio.mean(axis=1) if audio.ndim > 1 else audio), rate
    rate = next((int(p[5:]) for p in mime.replace(" ", "").split(";") if p.startswith("rate=")), 24000)
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0, rate


def _speech_body(model: str, script: str, style: str, voice: str) -> tuple[dict, str]:
    """The request for a Gemini voice model, and the voice it will speak in."""
    speaker = voice
    if model.startswith("gemini-3.8"):
        part = {"text": script, "speechMetadata": {"style": style}}
    else:
        part = {"text": f"Read the transcript below aloud in Hindi. {style} Speak only the transcript."
                        f"\n\nTRANSCRIPT:\n{script}"}
        # Older models know only the prebuilt voices, not the library's or a designed or replicated one.
        speaker = voice if voice in PREBUILT else VOICE
    voice_config = {"prebuiltVoiceConfig": {"voiceName": speaker}} if speaker in PREBUILT else {"voice": speaker}
    speech_config = {"voiceConfig": voice_config, "languageCode": "hi-IN"}
    return {"contents": [{"parts": [part]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech_config}}, speaker


def _sarvam(script: str) -> requests.Response:
    """Sarvam's news anchor reads the script, a little faster than normal speech; it takes no delivery notes."""
    body = {"text": script, "language_code": "hi-IN", "model": SARVAM.split(":", 1)[1], "speaker": SARVAM_SPEAKER,
            "pace": 1.1, "temperature": 0.5, "speech_sample_rate": 24000}
    return requests.post(SARVAM_URL, json=body, timeout=180,
                         headers={"api-subscription-key": os.environ.get("NEWS_SARVAM_API_KEY", "")})


def speech(script: str, style: str, voice: str = VOICE, models: list[str] | None = None,
           skip: set[str] | None = None) -> tuple[np.ndarray, int, str]:
    """The script read aloud in Hindi. 3.8 models take the delivery as speech metadata; older ones as a prefix;
    Sarvam reads in its own anchor's voice."""
    errors = []
    for model in _order([m for m in voice_models(models) if not (skip and m in skip)]):
        try:
            if model == SARVAM:
                resp, speaker = _sarvam(script), SARVAM_SPEAKER
            else:
                body, speaker = _speech_body(model, script, style, voice)
                resp = _post(model, body, 300)
        except requests.RequestException as exc:
            _COOL[model] = time.time() + 600
            errors.append(f"{model}: {exc}")
            log.warning("%s failed: %s", model, errors[-1])
            continue
        if resp.status_code != 200:
            _cool(model, resp)
            errors.append(f"{model}: HTTP {resp.status_code} {_refusal(resp)}")
            log.warning("%s refused: %s", model, errors[-1])
            continue
        try:
            if model == SARVAM:
                data, mime = base64.b64decode("".join(resp.json()["audios"])), "audio/wav"
            else:
                inline = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                data, mime = base64.b64decode(inline["data"]), inline.get("mimeType", "")
        except (KeyError, IndexError, TypeError, ValueError):
            errors.append(f"{model}: no audio")
            log.warning("%s gave no audio", model)
            continue
        audio, rate = _samples(data, mime)
        log.info("speech by %s (%s): %.1f s", model, speaker, len(audio) / rate)
        return audio, rate, model
    raise Exhausted("; ".join(errors))
