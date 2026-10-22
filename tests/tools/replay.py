"""Replay the anchored matcher and the shown-is-said gate on saved run artifacts, offline (SYNC-AUDIT 4.1 step 9.3).

    .venv/bin/python -I tests/tools/replay.py DIR_OR_SHORT_JSON... [--json out.json]

For every short.json under the arguments (a `gh run download` folder, the audit folders, or a short.json itself):
  original  the shots as made, through gate.check (gate.said_is_shown is the picture part), with the time shares of
            the views the legacy compose cut (timing.json) when the artifact has a timing, else per-beat weights;
  replanned visuals.direct's anchored half on the same pool: every photo vetted (match.vet), match.plan over the
            spoken beats, each card trimmed to its picture (visuals.card_over) and the hook kept only when said
            (writer.hook_said), as writer._short does, then the same gate on the views the anchored compose would
            cut on the same voice timing.

Offline by construction (sockets refuse to connect), so what needs the network is not replayed: the cast is the
artifact's own (no new Wikidata/Commons lookups, so no sub-place landmark, no re-ranked same-name place, no new
police, sight or route pictures, no face-size filter on new portraits), the writer is not re-run (its picture-first
RULES and the SHOWABLE retry need the model), and stale_pictures is skipped (it needs the channel's recent files).
The replanned refusal rate is therefore the rate BEFORE the SHOWABLE retry, on the old pipeline's photo pools.
"""
from __future__ import annotations

import json
import re
import socket
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from desk import compose, config, gate, match, visuals, writer  # noqa: E402
from desk.spec import Short, shot_photos  # noqa: E402


def _offline(*a, **k):
    raise OSError("replay is offline")

# The picture gate; licences, credits and facts are the other checks (reported apart, never the verdict here).
PICTURE = re.compile(r"^(pictures:|text cards:|beats:)")
# Problem strings by kind, for the refusal-reason tally (gate.held, gate.said_is_shown, match.problems).
REASONS = [
    ("vetted photo on screen", r"^pictures: beat \d+ shows photo \d+ \(.*\): "),
    ("picture the beat does not name", r"which the beat does not name$"),
    ("card names what is not on screen", r"^pictures: card \d+ names"),
    ("cards over half the beats", r"^text cards: \d+ of \d+ beats"),
    ("3+ cards in a row", r"^text cards: \d+ beats in a row"),
    ("maps over 40% of picture time", r"maps fill"),
    ("hook names someone never said", r"the hook names"),
    ("too few pictures once maps group", r"once a place's maps count as one"),
    ("one picture held too long", r"in a row$|under \d+ of \d+ beats"),
    ("named person not shown", r"names .* but shows someone"),
    ("title person not on screen", r"the title names"),
    ("too few different pictures", r"different ones on screen"),
]


def reason(p: str) -> str:
    return next((name for name, rx in REASONS if re.search(rx, p)), re.sub(r"\d+", "N", p.split(":")[0]))


def shorts(args: list[str]) -> list[Path]:
    out = []
    for a in args:
        p = Path(a)
        out += [p] if p.is_file() else sorted(p.rglob("short.json"))
    return out


def shots_of(short: Short, spans: list, duration: float) -> list[dict]:
    """compose's shot rows from a saved Short and its voice timing (render_full's layout, without the frames)."""
    photos, out = short.scene.get("photos") or [], []
    for k, (b, (a, e)) in enumerate(zip(short.beats, spans)):
        shown = [i for i in shot_photos(b.shot) if 0 <= i < len(photos)]
        main = shown[0] if shown else (out[-1]["photo"] if out else 0)
        out.append({"photo": main, "views": shown or [main], "start": a if k else 0.0,
                    "end": e if k < len(spans) - 1 else duration, "outro": b.shot == "outro", "beat": b,
                    "cut_word": b.cut_word, "cut_at": b.cut_at, "plate": b.plate, "card_view": b.card_view,
                    "motion": compose.MOTIONS[k % len(compose.MOTIONS)]})
    return out


