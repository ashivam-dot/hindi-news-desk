"""desk watch | make <wiki:Article title> [--voice-preview] | publish <story-id> | run [--dry [--voice-preview]] | health

--voice-preview narrates with Chatterbox's built-in voice so a dry run can be checked end to end before the Sulafat
voice is available. It is accepted only by `make` and `run --dry`; the Short it makes is marked (short.json,
timing.json and a PREVIEW file) and `publish`, the gate and the uploader all refuse it.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import config, gate, ledger, plan

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
RETRYABLE = ("under 6 hours old", "words (want", "does not confirm the death", "usable photos", "no draft passed",
             "came out garbled", "orbitwire")
MAX_WRITTEN = 2  # each script costs minutes when the local model writes it
PREVIEW = "PREVIEW"
log = logging.getLogger("desk")


def prepare(target: str | dict):
    """Build and gate a Short from a 'wiki:<title>' string or a watcher candidate."""
    from . import trends, writer

    if isinstance(target, str):
        if not target.startswith("wiki:"):
            raise ValueError("make takes wiki:<English Wikipedia article title>")
        cand = trends.candidate(target[5:])
        kept, notes = plan.apply_orbitwire([cand], datetime.now(timezone.utc))
        if not kept:
            raise ValueError("orbitwire: " + "; ".join(notes))
        target = kept[0]
    short = writer.build(target)
    work = WORK / short.id
    work.mkdir(parents=True, exist_ok=True)
    short.save(work / "short.json")
    problems = gate.check(short)
    if problems:
        raise ValueError("gate: " + "; ".join(problems))
    return short


def make(target: str | dict, short=None, preview: bool = False) -> tuple[object, dict]:
    from . import compose, voice

    short = short or prepare(target)
    work = WORK / short.id
    if preview:
        short.scene["voice_preview"] = True
        short.save(work / "short.json")
        (work / PREVIEW).write_text("made with the preview voice: never publish\n", encoding="utf-8")
    timing = voice.synthesize(short, work, preview=preview)
    stats = compose.render(short, timing, work)
    stats["voice"] = {k: timing["voice"].get(k) for k in ("engine", "identity", "preview", "served_model", "wpm",
                                                          "coverage", "tempo")}
    (work / "render.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    return short, stats


def overlap_record(short) -> dict | None:
    ov = short.scene.get("orbitwire")
    if not ov:
        return None
    return {k: ov.get(k) for k in ("qid", "status", "orbitwire_id", "orbitwire_published_at", "high_profile", "angle")}


def publish_refusal(short, work: Path, at: datetime) -> str | None:
    """Why this Short may not go out now: preview voice, no Sulafat record, channel not configured, or Orbitwire."""
    from . import orbitwire

    if (work / PREVIEW).exists() or short.scene.get("voice_preview"):
        return "voice: made with the preview voice; it can never be published"
    timing = work / "timing.json"
    voice = json.loads(timing.read_text(encoding="utf-8")).get("voice") if timing.exists() else None
    refused = gate.voice_ok(voice)
    if refused:
        return refused
    if not config.channel_id_ready():
        return "channel: DESK_CHANNEL_ID is not configured"
    qid = short.scene.get("qid") or orbitwire.qid_of(short.id)
    try:
        state = orbitwire.fetch()
    except Exception as exc:
        return f"orbitwire: its state is unreadable ({type(exc).__name__})"
    ov = orbitwire.overlap(qid, state, at)
    if ov and not short.scene.get("orbitwire"):
        return f"orbitwire: Orbitwire now covers {qid} ({ov['status']}); this Short was not written as a new angle"
    return orbitwire.wait(ov, at) if ov else None


def publish(story_id: str, publish_at: str | None = None) -> dict:
    """Publish now, or schedule for publish_at (ISO UTC); the ledger records the time it goes public."""
    from . import youtube
    from .spec import Short

    work = WORK / story_id
    short = Short.load(work / "short.json")
    problems = gate.check(short)
    if problems:
        raise ValueError("gate: " + "; ".join(problems))
    refused = publish_refusal(short, work, datetime.now(timezone.utc))
    if refused:
        raise ValueError(refused)
    voice = json.loads((work / "timing.json").read_text(encoding="utf-8"))["voice"]
    result = youtube.publish(short, work / "short.mp4", voice, publish_at=publish_at)
    when = datetime.fromisoformat(publish_at.replace("Z", "+00:00")).isoformat(timespec="seconds") if publish_at \
        else ledger.now()
    ledger.record_publish({"id": short.id, "kind": short.kind, "title": short.title, "loss": short.loss,
                           "published_at": when, "event_time": short.event_time, "voice": voice.get("engine"),
                           "voice_model": voice.get("served_model"), "orbitwire_overlap": overlap_record(short),
                           **result})
    return result


def run(dry: bool = False, preview: bool = False) -> dict:
    """One scheduled pass: watch, pick the best eligible story, make it, gate it, publish it. A dry run makes the
    best candidate (outside the schedule if need be) and never publishes or changes the ledger."""
    from . import voice

    if preview and not dry:
        raise ValueError("--voice-preview is only for dry runs")
    health = {"at": ledger.now(), "ok": True, "dry": dry, "steps": []}
    note_retry = (lambda i, r: None) if dry else ledger.retry
    note_skip = (lambda i, r: None) if dry else ledger.skip
    try:
        if not dry:
            for reason in (voice.ready(), None if config.channel_id_ready() else "hold: DESK_CHANNEL_ID is not set"):
                if reason:
                    health["steps"].append(reason)
                    health["held"] = reason
                    return health
        found = plan.watch(save=not dry)
        health["steps"].append(f"watch: {len(found['candidates'])} candidates from {len(found['trending'])} trending")
        health["steps"] += found["notes"][:8]
        if found.get("trend_errors"):
            health["steps"].append(f"trend radar errors: {found['trend_errors']}")
        ready, held = plan.lineup(found["candidates"])
        health["steps"] += held[:6]
        if dry and not ready:
            ready = [c for c in found["candidates"] if not c.get("orbitwire")] or found["candidates"]
        if not ready:
            return health
        recent_loss = [r.get("loss", False) for r in ledger.published()]
        written = 0
        for cand in ready[:4]:
            if written >= MAX_WRITTEN:
                health["steps"].append(f"later {cand['id']}: this run already wrote {written} scripts")
                continue
            try:
                short = prepare(cand)
            except ValueError as exc:
                written += "no draft passed" in str(exc)
                # Young or thin articles, and stories still short of free photos, get another chance next run.
                (note_retry if any(m in str(exc) for m in RETRYABLE) else note_skip)(cand["id"], str(exc)[:300])
                health["steps"].append(f"skip {cand['id']}: {exc}")
                continue
            except Exception as exc:  # one malformed article must not stop the other candidates
                note_retry(cand["id"], f"{type(exc).__name__}: {exc}"[:300])
                health.setdefault("warnings", []).append(f"{cand['id']}: {type(exc).__name__}: {exc}"[:300])
                continue
            written += 1
            mix = gate.channel_mix(recent_loss, short.loss)
            if mix and not dry:
                health["steps"].append(f"hold {cand['id']}: {mix}")
                continue
            try:
                short, stats = make(cand, short, preview=preview)
            except voice.VoiceHold as exc:
                health["steps"].append(str(exc))
                health["held"] = str(exc)
                return health
            except Exception as exc:  # ffmpeg, a corrupt take or an encoder error: count it, try the next story
                note_retry(cand["id"], f"{type(exc).__name__}: {exc}"[:300])
                health["steps"].append(f"skip {cand['id']}: {type(exc).__name__}: {exc}"[:400])
                continue
            if dry:
                health["steps"].append(f"dry run: made {short.id} ({stats['duration']} s, voice "
                                       f"{stats['voice']['engine']}), not published")
                health["made"] = {"id": short.id, "title": short.title, **stats}
                return health
            try:
                result = publish(short.id)
            except Exception as exc:
                note_retry(cand["id"], f"{type(exc).__name__}: {exc}"[:300])
                health["steps"].append(f"hold {cand['id']}: {type(exc).__name__}: {exc}"[:400])
                continue
            health["steps"].append(f"published {short.id}: {result['url']}")
            health["published"] = result
            return health
        health["steps"].append("nothing eligible to publish")
        return health
    except Exception as exc:
        health["ok"] = False
        health["error"] = f"{type(exc).__name__}: {exc}"[:500]
        health["trace"] = traceback.format_exc()[-2000:]
        return health
    finally:
        if not dry:
            ledger.save("health", health)
        else:
            WORK.mkdir(parents=True, exist_ok=True)
            (WORK / "dry-health.json").write_text(json.dumps(health, indent=1, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    p = argparse.ArgumentParser(prog="desk")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("watch")
    m = sub.add_parser("make")
    m.add_argument("event")
    m.add_argument("--voice-preview", action="store_true")
    pb = sub.add_parser("publish")
    pb.add_argument("story")
    r = sub.add_parser("run")
    r.add_argument("--dry", action="store_true")
    r.add_argument("--voice-preview", action="store_true")
    sub.add_parser("health")
    a = p.parse_args(argv)
    if a.cmd == "watch":
        print(json.dumps(plan.watch(save=False), indent=1, ensure_ascii=False))
    elif a.cmd == "make":
        short, stats = make(a.event, preview=a.voice_preview)
        print(json.dumps({"id": short.id, "title": short.title, **stats}, indent=1, ensure_ascii=False))
    elif a.cmd == "publish":
        print(json.dumps(publish(a.story), indent=1, ensure_ascii=False))
    elif a.cmd == "run":
        if a.voice_preview and not a.dry:
            p.error("--voice-preview is only for dry runs (run --dry --voice-preview)")
        health = run(dry=a.dry, preview=a.voice_preview)
        print(json.dumps({k: v for k, v in health.items() if k != "trace"}, indent=1, ensure_ascii=False))
        return 0 if health["ok"] else 1
    elif a.cmd == "health":
        print(json.dumps(ledger.load("health", {}), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
