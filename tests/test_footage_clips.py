"""Real footage in the full-screen Short (clips.py over the kit's footage.py)."""
import subprocess

import numpy as np
import soundfile as sf
from PIL import Image

from desk import clips, compose, match, youtube
from desk.spec import Beat, Short


def short(beats, photos, **scene):
    return Short(id="kh-test", kind="explainer", title="कर्नाटक में नंदिनी दूध 8 रुपये प्रति लीटर महंगा हुआ",
                 beats=beats, facts=[], sources=["https://en.wikipedia.org/wiki/Karnataka"], loss=False,
                 scene={"template": "full", "photos": photos, **scene})


def test_the_search_is_the_english_headlines_lead():
    assert clips.query("Karnataka hikes Nandini milk prices by ₹8 per litre from November 1: State minister") == \
        "Karnataka hikes Nandini milk prices litre November"
    pkg = clips.package(short([Beat("दूध महंगा।", "photo:0")], [{}], story="Nandini milk price hike: KMF",
                              cast=[{"en": "Karnataka", "hi": "कर्नाटक", "kind": "place"},
                                    {"en": "Milk", "hi": "दूध", "kind": "thing"}]))
    assert pkg["title"].startswith("Nandini milk price hike: ") and pkg["subjects"] == [
        {"name": "Karnataka", "anchor": "कर्नाटक"}] and pkg["location"] == "Karnataka"


def test_clips_go_on_the_hook_then_the_map_never_on_a_card_or_a_short_beat():
    photos = [{"origin": "osm", "role": "map", "file": "map"}, {"file": "a.jpg"}, {"file": "b.jpg"}]
    beats = [Beat("एक", "photo:1"), Beat("दो", "photo:2", plate=match.CARD), Beat("तीन", "photo:2"),
             Beat("चार", "photo:0"), Beat("पाँच", "photo:1"), Beat("छह", "outro")]
    s = short(beats, photos)
    spans = [(0, 3), (3, 6), (6, 9), (9, 12), (12, 13), (13, 15)]
    assert clips.order(s, spans)[:2] == [0, 3]
    assert set(clips.order(s, spans)) == {0, 2, 3}
    placed = clips.assign(s, [{"relevance": 6, "path": "low"}, {"relevance": 9, "path": "best"}], spans)
    assert [(c["beat"], c["path"]) for c in placed] == [(0, "best"), (3, "low")]


def test_without_a_youtube_sign_in_there_is_no_footage_and_no_error(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_JSON", raising=False)
    s = short([Beat("एक", "photo:0")], [{}])
    assert clips.attach(s, tmp_path) == [] and s.scene["clips"] == []
    monkeypatch.setenv("DESK_FOOTAGE", "off")
    s.scene.pop("clips")
    assert clips.attach(s, tmp_path) == [] and "clips" not in s.scene


def test_the_description_credits_each_clip_as_cc_by_asks():
    clip = {"video": "abc123", "channel": "News18 Kannada", "title": "Nandini milk price hike", "beat": 0}
    s = short([Beat("एक", "photo:0")], [], clips=[clip])
    s.credits = ["तस्वीरें: Wikimedia Commons"]
    text = youtube._description(s, {"engine": "gemini"}, narration=True, grouped=False)
    assert "https://youtu.be/abc123" in text and "News18 Kannada" in text and "CC BY 3.0" in text
    assert "असली वीडियो क्लिप" in text


def test_a_beats_clip_plays_over_its_photo_with_its_credit(tmp_path, monkeypatch):
    monkeypatch.setattr(compose, "W", 360)
    monkeypatch.setattr(compose, "H", 640)
    plate, camera, grade = compose.Plate, compose.Camera, compose.Grade
    monkeypatch.setattr(compose, "Plate", lambda photo, cache, size=(360, 640), **kw: plate(photo, cache, size=size, **kw))
    monkeypatch.setattr(compose, "Camera", lambda size=(360, 640): camera(size=size))
    monkeypatch.setattr(compose, "Grade", lambda mood, seed, size=(360, 640), **kw: grade(mood, seed, size=size, **kw))
    monkeypatch.setattr(compose.depth, "estimate", lambda image, cache: np.full((image.height, image.width), .5,
                                                                                 dtype=np.float32))
    picture = tmp_path / "photo.jpg"
    Image.new("RGB", (360, 640), (20, 20, 200)).save(picture)
    photo = {"path": str(picture), "credit": "Photo: public domain", "host": "Wikimedia Commons",
             "license": "Public domain", "page": "https://commons.wikimedia.org/wiki/File:Test.jpg"}
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00ff00:s=360x640:d=1.5:r=30",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    s = short([Beat("पहली बात।", "photo:0"), Beat("दूसरी बात।", "photo:0")], [photo],
              clips=[{"path": str(clip), "seconds": 1.5, "beat": 1, "credit": "वीडियो: Test / YouTube (CC BY)"}])
    sf.write(tmp_path / "narration.wav", np.zeros(4 * 24000), 24000)
    timing = {"duration": 4.0, "beats": [[0, 2.0], [2.0, 4.0]],
              "words": [{"text": "पहली", "start": 0, "end": 1.9, "beat": 0},
                        {"text": "दूसरी", "start": 2.0, "end": 3.9, "beat": 1}]}
    stats = compose.render(s, timing, tmp_path)
    assert stats["clips"] == [{"beat": 1, "video": None, "seconds": 1.5}]

    def at(sec):
        raw = subprocess.check_output(["ffmpeg", "-loglevel", "error", "-ss", str(sec), "-i", str(tmp_path / "short.mp4"),
                                       "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        f = np.frombuffer(raw, np.uint8).reshape(640, 360, 3).astype(int)
        return f[100:300, 60:300].mean(axis=(0, 1))

    photo_beat, clip_beat, after = at(1.0), at(2.7), at(3.8)
    assert clip_beat[1] > clip_beat[2] + 40          # the green clip, over the beat's blue photo
    assert photo_beat[2] > photo_beat[1] + 20 and after[2] > after[1] + 20  # the photo before it and once it ends
