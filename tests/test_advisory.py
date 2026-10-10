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


def test_a_photo_advisory_names_a_photo_for_every_beat():
    photo_specs = [s for s in advisory.load_all() if any(b.get("photo") for b in s["beats"])]
    assert photo_specs
    for spec in photo_specs:
        assert all(b.get("photo", "").startswith("File:") for b in spec["beats"])


def test_v2_replaces_the_plain_advisory_and_credits_its_photos():
    spec = next(s for s in advisory.load_all() if s["id"] == "adv-delhi-cjp-2026-10-10-v2")
    short = advisory.short_of(spec)
    assert short.scene["replaces"] == "TYsCL-64fSM"
    short.scene["photos"] = [{"author": f"Author {i}", "license": "CC BY-SA 4.0" if i % 3 else "CC BY 4.0"}
                             for i in range(len(spec["beats"]))]
    text = youtube.description(short, {"engine": "gemini-sulafat"})
    assert "Author 0, Author 3, Author 6 (CC BY 4.0)" in text and "तस्वीरें असली हैं" in text
    assert len(text.encode()) <= youtube.DESCRIPTION_BYTES


def test_a_card_unrolls_from_the_top():
    card = advisory.card_layer({"kind": "points", "big": "क्या करें", "lines": ["एक", "दो", "तीन"]}, advisory.GLASS)
    _, a = advisory._unrolled(card, 0.3)
    assert a[10].max() > 0 and a[-10].max() == 0
    assert advisory._unrolled(card, 1.0) is card


def test_frames_without_photos_keep_the_plain_backdrop():
    spec = next(s for s in advisory.load_all() if s["id"] == "adv-delhi-cjp-2026-10-10")
    short = advisory.short_of(spec)
    backdrops = advisory.Backdrops(short)
    shots = [{"start": i * 2.0, "end": (i + 1) * 2.0, "photo": None, "card": advisory.card_layer(b.card),
              "motion": None} for i, b in enumerate(short.beats)]
    frame = advisory.frame_at(2.05, shots, backdrops, [None, *([(advisory.np.zeros((2, 2, 3)),
                                                                   advisory.np.zeros((2, 2, 1)))] * 2)])
    assert frame.shape == (advisory.H, advisory.W, 3)


def test_description_over_the_byte_limit_fails_closed():
    spec = next(s for s in advisory.load_all() if s["id"] == "adv-delhi-cjp-2026-10-10")
    long = advisory.short_of({**spec, "summary": "दिल्ली " * 900})
    try:
        youtube.description(long, {"engine": "gemini-sulafat"})
    except ValueError:
        return
    raise AssertionError("an over-long description must not reach the API")
