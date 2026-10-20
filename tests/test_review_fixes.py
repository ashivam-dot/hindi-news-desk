from desk import align, gate, orbitwire, writer


def test_not_today_flags_aaj_and_abhi_but_not_lasting_or_other_words():
    assert writer.not_today("सिनेमा के एक युग का आज अंत हो गया।")
    assert writer.not_today("अभी खबर आई है")
    assert not writer.not_today("उनके गीत आज भी गूंजते हैं।")
    assert not writer.not_today("वे आज़ादी के बाद मशहूर हुईं, आजकल भी याद की जाती हैं।")
    assert not writer.not_today("6 अक्टूबर 2026 को उनका निधन हुआ।")
    # The Tiger Shroff remake failed four drafts on "so far" (2026-10-20).
    assert not writer.not_today("हमले का मकसद अभी तक पूरी तरह से सामने नहीं आया है।")
    assert not writer.not_today("आज तक कोई गिरफ्तारी नहीं हुई।")
    assert writer.not_today("आज भीड़ जमा हुई।")


def test_a_case_short_names_only_the_people_and_places_its_file_lists():
    draft = {"names": [{"en": "Tiger Shroff", "hi": "टाइगर श्रॉफ"}, {"en": "kota", "hi": "कोटा"},
                       {"en": "Some Accused", "hi": "कोई आरोपी"}]}
    assert writer.off_case(draft, ["Tiger Shroff", "Kota"]) == \
        ["Some Accused is not on this case's list of names: leave them out"]


def test_a_case_short_never_says_an_accused_or_gang_name_even_unlisted():
    draft = {"title": "टाइगर श्रॉफ केस", "names": [{"en": "Tiger Shroff", "hi": "टाइगर श्रॉफ"}],
             "beats": [{"say": "पुलिस के मुताबिक़ बिश्नोई गैंग के नाम से दावा हुआ।", "caption": "", "label": ""}]}
    assert writer.off_case(draft, ["Tiger Shroff"], ["Bishnoi", "बिश्नोई"]) == \
        ["never name बिश्नोई (an accused or a gang): leave them out"]
    assert writer.off_case(draft, ["Tiger Shroff"], ["Anil Pandit", "अनिल पंडित"]) == []


def test_casualty_words_cover_more_phrasings_but_not_inside_other_words():
    assert gate.found("हादसे में 12 लोगों की जान चली गई", gate.CASUALTY)
    assert gate.found("एक व्यक्ति मारा गया", gate.CASUALTY)
    assert not gate.found("यह हमारा देश है", gate.CASUALTY)


def test_percentile_rule_needs_ten_candidates():
    small = [orbitwire.PERCENTILE_FLOOR + k for k in range(5)]
    assert orbitwire.high_profile({"fame": max(small)}, small) is None
    many = [orbitwire.PERCENTILE_FLOOR + k for k in range(20)]
    assert orbitwire.high_profile({"fame": max(many)}, many)


def test_extra_speech_before_the_script_is_not_hidden_by_an_unheard_first_word():
    # A read-aloud direction (0-3 s) before the script; Whisper misses the script's first word.
    tokens = [("पहला", 0), ("दूसरा", 0), ("वाक्य", 0), ("यहां", 0)]
    spoken = [("speak calmly in a warm voice", 0.0, 3.0), ("दूसरा", 3.6, 4.0), ("वाक्य", 4.0, 4.5),
              ("यहां", 4.5, 5.0)]
    words, _ = align.align(tokens, spoken)
    assert words[0]["heard"] is False and words[0]["start"] > 2.0
    before, _ = align.outside(words, spoken)
    assert before > 0
