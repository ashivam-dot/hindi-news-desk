"""Real pictures (2026-10-22). The owner on CAPraPdXvns (run 39725154704, "प्रियंका वाड्रा के बेटे रेहान की तस्वीरें
हटीं"): the map of New Delhi or Bikaner House under four of five beats, no tricolour while the voice said "तिरंगे",
and no photo of Raihan, whom the Short was about. Things a beat names get their own photo (desk/things.py), a map is
rare (one view a Short, only under a beat whose point is where), cards at most a third, and a Short whose subject
has no photo is refused before it is rendered, for good. Offline: wiki and media are faked."""
from dataclasses import replace

import pytest

from desk import cli, config, gate, hindi, match, things, visuals, wiki, writer

from .test_match import short

CAP = "39725154704"
CAST_FOR = visuals.cast_for  # conftest replaces visuals.cast_for with an offline stub; this is the real one
FLAG = next(e for e in things.LEXICON if e["en"] == "Flag of India")
HEADLINES = ["Priyanka Gandhi's son Raihan alleges Bikaner House pulled down his protest pics ahead of exhibition",
             "'Not A Democracy': Priyanka Gandhi's Son Says Bikaner House Pulled Down His Delhi Protest Photos",
             "Controversy erupts after ‘protest’ photographs by Priyanka Gandhi’s son allegedly get removed from "
             "Bikaner House exhibition",
             "Curtailing art is wrong: Priyanka Gandhi's son on protest photos being removed"]


def claim(value):
    return {"mainsnak": {"datavalue": {"value": value}}}


def spoken(s):
    return [{"say": b.text, "card": b.card or {}} for b in s.beats if b.shot != "outro"]


# --- Things a beat names --------------------------------------------------------------------------------------------

def test_the_tricolour_beat_names_the_flag_of_india():
    beats = spoken(short(CAP))
    assert [h["en"] for h in things.lexicon_hits(beats, True)] == ["Flag of India"]
    assert [k for k, b in enumerate(beats) if things.said_at(b["say"], FLAG["forms"]) >= 0] == [2]  # "तिरंगे की"
    hit = things.lexicon_hits(beats, True)[0]
    assert hit["kind"] == "thing" and hit["hi"] == "तिरंगा" and "तिरंगे" in hit["alias"] and len(hit["files"]) == 4


def test_lexicon_words_match_whole_words_in_every_listed_form_and_never_abroad():
    forms = things.LEXICON[1]["forms"]  # संसद
    assert things.said_at("संसद में आज बहस हुई", forms) == 0
    assert things.said_at("ब्रिटेन की संसद में बहस हुई", forms) == -1  # Westminster, not Parliament House
    court = next(e for e in things.LEXICON if e["en"] == "Supreme Court of India")["forms"]
    assert things.said_at("अमेरिका के सुप्रीम कोर्ट ने फैसला दिया", court) == -1
    assert things.said_at("अमेरिकी सुप्रीम कोर्ट ने फैसला दिया", court) == -1
    assert things.said_at("सुप्रीम कोर्ट ने फैसला दिया", court) == 0
    tiger = next(e for e in things.LEXICON if e["en"] == "Bengal tiger")["forms"]
    assert things.said_at("बाघा बॉर्डर पर परेड हुई", tiger) == -1  # a whole word, never inside another
    assert things.said_at("जंगल में दो बाघों को देखा गया", tiger) > 0  # an inflection the lexicon lists
    assert things.said_at("घर पर तिरंगों की कतार", FLAG["forms"]) > 0
    # India-only things only in an Indian story; the tricolour in any.
    assert [h["en"] for h in things.lexicon_hits([{"say": "संसद में तिरंगा फहराया गया"}], False)] == ["Flag of India"]
    assert [h["en"] for h in things.lexicon_hits([{"say": "संसद में तिरंगा फहराया गया"}], True)] == [
        "Flag of India", "Parliament House, New Delhi"]


def test_a_thing_is_never_a_work_a_logo_or_a_body():
    def ent(desc, p31="Q1"):
        return {"descriptions": {"en": {"value": desc}}, "claims": {"P31": [claim({"id": p31})]}}

    assert things.thing_like(ent("aircraft carrier of the Indian Navy"))
    assert things.thing_like(ent("subspecies of tiger"))
    assert not things.thing_like(ent("2014 Indian Hindi-language action film about a ship"))
    assert not things.thing_like(ent("Indian multinational conglomerate company"))
    assert not things.thing_like(ent("political party in India"))
    assert not things.thing_like(ent("Indian actor", wiki.HUMAN))
    assert things.NOT_THING.search("File:Vande Bharat poster.jpg") and things.NOT_THING.search("Company logo")
    assert not things.NOT_THING.search("File:Flag of India, New Delhi.jpg")


