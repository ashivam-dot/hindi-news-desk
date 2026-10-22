import copy

import pytest

from desk import wiki, writer

REAL_READINGS = wiki.hindi_readings  # conftest stubs it for every test

SOURCE_EN = ("Ramesh Prasad Verma (2 March 1945 – 8 October 2026) was an Indian playback singer from Varanasi. His first "
             "album came out in 1968. He sang in 12 languages, and more than 300,000 people attended one concert in "
             "Mumbai. He received the Padma Shri in 1999 and dedicated it to his teacher.")
SOURCE_HI = "रमेश प्रसाद वर्मा वाराणसी के गायक थे। उन्हें 1999 में पद्म श्री मिला।"
HI_NAMES = {"Ramesh Prasad Verma": "रमेश प्रसाद वर्मा", "Varanasi": "वाराणसी", "Mumbai": "मुंबई"}
SUBJECT = {"en": "Ramesh Prasad Verma", "hi": "रमेश प्रसाद वर्मा", "person": True}
PHOTOS = [{"file": f"File:{i}.jpg", "description": "Ramesh Prasad Verma"} for i in range(3)]
SAYS = [
    "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे, 8 अक्टूबर 2026 को उनका निधन हो गया।",
    "रमेश वाराणसी के रहने वाले थे।",
    "1968 में उनका पहला एल्बम आया और पूरे देश ने उस नई आवाज़ को ध्यान से सुना।",
    "उन्होंने 12 भाषाओं में गाया, और उनकी आवाज़ हर घर तक पहुंच गई।",
    "मुंबई के एक संगीत समारोह में 3 लाख से ज़्यादा लोग उन्हें सुनने आए थे।",
    "1999 में उन्हें पद्म श्री मिला, जिसे उन्होंने अपने गुरु को समर्पित कर दिया।",
]
NAMES = [{"hi": "रमेश प्रसाद वर्मा", "en": "Ramesh Prasad Verma"}, {"hi": "वाराणसी", "en": "Varanasi"},
         {"hi": "मुंबई", "en": "Mumbai"}, {"hi": "पद्म श्री", "en": "Padma Shri"}]


def draft(**changes):
    d = {"title": "रमेश प्रसाद वर्मा: सुरों का एक युग", "names": copy.deepcopy(NAMES),
         "beats": [{"say": s, "photo": i % 3, "caption": "श्रद्धांजलि"} for i, s in enumerate(SAYS)]}
    d.update(changes)
    return d


def check(d, **kw):
    args = dict(photos=PHOTOS, subject=SUBJECT, ground_en=SOURCE_EN, ground_hi=SOURCE_HI, hi_names=HI_NAMES,
                banned_names=[], kind="death", agreed_toll=False)
    args.update(kw)
    return writer.validate(d, **args)


def test_a_grounded_hindi_draft_passes():
    problems, doubtful = check(draft())
    assert problems == [] and doubtful == []


def test_a_long_beat_or_a_vague_ending_goes_back_to_the_writer():
    d = draft()
    d["beats"][2]["say"] = ("1968 में उनका पहला एल्बम आया और पूरे देश ने उस नई आवाज़ को ध्यान से सुना और फिर "
                            "उनकी आवाज़ हर घर और हर गली तक पहुंच गई।")
    d["beats"][5]["say"] = "1999 में उन्हें पद्म श्री मिला, और मामले में आगे की कानूनी कार्रवाई जारी है।"
    problems, _ = check(d)
    assert any(p.startswith("beat 3 has 29 words") for p in problems)
    assert any(p.startswith("beat 6 ends on filler") for p in problems)


@pytest.mark.parametrize("say,title", [
    ("आइए जानते हैं रमेश प्रसाद वर्मा के बारे में, 8 अक्टूबर 2026 को उनका निधन हो गया।", None),
    ("दोस्तों, मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे, 8 अक्टूबर 2026 को उनका निधन हो गया!", None),
    ("रमेश प्रसाद वर्मा क्यों याद किए जाएंगे? 8 अक्टूबर 2026 को उनका निधन हो गया।", None),
    (None, "रमेश प्रसाद वर्मा क्यों याद किए जाएंगे?"),
])
def test_a_bulletin_never_chats_exclaims_or_asks(say, title):
    d = draft()
    if say:
        d["beats"][0]["say"] = say
    if title:
        d["title"] = title
    assert writer.casual(d)


