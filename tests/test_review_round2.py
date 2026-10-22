"""The 2026-10-22 review of the anchored matcher, round 2 (9 findings): each one pinned on its own beat."""
from dataclasses import replace
from types import SimpleNamespace

from desk import compose, config, gate, hindi, match, visuals, writer
from desk.spec import Beat, Short

from .test_match import short

MODI = [{"file": "File:Narendra Modi 2025.jpg", "description": "Narendra Modi in 2025", "origin": "wikidata",
         "focus": [1, 1, 300, 300], "depicts": [match.SUBJECT]},
        {"file": "File:Narendra Modi 2024.jpg", "description": "Narendra Modi at a rally, 2024", "origin": "wikidata",
         "focus": [1, 1, 300, 300], "depicts": [match.SUBJECT]}]


def made(kind, title, name_hi, beats, rows, photos, cast, names):
    return Short(id="kh-20261022-Q1", kind=kind, title=title, facts=[], sources=[], loss=False, event_time="2026-10-22",
                 beats=[Beat(b["say"], "photo:" + "/".join(map(str, r["views"])), b["card"], plate=r["plate"],
                             cut_word=r["cut_word"], cut_at=r["cut_at"], card_view=r["card_view"])
                        for b, r in zip(beats, rows)],
                 scene={"name_hi": name_hi, "subject_person": True, "photos": photos, "cast": cast, "names": names})


def test_the_hook_is_checked_against_its_picture():
    # Finding 1: "शिंदे: गोली का जवाब गोली से" came up over Tiger Shroff (39546660530), and "ड्राइवर और एक फैन को
    # लगी गोली" over his portrait (39553699482).
    assert "pictures: the hook quotes शिंदे over a picture of someone else" in match.opening(short("39546660530"))
    assert match.opening(short("39553699482")) == ["pictures: the hook says someone was hurt over the subject's photo"]
    assert "pictures: the hook says someone was hurt over the subject's photo" in match.problems(short("39553699482"))
    shinde = hindi.norm("एकनाथ शिंदे")
    others = [{"hi": "एकनाथ शिंदे", "en": "Eknath Shinde"}]
    spelt = ["टाइगर श्रॉफ", "टाइगर", "श्रॉफ"]
    assert match.hook_problems("शिंदे: सख्त कार्रवाई होगी", {shinde}, [], spelt, others) == []  # over Shinde
    assert match.hook_problems("टाइगर श्रॉफ को लगी चोट", {match.SUBJECT}, [], spelt, others) == []  # says it is him
    assert match.hook_problems("अभिनेता का निधन", {match.SUBJECT}, [], spelt, others, death=True) == []


def test_a_police_card_needs_the_police_on_screen():
    # Finding 2: "मुंबई पुलिस" / "राजस्थान पुलिस" as a card's big line over Tiger Shroff passed.
    s = short("39546660530")
    for big in ("मुंबई पुलिस", "राजस्थान पुलिस"):
        f = replace(s, beats=[replace(s.beats[0], card={"big": big, "small": ""}), *s.beats[1:]])
        assert "pictures: card 1 names @police over a picture of something else" in match.problems(f), big
    f = replace(s, beats=[replace(s.beats[0], card={"big": "बेगूसराय", "small": ""}), *s.beats[1:]])
    assert not [p for p in match.problems(f) if "card 1" in p]  # no picture name: a caption
    mumbai = hindi.norm("मुंबई")
    cast = [{"hi": "मुंबई", "en": "Mumbai", "kind": "place", "photos": [0]}, {"kind": "police", "hi": "मुंबई", "photos": []}]
    photos = [{"role": "map", "depicts": [mumbai], "description": "MAP: Mumbai"}, MODI[0]]
    assert match.POLICE in match.card_on([0], photos, cast)  # over its own city's map
    assert match.POLICE not in match.card_on([1], photos, cast)
    assert match.card_keys("मुंबई पुलिस", "", cast) == {match.POLICE}
    assert match.card_keys("राजस्थान पुलिस", "", cast) == {match.OTHER_POLICE}  # never on screen
    assert match.card_keys("3 आरोपी गिरफ्तार", "", cast) == set()  # no पुलिस: not the police
    assert match.card_keys("गिरफ्तारी", "मुंबई पुलिस", cast) == {match.POLICE}  # a small line that is only a name


