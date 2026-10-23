"""Real pictures, review round 1 (2026-10-23): the viewer verdicts on the real-pictures branch's dry runs. A card over
the wrong face (Rahul Gandhi behind "गृह मंत्री ने यमुना ..."), the subject barely on screen, a summit stage opening
the Short, "दोनों" mid-line, one portrait as two files, faceless subjects the natural title let through, lexicon
matches abroad and in compounds, ceiling refusals that cost a script each, live network in tests, and the legacy
rollback still taking lexicon things. Offline throughout."""
from dataclasses import replace

import numpy as np
import pytest
import requests

from desk import cli, config, gate, match, things, visuals, wiki, writer

from .conftest import Offline
from .test_match import applied, planned, short
from .test_real_pictures import CAP, CAST_FOR, FLAG, spoken

SHAH = "39794659993"  # dry run: "अमित शाह ने नई दिल्ली में राहुल गांधी पर तीखा हमला बोला है" (Amit Shah, Rahul Gandhi)
TUSK = "39833792083"  # dry run: Donald Tusk and Narendra Modi in New Delhi


def hits(say: str, india: bool = True) -> list[str]:
    return [h["en"] for h in things.lexicon_hits([{"say": say}], india)]


# --- F1, F2: the subject's title and pronoun name them; a card's backdrop is of what it says ---------------------------

def test_the_home_ministers_title_and_his_claim_show_amit_shah():
    s = short(SHAH)
    rows, photos = planned(s)
    shah = {i for i, p in enumerate(photos) if not p.get("role")}
    # "गृह मंत्री ने यमुना सफाई ..." (once a card over Rahul Gandhi's blurred face): Shah's own photo.
    assert rows[1]["plate"] == "" and set(rows[1]["views"]) <= shah
    # "उन्होंने दावा किया कि राहुल गांधी की पार्टी ...": Shah who claims, once then Rahul on his name. One picture, one
    # beat (Matlabnama audit R4, 2026-10-23): Rahul's two photos are beats 1's and 3's, so beat 4 is a card and beat 5
    # Shah alone (a card beat's name still tells plan.speaker who is claimed about).
    # With one return (match.RETURNS, 2026-10-23) beat 4 shows Rahul's beat-1 photo again instead of a card, and
    # beat 5 opens on Shah.
    assert rows[3]["plate"] == ""
    assert rows[4]["plate"] == "" and set(rows[4]["views"][:1]) <= shah
    assert match.problems(applied(s, rows)) == []


def test_a_card_over_someone_the_line_does_not_name_is_drawn_plain():
    s = short(SHAH)
    rahul = next(i for i, p in enumerate(s.scene["photos"]) if p.get("who") == "राहुल गांधी")
    shah = 1
    beats = list(s.beats)
    beats[1] = replace(beats[1], plate=match.CARD, shot=f"photo:{rahul}")
    assert match.card_plain(replace(s, beats=beats), 1)  # "गृह मंत्री ने यमुना ..." over Rahul: plain
    beats[1] = replace(beats[1], shot=f"photo:{shah}")
    assert not match.card_plain(replace(s, beats=beats), 1)  # over Shah, whom the line names: his blur
    beats[3] = replace(beats[3], plate=match.CARD, shot=f"photo:{shah}")  # names Rahul and the party, not Shah
    assert match.card_plain(replace(s, beats=beats), 3)


def test_plan_puts_a_card_over_what_its_line_names():
    beats = [{"say": "अमित शाह दिल्ली पहुंचे।", "card": {"big": "दिल्ली"}},
             {"say": "राहुल गांधी ने विरोध किया।", "card": {"big": "विरोध"}},
             {"say": "गृह मंत्री ने यमुना पर बात की।", "card": {"big": "यमुना सफाई"}}]
    photos = [{"file": "File:Amit Shah.jpg"}, {"file": "File:Rahul.jpg", "role": "person", "who": "राहुल गांधी"},
              {"file": "File:Amit Shah 2.jpg"}]
    cast = [{"hi": "राहुल गांधी", "en": "Rahul Gandhi", "kind": "person", "photos": [1]}]
    for i, p in enumerate(photos):
        p["depicts"] = sorted(match.depicts(i, p, cast)) if p.get("role") else [match.SUBJECT]
    rows = match.plan(beats, photos, cast, [0, 2], "", ["अमित शाह", "अमित", "शाह", "गृह मंत्री"], True)
    # The title names Shah: his photo, not Rahul's (the beat before); his second one, the first being beat 0's (R4,
    # 2026-10-23: one picture, one beat).
    assert rows[2]["views"] == [2]