def test_the_card_label_is_shown_under_the_caption():
    d = draft()
    d["beats"][0]["label"] = "निधन"
    short = writer._short("kh-x", "explainer", "Ramesh Prasad Verma", "रमेश प्रसाद वर्मा", d, [], [], [],
                          [SOURCE_EN], SOURCE_EN, [{"credit": "c", "page": "p"}], ["https://x"], "2026-10-08",
                          False, "news", [], "", "")
    assert short.beats[0].card == {"big": "श्रद्धांजलि", "small": "निधन"}
    assert short.scene["template"] == "full" and short.beats[-1].shot != "outro"


def test_the_short_reads_with_latin_digits_and_one_spelling_per_name():
    """T7EVpcOu8ME said पोप लियो १४ where other titles say 14; bbx5XceX0sI said एलोन मस्क, QT1s3ANaodI एलन मस्क."""
    d = draft(title="रमेश प्रसाद बर्मा: १९९९ में एलोन मस्क से मिले")
    d["names"][0] = {"hi": "रमेश प्रसाद बर्मा", "en": "Ramesh Prasad Verma"}
    d["beats"][0]["say"] = d["beats"][0]["say"].replace("रमेश प्रसाद वर्मा", "रमेश प्रसाद बर्मा")
    d["beats"][1]["caption"] = "उड़ान १०७३"
    short = writer._short("kh-x", "explainer", "Ramesh Prasad Verma", "रमेश प्रसाद वर्मा", d, [], [], [],
                          [SOURCE_EN], SOURCE_EN, [{"credit": "c", "page": "p"}], ["https://x"], "2026-10-08",
                          False, "news", [], "", "")
    assert short.title == "रमेश प्रसाद वर्मा: 1999 में एलन मस्क से मिले"
    assert short.beats[0].text.startswith("मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे")
    assert short.beats[1].card["big"] == "उड़ान 1073"
    assert short.scene["names"][0]["hi"] == "रमेश प्रसाद वर्मा"
    assert d["title"].startswith("रमेश प्रसाद बर्मा")  # the writer's own draft is kept as it was, for the log


def test_a_surname_only_spelling_of_the_subject_is_not_expanded():
    d = {"title": "डोनाल्ड ट्रंप ने टैरिफ बढ़ाया, ट्रम्प का बड़ा फैसला",
         "beats": [{"say": "अमेरिकी राष्ट्रपति डोनाल्ड ट्रंप ने कहा", "caption": "ट्रंप", "label": ""}],
         "names": [{"en": "Donald Trump", "hi": "ट्रंप"}]}
    out = writer.respelled(d, "Donald Trump", "डोनाल्ड ट्रंप")
    assert out["title"] == "डोनाल्ड ट्रंप ने टैरिफ बढ़ाया, ट्रंप का बड़ा फैसला"
    assert out["beats"][0]["say"] == "अमेरिकी राष्ट्रपति डोनाल्ड ट्रंप ने कहा"
    assert out["names"][0]["hi"] == "ट्रंप"


def test_a_shared_surname_does_not_get_the_subjects_first_name():
    d = {"title": "सोनिया गांधी और राहुल गांधी की बैठक",
         "beats": [{"say": "सोनिया गांधी ने कहा। गांधी परिवार", "caption": "x", "label": ""}],
         "names": [{"en": "Rahul Gandhi", "hi": "गांधी"}]}
    out = writer.respelled(d, "Rahul Gandhi", "राहुल गांधी")
    assert out["title"] == "सोनिया गांधी और राहुल गांधी की बैठक"
    assert out["beats"][0]["say"] == "सोनिया गांधी ने कहा। गांधी परिवार"


def test_a_same_length_variant_of_the_subject_is_respelled():
    d = {"title": "राहुल गाँधी का भाषण", "beats": [],
         "names": [{"en": "Rahul Gandhi", "hi": "राहुल गाँधी"}]}
    assert writer.respelled(d, "Rahul Gandhi", "राहुल गांधी")["title"] == "राहुल गांधी का भाषण"


def test_respelling_takes_whole_words_only():
    from desk import hindi

    assert hindi.respell("ट्रम्प बोले, ट्रम्पकार्ड नहीं") == "ट्रंप बोले, ट्रम्पकार्ड नहीं"
    assert hindi.respell("Pope Leo XIV: लियो १४") == "Pope Leo XIV: लियो 14"


def test_a_number_not_in_the_sources_is_caught():
    d = draft()
    d["beats"][4]["say"] = "मुंबई के एक संगीत समारोह में 5 लाख से ज़्यादा लोग उन्हें सुनने आए थे।"
    problems, _ = check(d)
    assert any("500000" in p for p in problems)


def test_devanagari_digits_are_checked_too():
    d = draft()
    d["beats"][2]["say"] = "१९६७ में उनका पहला एल्बम आया और पूरे देश ने उस नई आवाज़ को ध्यान से सुना।"
    problems, _ = check(d)
    assert any("1967" in p for p in problems)


