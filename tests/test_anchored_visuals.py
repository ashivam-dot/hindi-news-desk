"""Steps 3 and 4 of SYNC-AUDIT 4.1 on audited Shorts: visuals.direct wires the anchored matcher and the writer writes
for the pictures that exist. All offline: Wikipedia, Wikidata and Commons are stubbed."""
from pathlib import Path

import numpy as np
import pytest

from desk import config, match, media, visuals, wiki, writer
from desk.spec import Short

SYNC = Path(__file__).parent / "fixtures" / "sync"
CAST_FOR = visuals.cast_for  # conftest stubs visuals.cast_for for every test


def short(name):
    return Short.load(SYNC / f"{name}.json")


@pytest.fixture
def items(monkeypatch):
    """Wikidata items as {"P31": [...], "P17": [...], "P1082": [...], "at": (lat, lon)}."""
    monkeypatch.setattr(wiki, "claims", lambda ent, pid: [{"value": v} for v in (ent or {}).get(pid, [])])
    monkeypatch.setattr(wiki, "coords", lambda ent: (ent or {}).get("at"))


def commons(monkeypatch, rows):
    """media.find and the download give rows; every image is blank and has no face."""
    from desk import faces

    monkeypatch.setattr(media, "find", lambda *a, **k: list(rows))
    monkeypatch.setattr(media, "download", lambda found, folder: found)
    monkeypatch.setattr(media, "as_dicts", lambda found: [dict(r) for r in found])
    monkeypatch.setattr("cv2.imread", lambda path: np.zeros((40, 40, 3), np.uint8))
    monkeypatch.setattr(faces, "detect", lambda img: [])


# --- Step 3: desk/visuals.py ----------------------------------------------------------------------------------------

def test_iskcon_not_juhu(monkeypatch, items, tmp_path):
    """"Juhu" showed ISKCON temple, Juhu: a suburb gets no sight photo, and a landmark photo is not its place."""
    def no_commons(*a, **k):
        raise AssertionError("a suburb's landmarks were looked up")

    monkeypatch.setattr(media, "find", no_commons)
    juhu = {"en": "Juhu", "hi": "जुहू", "kind": "place", "title": "Juhu", "ent": {"P31": ["Q123705"]}}
    assert visuals._sight_photos(juhu, tmp_path, set()) == []
    commons(monkeypatch, [{"file": "File:ISKCON temple, Juhu.jpg", "description": "ISKCON temple, Juhu", "path": "x"},
                          {"file": "File:Juhu Beach at dusk.jpg", "description": "Juhu Beach at dusk", "path": "y"}])
    beach = {"en": "Juhu Beach", "hi": "जुहू बीच", "kind": "place", "title": "Juhu Beach", "ent": {"P31": ["Q40080"]}}
    assert [r["file"] for r in visuals._sight_photos(beach, tmp_path, set(), keep=2)] == ["File:Juhu Beach at dusk.jpg"]


def test_andheri_station_not_flyover(monkeypatch, items, tmp_path):
    """"अंधेरी स्टेशन" is the station, resolved with one search, never Andheri (whose photo was its flyover)."""
    andheri = {"P31": ["Q188509"], "at": (19.11, 72.86)}
    station = {"P31": ["Q55488"], "at": (19.12, 72.85)}
    asked = []

    def hit(q, en, india):
        asked.append(q)
        return {"Andheri": ("Q1", "Andheri", andheri),
                "Andheri railway station": ("Q2", "Andheri railway station", station)}.get(q)

    monkeypatch.setattr(visuals, "_hit", hit)
    monkeypatch.setattr(visuals, "cast_for", CAST_FOR)
    draft = {"names": [{"en": "Andheri", "hi": "अंधेरी"}],
             "beats": [{"say": "हमलावर अंधेरी स्टेशन से लोकल ट्रेन में बैठे।"}, {"say": "अंधेरी में तलाशी जारी है।"}]}
    cast = visuals.cast_for(draft, "Tiger Shroff", True)
    # And "लोकल ट्रेन" a train (Matlabnama audit R1, 2026-10-23: a beat that says train shows one), a labelled stand-in.
    assert [(c["en"], c["hi"]) for c in cast] == [("Andheri", "अंधेरी"), ("Andheri railway station", "अंधेरी स्टेशन"),
                                                  ("Train", "ट्रेन")] and cast[2]["stand_in"]
    assert asked.count("Andheri railway station") == 1
    assert [c["en"] for c in visuals.mentions(draft["beats"][0]["say"], cast)] == ["Andheri railway station", "Train"]
    assert [c["en"] for c in visuals.mentions(draft["beats"][1]["say"], cast)] == ["Andheri"]
    commons(monkeypatch, [{"file": "File:Andheri flyover.jpg", "description": "Andheri flyover", "path": "x"},
                          {"file": "File:Andheri station platform.jpg", "description": "Andheri station", "path": "y"}])
    assert [r["file"] for r in visuals._sight_photos(cast[1], tmp_path, set(), keep=2)] == \
        ["File:Andheri station platform.jpg"]
    assert visuals._sight_photos(cast[0], tmp_path, set()) == []  # a suburb: its map only