def test_the_subject_floor_refuses_a_short_its_person_is_barely_in():
    s = short(TUSK)
    rows, _ = planned(s)
    assert "pictures: the story's person fills only 20% of the Short (want at least 25%)" in match.problems(
        applied(s, rows))
    assert match.SUBJECT_SHARE <= match.REAL_SHARE  # a floor under the real-photo floor, beside the ceilings


def test_the_writer_is_sent_back_when_its_person_is_named_too_rarely():
    beats = [{"say": "डोनाल्ड तुस्क दिल्ली पहुंचे।"}, {"say": "नरेंद्र मोदी ने स्वागत किया।"},
             {"say": "नरेंद्र मोदी ने कहा कि साझेदारी बढ़ेगी।"}, {"say": "दोनों देशों ने व्यापार पर बात की।"},
             {"say": "नरेंद्र मोदी ने न्योता दिया।"}, {"say": "नरेंद्र मोदी ने धन्यवाद कहा।"}]
    assert "only 1 of 6 beats name them" in writer._unnamed_subject(beats, "डोनाल्ड तुस्क")[0]
    beats[2] = {"say": "तुस्क ने कहा कि साझेदारी बढ़ेगी।"}
    assert writer._unnamed_subject(beats, "डोनाल्ड तुस्क") == []


# --- F3: a summit stage or another venue never opens the Short while cleaner portraits remain ------------------------

def test_a_summit_photo_is_vetted_out_while_portraits_remain():
    s = short(TUSK)
    photos, cast = s.scene["photos"], match.cast_of(s)
    whys = {p.get("file") or "": match.vet(i, photos, s, cast) for i, p in enumerate(photos)}

    def why(start):
        return next(w for f, w in whys.items() if f.startswith(start))

    assert why("File:Donald Tusk attended the 2024 NB8").startswith("a photo from somewhere else")
    assert why("File:Prime Minister Donald Tusk of Poland").startswith("a photo from somewhere else")  # Oval Office
    assert why("File:Donald Tusk 2025 (2).jpg") == ""
    rows, _ = planned(s)
    assert photos[rows[0]["views"][0]]["file"] == "File:Donald Tusk 2025 (2).jpg"


def test_soft_reasons_never_vet_out_a_persons_last_clean_photos():
    two = [{"file": "File:Donald Tusk at the NB8 summit.jpg"}, {"file": "File:Donald Tusk and Mark Carney.jpg"},
           {"file": "File:Donald Tusk 2025.jpg"}]
    whys = [match.vet_photo(i, two, [], 2026, True, False) for i in range(3)]
    assert whys == ["", "", ""]  # one clean portrait: the others stay (SOFT_FLOOR)
    more = two + [{"file": "File:Donald Tusk KPRM.jpg"}]
    whys = [match.vet_photo(i, more, [], 2026, True, False) for i in range(4)]
    assert whys[0].startswith("a photo from somewhere else") and whys[1].startswith("a photo with someone else")


def test_with_other_catches_commas_ampersands_and_known_people():
    pool = [{"file": f"File:{f}.jpg"} for f in ("Donald Tusk, Ursula von der Leyen", "Donald Tusk & Olaf Scholz",
                                                "Donald Tusk 2024", "Donald Tusk KPRM", "Donald Tusk speaks")]
    whys = [match.vet_photo(i, pool, [], 2026, True, False) for i in range(len(pool))]
    assert whys[0].startswith("a photo with someone else") and whys[1].startswith("a photo with someone else")
    assert whys[2:] == ["", "", ""]
    # "Name, Title" is one person: Modi's official portrait stays.
    modi = [{"file": "File:Shri Narendra Modi, Prime Minister of India (3x4 cropped).jpg"},
            {"file": "File:Narendra Modi 2024.jpg"}, {"file": "File:Narendra Modi 2023.jpg"}]
    assert [match.vet_photo(i, modi, [], 2026, True, False) for i in range(3)] == ["", "", ""]
    # A known person beside the subject (things.FIGURES) is hard: vetted even with one clean photo left.
    shah = [{"file": "File:Amit Shah with Narendra Modi.jpg"}, {"file": "File:Amit Shah 2024.jpg"},
            {"file": "File:Amit Shah.jpg"}]
    assert match.vet_photo(0, shah, [], 2026, True, False) == "a photo with someone else (Narendra Modi)"