def test_a_shared_first_name_is_not_the_subject():
    # Finding 3: "अमित मालवीय" was exempt from others_of in an Amit Shah Short, so his beat showed Amit Shah.
    names = [{"hi": "अमित शाह", "en": "Amit Shah"}, {"hi": "अमित मालवीय", "en": "Amit Malviya"},
             {"hi": "राहुल गांधी", "en": "Rahul Gandhi"}]
    spell = ["अमित शाह", "अमित", "शाह"]
    assert [o["hi"] for o in match.others_of(names, [], spell)] == ["अमित मालवीय", "राहुल गांधी"]
    say = "भाजपा नेता अमित मालवीय ने इस पर विपक्ष से सवाल पूछे।"
    assert [x for _, x in match.names(say, [], spell, names)] == ["अमित मालवीय"]
    beats = [{"say": "गृह मंत्री अमित शाह ने आज संसद में नया विधेयक पेश किया।", "card": {"big": "नया विधेयक", "small": ""}},
             {"say": say, "card": {"big": "अमित मालवीय", "small": "भाजपा आईटी सेल"}}]
    rows = match.plan(beats, MODI, [], [0, 1], "explainer", spell, True, names)
    assert [r["plate"] for r in rows] == ["", match.CARD]


def test_a_title_spelling_is_not_another_persons_title():
    # Finding 4: "प्रधानमंत्री" is one of Modi's spellings; "पाकिस्तान के प्रधानमंत्री शहबाज शरीफ" is Sharif alone.
    names = [{"hi": "नरेंद्र मोदी", "en": "Narendra Modi"}, {"hi": "शहबाज शरीफ", "en": "Shehbaz Sharif"},
             {"hi": "पाकिस्तान", "en": "Pakistan"}]
    sharif = {"file": "File:Shehbaz Sharif 2024.jpg", "description": "Shehbaz Sharif", "role": "person",
              "who": "शहबाज शरीफ", "focus": [1, 1, 300, 300], "depicts": ["शहबाज शरीफ"]}
    cast = [{"hi": "शहबाज शरीफ", "en": "Shehbaz Sharif", "kind": "person", "photos": [2]}]
    beats = [{"say": "प्रधानमंत्री नरेंद्र मोदी ने आज सिंधु जल समझौते पर बयान दिया।", "card": {"big": "मोदी का बयान", "small": ""}},
             {"say": "प्रधानमंत्री नरेंद्र मोदी ने कहा कि पानी और खून साथ नहीं बह सकते।", "card": {"big": "कड़ा संदेश", "small": ""}},
             {"say": "पाकिस्तान के प्रधानमंत्री शहबाज शरीफ ने इस फैसले को युद्ध जैसा कदम बताया।",
              "card": {"big": "पाकिस्तान का जवाब", "small": "प्रधानमंत्री"}}]
    probe = made("explainer", "मोदी का सिंधु जल पर बड़ा बयान", "नरेंद्र मोदी", beats, [{"views": [0], "plate": "",
                 "cut_word": "", "cut_at": -1, "card_view": 0}] * 3, MODI + [sharif], cast, names)
    spell = match.spellings_of(probe)
    assert "प्रधानमंत्री" in spell
    assert [x for _, x in match.names(beats[2]["say"], cast, spell, names)] == [hindi.norm("शहबाज शरीफ")]
    assert match.SUBJECT in {x for _, x in match.names("देश के प्रधानमंत्री ने कहा", cast, spell, names)}
    rows = match.plan(beats, MODI + [sharif], cast, [0, 1], "explainer", spell, True, names)
    assert rows[2]["views"] == [2] and rows[2]["plate"] == ""
    assert match.problems(replace(probe, beats=made("", "", "", beats, rows, [], [], []).beats)) == []


def test_a_chip_ends_at_its_cut():
    # Finding 5: "जुहू में फायरिंग" stayed 1.5 s over Tiger Shroff in Bandra after the cut (39508637683 replan).
    assert match.chip_window(4.0, 9.0) == (4.0, 4.0 + match.CHIP_HOLD)
    assert match.chip_window(4.0, 5.5) == (4.0, 5.5) and match.chip_window(4.0, 4.5) is None
    beat = Beat("x", "photo:1/2", {"big": "जुहू में फायरिंग", "small": ""})
    shots = [{"views": [0], "photo": 0, "card_view": 0, "plate": "", "outro": False, "beat": replace(beat, card={})},
             {"views": [1, 2], "photo": 1, "card_view": 0, "plate": "", "outro": False, "beat": beat},
             {"views": [3], "photo": 3, "card_view": 0, "plate": "", "outro": False,
              "beat": replace(beat, card={"big": "मुंबई", "small": ""})}]
    seen = [{"beat_k": 0, "photo": 0, "start": 0.0, "end": 4.0}, {"beat_k": 1, "photo": 1, "start": 4.0, "end": 5.5},
            {"beat_k": 1, "photo": 2, "start": 5.5, "end": 9.0}, {"beat_k": 2, "photo": 3, "start": 9.0, "end": 9.5}]
    assert compose.chip_spans(shots, seen) == {0: (0.0, 3.0), 1: (4.0, 5.5)}  # beat 3's view is under CHIP_MIN: no chip
    hook, chips = compose.chip_plan(SimpleNamespace(scene={"hook": ""}), shots, seen)
    assert chips == {1: (4.0, 5.5)} and hook == "" and seen[1]["chip"] == (4.0, 5.5) and "chip" not in seen[2]
    photos = [{"file": f"File:{i}.jpg"} for i in range(4)]
    assert match._chip_overrun(2, 1, 1, seen, photos, False) == []  # stamped: up only over its own picture
    old = [{k: v for k, v in s.items() if k != "chip"} for s in seen]  # a render saved before chips were stamped
    assert match._chip_overrun(2, 1, 1, old, photos, False) == ["pictures: card 2 stays up over photo 2 (File:2.jpg) "
                                                                "after the cut"]


