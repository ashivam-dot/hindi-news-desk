from PIL import Image

from desk import compose, visuals
from desk.spec import shot_photos

cast_for = visuals.cast_for

# The Tiger Shroff script of 2026-10-20, which went out over one photo for all six beats.
TIGER = [
    {"say": "एक्टर टाइगर श्रॉफ पर मुम्बई में फायरिंग हुई, जिसमें वे बाल-बाल बच गए।", "photo": 0},
    {"say": "रिपोर्टों के मुताबिक रविवार शाम फुटबॉल खेलकर लौट रहे टाइगर की कार पर दो लोगों ने गोलियां चलाईं।", "photo": 0},
    {"say": "महाराष्ट्र के उपमुख्यमंत्री एकनाथ शिंदे ने टाइगर से मिलकर उनके परिवार को पूरी सुरक्षा का भरोसा दिया।", "photo": 0},
    {"say": "पुलिस ने इस हमले की कोई आधिकारिक वजह अब तक साफ नहीं की है।", "photo": 0},
    {"say": "टाइगर एक्टर जैकी श्रॉफ के बेटे हैं और उन्होंने 2014 में फिल्म heropanti से करियर शुरू किया था।", "photo": 0},
    {"say": "कोटा से पकड़े गए 3 संदिग्धों को पुलिस अब पूछताछ के लिए मुम्बई ला रही है।", "photo": 0},
]


def tiger_cast(own: int = 3):
    """Indices: the story's own photos 0..own-1, then Shinde, Jackie Shroff, maps and the police."""
    n = own
    shinde, jackie = [n], [n + 1]
    mumbai, mumbai_near, maha, kota, route, police = n + 2, n + 3, n + 4, n + 5, n + 6, n + 7
    cast = [
        {"en": "Mumbai", "hi": "मुम्बई", "kind": "place", "photos": [mumbai], "near": [mumbai_near]},
        {"en": "Maharashtra", "hi": "महाराष्ट्र", "kind": "place", "photos": [maha], "near": []},
        {"en": "Eknath Shinde", "hi": "एकनाथ शिंदे", "kind": "person", "photos": shinde},
        {"en": "Jackie Shroff", "hi": "जैकी श्रॉफ", "kind": "person", "photos": jackie},
        {"en": "Kota", "hi": "कोटा", "kind": "place", "photos": [kota], "near": []},
        {"kind": "route", "pair": ("Kota", "Mumbai"), "photos": [route]},
        {"kind": "police", "photos": [police]},
    ]
    return list(range(own)), cast, dict(shinde=shinde[0], jackie=jackie[0], mumbai=mumbai, maha=maha, route=route,
                                         police=police)


def test_each_beat_shows_who_or_where_it_names():
    subject, cast, at = tiger_cast()
    views = visuals.assign_legacy(TIGER, subject, cast, first=0)
    mains = [v[0] for v in views]
    assert mains[0] == 0 and at["mumbai"] in views[0]
    assert mains[1] in subject and mains[1] != 0
    assert mains[2] == at["shinde"]
    assert mains[3] == at["police"]
    assert mains[4] == at["jackie"]
    assert mains[5] == at["route"]
    assert len({i for v in views for i in v}) >= 8
    assert all(a[0] != b[0] for a, b in zip(views, views[1:]))


def test_the_picture_that_closed_a_beat_never_opens_the_next():
    subject, cast, at = tiger_cast()
    beats = TIGER[:5] + [TIGER[5], {"say": "पुलिस ने आगे की जांच शुरू कर दी है।", "photo": 0}]
    views = visuals.assign_legacy(beats, subject, cast, first=0)
    flat = [i for v in views for i in v]
    assert all(a != b for a, b in zip(flat, flat[1:]))
    assert at["police"] in views[6]


def test_a_beat_that_only_quotes_the_police_shows_its_place_and_never_another_forces_police():
    subject, cast, at = tiger_cast()
    cast[-1]["hi"] = "मुंबई"
    beats = [TIGER[0],
             {"say": "पुलिस के अनुसार, आरोपी कोटा पहुंचे और वहां ट्रेन में सवार हुए थे।", "photo": 0},
             {"say": "राजस्थान पुलिस ने बताया कि तीनों आरोपी पकड़े गए।", "photo": 0},
             {"say": "मुंबई पुलिस आरोपियों से पूछताछ कर रही है।", "photo": 0}]
    views = visuals.assign_legacy(beats, subject, cast, first=0)
    assert views[1][0] != at["police"] and at["police"] not in views[2]
    assert views[3][0] == at["police"]
    assert len(views[1]) == 2 and not set(views[1]) & set(subject)
    assert visuals.other_force("राजस्थान पुलिस ने बताया", cast[-1])
    assert not visuals.other_force("संदिग्धों को पुलिस अब मुम्बई ला रही है", cast[-1])
    assert not visuals.other_force("मुम्बई पुलिस ने कहा", cast[-1])


