"""Shown is said (SYNC-AUDIT 4.1 step 7): the gate fails any picture the voice does not name, at prepare, after the
render (render.json's views, for the time shares) and at publish. Three audits of 23 Shorts (2026-10-22) found 98 of
145 beats showing something the voice was not talking about; the one clean Short (Jaishankar) must still pass."""
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from desk import cli, compose, config, gate, match, voice

from .test_cli import made  # noqa: F401
from .test_match import applied, planned, rehosted, short


def beats_flagged(problems):
    return {int(w) for p in problems for w in re.findall(r"(?:beat|card) (\d+) ", p)}


def test_rubio_artifact_blocked():
    # 39714003987: his 1989 yearbook photo, Mukesh Ambani at a gala, the Vantara map under crude oil and data centres.
    bad = gate.said_is_shown(short("39714003987"))
    # Beat 4's "card 4 names वनतारा" is a dateline now (a place with only a map, match.problems): beats 1-3, 5, 6.
    assert beats_flagged(bad) == {1, 2, 3, 5, 6}
    assert "pictures: maps fill 67% of the picture time (at most 20%)" in bad and "pictures: 7 map views (at most 1)" in bad


def test_rubio_hand_fix_is_blocked_now():
    s = short("39714003987")
    # The hand fix cut to the Jamnagar map in beat 1 and the Vantara map in beat 4, both under beats naming Rubio:
    # it passed at the 40% ceiling; since 2026-10-22 (real pictures: one map a Short, never under a beat naming a
    # person with a photo, maps at most 20%) it is blocked. Re-planned, no picture problem is left: only the three
    # beats that name nothing showable (a third is the card ceiling), which the writer's SHOWABLE retry rewrites.
    shots = [("photo:7/8", "", "जामनगर"), ("photo:10", "", ""), ("photo:8", match.CARD, ""),
             ("photo:4/11", "", "वनतारा"), ("photo:11", match.CARD, ""), ("photo:4", match.CARD, "")]
    fixed = replace(s, beats=[replace(b, shot=sh, plate=pl, cut_word=w) for b, (sh, pl, w) in zip(s.beats, shots)])
    bad = gate.said_is_shown(fixed)
    assert "pictures: beat 1 shows a map though it names @subject, who has a photo" in bad
    assert "pictures: beat 4 shows a map though it names @subject, who has a photo" in bad
    assert "pictures: 2 map views (at most 1)" in bad
    assert "pictures: maps fill 50% of the picture time (at most 20%)" in gate.said_is_shown(short("39714003987-fixed"))
    rows, _ = planned(s)
    # And the "दोनों के बीच" pair, its Ambani photo beat 2's (R4, 2026-10-23: one picture, one beat): a third card.
    assert gate.said_is_shown(applied(s, rows)) == ["text cards: 2 beats in a row from beat 5",
                                                    "text cards: 3 of 6 beats (at most 2)"]
    # As rendered: Rubio to 20.60 s, the Vantara map from "वनतारा"; a card's backdrop is not picture time: 5.56 s of
    # maps in 17.61 s (32%, once under 40%).
    views = [{"start": 0.35, "end": 3.5, "photo": 7, "beat_k": 0}, {"start": 3.5, "end": 6.14, "photo": 8, "beat_k": 0},
             {"start": 6.14, "end": 12.1, "photo": 10, "beat_k": 1},
             {"start": 12.1, "end": 17.66, "photo": 8, "beat_k": 2, "plate": match.CARD},
             {"start": 17.66, "end": 20.6, "photo": 4, "beat_k": 3}, {"start": 20.6, "end": 23.52, "photo": 11, "beat_k": 3},
             {"start": 23.52, "end": 29.46, "photo": 11, "beat_k": 4, "plate": match.CARD},
             {"start": 29.46, "end": 35.47, "photo": 4, "beat_k": 5, "plate": match.CARD}]
    assert "pictures: maps fill 32% of the picture time (at most 20%)" in gate.shown_is_said(fixed, views)
    # The same Short cut to the Vantara map at the middle of beat 4 and held it for beats 5 and 6: more still.
    late = views[:4] + [{"start": 17.66, "end": 18.0, "photo": 4, "beat_k": 3},
                        {"start": 18.0, "end": 23.52, "photo": 11, "beat_k": 3}]
    assert any("maps fill" in p for p in gate.shown_is_said(fixed, late))


def test_accused_line_never_victim():
    # "आरोपियों से पूछताछ..." over Tiger Shroff on a film set (39560243173 b5); "कोटा पुलिस ने ... इन्हें दबोच लिया"
    # over Tiger Shroff in Bandra (39503061196 b4): the accused, pictured as the victim.
    for name, k, victim in (("39560243173", 4, 6), ("39503061196", 3, 1)):
        s = short(name)
        assert any(p.startswith(f"pictures: beat {k + 1} shows photo {victim} ") for p in gate.said_is_shown(s))
        rows, _ = planned(s)
        assert rows[k]["plate"] == match.CARD  # it names no one a picture can show
        assert not any(f"beat {k + 1} shows" in p for p in gate.said_is_shown(applied(s, rows)))
    assert match.plain(short("39560243173").beats[4].text)  # and on the plain background, no face blurred behind


