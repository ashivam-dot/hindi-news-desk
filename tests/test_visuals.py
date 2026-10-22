from PIL import Image

from desk import compose, match, visuals
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


def anchored(beats, subject, cast, spell=(), kind="", person=True):
    """match.plan's rows for a test cast, as visuals.direct stamps it: each cast picture depicts its member (a route
    both ends, the police POLICE), the story's own photos the subject. The anchored path replaced assign_legacy's
    fallbacks (SYNC-AUDIT 4.1 step 8): these tests once pinned a filled beat and now pin a card or the named picture."""
    n = max([*subject, *(i for c in cast for f in ("photos", "near", "sight") for i in c.get(f) or [])]) + 1
    photos = [{} for _ in range(n)]
    by_en = {c.get("en"): c for c in cast}
    for c in cast:
        keys = [match.key(by_en[e]) for e in c["pair"]] if c.get("kind") == "route" else [match.key(c)]
        for i in [*(c.get("photos") or []), *(c.get("near") or []), *(c.get("sight") or [])]:
            photos[i] = {"depicts": keys, "role": "map" if c.get("kind") in ("place", "route") else c.get("kind")}
    for i in subject:
        photos[i] = {"depicts": [match.SUBJECT]}
    return match.plan([{"say": b["say"]} for b in beats], photos, cast, subject, kind, spell, person)


TIGER_SPELT = ["टाइगर श्रॉफ", "टाइगर", "श्रॉफ"]


def views_of(rows):
    return [r["views"] if r["plate"] != match.CARD else None for r in rows]


def test_each_beat_shows_who_or_where_it_names():
    subject, cast, at = tiger_cast()
    rows = anchored(TIGER, subject, cast, TIGER_SPELT)
    assert views_of(rows) == [[0, at["mumbai"]], [1], [at["maha"], at["shinde"]], [at["police"]], [2, at["jackie"]],
                              [at["route"], at["police"]]]
    # The second picture comes on the word that names it, never at the middle of the beat.
    assert [r["cut_word"] for r in rows] == ["मुम्बई", "", "एकनाथ", "", "जैकी", "संदिग्धों"]
    assert len({i for v in views_of(rows) for i in v}) >= 8


def test_the_picture_that_closed_a_beat_opens_the_next_only_when_it_is_the_one_named():
    subject, cast, at = tiger_cast()
    beats = TIGER[:5] + [TIGER[5], {"say": "पुलिस ने आगे की जांच शुरू कर दी है।"}]
    assert views_of(anchored(beats, subject, cast, TIGER_SPELT))[5:] == [[at["route"], at["police"]], [at["police"]]]
    cast[-1]["photos"] = [at["police"], at["police"] + 1]  # a second police photo: the next beat opens on it
    v = views_of(anchored(beats, subject, cast, TIGER_SPELT))
    assert v[6] != v[5][-1:] and set(v[5][-1:] + v[6]) == set(cast[-1]["photos"])


def test_a_beat_that_quotes_another_force_is_a_card():
    subject, cast, at = tiger_cast()
    cast[-1]["hi"] = "मुंबई"
    beats = [TIGER[0],
             {"say": "पुलिस के अनुसार, आरोपी कोटा पहुंचे और वहां ट्रेन में सवार हुए थे।"},
             {"say": "राजस्थान पुलिस ने बताया कि तीनों आरोपी पकड़े गए।"},
             {"say": "मुंबई पुलिस आरोपियों से पूछताछ कर रही है।"}]
    rows = anchored(beats, subject, cast, TIGER_SPELT)
    kota = cast[4]["photos"][0]
    # Rajasthan's police: not Mumbai's. Kota's map, cut to on its word, would hold half the voice's picture time
    # (beat 1 cuts to Mumbai's on its fourth word): plan drops the latest map cut (finding 12).
    assert views_of(rows)[1:] == [[at["police"]], None, [at["police"]]]
    assert rows[0]["views"] == [0, at["mumbai"]] and kota in cast[4]["photos"]
    assert visuals.other_force("राजस्थान पुलिस ने बताया", cast[-1])
    assert not visuals.other_force("संदिग्धों को पुलिस अब मुम्बई ला रही है", cast[-1])
    assert not visuals.other_force("मुम्बई पुलिस ने कहा", cast[-1])