def timed_views(short: Short, timing: dict | None, anchored: bool) -> list[dict] | None:
    if not timing or len(timing.get("beats") or []) != len(short.beats):
        return None
    shots = shots_of(short, timing["beats"], timing.get("duration") or timing["beats"][-1][1])
    return compose.view_record(compose.views(shots, timing.get("words") or [], anchored=anchored))


def replan(short: Short) -> tuple[Short, list[dict]]:
    """visuals.direct's anchored half on the artifact's own pool and cast (no network), then writer._short's beats."""
    photos, cast = [dict(p) for p in short.scene.get("photos") or []], match.cast_of(short)
    for i, p in enumerate(photos):
        if why := match.vet(i, photos, short, cast):
            p["vet"] = why
        else:
            p.pop("vet", None)
    spell = match.spellings_of(short)
    spoken = [b for b in short.beats if b.shot.startswith("photo:")]
    subject = [i for i, p in enumerate(photos) if not p.get("role")]
    lead = next(iter(shot_photos(spoken[0].shot)), None) if spoken else None
    ranked = ([lead] if lead in subject else []) + [i for i in subject if i != lead]
    cards = [{"say": b.text, "card": b.card or {}} for b in spoken]
    names = short.scene.get("names") or []
    rows = match.plan(cards, photos, cast, ranked, short.kind, spell, match._person(short), names)
    it = iter(rows)
    beats = []
    for b in short.beats:
        if not b.shot.startswith("photo:"):
            beats.append(b)
            continue
        r = next(it)
        shown = r["views"] or shot_photos(b.shot)[:1]
        card = visuals.card_over(b.card or {}, shown, cast, photos, spell, r["plate"], names)
        beats.append(replace(b, shot="photo:" + "/".join(map(str, shown)), card=card, plate=r["plate"],
                             cut_word=r["cut_word"], cut_at=r["cut_at"], card_view=r["card_view"]))
    scene = short.scene | {"photos": photos}
    if hook := scene.get("hook"):  # writer._short keeps a hook only when the title or beat 1 says its names
        first = next((b.text for b in beats), "")
        scene["hook"] = hook if writer.hook_said(hook, short.title, first, scene.get("names") or []) else ""
    return replace(short, beats=beats, scene=scene), rows


def map_share(short: Short, views: list[dict] | None) -> float:
    """Maps' share of the picture time, as match.problems weighs it: a text card's time is neither (finding 12)."""
    photos = short.scene.get("photos") or []
    if views:
        shown = [v for v in views if v.get("plate") != match.CARD and not v.get("outro")]
        total = sum(max(v["end"] - v["start"], 0.0) for v in shown)
        maps = sum(max(v["end"] - v["start"], 0.0) for v in shown
                   if v["photo"] < len(photos) and visuals.is_map(photos[v["photo"]]))
        return maps / total if total else 0.0
    total = maps = 0.0
    for b in short.beats:
        if not b.shot.startswith("photo:") or b.plate == match.CARD:
            continue
        total += 1.0
        shown = shot_photos(b.shot)
        maps += sum(visuals.is_map(photos[i]) for i in shown if i < len(photos)) / max(len(shown), 1)
    return maps / total if total else 0.0


def verdict(short: Short, views: list[dict] | None) -> dict:
    allp = gate.check(short)
    pictures = [p for p in allp if PICTURE.match(p)]
    if views is not None:  # cli.prepare's gate, then the after-render one (cli.make) on the time shares
        pictures = list(dict.fromkeys(pictures + gate.shown_is_said(short, views)))
    spoken = [b for b in short.beats if b.shot.startswith("photo:")]
    return {"pass": not pictures, "problems": pictures, "other": [p for p in allp if not PICTURE.match(p)],
            "beats": len(spoken), "cards": sum(b.plate == match.CARD for b in spoken),
            "map_share": round(map_share(short, views), 3), "timed": views is not None}