def test_every_name_pair_must_be_grounded_and_written():
    d = draft(names=NAMES + [{"hi": "कोलकाता", "en": "Kolkata"}])
    problems, _ = check(d)
    assert any("Kolkata" in p and "not in the sources" in p for p in problems)
    assert any("never writes it" in p for p in problems)


def test_wikidata_hindi_spelling_wins():
    d = draft()
    d["beats"][1]["say"] = d["beats"][1]["say"].replace("वाराणसी", "बनारसी")
    d["names"][1] = {"hi": "बनारसी", "en": "Varanasi"}
    problems, _ = check(d)
    assert any("write Varanasi as वाराणसी" in p for p in problems)


def test_a_far_spelling_without_a_label_is_double_checked():
    d = draft()
    # A translation, not a transliteration: the fact-check pass is asked whether it names the same honour.
    d["beats"][5]["say"] = d["beats"][5]["say"].replace("पद्म श्री", "कमल सम्मान")
    d["names"][3] = {"hi": "कमल सम्मान", "en": "Padma Shri"}
    problems, doubtful = check(d, ground_hi="")
    assert doubtful == [{"hi": "कमल सम्मान", "en": "Padma Shri"}] and problems == []


def test_latin_words_must_be_in_the_english_source():
    d = draft()
    d["beats"][3]["say"] = "उन्होंने 12 भाषाओं में गाया, और Grammy जैसी पहचान पाई।"
    problems, _ = check(d)
    assert any("'Grammy'" in p for p in problems)


def test_beat_one_names_the_subject_in_hindi():
    d = draft()
    d["beats"][0]["say"] = "एक मशहूर गायक नहीं रहे, 8 अक्टूबर 2026 को उनका निधन हो गया।"
    problems, _ = check(d)
    assert any("beat 1 must name" in p for p in problems)


def test_beat_one_opens_on_the_person_not_on_the_place():
    d = draft()
    d["beats"][0]["say"] = "पटना में आज मशहूर लोक गायक रमेश प्रसाद वर्मा का 75 साल की उम्र में निधन हो गया।"
    problems, _ = check(d)
    assert any("beat 1 must open on" in p for p in problems)
    d["beats"][0]["say"] = "मशहूर गायक रमेश प्रसाद वर्मा का 75 साल की उम्र में पटना में निधन हो गया।"
    assert not any("beat 1 must" in p for p in check(d)[0])


def test_a_bare_section_name_is_dropped_from_the_card():
    assert writer.card_label(" मुख्य खबर ") == "" and writer.card_label(None) == ""
    assert writer.card_label("पुलिस कार्रवाई") == "पुलिस कार्रवाई"


def test_perpetrators_are_never_named():
    problems, _ = check(draft(), banned_names=["Varanasi Attacker"], kind="incident")
    assert any("perpetrator" in p for p in problems)


def test_decorum_applies_to_drafts():
    d = draft(title="ब्रेकिंग: रमेश प्रसाद वर्मा नहीं रहे")
    problems, _ = check(d)
    assert any("banned" in p for p in problems)


def test_an_angle_shows_in_the_title():
    problems, _ = check(draft(), angle="india")
    assert any("angle" in p for p in problems)
    problems, _ = check(draft(title="रमेश प्रसाद वर्मा: भारत की आवाज़"), angle="india")
    assert not any("angle" in p for p in problems)


def test_subject_matching():
    names = [{"hi": "वर्मा जी", "en": "Verma"}]
    assert writer.subject_in("वर्मा जी नहीं रहे", SUBJECT, names)
    assert writer.subject_in("वर्मा नहीं रहे", SUBJECT, [])
    assert not writer.subject_in("एक गायक नहीं रहे", SUBJECT, [{"hi": "गायक", "en": "Prasad Kumar"}])
    event = {"en": "2026 Varanasi floods", "hi": "2026 वाराणसी बाढ़", "person": False}
    assert writer.subject_in("वाराणसी की बाढ़ ने शहर बदल दिया", event, [{"hi": "वाराणसी की बाढ़", "en": "Varanasi floods"}])


def test_monotone_scripts_are_sent_back():
    flat = {"beats": [{"say": s} for s in ["वे आए।", "वे गए।", "वे गाए।", "फिर लौटे।"]]}
    problems = writer.monotone(flat)
    assert len(problems) == 1 and "3 beats" in problems[0]
    assert writer.monotone(draft()) == []


