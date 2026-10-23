"""The owner's rule of 2026-10-23, "the picture follows the voice" (Matlabnama audit R1-R5): a beat that says train
shows a train, a flight a plane; one map, where the story happened, or for a journey one route map with both ends; no
map, photo or card backdrop on two beats; a stand-in photo says so (प्रतीकात्मक तस्वीर) and is credited; and what
cannot be shown is refused with a logged reason ("pictures: ...", cli.RETRYABLE)."""
from dataclasses import replace

from desk import hindi, match, things, visuals, youtube
from desk.spec import Beat, Short

PLANE, TRAIN = hindi.norm("विमान"), hindi.norm("ट्रेन")
DELHI, LONDON = hindi.norm("दिल्ली"), hindi.norm("लंदन")
CAST_FOR = visuals.cast_for  # conftest stubs it to [] for every test; these run the real one offline


def hits(say, india=True):
    return [h["en"] for h in things.lexicon_hits([{"say": say}], india)]


def photo(file, **kw):
    return {"file": file, "page": "https://commons.wikimedia.org/wiki/" + file, "author": "A", "license": "CC0",
            "credit": "फ़ोटो: A / CC0 / Wikimedia Commons", "path": "x.jpg", **kw}


def stand_in(file, who, key):
    return things.label(photo(file, role="thing", who=who, depicts=[key], focus=None))


def a_map(file, who, keys, about, **kw):
    return photo(file, role="map", who=who, depicts=keys, description=f"MAP: {about}", host="OpenStreetMap", **kw)


CAST = [{"en": "Delhi", "hi": "दिल्ली", "kind": "place", "photos": [3]},
        {"en": "London", "hi": "लंदन", "kind": "place", "photos": [4]},
        {"en": "Airplane", "hi": "विमान", "kind": "thing", "stand_in": True,
         "alias": ["फ्लाइट", "फ्लाइट्स", "उड़ान"], "photos": [1, 2]}]


def travel_photos():
    return [photo("File:Story.jpg"), stand_in("File:Airbus A380.jpg", "विमान", PLANE),
            stand_in("File:ANA Cargo.jpg", "विमान", PLANE),
            a_map("OpenStreetMap: दिल्ली", "दिल्ली", [DELHI], "where Delhi is"),
            a_map("OpenStreetMap: लंदन", "लंदन", [LONDON], "where London is"),
            a_map("OpenStreetMap: दिल्ली - लंदन", "दिल्ली - लंदन", [DELHI, LONDON], "Delhi and London")]


def mk(says, shots, photos, cast=CAST, plates=None, kind="incident"):
    beats = [Beat(t, s, plate=(plates or {}).get(k, "")) for k, (t, s) in enumerate(zip(says, shots))]
    return Short(id="kh-20261023-test", kind=kind, title="t", beats=beats, facts=[], sources=[], loss=False,
                 scene={"photos": photos, "cast": cast, "name_hi": "", "subject_person": False, "names": []})


# --- R1: the beat shows the thing its words name --------------------------------------------------------------------

def test_a_beat_naming_a_vehicle_gets_its_stand_in_row():
    assert hits("ट्रेन पटरी से उतर गई") == ["Train"]
    assert hits("सैकड़ों फ्लाइट्स रद्द") == ["Airplane"]
    assert hits("एयर इंडिया का विमान दिल्ली लौटा") == ["Airplane"]  # an aircraft, never the airline's livery
    assert hits("इस जहाज़ पर 20 भारतीय सवार हैं") == ["Ship"]
    assert hits("हवाई जहाज़ में आग लगी") == ["Airplane"]  # a plane, not a ship
    assert hits("कुवैत के एक टैंकर पर ड्रोन हमला हुआ", india=False) == ["Oil tanker"]
    assert hits("हेलीकॉप्टर क्रैश में दो की मौत") == ["Helicopter"]
    assert "Missile" in hits("मिसाइल हमले में इमारत ढह गई")
    assert hits("अमेरिकी मिसाइल का परीक्षण हुआ", india=False) == ["Missile"]  # any country's missile is a missile
    # Not the vehicle: a scheme, an evacuation, a water tanker, a dream.
    assert hits("उड़ान योजना के तहत नए हवाई अड्डे") == []
    assert "Vande Bharat Express" not in hits("वंदे भारत मिशन से लोग लौटे") and "Train" not in hits("वंदे भारत मिशन")
    # The mission is no train; its flights are flights (once test_review_round1's "no lexicon thing" for this line).
    assert hits("वंदे भारत मिशन के तहत उड़ानें") == ["Airplane"]
    assert hits("गांव में पानी के टैंकर पहुंचे") == []
    rows = {h["en"]: h for h in things.lexicon_hits([{"say": "ट्रेन पटरी से उतर गई"}], True)}
    assert rows["Train"]["stand_in"] and rows["Train"]["files"]