# --- F4: "दोनों" anywhere shows the pair, cut on the word ----------------------------------------------------------

def test_both_mid_line_shows_the_pair_cut_on_both():
    photos = [{"file": "File:Tusk.jpg", "depicts": [match.SUBJECT]},
              {"file": "File:Modi.jpg", "role": "person", "who": "नरेंद्र मोदी"},
              {"file": "File:Modi 2.jpg", "role": "person", "who": "नरेंद्र मोदी"},
              {"file": "File:Tusk 2.jpg", "depicts": [match.SUBJECT]}]
    cast = [{"hi": "नरेंद्र मोदी", "en": "Narendra Modi", "kind": "person", "photos": [1, 2]}]
    for i, p in enumerate(photos):
        p.setdefault("depicts", sorted(match.depicts(i, p, cast)))
    say = "नरेंद्र मोदी ने कहा कि दोनों नेता रक्षा सहयोग बढ़ाएंगे।"
    beats = [{"say": "डोनाल्ड तुस्क और नरेंद्र मोदी दिल्ली में मिले।"}, {"say": say}]
    rows = match.plan(beats, photos, cast, [0, 3], "", ["डोनाल्ड तुस्क", "डोनाल्ड", "तुस्क"], True)
    assert [photos[i]["file"] for i in rows[1]["views"]][0].startswith("File:Modi")
    assert match.SUBJECT in photos[rows[1]["views"][1]]["depicts"] and rows[1]["cut_word"] == "दोनों"
    assert rows[1]["cut_at"] == say.index("दोनों")


def test_both_after_two_beats_of_one_leader_each_is_the_pair():
    # Dry run 39860680187: "तुस्क ... मिले।", "मोदी ने ... चर्चा की।", then "रिपोर्टों के मुताबिक, दोनों नेताओं ने ..."
    # was a card; the two leaders the last two beats showed are the pair.
    # One picture, one beat (Matlabnama audit R4, 2026-10-23): Modi's one picture (two files, one a crop of the other:
    # one look) is beat 1's, so the pair beat is a card now (two of six: still within a third). With a second Modi
    # picture it is the pair again.
    s = short("39860680187")
    rows, photos = planned(s)
    assert rows[2]["plate"] == match.CARD
    assert match.problems(applied(s, rows)) == []
    assert sum(r["plate"] == match.CARD for r in rows) == 2
    modi = next(i for i, p in enumerate(photos) if p.get("who") == "नरेंद्र मोदी")
    photos.append({k: v for k, v in photos[modi].items() if k != "look"} | {"file": "File:Narendra Modi 2019.jpg"})
    cast = [c | {"photos": [*c["photos"], len(photos) - 1]} if modi in (c.get("photos") or []) else c
            for c in match.cast_of(s)]
    beats = [{"say": b.text, "card": b.card} for b in s.beats if b.shot != "outro"]
    subject = [i for i, p in enumerate(photos) if not p.get("role")]
    rows = match.plan(beats, photos, cast, subject, s.kind, match.spellings_of(s), match._person(s), s.scene["names"])
    assert rows[2]["plate"] == "" and len(rows[2]["views"]) == 2
    assert not photos[rows[2]["views"][0]].get("role") and photos[rows[2]["views"][1]].get("who") == "नरेंद्र मोदी"


# --- F5: one picture as two files counts as one --------------------------------------------------------------------

def test_a_crop_of_a_portrait_is_one_picture(tmp_path):
    import cv2

    rng = np.random.default_rng(7)
    base = cv2.GaussianBlur((rng.random((600, 480)) * 255).astype(np.uint8), (5, 5), 0)
    base = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    other = cv2.cvtColor(cv2.GaussianBlur((rng.random((600, 480)) * 255).astype(np.uint8), (5, 5), 0),
                         cv2.COLOR_GRAY2BGR)
    for name, img in (("a", base), ("b", base[60:540, 40:440]), ("c", other)):
        cv2.imwrite(str(tmp_path / f"{name}.jpg"), img)
    photos = [{"file": f"File:{n}.jpg", "path": str(tmp_path / f"{n}.jpg")} for n in "abc"]
    visuals.looks(photos)
    assert photos[0]["look"] == photos[1]["look"] == "File:a.jpg" and "look" not in photos[2]
    assert match.held_key(0, photos, {}) == match.held_key(1, photos, {}) != match.held_key(2, photos, {})


