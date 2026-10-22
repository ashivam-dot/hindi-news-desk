"""The 2026-10-22 review of the anchored matcher (23 findings, SYNC-AUDIT 4.0/4.1): each one pinned on its own beat."""
import importlib
from dataclasses import replace
from pathlib import Path

import numpy as np

from desk import compose, config, gate, hindi, match, visuals, writer
from desk.spec import Beat

from .test_match import applied, planned, rehosted, short

TIGER_SPELT = ["टाइगर श्रॉफ", "टाइगर", "श्रॉफ"]
TIGER_NAMES = [{"hi": "टाइगर श्रॉफ", "en": "Tiger Shroff"}, {"hi": "जैकी श्रॉफ", "en": "Jackie Shroff"},
               {"hi": "संजय राउत", "en": "Sanjay Raut"}, {"hi": "पद्म श्री", "en": "Padma Shri"},
               {"hi": "मुंबई", "en": "Mumbai"}]


def test_a_name_outside_the_cast_masks_the_subjects_surname():
    # Finding 1: Jackie Shroff unresolved (no cast row): his "श्रॉफ" is not Tiger's, said once or twice.
    cast = [{"en": "Mumbai", "hi": "मुंबई", "kind": "place", "photos": [1]}]
    for say in ("जैकी श्रॉफ मुंबई में एक कार्यक्रम में पहुंचे।", "जैकी श्रॉफ ने कहा कि जैकी श्रॉफ का परिवार सुरक्षित है।"):
        keys = [x for _, x in match.names(say, cast, TIGER_SPELT, TIGER_NAMES)]
        assert match.SUBJECT not in keys and hindi.norm("जैकी श्रॉफ") in keys, say
    assert match.SUBJECT in {x for _, x in match.names("जैकी श्रॉफ ने टाइगर श्रॉफ से बात की।", cast, TIGER_SPELT,
                                                       TIGER_NAMES)}
    # One-word names and honours are never someone else's face: "भारत दौरा", "पद्म श्री सम्मान" stand.
    assert [o["hi"] for o in match.others_of(TIGER_NAMES, cast, TIGER_SPELT)] == ["जैकी श्रॉफ", "संजय राउत"]


def test_a_context_fill_is_never_the_subject():
    # Finding 2: writer.fill_photos' faceless school photo (origin "related", focus None) stood as the subject.
    jnu = {"file": "File:JNU admin block.jpg", "origin": "related", "focus": None}
    assert match.fill(jnu) and match.fill({"fill": True}) and match.fill({"origin": "openverse"})
    assert not match.fill({"origin": "story", "focus": [1, 2, 3, 4]}) and not match.fill({"origin": "article"})
    assert match.depicts(2, jnu) == {match.CONTEXT} and match.depicts(0, {"origin": "story"}) == {match.SUBJECT}
    photos = [{"origin": "story"}, {"origin": "wikidata"}, jnu]
    for p in photos:  # as visuals.direct stamps them
        p["depicts"] = [match.CONTEXT if match.fill(p) else match.SUBJECT]
    beats = [{"say": "विदेश मंत्री एस जयशंकर आज मुंबई पहुंचे।"}, {"say": "जयशंकर ने कहा कि भारत अडिग रहेगा।"},
             {"say": "जयशंकर ने व्यापार समझौते पर भी बात की।"}]
    rows = match.plan(beats, photos, [], [0, 1, 2], "explainer", ["एस जयशंकर", "जयशंकर"])
    assert all(2 not in r["views"] for r in rows)


def test_a_card_naming_someone_outside_the_cast_is_trimmed_and_flagged():
    # Finding 3: "संजय राउत" over Tiger Shroff, Raut unresolved (not in the cast).
    s = short("39508637683")
    photos = [dict(p) for p in s.scene["photos"]][:8]
    sc = s.scene | {"photos": photos, "cast": [], "names": TIGER_NAMES}
    card = {"big": "सुरक्षा में चूक", "small": "संजय राउत"}
    assert visuals.card_over(card, [1], [], photos, TIGER_SPELT, "", TIGER_NAMES) == {"big": "सुरक्षा में चूक",
                                                                                      "small": ""}
    assert visuals.card_over({"big": "संजय राउत का हमला", "small": ""}, [1], [], photos, TIGER_SPELT, "",
                             TIGER_NAMES) == {}
    beat = Beat("संजय राउत ने कहा कि टाइगर श्रॉफ की सुरक्षा में चूक हुई।", "photo:1", card)
    bad = match.problems(replace(s, beats=[beat], scene=sc))
    assert f"pictures: card 1 names {hindi.norm('संजय राउत')} over a picture of something else" in bad