def test_jantar_mantar_ranked_by_story_city(monkeypatch, items):
    """A Delhi protest at "जंतर मंतर" resolved to Jaipur's and showed its 1928 photo (39708703684): the hit nearest
    the story's dateline wins, with no fixed distance (Jaipur is about 240 km from Delhi)."""
    places = {"Jantar Mantar": "Jantar Mantar, Jaipur", "Jantar Mantar New Delhi": "Jantar Mantar, New Delhi",
              "Jantar Mantar, India": "Jantar Mantar, Jaipur", "New Delhi": "New Delhi"}
    ents = {"Jantar Mantar, Jaipur": {"P17": ["Q668"], "at": (26.92, 75.82)},
            "Jantar Mantar, New Delhi": {"P17": ["Q668"], "at": (28.63, 77.22)},
            "New Delhi": {"P17": ["Q668"], "P1082": [249998.0], "at": (28.61, 77.21)}}
    monkeypatch.setattr(wiki, "search", lambda q: places.get(q))
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"qid": t} for t in titles})
    monkeypatch.setattr(wiki, "entities", lambda qids: {q: ents[q] for q in qids})
    monkeypatch.setattr(media, "place_like", lambda ent: True)
    reports = [{"text": "NEW DELHI: Hundreds gathered at Jantar Mantar on Sunday ..."},
               {"url": "https://timesofindia.indiatimes.com/city/delhi/protest/articleshow/1.cms", "text": "x"},
               {"text": "NEW DELHI: Farmers' groups said ..."}]
    near = writer.story_anchor(reports)
    assert near == {"en": "New Delhi", "at": (28.61, 77.21)}
    assert visuals.resolve("Jantar Mantar", True)[1] == "Jantar Mantar, Jaipur"  # no story place: as before
    assert visuals.resolve("Jantar Mantar", True, near)[1] == "Jantar Mantar, New Delhi"
    assert writer.story_place("Jantar Mantar", near)[0] == "Jantar Mantar, New Delhi"
    assert writer.story_place("Jantar Mantar")[0] == "Jantar Mantar, Jaipur"
    assert writer.dateline([{"text": "In Chamoli, teams reached 14 villages"}]) is None  # no dateline



def test_a_book_title_beside_the_story_city_is_no_place(monkeypatch, items):
    """Sonia Gandhi's book 'बिलोंगिंग' (dry run 39747949900): "Belonging New Delhi" found Delhi and "Italy New Delhi"
    found New Delhi, and both went up as their maps. A place hit must hold the name the script said."""
    places = {"Belonging": "Belonging", "Belonging New Delhi": "Delhi", "Belonging, India": "India",
              "Italy": "Italy", "Italy New Delhi": "New Delhi", "Italy, India": "India–Italy relations",
              "Bombay": "Mumbai"}
    ents = {"Belonging": {"P31": ["Q7725634"]}, "Delhi": {"P17": ["Q668"], "at": (28.61, 77.21)},
            "India": {"P31": ["Q6256"], "at": (22.0, 79.0)}, "Italy": {"P31": ["Q6256"], "at": (42.0, 12.0)},
            "New Delhi": {"P17": ["Q668"], "at": (28.61, 77.21)}, "India–Italy relations": {"P31": ["Q15221623"]},
            "Mumbai": {"P17": ["Q668"], "at": (19.07, 72.88), "aliases": {"en": [{"value": "Bombay"}]}}}
    monkeypatch.setattr(wiki, "search", lambda q: places.get(q))
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"qid": t} for t in titles})
    monkeypatch.setattr(wiki, "entities", lambda qids: {q: ents[q] for q in qids})
    monkeypatch.setattr(media, "place_like", lambda ent: bool(ent.get("at")))
    monkeypatch.setattr(visuals, "COUNTRY_KINDS", {"Q6256"})
    near = {"en": "New Delhi", "at": (28.61, 77.21)}
    assert visuals.resolve("Belonging", True, near) is None
    assert visuals.resolve("Italy", True, near) is None
    assert visuals.resolve("Bombay", True)[1] == "Mumbai"  # an alias names it

