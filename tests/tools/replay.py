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

Real pictures (2026-10-22): per Short, the map views on screen (match._map_views, one map held across a cut counts
once) and the card share, before and after; and which beats would gain a thing's picture (desk/things.py's lexicon,
"तिरंगे" -> Flag of India) were the Short made today. Not replayed: the thing photos themselves (Commons downloads),
so a beat that would gain one is still a card or a map here and the replanned refusals are an upper bound; the
cast's new "thing" rows from the script's English names (Wikipedia lookups); and the prepare-time faceless refusal
of a relative's story (writer.relative_faceless reads Wikidata). The faceless check on the saved photos
(gate.richness) runs, but only on artifacts whose photos carry the "depicts" stamps.
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

from desk import compose, config, gate, match, things, visuals, writer  # noqa: E402
from desk.spec import Short, shot_photos  # noqa: E402


def _offline(*a, **k):
    raise OSError("replay is offline")

# The picture gate; licences, credits and facts are the other checks (reported apart, never the verdict here).
PICTURE = re.compile(r"^(pictures:|text cards:|beats:|faceless:)")
# Problem strings by kind, for the refusal-reason tally (gate.held, gate.said_is_shown, match.problems).
REASONS = [
    # The picture-follows-voice rules (Matlabnama audit, 2026-10-23), before the vetted-photo catch-all.
    ("map not where it happened", r"not where the story happened|one-ended map"),
    ("picture on two beats", r" on beats [\d, ]+ and \d+$"),
    ("stand-in without its label", r"a stand-in, without"),
    ("vetted photo on screen", r"^pictures: beat \d+ shows photo \d+ \(.*\): "),
    ("picture the beat does not name", r"which the beat does not name$"),
    ("card names what is not on screen", r"^pictures: card \d+ names"),
    ("cards over a third of the beats", r"^text cards: \d+ of \d+ beats"),
    ("2+ cards in a row", r"^text cards: \d+ beats in a row"),
    ("maps over 20% of picture time", r"maps fill"),
    ("more than one map view", r"map views \(at most"),
    ("map under a name with a photo", r"shows a map though it names"),
    ("real photos under half the Short", r"real photos fill only"),
    ("faceless subject", r"^faceless:"),
    ("hook names someone never said", r"the hook names"),
    ("harm hook over the subject", r"the hook says someone was hurt"),
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
    seen = compose.views(shots, timing.get("words") or [], anchored=anchored)
    if anchored:  # a picture held past match.HOLD_MAX cut to its twin, as the renders do (compose.twins)
        compose.twins(seen, short.scene.get("photos") or [], match.cast_of(short))
    if anchored:  # render_full's chips, each stamped on its view; the legacy render held them CHIP_HOLD from the cut
        compose.chip_plan(short, shots, seen)
    # The opening flash the renders show over beat 1 (compose.burst), recorded as render.json records it.
    flash = [] if short.loss or not anchored else compose.burst(seen, short.scene.get("photos") or [],
                                                                 match.cast_of(short))
    return compose.view_record(seen, flash)


def replan(short: Short) -> tuple[Short, list[dict]]:
    """visuals.direct's anchored half on the artifact's own pool and cast (no network), then writer._short's beats."""
    photos, cast = [dict(p) for p in short.scene.get("photos") or []], match.cast_of(short)
    spoken = [b for b in short.beats if b.shot.startswith("photo:")]
    # One map, where it happened (visuals.map_scope; offline the dateline is unknown: the place named most).
    visuals.map_scope([{"say": b.text} for b in spoken], cast, photos)
    for i, p in enumerate(photos):
        if why := match.vet(i, photos, short, cast):
            p["vet"] = why
        else:
            p.pop("vet", None)
    spell = match.spellings_of(short)
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
    out = replace(short, beats=beats, scene=scene)
    if scene.get("hook") and match.opening(out):  # and its pictures show them (writer._short)
        out = replace(out, scene=scene | {"hook": ""})
    return out, rows


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


def repeats(short: Short, views: list[dict] | None = None) -> int:
    """How many pictures (a photo or its look, a place's maps as one) are on more than one beat (match.repeats)."""
    return len(match.repeats(short, views))


def map_places(short: Short, views: list[dict] | None = None) -> list[str]:
    """The places the maps on screen show, once each in the order they come (a route's two ends together)."""
    photos, cast, out = short.scene.get("photos") or [], match.cast_of(short), []
    for b in short.beats:
        if b.shot.startswith("photo:") and b.plate != match.CARD:
            for i in shot_photos(b.shot):
                if i < len(photos) and visuals.is_map(photos[i]):
                    out.append("+".join(sorted(match.depicts(i, photos[i], cast))))
    return list(dict.fromkeys(out))


def per_beat(short: Short) -> list[str]:
    """Beat words -> what is on screen (file or "card"), for the per-beat review table."""
    photos, out = short.scene.get("photos") or [], []
    for n, b in enumerate([b for b in short.beats if b.shot.startswith("photo:")], 1):
        shown = [photos[i] for i in shot_photos(b.shot) if i < len(photos)]
        what = "card" if b.plate == match.CARD else " / ".join(
            ("MAP " + (p.get("who") or "")) if visuals.is_map(p) else
            f"{(p.get('file') or '')[5:60]}{' [' + things.STAND_IN + ']' if p.get('stand_in') else ''}" for p in shown)
        out.append(f"b{n} {b.text[:60]} -> {what}{' (cut: ' + b.cut_word + ')' if b.cut_word else ''}")
    return out


def verdict(short: Short, views: list[dict] | None) -> dict:
    allp = gate.check(short)
    pictures = [p for p in allp if PICTURE.match(p)]
    if views is not None:  # cli.prepare's gate, then the after-render one (cli.make) on the time shares
        pictures = list(dict.fromkeys(pictures + gate.shown_is_said(short, views)))
    spoken = [b for b in short.beats if b.shot.startswith("photo:")]
    return {"pass": not pictures, "problems": pictures, "other": [p for p in allp if not PICTURE.match(p)],
            "beats": len(spoken), "cards": sum(b.plate == match.CARD for b in spoken),
            "map_share": round(map_share(short, views), 3), "map_views": match._map_views(short, views),
            "repeats": repeats(short, views), "map_places": map_places(short, views), "per_beat": per_beat(short),
            "timed": views is not None}


def thing_beats(short: Short) -> list[tuple[int, str]]:
    """(beat number, thing) for each spoken beat that names a lexicon thing (things.lexicon_hits): the picture it
    would gain today. India-only entries count for every story (the channel's are Indian), the foreign guard holds."""
    spoken = [b for b in short.beats if b.shot.startswith("photo:")]
    return [(n, hit["en"]) for n, b in enumerate(spoken, 1) for hit in things.lexicon_hits([{"say": b.text}], True)]


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
            "original": before, "replanned": after | {"changed_beats": changed}, "things": thing_beats(short)}


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "0/0"