def replay(path: Path) -> dict:
    short = Short.load(path)
    timing_p = path.with_name("timing.json")
    timing = json.loads(timing_p.read_text(encoding="utf-8")) if timing_p.exists() else None
    before = verdict(short, timed_views(short, timing, anchored=False))
    fixed, rows = replan(short)
    after = verdict(fixed, timed_views(fixed, timing, anchored=True))
    changed = sum(a.shot != b.shot or a.plate != b.plate for a, b in zip(short.beats, fixed.beats))
    made = path.with_name("short.mp4").exists() or path.with_name("render.json").exists()
    return {"path": str(path), "id": short.id, "kind": short.kind, "made": made,
            "preview": bool(short.scene.get("voice_preview")) or path.with_name("PREVIEW").exists(),
            "original": before, "replanned": after | {"changed_beats": changed}}


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "0/0"


def summary(rows: list[dict]) -> list[str]:
    n, made = len(rows), [r for r in rows if r["made"]]
    blocked = [r for r in rows if not r["replanned"]["pass"]]
    beats = sum(r["replanned"]["beats"] for r in rows)
    cards = sum(r["replanned"]["cards"] for r in rows)
    why = Counter(x for r in blocked for x in {reason(p) for p in r["replanned"]["problems"]})
    return [f"Shorts: {n} (rendered: {len(made)}; distinct stories: {len({r['id'] for r in rows})})",
            f"original shots BLOCKED by the new picture gate: {pct(sum(not r['original']['pass'] for r in rows), n)}",
            f"re-planned (match.plan) BLOCKED: {pct(len(blocked), n)}; would pass: {pct(n - len(blocked), n)}; "
            f"rendered only: BLOCKED {pct(sum(not r['replanned']['pass'] for r in made), len(made))}",
            f"re-planned text cards: {pct(cards, beats)} of spoken beats, {cards / max(n, 1):.1f} per Short; Shorts "
            f"over half cards: {sum(r['replanned']['cards'] * 2 > r['replanned']['beats'] for r in rows)}",
            "re-planned refusal reasons (Shorts): " + ", ".join(f"{k} {v}" for k, v in why.most_common())]


def table(rows: list[dict]) -> list[str]:
    out = ["| run | story | orig | orig flags | replan | cards | map share (orig -> replan) | replan refusal reasons |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        o, a = r["original"], r["replanned"]
        run = next((p for p in Path(r["path"]).parts if re.fullmatch(r"r?\d{8,}", p)), "")
        why = "; ".join(sorted({reason(p) for p in a["problems"]})) or "-"
        out.append(f"| {run.lstrip('r')}{' (dry)' if r['preview'] else ''} | {r['id']} | "
                   f"{'PASS' if o['pass'] else 'BLOCK'} | {len(o['problems'])} | {'PASS' if a['pass'] else 'BLOCK'} | "
                   f"{a['cards']}/{a['beats']} | {o['map_share']:.0%} -> {a['map_share']:.0%}"
                   f"{'' if a['timed'] else ' (per beat)'} | {why} |")
    return out


def main(argv: list[str]) -> int:
    out_json = None
    if "--json" in argv:
        i = argv.index("--json")
        out_json, argv = Path(argv[i + 1]), argv[:i] + argv[i + 2:]
    socket.socket.connect = _offline  # type: ignore[method-assign]
    socket.create_connection = _offline  # type: ignore[assignment]
    if config.MATCHER == "legacy":
        print("DESK_MATCHER=legacy: the shown-is-said gate is off; unset it to replay", file=sys.stderr)
        return 2
    rows = []
    for p in shorts(argv):
        try:
            rows.append(replay(p))
        except Exception as exc:  # an artifact the current Short format cannot load
            print(f"skip {p}: {type(exc).__name__}: {exc}", file=sys.stderr)
    print("\n".join(summary(rows) + [""] + table(rows)))
    if out_json:
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
