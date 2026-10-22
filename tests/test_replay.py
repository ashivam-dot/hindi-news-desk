"""tests/tools/replay.py (SYNC-AUDIT 4.1 step 9.3) on audited fixtures: the original shots block, the re-plan of the
same pool passes, offline."""
from pathlib import Path

from .test_match import SYNC
from .tools import replay


def test_replay_blocks_the_original_and_passes_the_replan():
    r = replay.replay(SYNC / "39714003987.json")
    assert not r["original"]["pass"] and r["replanned"]["pass"], r["replanned"]["problems"]
    assert r["original"]["map_share"] > 0.4 >= r["replanned"]["map_share"] and r["replanned"]["cards"] == 3
    assert replay.replay(SYNC / "39714003987-fixed.json")["original"]["pass"]
    assert replay.reason("pictures: beat 4 shows photo 11 (वनतारा), which the beat does not name") == \
        "picture the beat does not name"
    assert replay.shorts([str(SYNC / "39714003987.json")]) == [SYNC / "39714003987.json"]
