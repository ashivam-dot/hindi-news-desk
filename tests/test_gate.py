import copy
from dataclasses import replace
from datetime import date
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


def test_a_death_is_held_without_a_news_report_that_states_it(short):
    """FMKaXjYtmOk (Nana Patekar) went out on Wikidata and the infobox alone, with report_urls: []."""
    from desk import cli

    assert cli.report_urls(short) == ["https://www.thehindu.com/example/ramesh-prasad-verma"]
    bare = replace(short, scene={k: v for k, v in short.scene.items() if k != "death_reports"})
    assert cli.report_urls(bare) == []
    assert any("no news report states the death" in p for p in gate.check(bare))
    [row] = short.scene["death_reports"]
    other = replace(short, scene=dict(short.scene, death_reports=[row | {"says": "Ramesh Prasad Verma sang in 12 "
                                                                                 "languages."}]))
    assert any("no news report states the death" in p for p in gate.check(other))
    plain = replace(short, scene=dict(short.scene, death_reports=[row | {"url": "http://example.com/x"}]))
    assert any("no news report states the death" in p for p in gate.check(plain))
    incident = replace(bare, kind="incident")
    assert not any("states the death" in p for p in gate.check(incident))


def test_a_death_sentence_must_name_the_person():
    names = ["Ramesh Prasad Verma", "रमेश प्रसाद वर्मा"]
    assert gate.states_death("Veteran singer Ramesh Prasad Verma passed away in Mumbai on Thursday.", names)
    assert gate.states_death("मशहूर गायक रमेश प्रसाद वर्मा का गुरुवार को निधन हो गया।", names)
    assert gate.states_death("Ramesh Prasad Verma was admitted to hospital. His brother died in 2001.", names) is None
    assert gate.states_death("Ramesh Prasad Verma studied in Varanasi.", names) is None


def _verma_item(monkeypatch, body, key="thehindu"):
    from desk import outlets

    o = next(o for o in outlets.OUTLETS if o["key"] == key)
    item = {"title": "Singer Ramesh Prasad Verma passes away", "url": f"https://{key}.example/verma",
            "outlet": o["name"], "outlet_hi": o["name_hi"], "owner": o["owner"], "group": o["group"],
            "lang": o["lang"], "geo": o["geo"], "feed": key, "at": "2026-10-08T10:00:00+00:00", "summary": ""}
    monkeypatch.setattr(outlets, "text", lambda url: body if url == item["url"] else None)
    return item


def _death_build(monkeypatch, reports):
    """build_death up to its death check: a Wikidata item that died on 8 October 2026 and an infobox that says so."""
    from desk import wiki, writer

    ent = {"labels": {"en": {"value": "Ramesh Prasad Verma"}, "hi": {"value": "रमेश प्रसाद वर्मा"}},
           "claims": {p: [{"mainsnak": {"datavalue": {"value": {"time": t}}}}]
                      for p, t in (("P569", "+1945-03-02T00:00:00Z"), ("P570", "+2026-10-08T00:00:00Z"))}}
    monkeypatch.setattr(wiki, "entities", lambda qids: {"Q900001": ent})
    monkeypatch.setattr(wiki, "infobox", lambda title: ("", {"occupation": "singer"}, {"death_date": "8 October 2026"}))
    monkeypatch.setattr(writer, "_today_ist", lambda: date(2026, 10, 9))
    monkeypatch.setattr(writer, "_shared", lambda *a: pytest.fail("past the death check"))
    cand = {"id": "wk-Q900001", "title": "Ramesh Prasad Verma", "qid": "Q900001", "reports": reports}
    return lambda: writer.build_death(cand)


