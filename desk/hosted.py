"""Free hosted open models (Groq, Mistral, NVIDIA NIM, OpenRouter's free models) behind Gemini Flash: the writer's
second tier, ahead of Gemini Flash Lite, which ignores the length and picture rules (dry runs of 2026-10-23).

Each provider is used only when its key is set (GROQ_API_KEY, MISTRAL_API_KEY, NVIDIA_API_KEY, OPENROUTER_API_KEY).
A key travels only in the Authorization header; it is never logged, printed or written anywhere. Models are
discovered at run time (GET /models) and only the large ones in PREFER are used, best first. A 429 that asks for a
short wait is waited out once; anything longer, or a model that rejects the request, moves on to the next model.
"""
from __future__ import annotations

import json
import logging
import os
import time

import requests

from .gemini import _json

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY",
             ("openai/gpt-oss-120b", "moonshotai/kimi-k2", "meta-llama/llama-4-maverick", "qwen/qwen3",
              "llama-3.3-70b")),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", ("mistral-large-latest", "mistral-medium-latest")),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY",
               ("deepseek-ai/deepseek-v4", "moonshotai/kimi-k2", "qwen/qwen3", "meta/llama-4-maverick",
                "openai/gpt-oss-120b")),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                   ("deepseek/deepseek", "moonshotai/kimi-k2", "qwen/qwen3", "openai/gpt-oss-120b",
                    "meta-llama/llama-4-maverick")),
}
PER_PROVIDER = 3
MAX_WAIT = 30.0
READ_TIMEOUT = 180
log = logging.getLogger("desk.hosted")

_spent: set[str] = set()
_refused: set[str] = set()
_discovered: dict[str, list[str]] = {}


class Unavailable(RuntimeError):
    """No hosted model can answer now: no key set, keys refused, or every model out of quota."""


def key(provider: str) -> str | None:
    return os.environ.get(PROVIDERS[provider][1]) or None


def providers() -> list[str]:
    return [p for p in PROVIDERS if key(p) and p not in _refused]


def available() -> bool:
    return bool(providers())


def pick(provider: str, ids: list[str]) -> list[str]:
    """The provider's large models from a /models answer, in PREFER order (OpenRouter: only its free ones)."""
    prefer = PROVIDERS[provider][2]
    if provider == "openrouter":
        ids = [i for i in ids if i.endswith(":free")]
    ranked = sorted((n, i) for i in dict.fromkeys(ids)
                    for n, p in enumerate(prefer) if i.startswith(p))
    seen: list[str] = []
    for _, i in ranked:
        if i not in seen:
            seen.append(i)
    return seen[:PER_PROVIDER]


def models(provider: str) -> list[str]:
    if provider not in _discovered:
        base = PROVIDERS[provider][0]
        ids: list[str] = []
        try:
            r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key(provider)}"}, timeout=30)
            if r.status_code in (401, 403):
                _refused.add(provider)
            elif r.status_code == 200:
                ids = [m.get("id", "") for m in r.json().get("data", [])]
        except (requests.RequestException, ValueError):
            pass
        _discovered[provider] = pick(provider, ids)
        log.info("%s models: %s", provider, ", ".join(_discovered[provider]) or "(none usable)")
    return list(_discovered[provider])


def _body(model: str, messages: list[dict], schema: dict | None, temperature: float, max_tokens: int) -> dict:
    messages = list(messages)
    body = {"model": model, "temperature": temperature, "max_tokens": max(max_tokens, 4096)}
    if schema:
        messages.append({"role": "system", "content": "Answer with one JSON object, nothing else, matching this "
                                                      "JSON schema:\n" + json.dumps(schema, ensure_ascii=False)})
        body["response_format"] = {"type": "json_object"}
    body["messages"] = messages
    return body


def _retry_after(r) -> float | None:
    try:
        return float(r.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None


def chat(messages: list[dict], schema: dict | None = None, temperature: float = 0.7,
         max_tokens: int = 4096) -> tuple[dict | str, str]:
    """(answer, "provider:model") from the first hosted model that answers. Raises Unavailable when none can."""
    errors = []
    for provider in providers():
        base = PROVIDERS[provider][0]
        for model in models(provider):
            name = f"{provider}:{model}"
            if name in _spent or provider in _refused:
                continue
            for attempt in range(2):
                started = time.monotonic()
                try:
                    r = requests.post(f"{base}/chat/completions", timeout=(20, READ_TIMEOUT),
                                      headers={"Authorization": f"Bearer {key(provider)}"},
                                      json=_body(model, messages, schema, temperature, max_tokens))
                except requests.Timeout:
                    _spent.add(name)
                    errors.append(f"{name}: timeout")
                    break
                except requests.RequestException as exc:
                    errors.append(f"{name}: {type(exc).__name__}")
                    time.sleep(5)
                    continue
                log.info("%s: HTTP %s in %.0f s", name, r.status_code, time.monotonic() - started)
                if r.status_code == 200:
                    try:
                        text = (r.json()["choices"][0]["message"].get("content") or "").strip()
                    except (ValueError, KeyError, IndexError, TypeError):
                        text = ""
                    if not text:
                        errors.append(f"{name}: empty answer")
                        break
                    if not schema:
                        return text, name
                    try:
                        answer = _json(text)
                    except (json.JSONDecodeError, ValueError):
                        errors.append(f"{name}: malformed JSON")
                        continue
                    if isinstance(answer, dict) and all(k in answer for k in schema.get("required", [])):
                        return answer, name
                    errors.append(f"{name}: JSON missing required fields")
                    continue
                if r.status_code in (401, 403):
                    _refused.add(provider)
                    errors.append(f"{provider}: key refused (HTTP {r.status_code})")
                    break
                if r.status_code == 429:
                    wait = _retry_after(r)
                    if attempt == 0 and wait is not None and wait <= MAX_WAIT:
                        time.sleep(wait + 1)
                        continue
                    log.info("%s is out of free quota for now; next model", name)
                _spent.add(name)
                errors.append(f"{name}: HTTP {r.status_code}")
                break
    raise Unavailable("no hosted model answered: " + ("; ".join(errors[-6:]) or "no key set"))