def test_raut_label_dropped():
    """A card names only what its picture shows: "संजय राउत" under Tiger Shroff (39546660530's sibling), "वनतारा
    केंद्र" over the Jamnagar map (39714003987)."""
    s = short("39714003987")
    photos, cast = s.scene["photos"], s.scene["cast"]
    raut = {"en": "Sanjay Raut", "hi": "संजय राउत", "kind": "person", "photos": []}
    spell = ["मार्को रुबियो", "मार्को", "रुबियो"]
    card = {"big": "इस्तीफे की मांग", "small": "संजय राउत"}
    assert visuals.card_over(card, [1], cast + [raut], photos, spell) == {"big": "इस्तीफे की मांग", "small": ""}
    vantara = {"big": "वनतारा केंद्र", "small": "रुबियो का दौरा"}
    assert visuals.card_over(vantara, [8], cast, photos, spell) == {"big": "रुबियो का दौरा", "small": ""}
    assert visuals.card_over(vantara, [8, 12], cast, photos, spell) == vantara  # the cut is Vantara's own
    assert visuals.card_over({"big": "रुबियो का दौरा", "small": "मुकेश अंबानी"}, [1], cast, photos, spell) == \
        {"big": "रुबियो का दौरा", "small": ""}
    assert visuals.card_over(vantara, [8], cast, photos, spell, plate=match.CARD) == vantara  # a text card's words


def test_cast_drops_gala_and_small_face(monkeypatch, items, tmp_path):
    """Mukesh Ambani at the 2023 NMACC gala (p9) stood under "welcomed him at Jamnagar"; his 2007 WEF photo (p10)
    is fine; a speck of a face in a crowd is not a picture of him. Nothing left gives [] (a card)."""
    photos = short("39714003987").scene["photos"]
    p9, p10 = ({k: v for k, v in photos[i].items() if k not in ("role", "who")} for i in (9, 10))
    crowd = {"file": "File:Reliance AGM crowd.jpg", "description": "Reliance AGM", "date": "2024", "face": 0.04}
    rows = [p9 | {"face": 0.3}, crowd, p10 | {"face": 0.25}]
    monkeypatch.setattr(writer, "_own_photos", lambda *a, **k: [dict(r) for r in rows])
    ambani = {"en": "Mukesh Ambani", "hi": "मुकेश अंबानी", "kind": "person", "title": "Mukesh Ambani", "ent": {}}
    got = visuals._person_photos(ambani, tmp_path, set(), year=2026)
    assert [r["file"] for r in got] == [p10["file"]] and got[0]["role"] == "person"
    rows[:] = [p9, crowd]
    assert visuals._person_photos(ambani, tmp_path, set(), year=2026) == []


TIGER_DRAFT = {
    "names": [{"en": "Tiger Shroff", "hi": "टाइगर श्रॉफ"}, {"en": "Mumbai", "hi": "मुम्बई"}],
    "beats": [{"say": "टाइगर श्रॉफ की कार पर फायरिंग हुई।", "photo": 0, "caption": "कार पर फायरिंग", "label": ""},
              {"say": "यह हमला मुम्बई में हुआ।", "photo": 1, "caption": "रविवार रात", "label": ""},
              {"say": "डॉक्टरों के मुताबिक दोनों घायलों की हालत स्थिर है।", "photo": 2, "caption": "हालत स्थिर",
               "label": ""}]}


def test_legacy_matcher_switch(monkeypatch, items, tmp_path):
    """config.MATCHER: "anchored" puts a card under the beat that names nothing; "legacy" fills it as before."""
    mumbai = {"P31": ["Q515"], "P1082": [12442373.0], "at": (19.07, 72.88)}
    monkeypatch.setattr(visuals, "cast_for", lambda *a, **k: [{"en": "Mumbai", "hi": "मुम्बई", "kind": "place",
                                                               "qid": "Q1490", "title": "Mumbai", "ent": mumbai}])
    monkeypatch.setattr(visuals, "map_photo", lambda sites, km, path, about: {
        "file": f"OpenStreetMap: {path.name}", "role": "map", "who": sites[0][1], "description": f"MAP: {about}",
        "credit": "c", "page": "p"})
    own = [{"file": f"File:Tiger Shroff {i}.jpg", "description": "Tiger Shroff", "credit": "c", "page": "p"}
           for i in range(3)]

    def run(mode):
        monkeypatch.setattr(config, "MATCHER", mode)
        return visuals.direct(TIGER_DRAFT, own, "Tiger Shroff", True, tmp_path, kind="explainer", year=2026,
                              subject_hi="टाइगर श्रॉफ")

    photos, rows, cast = run("anchored")
    assert photos[3]["depicts"] == ["मुंबई"] and photos[0]["depicts"] == [match.SUBJECT]
    # Mumbai's beat is a third of this three-beat Short's voice: its map would fill a third of the picture time
    # (match.MAP_SHARE 20%, 2026-10-22), so it is a card over Tiger, never over the map (once rows[1] == [3]).
    assert rows[1]["plate"] == rows[2]["plate"] == match.CARD and rows[1]["views"] == [0]
    assert own[0].get("depicts") is None  # the writer's photos are not changed in place
    _, legacy, _ = run("legacy")
    assert all(r["plate"] == "" and r["views"] for r in legacy)
    assert legacy[2]["views"] != rows[2]["views"] or legacy[2]["plate"] != rows[2]["plate"]