def test_prompts_carry_the_hindi_names_and_the_protest_rules():
    msgs = writer._messages(writer.PROTEST_BRIEF.format(name="X"), [], "src", "", PHOTOS, "एक्स", HI_NAMES,
                            ["Headline one"])
    text = msgs[1]["content"]
    assert "strictly neutral" in text and "context only" in text and "Varanasi = वाराणसी" in text
    assert "Hindi Wikipedia" not in text
    check_msgs = writer._check_messages("स्क्रिप्ट", NAMES, [], "src", "स्रोत", [{"hi": "क", "en": "K"}])
    assert "DOUBLE-CHECK" in check_msgs[1]["content"] and "SOURCE (Hindi)" in check_msgs[1]["content"]


@pytest.mark.parametrize("headline, ok", [
    ("Ramesh Prasad Verma dies at 81 in Mumbai", True),
    ("Ramesh Prasad Verma dies at 82 in Mumbai", False),
    ("Ramesh Prasad Verma's family thanks Kolkata fans", False),
    ("रमेश प्रसाद वर्मा का निधन", False),
])
def test_headlines_used_as_context_must_be_confirmed(headline, ok):
    from desk import hindi

    assert writer._headline_ok(headline, hindi.values(SOURCE_EN + " 81"), SOURCE_EN) is ok


class FakePen:
    def __init__(self, verdicts, titles=()):
        self.verdicts, self.used, self.titles = list(verdicts), [], list(titles)

    def chat(self, messages, schema=None, **kw):
        self.used.append("fake")
        if schema is writer.CHECK_SCHEMA:
            return {"unsupported": self.verdicts.pop(0)}
        if schema is writer.TITLE_SCHEMA:
            return {"titles": self.titles}
        return draft()


def write(verdicts, tmp_path, titles=()):
    pen = FakePen(verdicts, titles)
    out, log, used = writer.write("death", SUBJECT, "He", [], SOURCE_EN, SOURCE_HI, PHOTOS, HI_NAMES,
                                  log_path=tmp_path / "log.json", pen=pen)
    out.pop("titles", None)
    return out, log, used


def test_a_reviewed_draft_is_checked_first_and_never_rewritten_when_it_passes(tmp_path):
    class NoWriting(FakePen):
        def chat(self, messages, schema=None, **kw):
            assert schema in (writer.CHECK_SCHEMA, writer.TITLE_SCHEMA), "wrote a new draft"
            return super().chat(messages, schema, **kw)

    given = draft()
    out, log, _ = writer.write("death", SUBJECT, "He", [], SOURCE_EN, SOURCE_HI, PHOTOS, HI_NAMES,
                               log_path=tmp_path / "log.json", pen=NoWriting([[]]), start=given)
    assert out["beats"] == given["beats"] and log == []


def test_the_headline_editor_picks_the_first_simple_title(tmp_path):
    out, _, _ = write([[]], tmp_path, titles=["रमेश प्रसाद वर्मा का निधन, अन्तर्राष्ट्रीय पहचान वाले गायक थे",
                                              "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे",
                                              "रमेश प्रसाद वर्मा का निधन"])
    assert out["title"] == "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे"


def test_a_title_gives_a_cause_only_with_who_gives_it():
    d, args = draft(), (SUBJECT, SOURCE_EN, "death", False)
    assert any("cause" in p for p in writer.title_problems("रमेश प्रसाद वर्मा के कार्यक्रम में भगदड़, आयोजक बने वजह",
                                                           d, *args))
    assert not any("cause" in p for p in writer.title_problems(
        "रमेश प्रसाद वर्मा के कार्यक्रम में भगदड़, पुलिस के मुताबिक आयोजक बने वजह", d, *args))
    assert not any("cause" in p for p in writer.title_problems("बारिश के कारण रमेश प्रसाद वर्मा का कार्यक्रम रद्द",
                                                               d, *args))


def test_titles_with_hard_words_new_numbers_or_bare_questions_are_refused():
    d, args = draft(), (SUBJECT, SOURCE_EN, "death", False)
    assert writer.title_problems("मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे", d, *args) == []
    assert any("मुद्रास्फीति" in p for p in writer.title_problems("रमेश प्रसाद वर्मा और मुद्रास्फीति की कहानी", d, *args))
    assert any("numbers" in p for p in writer.title_problems("रमेश प्रसाद वर्मा का 95 साल में निधन", d, *args))
    assert any("question" in p for p in writer.title_problems("रमेश प्रसाद वर्मा कौन थे?", d, *args))
    assert writer.title_problems("रमेश प्रसाद वर्मा ने 12 भाषाओं में गाया, क्या थी वजह?", d, *args) == []
    assert any("names no one" in p for p in writer.title_problems("मशहूर गायक का निधन, संगीत जगत में शोक", d, *args))
    assert any("earlier part" in p for p in writer.title_problems(
        "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे", d, *args, earlier=["मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे"]))