def test_min_visuals_not_met_by_maps():
    # Three maps of one city are one picture: Jamnagar, Vantara in Jamnagar, Vantara up close.
    s = short("39714003987-fixed")
    shots = ["photo:8", "photo:8", "photo:8", "photo:11/12", "photo:11", "photo:4"]
    plates = ["", "", match.CARD, "", match.CARD, match.CARD]
    maps = replace(s, beats=[replace(b, shot=sh, plate=pl) for b, sh, pl in zip(s.beats, shots, plates)],
                   scene=s.scene | {"min_visuals": 3})
    assert "pictures: only 1 different pictures once a place's maps count as one (want 3)" in gate.said_is_shown(maps)
    assert not any("count as one" in p for p in gate.said_is_shown(replace(rehosted(s), scene=s.scene | {"min_visuals": 3})))


def test_jaishankar_clean_short_still_passes():
    # The audits' one clean Short (0 of 7): only beat 7's known strictness ("आगे इस दौरे पर दोनों देशों के बीच..."
    # names no one) is flagged, and planned it is a card and passes.
    s = short("39411111185")
    bad = gate.said_is_shown(s)
    # Since 2026-10-22 also beat 2's Mumbai map under "मार्को रुबियो", who has a photo; planned, it is his photo.
    assert bad[0].startswith("pictures: beat 2 shows a map though it names")
    # Since 2026-10-22 (dry run 39827809002) also beat 6's "Secretary Blinken Meets with ... Jaishankar": Blinken's
    # face under the Padma Shri line (was: only beat 7).
    # Since 2026-10-23 (Matlabnama audit R2, R4) beat 4's handshake crop and three portraits on two beats each.
    assert bad[1:] and all("beat 7 shows" in p or p.startswith(("pictures: beat 6 shows photo 7",
                                                                 "pictures: beat 4 shows photo 4"))
                           and "a photo with someone else" in p or " on beats " in p for p in bad[1:])
    rows, _ = planned(s)
    assert gate.said_is_shown(applied(s, rows)) == []


def test_the_legacy_matcher_skips_the_gate(monkeypatch):
    monkeypatch.setattr(config, "MATCHER", "legacy")
    assert gate.shown_is_said(short("39714003987")) == []


def test_shown_is_said_problems_are_retried():
    jantar = short("39708703684")
    problems = gate.said_is_shown(short("39714003987")) + gate.said_is_shown(applied(jantar, planned(jantar)[0]))
    assert problems and all(any(m in p for m in cli.RETRYABLE) for p in problems)


def test_make_gates_the_render(made, monkeypatch):  # noqa: F811
    s, work = made
    s.scene["photos"][1] = s.scene["photos"][1] | {"role": "map", "who": "वाराणसी"}  # b2 names it: allowed, briefly
    monkeypatch.setattr(voice, "synthesize", lambda sh, w, preview=False: {"voice": {"engine": "gemini-sulafat"}})
    views = [{"start": 0.0, "end": 1.0, "photo": 0, "beat_k": 0, "plate": ""},
             {"start": 1.0, "end": 9.0, "photo": 1, "beat_k": 1, "plate": ""}]
    monkeypatch.setattr(compose, "render", lambda sh, t, w: {"duration": 40.0, "views": views})
    with pytest.raises(ValueError, match="gate: .*pictures: maps fill 89%"):
        cli.make(None, s)
    assert cli.rendered_views(work) == views  # written before the gate: the review reads what was on screen
    monkeypatch.setattr(compose, "render", lambda sh, t, w: {"duration": 40.0, "views": views[:1]})
    monkeypatch.setattr(match, "ONE_SHARE", 1.0)  # a one-view render: this test is about the maps' share only
    assert cli.make(None, s)[1]["views"] == views[:1]
    assert cli.rendered_views(Path(work.parent / "none")) is None


def test_publish_reruns_the_gate_on_the_render(made, monkeypatch):  # noqa: F811
    from desk import youtube

    s, work = made
    s.scene["photos"][1] = s.scene["photos"][1] | {"role": "map", "who": "वाराणसी"}
    s.save(work / "short.json")  # 2 of 7 beats show the map: under 40% by beats, 89% of the time as rendered
    monkeypatch.setattr(youtube, "publish", lambda *a, **k: pytest.fail("published past the gate"))
    views = [{"start": 0.0, "end": 1.0, "photo": 0, "beat_k": 0, "plate": ""},
             {"start": 1.0, "end": 9.0, "photo": 1, "beat_k": 1, "plate": ""}]
    (work / "render.json").write_text(json.dumps({"views": views}), encoding="utf-8")
    with pytest.raises(ValueError, match="maps fill 89%"):
        cli.publish(s.id)