def test_build_death_holds_a_death_no_report_states(monkeypatch):
    with pytest.raises(ValueError, match="no news report states the death of Ramesh Prasad Verma"):
        _death_build(monkeypatch, [])()
    item = _verma_item(monkeypatch, "Ramesh Prasad Verma will sing in Mumbai next month, the organisers said. " * 5)
    item["title"] = "Ramesh Prasad Verma to sing in Mumbai"
    with pytest.raises(ValueError, match="no news report states the death"):
        _death_build(monkeypatch, [item])()


def test_one_confirming_report_lets_a_death_through(monkeypatch):
    from desk import writer

    body = "Veteran playback singer Ramesh Prasad Verma died in Mumbai on Thursday, his family said. " * 5
    item = _verma_item(monkeypatch, body)
    with pytest.raises(pytest.fail.Exception, match="past the death check"):
        _death_build(monkeypatch, [item])()
    [row] = writer.death_reports({"reports": [item]}, [], "Ramesh Prasad Verma", "रमेश प्रसाद वर्मा",
                                 writer._since(date(2026, 10, 8)))
    assert row["url"] == item["url"] and row["name"] == "Ramesh Prasad Verma" and row["says"] == item["title"] + "."
    assert "text" not in row  # the scene keeps the sentence, not the article


@pytest.mark.parametrize("says", [
    "Satish Shah is alive, family dismisses reports that he died.",
    "Satish Shah death hoax: actor's team says reports of his demise are fake.",
    "सतीश शाह के निधन की खबर झूठी, परिवार ने कहा- वह स्वस्थ हैं।",
    "सतीश शाह की मौत की अफवाह, टीम ने किया खंडन।",
    "Satish Shah has not died, his son says after posts claimed he passed away.",
    "Satish Shah did not die in the crash, police said.",
    "सतीश शाह का निधन नहीं हुआ, बेटे ने बताया।",
    "सतीश शाह की मौत नहीं हुई है।",
])
def test_a_sentence_that_denies_the_death_never_states_it(says):
    # The 2026-10-22 on-air review: a vandalised P570 is when outlets write "X is alive".
    names = ["Satish Shah", "सतीश शाह"]
    assert gate.states_death(says, names) is None and gate.denies_death(says, names)
    assert gate.states_death("Veteran actor Satish Shah dies at 74.", names)
    assert gate.denies_death("Veteran actor Satish Shah dies at 74. He was cremated in Mumbai.", names) is None


def test_an_article_about_a_death_hoax_never_confirms_it(monkeypatch):
    from desk import writer

    body = ("Ramesh Prasad Verma died on Thursday, a post on social media claimed. His manager said the reports are "
            "false and the singer is at home. ") * 3
    item = _verma_item(monkeypatch, body)
    assert writer.death_reports({"reports": [item]}, [item | {"text": body}], "Ramesh Prasad Verma",
                                "रमेश प्रसाद वर्मा", writer._since(date(2026, 10, 8))) == []
    with pytest.raises(ValueError, match="no news report states the death"):
        _death_build(monkeypatch, [item])()


def test_a_hindi_report_may_write_the_name_without_its_dots(monkeypatch):
    from desk import writer

    item = _verma_item(monkeypatch, "मशहूर गायक आर पी वर्मा का गुरुवार को मुंबई में निधन हो गया। " * 5)
    item["title"] = "गायक आर पी वर्मा नहीं रहे"
    [row] = writer.death_reports({"reports": []}, [item | {"text": "मशहूर गायक आर पी वर्मा का गुरुवार को निधन।"}],
                                 "R.P. Verma", "आर.पी. वर्मा", writer._since(date(2026, 10, 8)))
    assert row["name"] == "आर पी वर्मा"


def test_a_death_search_reads_at_most_death_reads_articles(monkeypatch):
    from desk import outlets, writer

    rows = [_verma_item(monkeypatch, "") | {"url": f"https://thehindu.example/verma-{n}",
                                               "title": "Ramesh Prasad Verma in Mumbai"} for n in range(20)]
    read = []
    monkeypatch.setattr(writer, "_report_rows", lambda *a, **k: rows)
    monkeypatch.setattr(outlets, "text", lambda url: read.append(url) or "Ramesh Prasad Verma sang in Mumbai.")
    assert writer.death_reports({}, [], "Ramesh Prasad Verma", None, writer._since(date(2026, 10, 8))) == []
    assert len(read) == writer.DEATH_READS


