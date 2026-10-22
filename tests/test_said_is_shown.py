"""What the voice says is what the screen shows. The Modi Dussehra Short (TAuiM3yuZKk, 2026-10-21) was told about
Delhi, so its title and three beats named Narendra Modi over a Jain temple, a dry-fruit market and a rickshaw; and
seven Tiger Shroff Shorts in a day opened on the same portraits."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from desk import explain, gate, ledger, news, visuals, wiki
from desk.spec import Beat

from . import test_gate
from .test_explain import BY_KEY, NOW

short = test_gate.short  # the fixture

cast_for = visuals.cast_for  # conftest stubs visuals.cast_for for every test


def item(key, title, hours_ago=1.0):
    o = BY_KEY[key]
    return {"title": title, "url": f"https://{key}.example/{abs(hash(title)) % 10**8}", "outlet": o["name"],
            "outlet_hi": o["name_hi"], "owner": o["owner"], "group": o["group"], "lang": o["lang"], "geo": o["geo"],
            "feed": key, "at": (NOW - timedelta(hours=hours_ago)).isoformat(), "summary": ""}


DUSSEHRA = [
    item("news18", "PM Modi To Attend Dussehra Celebrations In Delhi Today; Traffic Restrictions, Security "
                   "Arrangements In Place", 5),
    item("indiatoday", "Delhi's Dussehra celebrations to feature giant cockroach effigy. You read that right", 4),
    item("ht", "3-layer security deployed for Modi's expected presence at Delhi Dussehra celebrations", 3),
    item("thehindu", "PM Modi invokes Ram Rajya as good governance model at Delhi Dussehra celebrations", 1),
    item("ndtv", "PM Modi burns Ravan effigy at Delhi Dussehra celebrations", 2),
]


def claim(value):
    return {"mainsnak": {"datavalue": {"value": value}}}


def _stub(monkeypatch):
    india = [claim({"id": "Q668"})]
    items = {
        "Delhi": ("Q1353", {"labels": {"en": {"value": "Delhi"}, "hi": {"value": "दिल्ली"}},
                            "claims": {"P31": [claim({"id": "Q515"})], "P17": india,
                                       "P1082": [claim({"amount": "+16787941"})]}}),
        "Narendra Modi": ("Q1058", {"labels": {"en": {"value": "Narendra Modi"}, "hi": {"value": "नरेन्द्र मोदी"}},
                                    "claims": {"P31": [claim({"id": "Q5"})], "P27": india}}),
        "Dussehra": ("Q1047", {"labels": {"en": {"value": "Dussehra"}},
                               "descriptions": {"en": {"value": "Hindu festival"}}, "claims": {}}),
    }

    def search(q, lang="en"):
        return next((t for t in items if t.split()[-1].lower() in q.lower()), None)

    monkeypatch.setattr(wiki, "search", search)
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"title": t, "qid": items[t][0]} for t in titles
                                                           if t in items})
    by_qid = {q: e for q, e in items.values()}
    monkeypatch.setattr(wiki, "entities", lambda qids: {q: by_qid[q] for q in qids if q in by_qid})
    monkeypatch.setattr(news, "headlines", lambda feed, now=None: [])


def test_a_story_about_a_person_in_a_city_is_told_about_the_person(monkeypatch):
    _stub(monkeypatch)
    cands, notes = explain.find(DUSSEHRA, NOW)
    assert cands, notes
    assert cands[0]["qid"] == "Q1058" and cands[0]["person"]


def test_a_city_alone_is_still_the_centre(monkeypatch):
    _stub(monkeypatch)
    rows = [item("news18", "Delhi schools shut as air quality turns severe", 3),
            item("ht", "Delhi air quality turns severe, schools shut till Friday", 2),
            item("ndtv", "Schools in Delhi shut as air quality stays severe", 1)]
    cands, notes = explain.find(rows, NOW)
    assert cands and cands[0]["qid"] == "Q1353", notes


def test_a_place_story_keeps_the_people_it_names():
    # A story about a place passes no subject name: "" is inside every name and once dropped them all.
    assert not visuals._subject("Narendra Modi", "")
    assert visuals._subject("Tiger Shroff", "Tiger Shroff")


def test_cast_for_resolves_modi_when_the_story_is_about_delhi(monkeypatch):
    modi = {"claims": {"P31": [claim({"id": "Q5"})]}}
    monkeypatch.setattr(visuals, "resolve", lambda en, india: ("Q1058", en, modi) if en == "Narendra Modi" else None)
    draft = {"names": [{"en": "Narendra Modi", "hi": "नरेन्द्र मोदी"}, {"en": "Delhi", "hi": "दिल्ली"}],
             "beats": [{"say": "प्रधानमंत्री नरेन्द्र मोदी दिल्ली में दशहरा के कार्यक्रम में शामिल हुए।"}]}
    cast = cast_for(draft, "", True)
    assert [(c["en"], c["kind"]) for c in cast] == [("Narendra Modi", "person")]


def _modi_short(short, shots, cast, title="Narendra Modi: दिल्ली में दशहरा कार्यक्रम में शामिल हुए पीएम"):
    beats = [Beat("प्रधानमंत्री नरेन्द्र मोदी दिल्ली में दशहरा के कार्यक्रम में शामिल हुए।", shots[0]),
             Beat("यह आयोजन आईपी एक्सटेंशन के उत्सव मैदान में हुआ।", shots[1]),
             Beat("मोदी ने राम राज्य को सुशासन का मॉडल बताया।", shots[2])]
    return replace(short, title=title, beats=beats, scene=short.scene | {"cast": cast})


def test_the_title_person_must_be_on_screen(short):  # noqa: F811
    nobody = [{"en": "Narendra Modi", "hi": "नरेन्द्र मोदी", "kind": "person", "photos": []}]
    problems = gate.said_is_shown(_modi_short(short, ["photo:0", "photo:1", "photo:0"], nobody))
    assert any("title names Narendra Modi" in p for p in problems), problems


def test_a_beat_that_names_someone_shows_them(short):  # noqa: F811
    modi = [{"en": "Narendra Modi", "hi": "नरेन्द्र मोदी", "kind": "person", "photos": [2]}]
    wrong = gate.said_is_shown(_modi_short(short, ["photo:0/1", "photo:1", "photo:2"], modi))
    assert wrong == ["pictures: beat 1 names Narendra Modi but shows someone or something else"]
    assert gate.said_is_shown(_modi_short(short, ["photo:2/0", "photo:1", "photo:0/2"], modi)) == []


def test_a_surname_alone_still_shows_the_person():
    cast = [{"en": "Devendra Fadnavis", "hi": "देवेंद्र फडणवीस", "kind": "person", "photos": [3]},
            {"en": "Jackie Shroff", "hi": "जैकी श्रॉफ", "kind": "person", "photos": [4]},
            {"en": "Juhu", "hi": "जुहू", "kind": "place", "photos": [5], "near": []}]
    visuals.surnames(cast, "टाइगर श्रॉफ")
    assert cast[0]["alias"] == ["फडणवीस"] and "alias" not in cast[1]  # श्रॉफ is the story's own person too
    beats = [{"say": "टाइगर श्रॉफ पर फायरिंग हुई।", "photo": 0},
             {"say": "फडणवीस के मुताबिक हमले के मास्टरमाइंड राज्य के बाहर हैं।", "photo": 0},
             {"say": "रविवार को जुहू में फायरिंग के वक्त टाइगर के साथ सुरक्षाकर्मी थे।", "photo": 0},
             {"say": "फडणवीस ने कहा कि किसी भी दोषी को बख्शा नहीं जाएगा।", "photo": 0}]
    views = visuals.assign_legacy(beats, [0, 1], cast, first=0)
    assert views[1][0] == 3 and views[3][0] == 3 and views[2][0] == 5


KOTA = ["टाइगर श्रॉफ की कार पर फायरिंग हुई और वे सुरक्षित बचे।",
        "तीन संदिग्ध आरोपियों को राजस्थान के कोटा से गिरफ्तार किया गया।",
        "कोटा कोर्ट ने आरोपियों को मुम्बई पुलिस की रिमांड पर दिया।",
        "पुलिस के मुताबिक मामले में एक गैंग का लिंक जांचा जा रहा है।",
        "हमले के लिए इस्तेमाल मोटरसाइकिल पुलिस ने बरामद कर ली है।",
        "फायरिंग की इस घटना में दो लोग घायल हुए हैं।",
        "गिरफ्तार किए गए आरोपियों से मुम्बई में पूछताछ जारी है।"]


def test_one_place_never_fills_the_short(short):  # noqa: F811
    kota = {"file": "OpenStreetMap: कोटा", "role": "map", "license": "CC BY-SA 2.0", "page": "x"}
    photos = [{"file": "File:Tiger.jpg"}, {"file": "File:Tiger2.jpg"}, kota, dict(kota)]
    shots = ["photo:0/1", "photo:2/3", "photo:2", "photo:3", "photo:2", "photo:3", "photo:2"]
    bad = replace(short, beats=[Beat(t, s) for t, s in zip(KOTA, shots)],
                  scene=short.scene | {"photos": photos, "cast": []})
    problems = gate.held(bad)
    assert any("3 beats in a row" in p for p in problems) and any("under 6 of 7 beats" in p for p in problems)
    good = ["photo:0/1", "photo:2/3", "photo:2", "photo:1", "photo:3", "photo:0", "photo:1"]
    assert gate.held(replace(bad, beats=[Beat(t, s) for t, s in zip(KOTA, good)])) == []


def test_beats_about_nobody_leave_a_place_already_shown_twice():
    cast = [{"en": "Kota", "hi": "कोटा", "kind": "place", "photos": [2], "near": [3]},
            {"kind": "police", "hi": "मुंबई", "photos": [4]}]
    views = visuals.assign_legacy([{"say": t, "photo": 0} for t in KOTA], [0, 1], cast, first=0,
                           person=["Tiger Shroff", "टाइगर", "श्रॉफ"])
    run = 0
    for v in views:
        run = run + 1 if set(v) & {2, 3} else 0
        assert run < gate.HELD_RUN, views


def test_a_festival_is_pictured_as_itself_never_as_a_ground_named_after_it(monkeypatch):
    ramlila = {"descriptions": {"en": {"value": "multi-day drama-dance performance art festival based on the "
                                                 "Hindu Ramayana"}},
               "claims": {"P31": [claim({"id": "Q15116915"})], "P625": [claim({"latitude": 26.8, "longitude": 82.2})],
                          "P17": [claim({"id": "Q668"})]}}
    maidan = {"descriptions": {"en": {"value": "ground in New Delhi"}},
              "claims": {"P625": [claim({"latitude": 28.6, "longitude": 77.2})], "P17": [claim({"id": "Q668"})],
                         "P131": [claim({"id": "Q1353"})]}}
    assert visuals.topic_like(ramlila) and not visuals.topic_like(maidan)
    monkeypatch.setattr(visuals, "resolve", lambda en, india: ("Q167067", "Ramlila", ramlila))
    monkeypatch.setattr(visuals, "resolve_topic", lambda en: ("Q167067", "Ramlila", ramlila))
    draft = {"names": [{"en": "Ramlila", "hi": "राम लीला"}], "beats": [{"say": "राम लीला समिति ने आयोजन किया।"}]}
    found = cast_for(draft, "Narendra Modi", True)
    assert [c["kind"] for c in found] == ["topic"]
    assert cast_for(draft, "Narendra Modi", True, places_too=False) == []
    cast = [found[0] | {"photos": [4]}]
    views = visuals.assign_legacy([{"say": "x", "photo": 0}, {"say": "देश भर में राम लीलाओं का मंचन हुआ।", "photo": 0}],
                           [0, 1], cast, first=0)
    assert views[1][0] == 4


def test_government_of_india_photos_are_free_and_a_likeness_is_not_the_person():
    from desk import media

    assert media.FREE.match("GODL-India") and not media.FREE.match("CC BY-NC 4.0")
    photo = media.Photo("File:x.jpg", "u", "p", 1, 1, "Prime Minister's Office", "GODL-India", "", "", "search")
    assert media.GODL_URL in photo.credit
    assert media.NOT_PERSON.search("File:Narendra Modi figure at Madame Tussauds London (33783646132).jpg")
    assert not media.NOT_PERSON.search("File:The Prime Minister, Shri Narendra Modi addressing the gathering at "
                                       "the Dussehra celebrations at Madhav Das Park.jpg")


def test_the_storys_words_come_from_its_headlines():
    from desk import writer

    heads = ["PM Modi To Attend Dussehra Celebrations In Delhi Today",
             "3-layer security deployed for Modi's expected presence at Delhi Dussehra celebrations",
             "PM Modi invokes Ram Rajya as good governance model at Delhi Dussehra celebrations"]
    assert writer.story_words(heads, "Narendra Modi") == ["Dussehra"]


def test_a_beat_that_names_the_storys_person_opens_on_them():
    cast = [{"en": "Delhi", "hi": "दिल्ली", "kind": "place", "photos": [5], "near": []}]
    beats = [{"say": "प्रधानमंत्री नरेन्द्र मोदी दशहरा कार्यक्रम में शामिल हुए।", "photo": 0},
             {"say": "आयोजन दिल्ली में हुआ।", "photo": 0},
             {"say": "नरेन्द्र मोदी ने दिल्ली में राम राज्य का जिक्र किया।", "photo": 0}]
    views = visuals.assign_legacy(beats, [0, 1, 2], cast, first=0, person=["Narendra Modi", "नरेन्द्र", "मोदी"])
    assert views[2][0] in (1, 2) and 5 in views[2]


DUSSEHRA_BEATS = [{"say": "प्रधानमंत्री नरेन्द्र मोदी दिल्ली में दशहरा के कार्यक्रम में शामिल हुए।", "photo": 0},
                  {"say": "यह आयोजन दिल्ली के आईपी एक्सटेंशन में हुआ।", "photo": 0},
                  {"say": "स्थानीय राम लीला समिति ने इस कार्यक्रम का आयोजन किया था।", "photo": 0},
                  {"say": "प्रधानमंत्री नरेन्द्र मोदी ने दिल्ली में रावण दहन किया।", "photo": 0},
                  {"say": "कार्यक्रम में देश भर में राम लीलाओं के मंचन और दिल्ली की परंपरा की बात हुई।", "photo": 0},
                  {"say": "विजयदशमी पर प्रधानमंत्री ने सच्चाई की जीत की बात कही।", "photo": 0}]


def test_the_title_before_the_storys_person_names_them():
    assert visuals.titles(DUSSEHRA_BEATS, "नरेन्द्र मोदी") == ["प्रधानमंत्री"]
    assert visuals.titles(DUSSEHRA_BEATS[:1], "नरेन्द्र मोदी") == []
    assert visuals.titles([{"say": "इस पर नरेन्द्र मोदी बोले।"}, {"say": "इस पर नरेन्द्र मोदी चुप रहे।"}],
                          "नरेन्द्र मोदी") == []


def test_a_city_every_line_names_does_not_stand_under_every_beat():
    delhi = {"en": "Delhi", "hi": "दिल्ली", "kind": "place", "photos": [5], "near": [6]}
    ramlila = {"en": "Ramlila", "hi": "राम लीला", "kind": "topic", "photos": [7, 8], "alias": ["राम लीलाओं"]}
    person = ["Narendra Modi", "नरेन्द्र", "मोदी", *visuals.titles(DUSSEHRA_BEATS, "नरेन्द्र मोदी")]
    views = visuals.assign_legacy(DUSSEHRA_BEATS, [0, 1, 2], [delhi, ramlila], first=0, person=person)
    maps = [any(i in (5, 6) for i in v) for v in views]
    assert sum(maps) * 2 <= len(views) and "TTT" not in "".join("T" if m else "F" for m in maps)
    assert views[5][0] in (0, 1, 2) and views[3][0] in (0, 1, 2) and views[2][0] in (7, 8)


def test_a_place_card_sits_only_over_its_own_place():
    cast = [{"en": "Delhi", "hi": "दिल्ली", "kind": "place", "photos": [8, 9]}]
    venue = {"big": "उत्सव मैदान", "small": "कार्यक्रम स्थल"}
    assert visuals.card_over(venue, [9], cast) == {"big": "दिल्ली", "small": "कार्यक्रम स्थल"}
    assert visuals.card_over(venue, [0], cast) == {}
    assert visuals.card_over({"big": "दिल्ली", "small": "कार्यक्रम स्थल"}, [8], cast)["big"] == "दिल्ली"
    assert visuals.card_over({"big": "राम राज्य", "small": "सुशासन"}, [0], cast)["big"] == "राम राज्य"


def test_the_gate_fails_a_place_card_over_another_picture(short):
    short.scene["cast"] = [{"en": "Delhi", "hi": "दिल्ली", "kind": "place", "photos": [1]}]
    short.beats[0].shot, short.beats[0].card = "photo:0", {"big": "उत्सव मैदान", "small": "कार्यक्रम स्थल"}
    assert any("card 1 names the place" in p for p in gate.said_is_shown(short))


def test_a_short_of_only_photos_shown_lately_is_not_made():
    from desk import writer

    photos = [{"file": f"File:Tiger Shroff {n}.jpg"} for n in range(4)] + [{"file": "OpenStreetMap: जुहू", "role": "map"}]
    views = [[0, 4], [1], [2], [4], [3]]
    shown_before = {p["file"] for p in photos}
    assert "only 0 of 4 photos" in writer.stale_pictures(photos, views, shown_before)
    assert writer.stale_pictures(photos, views, shown_before - {photos[2]["file"], photos[3]["file"]}) is None
    assert writer.stale_pictures(photos, views, set()) is None
    five = photos[:4] + [{"file": "File:Juhu ISKCON.jpg"}, photos[4]]
    # The Tiger Shroff security Short: 2 of 5 new (an award portrait, Juhu's temple), the rest shown before.
    seen = {f["file"] for f in five} - {five[0]["file"], five[4]["file"]}
    assert "only 2 of 5" in writer.stale_pictures(five, [[0, 5], [1], [2], [3], [4]], seen)


def test_the_police_of_the_town_a_place_lies_in(monkeypatch):
    juhu = {"en": "Juhu", "hi": "जुहू", "qid": "Q674362", "ent": {"claims": {"P131": [claim("Q1156")]}}}
    mumbai = {"labels": {"en": {"value": "Mumbai"}}, "claims": {"P1082": [claim({"amount": "+12442373"})]}}
    monkeypatch.setattr(wiki, "entities", lambda qids: {"Q1156": mumbai})
    monkeypatch.setattr(wiki, "common_hindi", lambda ent: "मुंबई")
    around = list(visuals._cities_around([juhu]))
    assert [(c["en"], c["hi"], c["qid"]) for c in around] == [("Mumbai", "मुंबई", "Q1156")]
    assert list(visuals._cities_around([juhu, {**juhu, "qid": "Q2"}])) == around


def test_the_police_photo_waits_for_the_police_beat():
    juhu = {"en": "Juhu", "hi": "जुहू", "kind": "place", "photos": [8], "near": [9]}
    police = {"kind": "police", "hi": "मुंबई", "photos": [10]}
    beats = [{"say": "टाइगर श्रॉफ पर फायरिंग के बाद संगठनों ने सुरक्षा मांगी।", "photo": 0},
             {"say": "रविवार शाम जुहू में एक्टर की कार पर गोलियां चलीं।", "photo": 0},
             {"say": "AICWA का दावा है कि कलाकारों को डराने के लिए हमले हो रहे हैं।", "photo": 0},
             {"say": "पुलिस अब अन्य फिल्मी हस्तियों के घरों की सुरक्षा की जांच कर रही है।", "photo": 0},
             {"say": "आरोपियों से पूछताछ कर हमले की वजह जानने की कोशिश जारी है।", "photo": 0}]
    views = visuals.assign_legacy(beats, [0, 1, 2], [juhu, police], first=0, person=["Tiger Shroff", "टाइगर", "श्रॉफ"])
    assert 10 not in views[2] and 10 in views[3] and 10 in views[4]


def test_photos_shown_lately_go_last(monkeypatch):
    rows = [{"file": "File:A.jpg"}, {"file": "File:B.jpg"}, {"file": "File:C.jpg"}]
    assert [r["file"] for r in visuals.fresh_first(rows, {"File:A.jpg"})] == ["File:B.jpg", "File:C.jpg",
                                                                              "File:A.jpg"]
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(ledger, "published", lambda: [
        {"published_at": (now - timedelta(hours=2)).isoformat(), "photos": ["File:A.jpg"]},
        {"published_at": (now - timedelta(days=9)).isoformat(), "photos": ["File:Old.jpg"]},
        {"published_at": now.isoformat()}])
    assert ledger.recent_photos() == {"File:A.jpg"}