def test_the_cast_takes_the_tricolour_from_the_beats(monkeypatch):
    s = short(CAP)
    draft = {"names": s.scene["names"], "beats": spoken(s)}
    looked = []

    def lookup(e):
        looked.append(e["en"])
        return e | {"qid": "Q80015", "title": e["en"], "ent": {"claims": {"P18": [claim("Flag of India.svg")]}}}

    cast = CAST_FOR(draft, "Priyanka Gandhi", True, resolver=lambda *a, **k: None,
                    thing_resolver=lambda en: None, thing_lookup=lookup)
    assert [(c["en"], c["kind"]) for c in cast] == [("Flag of India", "thing")] and looked == ["Flag of India"]
    # Its Wikidata image is a drawing (an SVG), so the editor's checked photos are what show it.
    assert things.has_picture(cast[0]) and not things.has_picture(cast[0] | {"files": []})
    # A failed lookup keeps an entry with editor's files, and drops one without.
    assert [c["en"] for c in CAST_FOR(draft, "", True, resolver=lambda *a, **k: None, thing_resolver=lambda en: None,
                                      thing_lookup=lambda e: None)] == ["Flag of India"]
    tiger = {"names": [], "beats": [{"say": "जंगल में बाघ दिखा"}]}
    assert CAST_FOR(tiger, "", True, resolver=lambda *a, **k: None, thing_resolver=lambda en: None,
                    thing_lookup=lambda e: None) == []


# --- Maps are rare, things are shown ----------------------------------------------------------------------------------

def cap_plan(flag: bool = True):
    """CAPraPdXvns's own pool and cast through match.plan, as visuals.direct stamps them, with (flag) the
    tricolour's photo things.photos would add today."""
    s = short(CAP)
    photos = [dict(p) for p in s.scene["photos"]]
    cast = match.cast_of(s)
    subject = [0, 1]
    for i in subject:
        photos[i]["depicts"] = [match.SUBJECT]
    if flag:
        row = {"en": "Flag of India", "hi": "तिरंगा", "kind": "thing", "alias": list(FLAG["forms"][1:]),
               "photos": [len(photos)]}
        photos.append({"file": "File:Flag of India, New Delhi.jpg", "role": "thing", "who": "तिरंगा",
                       "depicts": [match.key(row)], "license": "CC BY-SA 4.0", "credit": "Yann Forget", "page": "p"})
        cast.append(row)
    rows = match.plan(spoken(s), photos, cast, subject, s.kind, match.spellings_of(s), True, s.scene["names"])
    return s, photos, cast, rows


def test_the_tricolour_beat_shows_the_flag_and_the_short_shows_one_map_at_most():
    s, photos, cast, rows = cap_plan()
    flag = len(photos) - 1
    assert rows[2]["views"] == [flag] and rows[2]["plate"] == ""  # "रेहान ने तिरंगे की तस्वीरें ...": the flag
    shown = [i for r in rows if r["plate"] != match.CARD for i in r["views"]]
    assert sum(visuals.is_map(photos[i]) for i in shown) <= match.MAX_MAP_VIEWS
    # The original: maps under four of five beats (seven map views counted by shot), under "तिरंगे" too.
    bad = match.problems(s)
    assert "pictures: 5 map views (at most 1)" in bad and any(p.startswith("pictures: maps fill") for p in bad)
    assert 2 in [i for i in match.shot_photos(s.beats[2].shot)]  # New Delhi's map under the tricolour beat
    # Without the flag's photo that beat names nothing with a picture: a card, never New Delhi's map.
    _, photos2, _, rows2 = cap_plan(flag=False)
    assert rows2[2]["plate"] == match.CARD and not visuals.is_map(photos2[rows2[2]["views"][0]])


def test_a_map_under_a_beat_naming_a_pictured_thing_is_a_problem():
    s, photos, cast, _ = cap_plan()
    scene = s.scene | {"photos": photos, "cast": [{k: v for k, v in c.items()} for c in cast]}
    beats = [replace(b, shot="photo:2") if k == 2 else b for k, b in enumerate(s.beats)]
    found = match.problems(replace(s, beats=beats, scene=scene))
    assert f"pictures: beat 3 shows a map though it names {match.key({'hi': 'तिरंगा'})}, who has a photo" in found


