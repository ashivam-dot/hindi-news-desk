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
                                                   for i in range(5)])
    text = youtube.description(many, GEMINI)
    assert len(text.encode()) <= youtube.DESCRIPTION_BYTES
    assert short.beats[0].text not in text
    assert all(s in text for s in short.sources) and "Author 4 / CC BY-SA 2.0" in text and "AI आवाज़" in text
    assert youtube.HOW_MADE in text
    assert short.beats[0].text in youtube.description(short, GEMINI)


def test_the_description_says_once_how_the_short_was_made(short):
    text = youtube.description(short, GEMINI)
    assert text.count(youtube.HOW_MADE_MARK) == 1 and youtube.HOW_MADE in text
    # It sits with the AI disclosure, before the voice line, and promises no human review it does not get.
    lines = text.splitlines()
    assert lines.index(youtube.HOW_MADE) + 1 == next(i for i, line in enumerate(lines) if line.startswith("आवाज़:"))
    assert "पिन" not in text and "इंसान" not in youtube.HOW_MADE


def test_the_how_made_line_goes_last_when_the_description_is_too_long(short, monkeypatch):
    sizes = {}

    def fake(s, voice, narration, grouped, how=True):
        sizes[(narration, grouped, how)] = True
        return "x" * (100 if not how else 6000)
    monkeypatch.setattr(youtube, "_description", fake)
    assert youtube.description(short, GEMINI) == "x" * 100
    assert list(sizes) == [(True, False, True), (False, False, True), (False, True, True), (False, True, False)]


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


def test_the_title_tag_is_whom_the_title_names(short):
    """JEm0Ivq1_74: an explainer centred on Saurav Das, titled after Ashutosh Ranka, went out as #sauravdas."""
    names = [{"hi": "सौरव दास", "en": "Saurav Das"}, {"hi": "आशुतोष रांका", "en": "Ashutosh Ranka"},
             {"hi": "दिल्ली", "en": "Delhi"}]
    ranka = replace(short, kind="explainer", title="Ashutosh Ranka: कोर्ट ने जमानतदार मानने से इनकार किया, क्यों?",
                    hashtags=["sauravdas", "hindinews", "shorts", "sauravdasnews"],
                    scene=dict(short.scene, names=names, name_hi="सौरव दास"))
    assert youtube.upload_title(ranka) == ranka.title + " #shorts #ashutoshranka"
    # The subject named in Hindi, or in English letters, keeps the subject's tag.
    for title in ("सौरव दास की हिरासत दो दिन बढ़ी, कोर्ट ने कहा", "Saurav Das: हिरासत दो दिन बढ़ी, कोर्ट ने कहा"):
        assert youtube.title_tag(replace(ranka, title=title)) == "sauravdas"
    # A title that names nobody in the story carries #shorts alone; a nameless tag is fine anywhere.
    assert youtube.upload_title(replace(ranka, title="कोर्ट ने जमानतदार मानने से इनकार किया, क्यों?")).endswith(
        "क्यों? #shorts")
    assert youtube.title_tag(replace(ranka, hashtags=["hindinews", "shorts"])) == "hindinews"
    # An advisory's hand-picked tags stand.
    assert youtube.title_tag(replace(ranka, kind="advisory", hashtags=["दिल्लीमेट्रो"])) == "दिल्लीमेट्रो"


def test_tags_carry_no_machine_marker(short):
    tags = youtube.tags(replace(short, tags=[f"टैग संख्या {i}" for i in range(80)]))
    assert not any(config.MARKER in t for t in tags) and sum(len(t) + 2 for t in tags) <= 482
    assert youtube.tags(short)[:len(short.tags)] == short.tags


class FakeVideos:
    def __init__(self, items):
        self.items = items

    def list(self, **kwargs):
        return self

    def execute(self):
        return {"items": self.items}


class FakeApi:
    def __init__(self, videos):
        self._videos = videos

    def playlistItems(self):
        return FakeVideos([{"contentDetails": {"videoId": v["id"]}} for v in self._videos])

    def videos(self):
        return FakeVideos(self._videos)


CHANNEL = {"contentDetails": {"relatedPlaylists": {"uploads": "UUx"}}}


def video(vid, title="", tags=None):
    return {"id": vid, "snippet": {"title": title, "tags": tags or []}}


