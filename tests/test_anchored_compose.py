"""Pictures change on the word that names them (SYNC-AUDIT 4.1 step 6): the Rubio Short (39714003987) cut to the
Vantara map at the middle of a line about crude oil and held a blurred face behind "दो घायल"; now a beat cuts only on
its cut_word, stays on its picture (closer) otherwise, and a card about harm sits on the plain channel background."""
import numpy as np

from desk import compose, match
from desk.spec import Beat

B4 = "रुबियो ने क्लीन एनर्जी गीगा-फैक्ट्री और वनतारा पशु केंद्र का भी दौरा किया।"
# Beat 4's timed words as voiced (/tmp/mn-sync/audit0/39714003987 timing.json; beat spans 17.66-23.52).
WORDS = [(w, s, e) for w, s, e in zip(B4.split(), (17.74, 18.34, 18.52, 18.88, 19.28, 20.08, 20.6, 21.18, 21.433,
                                                     21.94, 22.12, 22.3, 22.6),
                                      (18.254, 18.52, 18.88, 19.28, 20.08, 20.6, 21.18, 21.433, 21.94, 22.12, 22.3,
                                       22.6, 23.6))]


def words(spell=None):
    return [{"text": spell if spell and w == "वनतारा" else w, "start": s, "end": e, "beat": 3} for w, s, e in WORDS]


def shot(cut_word="वनतारा", views=(4, 11), plate="", text=B4):
    return {"photo": views[0], "views": list(views), "start": 17.66, "end": 23.52, "motion": compose.MOTIONS[0],
            "beat": Beat(text, "photo:" + "/".join(map(str, views)), plate=plate, cut_word=cut_word), "outro": False,
            "plate": plate, "cut_word": cut_word, "card_view": 1}


PAD = [{"photo": 7, "views": [7], "start": 0.35 + 6 * j, "end": 6.0 + 6 * j, "motion": compose.MOTIONS[0],
        "beat": Beat("x", "photo:7"), "outro": False, "plate": match.CARD} for j in range(3)]


def beat4(sh, w):
    """Beat 4 alone, after three beats of the Short (views reads beat k's words by their beat)."""
    return [v for v in compose.views(PAD + [sh], w, anchored=True) if v["beat_k"] == 3]


def test_compose_cuts_on_named_word():
    seen = beat4(shot(), words())
    assert [(v["photo"], v["start"], v["end"], v["cut"]) for v in seen] == [(4, 17.66, 20.6, False),
                                                                           (11, 20.6, 23.52, True)]
    assert compose.card_starts(PAD + [shot()], seen) == {3: 20.6}  # its card waits for the Vantara map
    assert compose.view_record(seen)[1] == {"start": 20.6, "end": 23.52, "photo": 11, "beat_k": 3, "plate": ""}


def test_compose_cut_falls_back_to_where_the_text_says_it():
    # Whisper heard "वंतारा": the cut goes where the word sits in the line, mapped onto the beat's spoken time.
    at = compose.cut_time(shot(), words("वंतारा"), 3)
    assert at == 17.74 + (23.6 - 17.74) * B4.index("वनतारा") / len(B4)
    assert 20.0 < at < 21.2


def test_no_cut_without_second_anchor_is_tight():
    for sh in (shot(cut_word="", views=(4, 11)), shot(cut_word="वनतारा", views=(4,)),
               shot(cut_word="रुबियो", views=(4, 11))):  # "रुबियो" at 17.74 s: inside CUT_EDGE of the beat's start
        seen = beat4(sh, words())
        assert [v["photo"] for v in seen] == [4, 4] and seen[1]["motion"] == compose.TIGHT
    assert compose.card_starts(PAD + [shot()], beat4(shot(cut_word=""), words())) == {}  # no card over Rubio


def test_injury_card_plain_background():
    hurt = "फायरिंग की इस घटना में दो लोग घायल हुए हैं।"
    assert match.plain(hurt) and match.plain("आरोपियों से पूछताछ जारी है।") and match.plain("x", loss=True)
    assert not match.plain("रिलायंस ने बताया कि बैठक में डेटा सेंटर और ऊर्जा आपूर्ति पर बात हुई।")
    seen = beat4(shot(plate=match.CARD, text=hurt), words())
    assert len(seen) == 1 and seen[0]["plate"] == match.CARD  # a card never cuts
    plain = compose.card_backdrop(None)
    assert plain.shape == (compose.H, compose.W, 3) and (plain[:, 0] == plain[:, -1]).all()  # no picture in it
    face = np.zeros((compose.H, compose.W, 3), np.uint8)
    face[:, : compose.W // 2] = 250
    blur = compose.card_backdrop(face)
    assert blur[compose.H // 2, 10].mean() > blur[compose.H // 2, -10].mean() and blur.max() < 140  # dark, still it


def test_place_stamp_only_on_its_place():
    photos = [{"role": None}, {"role": "map", "who": "जामनगर"}, {"role": "map", "who": "वनतारा, जामनगर"},
              {"role": "place", "who": "वनतारा"}]
    seen = [{"photo": 0, "start": 0.0, "end": 3.0, "beat_k": 0}, {"photo": 1, "start": 3.0, "end": 6.0, "beat_k": 0},
            {"photo": 1, "start": 6.0, "end": 9.0, "beat_k": 1, "plate": match.CARD},
            {"photo": 2, "start": 9.0, "end": 11.0, "beat_k": 2}, {"photo": 3, "start": 11.0, "end": 12.0, "beat_k": 2},
            {"photo": 0, "start": 12.0, "end": 15.0, "beat_k": 3}, {"photo": 1, "start": 15.0, "end": 16.0,
                                                                     "beat_k": 4, "outro": True}]
    # Never over Rubio, never over a card's backdrop, never past its map; Vantara's map says Vantara, not Jamnagar.
    assert compose.places_on(seen, photos) == [(3.0, 6.0, "जामनगर"), (9.0, 11.0, "वनतारा, जामनगर"),
                                               (11.0, 12.0, "वनतारा")]


def test_early_second_name_still_cuts():
    # Dry run 39837265455 beat 1: "डोनाल्ड तुस्क और नरेंद्र मोदी ने ...", Modi said 1.18 s in; it used to hold Tusk.
    say = "डोनाल्ड तुस्क और नरेंद्र मोदी ने नई दिल्ली में रक्षा सहयोग बढ़ाने पर चर्चा की।"
    times = (0.297, 0.669, 1.025, 1.178, 1.534, 1.822, 1.941, 2.144, 2.415, 2.551, 2.839, 3.144, 3.466, 3.585)
    w = [{"text": t, "start": s, "end": s + 0.2, "beat": 0} for t, s in zip(say.split(), times)]
    sh = {"photo": 0, "views": [0, 8], "start": 0.0, "end": 9.98, "motion": compose.MOTIONS[0], "outro": False,
          "beat": Beat(say, "photo:0/8", cut_word="नरेंद्र", cut_at=say.index("नरेंद्र")), "plate": "",
          "cut_word": "नरेंद्र", "cut_at": say.index("नरेंद्र"), "card_view": 0}
    assert compose.cut_time(sh, w, 0) == compose.CUT_EDGE
    seen = compose.views([sh], w, anchored=True)
    assert [(v["photo"], v["cut"]) for v in seen] == [(0, False), (8, True)]
