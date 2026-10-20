import pytest

from desk import media, outlets, plan, visuals, wiki


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch, tmp_path_factory):
    """The repo's own case and remake files are live work orders; tests that need one write their own."""
    monkeypatch.setattr(plan, "CASES", tmp_path_factory.mktemp("cases"))
    monkeypatch.setattr(plan, "REMAKES", tmp_path_factory.mktemp("remakes"))


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