def test_find_uses_the_ledger_id_then_the_old_marker_then_an_unowned_title(tmp_path, monkeypatch):
    from desk import ledger
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    api = FakeApi([video("old", "पुराना", [config.MARKER + "wk-Q1"]), video("new", "नया #shorts"),
                   video("told", "खोया #shorts"), video("lost", "खोया #shorts")])
    assert youtube.find(api, CHANNEL, "wk-Q1")["id"] == "old"  # uploaded before 2026-10-22
    youtube.remember("kh-2", "new")
    assert ledger.load("uploads", {}) == {"kh-2": "new"}
    assert youtube.find(api, CHANNEL, "kh-2", "नया #shorts")["id"] == "new"
    # An upload whose run died before the ledger was saved: the one same-titled video no ledger row owns.
    ledger.save("published", [{"id": "kh-1", "video_id": "told"}])
    assert youtube.find(api, CHANNEL, "kh-3", "खोया #shorts")["id"] == "lost"
    assert youtube.find(api, CHANNEL, "kh-6", "नया #shorts") is None  # "new" is kh-2's
    youtube.remember("kh-4", "lost")
    assert youtube.find(api, CHANNEL, "kh-3", "खोया #shorts") is None
    assert youtube.find(api, CHANNEL, "kh-5") is None


def test_find_refuses_two_unowned_uploads_of_one_story(tmp_path, monkeypatch):
    from desk import ledger
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    api = FakeApi([video("a", "एक #shorts"), video("b", "एक #shorts")])
    with pytest.raises(RuntimeError, match="twice"):
        youtube.find(api, CHANNEL, "kh-1", "एक #shorts")


def test_upload_metadata_is_hindi_news():
    assert config.LANGUAGE == "hi" and youtube.CATEGORY == "25" and youtube.MARKER == "hindi-news-desk:"


class FakeUpdate(FakeVideos):
    def __init__(self, items, writes):
        super().__init__(items)
        self.writes = writes

    def update(self, part, body):
        self.writes.append((part, body))
        return self


def test_untag_keeps_the_ids_then_takes_only_the_marker_off(tmp_path, monkeypatch):
    from desk import ledger
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(config, "CHANNEL_ID", UC)
    items = [{"id": f"v{i}", "snippet": {"channelId": UC, "title": f"शीर्षक {i}", "description": "विवरण",
                                         "categoryId": "25", "defaultLanguage": "hi",
                                         "tags": ["दिल्ली", config.MARKER + f"kh-{i}"]}} for i in range(3)]
    items.append({"id": "clean", "snippet": {"channelId": UC, "title": "साफ़", "tags": ["मुंबई"]}})
    writes = []

    class Api(FakeApi):
        def videos(self):
            return FakeUpdate(items, writes)

        def channels(self):
            return FakeVideos([{"id": UC, **CHANNEL}])

    monkeypatch.setattr(youtube, "client", lambda *a: Api(items))
    assert youtube.untag(limit=2) == 2
    assert ledger.load("uploads", {}) == {"kh-0": "v0", "kh-1": "v1"}
    assert [b["snippet"]["tags"] for _, b in writes] == [["दिल्ली"], ["दिल्ली"]]
    assert writes[0] == ("snippet", {"id": "v0", "snippet": {"title": "शीर्षक 0", "description": "विवरण",
                                                              "categoryId": "25", "tags": ["दिल्ली"],
                                                              "defaultLanguage": "hi"}})
    assert config.UNTAG is False  # off unless the owner sets DESK_UNTAG=true


def test_untag_without_a_write_scope_is_one_clear_note(tmp_path, monkeypatch):
    from desk import ledger
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    monkeypatch.setattr(config, "CHANNEL_ID", UC)
    items = [{"id": "v0", "snippet": {"channelId": UC, "title": "शीर्षक", "tags": [config.MARKER + "kh-0"]}}]

    class Refused(FakeUpdate):
        def execute(self):
            if self.writes:
                raise type("HttpError", (Exception,), {"resp": type("R", (), {"status": 403})()})("forbidden")
            return super().execute()

    class Api(FakeApi):
        def videos(self):
            return Refused(items, [])

        def channels(self):
            return FakeVideos([{"id": UC, **CHANNEL}])

    monkeypatch.setattr(youtube, "client", lambda *a: Api(items))
    # A token that lists only the upload scope is never sent to videos.update.
    monkeypatch.setattr(youtube, "scopes", lambda: {"https://www.googleapis.com/auth/youtube.upload"})
    with pytest.raises(youtube.NoWriteScope, match="youtube.force-ssl"):
        youtube.untag()
    assert ledger.load("uploads", {}) == {}
    # A token that lists no scopes is refused by YouTube with 403: the id is kept, then one clear note.
    monkeypatch.setattr(youtube, "scopes", lambda: None)
    with pytest.raises(youtube.NoWriteScope, match="HTTP 403 after 0 done"):
        youtube.untag()
    assert ledger.load("uploads", {}) == {"kh-0": "v0"}
