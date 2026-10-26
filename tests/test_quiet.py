from datetime import datetime, timedelta, timezone

import pytest

from desk import ledger, quiet, writer

NOW = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)

# Refusals from the 25-26 Oct silence (state skipped.json / retries.json) and the gates' own wording.
SOFT = [
    "text cards: 2 beats in a row from beat 4",
    "text cards: 4 of 6 beats (at most 2)",
    "pictures: real photos fill only 33% of the Short (want at least 50%)",
    "pictures: the story's person fills only 22% of the Short (want at least 25%)",
    "beats 3,5,6 name nothing that can be shown (or only a city or state, whose map a Short shows once); SHOWABLE: x",
    "the story is about लुला, but only 1 of 6 beats name them: name लुला in at least 2 beats",
    "pictures: photo 2 (Kota) fills 40% of the Short (at most 35%)",
    "pictures: photo 1 (x) stays up 7.2 s in a row from 3.0 s (at most 6 s)",
    "pictures: photo 1 (x) stays on screen for 3 beats in a row",
    "pictures: photo 1 (x) is under 4 of 6 beats",
    "pictures: maps fill 40% of the picture time (at most 20%)",
    "pictures: 2 map views (at most 1)",
]
HARD = [
    "beat 3: the number 19 isn't backed by any sourced fact",
    "unsupported: ओडिशा में 5 जिलों के स्कूल बंद रहेंगे",
    "casualties without an agreed toll (घायलों)",
    "'CEC' is not in the English source",
    "pictures: beat 3 names Rajiv Gandhi but shows someone or something else",
    "pictures: beat 2 shows photo 4 (Film City), which the beat does not name",
    "pictures: card 3 stays up over photo 2 (x) after the cut",
    "pictures: card 2 names the place दिल्ली over another picture",
    "pictures: the title names Narendra Modi but no photo of them is on screen",
    "gate: the article is under 6 hours old; facts may still change",
    "gate: fewer than 2 independent outlets' articles name Nilgiri Mountain Railway",
    "gate: only 0 usable photos of Arnab (want 2)",
    "fact deaths: 1 independent outlet(s) report it (want 2)",
]


@pytest.mark.parametrize("p", SOFT)
def test_presentation_ceilings_are_soft(p):
    assert quiet.soft(p)


@pytest.mark.parametrize("p", HARD)
def test_truth_and_wrong_pictures_stay_hard(p):
    assert not quiet.soft(p)


def test_keep_waives_only_while_quiet(monkeypatch):
    both = SOFT[:2] + HARD[:2]
    assert quiet.keep(both) == both
    monkeypatch.setenv("DESK_QUIET", "on")
    assert quiet.keep(both) == HARD[:2]


@pytest.mark.parametrize("hours, on", [(1, False), (2.9, False), (3, True), (36, True)])
def test_quiet_after_three_hours_without_a_short(monkeypatch, hours, on):
    monkeypatch.delenv("DESK_QUIET")
    rows = [{"published_at": (NOW - timedelta(hours=hours)).isoformat()},
            {"published_at": (NOW - timedelta(hours=1)).isoformat(), "retired_at": "x"},
            {"published_at": (NOW + timedelta(hours=2)).isoformat()}]
    monkeypatch.setattr(ledger, "published", lambda: rows)
    assert quiet.active(NOW) is on


def test_quiet_word_budget(monkeypatch):
    draft = {"beats": [{"say": " ".join(["शब्द"] * 12)} for _ in range(6)]}  # 72 words, the flash-lite drafts' size
    says = " ".join(b["say"] for b in draft["beats"])
    loud = len(says.split()) <= writer.MAX_WORDS
    monkeypatch.setenv("DESK_QUIET", "on")
    assert not loud and len(says.split()) <= quiet.MAX_WORDS
    assert max(len(b["say"].split()) for b in draft["beats"]) <= quiet.MAX_BEAT_WORDS


@pytest.mark.parametrize("headline, out", [
    ("Kolkata teen, father and friend paraded naked after he was caught with 13-year-old", True),
    ("Father, 18-year-old son allegedly paraded naked over relationship with minor girl in Kolkata", True),
    ("नाबालिग से दुष्कर्म के आरोपी को उम्रकैद", True),
    ("Israeli strike kills 12 children in Gaza", False),
    ("India-US relationship: more student visas, says Rubio", False),
    ("Police assault students at Jadavpur protest", False),
    ("Sexual harassment case against minister: court summons", False),
])
def test_child_harm_stories_are_dropped(headline, out):
    from desk import plan

    assert bool(plan.child_harm({"title": "", "headlines": [headline]})) is out


def test_stale_pictures_wants_one_new_photo_when_quiet(monkeypatch):
    photos = [{"file": f"F{i}.jpg"} for i in range(4)]
    views = [[0], [1], [2], [3]]
    recent = {"F0.jpg", "F1.jpg", "F2.jpg"}
    assert writer.stale_pictures(photos, views, recent)
    monkeypatch.setenv("DESK_QUIET", "on")
    assert writer.stale_pictures(photos, views, recent) is None
    assert writer.stale_pictures(photos, views, recent | {"F3.jpg"})