def test_a_death_no_report_states_yet_is_retried_not_skipped():
    # The 2026-10-22 correctness review: Wikidata's P570 comes before the outlets' items, and a skip is for good.
    from desk import cli

    assert any(m in "gate: no news report states the death of Ramesh Prasad Verma" for m in cli.RETRYABLE)


# YM2dyGiYNJQ (2026-10-20): the reporting gave the resignation demand to Congress's Sapkal; Raut alleged "jungle raj"
# and asked for President's Rule.
RAUT_NAMES = [{"hi": "टाइगर श्रॉफ", "en": "Tiger Shroff"}, {"hi": "संजय राउत", "en": "Sanjay Raut"},
              {"hi": "देवेंद्र फडणवीस", "en": "Devendra Fadnavis"}, {"hi": "हर्षवर्धन सपकाल", "en": "Harshwardhan Sapkal"}]
RAUT_REPORTS = [
    {"owner": "The Hindu Group", "title": "Opposition targets Fadnavis after firing at Tiger Shroff's house",
     "text": "Shiv Sena (UBT) MP Sanjay Raut alleged 'jungle raj' in Maharashtra and demanded President's Rule. "
             "Maharashtra Congress chief Harshwardhan Sapkal demanded the resignation of Chief Minister Devendra "
             "Fadnavis."},
    {"owner": "Bennett, Coleman & Co.", "title": "Raut slams Fadnavis govt, says regime change needed",
     "text": "Raut said regime change was needed and demanded President's Rule in the state. Sapkal sought "
             "Fadnavis's resignation over the law and order situation."},
    {"owner": "Living Media", "title": "टाइगर श्रॉफ के घर फायरिंग पर सियासत",
     "text": "संजय राउत ने महाराष्ट्र में 'जंगल राज' का आरोप लगाया और राष्ट्रपति शासन की मांग की।"},
]
RAUT_WRONG = "Tiger Shroff: फायरिंग के बाद राउत की फडणवीस से इस्तीफे की मांग"
RAUT_RIGHT = "Tiger Shroff: फायरिंग के बाद राउत ने लगाया 'जंगल राज' का आरोप, राष्ट्रपति शासन की मांग"


def test_a_demand_given_to_the_wrong_person_is_refused():
    [(who, claim, what, _)] = gate.claims(RAUT_WRONG, RAUT_NAMES)
    assert (who["en"], claim, what) == ("Sanjay Raut", "demand", "resignation")  # Fadnavis is asked, not asking
    [problem] = gate.unattributed(RAUT_WRONG, RAUT_NAMES, RAUT_REPORTS)
    assert "Sanjay Raut a demand (resignation)" in problem and "Sapkal demanded the resignation" in problem
    assert gate.claim_backers(RAUT_NAMES[3], "demand", "resignation", RAUT_REPORTS) == ["Bennett, Coleman & Co.",
                                                                                       "The Hindu Group"]
    # ने marks Raut as the one demanding; फडणवीस के इस्तीफे is whose resignation.
    assert gate.unattributed("राउत ने फडणवीस के इस्तीफे की मांग की।", RAUT_NAMES, RAUT_REPORTS)


def test_a_claim_attributed_as_the_reporting_does_passes():
    found = [(w["en"], c, o) for w, c, o, _ in gate.claims(RAUT_RIGHT, RAUT_NAMES)]
    assert found == [("Sanjay Raut", "allegation", None), ("Sanjay Raut", "demand", "President's Rule")]
    assert gate.unattributed(RAUT_RIGHT, RAUT_NAMES, RAUT_REPORTS) == []
    assert gate.unattributed("सपकाल ने फडणवीस के इस्तीफे की मांग की।", RAUT_NAMES, RAUT_REPORTS) == []