def test_a_beat_that_does_not_name_the_storys_person_never_shows_their_portrait():
    subject, cast, at = tiger_cast()
    beats = [TIGER[0],
             {"say": "आरोपियों से अब पूछताछ की जा रही है।", "photo": 1},
             {"say": "इस फायरिंग में दो लोग घायल हुए थे जो अस्पताल में हैं।", "photo": 2},
             {"say": "पुलिस के मुताबिक आरोपी कोटा के रास्ते भाग रहे थे।", "photo": 0},
             {"say": "टाइगर श्रॉफ ने बाद में शूटिंग फिर शुरू की।", "photo": 1}]
    views = visuals.assign_legacy(beats, subject, cast, first=0, person=["Tiger Shroff", "टाइगर", "श्रॉफ"])
    assert views[1][0] == at["police"]
    assert all(not set(v) & set(subject) for v in views[1:4]), views
    assert views[4][0] in subject
    # Without the person's names, a beat that names nobody falls back on the story's own photos as before.
    assert visuals.assign_legacy(beats, subject, cast, first=0)[2][0] in subject


def test_a_lone_portrait_still_alternates_with_maps_and_never_fills_every_beat():
    subject, cast, at = tiger_cast(own=1)
    views = visuals.assign_legacy(TIGER, subject, cast, first=0)
    assert sum(v[0] == 0 for v in views) <= 2
    assert len({i for v in views for i in v}) >= 5


def test_with_no_cast_the_own_photos_rotate():
    views = visuals.assign_legacy(TIGER, [0, 1, 2], [], first=0)
    mains = [v[0] for v in views]
    assert all(a != b for a, b in zip(mains, mains[1:]))
    assert set(mains) == {0, 1, 2}
    assert all(len(v) == 2 and v[0] != v[1] for v in views)


def test_shots_name_their_cut():
    assert shot_photos("photo:3/7") == [3, 7] and shot_photos("photo:2") == [2]
    assert shot_photos("outro") == [] and shot_photos("photo:x") == []


def test_a_long_beat_cuts_between_words_to_its_second_picture():
    beat = {"photo": 1, "views": [1, 4], "start": 0.0, "end": 6.0, "motion": compose.MOTIONS[0], "outro": False}
    short_beat = beat | {"views": [2], "photo": 2, "start": 6.0, "end": 8.0}
    words = [{"start": s, "end": s + 0.4, "text": "x"} for s in (0.2, 1.0, 2.1, 2.9, 3.6, 4.5, 6.2)]
    seen = compose.views([beat, short_beat], words, anchored=False)  # the legacy matcher: at the middle
    assert [(s["photo"], s["start"], s["end"], s["cut"]) for s in seen] == \
        [(1, 0.0, 2.9, False), (4, 2.9, 6.0, True), (2, 6.0, 8.0, False)]
    # Anchored (SYNC-AUDIT 4.1 step 6): the second picture only on the word naming it; with no cut word, the same
    # photo closer.
    seen = compose.views([beat, short_beat], words)
    assert [(s["photo"], s["start"], s["cut"]) for s in seen[:2]] == [(1, 0.0, False), (1, 2.9, True)]
    assert seen[1]["motion"] is compose.TIGHT
    alone = compose.views([beat | {"views": [1]}], words, anchored=False)
    assert alone[1]["photo"] == 1 and alone[1]["motion"] is compose.TIGHT


def place(qid, en, lat, lon, pop=None, part_of=None, region=False):
    def claim(value):
        return {"mainsnak": {"datavalue": {"value": value}}}
    claims = {"P625": [claim({"latitude": lat, "longitude": lon})]}
    if pop:
        claims["P1082"] = [claim({"amount": f"+{pop}"})]
    if part_of:
        claims["P131"] = [claim({"id": part_of})]
    if region:
        claims["P36"] = [claim({"id": "Q1"})]
    return {"en": en, "qid": qid, "kind": "place", "ent": {"claims": claims}}