def test_train_beat_shows_the_train_picture():
    photos = [photo("File:Story.jpg"), stand_in("File:Ramgiri Pass.jpg", "ट्रेन", TRAIN)]
    cast = [{"en": "Train", "hi": "ट्रेन", "kind": "thing", "stand_in": True, "alias": ["ट्रेनों"], "photos": [1]}]
    rows = match.plan([{"say": "ओडिशा में बड़ा हादसा।"}, {"say": "एक ट्रेन पटरी से उतर गई।"}], photos, cast, [0],
                      "incident", person=False)
    assert rows[1]["views"] == [1] and rows[1]["plate"] == ""


def test_stand_in_lexicon_rows_skip_the_wikidata_lookup(monkeypatch):
    looked = []
    draft = {"names": [], "beats": [{"say": "सैकड़ों फ्लाइट्स रद्द हुईं।"}]}
    cast = CAST_FOR(draft, "", True, resolver=lambda *a, **k: None, thing_lookup=lambda e: looked.append(e["en"]))
    assert [(c["en"], c.get("stand_in")) for c in cast] == [("Airplane", True)] and looked == []


def test_an_actual_thing_takes_the_generic_words():
    """The script's own ship (INS Vikrant) is shown under "जहाज़", never a stand-in container ship."""
    vikrant = {"descriptions": {"en": {"value": "aircraft carrier of the Indian Navy"}}, "claims": {}}
    draft = {"names": [{"en": "INS Vikrant", "hi": "आईएनएस विक्रांत"}],
             "beats": [{"say": "आईएनएस विक्रांत मुंबई पहुंचा।"}, {"say": "इस जहाज़ पर 1600 नौसैनिक हैं।"}]}
    cast = CAST_FOR(draft, "", True, resolver=lambda *a, **k: None,
                    thing_resolver=lambda en: ("Q1", en, vikrant) if en == "INS Vikrant" else None)
    assert [c["en"] for c in cast] == ["INS Vikrant"] and "जहाज़" in cast[0]["alias"]


# --- R2: a stand-in says so and is credited ----------------------------------------------------------------------

def test_a_stand_in_carries_the_label_on_screen_and_in_the_description():
    p = stand_in("File:Airbus A380.jpg", "विमान", PLANE)
    assert p["stand_in"] and p["credit"].startswith(things.STAND_IN) and "Wikimedia Commons" in p["credit"]
    assert things.label(p) == p  # once
    assert things.STAND_IN == "प्रतीकात्मक तस्वीर"
    assert things.STAND_IN in youtube.photo_credits([p])
    unlabelled = travel_photos()
    unlabelled[1] = unlabelled[1] | {"credit": "फ़ोटो: A / CC0 / Wikimedia Commons"}
    s = mk(["ओडिशा में हादसा।", "सैकड़ों फ्लाइट्स रद्द हुईं।"], ["photo:0", "photo:1"], unlabelled)
    assert any("प्रतीकात्मक" in x for x in match.problems(s))
    ok = mk(["ओडिशा में हादसा।", "सैकड़ों फ्लाइट्स रद्द हुईं।"], ["photo:0", "photo:1"], travel_photos())
    assert not any("प्रतीकात्मक" in x for x in match.problems(ok))


def test_a_handshake_or_a_second_face_is_someone_else():
    tusk = {"file": "File:Obama Poland Tusk (2).jpg", "role": "person", "who": "डोनाल्ड तुस्क",
            "description": "with President Barack Obama, President Bronisław Komorowski and Prime Minister Donald Tusk",
            "categories": "Barack Obama and Donald Tusk|Donald Tusk shaking hands", "others": 1}
    why, hard = match._with_someone(tusk, [tusk], ["Donald Tusk"], "Donald Tusk", "person")
    assert why and hard
    alone = {"file": "File:Donald Tusk 2024.jpg", "role": "person", "who": "डोनाल्ड तुस्क", "others": 0}
    assert match._with_someone(alone, [alone], ["Donald Tusk"], "Donald Tusk", "person") == ("", False)


# --- R3: one map, where it happened; a journey's route with both ends -----------------------------------------------