# --- Step 4: desk/writer.py -----------------------------------------------------------------------------------------

def hurt_draft():
    s = short("39553699482")
    return {"title": s.title, "names": s.scene["names"],
            "beats": [{"say": b.text, "photo": 0, "caption": b.card["big"], "label": b.card["small"]}
                      for b in s.beats if b.shot != "outro"]}


def test_explainer_retry_offers_its_subject_as_a_visual_anchor(monkeypatch):
    # Run 40183742922 had eight Sonia photos and one Rajiv photo, but the writer's
    # retry listed only Rajiv. Keep refusing unanchored beats and offer both names.
    subject = {"en": "Sonia Gandhi", "hi": "सोनिया गाँधी", "person": True}
    monkeypatch.setattr(visuals, "showable_rows", lambda *a, **k: [
        {"hi": "राजीव गाँधी", "kind": "person", "alias": [], "map_only": False}])
    draft = {"beats": [{"say": say} for say in [
        "सोनिया गाँधी ने अपनी किताब का वीडियो साझा किया।",
        "राजीव गाँधी से उनकी मुलाकात कैम्ब्रिज में हुई।",
        "उन्होंने पुरानी यादें साझा कीं।",
        "यह एक संस्मरण है।",
        "किताब नवंबर में आएगी।"]]}
    problems = writer.anchorless(draft, subject, True, kind="explainer")
    assert any("beats 3,4,5 name nothing" in p for p in problems)
    assert any("SHOWABLE: सोनिया गाँधी, राजीव गाँधी" in p for p in problems)
    for beat in draft["beats"][2:]:
        beat["say"] = "सोनिया गाँधी ने अपनी किताब की यादें साझा कीं।"
    assert writer.anchorless(draft, subject, True, kind="explainer") == []


def test_card_ceiling_and_showable_retry(monkeypatch, tmp_path):
    """The Tiger Shroff "hurt" Short (39553699482) ended on three beats about the hospitals and the doctors, with no
    picture of them: its own rows are three cards in a row (the ceiling), and the writer is sent back with the
    names that can be shown."""
    def rows(*names):
        return lambda *a, **k: [{"hi": n, "kind": "place", "alias": [], "map_only": False} for n in names]

    monkeypatch.setattr(visuals, "showable_rows", rows("मुम्बई", "जुहू"))
    subject = {"en": "Tiger Shroff", "hi": "टाइगर श्रॉफ", "person": True}
    problems = writer.anchorless(hurt_draft(), subject, True, kind="incident")
    assert problems == ["beats 3,4,5,6 name nothing that can be shown (or only a city or state, whose map a Short "
                        "shows once); SHOWABLE: मुम्बई, जुहू. Name in each beat the person, thing, place or police it "
                        "is about (one of SHOWABLE where the SOURCES allow), so that at most 2 beats are text cards "
                        "and never two in a row."]
    monkeypatch.setattr(visuals, "showable_rows", rows("मुम्बई", "जुहू", "Nanavati Hospital", "KEM Hospital"))
    assert writer.anchorless(hurt_draft(), subject, True, kind="incident") == []  # beat 6 alone is a card
    monkeypatch.setattr(visuals, "showable_rows", rows())
    assert writer.anchorless(hurt_draft(), subject, True, kind="incident") == []  # nothing to name: a rewrite cannot help
    s = short("39553699482")
    rows = [{"views": [0], "plate": match.CARD if k >= 3 else "", "cut_word": "", "card_view": 0} for k in range(6)]
    from dataclasses import replace

    carded = replace(s, beats=[replace(b, plate=r["plate"]) for b, r in zip(s.beats, rows)] + s.beats[6:])
    # Two cards in a row is the ceiling now (match.CARD_RUN 2, once 3), and three of six beats is over a third.
    found = match.problems(carded)
    assert any(p.startswith("text cards: 2 beats in a row from beat 4") for p in found)
    assert "text cards: 3 of 6 beats (at most 2)" in found

    from .test_writer import HI_NAMES, PHOTOS, SOURCE_EN, SOURCE_HI, SUBJECT, FakePen

    calls = []

    def once(draft, subject, india, cache=None, near=None, kind=""):
        calls.append(india)
        return ["beats 3,4,5 name nothing that can be shown; SHOWABLE: वाराणसी"] if len(calls) == 1 else []

    monkeypatch.setattr(writer, "anchorless", once)
    out, log, _ = writer.write("death", SUBJECT, "He", [], SOURCE_EN, SOURCE_HI, PHOTOS, HI_NAMES,
                               log_path=tmp_path / "log.json", pen=FakePen([[]]), india=True)
    assert calls == [True, True] and len(log) == 1 and "SHOWABLE: वाराणसी" in log[0]["problems"][-1]
    calls.clear()
    writer.write("death", SUBJECT, "He", [], SOURCE_EN, SOURCE_HI, PHOTOS, HI_NAMES, log_path=tmp_path / "l.json",
                 pen=FakePen([[]]))
    assert calls == []  # no story region given: no SHOWABLE check