def test_cards_do_not_dilute_the_map_share():
    # Findings 4, 12, 16: two maps under three picture beats is 67%, whatever three cards add.
    s = short("39714003987-fixed")
    shots = ["photo:7", "photo:8", "photo:8", "photo:11", "photo:11", "photo:4"]
    plates = ["", "", match.CARD, "", match.CARD, match.CARD]
    crafted = replace(s, beats=[replace(b, shot=sh, plate=pl, cut_word="") for b, sh, pl in zip(s.beats, shots, plates)])
    assert "pictures: maps fill 67% of the picture time (at most 20%)" in match.problems(crafted)
    from .tools import replay
    assert replay.map_share(crafted, None) == 2 / 3
    # plan() keeps under it: of the hand fix's two Jamnagar cuts it drops the one said again (beat 2), and a card's
    # backdrop is the last picture that is not a map.
    rows, _ = planned(short("39714003987"))
    assert rows[1]["views"] == [10] and all(not visuals.is_map(s.scene["photos"][r["views"][0]])
                                            for r in rows if r["plate"] == match.CARD)


def test_plan_keeps_the_held_ceiling():
    # Findings 5, 14: the chase Short's one police photo stood under 3 of 5 beats; gate.held refused the re-plan.
    s = short("39503061196")
    rows, _ = planned(s)
    assert sum(16 in r["views"] for r in rows if r["plate"] != match.CARD) * 2 <= len(rows)
    assert rows[4]["plate"] == match.CARD  # "मुंबई पुलिस क्राइम ब्रांच...": the photo is spent, a card
    assert gate.held(applied(s, rows)) == []
    groups = match.group(s.scene["photos"], match.cast_of(s))
    assert match.held_key(9, s.scene["photos"], groups) == match.held_key(10, s.scene["photos"], groups)  # Kota


def test_only_a_place_before_ki_ke_is_another_force():
    # Findings 6, 17: "साजिश की पुलिस जांच" (39333390694 b6) named no other force, and the beat lost its police photo.
    mumbai = {"hi": "मुंबई", "kind": "police"}
    for say in ("इस हमले के कारणों और साजिश की पुलिस लगातार जांच कर रही है।", "फायरिंग की पुलिस जांच कर रही है।",
                "आरोपी के पुलिस हिरासत में होने की खबर है।", "मामले की पुलिस जांच जारी है।", "उधर पुलिस ने बताया।",
                "उन्हें पुलिस ने पकड़ा।", "शहर की पुलिस अलर्ट पर है।", "स्थानीय पुलिस मौके पर पहुंची।",
                "मुंबई की पुलिस ने केस दर्ज किया।"):
        assert not visuals.other_force(say, mumbai), say
        assert match.POLICE in {x for _, x in match.names(say, [mumbai])}, say
    for say in ("राजस्थान की पुलिस ने इन्हें पकड़ा।", "राजस्थान पुलिस ने बताया।", "उत्तर प्रदेश की पुलिस ने बताया।"):
        assert visuals.other_force(say, mumbai), say
    assert visuals.other_force("जामनगर की पुलिस ने बताया।", mumbai, ["जामनगर"])
    assert not visuals.other_force("राजस्थान पुलिस ने बताया।", {"hi": "", "kind": "police"})  # no city: no other


def test_a_harm_line_about_the_subjects_driver_is_not_about_the_subject():
    # Finding 8: "टाइगर के ड्राइवर ... गोली लगी": the subject is the possessor, the harm chip is not over him.
    for say in ("टाइगर के ड्राइवर और एक फैन को गोली लगी।", "टाइगर श्रॉफ के बॉडीगार्ड को चोट आई।"):
        assert match.SUBJECT not in {x for _, x in match.names(say, [], TIGER_SPELT)}, say
    assert match.SUBJECT in {x for _, x in match.names("टाइगर के ड्राइवर ने गाड़ी रोकी।", [], TIGER_SPELT)}
    assert match.SUBJECT in {x for _, x in match.names("टाइगर श्रॉफ को चोट आई।", [], TIGER_SPELT)}