def test_plan_rotates_past_a_look_on_screen_in_the_last_beat():
    photos = [{"file": "File:a.jpg", "look": "File:a.jpg", "depicts": [match.SUBJECT]},
              {"file": "File:b.jpg", "look": "File:a.jpg", "depicts": [match.SUBJECT]},
              {"file": "File:c.jpg", "depicts": [match.SUBJECT]}]
    beats = [{"say": "मोदी दिल्ली में थे।"}, {"say": "मोदी ने भाषण दिया।"}, {"say": "मोदी ने धन्यवाद कहा।"}]
    rows = match.plan(beats, photos, [], [0, 1, 2], "", ["नरेंद्र मोदी", "मोदी"], True)
    assert [r["views"] for r in rows][:2] == [[0], [2]]  # never photo 1 (photo 0 cropped) right after photo 0


# --- F7, F19: a faceless person the title, hook or two beats name ---------------------------------------------------

def bypass():
    """The reviewer's natural-title variant of CAPraPdXvns: no kinship word before Raihan's name in the title."""
    s = short(CAP)
    new = {3: "बीकानेर हाउस के मुताबिक नो आइडिया इज फाइनल शो कुछ तस्वीरों के साथ जारी रहेगा।",
           4: "प्रियंका वाड्रा के बेटे ने कहा कि वे हटाई गई तस्वीरों के लिए नया वेन्यू तलाशेंगे।"}
    s = replace(s, title="रेहान वाड्रा की प्रदर्शनी से तस्वीरें हटाई गईं",
                beats=[replace(b, text=new.get(k, b.text)) for k, b in enumerate(s.beats)])
    photos = [dict(p) for p in s.scene["photos"]]
    for i in (0, 1):
        photos[i]["depicts"] = [match.SUBJECT]
    for i, p in enumerate(photos):
        p.setdefault("depicts", sorted(match.depicts(i, p, match.cast_of(s))))
    return s, photos


def test_the_natural_title_about_raihan_is_refused():
    s, photos = bypass()
    cast = match.cast_of(s)
    lines = [b.text for b in s.beats if b.shot != "outro"]
    why = writer.faceless(s.title, photos, cast, s.scene["name_hi"], True, s.scene["names"], "", lines)
    assert why and why.startswith(writer.FACELESS) and "रेहान" in why
    assert not cli.retryable(why)
    a = replace(s, scene=s.scene | {"photos": photos, "cast": cast})
    assert any(p.startswith(writer.FACELESS) for p in gate.richness(a))
    # A show's name and a building are no face ("नो आइडिया इज फाइनल", "बीकानेर हाउस").
    assert not writer._face_like({"en": "No Idea Is Final", "hi": "नो आइडिया इज फाइनल"})
    assert not writer._face_like({"en": "Bikaner House", "hi": "बीकानेर हाउस"})
    assert writer._face_like({"en": "Raihan Vadra", "hi": "रेहान वाड्रा"})


def test_a_two_word_name_two_beats_name_is_owed_a_face_without_a_kinship_word():
    photos = [{"file": "File:P.jpg", "depicts": [match.SUBJECT]}]
    names = [{"hi": "रेहान वाड्रा", "en": "Raihan Vadra"}]
    lines = ["रेहान वाड्रा ने प्रदर्शनी लगाई।", "रेहान वाड्रा ने कहा कि वे नया वेन्यू खोजेंगे।", "प्रियंका ने बात की।"]
    why = writer.faceless("प्रदर्शनी से तस्वीरें हटीं", photos, [], "प्रियंका वाड्रा", True, names, "", lines)
    assert why and "रेहान वाड्रा" in why
    assert writer.faceless("प्रदर्शनी से तस्वीरें हटीं", photos, [], "प्रियंका वाड्रा", True, names, "",
                           lines[:1] + lines[2:]) is None  # one beat: a mention
    # The hook counts like the title.
    assert writer.faceless("प्रदर्शनी", photos, [], "प्रियंका वाड्रा", True, names, "रेहान वाड्रा: नया वेन्यू", [])


