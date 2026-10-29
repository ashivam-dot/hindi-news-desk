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
out = Path("/tmp/clip.mp4")
for f in fmts[:4]:
    try:
        footage._ffmpeg(*footage._source(f), "-ss", "30", "-t", "4", "-an", "-c:v", "libx264", "-preset", "ultrafast", out,
                        timeout=120)
        print("CUT OK from format", f["format_id"], out.stat().st_size, "bytes")
        break
    except Exception as exc:  # noqa: BLE001
        print("format", f["format_id"], "failed:", footage._quiet(exc)[-200:])