def test_a_route_story_gets_one_origin_destination_map():
    photos = travel_photos()
    says = ["दिल्ली से लंदन जा रही फ्लाइट रद्द कर दी गई।", "लंदन में सैकड़ों यात्री फंसे।", "दिल्ली में भी उड़ान रुकी।"]
    beats = [{"say": s} for s in says]
    told = [dict(c) for c in CAST]
    visuals.map_scope(beats, told, photos, None)
    assert photos[5].get("travel") and not photos[5].get("away")
    assert photos[3].get("away") and photos[4].get("away")  # one-ended maps in a journey
    for i, p in enumerate(photos):
        if why := match.vet_photo(i, photos, told, 2026, False, True):
            p["vet"] = why
    rows = match.plan(beats, photos, told, [0], "incident", person=False)
    shown = [i for r in rows if r["plate"] != match.CARD for i in r["views"]]
    assert [i for i in shown if visuals.is_map(photos[i])] == [5]
    assert rows[0]["views"] == [5, 1] and rows[0]["cut_word"] in ("फ्लाइट",)


def test_the_map_is_of_where_it_happened():
    photos = travel_photos()[:5]
    beats = [{"say": "दिल्ली में एक इमारत गिरी।"}, {"say": "लंदन से आए दल ने मदद की।"}]
    visuals.map_scope(beats, [dict(c) for c in CAST], photos, {"en": "Delhi"})
    assert not photos[3].get("away") and photos[4].get("away")
    s = mk(["दिल्ली में एक इमारत गिरी।", "लंदन से आए दल ने मदद की।"], ["photo:3", "photo:4"], photos)
    assert any("not where the story happened" in x for x in match.problems(s))


def test_a_second_map_beat_is_refused():
    photos = travel_photos()
    s = mk(["दिल्ली में हादसा हुआ।", "दिल्ली में बचाव जारी है।"], ["photo:3", "photo:3"], photos)
    out = match.problems(s)
    assert any("map views" in x for x in out) and any("on beats 1 and 2" in x for x in out)


# --- R4: no picture on two beats -----------------------------------------------------------------------------------

def test_a_repeated_picture_is_refused():
    photos = travel_photos()
    s = mk(["सैकड़ों फ्लाइट्स रद्द हुईं।", "यात्री परेशान।", "उड़ानें कल शुरू होंगी।"], ["photo:1", "photo:0", "photo:1"],
           photos, plates={1: match.CARD})
    assert any(x.startswith("pictures: photo 1") and "on beats 1 and 3" in x for x in match.problems(s))


def test_plan_never_puts_one_picture_on_two_beats():
    photos = travel_photos()
    beats = [{"say": s} for s in ["सैकड़ों फ्लाइट्स रद्द हुईं।", "फ्लाइट्स में देरी जारी है।", "उड़ानें कल शुरू होंगी।"]]
    rows = match.plan(beats, photos, CAST, [0], "incident", person=False)
    seen = [i for r in rows if r["plate"] != match.CARD for i in r["views"]]
    assert len(seen) == len(set(seen))
    assert rows[2]["plate"] == match.CARD  # two plane photos, three plane beats: the third is an honest card
    # And its card is plain, never a blur of a picture another beat shows.
    s = mk([b["say"] for b in beats], ["photo:" + "/".join(map(str, r["views"])) for r in rows], photos,
           plates={k: r["plate"] for k, r in enumerate(rows)})
    assert match.card_plain(s, 2)


def test_legacy_rollback_keeps_its_own_plan(monkeypatch):
    from desk import config, gate

    monkeypatch.setattr(config, "MATCHER", "legacy")
    photos = travel_photos()
    s = mk(["दिल्ली में हादसा हुआ।", "दिल्ली में बचाव जारी है।"], ["photo:3", "photo:3"], photos)
    assert gate.shown_is_said(s) == []  # the rollback is judged as main judged it
    assert hits("ट्रेन पटरी से उतर गई") == ["Train"]  # the lexicon is data; cast_for skips it under legacy
    draft = {"names": [], "beats": [{"say": "ट्रेन पटरी से उतर गई।"}]}
    assert CAST_FOR(draft, "", True, resolver=lambda *a, **k: None) == []


def test_replay_reports_repeats_and_maps():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("replay", Path(__file__).parent / "tools" / "replay.py")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    photos = travel_photos()
    s = mk(["दिल्ली में हादसा हुआ।", "दिल्ली में बचाव जारी है।"], ["photo:3", "photo:3"], photos)
    assert replay.repeats(s) == 1 and replay.map_places(s) == [DELHI]
    assert replace(s).beats[0].text == "दिल्ली में हादसा हुआ।"


# --- Dry run 39954439164 (wiki:Air India Flight 171), the branch's own first dry run --------------------------------

def _claim(pid, value):
    return {pid: [{"rank": "normal", "mainsnak": {"datavalue": {"value": value}}}]}


