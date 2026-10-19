import copy

import pytest

from desk import wiki, writer

SOURCE_EN = ("Ramesh Prasad Verma (2 March 1945 – 8 October 2026) was an Indian playback singer from Varanasi. His first "
             "album came out in 1968. He sang in 12 languages, and more than 300,000 people attended one concert in "
             "Mumbai. He received the Padma Shri in 1999 and dedicated it to his teacher.")
SOURCE_HI = "रमेश प्रसाद वर्मा वाराणसी के गायक थे। उन्हें 1999 में पद्म श्री मिला।"
HI_NAMES = {"Ramesh Prasad Verma": "रमेश प्रसाद वर्मा", "Varanasi": "वाराणसी", "Mumbai": "मुंबई"}
SUBJECT = {"en": "Ramesh Prasad Verma", "hi": "रमेश प्रसाद वर्मा", "person": True}
PHOTOS = [{"file": f"File:{i}.jpg", "description": "Ramesh Prasad Verma"} for i in range(3)]
SAYS = [
    "मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे, 8 अक्टूबर 2026 को उनका निधन हो गया।",
    "वाराणसी की गलियों में पले रमेश बचपन से ही मंदिर के भजनों में अपनी आवाज़ ढूंढते थे।",
    "1968 में उनका पहला एल्बम आया और पूरे देश ने उस नई आवाज़ को ध्यान से सुना।",
    "उन्होंने 12 भाषाओं में गाया, और उनकी आवाज़ हर घर तक पहुंच गई।",
    "मुंबई के एक संगीत समारोह में 3 लाख से ज़्यादा लोग उन्हें सुनने आए थे।",
    "1999 में उन्हें पद्म श्री मिला, जिसे उन्होंने अपने गुरु को समर्पित कर दिया।",
    "मंच के बाहर वे सादगी से रहते थे और हर किसी से प्यार से मिलते थे।",
    "उनकी आवाज़ अब रिकॉर्ड में रहेगी, और उनके सुर हमेशा हमारे साथ रहेंगे।",
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
    assert short.scene["template"] == "bulletin"


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


def test_the_headline_editor_prefers_a_title_led_by_the_name_in_english(tmp_path):
    out, _, _ = write([[]], tmp_path, titles=["मशहूर गायक रमेश प्रसाद वर्मा नहीं रहे",
                                              "Ramesh Prasad Verma: मशहूर गायक नहीं रहे"])
    assert out["title"] == "Ramesh Prasad Verma: मशहूर गायक नहीं रहे"


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


def test_checker_items_that_quote_only_the_sources_are_ignored(tmp_path):
    out, log, _ = write([["unsupported: पंडित दीनानाथ मंगेशकर", "कुन्दन लाल सहगल"]], tmp_path)
    assert out == draft() and log == []


def test_checker_items_that_quote_the_script_still_reject(tmp_path):
    flagged = ["'हर किसी से प्यार से मिलते थे' is not in the sources"]
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
    assert "write Eknath Shinde as एकनाथ शिंदे (Wikidata's Hindi name), not एकनाथ शून्डे" in problems


def test_the_hindi_source_is_dropped_when_missing():
    msgs = writer._messages(writer.DEATH_BRIEF.format(name="X", pronoun="he", object="him"), ["f"], "src",
                            "हिंदी स्रोत", PHOTOS, "एक्स", {})
    assert "SOURCE (Hindi Wikipedia):\nहिंदी स्रोत" in msgs[1]["content"] and "- (none)" in msgs[1]["content"]