def summary(rows: list[dict]) -> list[str]:
    n, made = len(rows), [r for r in rows if r["made"]]
    blocked = [r for r in rows if not r["replanned"]["pass"]]
    beats = sum(r["replanned"]["beats"] for r in rows)
    cards = sum(r["replanned"]["cards"] for r in rows)
    why = Counter(x for r in blocked for x in {reason(p) for p in r["replanned"]["problems"]})
    gain = [r for r in rows if r.get("things")]
    views = Counter(min(r["replanned"]["map_views"], 2) for r in rows)
    rep = (sum(r["original"]["repeats"] > 0 for r in rows), sum(r["replanned"]["repeats"] > 0 for r in rows))
    return [f"Shorts: {n} (rendered: {len(made)}; distinct stories: {len({r['id'] for r in rows})})",
            f"map views per Short, original: {sum(r['original']['map_views'] for r in rows) / max(n, 1):.1f} "
            f"(over one: {sum(r['original']['map_views'] > 1 for r in rows)}); re-planned: "
            f"{sum(r['replanned']['map_views'] for r in rows) / max(n, 1):.1f} (0: {views[0]}, 1: {views[1]}, "
            f"2+: {views[2]})",
            f"Shorts with a picture on two beats, original: {pct(rep[0], n)}; re-planned: {pct(rep[1], n)}",
            f"original text cards: {pct(sum(r['original']['cards'] for r in rows), beats)} of spoken beats",
            f"Shorts with a beat that would gain a thing's picture: {len(gain)} ("
            + ", ".join(f"{r['id']} b{n} {t}" for r in gain for n, t in r["things"]) + ")",
            f"original shots BLOCKED by the new picture gate: {pct(sum(not r['original']['pass'] for r in rows), n)}",
            f"re-planned (match.plan) BLOCKED: {pct(len(blocked), n)}; would pass: {pct(n - len(blocked), n)}; "
            f"rendered only: BLOCKED {pct(sum(not r['replanned']['pass'] for r in made), len(made))}",
            f"re-planned text cards: {pct(cards, beats)} of spoken beats, {cards / max(n, 1):.1f} per Short; Shorts "
            f"over a third cards: {sum(r['replanned']['cards'] > match.card_limit(r['replanned']['beats']) for r in rows)}",
            "re-planned refusal reasons (Shorts): " + ", ".join(f"{k} {v}" for k, v in why.most_common())]


def table(rows: list[dict]) -> list[str]:
    out = ["| run | story | orig | orig flags | replan | cards | map share (orig -> replan) | map views | things | "
           "replan refusal reasons |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        o, a = r["original"], r["replanned"]
        run = next((p for p in Path(r["path"]).parts if re.fullmatch(r"r?\d{8,}", p)), "")
        why = "; ".join(sorted({reason(p) for p in a["problems"]})) or "-"
        out.append(f"| {run.lstrip('r')}{' (dry)' if r['preview'] else ''} | {r['id']} | "
                   f"{'PASS' if o['pass'] else 'BLOCK'} | {len(o['problems'])} | {'PASS' if a['pass'] else 'BLOCK'} | "
                   f"{a['cards']}/{a['beats']} | {o['map_share']:.0%} -> {a['map_share']:.0%}"
                   f"{'' if a['timed'] else ' (per beat)'} | {o['map_views']} -> {a['map_views']} | "
                   f"{', '.join(f'b{n} {t}' for n, t in r.get('things') or []) or '-'} | {why} |")
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
    beats = "--beats" in argv  # also print each replanned beat: its words -> what is on screen
    argv = [a for a in argv if a != "--beats"]
    rows = []
    for p in shorts(argv):
        try:
            rows.append(replay(p))
        except Exception as exc:  # an artifact the current Short format cannot load
            print(f"skip {p}: {type(exc).__name__}: {exc}", file=sys.stderr)
    print("\n".join(summary(rows) + [""] + table(rows)))
    for r in rows if beats else ():
        print(f"\n{r['id']} ({'PASS' if r['replanned']['pass'] else 'BLOCK'}):\n  " + "\n  ".join(r["replanned"]["per_beat"]))
    if out_json:
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