def test_the_card_ceiling_is_a_third_and_one_in_any_short():
    assert [match.card_limit(n) for n in (1, 3, 5, 6, 7, 9)] == [1, 1, 1, 2, 2, 3]
    assert match.CARD_RUN == 2 and match.MAP_SHARE == 0.2 and match.MAX_MAP_VIEWS == 1


def test_real_photos_must_fill_half_the_short():
    s = short("39708703684")  # Jantar Mantar: four of six beats name nothing showable
    from .test_match import applied, planned

    rows, _ = planned(s)
    assert "pictures: real photos fill only 33% of the Short (want at least 50%)" in match.problems(applied(s, rows))


def test_map_views_count_a_held_map_once():
    s = short(CAP)
    views = [{"start": 0, "end": 2, "photo": 0, "beat_k": 0}, {"start": 2, "end": 4, "photo": 2, "beat_k": 0},
             {"start": 4, "end": 6, "photo": 2, "beat_k": 1}, {"start": 6, "end": 8, "photo": 3, "beat_k": 1},
             {"start": 8, "end": 9, "photo": 4, "beat_k": 2, "plate": match.CARD}]
    assert match._map_views(s, views) == 1  # New Delhi's map held across the cut; a card's backdrop not counted
    assert match._map_views(s, views + [{"start": 9, "end": 10, "photo": 5, "beat_k": 3}]) == 2


# --- A Short whose subject cannot be shown is not made ------------------------------------------------------------------

def test_the_story_is_about_a_relative():
    assert writer.relative_story("Priyanka Gandhi", HEADLINES) == ("son", ["Bikaner", "Raihan", "Says"])
    assert writer.relative_story("Priyanka Gandhi", HEADLINES[:1] + ["Priyanka Gandhi attacks the government"] * 3) \
        is None  # one headline of four: a story about her
    assert writer.relative_story("Priyanka Gandhi", ["Priyanka Gandhi meets farmers in Wayanad"]) is None


def gandhi(children_p18=()):
    """Priyanka Gandhi (Q607685) and her children on Wikidata: Raihan (Q101533820) and Miraya, no image."""
    me = {"labels": {"en": {"value": "Priyanka Gandhi"}}, "claims": {"P40": [claim({"id": "Q101533820"}),
                                                                             claim({"id": "Q2"})]}}
    raihan = {"labels": {"en": {"value": "Raihan Vadra"}}, "claims": {}}
    if children_p18:
        raihan["claims"]["P18"] = [claim(f) for f in children_p18]
    kids = {"Q101533820": raihan, "Q2": {"labels": {"en": {"value": "Miraya Vadra"}}, "claims": {}}}
    return me, kids


def test_a_relatives_story_with_no_photo_of_them_is_refused_before_writing(monkeypatch):
    cand = {"story": HEADLINES[3], "headlines": HEADLINES}
    me, kids = gandhi()
    monkeypatch.setattr(wiki, "entities", lambda qids: {q: kids[q] for q in qids})
    why = writer.relative_faceless(cand, "Priyanka Gandhi", me)
    assert why.startswith("faceless: the story is about Priyanka Gandhi's son Raihan Vadra") and "not retried" in why
    me, kids = gandhi(["Raihan Vadra 2024.jpg"])
    assert writer.relative_faceless(cand, "Priyanka Gandhi", me) is None  # a photo: the Short may be made
    me, kids = gandhi(["Raihan Vadra signature.svg"])
    assert writer.relative_faceless(cand, "Priyanka Gandhi", me).startswith("faceless:")  # a drawing is no photo

    def down(qids):
        raise ConnectionError("offline")

    monkeypatch.setattr(wiki, "entities", down)
    assert writer.relative_faceless(cand, "Priyanka Gandhi", me) is None  # unread is not faceless


def test_build_explainer_refuses_before_any_reporting_or_writing(monkeypatch):
    me, kids = gandhi()
    monkeypatch.setattr(config, "EXPLAINERS", True)
    monkeypatch.setattr(wiki, "entities", lambda qids: {q: (me if q == "Q607685" else kids[q]) for q in qids})
    monkeypatch.setattr(wiki, "common_hindi", lambda ent: "प्रियंका गांधी")
    monkeypatch.setattr(writer, "_reporting", lambda *a, **k: pytest.fail("reported a faceless story"))
    monkeypatch.setattr(writer, "write", lambda *a, **k: pytest.fail("wrote a faceless story"))
    cand = {"id": "nw-20261021-priyanka-gandhi-protest", "category": "politics", "qid": "Q607685",
            "title": "Priyanka Gandhi", "person": True, "phrase": "Priyanka Gandhi", "story": HEADLINES[3],
            "headlines": HEADLINES}
    with pytest.raises(ValueError, match="^faceless: the story is about Priyanka Gandhi's son Raihan Vadra"):
        writer.build_explainer(cand)


