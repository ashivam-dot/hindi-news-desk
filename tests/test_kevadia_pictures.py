"""The Kevadia Short (xkatu15s0c0, 2026-10-30; owner: "if it is saying kevadia and sardar vallabh bhai patel then
where is the picture of that"): beat 5 said "केवड़िया में वल्लभ भाई पटेल की प्रतिमा पर पुष्पांजलि" over a text card,
because none of its names resolved and quiet mode waived the card ceiling."""
from pathlib import Path

from desk import hindi, match, media, quiet, visuals, wiki
from desk.spec import Short

SYNC = Path(__file__).parent / "fixtures" / "sync"
CAST_FOR = visuals.cast_for  # conftest stubs visuals.cast_for for every test
HUMAN, TOWN, DISTRICT, STATUE, STATION = "Q5", "Q3957", "Q1149652", "Q179700", "Q55488"
INDIA = visuals.INDIA

PAGES = {"Sardar Vallabhbhai Patel": "Vallabhbhai Patel", "Ekta Nagar": "Kevadia",
         "Banaskantha": "Banaskantha district", "Statue of Unity": "Statue of Unity"}
ENTS = {"Vallabhbhai Patel": {"P31": [HUMAN]},
        "Kevadia": {"P31": [TOWN], "P17": [INDIA], "at": (21.88, 73.71)},
        "Banaskantha district": {"P31": [DISTRICT], "P17": [INDIA], "P36": ["Q1"], "at": (24.17, 72.43)},
        "Ekta Nagar railway station": {"P31": [STATION], "P17": [INDIA], "at": (21.89, 73.70)},
        "Statue of Unity": {"P31": [STATUE], "P17": [INDIA], "at": (21.84, 73.72),
                            "descriptions": {"en": {"value": "colossal statue of Vallabhbhai Patel"}}}}
SEARCH = {"Sardar Vallabhbhai Patel": "Vallabhbhai Patel", "Ekta Nagar": "Ekta Nagar railway station",
          "Banaskantha": "Banaskantha district", "Statue of Vallabhbhai Patel": "Statue of Unity"}


def wikipedia(monkeypatch):
    monkeypatch.setattr(wiki, "claims", lambda ent, pid: [{"value": v} for v in (ent or {}).get(pid, [])])
    monkeypatch.setattr(wiki, "coords", lambda ent: (ent or {}).get("at"))
    monkeypatch.setattr(wiki, "search", lambda q: SEARCH.get(q))
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"qid": PAGES.get(t, t), "title": PAGES.get(t, t)}
                                                           for t in titles if PAGES.get(t, t) in ENTS})
    monkeypatch.setattr(wiki, "entities", lambda qids: {q: ENTS[q] for q in qids if q in ENTS})
    monkeypatch.setattr(media, "place_like", lambda ent: bool(ent.get("at")) and STATUE not in ent.get("P31", []))


def test_exact_title_finds_honorific_renamed_place_and_district(monkeypatch):
    wikipedia(monkeypatch)
    assert visuals.resolve("Sardar Vallabhbhai Patel", True)[1] == "Vallabhbhai Patel"
    assert visuals.resolve("Ekta Nagar", True)[1] == "Kevadia"  # never its railway station
    assert visuals.resolve("Banaskantha", True)[1] == "Banaskantha district"


def test_person_ki_pratima_is_the_statue(monkeypatch):
    wikipedia(monkeypatch)

    def thing(en):
        return (en, en, ENTS[en]) if en == "Statue of Unity" else None

    draft = {"names": [{"hi": "केवड़िया", "en": "Ekta Nagar"}, {"hi": "वल्लभ भाई पटेल", "en": "Sardar Vallabhbhai Patel"}],
             "beats": [{"say": "केवड़िया में वल्लभ भाई पटेल की प्रतिमा पर पुष्पांजलि अर्पित की जाएगी।"}]}
    cast = CAST_FOR(draft, "Narendra Modi", True, thing_resolver=thing)
    assert [(c["en"], c["kind"]) for c in cast] == [("Ekta Nagar", "place"), ("Sardar Vallabhbhai Patel", "person"),
                                                    ("Statue of Unity", "thing")]
    assert cast[2]["statue"] and cast[2]["hi"] == "प्रतिमा"
    say = draft["beats"][0]["say"]
    assert [c["en"] for c in visuals.mentions(say, cast)] == ["Ekta Nagar", "Sardar Vallabhbhai Patel",
                                                              "Statue of Unity"]


def test_named_with_a_photo_and_never_shown_refuses_even_when_quiet(monkeypatch):
    s = Short.load(SYNC / "39546660530.json")
    photos, cast = s.scene["photos"], match.cast_of(s)
    who = hindi.norm("देवेंद्र फडणवीस")
    his = {i for i, p in enumerate(photos) if who in match.depicts(i, p, cast)}
    assert his
    beats = [b if not set(match.shot_photos(b.shot)) & his else type(b)(**{**b.__dict__, "plate": match.CARD})
             for b in s.beats]
    bad = [p for p in match.problems(type(s)(**{**s.__dict__, "beats": beats})) if "never shows it" in p]
    assert bad and who in bad[0]
    monkeypatch.setenv("DESK_QUIET", "on")
    quiet.reset()
    assert quiet.keep(bad) == bad
