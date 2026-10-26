import pytest
import requests

from desk import media, outlets, plan, quiet, things, visuals, wiki


class Offline(RuntimeError):
    """A test reached the network. Not a requests error, so net.get does not back off and retry: the test fails (or
    its code's own `except Exception` degrades) at once instead of hanging in a retry loop or passing on whatever
    Wikipedia returns that day (review round 1: three real-pictures tests called en.wikipedia.org)."""


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch, tmp_path_factory):
    """The repo's own case and remake files are live work orders; tests that need one write their own."""
    monkeypatch.setattr(plan, "CASES", tmp_path_factory.mktemp("cases"))
    monkeypatch.setattr(plan, "REMAKES", tmp_path_factory.mktemp("remakes"))


@pytest.fixture(autouse=True)
def loud_channel(monkeypatch):
    """Every gate as a busy channel has it; test_quiet turns quiet mode on itself."""
    monkeypatch.setenv("DESK_QUIET", "off")
    quiet.reset()
    yield
    quiet.reset()


@pytest.fixture(autouse=True)
def offline_outlets(monkeypatch):
    """No test reads a live outlet feed, article or Openverse; tests that need them give fixtures."""
    def offline(*args, **kwargs):
        raise ConnectionError("offline in tests")

    outlets.reset()
    monkeypatch.setattr(outlets, "_feed", offline)
    monkeypatch.setattr(outlets, "_extract", offline)
    monkeypatch.setattr(media, "openverse_for", lambda *args, **kwargs: [])
    monkeypatch.setattr(wiki, "hindi_spellings", lambda names: {})
    monkeypatch.setattr(wiki, "hindi_readings", lambda words: {})
    monkeypatch.setattr(visuals, "cast_for", lambda *args, **kwargs: [])
    # The lookups cast_for makes besides resolve (a topic, a thing, a lexicon noun's item): None unless a test fakes
    # them, so a test that runs the real cast_for never reaches Wikipedia through them.
    monkeypatch.setattr(visuals, "resolve_topic", lambda *args, **kwargs: None)
    monkeypatch.setattr(things, "resolve_thing", lambda *args, **kwargs: None)
    monkeypatch.setattr(things, "lookup", lambda *args, **kwargs: None)
    yield
    outlets.reset()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test reaches the network: every HTTP request raises Offline at once."""
    def offline(self, method, url, *args, **kwargs):
        raise Offline(f"network in tests: {method} {url}")

    monkeypatch.setattr(requests.Session, "request", offline)
