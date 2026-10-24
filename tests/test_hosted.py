import pytest

from desk import gemini, hosted, writer

KEY = "test-key-never-shown"
SCHEMA = {"type": "object", "required": ["answer"]}


class Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload or {}, headers or {}

    def json(self):
        return self._payload


def ok(text):
    return Resp(200, {"choices": [{"message": {"content": text}}]})


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    for _, env, _ in hosted.PROVIDERS.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(hosted.time, "sleep", lambda s: None)
    hosted._spent.clear()
    hosted._refused.clear()
    hosted._discovered.clear()
    yield
    hosted._spent.clear()
    hosted._refused.clear()
    hosted._discovered.clear()


def test_no_key_means_no_hosted_tier():
    assert not hosted.available()
    with pytest.raises(hosted.Unavailable):
        hosted.chat([{"role": "user", "content": "x"}], SCHEMA)


def test_only_large_models_are_picked_in_preference_order():
    ids = ["llama-3.1-8b-instant", "qwen/qwen3-32b", "openai/gpt-oss-120b", "whisper-large-v3", "openai/gpt-oss-20b"]
    assert hosted.pick("groq", ids) == ["openai/gpt-oss-120b", "qwen/qwen3-32b"]
    assert hosted.pick("openrouter", ["qwen/qwen3-235b", "qwen/qwen3-235b:free"]) == ["qwen/qwen3-235b:free"]


def test_a_quota_moves_on_and_the_key_is_never_echoed(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    monkeypatch.setattr(hosted, "models", lambda p: ["openai/gpt-oss-120b", "qwen/qwen3-32b"])
    sent = []

    def post(url, timeout, headers, json):
        assert headers == {"Authorization": f"Bearer {KEY}"}
        assert json["response_format"] == {"type": "json_object"} and "JSON schema" in json["messages"][-1]["content"]
        sent.append(json["model"])
        if json["model"] == "openai/gpt-oss-120b":
            return Resp(429, headers={"retry-after": "600"})
        return ok('```json\n{"answer": 3}\n```')
    monkeypatch.setattr(hosted.requests, "post", post)
    assert hosted.chat([{"role": "user", "content": "x"}], SCHEMA) == ({"answer": 3}, "groq:qwen/qwen3-32b")
    assert hosted.chat([{"role": "user", "content": "y"}], SCHEMA) == ({"answer": 3}, "groq:qwen/qwen3-32b")
    assert sent.count("openai/gpt-oss-120b") == 1

    monkeypatch.setattr(hosted.requests, "post", lambda *a, **k: Resp(401, {"error": f"bad {KEY}"}))
    hosted._spent.clear()
    with pytest.raises(hosted.Unavailable) as exc:
        hosted.chat([{"role": "user", "content": "x"}], SCHEMA)
    assert KEY not in str(exc.value) and not hosted.available()


def test_the_pen_tries_flash_then_hosted_then_lite(monkeypatch):
    asked = []

    def gem(messages, schema, temperature, max_tokens, tier=None):
        asked.append(f"gemini-{tier}")
        if tier == "flash":
            raise gemini.Unavailable("429")
        return {"answer": "lite"}, "gemini-3.5-flash-lite"

    def host(messages, schema, temperature, max_tokens):
        asked.append("hosted")
        raise hosted.Unavailable("429")
    monkeypatch.setattr(gemini, "available", lambda: True)
    monkeypatch.setattr(gemini, "chat", gem)
    monkeypatch.setattr(hosted, "available", lambda: True)
    monkeypatch.setattr(hosted, "chat", host)
    pen = writer.Pen()
    assert pen.chat([{"role": "user", "content": "x"}], SCHEMA) == {"answer": "lite"}
    assert asked == ["gemini-flash", "hosted", "gemini-lite"] and pen.used == ["gemini-3.5-flash-lite"]


def test_gemini_keeps_to_its_tier(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setattr(gemini, "_refused", False)
    monkeypatch.setattr(gemini, "models", lambda: ["gemini-3.8-flash", "gemini-3.5-flash-lite"])
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    gemini._spent.clear()
    gemini._last.clear()
    urls = []

    def post(url, headers, json, timeout):
        urls.append(url)
        return Resp(200, {"candidates": [{"content": {"parts": [{"text": '{"answer": 1}'}]}}]})
    monkeypatch.setattr(gemini.requests, "post", post)
    assert gemini.chat([{"role": "user", "content": "x"}], SCHEMA, tier="lite")[1] == "gemini-3.5-flash-lite"
    assert gemini.chat([{"role": "user", "content": "x"}], SCHEMA, tier="flash")[1] == "gemini-3.8-flash"
    assert gemini.lite("gemini-flash-lite-latest") and not gemini.lite("gemini-flash-latest")
