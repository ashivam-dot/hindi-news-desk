import copy
from dataclasses import replace
from pathlib import Path

import pytest

from desk import gate
from desk.spec import Beat, Fact, Short

FIXTURE = Path(__file__).parent / "fixtures" / "wk-Q900001.json"


@pytest.fixture
def short() -> Short:
    return Short.load(FIXTURE)


def test_fixture_story_passes(short):
    assert gate.check(short) == []


@pytest.mark.parametrize("line", ["कम से कम 4,321 घर टूट गए।", "कम से कम ४३२१ घर टूट गए।", "करीब 7 लाख लोग पहुंचे।"])
def test_unsourced_numbers_fail_in_any_script(short, line):
    beats = short.beats[:-1] + [Beat(line, "photo:0"), short.beats[-1]]
    problems = gate.check(replace(short, beats=beats))
    assert any("isn't backed" in p for p in problems), problems


def test_scaled_numbers_match_their_fact(short):
    # 3 लाख is the 300000 the fixture's fact states.
    assert "300000" in gate.numbers("3 लाख से ज़्यादा लोग")
    assert not [p for p in gate.check(short) if "300000" in p]


@pytest.mark.parametrize("bad", ["ब्रेकिंग: रमेश प्रसाद वर्मा का निधन", "रमेश प्रसाद वर्मा की चौंकाने वाली कहानी",
                                 "सनसनीखेज खुलासा: रमेश प्रसाद वर्मा", "SHOCKING: रमेश प्रसाद वर्मा नहीं रहे"])
def test_sensational_titles_fail(short, bad):
    assert any("banned" in p for p in gate.check(replace(short, title=bad)))


def test_whole_words_only(short):
    # तलाश (search) contains लाश (corpse) but is an ordinary word.
    assert gate.found("उनकी तलाश जारी है", gate.BANNED) is None
    assert gate.found("सनसनीखेज", gate.BANNED) == "सनसनी"


def test_emoji_english_titles_and_shouting_fail(short):
    assert any("emoji" in p for p in gate.check(replace(short, title="रमेश प्रसाद वर्मा को श्रद्धांजलि \U0001F525")))
    assert any("not in Hindi" in p for p in gate.check(replace(short, title="A tribute to Ramesh Prasad Verma")))
    assert any("capitals" in p for p in gate.check(replace(short, title="रमेश प्रसाद वर्मा: LEGEND नहीं रहे")))
    assert not [p for p in gate.check(replace(short, title="रमेश प्रसाद वर्मा: ISRO और NASA की श्रद्धांजलि"))
                if "capitals" in p]


def test_narration_must_be_hindi(short):
    beats = [Beat("He was a great singer who sang for many years in many cities. " * 2, "photo:0")] * 5
    assert any("not in Hindi" in p for p in gate.check(replace(short, beats=beats + [short.beats[-1]])))


def test_sources_must_be_https(short):
    assert any("sources" in p for p in gate.check(replace(short, sources=["http://example.com"])))


def test_casualties_need_an_agreed_toll(short):
    incident = replace(short, kind="incident", beats=copy.deepcopy(short.beats))
    incident.beats[1].card = {"big": "कई लोग घायल", "small": ""}
    assert any("casualties without an agreed toll" in p for p in gate.check(incident))
    incident.facts = incident.facts + [Fact("deaths", "12", "https://en.wikipedia.org/wiki/X", ["12"])]
    assert not any("casualties" in p for p in gate.check(incident))


def test_suicide_is_never_mentioned(short):
    beats = short.beats[:-1] + [Beat("पुलिस ने इसे आत्महत्या बताया।", "photo:0"), short.beats[-1]]
    assert any("banned" in p for p in gate.check(replace(short, beats=beats)))


def test_photos_must_be_free_and_credited(short):
    scene = copy.deepcopy(short.scene)
    scene["photos"][1]["license"] = "CC BY-NC 2.0"
    assert any("not free" in p for p in gate.check(replace(short, scene=scene)))
    assert any("not credited" in p for p in gate.check(replace(short, credits=short.credits[:2])))
    scene = copy.deepcopy(short.scene)
    scene["photos"] = scene["photos"][:2]
    assert any("only 2" in p for p in gate.check(replace(short, scene=scene)))


def test_preview_voice_never_passes(short):
    scene = dict(short.scene, voice_preview=True)
    assert any("preview" in p for p in gate.check(replace(short, scene=scene)))


def test_only_the_sulafat_voice_is_publishable():
    assert gate.voice_ok({"engine": "gemini-sulafat", "identity": "sulafat", "preview": False}) is None
    assert gate.voice_ok({"engine": "chatterbox-sulafat-clone", "identity": "sulafat", "preview": False}) is None
    assert gate.voice_ok({"engine": "chatterbox-preview", "identity": "preview", "preview": True})
    assert gate.voice_ok({"engine": "chatterbox", "identity": "sulafat", "preview": False})
    assert gate.voice_ok({"engine": "gemini-kore", "identity": "kore", "preview": False})
    assert gate.voice_ok(None)


def test_shared_stories_need_their_own_angle_and_photos(short):
    ov = {"qid": "Q900001", "status": "published", "orbitwire_id": "wk-Q900001", "angle": "india",
          "high_profile": "fame 900,000 >= 400,000", "photo_pool_checked": True,
          "excluded_photos": ["File:Ramesh Prasad Verma 2010.jpg"]}
    shared = replace(short, scene=dict(short.scene, orbitwire=ov))
    problems = gate.check(shared)
    assert any("भारत से कनेक्शन" in p for p in problems)
    assert any("one Orbitwire would use" in p for p in problems)
    fixed = replace(shared, title="रमेश प्रसाद वर्मा: भारत के सुरों का सफ़र",
                    scene=dict(short.scene, orbitwire=ov | {"excluded_photos": ["File:Other.jpg"]}))
    assert gate.check(fixed) == []
    unchecked = replace(fixed, scene=dict(fixed.scene, orbitwire=ov | {"photo_pool_checked": False,
                                                                       "excluded_photos": []}))
    assert any("not checked" in p for p in gate.check(unchecked))


def test_channel_mix_limits_loss_runs():
    assert gate.channel_mix([True, True], True)
    assert gate.channel_mix([True, True], False) is None
    assert gate.channel_mix([False, True], True) is None
    assert gate.channel_mix([], True) is None