def test_a_thing_the_title_names_with_no_photo_is_refused():
    photos = [{"file": "File:P.jpg", "depicts": [match.SUBJECT]}]
    cast = [{"hi": "तिरंगा", "en": "Flag of India", "kind": "thing", "alias": list(FLAG["forms"][1:]), "photos": []}]
    why = writer.faceless("तिरंगे की तस्वीरें हटीं", photos, cast, "प्रियंका वाड्रा", True, [], "", [])
    assert why and why.startswith(writer.FACELESS) and "तिरंगा" in why


def test_kin_is_someone_else_outside_harm_lines_too():
    cast = [{"hi": "प्रियंका वाड्रा", "en": "Priyanka Vadra", "kind": "person", "photos": [1]}]
    say = "प्रियंका वाड्रा के बेटे ने कहा कि वे नया वेन्यू तलाशेंगे।"
    assert match.names(say, cast) == []
    assert match.names("टाइगर जैकी श्रॉफ के बेटे हैं।", [{"hi": "जैकी श्रॉफ", "kind": "person", "photos": [1]}])


# --- F18: a failed download is retried, not skipped for good ------------------------------------------------------

def test_a_cast_person_whose_photo_failed_to_download_is_retried():
    photos = [{"file": "File:P.jpg", "depicts": [match.SUBJECT]}]
    cast = [{"hi": "रेहान वाड्रा", "en": "Raihan Vadra", "kind": "person", "photos": [], "miss": True}]
    why = writer.faceless("रेहान वाड्रा की प्रदर्शनी", photos, cast, "प्रियंका वाड्रा", True, [], "", [])
    assert why.startswith("usable photos") and cli.retryable(why)
    del cast[0]["miss"]
    why = writer.faceless("रेहान वाड्रा की प्रदर्शनी", photos, cast, "प्रियंका वाड्रा", True, [], "", [])
    assert why.startswith(writer.FACELESS) and not cli.retryable(why)


def test_a_person_with_a_wikidata_photo_and_no_download_is_a_miss(monkeypatch):
    monkeypatch.setattr(writer, "_own_photos", lambda *a, **k: [])
    c = {"hi": "रेहान", "title": "Raihan", "ent": {"claims": {"P18": [{"mainsnak": {"datavalue": {
        "value": "Raihan Vadra.jpg"}}}]}}}
    assert visuals._person_photos(c, __import__("pathlib").Path("/nonexistent"), set()) == [] and c["miss"]
    c = {"hi": "रेहान", "title": "Raihan", "ent": {"claims": {}}}
    visuals._person_photos(c, __import__("pathlib").Path("/nonexistent"), set())
    assert not c["miss"]


# --- F8, F9, F14: the lexicon abroad and in compounds ---------------------------------------------------------------

@pytest.mark.parametrize("say", [
    "पोलैंड का राष्ट्रीय ध्वज फहराया गया।", "इजरायल की संसद ने कानून पास किया।", "यूरोपीय संसद में बहस हुई।",
    "इटली की संसद ने मंजूरी दी।", "यूक्रेनी संसद ने प्रस्ताव पास किया।", "दक्षिण कोरिया का सुप्रीम कोर्ट",
    "पोलिश राष्ट्रीय ध्वज लहराया।", "वंदे भारत मिशन के तहत लोग लौटे", "ताज महल पैलेस होटल में बैठक हुई।",
    "यह परियोजना सफेद हाथी बन गई।", "बाघ बकरी चाय की कंपनी", "राम मंदिर नाम की एक दुकान"])
def test_no_lexicon_thing_abroad_or_in_a_compound(say):
    assert hits(say) == []


@pytest.mark.parametrize("say,en", [
    ("संसद में तिरंगा फहराया गया।", "Flag of India"), ("भारत की संसद ने बिल पास किया।", "Parliament House, New Delhi"),
    ("अयोध्या के राम मंदिर में पूजा हुई।", "Ram Mandir"), ("यमुना सफाई के लिए परियोजनाएं", "Yamuna"),
    ("स्वतंत्रता दिवस पर राष्ट्रीय ध्वज फहराया गया।", "Flag of India")])
def test_the_lexicon_still_finds_indias_own(say, en):
    assert en in hits(say)


def test_a_generic_flag_word_is_indias_only_in_an_india_story():
    assert hits("राष्ट्रीय ध्वज फहराया गया।", india=False) == []
    assert hits("राष्ट्रीय ध्वज फहराया गया।", india=True) == ["Flag of India"]


def test_the_yamuna_has_photos_of_its_own():
    yamuna = next(e for e in things.LEXICON if e["en"] == "Yamuna")
    assert yamuna["files"] and all(f.startswith("File:") for f in yamuna["files"])


