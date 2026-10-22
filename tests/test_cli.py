import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from desk import cli, config, ledger, orbitwire, plan, voice
from desk.spec import Short

FIXTURE = Path(__file__).parent / "fixtures" / "wk-Q900001.json"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def made(tmp_path, monkeypatch):
    work = tmp_path / "wk-Q900001"
    work.mkdir()
    short = Short.load(FIXTURE)
    short.save(work / "short.json")
    (work / "timing.json").write_text(json.dumps({"voice": {"engine": "gemini-sulafat", "identity": "sulafat",
                                                            "preview": False}}), encoding="utf-8")
    monkeypatch.setattr(cli, "WORK", tmp_path)
    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(config, "CHANNEL_ID", "UC" + "a" * 22)
    monkeypatch.setattr(orbitwire, "fetch", lambda: {"published": [], "candidates": {}})
    return short, work


def test_a_preview_short_can_never_publish(made, monkeypatch):
    from desk import youtube

    short, work = made
    monkeypatch.setattr(youtube, "publish", lambda *a, **k: pytest.fail("uploaded a preview"))
    (work / cli.PREVIEW).write_text("x")
    with pytest.raises(ValueError, match="preview"):
        cli.publish(short.id)
    (work / cli.PREVIEW).unlink()
    (work / "timing.json").write_text(json.dumps({"voice": {"engine": "chatterbox-preview", "identity": "preview",
                                                            "preview": True}}))
    with pytest.raises(ValueError, match="preview"):
        cli.publish(short.id)
    (work / "timing.json").unlink()
    with pytest.raises(ValueError, match="voice"):
        cli.publish(short.id)


def test_a_remake_retires_the_old_video_once_the_new_one_is_public(made, monkeypatch):
    from desk import gate, youtube

    short, work = made
    short.scene.update(replaces="OLDVIDEO123", remake_of="nw-20261018-tiger-shroff-attack")
    short.save(work / "short.json")
    monkeypatch.setattr(gate, "check", lambda s: [])
    monkeypatch.setattr(cli, "publish_refusal", lambda *a: None)
    retired = []
    monkeypatch.setattr(youtube, "publish", lambda *a, **k: {"video_id": "NEWVIDEO456", "url": "u"})
    monkeypatch.setattr(youtube, "retire", lambda vid: retired.append(vid))
    cli.publish(short.id)
    row = ledger.published()[-1]
    assert retired == ["OLDVIDEO123"] and row["replaced"] == row["replaces"] == "OLDVIDEO123"
    assert row["video_id"] == "NEWVIDEO456" and row["remake_of"] == "nw-20261018-tiger-shroff-attack"


def test_a_storys_lane_audience_priority_and_series_reach_the_published_row(made, monkeypatch):
    from desk import gate, writer, youtube

    short, work = made
    monkeypatch.setattr(writer, "build", lambda target: Short.load(FIXTURE))
    monkeypatch.setattr(gate, "check", lambda s: [])
    cand = {"id": short.id, "kind": "death", "category": "death", "region": "world", "title": "x", "lane": "obituary",
            "audience": "india", "priority": 1234, "series": 3}
    made_now = cli.prepare(cand)
    assert {k: made_now.scene[k] for k in ("lane", "audience", "priority", "series")} == \
        {"lane": "obituary", "audience": "india", "priority": 1234, "series": 3}
    # A story that never went through watch() (make wiki:...) is labelled here.
    bare = cli.prepare({k: v for k, v in cand.items() if k not in ("lane", "audience", "priority", "series")})
    assert (bare.scene["lane"], bare.scene["audience"]) == ("obituary", "world") and "series" not in bare.scene
    monkeypatch.setattr(cli, "publish_refusal", lambda *a: None)
    monkeypatch.setattr(youtube, "publish", lambda *a, **k: {"video_id": "NEWVIDEO456", "url": "u"})
    made_now.save(work / "short.json")
    cli.publish(short.id)
    row = ledger.published()[-1]
    assert (row["lane"], row["audience"], row["priority"], row["series"]) == ("obituary", "india", 1234, 3)


def test_publish_refuses_while_the_channel_id_is_tbd(made, monkeypatch):
    short, work = made
    monkeypatch.setattr(config, "CHANNEL_ID", "TBD")
    assert "DESK_CHANNEL_ID" in cli.publish_refusal(short, work, datetime.now(timezone.utc))


