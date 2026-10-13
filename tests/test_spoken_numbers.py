from desk import voice


def test_digits_become_hindi_words_for_chatterbox():
    assert voice.spoken_numbers("12 अक्टूबर 2026 को 34 वर्ष") == "बारह अक्टूबर दो हज़ार छब्बीस को चौंतीस वर्ष"


def test_indian_scale_commas_decimals_and_devanagari_digits():
    assert voice.spoken_numbers("1,50,000 लोग") == "एक लाख पचास हज़ार लोग"
    assert voice.spoken_numbers("1.5 करोड़") == "एक दशमलव पाँच करोड़"
    assert voice.spoken_numbers("२०२६ में") == "दो हज़ार छब्बीस में"
    assert voice.hindi_number(1234567890) == "एक अरब तेईस करोड़ पैंतालीस लाख सड़सठ हज़ार आठ सौ नब्बे"


def test_years_and_hundreds_are_said_as_people_say_them():
    assert voice.hindi_number(1999) == "उन्नीस सौ निन्यानवे"
    assert voice.hindi_number(1500) == "पंद्रह सौ"
    assert voice.hindi_number(105) == "एक सौ पाँच"
    assert voice.hindi_number(2000) == "दो हज़ार"


def test_every_number_under_a_hundred_has_its_own_word():
    assert len(voice.HI_0_99) == 100 and len(set(voice.HI_0_99)) == 100


def test_clock_times_are_spelled_after_speakable():
    assert voice.spoken_numbers(voice.speakable("10:30 को")) == "दस बजकर तीस मिनट को"