def test_a_death_draft_naming_nothing_is_sent_back(monkeypatch):
    # Finding 6: a death Short's pronoun beats are cards, and nothing but the subject was showable: never rewritten.
    monkeypatch.setattr(visuals, "showable", lambda *a, **k: [])
    draft = {"beats": [{"say": "दिग्गज अभिनेता धर्मेंद्र का निधन हो गया।"}, {"say": "उन्होंने 300 से ज्यादा फिल्मों में काम किया।"},
                       {"say": "उनकी फिल्म शोले आज भी याद की जाती है।"}, {"say": "उनके परिवार ने यह जानकारी दी।"}]}
    subject = {"en": "Dharmendra", "hi": "धर्मेंद्र", "person": True}
    assert writer.anchorless(draft, subject, True, kind="death") == [
        "beats 2,3,4 name nothing that can be shown; SHOWABLE: धर्मेंद्र. Name in each beat the person, place or police "
        "it is about (one of SHOWABLE where the SOURCES allow)."]
    assert writer.anchorless(draft, subject, True, kind="explainer") == []  # the pronoun rule shows him there
    named = {"beats": [{"say": b["say"].replace("उन्होंने", "धर्मेंद्र ने").replace("उनकी", "धर्मेंद्र की")
                        .replace("उनके", "धर्मेंद्र के")} for b in draft["beats"]]}
    assert writer.anchorless(named, subject, True, kind="death") == []


def test_the_legacy_matcher_is_held_as_main_held_it(monkeypatch):
    # Finding 7: DESK_MATCHER=legacy still grouped a spot's maps with its city's, so the rollback blocked Rubio.
    s = short("39714003987")
    assert "pictures: place:जामनगर stays on screen for 3 beats in a row" in gate.held(s)
    monkeypatch.setattr(config, "MATCHER", "legacy")
    assert gate.held(s) == []
    assert gate.held(short("39714003987-fixed")) == ["pictures: OpenStreetMap: जामनगर stays on screen for 3 beats in a row"]


def test_continuity_never_holds_the_subject_under_someone_named():
    # Finding 8: "उनके पिता जैकी श्रॉफ..." after a beat about Tiger, Jackie's photo vetted: Tiger stayed up.
    s = short("39508637683")
    photos, cast = [dict(p) for p in s.scene["photos"]], match.cast_of(s)
    photos[8]["vet"] = "a photo from another event (gala)"
    beats = [{"say": "टाइगर श्रॉफ रविवार को जुहू में अपनी कार से निकले।", "card": {"big": "", "small": ""}},
             {"say": "उनके पिता जैकी श्रॉफ भी उनके साथ थे।", "card": {"big": "", "small": ""}}]
    subject = [i for i, p in enumerate(photos) if not p.get("role")]
    rows = match.plan(beats, photos, cast, subject, s.kind, match.spellings_of(s), True, s.scene.get("names"))
    assert rows[1]["plate"] == match.CARD
    held = replace(s, beats=[replace(s.beats[0], text=beats[0]["say"], shot="photo:0"),
                             replace(s.beats[1], text=beats[1]["say"], shot="photo:1"), *s.beats[2:]])
    assert "pictures: beat 2 shows photo 1 (File:Tiger Shroff in Bandra.jpg), which the beat does not name" in \
        match.problems(held)


def test_police_beats_are_empty_without_a_police_picture(monkeypatch):
    # Finding 9: outside India SHOWABLE has no police, yet "पुलिस ने बताया" counted as a showable beat.
    monkeypatch.setattr(visuals, "showable", lambda *a, **k: ["पेरिस"])
    draft = {"beats": [{"say": "पेरिस में एक संग्रहालय में चोरी हुई।"}, {"say": "पुलिस ने बताया कि चोर खिड़की से घुसे।"},
                       {"say": "पुलिस ने दो लोगों को गिरफ्तार किया।"}, {"say": "आरोपियों से पूछताछ जारी है।"}]}
    subject = {"en": "Louvre heist", "hi": "लूव्र चोरी", "person": False}
    assert writer.anchorless(draft, subject, False, kind="incident")[0].startswith("beats 2,3,4 name nothing")
    monkeypatch.setattr(visuals, "showable", lambda *a, **k: ["पेरिस", "पुलिस"])
    assert writer.anchorless(draft, subject, False, kind="incident") == []  # beat 4 alone is a card