# --- F12: thing_like is no airline, award statuette or bare "flag" ------------------------------------------------

def ent(desc):
    return {"descriptions": {"en": {"value": desc}}, "claims": {}}


@pytest.mark.parametrize("desc", ["flag carrier airline of India", "Indian airline", "award statuette",
                                  "Indian film award", "flag", "music award trophy"])
def test_thing_like_refuses_airlines_awards_and_bare_flags(desc):
    assert not things.thing_like(ent(desc))


@pytest.mark.parametrize("desc", ["national flag of India", "aircraft carrier of the Indian Navy",
                                  "highest civilian award of India"])
def test_thing_like_keeps_real_things(desc):
    assert things.thing_like(ent(desc))


# --- F10: a refusal after writing costs a writing slot; picture refusals are retried twice -------------------------

def test_picture_refusals_get_two_tries():
    assert cli.retry_limit("gate: pictures: beat 2 shows photo 3") == cli.PICTURE_TRIES == 2
    assert cli.retry_limit("gate: text cards: 3 of 6 beats (at most 2)") == 2
    assert cli.retry_limit("gate: only 2 usable photos of X") == 6


def test_a_refusal_after_writing_counts_toward_max_written(monkeypatch):
    calls = []

    def prepare(cand):
        calls.append(cand["id"])
        writer.DRAFTED[0] += 1  # the writer drafted a script, then a picture gate refused it
        raise ValueError("gate: pictures: beat 2 shows photo 3, which the beat does not name")

    cands = [{"id": f"s{n}", "kind": "", "title": "t"} for n in range(4)]
    monkeypatch.setattr(cli, "prepare", prepare)
    written = tried = 0
    for cand in cands:  # cli.run's own counting, as it reads writer.DRAFTED around prepare
        if written >= cli.MAX_WRITTEN:
            break
        drafted = writer.DRAFTED[0]
        try:
            cli.prepare(cand)
        except ValueError as exc:
            written += "no draft passed" in str(exc) or writer.DRAFTED[0] > drafted
        tried += 1
    assert calls == ["s0", "s1"]


def test_cli_run_counts_drafted_refusals():
    src = __import__("inspect").getsource(cli.run)
    assert "writer.DRAFTED[0] > drafted" in src and "limit=retry_limit" in src


# --- F15: no network in tests ---------------------------------------------------------------------------------------

def test_tests_never_reach_the_network():
    with pytest.raises(Offline):
        requests.get("https://en.wikipedia.org/wiki/Main_Page", timeout=1)
    with pytest.raises(Exception):
        wiki.search("Donald Tusk")


# --- F16: the legacy rollback takes no lexicon things ---------------------------------------------------------------

def test_legacy_keeps_the_red_fort_place_and_takes_no_lexicon_thing(monkeypatch):
    draft = {"names": [{"hi": "लाल किला", "en": "Red Fort"}],
             "beats": [{"say": "लाल किला सजाया गया और वहां तिरंगा फहराया गया।"}]}
    ent_ = {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": "Q57821"}}}]}}

    def resolver(en, india, **k):
        return ("Q45957", en, ent_) if en == "Red Fort" else None

    monkeypatch.setattr(visuals, "sub_place", lambda *a, **k: None)
    monkeypatch.setattr(config, "MATCHER", "legacy")
    cast = CAST_FOR(draft, "", True, resolver=resolver, thing_resolver=lambda en: pytest.fail("thing lookup"),
                    thing_lookup=lambda e: pytest.fail("lexicon lookup"))
    assert [(c["en"], c["kind"]) for c in cast] == [("Red Fort", "place")]
    monkeypatch.setattr(config, "MATCHER", "anchored")
    cast = CAST_FOR(draft, "", True, resolver=resolver, thing_resolver=lambda en: None, thing_lookup=lambda e: None)
    assert ("Flag of India", "thing") in [(c["en"], c["kind"]) for c in cast]


def test_legacy_writes_no_faceless_refusal(monkeypatch):
    src = __import__("inspect").getsource(writer._short)
    assert 'config.MATCHER != "legacy" and (refused := faceless(' in src
    monkeypatch.setattr(config, "MATCHER", "legacy")
    s, photos = bypass()
    assert gate.richness(replace(s, scene=s.scene | {"photos": photos, "cast": match.cast_of(s)})) == []