def test_the_headline_editor_prefers_a_natural_headline_to_a_name_label(tmp_path):
    out, _, _ = write([[]], tmp_path, titles=["Ramesh Prasad Verma: मशहूर गायक नहीं रहे",
                                              "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे"])
    assert out["title"] == "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे"


def test_title_style_wants_the_name_first_no_label_no_stock_tail_and_its_own_opening():
    d = draft()
    style = lambda t, **k: writer.title_style(t, d, SUBJECT, **k)  # noqa: E731
    assert style("मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे") == []
    assert any("Name:" in p for p in style("Ramesh Prasad Verma: मशहूर गायक नहीं रहे"))
    for tail in ("रमेश प्रसाद वर्मा ने 12 भाषाओं में गाया, वजह क्या है?", "रमेश प्रसाद वर्मा ने 12 भाषाओं में गाया, क्या थी वजह?",
                 "रमेश प्रसाद वर्मा ने 12 भाषाओं में गाया, क्यों?"):
        assert any("stock tail" in p for p in style(tail)), tail
    assert style("रमेश प्रसाद वर्मा ने गाया, गुरु को क्यों दिया सम्मान?") == []  # 53 characters
    assert any("first 3 words" in p for p in style("संगीत जगत में शोक, मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे"))
    recent = ["मशहूर गायक रमेश प्रसाद वर्मा अस्पताल में भर्ती"]
    assert any("also opens" in p for p in style("मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे", recent=recent))
    assert style("मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे", recent=recent, earlier=recent) == []  # this story's own part


def test_title_style_is_advisory_in_the_last_round(tmp_path):
    out, _, _ = write([[]], tmp_path, titles=["Ramesh Prasad Verma: मशहूर गायक नहीं रहे"])
    assert out["title"] == "Ramesh Prasad Verma: मशहूर गायक नहीं रहे"
    pen = FakePen([[]], ["मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे"])
    title, record = writer.retitle(pen, draft(), SUBJECT, SOURCE_EN, "death", False, recent=[])
    assert title == "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे" and len(record["options"]) == 1


def test_recent_titles_come_from_the_ledger(tmp_path, monkeypatch):
    from desk import ledger
    monkeypatch.setattr(ledger, "STATE", tmp_path)
    ledger.save("published", [{"id": "kh-1", "title": "मशहूर गायक रमेश प्रसाद वर्मा अस्पताल में भर्ती"}])
    out, _, _ = write([[]], tmp_path, titles=["मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे",
                                              "रमेश प्रसाद वर्मा नहीं रहे, 12 भाषाओं में गाया"])
    assert out["title"] == "रमेश प्रसाद वर्मा नहीं रहे, 12 भाषाओं में गाया"


def test_narration_in_a_notices_hindi_or_from_no_one_is_sent_back():
    d = draft()
    assert writer.bookish(d) == []
    d["beats"][1]["say"] = "स्रोत के अनुसार, 77 वर्षीय गायक को अस्पताल में भर्ती कराया गया।"
    d["beats"][2]["caption"] = "2 सप्ताह"
    problems = writer.bookish(d)
    assert any("वर्षीय" in p for p in problems) and any("सप्ताह" in p for p in problems)
    assert any("स्रोत के अनुसार" in p for p in problems)
    d = draft()
    for b in d["beats"][:3]:
        b["say"] = "रिपोर्टों के मुताबिक, " + b["say"]
    assert any("at most 2" in p for p in writer.bookish(d))
    d["beats"][0]["say"] += " 3 प्रतिशत"
    assert not any("प्रतिशत" in p for p in writer.bookish(d))


def test_formal_wikidata_labels_never_bind_the_writer():
    names = {"International Monetary Fund": "अन्तर्राष्ट्रीय मुद्रा कोष", "India Meteorological Department":
             "भारत मौसम विज्ञान विभाग", "United States": "संयुक्त राज्य", "L. K. Advani": "लालकृष्ण आडवाणी"}
    assert writer.everyday_names(names) == {"L. K. Advani": "लालकृष्ण आडवाणी"}
    d = draft(names=NAMES + [{"hi": "IMF", "en": "International Monetary Fund"}])
    assert writer.plain_name("अन्तर्राष्ट्रीय मुद्रा कोष", d, "International Monetary Fund") == "IMF"
    assert writer.plain_name("लालकृष्ण आडवाणी", d, "L. K. Advani") == "लालकृष्ण आडवाणी"