def test_whose_is_not_who_and_an_institutions_last_word_names_no_one():
    # The 2026-10-22 correctness review's false refusals.
    imran, court = [{"hi": "इमरान खान", "en": "Imran Khan"}], [{"hi": "सुप्रीम कोर्ट", "en": "Supreme Court"}]
    assert gate.claims("इमरान खान के वकील ने कहा कि सुनवाई टली।", imran) == []  # the lawyer's words
    assert gate.claims("बॉम्बे हाई कोर्ट ने जांच का आदेश दिया।", court) == []  # another court
    assert [(c, o) for _, c, o, _ in gate.claims("सुप्रीम कोर्ट ने जांच का आदेश दिया।", court)] == [("order", "probe")]
    # ने is who, whatever follows it: an object right after it is still this name's claim.
    assert [(w["en"], c, o) for w, c, o, _ in gate.claims("राउत ने जांच की मांग की।", RAUT_NAMES)] == [
        ("Sanjay Raut", "demand", "probe")]
    # Reports write saying many ways: "claimed", "wrote on X", बताया.
    rahul = [{"hi": "राहुल गांधी", "en": "Rahul Gandhi"}]
    reports = [{"owner": "A", "title": "", "text": "Rahul Gandhi claimed votes were being stolen in Bihar."},
               {"owner": "B", "title": "", "text": "Rahul Gandhi wrote on X that votes are being stolen."},
               {"owner": "C", "title": "", "text": "राहुल गांधी ने बताया कि बिहार में वोट चोरी हो रही है।"}]
    said = "राहुल गांधी ने कहा कि बिहार में वोट चोरी हो रही है।"
    assert gate.unattributed(said, rahul, reports[:2]) == [] and gate.unattributed(said, rahul, reports[1:]) == []


def test_one_owner_is_not_enough_and_a_claim_needs_a_named_claimant():
    # In English only The Hindu has Raut alleging anything; the Hindi report's owner was the second.
    assert gate.unattributed(RAUT_RIGHT, RAUT_NAMES, RAUT_REPORTS[:2])
    # The Wikipedia ground backs a claim on its own, as it backs a name or a number.
    assert gate.unattributed(RAUT_RIGHT, RAUT_NAMES, RAUT_REPORTS[:2],
                             ground="Raut alleged jungle raj in the state.") == []
    # आरोपी is the accused, not an allegation; a demand no listed name makes is no one's claim.
    assert gate.claims("पुलिस ने राउत के घर के पास से दो आरोपी पकड़े।", RAUT_NAMES) == []
    assert gate.claims("मुंबई में बिजली की मांग बढ़ी।", RAUT_NAMES) == []


@pytest.mark.parametrize("text", [
    "रमेश प्रसाद वर्मा के निधन की खबर गलत, परिवार बोला- वह ठीक हैं। सोशल मीडिया पर रमेश प्रसाद वर्मा के निधन की खबर वायरल हुई।",
    "रमेश प्रसाद वर्मा का नहीं हुआ निधन, बेटी ने बताया सच।",
    "Reports that Ramesh Prasad Verma died are untrue, his family said.",
    "Ramesh Prasad Verma has not passed away, his family clarified on Thursday. He is recovering at home.",
    "Ramesh Prasad Verma passed away? Family says the singer is doing well.",
    "Ramesh Prasad Verma never died, his manager said.",
])
def test_a_hoax_debunk_never_confirms_a_death(text):
    """2026-10-22 review: each of these articles was taken as the report that confirms the death."""
    names = ["Ramesh Prasad Verma", "रमेश प्रसाद वर्मा"]
    assert gate.denies_death(text, names)


