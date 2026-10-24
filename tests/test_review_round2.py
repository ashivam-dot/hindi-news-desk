"""Real pictures, review round 2 (2026-10-23): the viewer verdicts on dry run 39871573344 (Neha Bora) and the
reviewers' findings. Maps in the opening flash and the flash missing from render.json, a lecture photo passing as
the Delhi High Court, one still held 11.7 s over a babbling preview voice, six tries for a post-render picture
refusal, the "दोनों" pair under accused and countries lines, foreign cities and film/train/metro names in the
lexicon, faceless refusals of firms and of names never looked up, the legacy rollback, and state or foreign
ministers' titles read as the subject's. Offline throughout."""
import json
from dataclasses import replace

import pytest

from desk import align, cli, compose, config, gate, ledger, match, plan, things, visuals, voice, writer

from .test_match import SYNC, applied, planned, short
from .test_real_pictures import CAST_FOR

NEHA = "39871573344"  # dry run: "नेहा बोरा ने दिल्ली हाई कोर्ट में सरकार बदलने को सही बताया।"
TUSK = "39860680187"  # dry run: Donald Tusk and Narendra Modi, then "दोनों नेताओं ने ..."
SHAH = "39794659993"  # dry run: Amit Shah and Rahul Gandhi


def neha_views():
    return json.loads((SYNC / "views" / f"{NEHA}.json").read_text(encoding="utf-8"))


def hits(say: str, india: bool = True) -> list[str]:
    return [h["en"] for h in things.lexicon_hits([{"say": say}], india)]


# --- 1: the opening flash shows no map, one picture per look, and is in render.json ------------------------------

def test_the_flash_never_shows_a_map_and_is_recorded_as_views():
    s = short(NEHA)
    photos = s.scene["photos"]
    seen = [{"photo": 0, "start": 0.0, "end": 1.2, "beat_k": 0}, {"photo": 3, "start": 1.2, "end": 4.8, "beat_k": 0},
            {"photo": 1, "start": 4.8, "end": 9.0, "beat_k": 1}]
    # The run flashed Neha's photos 1 and 2 (one look) and the two High Court maps (4, 5) under "नेहा बोरा ने";
    # without them only photos 1 and 3 are left, too few for a flash.
    assert compose.burst(seen, photos, match.cast_of(s)) == []
    more = photos + [{"role": None, "file": "File:Neha Bora 2.jpg"}, {"role": None, "file": "File:Neha Bora 3.jpg"}]
    flash = compose.burst(seen, more, match.cast_of(s))
    # In the order they come, then the pool; never photo 1, beat 1's (Matlabnama audit R4, 2026-10-23: one picture,
    # one beat; it was [3, 1, 8, 9]).
    assert flash == [3, 8, 9]
    assert not any(visuals.is_map(more[i]) for i in flash) and 2 not in flash
    rec = compose.view_record(seen, [1, 3, 6])
    assert [v["photo"] for v in rec[:3]] == [1, 3, 6] and all(v["burst"] for v in rec[:3])
    assert rec[3]["photo"] == 0 and rec[3]["start"] == pytest.approx(3 * compose.BURST_STEP)
    assert not any(v.get("burst") for v in rec[3:])


def test_the_gate_counts_a_flashed_map_and_an_unsaid_flash():
    s = short(NEHA)
    views = neha_views()["views"]
    flashed = [{"start": 0.0, "end": 0.18, "photo": 4, "beat_k": 0, "plate": "", "burst": True},
               {"start": 0.18, "end": 0.36, "photo": 5, "beat_k": 0, "plate": "", "burst": True}]
    views = flashed + [v | {"start": max(v["start"], 0.36)} for v in views]
    out = match.problems(s, views)
    assert any("map views" in p for p in out), out  # the two flashed maps and the one under beat 6
    # Beat 1's lead picture is still Neha (main), not the flash: no pair or pronoun state from it.
    assert not any("beat 1 shows photo 0" in p for p in out)


def test_a_burst_view_is_not_a_chip_overrun():
    views = [{"start": 0.0, "end": 0.18, "photo": 5, "beat_k": 0, "plate": "", "burst": True},
             {"start": 0.18, "end": 4.0, "photo": 0, "beat_k": 0, "plate": "", "chip": [0.18, 3.18]}]
    assert match._chip_overrun(1, 0, 0, views, [{}] * 6, True) == []


