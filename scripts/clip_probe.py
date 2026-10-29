"""The desk's own footage path on this host: refused directly, then WARP, then a 4 s cut of the video read through it
(GitHub Actions diagnostic: uv run python scripts/clip_probe.py <video id>)."""
import logging
import sys
from pathlib import Path

from desk import footage

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
video = {"id": sys.argv[1] if len(sys.argv) > 1 else "IOUExBZgm88"}
try:
    footage.streams(video)
    print("direct: served")
except footage.Refused:
    print("direct: refused (not a bot)")
print("WARP proxy:", footage._warp(local=True))
info = footage.streams(video)
fmts = footage.candidates(info, 1080)
print("formats through WARP:", len(fmts), [(f["format_id"], f["height"], f["protocol"]) for f in fmts[:4]])
folder = Path("/tmp/clip-probe")
folder.mkdir(exist_ok=True)
prepared = footage.prepare(video, folder, info)
preview = folder / f"{video['id']}-preview.mp4"
print("PREVIEW", preview.stat().st_size, "bytes", footage.probe(preview), "shots", len(prepared["shots"]),
      "frames", len(prepared["frames"]))
shot, best = prepared["shots"][0], fmts[0]
out = footage.cut(best, shot[0], min(4.0, shot[1] - shot[0]), (0, 0, best["width"], best["height"]), folder / "clip.mp4")
print("CUT", out.stat().st_size, "bytes", footage.probe(out))