def test_hashtags_are_what_hindi_news_viewers_search():
    assert writer.search_name("L. K. Advani") == "LK Advani"
    assert writer.search_name("Imran Khan (actor)") == "Imran Khan"
    assert writer.search_name("2026 anti-CEC protests") == ""
    tags = writer.hashtags_for("L. K. Advani", "लालकृष्ण आडवाणी", "health", "india", "सुप्रीम कोर्ट ने कहा")
    assert tags[:4] == ["lkadvani", "hindinews", "shorts", "lkadvaninews"]
    assert {"supremecourt", "healthnews", "latestnews", "indianews", "लालकृष्ण आडवाणी"} <= set(tags)
    assert len(tags) <= 15
    event = writer.hashtags_for("2026 anti-CEC protests", "विरोध", "protest", "world", "")
    assert event[:2] == ["hindinews", "shorts"] and "worldnews" in event
    assert writer.search_tags("Imran Khan")[:2] == ["imran khan", "imran khan news"]


def test_no_usable_title_keeps_the_drafts_own(tmp_path):
    out, _, _ = write([[]], tmp_path, titles=["रमेश प्रसाद वर्मा कौन थे?"])
    assert out["title"] == draft()["title"]


SIXTY = "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे, 12 भाषाओं में गाया था"
SEVENTY_TWO = SIXTY + " उन्होंने भी"


def test_a_title_over_55_characters_is_flagged_and_over_65_refused():
    d, args = draft(), (SUBJECT, SOURCE_EN, "death", False)
    assert len(SIXTY) == 60 and len(SEVENTY_TWO) == 72
    assert writer.title_problems(SIXTY, d, *args) == []
    assert any("keep the title to 37-55" in p for p in writer.title_style(SIXTY, d, SUBJECT))
    assert writer.title_style("मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे", d, SUBJECT) == []  # 37: no flag below 55
    assert any("72 characters" in p for p in writer.title_problems(SEVENTY_TWO, d, *args))


def test_the_drafts_own_title_never_falls_back_over_65_characters(tmp_path):
    class LongFirst(FakePen):
        def chat(self, messages, schema=None, **kw):
            if schema is writer.SCHEMA and not any(m["role"] == "assistant" for m in messages):
                self.used.append("fake")
                return draft(title=SEVENTY_TWO)
            return super().chat(messages, schema, **kw)

    pen = LongFirst([[]], ["रमेश प्रसाद वर्मा कौन थे?"])
    out, log, _ = writer.write("death", SUBJECT, "He", [], SOURCE_EN, SOURCE_HI, PHOTOS, HI_NAMES,
                               log_path=tmp_path / "log.json", pen=pen)
    assert any("72 characters" in p for p in log[0]["problems"])
    assert out["title"] == draft()["title"]  # no usable option: the retried draft's own title, not the long one
    with pytest.raises(ValueError, match="at most 65"):
        writer.retitle(FakePen([], ["रमेश प्रसाद वर्मा कौन थे?"]), draft(title=SEVENTY_TWO), SUBJECT, SOURCE_EN,
                       "death", False, recent=[])


def test_checker_items_that_quote_only_the_sources_are_ignored(tmp_path):
    out, log, _ = write([["unsupported: पंडित दीनानाथ मंगेशकर", "कुन्दन लाल सहगल"]], tmp_path)
    assert out == draft() and log == []


def test_checker_items_that_quote_the_script_still_reject(tmp_path):
    flagged = ["'अपने गुरु को समर्पित कर दिया' is not in the sources"]
    out, log, _ = write([flagged, ["The concert size is not stated"], []], tmp_path)
    assert out == draft() and [e["problems"] for e in log] == [
        ["unsupported: " + flagged[0]], ["unsupported: The concert size is not stated"]]
    with pytest.raises(ValueError, match="no draft passed"):
        write([flagged] * writer.DRAFTS, tmp_path)


def test_a_sourced_name_missing_only_from_names_does_not_reject(tmp_path):
    out, log, _ = write([["The organisation 'पद्म श्री' (Padma Shri) is mentioned in SCRIPT but is missing from "
                          "NAMES."]], tmp_path)
    assert out == draft() and log == []
    assert not writer.unlisted_but_sourced("'पद्म श्री' (Bharat Ratna) is missing from NAMES.", SOURCE_EN)
    assert not writer.unlisted_but_sourced("'पद्म श्री' (Padma Shri) is not supported and missing from NAMES.",
                                           SOURCE_EN)


