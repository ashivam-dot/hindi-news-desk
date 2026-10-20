import pytest

from desk import media, outlets, visuals, wiki


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
    monkeypatch.setattr(visuals, "cast_for", lambda *args, **kwargs: [])
    yield
    outlets.reset()