def test_the_story_own_vehicle_is_shown_not_a_stand_in():
    """The article's "VT-ANB, the aircraft involved in the incident." stood unused while an Airbus A380 and an ANA
    cargo jet were shown as "विमान" (R2: a stand-in only when there is no free photo of the actual thing)."""
    story = [photo("File:Air India 787-8 (VT-ANB).jpg", origin="article",
                   description="VT-ANB, the aircraft involved in the incident."),
             photo("File:Sardar Vallabhbhai Patel International Airport, Ahmedabad, India 3.jpg", origin="article",
                   description="Ahmedabad Airport"),
             photo("File:VT-ANB B787-837 Air India BHX 25FEB14 (12781237535).jpg", origin="article",
                   description="This was a nice surprise, arriving just as it was getting dark."),
             photo("File:Boeing 777-337ER - Air India (VT-ALK).JPG", origin="article",
                   description="Boeing 777-337ER - Air India (VT-ALK) aircraft")]
    plane = {"en": "Airplane", "hi": "विमान", "kind": "thing", "stand_in": True,
             "cls": next(e["cls"] for e in things.LEXICON if e["en"] == "Airplane")}
    assert visuals.actual_thing(plane, story, [0, 1, 2, 3]) == [0, 2]  # VT-ALK is another Air India plane
    assert visuals.actual_thing(plane, story[1:], [0, 1, 2]) == []  # no photo says it is the one: a stand-in
    wreck = [photo("File:Coromandel Express.jpg", origin="article", description="The train involved, in 2019")]
    train = {"en": "Train", "hi": "ट्रेन", "kind": "thing", "stand_in": True,
             "cls": next(e["cls"] for e in things.LEXICON if e["en"] == "Train")}
    assert visuals.actual_thing(train, wreck, [0]) == [0]
    assert visuals.actual_thing(plane, wreck, [0]) == []


def test_a_spot_resolves_in_the_city_the_script_names_first():
    """"बी. जे. मेडिकल कॉलेज" in an Ahmedabad crash resolved to Pune's B. J. Medical College: its Pune photo stood
    under the beat. With no dateline, the script's first city is where later spots are looked up."""
    seen = []
    city = {"claims": _claim("P625", {"latitude": 23.03, "longitude": 72.58}) | _claim("P1082", {"amount": "+5570585"})}

    def resolver(en, india, near=None):
        seen.append((en, near))
        return ("Q1", "Ahmedabad", city) if en == "Ahmedabad" else None

    draft = {"names": [{"en": "Ahmedabad", "hi": "अहमदाबाद"}, {"en": "B. J. Medical College", "hi": "बी. जे. कॉलेज"}],
             "beats": [{"say": "अहमदाबाद में विमान गिरा।"}, {"say": "बी. जे. कॉलेज के हॉस्टल पर।"}]}
    CAST_FOR(draft, "", True, resolver=resolver, thing_resolver=lambda en: None, thing_lookup=lambda e: None)
    assert seen[0] == ("Ahmedabad", None)
    assert seen[1] == ("B. J. Medical College", {"en": "Ahmedabad", "at": (23.03, 72.58)})


def test_the_actual_aircraft_brings_its_registration_category(monkeypatch, tmp_path):
    """Commons keeps "Category:VT-ANB (aircraft)" (15 free photos): later beats that say "विमान" show the same
    aircraft again from other photos, not a stand-in and not a card (R1, R2, R4)."""
    from desk import media

    asked, given = [], []
    monkeypatch.setattr(media, "_category_files", lambda cat, limit=60: asked.append(cat) or
                        ["File:Air India 787-8 (VT-ANB).jpg", "File:VT-ANB.jpg", "File:VT-ANB 100624.jpg"])
    monkeypatch.setattr(things, "photos", lambda c, folder, exclude, recent=None, keep=0:
                        given.append((list(c["files"]), set(exclude))) or
                        [photo(f, role="thing", who=c["hi"], focus=None) for f in c["files"] if f not in exclude])
    story = [photo("File:Air India 787-8 (VT-ANB).jpg", origin="article",
                   description="VT-ANB, the aircraft involved in the incident.")]
    plane = {"en": "Airplane", "hi": "विमान", "kind": "thing"}
    rows = visuals.actual_more(plane, [0], story, tmp_path, {"File:Air India 787-8 (VT-ANB).jpg"})
    assert asked == ["VT-ANB (aircraft)"]
    assert [r["file"] for r in rows] == ["File:VT-ANB.jpg", "File:VT-ANB 100624.jpg"]
    assert all(not r.get("stand_in") for r in rows)
    monkeypatch.setattr(media, "_category_files", lambda cat, limit=60: (_ for _ in ()).throw(OSError("down")))
    assert visuals.actual_more(plane, [0], story, tmp_path, set()) == []  # a network failure keeps what it has