def test_a_name_the_subject_does_not_link_is_still_held_to_wikidatas_spelling(monkeypatch):
    calls = []
    monkeypatch.setattr(wiki, "hindi_spellings",
                        lambda names: calls.append(names) or {"Eknath Shinde": "एकनाथ शिंदे"})
    looked = {}
    bad = {"names": [{"hi": "एकनाथ शून्डे", "en": "Eknath Shinde"}, {"hi": "मुम्बई", "en": "Mumbai"}]}
    spelled = writer.spellings(bad, {"Mumbai": "मुम्बई"}, looked)
    assert spelled == {"Mumbai": "मुम्बई", "Eknath Shinde": "एकनाथ शिंदे"} and calls == [["Eknath Shinde"]]
    writer.spellings(bad, {"Mumbai": "मुम्बई"}, looked)
    assert len(calls) == 1  # a redraft does not look the same name up again
    beats = [{"say": "महाराष्ट्र के उप मुख्यमंत्री एकनाथ शून्डे ने मुलाकात की।", "photo": 0, "caption": "x"}]
    problems, _ = writer.validate({"title": "t", "beats": beats, "names": bad["names"][:1]}, PHOTOS,
                                  {"en": "Eknath Shinde", "hi": None}, "Eknath Shinde visited.", "", spelled, [],
                                  "explainer", False)
    assert "write Eknath Shinde as एकनाथ शिंदे (the Hindi name people know), not एकनाथ शून्डे" in problems


def test_the_hindi_source_is_dropped_when_missing():
    msgs = writer._messages(writer.DEATH_BRIEF.format(name="X", pronoun="he", object="him"), ["f"], "src",
                            "हिंदी स्रोत", PHOTOS, "एक्स", {})
    assert "SOURCE (Hindi Wikipedia):\nहिंदी स्रोत" in msgs[1]["content"] and "- (none)" in msgs[1]["content"]


# Wikidata's search for the two real slips, as it answered on 2026-10-22 (language=hi, uselang=en).
PAIRIS_SEARCH = {"search": [
    {"id": "Q209842", "label": "University of Paris", "description": "French university (c. 1150–1970)",
     "match": {"type": "label", "language": "hi", "text": "पैरिस विश्वविद्यालय"}},
    {"id": "Q724496", "label": "Treaty of Paris", "description": "treaty signed in 1951",
     "match": {"type": "label", "language": "hi", "text": "पैरिस संधि"}},
    {"id": "Q6622287", "label": "Template:Visitor attractions in Paris", "description": "Wikimedia template",
     "match": {"type": "label", "language": "hi", "text": "पैरिस के दर्शनीय स्थल"}},
    {"id": "Q90", "label": "Paris", "description": "capital and most populous city in France",
     "match": {"type": "label", "language": "bho", "text": "पैरिस"}}]}
OBAN_SEARCH = {"search": [{"id": "Q846342", "label": "Obanazawa", "description": "city in Yamagata Prefecture, Japan",
                           "match": {"type": "label", "language": "hi", "text": "ओबानज़वा"}}]}


def test_wikidata_readings_take_whole_hindi_words_only_and_are_cached(monkeypatch):
    calls = []

    def fake(url, params):
        calls.append(params["search"])
        return {"पैरिस": PAIRIS_SEARCH, "ओबान": OBAN_SEARCH}.get(params["search"], {"search": []})
    monkeypatch.setattr(wiki.net, "get_json", fake)
    monkeypatch.setattr(wiki, "_READINGS", {})
    got = REAL_READINGS(["पैरिस", "ओबान"])
    assert got == {"पैरिस": ["University of Paris", "Treaty of Paris", "Paris"]}  # ओबानज़वा is not ओबान
    REAL_READINGS(["पैरिस"])
    assert calls == ["पैरिस", "ओबान"]


def test_a_spelling_hindi_readers_take_for_paris_goes_back_to_the_writer(monkeypatch):
    monkeypatch.setattr(wiki, "hindi_readings", lambda words: {w: r for w, r in {
        "पैरिस": ["University of Paris", "Treaty of Paris", "Paris"], "चेन्नई": ["Chennai"]}.items() if w in words})
    rain = {"names": [{"hi": "पैरिस", "en": "Parrys"}, {"hi": "चेन्नई", "en": "Chennai"}]}
    problems = writer.misread(rain, {}, "चेन्नई में बारिश")
    assert len(problems) == 1 and problems[0].startswith("पैरिस reads as Paris in Hindi, not Parrys")
    assert writer.misread({"names": [{"hi": "पैरीज़", "en": "Parrys"}]}, {}, "") == []
    # A spelling the Hindi sources print, or a name Wikidata labels, is checked elsewhere.
    assert writer.misread(rain, {}, "चेन्नई के पैरिस इलाके में") == []
    assert writer.misread(rain, {"Parrys": "पैरीज़"}, "") == []


