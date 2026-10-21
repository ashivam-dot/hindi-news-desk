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

from . import config, gate, ledger, learn, plan

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
RETRYABLE = ("words (want", "does not confirm the death", "usable photos", "no draft passed", "came out garbled",
             "orbitwire", "pictures:")
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
    short.scene.setdefault("category", target.get("category"))
    short.scene.setdefault("article", target.get("title"))
    for key in ("replaces", "remake_of", "case", "case_story", "angle", "hook"):
        if target.get(key):
            short.scene[key] = target[key]
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


def report_urls(short) -> list[str]:
    return [r["url"] for r in short.scene.get("reporting") or []]


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
    ov = orbitwire.overlap(qid, state, at, title=short.scene.get("article"), story_id=short.id,
                           reports=report_urls(short))
    if ov and not short.scene.get("orbitwire"):
        return (f"orbitwire: Orbitwire now covers {qid or short.id} ({ov['status']}); this Short was not written as a "
                "new angle")
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
    row = {"id": short.id, "kind": short.kind, "title": short.title, "loss": short.loss,
           "published_at": when, "event_time": short.event_time, "voice": voice.get("engine"),
           "voice_model": voice.get("served_model"), "orbitwire_overlap": overlap_record(short),
           "category": short.scene.get("category"), "region": short.scene.get("region"),
           "article": short.scene.get("article"), "qid": short.scene.get("qid"),
           "report_urls": report_urls(short),
           "outlets": short.scene.get("outlets") or [], "headlines": short.scene.get("headlines") or [],
           "photos": [p["file"] for p in short.scene.get("photos") or [] if p.get("file")],
           **{k: short.scene[k] for k in ("case", "case_story", "angle") if short.scene.get(k)}, **result}
    if old := short.scene.get("replaces"):
        row.update(replaces=old, remake_of=short.scene.get("remake_of"))
        try:
            youtube.retire(old)
            row["replaced"] = old
        except Exception as exc:  # the new version is already public: record it, and say why the old one stayed
            row["replace_error"] = f"{old}: {type(exc).__name__}: {exc}"[:300]
    ledger.record_publish(row)
    return result


RETIRE = ROOT / "retire.json"


def retire_listed(health: dict) -> None:
    """Make private each upload retire.json lists ({"video_id", "why"}) that the ledger has not retired yet: a Short
    the owner found wrong, whose story is too old to remake. A failure is noted and tried again next run."""
    from . import youtube

    specs = json.loads(RETIRE.read_text(encoding="utf-8")) if RETIRE.exists() else []
    rows = ledger.published()
    for s in specs:
        row = next((r for r in rows if r.get("video_id") == s["video_id"]), None)
        if row is None or row.get("retired_at"):
            continue
        try:
            youtube.retire(s["video_id"])
        except Exception as exc:
            health["steps"].append(f"retire {s['video_id']}: {type(exc).__name__}: {exc}"[:300])
            continue
        ledger.update_published(s["video_id"], {"privacy": "private", "retired_at": ledger.now(),
                                                "retired_why": s["why"]})
        health["steps"].append(f"retired {s['video_id']}: {s['why']}"[:300])


def _advisory(health: dict, dry: bool) -> dict | None:
    """A current public-service advisory goes out before any story; a dry run makes it and stops there."""
    from . import advisory

    for spec in advisory.pending():
        try:
            short, stats = advisory.make(spec, WORK)
        except Exception as exc:
            health["steps"].append(f"advisory {spec['id']}: {type(exc).__name__}: {exc}"[:400])
            continue
        if dry:
            health["steps"].append(f"dry run: made advisory {short.id} ({stats['duration']} s), not published")
            health["made"] = {"id": short.id, "title": short.title, **stats}
            return health
        try:
            result = advisory.publish(short, WORK / short.id)
        except Exception as exc:
            health["steps"].append(f"advisory {spec['id']}: {type(exc).__name__}: {exc}"[:400])
            continue
        health["steps"].append(f"published advisory {short.id}: {result['url']}")
        health["published"] = result
        return health
    return None


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
            ledger.set_identity()
            try:
                learned = learn.refresh()
                if learned is not None:
                    health["steps"].append(f"learn: {learned['scored']} scored Shorts, lifts {learned['lifts']}"[:400])
                    if learned.get("retention_note"):
                        health["steps"].append(learned["retention_note"])
            except Exception as exc:  # the numbers steer ranking; reading them must never stop a publish
                health["steps"].append(f"learn: {type(exc).__name__}: {exc}"[:300])
            retire_listed(health)
            if config.UNTAG:
                from . import youtube
                try:
                    health["steps"].append(f"untag: old marker tag taken off {youtube.untag()} uploads")
                except Exception as exc:  # tidying old tags must never stop a publish
                    health["steps"].append(f"untag: {type(exc).__name__}: {exc}"[:300])
        if done := _advisory(health, dry):
            return done
        found = plan.watch(save=not dry)
        health["steps"].append(f"watch: {len(found['candidates'])} candidates from {len(found['trending'])} trending")
        health["steps"] += found["notes"][:8]
        if found.get("trend_errors"):
            health["steps"].append(f"trend radar errors: {found['trend_errors']}")
        ready, held = plan.lineup(found["candidates"])
        health["steps"] += held[:6]
        if note := plan.ad_note(found["candidates"]):
            health["steps"].append(note)
        if dry and not ready:
            # Outside the window a dry run previews the story the next live run would make first.
            now = datetime.now(timezone.utc)
            # A case angle over its caps is held by the live run whatever the hour, so it is never previewed.
            unheld = [c for c in found["candidates"] if not c.get("case_wait")]
            pool = [c for c in unheld if not c.get("orbitwire")] or unheld
            ready = [c for c in sorted(pool, key=lambda c: -plan.priority(c, now))
                     if c.get("case") or not (plan.stale(c, now) or plan.unpopular(c, now))] or pool
            ready.sort(key=lambda c: (not c.get("replaces"), not c.get("case")))  # as plan.lineup orders them
        if dry and config.DRY_KIND:
            ready = [c for c in found["candidates"] if c.get("kind") == config.DRY_KIND]
            health["steps"].append(f"dry run: only {config.DRY_KIND} candidates ({len(ready)})")
        if not ready:
            return health
        recent_loss = [r.get("loss", False) for r in ledger.published()]
        written = tried = 0
        for cand in ready:
            if tried >= 4:
                break
            tried += 1
            if written >= MAX_WRITTEN:
                health["steps"].append(f"later {cand['id']}: this run already wrote {written} scripts")
                continue
            try:
                short = prepare(cand)
            except ValueError as exc:
                written += "no draft passed" in str(exc)
                if ledger.waiting(str(exc)):
                    # A brand-new article waits for its facts to settle; waiting is not a failed try, and it does
                    # not take a slot from the stories that are ready now.
                    tried -= 1
                    health["steps"].append(f"wait {cand['id']}: {exc}")
                    continue
                # Thin articles, and stories still short of free photos, get another chance next run.
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