@pytest.mark.parametrize("text", [
    "मशहूर गायक रमेश प्रसाद वर्मा का गुरुवार को मुंबई में निधन हो गया। रमेश प्रसाद वर्मा पिछले कुछ समय से स्वस्थ नहीं थे।",
    "Veteran singer Ramesh Prasad Verma died in Mumbai on Thursday. Last year, fake reports of his death had circulated "
    "on social media.",
    "Veteran singer Ramesh Prasad Verma died in Mumbai on Thursday. Ramesh Prasad Verma kept the ghazal alive for five "
    "decades.",
    "Veteran singer Ramesh Prasad Verma died on Thursday. He was posthumously honoured by the guild, which denied entry "
    "to fans.",
])
def test_an_obituary_with_a_passing_denial_word_still_confirms_the_death(text):
    """2026-10-22 review: "स्वस्थ नहीं थे", an old hoax and "kept ... alive" each threw out a true obituary."""
    names = ["Ramesh Prasad Verma", "रमेश प्रसाद वर्मा"]
    assert gate.states_death(text, names) and gate.denies_death(text, names) is None


def test_a_statement_backed_in_other_spellings_or_by_a_pronoun_is_attributed():
    """2026-10-22 review: फडनवीस/फड़नवीस and "Fadnavis visited ... He said" backed nothing, sinking every draft."""
    names = [{"en": "Devendra Fadnavis", "hi": "देवेंद्र फडणवीस"}]
    spelled = [{"owner": "Amar Ujala", "title": "फडनवीस का बयान", "text": "मुख्यमंत्री देवेन्द्र फडनवीस ने कहा कि सरकार जांच कराएगी।"},
               {"owner": "Dainik Bhaskar", "title": "फड़नवीस बोले", "text": "सीएम फड़नवीस ने कहा कि दोषियों को बख्शा नहीं जाएगा।"}]
    assert gate.unattributed("मुख्यमंत्री देवेंद्र फडणवीस ने कहा कि सरकार जांच कराएगी।", names, spelled) == []
    pronoun = [{"owner": "Indian Express", "text": "Chief Minister Devendra Fadnavis visited the site on Monday. He said "
                "the guilty would not be spared."}, spelled[1]]
    assert gate.unattributed("मुख्यमंत्री फडणवीस ने कहा कि दोषियों को बख्शा नहीं जाएगा।", names, pronoun) == []
    # The pronoun speaks only for the sentence right before it, and another surname is never a spelling of this one.
    raut = [{"owner": "A", "text": "Sanjay Raut met reporters. Congress's Harshwardhan Sapkal demanded Fadnavis's "
             "resignation."}, {"owner": "B", "text": "हर्षवर्धन सपकाल ने फडणवीस के इस्तीफे की मांग की।"}]
    assert gate.unattributed("संजय राउत ने फडणवीस के इस्तीफे की मांग की।", [{"en": "Sanjay Raut", "hi": "संजय राउत"}],
                             raut)


@pytest.mark.parametrize("text", [
    "Satish Shah passes away?. The veteran actor is hale and hearty and at home in Mumbai, his son told reporters.",
    "सतीश शाह का निधन?. वे घर पर आराम कर रहे हैं और बिल्कुल ठीक हैं।",
    "Satish Shah hasn't passed away, confirms his son.",
    "सतीश शाह की मौत की खबरें गलत।",
    "सतीश शाह के निधन की खबर निकली गलत।",
    "Viral posts claimed that Satish Shah died on Monday. His family said the reports are incorrect.",
    "Several posts claimed that veteran actor Satish Shah died on Monday. Earlier today, his daughter denied the reports.",
    "सोशल मीडिया पर सतीश शाह के निधन की खबर वायरल हुई। उनकी बेटी ने पहले ही इन खबरों का खंडन कर दिया है।",
])
def test_the_second_reviews_hoaxes_never_confirm_a_death(text):
    names = ["Satish Shah", "सतीश शाह"]
    assert gate.denies_death(text, names)
    assert not gate.states_death("Satish Shah passes away?.", names)  # a stored "says" is refused again too