# --- 2: a place's photo of people at it is no picture of the place -------------------------------------------------

def test_a_lecture_at_the_high_court_is_vetted_out():
    s = short(NEHA)
    photos, cast = s.scene["photos"], match.cast_of(s)
    assert photos[3]["file"] == "File:Delhi HC.jpg"
    assert "people at the place" in match.vet(3, photos, s, cast)
    plain = dict(photos[3], file="File:Supreme Court of India building.jpg", description="The Supreme Court building",
                 categories="Supreme Court of India")
    assert match.vet(3, [*photos[:3], plain, *photos[4:]], s, cast) == ""


# --- 3: no still held past HOLD_MAX; no babble in a take --------------------------------------------------------

def test_the_117_second_hold_is_refused_and_a_twin_cuts_it():
    s = short(NEHA)
    views = neha_views()["views"]
    held = match.longest_hold(views)
    assert held[1] == 1 and held[0] == pytest.approx(11.66, abs=0.05)
    assert any("stays up 11.7 s" in p for p in match.problems(s, views))
    seen = [dict(v) for v in views]
    compose.twins(seen, s.scene["photos"], match.cast_of(s))
    # Photo 2 is photo 1 uncropped (one look); the twin was Neha's other portrait, photo 0. But photo 0 is beats 0's
    # and 4's (R4, 2026-10-23: one picture, one beat): no twin is left, and the hold is refused, never padded.
    assert {v["photo"] for v in seen if v["beat_k"] == 3} == {1}
    assert any("stays up" in p for p in match.problems(s, seen))
    # A portrait no other beat shows is the twin.
    photos = s.scene["photos"] + [{k: v for k, v in s.scene["photos"][0].items() if k != "look"}
                                  | {"file": "File:Neha Bora 2.jpg"}]
    seen = [dict(v) for v in views]
    compose.twins(seen, photos, match.cast_of(s))
    assert match.longest_hold(seen)[0] <= match.HOLD_MAX
    assert {v["photo"] for v in seen if v["beat_k"] == 3} == {1, len(photos) - 1}


def test_one_view_past_the_ceiling_is_split_with_its_twin():
    # Dry run 39508637683's replay: one Tiger Shroff photo held 10.5 s by itself after a closer cut.
    photos = [{"role": None, "depicts": [match.SUBJECT]}, {"role": None}, {"role": None}]
    seen = [{"start": 0.0, "end": 4.0, "photo": 2, "beat_k": 0}, {"start": 4.0, "end": 26.0, "photo": 2, "beat_k": 0}]
    compose.twins(seen, photos)
    assert match.longest_hold(seen)[0] <= match.HOLD_MAX
    assert [v["photo"] for v in seen] == [2, 0, 2, 0] and seen[-1]["end"] == 26.0
    alone = [{"start": 0.0, "end": 12.0, "photo": 1, "beat_k": 0}]
    compose.twins(alone, photos)
    assert [(v["photo"], v["start"], v["end"]) for v in alone] == [(1, 0.0, 6.0), (0, 6.0, 12.0)]


def test_a_hold_with_no_twin_stays_and_a_card_breaks_a_hold():
    photos = [{"role": "map", "who": "x"}]
    views = [{"start": 0.0, "end": 6.0, "photo": 0, "beat_k": 0}, {"start": 6.0, "end": 12.0, "photo": 0, "beat_k": 1}]
    assert compose.twins([dict(v) for v in views], photos)[1]["photo"] == 0
    assert match.longest_hold(views)[0] == 12.0
    carded = [views[0], views[1] | {"plate": match.CARD}, {"start": 12.0, "end": 18.0, "photo": 0, "beat_k": 2}]
    assert match.longest_hold(carded)[0] == 6.0


def test_stray_measures_babble_after_the_last_word_and_inside():
    words = [{"text": "नेहा", "start": 0.1, "end": 0.5}, {"text": "बोरा", "start": 0.55, "end": 0.9}]
    assert align.stray(words, 1.0) <= align.MAX_STRAY
    assert align.stray(words, 9.0) == pytest.approx(8.1)  # the 39871573344 beat-4 tail
    gap = words[:1] + [{"text": "बोरा", "start": 3.5, "end": 3.9}]
    assert align.stray(gap, 4.0) > align.MAX_STRAY
    unheard = words[:1] + [{"text": "दिल्ली", "start": 0.5, "end": 2.4, "heard": False}, words[1] | {"start": 2.4,
                                                                                                     "end": 2.8}]
    need = len(align.letters("दिल्ली")) * align.SECONDS_PER_LETTER
    assert align.stray(unheard, 2.9) == pytest.approx(1.9 - need, abs=0.01)