def test_aubagne_is_held_to_a_wikidata_label_and_otherwise_passes():
    # Aubagne (Q184047) had no Hindi label on 2026-10-22 and ओबान is no Hindi item's word (only ओबानज़वा), so
    # ओबान cannot be caught without one: a known limit. With a label the writer is held to it.
    beats = [{"say": "फ्रांस के ओबान शहर के एक स्कूल में फायरिंग हुई।", "photo": 0, "caption": "x"}]
    names = [{"hi": "ओबान", "en": "Aubagne"}]
    ground = "A shooting at a school in Aubagne, France."
    problems, _ = writer.validate({"title": "t", "beats": beats, "names": names}, PHOTOS,
                                  {"en": "Aubagne", "hi": None}, ground, "", {"Aubagne": "ओबान्य"}, [], "incident",
                                  False)
    assert "write Aubagne as ओबान्य (the Hindi name people know), not ओबान" in problems
    assert writer.misread({"names": names}, {}, "") == []


def test_a_misread_name_is_advisory_on_the_last_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(writer, "misread", lambda *a, **k: ["पैरिस reads as Paris in Hindi, not Parrys"])
    out, log, _ = write([[]], tmp_path)
    assert len(log) == writer.DRAFTS - 1 and all("Paris" in a["problems"][0] for a in log)
    assert out["beats"] == draft()["beats"]


def test_the_last_beat_says_what_comes_next_or_what_it_means_for_people():
    beats = lambda last: {"beats": [{"say": "पहली बात।"}, {"say": last}]}  # noqa: E731
    assert writer.value_beat(beats("इस फायरिंग में टाइगर श्रॉफ बाल-बाल बच गए, उन्हें कोई गोली नहीं लगी।"), "incident")
    assert writer.value_beat(beats("कोर्ट इस मामले पर 28 अक्टूबर को सुनवाई करेगा।"), "incident") == []
    assert writer.value_beat(beats("नई दरें 1 नवंबर से लागू होंगी, RBI ने बताया।"), "explainer") == []
    assert writer.value_beat(beats("मेट्रो के 45 स्टेशन आज रात तक बंद रहेंगे।"), "explainer") == []
    assert writer.value_beat(beats("वे 12 भाषाओं में गाते थे।"), "death") == []  # an obituary ends on its tributes


def test_a_value_beat_is_advisory_on_the_last_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(writer, "value_beat", lambda d, k: ["the last beat must say what happens next"])
    out, log, _ = write([[]], tmp_path)
    assert len(log) == writer.DRAFTS - 1 and out["beats"] == draft()["beats"]


def test_advice_and_expert_personas_are_never_in_the_script():
    advice = lambda say: writer.advice({"beats": [{"say": say}]})  # noqa: E731
    for say in ("विशेषज्ञों की सलाह है कि अभी सोना खरीदें।", "एक्सपर्ट्स का सुझाव है कि EMI पहले चुकाएं।",
                "ऐसे में निवेश करें तो फायदा होगा।", "आपको अभी अपना पैसा निकाल लेना चाहिए।", "डॉक्टर के बिना दवा न लें।"):
        assert advice(say), say
    for say in ("RBI के मुताबिक EMI 1 नवंबर से बढ़ेगी।", "सरकार ने लोगों से घरों में रहने की अपील की।",
                "अस्पताल ने बताया कि उनका इलाज चल रहा है।"):
        assert advice(say) == [], say
    # Reporting a reason or an attributed, quoted appeal is the news, not advice (review, 2026-10-22).
    for say in ("सरकार ने विशेषज्ञों की सलाह पर स्कूल बंद किए।", 'मोदी ने कहा, "आप सब मतदान करें।"',
                "मोदी ने कहा, “आप सब मतदान करें।”"):
        assert advice(say) == [], say
    assert advice('विशेषज्ञों ने कहा, "अभी सोना खरीदें।"')  # a quote is no cover for an unnamed expert


def test_advice_is_sent_back_but_advisory_on_the_last_draft(tmp_path, monkeypatch):
    d = draft()
    d["beats"][-1]["say"] = "विशेषज्ञों की सलाह है कि लोग अभी सोना खरीदें।"
    assert not any("gives advice" in p for p in check(d)[0])  # not a hard check: it never costs a story
    monkeypatch.setattr(writer, "advice", lambda d: ["beat 6 gives advice (विशेषज्ञों की सलाह)"])
    out, log, _ = write([[]], tmp_path)
    assert len(log) == writer.DRAFTS - 1 and all("gives advice" in a["problems"][0] for a in log)
    assert out["beats"] == draft()["beats"]
