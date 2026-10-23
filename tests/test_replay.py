"""tests/tools/replay.py (SYNC-AUDIT 4.1 step 9.3) on audited fixtures: the original shots block, the re-plan of the
same pool passes, offline."""
from pathlib import Path

from .test_match import SYNC
from .tools import replay


def test_replay_blocks_the_original_and_passes_the_replan():
    # Rubio (39714003987): seven map views at 67% of the picture time. Re-planned under the real-pictures ceilings
    # (2026-10-22: one map view, maps at most 20%, cards at most a third) it has no map left, and three of its six
    # beats name nothing showable: blocked before the writer's SHOWABLE retry, on cards alone (once a pass at 40%,
    # half-the-beats cards).
    r = replay.replay(SYNC / "39714003987.json")
    assert not r["original"]["pass"] and not r["replanned"]["pass"]
    assert r["original"]["map_share"] > 0.2 >= r["replanned"]["map_share"] and r["replanned"]["cards"] == 3
    assert r["original"]["map_views"] == 7 and r["replanned"]["map_views"] == 0
    # The "दोनों के बीच" beat was the Rubio/Ambani pair since dry run 39860680187 (2026-10-23): two cards, in a row.
    # One picture, one beat (Matlabnama audit R4, 2026-10-23): the Ambanis' photo is beat 2's, so it is a third card.
    assert {replay.reason(p) for p in r["replanned"]["problems"]} == {"2+ cards in a row", "cards over a third of the beats"}
    assert r["original"]["repeats"] > 0 and r["replanned"]["repeats"] == 0
    # The hand fix: maps under 1.5 of its 3 picture beats, two of them under beats naming Rubio.
    fixed = replay.replay(SYNC / "39714003987-fixed.json")
    assert "pictures: maps fill 50% of the picture time (at most 20%)" in fixed["original"]["problems"]
    assert fixed["original"]["map_share"] == 0.5 and fixed["replanned"]["map_share"] == 0.0
    assert replay.reason("pictures: beat 4 shows photo 11 (वनतारा), which the beat does not name") == \
        "picture the beat does not name"
    assert replay.reason("pictures: beat 2 shows a map though it names x, who has a photo") == \
        "map under a name with a photo"
    assert replay.reason("faceless: no photo of रेहान passed vetting") == "faceless subject"
    assert replay.shorts([str(SYNC / "39714003987.json")]) == [SYNC / "39714003987.json"]


def test_replay_reports_the_things_a_beat_would_gain():
    r = replay.replay(SYNC / "39725154704.json")  # CAPraPdXvns: "रेहान ने तिरंगे की तस्वीरें ..."
    assert (3, "Flag of India") in r["things"]
    assert r["original"]["map_views"] >= 2 and r["replanned"]["map_views"] <= 1
