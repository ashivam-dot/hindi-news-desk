from dataclasses import replace
from pathlib import Path

import pytest

from desk import config, youtube
from desk.spec import Short

FIXTURE = Path(__file__).parent / "fixtures" / "wk-Q900001.json"
GEMINI = {"engine": "gemini-sulafat", "identity": "sulafat", "preview": False}
UC = "UC" + "x" * 22


@pytest.fixture
def short() -> Short:
    return Short.load(FIXTURE)


def test_identity_refuses_while_the_channel_id_is_tbd(monkeypatch):
    monkeypatch.setattr(config, "CHANNEL_ID", "TBD")
    with pytest.raises(youtube.WrongChannel, match="not configured"):
        youtube.check_identity([{"id": "TBD"}])


def test_identity_refuses_another_channel(monkeypatch):
    monkeypatch.setattr(config, "CHANNEL_ID", UC)
    assert youtube.check_identity([{"id": UC}])["id"] == UC
    with pytest.raises(youtube.WrongChannel):
        youtube.check_identity([{"id": "UC" + "y" * 22}])
    with pytest.raises(youtube.WrongChannel):
        youtube.check_identity([{"id": UC}, {"id": UC}])
    with pytest.raises(youtube.WrongChannel):
        youtube.check_identity([])


def test_channel_id_format(monkeypatch):
    monkeypatch.setattr(config, "CHANNEL_ID", "UCfqAy1IxE2Cwu9pmZGMambA")
    assert config.channel_id_ready()
    monkeypatch.setattr(config, "CHANNEL_ID", "UC123")
    assert not config.channel_id_ready()


def test_publish_refuses_a_preview_voice_before_touching_youtube(short, tmp_path, monkeypatch):
    def never():
        raise AssertionError("signed in to YouTube")
    monkeypatch.setattr(youtube, "client", never)
    for bad in ({"engine": "chatterbox-preview", "identity": "preview", "preview": True},
                {"engine": "kokoro", "identity": "af_heart", "preview": False}, None):
        with pytest.raises(ValueError, match="voice"):
            youtube.publish(short, tmp_path / "short.mp4", bad)


def test_description_is_hindi_with_sources_credits_and_the_ai_label(short):
    text = youtube.description(short, GEMINI)
    assert "स्रोत:" in text and "https://en.wikipedia.org/wiki/Ramesh_Prasad_Verma" in text
    assert "AI आवाज़" in text and "Sulafat" in text and "Wikimedia Commons" in text
    assert "https://commons.wikimedia.org/wiki/File:Ramesh_Prasad_Verma_2010.jpg" in text
    assert len(text) <= 4900 and "<" not in text and ">" not in text
    clone = youtube.description(short, {"engine": "chatterbox-sulafat-clone"})
    assert "Chatterbox" in clone


def test_a_long_description_drops_the_narration_before_any_source_or_credit(short):
    url = "https://commons.wikimedia.org/wiki/File:" + "%CE%A3" * 70 + ".jpg"
    many = replace(short, credits=short.credits + [f"फ़ोटो: Author {i} / CC BY-SA 2.0 / Wikimedia Commons {url}"
                                                   for i in range(6)])
    text = youtube.description(many, GEMINI)
    assert len(text.encode()) <= youtube.DESCRIPTION_BYTES
    assert short.beats[0].text not in text
    assert all(s in text for s in short.sources) and "Author 5 / CC BY-SA 2.0" in text and "AI आवाज़" in text
    assert short.beats[0].text in youtube.description(short, GEMINI)


def test_hashtags_keep_devanagari_and_sit_under_the_title(short):
    text = youtube.description(replace(short, hashtags=["rameshprasadverma", "hindinews", "रमेश प्रसाद वर्मा"]), GEMINI)
    assert text.splitlines()[:2] == [short.title, "#rameshprasadverma #hindinews #रमेशप्रसादवर्मा"]
    assert text.count("#hindinews") == 1


def test_the_upload_title_carries_shorts_and_the_subject_tag_when_it_fits(short):
    tagged = replace(short, title="LK Advani: अस्पताल से छुट्टी मिली", hashtags=["lkadvani", "hindinews"])
    assert youtube.upload_title(tagged) == "LK Advani: अस्पताल से छुट्टी मिली #shorts #lkadvani"
    long = replace(tagged, title="क" * 92)
    assert youtube.upload_title(long) == "क" * 92 + " #shorts"
    assert youtube.upload_title(replace(tagged, title="क" * 99)) == "क" * 99


def test_tags_keep_the_marker(short):
    tags = youtube.tags(replace(short, tags=[f"टैग संख्या {i}" for i in range(80)]))
    assert tags[-1] == config.MARKER + short.id and sum(len(t) + 2 for t in tags) <= 482


def test_upload_metadata_is_hindi_news():
    assert config.LANGUAGE == "hi" and youtube.CATEGORY == "25" and youtube.MARKER == "hindi-news-desk:"
