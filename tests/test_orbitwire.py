import json
from datetime import datetime, timedelta, timezone

import pytest

from desk import cli, config, ledger, orbitwire, plan
from desk.spec import Short

AT = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)  # 14:30 IST


def state(published=(), top=None):
    rows = [{"id": i, "published_at": t, "url": f"https://www.youtube.com/shorts/{i}", "title": i} for i, t in published]
    cands = {"at": "2026-10-10T08:37:00+00:00", "candidates": [top] if top else []}
    return {"published": rows, "candidates": cands}


@pytest.mark.parametrize("story_id, qid", [("wk-Q42", "Q42"), ("wk-Q42-2026w41", "Q42"), ("wk-Q42-p2", "Q42"),
                                           ("eq-us6000u0xi", None), ("wk-Q42x", None), ("", None)])
def test_qid_comes_from_wk_ids(story_id, qid):
    assert orbitwire.qid_of(story_id) == qid


def test_published_within_seven_days_is_shared():
    s = state([("wk-Q42-2026w41", "2026-10-05T10:00:00+00:00")])
    ov = orbitwire.overlap("Q42", s, AT)
    assert ov["status"] == "published" and ov["orbitwire_id"] == "wk-Q42-2026w41"
    assert orbitwire.overlap("Q42", s, AT + timedelta(days=3)) is None
    assert orbitwire.overlap("Q43", s, AT) is None
    assert orbitwire.overlap(None, s, AT) is None


def test_newest_release_and_scheduled_ones_count():
    s = state([("wk-Q42", "2026-10-04T10:00:00+00:00"), ("wk-Q42-p2", "2026-10-10T12:00:00+00:00")])
    ov = orbitwire.overlap("Q42", s, AT)
    assert ov["status"] == "scheduled" and ov["orbitwire_published_at"] == "2026-10-10T12:00:00+00:00"


def test_orbitwire_top_candidate_is_shared():
    s = state(top={"id": "wk-Q7-2026w41", "qid": "Q7", "title": "Seven"})
    assert orbitwire.overlap("Q7", s, AT)["status"] == "top_candidate"
    s = state(top={"id": "wk-Q7-2026w41", "title": "Seven"})
    assert orbitwire.overlap("Q7", s, AT)["status"] == "top_candidate"
    assert orbitwire.overlap("Q8", s, AT) is None


def test_high_profile():
    assert orbitwire.high_profile({"fame": 450_000}, [])
    assert orbitwire.high_profile({"fame": 150_000}, [10_000] * 9 + [150_000])
    assert orbitwire.high_profile({"fame": 90_000}, [1_000] * 9 + [90_000]) is None
    assert orbitwire.high_profile({"fame": 50_000, "region": "india", "hindi_news": 3}, [])
    assert orbitwire.high_profile({"fame": 50_000, "region": "world", "hindi_news": 5}, []) is None


def test_waits_three_hours_after_orbitwire_and_for_its_top_candidate():
    ov = {"status": "published", "orbitwire_published_at": "2026-10-10T07:00:00+00:00"}
    assert "3 h" in orbitwire.wait(ov, AT)
    assert orbitwire.wait(ov, AT + timedelta(hours=1)) is None
    sched = {"status": "scheduled", "orbitwire_published_at": "2026-10-10T12:00:00+00:00"}
    assert orbitwire.wait(sched, AT) and orbitwire.wait(sched, AT + timedelta(hours=6)) is None
    assert orbitwire.wait({"status": "top_candidate"}, AT)
    assert orbitwire.wait(None, AT) is None


def test_angles():
    assert orbitwire.angle_for("death", india_link=True) == "india"
    assert orbitwire.angle_for("death", india_link=False) == "timeline"
    assert orbitwire.angle_for("incident", india_link=False) == "explainer"
    assert orbitwire.angle_for("protest", india_link=False) == "explainer"
    assert orbitwire.title_fits("भूकंप: आगे क्या होगा", "next")
    assert not orbitwire.title_fits("भूकंप की कहानी", "next")


def test_desk_skips_shared_stories_unless_high_profile(monkeypatch):
    s = state([("wk-Q1", "2026-10-09T10:00:00+00:00"), ("wk-Q2-2026w41", "2026-10-09T11:00:00+00:00")])
    monkeypatch.setattr(orbitwire, "fetch", lambda: s)
    cands = [{"id": "wk-Q1", "qid": "Q1", "kind": "death", "fame": 60_000, "india_link": False},
             {"id": "wk-Q2-2026w41", "qid": "Q2", "kind": "incident", "category": "protest", "fame": 900_000,
              "india_link": True},
             {"id": "wk-Q3", "qid": "Q3", "kind": "incident", "fame": 80_000}]
    kept, notes = plan.apply_orbitwire(cands, AT)
    assert [c["id"] for c in kept] == ["wk-Q2-2026w41", "wk-Q3"]
    assert any("skip wk-Q1" in n and "not high-profile" in n for n in notes)
    ov = kept[0]["orbitwire"]
    assert ov["angle"] == "india" and ov["high_profile"] and ov["orbitwire_id"] == "wk-Q2-2026w41"
    assert "orbitwire" not in kept[1]