def test_a_cast_row_without_en_takes_the_scripts():
    # Finding 9: the saved cast had no 'en', so the Andheri flyover passed as Andheri (vet_photo's not_itself).
    s = short("39503061196")
    cast = match.cast_of(s)
    assert next(c for c in cast if c["hi"] == "अंधेरी")["en"] == "Andheri"
    assert match.vet(11, s.scene["photos"], s, cast) == "a landmark at Andheri, not Andheri itself"


def test_the_bulletin_draws_a_text_card():
    # Findings 10, 22: render_bulletin showed the backdrop photo itself under a line that names nothing on it.
    size = (compose.W, compose.WIN_H)
    photo = np.full((1500, 1080, 3), 200, np.uint8)
    win = compose.card_window(photo, {"big": "कच्चा तेल", "small": "चर्चा"}, size)
    bare = compose.card_window(photo, {}, size)
    assert win.shape == (compose.WIN_H, compose.W, 3) and bare.mean() < 120  # a dark blur, not the photo
    assert (win != bare).any() and win.max() == 255  # the words on it
    assert compose.card_window(None, {"big": "दो घायल"}, size).shape == bare.shape  # the plain background


def test_the_cut_comes_on_the_time_the_plan_cut_on():
    # Findings 11, 20: "...आरोपी अंधेरी स्टेशन पहुंचे और ... पैदल चलकर अंधेरी पश्चिम ..." cut to the Andheri map on
    # the station's अंधेरी.
    photos = [{}, {"role": "place", "who": "अंधेरी स्टेशन", "depicts": ["अंधेरी स्टेशन"]},
              {"role": "map", "who": "अंधेरी", "depicts": ["अंधेरी"]}]
    cast = [{"hi": "अंधेरी स्टेशन", "kind": "place", "photos": [1]}, {"hi": "अंधेरी", "kind": "place", "photos": [2]}]
    say = "वारदात के बाद दोनों आरोपी अंधेरी स्टेशन पहुंचे और वहां से पैदल चलकर अंधेरी पश्चिम की एक गली में छिप गए"
    row = match.plan([{"say": "टाइगर श्रॉफ पर हमला हुआ"}, {"say": say}], photos, cast, [0], spellings=TIGER_SPELT)[1]
    # The station's photo, and no cut to Andheri's map (a map is never a cut, 2026-10-22; once [1, 2] on the second
    # अंधेरी). compose's cut timing is pinned on the cut the old plan made.
    assert row["views"] == [1] and row["cut_word"] == ""
    row = {"cut_at": say.rindex("अंधेरी")}
    ws = say.split()
    words = [{"text": w, "start": 10 + 0.4 * i, "end": 10.35 + 0.4 * i, "beat": 1} for i, w in enumerate(ws)]
    second = 10 + 0.4 * ws.index("पश्चिम") - 0.4
    shot = {"cut_word": "अंधेरी", "start": 10.0, "end": 10 + 0.4 * len(ws), "beat": Beat(say, "photo:1/2", None,
                                                                                      cut_word="अंधेरी",
                                                                                      cut_at=row["cut_at"])}
    assert abs(compose.cut_time(shot, words, 1) - second) < 1e-9
    drift = [w | {"text": "अंधेरि"} if w["start"] == second else w for w in words]  # whisper misheard it
    assert compose.cut_time(shot, drift, 1) > 10 + 0.4 * ws.index("पैदल")
    assert compose.cut_time(shot | {"beat": Beat(say, "photo:1/2", None, cut_word="अंधेरी")}, words, 1) < second


def test_a_place_worded_text_card_is_not_a_place_card():
    # Finding 13: "रिफाइनरी परिसर" as a text card (match.CARD, kept as written) was flagged over the map backdrop.
    s = rehosted(short("39714003987-fixed"))
    beats = list(s.beats)
    beats[2] = replace(beats[2], card={"big": "रिफाइनरी परिसर", "small": "कार्यक्रम स्थल"})
    assert visuals.place_card(beats[2].card)
    # The Short is blocked on its maps now (2026-10-22), but never for card 3's wording.
    assert not any("card 3" in p for p in gate.said_is_shown(replace(s, beats=beats)))