def stamped(s):
    photos = [dict(p) for p in s.scene["photos"]]
    for i, p in enumerate(photos):
        p["depicts"] = [match.SUBJECT] if not p.get("role") else sorted(match.depicts(i, p, s.scene["cast"]))
    return photos


def test_a_written_short_about_someone_with_no_photo_is_refused_at_prepare():
    s = short(CAP)
    photos = stamped(s)
    why = writer.faceless(s.title, photos, s.scene["cast"], s.scene["name_hi"], True, s.scene["names"])
    assert why == "faceless: the title is about रेहान, and no free photo of them was found (skipped, not retried)"
    # With a vetted photo of Raihan in the cast, the Short may be made.
    raihan = {"en": "Raihan Vadra", "hi": "रेहान", "kind": "person", "photos": [len(photos)]}
    ok = photos + [{"file": "File:Raihan Vadra.jpg", "role": "person", "who": "रेहान", "depicts": [match.key(raihan)]}]
    assert writer.faceless(s.title, ok, s.scene["cast"] + [raihan], s.scene["name_hi"], True, s.scene["names"]) is None
    # Its own subject vetted out: refused too.
    gone = [p | {"vet": "a childhood photo"} if not p.get("role") else p for p in photos]
    assert writer.faceless("x", gone, [], "प्रियंका वाड्रा", True).startswith("faceless: no photo of प्रियंका वाड्रा")
    # "भाई दूज" after a kinship word is a festival, not a name the script lists.
    assert writer.faceless("बहन भाई दूज पर घर आईं", photos, [], s.scene["name_hi"], True, s.scene["names"]) is None
    # The gate reads the same off the saved Short (stamped photos only; an older artifact is not judged).
    assert gate.richness(s) == []
    assert gate.richness(replace(s, scene=s.scene | {"photos": photos})) == [why]
    assert why in gate.said_is_shown(replace(s, scene=s.scene | {"photos": photos}))


def test_a_faceless_story_is_skipped_never_retried():
    assert not cli.retryable("faceless: the title is about रेहान, and no free photo of them was found")
    assert not cli.retryable("gate: pictures: maps fill 40%; faceless: the title is about रेहान")
    assert cli.retryable("gate: pictures: 2 map views (at most 1)")
    assert cli.retryable("gate: text cards: 3 of 6 beats (at most 2)")
    assert not cli.retryable("gate: the story is too old")


# --- The writer is told ------------------------------------------------------------------------------------------------

def rows_of(*rows):
    """showable_rows as visuals gives them: a lexicon thing with its inflected forms (alias)."""
    return lambda *a, **k: [{"hi": hi, "kind": kind, "alias": list(FLAG["forms"][1:]) if hi == "तिरंगा" else [],
                             "map_only": m} for hi, kind, m in rows]


def test_the_writer_is_sent_back_for_a_second_map_beat(monkeypatch):
    subject = {"en": "Tiger Shroff", "hi": "टाइगर श्रॉफ", "person": True}
    monkeypatch.setattr(visuals, "showable_rows", rows_of(("मुम्बई", "place", True), ("तिरंगा", "thing", False)))

    def draft(*says):
        return {"beats": [{"say": s} for s in says]}

    tiger, mumbai = "टाइगर श्रॉफ ने बयान दिया।", "यह मुम्बई में हुआ।"
    assert writer.anchorless(draft(tiger, mumbai, tiger, mumbai, tiger, tiger), subject, True) == []  # one card
    sent = writer.anchorless(draft(tiger, mumbai, mumbai, mumbai, tiger, tiger), subject, True)
    assert sent and sent[0].startswith("beats 3,4 name nothing that can be shown (or only a city or state")
    assert "things with photos: तिरंगा" in sent[0] and "never two in a row" in sent[0]
    # The thing in its inflected forms (the lexicon's, which showable_rows carries) is a beat with a picture.
    assert writer.anchorless(draft(tiger, mumbai, "तिरंगे लहराए गए।", "तिरंगों से घर सजे।", tiger, tiger), subject,
                             True) == []