def test_a_beat_that_does_not_name_the_storys_person_never_shows_their_portrait():
    subject, cast, at = tiger_cast()
    beats = [TIGER[0],
             {"say": "आरोपियों से अब पूछताछ की जा रही है।"},
             {"say": "इस फायरिंग में दो लोग घायल हुए थे जो अस्पताल में हैं।"},
             {"say": "पुलिस के मुताबिक आरोपी कोटा के रास्ते भाग रहे थे।"},
             {"say": "टाइगर श्रॉफ ने बाद में शूटिंग फिर शुरू की।"}]
    rows = anchored(beats, subject, cast, TIGER_SPELT)
    assert views_of(rows)[1:4] == [[at["police"]], None, [at["police"], cast[4]["photos"][0]]]
    assert rows[4]["views"][0] in subject
    # The injured beat names no one a picture is of: a card, and its backdrop is not their portrait either.
    assert not set(rows[2]["views"]) & set(subject) and match.plain(beats[2]["say"])
    # Without the person's spellings nothing names them: their beat is a card, never a fill from their own photos.
    blind = anchored(beats, subject, cast)
    assert blind[4]["plate"] == match.CARD and not any(set(r["views"]) & set(subject) for r in blind[1:])


def test_a_lone_portrait_stands_only_under_the_beats_that_name_him():
    subject, cast, at = tiger_cast(own=1)
    rows = anchored(TIGER, subject, cast, TIGER_SPELT)
    assert [k for k, r in enumerate(rows) if 0 in r["views"]] == [0, 1, 4]  # beats 2 and 5 name Shinde, Jackie
    assert all(r["plate"] == "" for r in rows) and len({i for r in rows for i in r["views"]}) >= 5


def test_with_no_cast_a_beat_naming_nothing_is_a_card():
    rows = anchored(TIGER, [0, 1, 2], [], TIGER_SPELT)
    assert views_of(rows) == [[0], [1], [2], None, [0], None]  # no police, no Kota: cards, not the own photos
    assert all(not r["cut_word"] for r in rows)


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
    # "मुम्बई के जुहू": the beat shows Juhu on Mumbai's map, not Mumbai's centre, and no route between them; and
    # "मुम्बई पुलिस" names the police, not the city, so with no police photo it is a card (never Juhu's map, the
    # spot-near half the legacy matcher put under its city).
    cast = [{"en": "Mumbai", "hi": "मुम्बई", "kind": "place", "photos": [3], "near": []},
            {"en": "Juhu", "hi": "जुहू", "kind": "place", "photos": [5], "near": [6], "inside": "Mumbai"}]
    rows = anchored([{"say": "x"}, {"say": "यह मुम्बई के जुहू में हुआ।"}, {"say": "मुम्बई पुलिस जांच कर रही है।"}],
                    [0, 1], cast)
    assert views_of(rows) == [[0], [5], None]
    assert views_of(anchored([{"say": "x"}, {"say": "मुम्बई में बैठक हुई।"}], [0, 1], cast)) == [[0], [3]]


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


def test_a_named_landmark_shows_its_photo_and_two_places_their_route():
    cast = [{"en": "Kota Junction", "hi": "कोटा जंक्शन", "kind": "place", "photos": [4], "near": [], "sight": [3]},
            {"en": "Surat", "hi": "सूरत", "kind": "place", "photos": [5], "near": []},
            {"kind": "route", "pair": ("Surat", "Kota Junction"), "photos": [6]}]
    rows = anchored([{"say": "x"}, {"say": "वे कोटा जंक्शन पर पकड़े गए।"}, {"say": "वे सूरत से कोटा जंक्शन तक गए।"}],
                    [0, 1], cast)
    # One name, one picture: the station's own photo, no cut to its map (compose holds it closer, TIGHT).
    assert views_of(rows) == [[0], [3], [6]] and rows[1]["cut_word"] == ""


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