def test_the_matcher_switch_is_normalised(monkeypatch):
    # Finding 15: run.yml passes vars.DESK_MATCHER, and " Legacy" from the UI still means the rollback.
    assert "DESK_MATCHER: ${{ vars.DESK_MATCHER }}" in (Path(__file__).parents[1] / ".github" / "workflows" /
                                                       "run.yml").read_text(encoding="utf-8")
    try:
        monkeypatch.setenv("DESK_MATCHER", " Legacy\n")
        assert importlib.reload(config).MATCHER == "legacy"
        monkeypatch.setenv("DESK_MATCHER", "")
        assert importlib.reload(config).MATCHER == "anchored"
    finally:
        monkeypatch.delenv("DESK_MATCHER", raising=False)
        importlib.reload(config)


def test_city_police_beats_are_anchored_before_the_city_is_known(monkeypatch):
    # Finding 18: anchorless built its police row with hi "", so "मुंबई पुलिस ने ..." named "another force".
    monkeypatch.setattr(visuals, "showable_rows", lambda *a, **k: [
        {"hi": "मुंबई", "kind": "place", "alias": [], "map_only": True},
        {"hi": "पुलिस", "kind": "police", "alias": [], "map_only": False}])
    draft = {"beats": [{"say": "टाइगर श्रॉफ के घर के बाहर फायरिंग हुई।"}, {"say": "मुंबई पुलिस ने मामला दर्ज किया।"},
                       {"say": "मुंबई पुलिस की टीम मौके पर पहुंची।"}, {"say": "मुंबई पुलिस आरोपियों को खोज रही है।"},
                       {"say": "मुंबई में सुरक्षा बढ़ा दी गई है।"}]}
    assert writer.anchorless(draft, {"en": "Tiger Shroff", "hi": "टाइगर श्रॉफ"}, True, kind="incident") == []


def test_a_photoless_first_name_never_puts_a_later_one_first():
    # Finding 19: Jaishankar (no photo), Mumbai, then Delhi: the main view is Mumbai's, Delhi cuts in on its word.
    # Their own photos (a landmark each): a map is never a cut and never under a beat naming a person (2026-10-22).
    photos = [{}, {"role": "place", "depicts": ["मुंबई"]}, {"role": "place", "depicts": ["दिल्ली"]}]
    cast = [{"hi": "जयशंकर", "kind": "person", "photos": []}, {"hi": "मुंबई", "kind": "place", "photos": [1]},
            {"hi": "दिल्ली", "kind": "place", "photos": [2]}]
    say = "जयशंकर ने मुंबई में बैठक के बाद दिल्ली लौटने की बात कही"
    beats = [{"say": "विदेश मंत्री ने बयान दिया", "card": {"big": "बयान"}}, {"say": say, "card": {"big": "दिल्ली वापसी"}}]
    row = match.plan(beats, photos, cast, [0])[1]
    assert row["views"] == [1, 2] and (row["cut_word"], row["cut_at"]) == ("दिल्ली", say.index("दिल्ली"))


def test_harm_and_unnamed_words_match_whole_words():
    # Finding 21: अमृतसर (मृत), व्यक्तिगत (व्यक्ति), चोटी (चोट) are not harm or an unnamed actor.
    for say in ("उन्होंने अमृतसर में स्वर्ण मंदिर में मत्था टेका।", "उन्होंने कहा कि यह व्यक्तिगत फैसला है।",
                "उन्होंने चोटी पर तिरंगा फहराया।"):
        assert match.says(say, match.HARM + match.UNNAMED) < 0, say
        assert match.continues(say, match.SUBJECT, False, 0, True), say
    for say in ("हमले में दो लोग मृत पाए गए।", "एक व्यक्ति ने जिम्मेदारी ली।", "ड्राइवर को चोटें आईं।", "वे घायल हुए।"):
        assert match.says(say, match.HARM + match.UNNAMED) >= 0, say
