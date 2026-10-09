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


def test_hashtags_keep_devanagari(short):
    last = youtube.description(replace(short, hashtags=["रमेश प्रसाद वर्मा", "हिंदी समाचार", "news"]), GEMINI)
    assert last.splitlines()[-1] == "#रमेशप्रसादवर्मा #हिंदीसमाचार #news"


def test_tags_keep_the_marker(short):
    tags = youtube.tags(replace(short, tags=[f"टैग संख्या {i}" for i in range(80)]))
    assert tags[-1] == config.MARKER + short.id and sum(len(t) + 2 for t in tags) <= 482


def test_upload_metadata_is_hindi_news():
    assert config.LANGUAGE == "hi" and youtube.CATEGORY == "25" and youtube.MARKER == "hindi-news-desk:"