def test_the_saved_preview_timings_had_long_tails():
    t = neha_views()["timing"]
    a, e = t["beats"][3]
    mine = [w for w in t["words"] if w["beat"] == 3]
    assert e - mine[-1]["end"] > 5  # 8 s with no caption: the take the voice now trims or retakes


def test_a_chatterbox_tail_is_cut_and_a_gap_is_retaken(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf

    base = short(NEHA)
    s = replace(base, beats=[replace(base.beats[0], text="नेहा बोरा", pause_after=0.0)])
    rate = voice.SAMPLE_RATE
    calls = {"n": 0}

    def fake_chatterbox(lines, out, style, seed, ref):
        out.mkdir(parents=True, exist_ok=True)
        f = out / f"{seed}.wav"
        sf.write(f, (0.3 * np.ones(int(6.0 * rate))).astype(np.float32), rate)
        return [{"file": str(f)} for _ in lines]

    def fake_listen(clip, tokens):
        calls["n"] += 1
        if calls["n"] == 1:  # a gap of 3 s inside: retaken
            return ([{"text": "नेहा", "start": 0.1, "end": 0.5}, {"text": "बोरा", "start": 3.5, "end": 3.9}],
                    [1.0], [], None)
        return [{"text": "नेहा", "start": 0.1, "end": 0.5}, {"text": "बोरा", "start": 0.6, "end": 1.0}], [1.0], [], None

    monkeypatch.setattr(voice, "_chatterbox", fake_chatterbox)
    monkeypatch.setattr(voice, "_listen", fake_listen)
    monkeypatch.setattr(voice, "_bounds", lambda a: (0, len(a)))
    timing = voice._chatterbox_story(s, tmp_path, None)
    assert calls["n"] == 2
    clip = sf.info(str(tmp_path / "beat00.wav")).duration
    assert clip == pytest.approx(1.0 + voice.TAIL_KEEP, abs=0.01)  # 6 s take, cut after its last word
    assert timing["duration"] < 3


def test_a_take_that_always_babbles_inside_is_rejected(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf

    base = short(NEHA)
    s = replace(base, beats=[replace(base.beats[0], text="नेहा बोरा", pause_after=0.0)])
    rate = voice.SAMPLE_RATE

    def fake_chatterbox(lines, out, style, seed, ref):
        out.mkdir(parents=True, exist_ok=True)
        f = out / f"{seed}.wav"
        sf.write(f, (0.3 * np.ones(int(5.0 * rate))).astype(np.float32), rate)
        return [{"file": str(f)} for _ in lines]

    monkeypatch.setattr(voice, "_chatterbox", fake_chatterbox)
    monkeypatch.setattr(voice, "_listen", lambda clip, tokens: (
        [{"text": "नेहा", "start": 0.1, "end": 0.5}, {"text": "बोरा", "start": 3.5, "end": 3.9}], [1.0], [], None))
    monkeypatch.setattr(voice, "_bounds", lambda a: (0, len(a)))
    with pytest.raises(voice.TakeRejected, match="came out garbled"):
        voice._chatterbox_story(s, tmp_path, None)
    assert cli.retryable("voice: beat 1 came out garbled (3.0 s with none of its words)")


# --- 4: a post-render picture refusal gets PICTURE_TRIES, not six ---------------------------------------------------

@pytest.fixture
def live(monkeypatch, tmp_path):
    from desk import learn, review

    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(cli, "WORK", tmp_path / "work")
    monkeypatch.setattr(config, "CHANNEL_ID", "UC" + "a" * 22)
    monkeypatch.setattr(config, "UNTAG", False)
    monkeypatch.setattr(config, "CHANNEL_JOBS", ())
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(learn, "refresh", lambda: None)
    monkeypatch.setattr(review, "daily", lambda: None)
    monkeypatch.setattr(cli, "retire_listed", lambda health: None)
    monkeypatch.setattr(cli, "retitle_listed", lambda health: None)
    monkeypatch.setattr(cli, "_advisory", lambda health, dry: None)
    cand = {"id": "kh-test", "kind": "", "title": "t"}
    monkeypatch.setattr(plan, "watch", lambda save=True: {"candidates": [cand], "trending": [cand], "notes": []})
    monkeypatch.setattr(plan, "lineup", lambda c, at=None: ([cand], []))
    monkeypatch.setattr(plan, "ad_note", lambda c: None)
    monkeypatch.setattr(gate, "channel_mix", lambda recent, loss: None)
    monkeypatch.setattr(cli, "prepare", lambda c: short(NEHA))
    calls = []
    monkeypatch.setattr(ledger, "retry", lambda i, r, limit=6: calls.append(("retry", r[:20], limit)) or True)
    monkeypatch.setattr(ledger, "skip", lambda i, r: calls.append(("skip", r[:20], None)))
    return calls


def test_a_post_render_picture_refusal_is_retried_picture_tries(live, monkeypatch):
    def make(cand, s, preview=False):
        raise ValueError("gate: pictures: photo 1 (x) stays up 11.7 s in a row from 11.7 s (at most 10 s)")

    monkeypatch.setattr(cli, "make", make)
    cli.run()
    assert live == [("retry", "gate: pictures: phot", cli.PICTURE_TRIES)]


def test_a_rejected_take_keeps_six_tries_and_legacy_keeps_six(live, monkeypatch):
    def make(cand, s, preview=False):
        raise voice.TakeRejected("voice: beat 2 came out garbled (40% of its letters heard)")

    monkeypatch.setattr(cli, "make", make)
    cli.run()
    assert live == [("retry", "TakeRejected: voice:", 6)]
    monkeypatch.setattr(config, "MATCHER", "legacy")
    assert cli.retry_limit("gate: pictures: beat 2 shows photo 3") == 6


# --- 5/8: "दोनों" is the pair only for people ------------------------------------------------------------------

@pytest.mark.parametrize("line", ["दोनों आरोपियों को पुलिस ने गिरफ्तार कर लिया।", "दोनों देशों के बीच तनाव बढ़ा।",
                                  "दोनों हमलावर मौके से फरार हो गए।", "हमले में दोनों बच्चों की मौत हो गई।",
                                  "दोनों घायलों को अस्पताल ले जाया गया।", "दोनों विमान सुरक्षित उतरे।"])
def test_both_under_the_accused_countries_injured_or_dead_is_no_pair(line):
    assert match.pair_at(line) < 0
    s = short(TUSK)
    beats = list(s.beats)
    beats[2] = replace(beats[2], text=line)
    t = replace(s, beats=beats)
    rows, photos = planned(t)
    people = {i for i, p in enumerate(photos) if not visuals.is_map(p) and p.get("role") in (None, "person")}
    assert rows[2]["plate"] == match.CARD or not set(rows[2]["views"]) & people
    assert not [p for p in match.problems(applied(t, rows)) if "beat 3 " in p]


@pytest.mark.parametrize("line", ["रिपोर्टों के मुताबिक, दोनों नेताओं ने रक्षा सहयोग पर बात की।",
                                  "दोनों ने रक्षा सहयोग पर बात की।", "दोनों के बीच व्यापार पर चर्चा हुई।",
                                  "दोनों ही नेता मुस्कुराए।"])
def test_both_for_two_people_is_still_the_pair(line):
    assert match.pair_at(line) >= 0


# --- 6: the lexicon abroad and in names -------------------------------------------------------------------------

@pytest.mark.parametrize("say", ["ढाका में सुप्रीम कोर्ट ने शेख हसीना को सजा सुनाई",
                                 "इस्लामाबाद में शीर्ष अदालत ने याचिका खारिज की",
                                 "लंदन में संसद के बाहर भारतीयों ने प्रदर्शन किया",
                                 "काठमांडू में संसद भवन में आग लगा दी गई", "वॉशिंगटन में संसद ने बिल पास किया",
                                 "शेख हसीना ने ढाका में राष्ट्रीय ध्वज फहराया", "पाक संसद में हंगामा",
                                 "फिल्म तिरंगा के गाने पर विवाद", "लाल किला मेट्रो स्टेशन के पास धमाका",
                                 "बाघ एक्सप्रेस रद्द कर दी गई"])
def test_the_lexicon_takes_no_foreign_city_film_train_or_station(say):
    assert hits(say) == []


@pytest.mark.parametrize("say,en", [("संसद में बिल पास हुआ", "Parliament House"), ("तिरंगा यात्रा निकली", "Flag of India"),
                                    ("लाल किले पर झंडा फहराया गया", "Red Fort")])
def test_the_lexicon_still_takes_the_indian_things(say, en):
    got = hits(say)
    assert any(en.split()[0] in h for h in got), got


# --- 7/11: faceless only for a name looked up and not found ------------------------------------------------------

SUBJECT_PHOTO = [{"depicts": [match.SUBJECT]}]


@pytest.mark.parametrize("en,hi,fate", [("Air India", "एयर इंडिया", "other"), ("Delhi Metro", "दिल्ली मेट्रो", "other"),
                                        ("Bharat Mandapam", "भारत मंडपम", "other"),
                                        ("Raihan Vadra", "रेहान वाड्रा", "cap"),
                                        ("Raihan Vadra", "रेहान वाड्रा", "unread")])
def test_a_firm_a_capped_or_an_unread_name_is_not_faceless(en, hi, fate):
    names = [{"en": en, "hi": hi}]
    lines = [f"{hi} ने बयान जारी किया।", f"{hi} के मुताबिक जांच जारी है।"]
    looked = {writer.hindi.norm(hi): fate}
    assert writer.faceless(f"{hi} का बयान", SUBJECT_PHOTO, [], "प्रियंका वाड्रा", True, names, "", lines, looked) is None


def test_a_name_looked_up_and_not_found_is_faceless():
    names = [{"en": "Raihan Vadra", "hi": "रेहान वाड्रा"}]
    looked = {writer.hindi.norm("रेहान वाड्रा"): "unfound"}
    why = writer.faceless("रेहान वाड्रा की प्रदर्शनी", SUBJECT_PHOTO, [], "प्रियंका वाड्रा", True, names, "", [],
                          looked)
    assert why.startswith("faceless: the title is about रेहान वाड्रा")


def test_the_title_needs_the_full_name_and_a_place_is_no_alias():
    names = [{"en": "Delhi Sharma", "hi": "दिल्ली शर्मा"}]
    looked = {writer.hindi.norm("दिल्ली शर्मा"): "unfound"}
    lines = ["दिल्ली में बैठक हुई।", "दिल्ली पुलिस ने बताया।"]
    assert writer.faceless("दिल्ली में बैठक", SUBJECT_PHOTO, [], "प्रियंका वाड्रा", True, names, "", lines,
                           looked) is None
    names = [{"en": "Raihan Vadra", "hi": "रेहान वाड्रा"}]
    looked = {writer.hindi.norm("रेहान वाड्रा"): "unfound"}
    assert writer.faceless("रेहान की प्रदर्शनी", SUBJECT_PHOTO, [], "प्रियंका वाड्रा", True, names, "", [],
                           looked) is None  # the first word alone in the title is not the full name


def test_cast_for_records_each_names_fate(monkeypatch):
    ents = {"Air India": {"k": {"Q46970"}}, "Rahul Gandhi": {"k": {"Q5"}}, "Amit Shah": {"k": {"Q5"}}}

    def hit(q, en, india):
        if en == "Unread Person":
            raise OSError("api down")
        e = ents.get(en)
        return (f"Q-{en}", en, e) if e else None

    monkeypatch.setattr(visuals, "_hit", hit)
    monkeypatch.setattr(visuals, "kinds", lambda ent: {"Q5"} & ent.get("k", set()) or ent.get("k", set()))
    monkeypatch.setattr(visuals.wiki, "HUMAN", "Q5")
    monkeypatch.setattr(visuals, "resolve_topic", lambda en: None)
    monkeypatch.setattr(visuals, "sub_place", lambda *a, **k: None)
    monkeypatch.setattr(visuals, "is_region", lambda ent: False)
    monkeypatch.setattr(visuals, "MAX_PEOPLE", 1)
    names = [("Air India", "एयर इंडिया"), ("Rahul Gandhi", "राहुल गांधी"), ("Amit Shah", "अमित शाह"),
             ("Raihan Vadra", "रेहान वाड्रा"), ("Unread Person", "अनरीड पर्सन")]
    draft = {"names": [{"en": e, "hi": h} for e, h in names],
             "beats": [{"say": " और ".join(h for _, h in names) + " पहुंचे।"}]}
    fates = {}
    CAST_FOR(draft, "Priyanka Gandhi", True, thing_resolver=lambda en: None, thing_lookup=lambda e: None,
                     fates=fates)
    n = writer.hindi.norm
    assert fates == {n("एयर इंडिया"): "other", n("राहुल गांधी"): "cast", n("अमित शाह"): "cap",
                     n("रेहान वाड्रा"): "unfound", n("अनरीड पर्सन"): "unread"}


def test_the_gate_reads_the_saved_fates():
    import inspect

    assert 'short.scene.get("names_looked")' in inspect.getsource(gate.richness)
    assert '"names_looked": looked' in inspect.getsource(writer._short)


# --- 9: DESK_MATCHER=legacy is main ------------------------------------------------------------------------------

def test_legacy_anchorless_is_mains(monkeypatch):
    monkeypatch.setattr(config, "MATCHER", "legacy")
    monkeypatch.setattr(visuals, "showable", lambda *a, **k: ["दिल्ली"])
    draft = {"beats": [{"say": "नेहा बोरा ने दिल्ली में कहा।"}, {"say": "उन्होंने कहा।"}, {"say": "दिल्ली में बैठक।"},
                       {"say": "उन्होंने बताया।"}, {"say": "दिल्ली में फैसला।"}]}
    subject = {"en": "Neha Bora", "hi": "नेहा बोरा"}
    # Two of five empty, never three in a row: main lets it pass; the anchored ceilings (a third) refuse it.
    assert writer.anchorless(draft, subject, True) == []
    monkeypatch.setattr(config, "MATCHER", "anchored")
    monkeypatch.setattr(visuals, "showable_rows", lambda *a, **k: [{"hi": "दिल्ली", "kind": "place"}])
    assert writer.anchorless(draft, subject, True)
    monkeypatch.setattr(config, "MATCHER", "legacy")
    draft["beats"][2] = {"say": "बैठक हुई।"}
    assert writer.anchorless(draft, subject, True)  # beats 2-4 empty: main's run of three


def test_legacy_skips_figures_looks_and_relative_faceless(monkeypatch):
    import inspect

    monkeypatch.setattr(config, "MATCHER", "legacy")
    monkeypatch.setattr(visuals, "_hit", lambda q, en, india: pytest.fail(f"looked up {en}"))
    draft = {"names": [], "beats": [{"say": "प्रधानमंत्री मोदी ने कहा।"}]}
    assert CAST_FOR(draft, "Neha Bora", True) == []
    src = inspect.getsource(visuals.direct)
    assert "if not legacy:  # the rollback" in src and "if legacy else c.get(\"sight\"" in src
    assert 'config.MATCHER != "legacy" and (refused := relative_faceless(' in inspect.getsource(writer.build_explainer)


def test_legacy_draws_a_card_plain_only_when_main_did(monkeypatch):
    s = short(SHAH)
    k = next(k for k, b in enumerate(s.beats) if b.shot.startswith("photo:") and not match.plain(b.text, False))
    monkeypatch.setattr(config, "MATCHER", "legacy")
    assert match.card_plain(s, k) is False


# --- 10: a state's or Pakistan's home minister is not Amit Shah ------------------------------------------------

@pytest.mark.parametrize("line", ["पाक गृह मंत्री ने यमुना सफाई पर बात की।", "कर्नाटक गृह मंत्री ने इस्तीफा दिया।",
                                  "बिहार के गृह मंत्री ने कहा।", "पाकिस्तान के गृह मंत्री ने कहा।"])
def test_another_countrys_or_states_home_minister_is_not_the_subject(line):
    s = short(SHAH)
    cast, spell = match.cast_of(s), match.spellings_of(s)
    found = match.names(line, cast, spell, match.others_of(s.scene.get("names"), cast, spell))
    assert match.SUBJECT not in {x for _, x in found}
    assert "पाक" in things.FOREIGN


def test_the_home_minister_and_the_countrys_are_still_the_subject():
    s = short(SHAH)
    cast, spell = match.cast_of(s), match.spellings_of(s)
    others = match.others_of(s.scene.get("names"), cast, spell)
    for line in ("गृह मंत्री ने यमुना सफाई पर बात की।", "देश के गृह मंत्री ने कहा।"):
        assert match.SUBJECT in {x for _, x in match.names(line, cast, spell, others)}