def test_a_pronoun_or_a_sound_alike_never_gives_raut_another_persons_demand():
    """2026-10-22 second review: रात ("night") sounded like Raut, and "Sapkal hit back at Raut. He demanded ..."
    gave Raut the resignation demand."""
    names = [{"en": "Sanjay Raut", "hi": "संजय राउत"}, {"en": "Devendra Fadnavis", "hi": "देवेंद्र फडणवीस"},
             {"en": "Harshwardhan Sapkal", "hi": "हर्षवर्धन सपकाल"}]
    line = "संजय राउत ने फडणवीस के इस्तीफे की मांग की।"
    for reports in (
        [{"owner": "A", "text": "देर रात कांग्रेस प्रदेश अध्यक्ष हर्षवर्धन सपकाल ने फडणवीस के इस्तीफे की मांग की।"},
         {"owner": "B", "text": "सोमवार रात सपकाल ने मुख्यमंत्री फडणवीस से इस्तीफे की मांग की।"}],
        [{"owner": "A", "text": "Harshwardhan Sapkal hit back at Sanjay Raut. He demanded Fadnavis's resignation."},
         {"owner": "B", "text": "सपकाल ने राउत पर पलटवार किया। उन्होंने फडणवीस के इस्तीफे की मांग की।"}],
        [{"owner": "A", "text": "संजय राउत मीडिया से मिले। उनके बाद सपकाल ने फडणवीस से इस्तीफे की मांग की।"},
         {"owner": "B", "text": "संजय राउत मीडिया से मिले। उनके बाद सपकाल ने फडणवीस से इस्तीफे की मांग की।"}],
    ):
        assert gate.unattributed(line, names, reports), reports[0]["text"]


@pytest.mark.parametrize("name, text", [
    ("Krishnaswamy Kasturirangan", "Former ISRO chief K. Kasturirangan passes away at 84. He led ISRO for nine years."),
    ("Krishnaswamy Kasturirangan", "K Kasturirangan died in Bengaluru on Friday."),
    ("V. S. Achuthanandan", "VS Achuthanandan, Former Kerala Chief Minister, Dies At 101"),
    ("V. S. Achuthanandan", "V.S. Achuthanandan died on Monday."),
    ("M. T. Vasudevan Nair", "M.T. Vasudevan Nair died at a private hospital in Kozhikode."),
    ("M. T. Vasudevan Nair", "MT Vasudevan Nair dies at 91"),
])
def test_a_death_reported_with_the_persons_initials_is_stated(name, text):
    """2026-10-22 third review: the press writes a Wikidata name by its initials, and "K. " ended a sentence."""
    assert gate.states_death(text, [name]) and gate.denies_death(text, [name]) is None


@pytest.mark.parametrize("text", [
    "Dharmendra dies at 89. Veteran actor Dharmendra passed away on Monday at his Mumbai home. Earlier this month, "
    "his family had dismissed reports of his death as false after he was hospitalised.",
    "Dharmendra dies at 89. Veteran actor Dharmendra passed away on Monday. Earlier this month, fake news of his "
    "death had spread on social media, which Hema Malini slammed.",
    "धर्मेंद्र का 89 साल की उम्र में निधन. धर्मेंद्र का निधन हो गया। इससे पहले इसी महीने उनके निधन की झूठी खबरें फैली थीं।",
    "Dharmendra passes away at 89: Who was he?. He acted in Sholay.",
])
def test_an_obituary_recalling_a_recent_hoax_or_asking_who_he_was_still_confirms_the_death(text):
    """2026-10-22 third review: Dharmendra's and Ratan Tata's obituaries recalled false reports from days before."""
    names = ["Dharmendra", "धर्मेंद्र"]
    assert gate.states_death(text, names) and gate.denies_death(text, names) is None