def test_messages_list_years_and_vetted_photos():
    """The writer sees each photo's year and which may not be shown; beat 1 opens on the first that may (Rubio's
    1989 yearbook photo was photo 0 and opened the Short)."""
    photos = short("39714003987").scene["photos"][:3]
    vet = [match.vet_photo(i, photos, [], 2026, True, False) for i in range(3)]
    text = writer._messages("brief", [], "src", "", photos, "रुबियो", {}, vet=vet)[1]["content"]
    assert "0: (1988) A high school yearbook" in text and "(not to be shown: a childhood photo (Yearbook))" in text
    assert "1: (2011) Official portrait" in text
    assert "Beat 1 uses photo 1." in text and "Use every photo at least once" not in text
    assert "each beat names the person, place, thing or police" in text.lower()
    assert "a short may show one map at most" in text.lower()


def test_stale_floor_uses_only_clean_photos():
    """The freshness floor counts only pictures a beat is anchored to: a card's backdrop or a vetted-out photo
    cannot make a Short look fresh."""
    photos = [{"file": f"File:{n}.jpg"} for n in "abcd"]
    photos[3]["vet"] = "a childhood photo (yearbook)"
    seen = {"File:a.jpg", "File:b.jpg"}
    rows = [{"views": [0], "plate": ""}, {"views": [1], "plate": ""}, {"views": [2], "plate": match.CARD},
            {"views": [3], "plate": ""}]
    assert "only 0 of 2 photos" in writer.stale_pictures(photos, rows, seen)
    # Old callers' plain lists: the vetted photo still never counts, the backdrop (no plate known) does.
    assert "only 1 of 3 photos" in writer.stale_pictures(photos, [[0], [1], [2], [3]], seen)
    assert writer.stale_pictures(photos, [{"views": [0], "plate": ""}, {"views": [2], "plate": ""}],
                                 {"File:b.jpg"}) is None


def test_hook_speaker_must_be_said(monkeypatch):
    """"शिंदे: गोली का जवाब गोली से" opened the government Short (39546660530) and nobody says Shinde: the hook goes;
    one whose names the title or beat 1 say stays."""
    s = short("39546660530")
    first = s.beats[0].text
    assert not writer.hook_said(s.scene["hook"], s.title, first, s.scene["names"])
    assert writer.hook_said("टाइगर श्रॉफ को पुलिस सुरक्षा", s.title, first, s.scene["names"])
    assert not writer.hook_said("फडणवीस: दोषी बख्शे नहीं जाएंगे", s.title, first, s.scene["names"])  # said in beat 2
    from .test_writer import SOURCE_EN, draft

    d = draft()
    args = ("kh-x", "explainer", "Ramesh Prasad Verma", "रमेश प्रसाद वर्मा", d, [], [], [], [SOURCE_EN], SOURCE_EN,
            [{"credit": "c", "page": "p"}], ["https://x"], "2026-10-08", False, "news", [], "", "")
    assert writer._short(*args, hook="शिंदे: गोली का जवाब गोली से").scene["hook"] == ""
    assert writer._short(*args, hook="रमेश प्रसाद वर्मा नहीं रहे").scene["hook"] == "रमेश प्रसाद वर्मा नहीं रहे"
    assert "hook" not in writer._short(*args).scene
    assert match.problems(s) and any("hook names शिंदे" in p for p in match.problems(s))