def test_unreadable_orbitwire_state_holds_everything(monkeypatch):
    def broken():
        raise OSError("raw.githubusercontent.com unreachable")
    monkeypatch.setattr(orbitwire, "fetch", broken)
    kept, notes = plan.apply_orbitwire([{"id": "wk-Q3", "qid": "Q3", "fame": 1}], AT)
    assert kept == [] and "hold all" in notes[0]


def test_fetch_fails_closed_on_a_bad_ledger(monkeypatch):
    monkeypatch.setattr(orbitwire.net, "get", lambda url, **k: "{}" if url.endswith("published.json") else "{}")
    with pytest.raises(ValueError):
        orbitwire.fetch()
    # An unreadable candidates.json would hide Orbitwire's next story: that fails closed too.
    monkeypatch.setattr(orbitwire.net, "get", lambda url, **k: "[]" if url.endswith("published.json") else "not json")
    with pytest.raises(ValueError):
        orbitwire.fetch()
    monkeypatch.setattr(orbitwire.net, "get", lambda url, **k: "[]" if url.endswith("published.json") else "{}")
    assert orbitwire.fetch() == {"published": [], "candidates": {}}


def test_lineup_holds_a_shared_story_until_three_hours_after_orbitwire(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    ov = {"status": "published", "orbitwire_published_at": "2026-10-10T07:30:00+00:00", "angle": "india"}
    cand = {"id": "wk-Q2", "kind": "incident", "region": "india", "fame": 900_000,
            "news_at": "2026-10-10T08:00:00+00:00", "orbitwire": ov}
    ready, notes = plan.lineup([cand], AT)
    assert ready == [] and any("3 h after" in n for n in notes)
    ready, _ = plan.lineup([cand], AT + timedelta(hours=2))
    assert [c["id"] for c in ready] == ["wk-Q2"]


@pytest.fixture
def made(tmp_path, monkeypatch):
    from pathlib import Path

    work = tmp_path / "wk-Q900001"
    work.mkdir()
    short = Short.load(Path(__file__).parent / "fixtures" / "wk-Q900001.json")
    short.save(work / "short.json")
    (work / "timing.json").write_text(json.dumps({"voice": {"engine": "gemini-sulafat", "identity": "sulafat",
                                                            "preview": False}}), encoding="utf-8")
    monkeypatch.setattr(config, "CHANNEL_ID", "UC" + "a" * 22)
    return short, work


def test_publish_rechecks_orbitwire(made, monkeypatch):
    short, work = made
    monkeypatch.setattr(orbitwire, "fetch", lambda: state())
    assert cli.publish_refusal(short, work, AT) is None
    monkeypatch.setattr(orbitwire, "fetch", lambda: state([("wk-Q900001", "2026-10-10T08:00:00+00:00")]))
    assert "not written as a new angle" in cli.publish_refusal(short, work, AT)
    shared = Short.load(work / "short.json")
    shared.scene["orbitwire"] = {"status": "published", "orbitwire_published_at": "2026-10-10T08:00:00+00:00"}
    assert "3 h after" in cli.publish_refusal(shared, work, AT)
    assert cli.publish_refusal(shared, work, AT + timedelta(hours=3)) is None

    def broken():
        raise OSError("down")
    monkeypatch.setattr(orbitwire, "fetch", broken)
    assert "unreadable" in cli.publish_refusal(short, work, AT)


def test_ledger_records_the_overlap(made, tmp_path, monkeypatch):
    from desk import youtube

    short, work = made
    released = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(timespec="seconds")
    short.scene["orbitwire"] = {"qid": "Q900001", "status": "published", "orbitwire_id": "wk-Q900001",
                                "orbitwire_published_at": released, "high_profile": "fame",
                                "angle": "india", "excluded_photos": ["File:Other.jpg"], "photo_pool_checked": True}
    short.title = "रमेश प्रसाद वर्मा: भारत के सुरों का सफ़र"
    short.save(work / "short.json")
    monkeypatch.setattr(cli, "WORK", tmp_path)
    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(orbitwire, "fetch", lambda: state([("wk-Q900001", released)]))
    monkeypatch.setattr(youtube, "publish", lambda *a, **k: {"video_id": "v", "url": "https://youtu.be/v",
                                                            "privacy": "public", "synthetic_declared": True})
    cli.publish("wk-Q900001")
    row = ledger.published()[0]
    assert row["orbitwire_overlap"] == {"qid": "Q900001", "status": "published", "orbitwire_id": "wk-Q900001",
                                        "orbitwire_published_at": released, "high_profile": "fame", "angle": "india"}
    assert row["voice"] == "gemini-sulafat"
