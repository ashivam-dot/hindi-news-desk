import pytest
import requests

from desk import gemini

KEY = "test-key-never-shown"
SCHEMA = {"type": "object", "required": ["answer"]}


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def ok(text):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True}, {"text": text}]}}]})


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setattr(gemini, "models", lambda: ["gemini-3.8-flash", "gemini-3.7-flash"])
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "_refused", False)
    gemini._spent.clear()
    gemini._last.clear()
    yield
    gemini._spent.clear()


def test_a_stalled_model_is_skipped_for_the_rest_of_the_run(monkeypatch):
    calls = []

    def post(url, headers, json, timeout):
        calls.append(url)
        if "3.8-flash" in url:
            raise requests.ReadTimeout()
        return ok('{"answer": 1}')
    monkeypatch.setattr(gemini.requests, "post", post)
    assert gemini.chat([{"role": "user", "content": "x"}], SCHEMA) == ({"answer": 1}, "gemini-3.7-flash")
    assert gemini.chat([{"role": "user", "content": "y"}], SCHEMA) == ({"answer": 1}, "gemini-3.7-flash")
    assert sum("3.8-flash" in u for u in calls) == 1 and "gemini-3.8-flash" in gemini._spent


def test_a_daily_quota_moves_on_and_a_minute_quota_is_waited_out(monkeypatch):
    answers = {"3.8": [Resp(429, {"error": {"details": [{"violations": [{"quotaId": "RequestsPerDay"}]}]}})],
               "3.7": [Resp(429, {"error": {"details": [{"@type": "x.RetryInfo", "retryDelay": "5s"}]}}),
                       ok("```json\n{\"answer\": 2}\n```")]}

    def post(url, headers, json, timeout):
        assert headers == {"x-goog-api-key": KEY}
        return answers["3.8" if "3.8" in url else "3.7"].pop(0)
    monkeypatch.setattr(gemini.requests, "post", post)
    assert gemini.chat([{"role": "user", "content": "x"}], SCHEMA) == ({"answer": 2}, "gemini-3.7-flash")
    assert gemini._spent == {"gemini-3.8-flash"}


def test_a_refused_key_stops_everything_and_is_never_echoed(monkeypatch):
    monkeypatch.setattr(gemini.requests, "post", lambda *a, **k: Resp(403, {"error": {"message": f"bad {KEY}"}}))
    with pytest.raises(gemini.Unavailable) as exc:
        gemini.chat([{"role": "user", "content": "x"}], SCHEMA)
    assert KEY not in str(exc.value) and not gemini.available()