def test_a_spot_inside_a_city_is_marked_on_the_city_never_joined_to_it():
    mumbai = place("Q1156", "Mumbai", 18.97, 72.83, pop=12_442_373)
    juhu = place("Q1764487", "Juhu", 19.10, 72.83)
    kota = place("Q200009", "Kota", 25.18, 75.83, pop=1_001_694)
    maha = place("Q1191", "Maharashtra", 19.6, 75.5, pop=112_374_333, region=True)
    assert {a: b["en"] for a, b in visuals.within([mumbai, juhu, kota, maha]).items()} == {"Juhu": "Mumbai"}
    assert visuals.within([place("Q5", "Bandra", 19.05, 72.84, part_of="Q1156"), mumbai])["Bandra"] is mumbai
    # "मुम्बई के जुहू": the beat shows Juhu on Mumbai's map, not Mumbai's centre, and no route between them.
    cast = [{"en": "Mumbai", "hi": "मुम्बई", "kind": "place", "photos": [3], "near": [5]},
            {"en": "Juhu", "hi": "जुहू", "kind": "place", "photos": [5], "near": [6], "inside": "Mumbai"}]
    views = visuals.assign_legacy([{"say": "x", "photo": 0}, {"say": "यह मुम्बई के जुहू में हुआ।", "photo": 0},
                            {"say": "मुम्बई पुलिस जांच कर रही है।", "photo": 0}], [0, 1], cast, first=0)
    assert views[1][0] == 5 and 3 not in views[1]


def test_states_leave_room_for_the_towns_and_stations(monkeypatch):
    # The probe Short of 2026-10-20: two home states, two districts, Mumbai, Rajasthan and Kota's station.
    names = [("Haryana", "हरियाणा", True), ("Kota Police", "कोटा पुलिस", False), ("Sonipat", "सोनीपत", False),
             ("Bihar", "बिहार", True), ("Begusarai", "बेगूसराय", False), ("Mumbai", "मुम्बई", False),
             ("Andheri West", "अंधेरी वेस्ट", False), ("Rajasthan", "राजस्थान", True),
             ("Kota railway station", "कोटा रेलवे स्टेशन", False), ("Juhu", "जुहू", False),
             ("Delhi", "दिल्ली", False), ("Surat", "सूरत", False), ("Gujarat", "गुजरात", True)]
    known = {en: place(f"Q{i}", en, 20.0 + i, 75.0, region=r) for i, (en, _, r) in enumerate(names)}
    monkeypatch.setattr(visuals, "resolve", lambda en, india: (known[en]["qid"], en, known[en]["ent"]))
    monkeypatch.setattr(visuals, "kinds", lambda ent: set())
    draft = {"names": [{"en": en, "hi": hi} for en, hi, _ in names],
             "beats": [{"say": " ".join(hi for _, hi, _ in names)}]}
    assert [c["en"] for c in cast_for(draft, "Tiger Shroff", True)] == [
        "Haryana", "Sonipat", "Bihar", "Begusarai", "Mumbai", "Andheri West", "Rajasthan", "Kota railway station",
        "Juhu", "Delhi"]


def test_a_named_landmark_shows_its_photo_then_its_map_and_a_route_still_gets_the_photo():
    cast = [{"en": "Kota Junction", "hi": "कोटा जंक्शन", "kind": "place", "photos": [4], "near": [], "sight": [3]},
            {"en": "Surat", "hi": "सूरत", "kind": "place", "photos": [5], "near": []},
            {"kind": "route", "pair": ("Surat", "Kota Junction"), "photos": [6]}]
    views = visuals.assign_legacy([{"say": "x", "photo": 0}, {"say": "वे कोटा जंक्शन पर पकड़े गए।", "photo": 0},
                            {"say": "वे सूरत से कोटा जंक्शन तक गए।", "photo": 0}], [0, 1], cast, first=0)
    assert views[1] == [3, 4]
    assert views[2][0] == 6 and 3 in views[2]


def test_maps_hold_every_site_inside_the_frame():
    win = visuals.window([(25.18, 75.83), (19.08, 72.88)], 300.0)
    for lat, lon in ((25.18, 75.83), (19.08, 72.88)):
        x, y = visuals.project(win, lat, lon)
        assert 0.1 * visuals.MAP_W < x < 0.9 * visuals.MAP_W and 0.1 * visuals.MAP_H < y < 0.9 * visuals.MAP_H


def test_a_map_is_drawn_with_its_hindi_names(tmp_path):
    win = visuals.window([(19.08, 72.88)], visuals.WIDE_KM)
    img = visuals.draw(Image.new("RGB", (visuals.MAP_W, visuals.MAP_H), (200, 220, 200)), win,
                       [((19.08, 72.88), "मुम्बई")])
    assert img.size == (visuals.MAP_W, visuals.MAP_H)
    x, y = (round(v) for v in visuals.project(win, 19.08, 72.88))
    assert img.getpixel((x, y))[0] > 180  # the red marker sits on the site