def test_voice_preview_is_only_for_dry_runs():
    with pytest.raises(ValueError):
        cli.run(dry=False, preview=True)
    r = subprocess.run([sys.executable, "-m", "desk.cli", "run", "--voice-preview"], cwd=ROOT, capture_output=True,
                       text=True)
    assert r.returncode != 0 and "only for dry runs" in r.stderr


def test_a_scheduled_run_holds_without_a_sulafat_voice(made, monkeypatch):
    monkeypatch.setattr(voice, "ready", lambda: "hold: no Sulafat voice: test")
    monkeypatch.setattr(plan, "watch", lambda **k: pytest.fail("watched without a voice"))
    health = cli.run()
    assert health["ok"] and health["held"].startswith("hold: no Sulafat voice")
    assert ledger.load("health", {})["held"]


def test_a_scheduled_run_holds_without_a_channel_id(made, monkeypatch):
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(config, "CHANNEL_ID", "TBD")
    monkeypatch.setattr(plan, "watch", lambda **k: pytest.fail("watched without a channel"))
    assert "DESK_CHANNEL_ID" in cli.run()["held"]


def test_a_dry_run_makes_but_never_publishes_or_writes_the_ledger(made, monkeypatch):
    short, work = made
    cand = {"id": short.id, "kind": "death", "fame": 1}
    monkeypatch.setattr(plan, "watch", lambda save=True: {"candidates": [cand], "trending": [cand], "notes": []}
                        if not save else pytest.fail("dry run saved candidates"))
    monkeypatch.setattr(cli, "prepare", lambda c: short)
    made_with = []
    monkeypatch.setattr(cli, "make", lambda c, s, preview=False: made_with.append(preview) or
                        (s, {"duration": 40.0, "voice": {"engine": "chatterbox-preview"}}))
    monkeypatch.setattr(cli, "publish", lambda *a, **k: pytest.fail("published in a dry run"))
    health = cli.run(dry=True, preview=True)
    assert health.get("made", {}).get("id") == short.id and made_with == [True], health.get("trace")
    assert not (cli.ledger.STATE / "health.json").exists() and (cli.WORK / "dry-health.json").exists()


@pytest.mark.parametrize("held_only", [False, True])
def test_a_dry_run_never_previews_a_case_angle_the_live_run_would_hold(made, monkeypatch, held_only):
    short, work = made
    held = {"id": "nw-case-hurt", "case": "A case", "kind": "death", "fame": 10 ** 7,
            "case_wait": "3 of the case's angles today (IST), 3 a day"}
    other = {"id": short.id, "kind": "death", "fame": 1}
    cands = [held] if held_only else [held, other]
    monkeypatch.setattr(plan, "watch", lambda save=True: {"candidates": cands, "trending": cands, "notes": []})
    monkeypatch.setattr(plan, "lineup", lambda c, at=None: ([], ["hold nw-case-hurt: ..."]))  # outside the window
    prepared = []
    monkeypatch.setattr(cli, "prepare", lambda c: prepared.append(c["id"]) or short)
    monkeypatch.setattr(cli, "make", lambda c, s, preview=False: (s, {"duration": 40.0,
                                                                       "voice": {"engine": "chatterbox-preview"}}))
    monkeypatch.setattr(cli, "publish", lambda *a, **k: pytest.fail("published in a dry run"))
    health = cli.run(dry=True, preview=True)
    assert "nw-case-hurt" not in prepared, health.get("trace")
    assert prepared == ([] if held_only else [short.id])


def test_a_voice_hold_mid_run_stops_without_counting_a_retry(made, monkeypatch):
    short, work = made
    cand = {"id": short.id, "kind": "death", "fame": 1}
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(plan, "watch", lambda save=True: {"candidates": [cand], "trending": [cand], "notes": []})
    monkeypatch.setattr(plan, "lineup", lambda c: (c, []))
    monkeypatch.setattr(cli, "prepare", lambda c: short)

    def hold(*a, **k):
        raise voice.VoiceHold("hold: no Sulafat voice: quota")
    monkeypatch.setattr(cli, "make", hold)
    health = cli.run()
    assert health["held"] == "hold: no Sulafat voice: quota" and ledger.load("retries", {}) == {}


def test_make_marks_a_preview(made, monkeypatch):
    from desk import compose

    short, work = made
    monkeypatch.setattr(voice, "synthesize", lambda s, w, preview=False: {"voice": {"engine": "chatterbox-preview",
                                                                                     "preview": preview}})
    monkeypatch.setattr(compose, "render", lambda s, t, w: {"duration": 40.0})
    cli.make(None, short, preview=True)
    assert (work / cli.PREVIEW).exists() and Short.load(work / "short.json").scene["voice_preview"] is True
