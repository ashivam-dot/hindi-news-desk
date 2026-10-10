from datetime import datetime, timezone

from desk import advisory, youtube


def test_every_committed_card_fits_above_the_captions():
    for spec in advisory.load_all():
        for beat in spec["beats"]:
            advisory.card_layer(beat["card"])


def test_station_list_is_complete_and_unique():
    spec = next(s for s in advisory.load_all() if s["id"] == "adv-delhi-cjp-2026-10-10")
    stations = [s for b in spec["beats"] if b["card"].get("big", "").startswith("बंद मेट्रो") for s in b["card"]["items"]]
    assert len(stations) == len(set(stations)) == 45


def test_pending_until_published_or_stale(monkeypatch):
    spec = {"id": "adv-x", "until": "2026-10-10T12:30:00Z"}
    monkeypatch.setattr(advisory, "load_all", lambda: [spec])
    monkeypatch.setattr(advisory.ledger, "published", lambda: [])
    assert advisory.pending(datetime(2026, 10, 10, 6, tzinfo=timezone.utc)) == [spec]
    assert advisory.pending(datetime(2026, 10, 10, 12, 30, tzinfo=timezone.utc)) == []
    monkeypatch.setattr(advisory.ledger, "published", lambda: [{"id": "adv-x"}])
    assert advisory.pending(datetime(2026, 10, 10, 6, tzinfo=timezone.utc)) == []


def test_description_lists_the_closures_and_says_how_it_was_made():
    spec = next(s for s in advisory.load_all() if s["id"] == "adv-delhi-cjp-2026-10-10")
    text = youtube.description(advisory.short_of(spec), {"engine": "gemini-sulafat"})
    assert "रिठाला" in text and "धौला कुआं" in text and "Wikimedia" not in text
    assert len(text.encode()) <= youtube.DESCRIPTION_BYTES


def test_description_over_the_byte_limit_fails_closed():
    spec = next(s for s in advisory.load_all() if s["id"] == "adv-delhi-cjp-2026-10-10")
    long = advisory.short_of({**spec, "summary": "दिल्ली " * 900})
    try:
        youtube.description(long, {"engine": "gemini-sulafat"})
    except ValueError:
        return
    raise AssertionError("an over-long description must not reach the API")
