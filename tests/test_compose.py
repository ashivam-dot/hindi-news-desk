import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from desk import compose
from desk.spec import Short

SAMPLE = "क्षत्रिय श्री दृष्टि"


def _ink(layout) -> np.ndarray:
    font = ImageFont.truetype(str(compose.FONTS / compose.WEIGHTS["Bold"]), 80, layout_engine=layout)
    img = Image.new("L", (900, 140), 0)
    ImageDraw.Draw(img).text((10, 10), SAMPLE, font=font, fill=255)
    return np.asarray(img)


def test_devanagari_is_shaped_with_raqm():
    assert features.check("raqm")
    font = compose._font("Bold", 80)
    assert font.layout_engine == ImageFont.Layout.RAQM
    # Shaping forms conjuncts (क्ष, त्र, ष्ट) and reorders the vowel sign of दृ: the drawing differs from basic layout.
    assert not np.array_equal(_ink(ImageFont.Layout.RAQM), _ink(ImageFont.Layout.BASIC))


def test_conjuncts_are_single_glyphs():
    from fontTools.ttLib import TTFont

    cmap = TTFont(str(compose.FONTS / compose.WEIGHTS["Medium"])).getBestCmap()
    assert all(ord(ch) in cmap for ch in SAMPLE.replace(" ", ""))
    font = compose._font("Medium", 80)
    # With RAQM, क्ष (three code points) takes far less room than क + ् + ष drawn side by side.
    assert font.getlength("क्ष") < font.getlength("क") + font.getlength("ष") * 0.9


def test_credit_text_drops_glyphs_the_font_lacks():
    assert compose.drawable("फ़ोटो: 张伟 (Zhang Wei) / CC BY-SA 4.0") == "फ़ोटो: (Zhang Wei) / CC BY-SA 4.0"
    assert compose.drawable("फ़ोटो: 张伟 / CC BY 2.0") == "फ़ोटो: / CC BY 2.0"
    assert compose.drawable("फ़ोटो: José Núñez / CC0") == "फ़ोटो: José Núñez / CC0"


def test_captions_break_at_hindi_full_stops_and_width():
    words = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25}
             for i, t in enumerate("वे नहीं रहे। उनकी आवाज़ हमेशा याद रहेगी".split())]
    chunks = compose._chunks(words, lambda text: len(text) * 40)
    assert [" ".join(w["text"] for w in c) for c in chunks] == ["वे नहीं रहे।", "उनकी आवाज़ हमेशा", "याद रहेगी"]
    narrow = compose._chunks(words, lambda text: len(text) * 120)
    assert all(len(" ".join(w["text"] for w in c)) * 120 <= compose.CAPTION_WIDTH or len(c) == 1 for c in narrow)


def test_caption_layers_are_tall_enough_for_matras():
    captions = compose.Captions([{"text": "क्षत्रिय", "start": 0.0, "end": 0.5},
                                 {"text": "दृष्टि", "start": 0.5, "end": 1.0}], (255, 205, 92))
    rgb, alpha = captions.groups[0]["variants"][0]
    rows = np.flatnonzero(alpha[..., 0].max(axis=1) > 0)
    # Ink never touches the layer's top or bottom edge, so no matra or stroke is clipped.
    assert rows[0] > 0 and rows[-1] < alpha.shape[0] - 1


def test_disclosure_and_badge():
    assert "आवाज़: AI" in compose.DISCLOSURE and "Wikimedia Commons" in compose.DISCLOSURE
    assert "AI" in compose.AI_BADGE
    badge = compose._badge_layer()
    assert badge[1].shape[1] < 300


def test_end_card_without_a_channel_name(monkeypatch):
    monkeypatch.setattr(compose.config, "NAME_HI", None)
    monkeypatch.setattr(compose.config, "NAME", None)
    logo, src, disc = compose._end_layers((255, 205, 92))
    assert logo is None and src[1].shape[1] > 0 and disc[1].shape[1] < compose.W
    monkeypatch.setattr(compose.config, "NAME_HI", "समाचार डेस्क")
    assert compose._end_layers((255, 205, 92))[0] is not None


def test_camera_moves_with_numpy_scalars():
    from types import SimpleNamespace

    size = (np.int64(compose.H + 120), np.int64(compose.W + 120))
    plate = SimpleNamespace(pw=size[1], ph=size[0], rgb=np.full((*size, 3), 90, np.uint8),
                            depth=np.zeros(size, np.float32))
    frame = compose.Camera().shoot(plate, np.float64(0.4), compose.MOTIONS[1], punch=np.float64(0.02))
    assert frame.shape == (compose.H, compose.W, 3) and frame.dtype == np.uint8 and frame.mean() > 80


def test_mix_lasts_as_long_as_the_video(tmp_path):
    import soundfile as sf

    t = np.arange(int(2.0 * 24000)) / 24000
    sf.write(tmp_path / "narration.wav", (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 24000)
    short = Short(id="t1", kind="death", title="T", beats=[], facts=[], sources=[], loss=False,
                  scene={"mood": "tribute"})
    mixed = compose._mix(tmp_path / "narration.wav", short, 2.6, tmp_path)
    assert abs(sf.info(str(mixed)).duration - 2.6) < 0.01
