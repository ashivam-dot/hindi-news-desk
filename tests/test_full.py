"""The full-screen Short (owner, 2026-10-21: "you are not able to present the video properly")."""
from desk import compose


PHOTOS = [{"role": "person", "who": "टाइगर श्रॉफ"}, {"role": "person", "who": "जैकी श्रॉफ"},
          {"role": "map", "who": "जुहू, मुंबई"}, {"role": "person", "who": "टाइगर श्रॉफ"},
          {"role": "police", "who": "मुंबई पुलिस"}]


def test_a_beat_naming_two_people_shows_them_side_by_side():
    shots = [{"views": [0, 1]}, {"views": [2]}, {"views": [0, 3]}, {"views": [4, 1]}]
    assert compose.splits(shots, PHOTOS) == {0: (0, 1)}


def test_a_name_strap_shows_once_when_a_person_first_appears():
    seen = [{"photo": 0, "start": 0.0}, {"photo": 2, "start": 3.0}, {"photo": 3, "start": 6.0},
            {"photo": 1, "start": 9.0}, {"photo": 4, "start": 12.0}, {"photo": 0, "start": 15.0}]
    assert compose.name_straps(seen, PHOTOS) == {0: 0.0, 3: 9.0, 4: 12.0}


def test_text_stays_above_youtubes_own_title_and_buttons():
    hook = compose._hookcard_layer("पिता जैकी श्रॉफ: 'टाइगर ठीक है'", size=84, width=compose.W - 200)
    chip = compose._fact_layer("तीनों आरोपी गिरफ्तार", "कोटा जंक्शन", "")
    bottom = 0.8 * compose.H
    assert compose.H * compose.FULL_HOOK_Y + hook[1].shape[0] / 2 < compose.H * compose.FULL_CAPTION_Y - 50
    assert compose.H * compose.FULL_CHIP_Y + chip[1].shape[0] < compose.H * compose.FULL_CAPTION_Y - 50
    assert compose.H * compose.FULL_CAPTION_Y + compose.FULL_CAPTION_SIZE < bottom
    assert compose.H * compose.FULL_CREDIT_Y + 40 < bottom + 40
    assert hook[1].shape[1] <= compose.W - 120 and chip[1].shape[1] <= compose.W - 72


def test_the_scrim_darkens_top_and_bottom_and_keeps_the_middle():
    s = compose.scrim()
    assert s.shape == (compose.H, 1, 1)
    assert s[0, 0, 0] < 0.6 and s[-1, 0, 0] < 0.4 and s[compose.H // 3, 0, 0] > 0.99


def test_the_writer_asks_for_the_full_screen_template_and_no_spoken_outro():
    from desk import writer

    assert not hasattr(writer, "OUTRO")
    assert writer.MAX_WORDS <= 90
