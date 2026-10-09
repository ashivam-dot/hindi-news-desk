from datetime import date

import pytest

from desk import hindi


@pytest.mark.parametrize("text, want", [
    ("1994 में", [("1994", False)]),
    ("१९९४ में", [("1994", False)]),
    ("15 लाख लोग", [("1500000", True)]),
    ("१५ लाख लोग", [("1500000", True)]),
    ("1.5 करोड़ रुपये", [("15000000", True)]),
    ("डेढ़ करोड़", [("15000000", True)]),
    ("साढ़े 3 लाख", [("350000", True)]),
    ("दो लाख", [("200000", True)]),
    ("15,00,000", [("1500000", False)]),
    ("8,700 people", [("8700", False)]),
    ("2 million", [("2000000", True)]),
    ("सुबह 9:30 बजे", [("9:30", False)]),
    ("3D तस्वीर", []),
])
def test_numbers_are_normalised(text, want):
    assert hindi.numbers(text) == want


def test_plain_number_words_are_not_claims():
    # Orbitwire leaves "two" alone; the desk leaves "दो" alone unless a scale makes it an amount.
    assert hindi.numbers("दो दिन बाद एक नई शुरुआत") == []


def test_a_script_number_must_have_its_value_in_a_source():
    source = hindi.values("About 1.5 million people were displaced in 2026; 260 died.")
    assert hindi.unsupported_numbers("2026 में 15 लाख लोग बेघर हुए, 260 लोगों की जान गई।", source) == []
    assert hindi.unsupported_numbers("16 लाख लोग बेघर हुए", source) == ["1600000"]
    assert hindi.unsupported_numbers("261 लोग", source) == ["261"]
    # A scaled amount may round its source by 1% (1,234,567 is about 12.3 लाख), a bare count may not.
    rounded = hindi.values("1,234,567 people")
    assert hindi.unsupported_numbers("12.3 लाख लोग", rounded) == []
    assert hindi.unsupported_numbers("1234560 लोग", rounded) == ["1234560"]


def test_hindi_source_numbers_count_too():
    source = hindi.values("बाढ़ से ४ लाख लोग प्रभावित हुए।")
    assert hindi.unsupported_numbers("4 लाख लोग", source) == []


def test_norm_and_whole_word_contains():
    assert hindi.norm("ज़िंदगी") == hindi.norm("जिंदगी")
    assert hindi.norm("पाँच") == hindi.norm("पांच")
    assert hindi.contains("वे वाराणसी में पले", "वाराणसी")
    assert not hindi.contains("उनकी तलाश जारी है", "लाश")
    assert hindi.contains("Padma Shri award", "padma shri")


def test_devanagari_share_and_latin_words():
    assert hindi.devanagari_share("रमेश प्रसाद वर्मा") == 1.0
    assert hindi.devanagari_share("Ramesh Prasad Verma") == 0.0
    assert hindi.latin_words("NDRF की टीम और Air India") == ["NDRF", "Air", "India"]


def test_dates_in_hindi():
    assert hindi.date_hi(date(2026, 10, 10)) == "10 अक्टूबर 2026"
    assert hindi.date_hi(date(2026, 2, 1)) == "1 फ़रवरी 2026"


@pytest.mark.parametrize("hi, en", [("चेन्नई", "Chennai"), ("मुंबई", "Mumbai"), ("रमेश प्रसाद वर्मा", "Ramesh Prasad Verma"),
                                    ("पद्म श्री", "Padma Shri"), ("शाहरुख़ ख़ान", "Shah Rukh Khan")])
def test_transliterations_sound_alike(hi, en):
    assert hindi.sounds_alike(hi, en)


@pytest.mark.parametrize("hi, en", [("दिल्ली", "Kolkata"), ("लता मंगेशकर", "Asha Bhosle")])
def test_different_names_do_not(hi, en):
    assert not hindi.sounds_alike(hi, en)
