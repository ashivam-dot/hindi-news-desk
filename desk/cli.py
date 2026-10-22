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

from . import config, gate, ledger, learn, plan, review

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
# A death no news report states yet is retried: Wikidata's P570 often comes before the outlets' items are read.
RETRYABLE = ("words (want", "does not confirm the death", "no news report states the death", "usable photos",
             "no draft passed", "came out garbled", "orbitwire", "pictures:", "text cards", "too few showable")
# A faceless subject (writer.FACELESS) is skipped for good whatever else the gate said: a run later the photo still
# does not exist (CAPraPdXvns, Raihan Vadra). Picture and card ceilings stay retryable: the writer is stochastic and
# a rewrite that names the person or thing in each beat passes, within ledger.retry's six tries.
FACELESS = "faceless:"


def retryable(reason: str) -> bool:
    return FACELESS not in reason and any(m in reason for m in RETRYABLE)


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
    if not target.get("lane"):  # a wiki: story never went through watch()
        target = target | {"audience": target.get("audience") or plan.audience_of(target)}
        target["lane"] = plan.lane_of(target, datetime.now(timezone.utc))
    short = writer.build(target)
    short.scene.setdefault("category", target.get("category"))
    short.scene.setdefault("article", target.get("title"))
    for key in ("replaces", "remake_of", "case", "case_story", "angle", "hook", "lane", "audience", "priority",
                "series"):
        if target.get(key) and not (key == "hook" and key in short.scene):  # writer.hook_said kept it or not
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
    # The second of the gate's three runs (prepare, here, publish): the picture time shares as rendered.
    if problems := gate.shown_is_said(short, stats.get("views")):
        raise ValueError("gate: " + "; ".join(problems))
    return short, stats


def rendered_views(work: Path) -> list[dict] | None:
    """render.json's views ({start, end, photo, beat_k, plate}), or None for a Short rendered before they existed."""
    path = work / "render.json"
    return json.loads(path.read_text(encoding="utf-8")).get("views") if path.exists() else None


def overlap_record(short) -> dict | None:
    ov = short.scene.get("orbitwire")
    if not ov:
        return None
    return {k: ov.get(k) for k in ("qid", "status", "orbitwire_id", "orbitwire_published_at", "high_profile", "angle")}


def report_urls(short) -> list[str]:
    """The outlet articles a Short used: its reporting, and the reports that state a death (gate._death_reported)."""
    return list(dict.fromkeys(r["url"] for r in (short.scene.get("reporting") or [])
                              + (short.scene.get("death_reports") or [])))


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
    if (views := rendered_views(work)) is not None:  # the gate's third run, with the time shares as rendered
        problems += [p for p in gate.shown_is_said(short, views) if p not in problems]
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
           **{k: short.scene[k] for k in ("case", "case_story", "angle", "lane", "audience", "priority", "series")
              if short.scene.get(k)}, **result}
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
RETITLE = ROOT / "retitle.json"


# A retirement that fails this many runs is left to Studio: each try costs up to two status updates (100 units).
RETIRE_TRIES = 4


def retire_listed(health: dict) -> None:
    """Make private each upload retire.json lists ({"video_id", "why"}) that the ledger has not retired yet: a Short
    the owner found wrong, whose story is too old to remake. A failure is noted and tried again next run."""
    from . import youtube

    specs = json.loads(RETIRE.read_text(encoding="utf-8")) if RETIRE.exists() else []
    rows = ledger.published()
    for s in specs:
        row = next((r for r in rows if r.get("video_id") == s["video_id"]), None)
        if row is None or row.get("retire_public_read"):  # rows retired before this read-back are read once more
            continue
        if row.get("retire_tries", 0) >= RETIRE_TRIES:
            health["steps"].append(f"retire {s['video_id']}: failed {RETIRE_TRIES} runs; make it private in Studio")
            continue
        try:
            got = youtube.retire(s["video_id"])
        except Exception as exc:
            ledger.update_published(s["video_id"], {"retire_tries": row.get("retire_tries", 0) + 1})
            health["steps"].append(f"retire {s['video_id']}: {type(exc).__name__}: {exc}"[:300])
            continue
        ledger.update_published(s["video_id"], {"privacy": "private", "retired_why": s["why"], "retire_read_back": got,
                                                "retire_public_read": got != youtube.PAGE_UNREAD,
                                                "retired_at": row.get("retired_at") or ledger.now()})
        health["steps"].append(f"retired {s['video_id']} ({got}): {s['why']}"[:300])


def retitle_listed(health: dict) -> None:
    """Give each upload retitle.json lists ({"video_id", "title", "why"}) its new title, once: a true Short whose
    title the owner or a source re-check found unclear. A failure is noted and tried again next run."""
    from . import youtube

    specs = json.loads(RETITLE.read_text(encoding="utf-8")) if RETITLE.exists() else []
    rows = ledger.published()
    for s in specs:
        row = next((r for r in rows if r.get("video_id") == s["video_id"]), None)
        if row is None or row.get("retired_at") or (row.get("retitled_at") and row.get("title") == s["title"]):
            continue
        try:
            got = youtube.retitle(s["video_id"], s["title"])
        except Exception as exc:
            health["steps"].append(f"retitle {s['video_id']}: {type(exc).__name__}: {exc}"[:300])
            continue
        if got == "missing":
            health["steps"].append(f"retitle {s['video_id']}: no such video")
            continue
        ledger.update_published(s["video_id"], {"title": s["title"], "old_title": row.get("title"),
                                                "retitled_at": ledger.now(), "retitled_why": s["why"]})
        health["steps"].append(f"retitled {s['video_id']} ({got}): {s['why']}"[:300])


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


def _channel_jobs(health: dict) -> None:
    """The owner's one-off channel setup (DESK_UNTAG words "about", "playlists"), after the publish step so it only
    spends what the upload left, and never on a held run (no channel id, no voice, or a quota hold)."""
    if not config.CHANNEL_JOBS or health.get("held") or not config.channel_id_ready():
        return
    try:
        from . import channel
        health["steps"].append(channel.run(config.CHANNEL_JOBS))
    except Exception as exc:  # the setup must never stop a publish or the health record
        health["steps"].append(f"channel: {type(exc).__name__}: {exc}"[:300])


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
            try:
                if note := review.daily():
                    health["steps"].append(note)
            except Exception as exc:  # the scorecard only reports; writing it must never stop a publish
                health["steps"].append(f"review: {type(exc).__name__}: {exc}"[:300])
            retire_listed(health)
            retitle_listed(health)
            if config.UNTAG:
                from . import youtube
                try:
                    health["steps"].append(f"untag: old marker tag taken off {youtube.untag()} uploads")
                except youtube.NoWriteScope as exc:  # one clear line: the token needs a write scope
                    health["steps"].append(str(exc)[:300])
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
                (note_retry if retryable(str(exc)) else note_skip)(cand["id"], str(exc)[:300])
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
            _channel_jobs(health)
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
