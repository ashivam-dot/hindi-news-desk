"""Exercise real Hindi compositing and muxing, including fractional closing frames and audio."""
import json
import math
import subprocess

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from desk import compose
from desk.spec import Beat, Short


@pytest.mark.parametrize("template,tail", [("story", 0.6), ("full", compose.END_HOLD)])
def test_every_generated_closing_frame_reaches_the_mp4(tmp_path, monkeypatch, template, tail):
    monkeypatch.setattr(compose, "W", 360)
    monkeypatch.setattr(compose, "H", 640)
    # Production constructors bind their default sizes at import; keep their real implementations at test size.
    plate, camera, grade = compose.Plate, compose.Camera, compose.Grade
    monkeypatch.setattr(compose, "Plate", lambda photo, cache, size=(360, 640), **kw:
                        plate(photo, cache, size=size, **kw))
    monkeypatch.setattr(compose, "Camera", lambda size=(360, 640): camera(size=size))
    monkeypatch.setattr(compose, "Grade", lambda mood, seed, size=(360, 640), **kw:
                        grade(mood, seed, size=size, **kw))
    monkeypatch.setattr(compose.depth, "estimate", lambda image, cache: np.full(
        (image.height, image.width), .5, dtype=np.float32))
    picture = tmp_path / "photo.jpg"
    Image.new("RGB", (360, 640), (75, 110, 145)).save(picture)
    photo = {"path": str(picture), "credit": "Photo: public domain", "host": "Wikimedia Commons",
             "license": "Public domain", "page": "https://commons.wikimedia.org/wiki/File:Test.jpg"}
    short = Short(id="encode-regression", kind="death", title="प्रभात की कहानी",
                  beats=[Beat("प्रभात की कहानी।", "photo:0")], facts=[], sources=[], loss=True,
                  scene={"mood": "tribute", "photos": [photo], "template": template})
    spoken = 2.011
    wave = np.arange(round(spoken * 24000)) / 24000
    sf.write(tmp_path / "narration.wav", .2 * np.sin(2 * np.pi * 220 * wave), 24000)
    timing = {"duration": spoken, "beats": [[0, spoken]],
              "words": [{"text": "प्रभात", "start": 0, "end": spoken - .011, "beat": 0}]}
    stats = compose.render(short, timing, tmp_path)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=codec_type,nb_read_frames,duration", "-of", "json", str(tmp_path / "short.mp4")]))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert int(video["nb_read_frames"]) == stats["frames"] == math.ceil((spoken + tail) * compose.FPS)
    assert float(audio["duration"]) >= spoken
