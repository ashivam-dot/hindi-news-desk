"""The anchored matcher (SYNC-AUDIT 4.1 step 2) on audited beats: a beat shows only what it names, else a text card."""
from dataclasses import replace
from pathlib import Path

from desk import hindi, match, visuals
from desk.spec import Short

SYNC = Path(__file__).parent / "fixtures" / "sync"


def short(name):
    return Short.load(SYNC / f"{name}.json")


def planned(s):
    """direct()'s part, as step 3 will wire it: vet every photo, then plan the spoken beats."""
    photos, cast = [dict(p) for p in s.scene["photos"]], match.cast_of(s)
    for i in range(len(photos)):
        if why := match.vet(i, photos, s, cast):
            photos[i]["vet"] = why
    beats = [{"say": b.text, "card": b.card} for b in s.beats if b.shot != "outro"]
    subject = [i for i, p in enumerate(photos) if not p.get("role")]
    return match.plan(beats, photos, cast, subject, s.kind, match.spellings_of(s), match._person(s)), photos


def applied(s, rows):
    beats = [replace(b, shot="photo:" + "/".join(map(str, r["views"])), plate=r["plate"], cut_word=r["cut_word"],
                     card_view=r["card_view"]) for b, r in zip(s.beats, rows)]
    return replace(s, beats=beats + s.beats[len(rows):])


def test_find_and_located_offsets():
    say = "मुकेश अंबानी और अनंत अंबानी ने जामनगर परिसर में उनका स्वागत किया।"
    assert hindi.find(say, "जामनगर") == say.index("जामनगर") and hindi.find(say, "नगर") == -1
    cast = short("39714003987").scene["cast"]
    assert [(at, c["en"]) for at, c in visuals.located(say, cast)] == [(0, "Mukesh Ambani"), (31, "Jamnagar")]
    assert [c["en"] for c in visuals.mentions(say, list(reversed(cast)))] == ["Mukesh Ambani", "Jamnagar"]


def test_map_description_depicts_own_place():
    photos, cast = short("39714003987").scene["photos"], short("39714003987").scene["cast"]
    assert match.depicts(8, photos[8], cast) == {"जामनगर"}  # MAP: where Jamnagar is
    assert match.depicts(11, photos[11], cast) == {"वनतारा"}  # MAP: Vantara in Jamnagar: Vantara, not Jamnagar
    assert match.depicts(12, photos[12], cast) == {"वनतारा"}  # Vantara up close
    assert match.depicts(1, photos[1], cast) == {match.SUBJECT}
    assert match.depicts(9, photos[9], cast) == {hindi.norm("मुकेश अंबानी")}
    assert match.depicts(0, {"role": "map", "description": "MAP: Bandra and Juhu"}) == {hindi.norm("Bandra"), hindi.norm("Juhu")}
    assert match.depicts(0, {"role": "map", "depicts": ["x"], "description": "MAP: Juhu up close"}) == {"x"}
    g = match.group(photos, cast)
    assert g[11] == g[12] == g[8]  # a spot's maps count with its city's for MIN_VISUALS


def test_city_never_shows_spot_map():
    rows, _ = planned(short("39714003987"))
    for k in (0, 1):  # "...जामनगर में रिलायंस रिफाइनरी", "...जामनगर परिसर में": the city only
        assert 11 not in rows[k]["views"] and 12 not in rows[k]["views"]
    assert rows[0] == {"views": [1, 8], "cut_word": "जामनगर", "cut_at": 27, "plate": "", "card_view": 1}
    # beat 2's Jamnagar cut would put maps at 50% of the picture time (finding 12): the hosts alone, no map
    assert rows[1] == {"views": [10], "cut_word": "", "cut_at": -1, "plate": "", "card_view": 0}
    assert rows[3] == {"views": [2, 11], "cut_word": "वनतारा", "cut_at": 40, "plate": "", "card_view": 1}  # Vantara's own map


def test_pronoun_continuity_needs_leading_pronoun_and_prev_subject():
    # Jaishankar b5 "उन्होंने इससे पहले चीन और अमेरिका में..." after a beat about him: his photo stays.
    rows, _ = planned(short("39411111185"))
    assert rows[4]["plate"] == "" and rows[4]["views"] == [3]
    # 39527132685 b4 "उन्होंने कार्यक्रम में मुख्यमंत्री..." after the Fadnavis beat: not Tiger, a card.
    rows, _ = planned(short("39527132685"))
    assert rows[3]["plate"] == match.CARD
    # 39508637683 b3 "...फडणवीस भी उनके साथ मौजूद थे": Fadnavis, and no Tiger photo.
    s = short("39508637683")
    rows, _ = planned(s)
    assert rows[2]["views"] == [9] and not set(rows[2]["views"]) & {i for i, p in enumerate(s.scene["photos"])
                                                                     if not p.get("role")}
    assert not match.continues("वे बाल-बाल बचे।", None, False, 0, True)  # no previous subject
    assert not match.continues("उनके साथ", match.SUBJECT, True, 1, True)  # never two in a row
    assert not match.continues("उनके साथ", match.SUBJECT, False, match.CONTINUITY, True)  # at most 2
    assert not match.continues("जयशंकर ने कहा", match.SUBJECT, False, 0, True)  # no leading pronoun


def test_continuity_excludes_unnamed_actor():
    # "उनके ड्राइवर और एक फैन को गोली लगी": harm, and not about Tiger: a card, never Tiger.
    rows, _ = planned(short("39505534156-family"))
    assert rows[4]["plate"] == match.CARD
    # "विदेश मंत्री ने मेहमान नेता के जरिए...": the unnamed guest is not shown as Jaishankar.
    rows, _ = planned(short("39435270246"))
    assert rows[5]["plate"] == match.CARD


def test_claimant_beat_not_subject():
    # "एक ऑडियो क्लिप में एक व्यक्ति ने इस हमले की जिम्मेदारी ली है" sat over Tiger Shroff.
    s = short("39411041538")
    rows, _ = planned(s)
    assert rows[5]["plate"] == match.CARD
    assert any("beat 6 shows" in p for p in match.problems(s))


def test_city_police_is_police():
    cast = match.cast_of(short("39411041538"))
    say = "महाराष्ट्र के मुख्यमंत्री देवेन्द्र फडणवीस ने मुम्बई पुलिस कमिश्नर को फोन कर सख्त कार्रवाई के निर्देश दिए।"
    # "मुम्बई पुलिस" names the police, not Mumbai; with no police row (no police photo) it names nothing a picture
    # could show, so writer.anchorless counts the line as empty (2026-10-22 review round 2).
    assert [x for _, x in match.names(say, cast)] == [hindi.norm("देवेन्द्र फडणवीस")]
    police = cast + [{"kind": "police", "hi": "मुम्बई", "photos": []}]
    assert [x for _, x in match.names(say, police)] == [hindi.norm("देवेन्द्र फडणवीस"), match.POLICE]


def test_surname_inside_another_name_is_not_the_subject():
    s = short("39505534156-family")
    found = match.names(s.beats[0].text, match.cast_of(s), match.spellings_of(s))
    assert [x for _, x in found] == [match.SUBJECT, hindi.norm("जैकी श्रॉफ")]  # श्रॉफ in जैकी श्रॉफ is Jackie


def test_card_takes_the_view_it_names():
    rows, _ = planned(short("39411111185"))  # subject, Mumbai, Rubio; the card says "मार्को रुबियो से मुलाकात"
    assert rows[0] == {"views": [0, 10], "cut_word": "मार्को", "cut_at": 55, "plate": "", "card_view": 1}


def test_rubio_plan_passes_and_original_blocks():
    s = short("39714003987")
    bad = match.problems(s)
    assert any("beat 1 shows" in p and "childhood" in p for p in bad)  # the 1989 yearbook photo
    assert any(p.startswith("pictures: maps fill") for p in bad)
    assert any("card 4 names" in p and hindi.norm("वनतारा") in p for p in bad)
    rows, _ = planned(s)
    assert match.problems(applied(s, rows)) == []
    # the hand fix held maps under 1.5 of its 3 picture beats (finding 12: card time no longer pads the share):
    fixed = short("39714003987-fixed")
    assert match.problems(fixed) == ["pictures: maps fill 50% of the picture time (at most 40%)"]
    assert match.problems(rehosted(fixed)) == []  # beat 2 on the hosts alone, as plan() makes it


def rehosted(s):
    """The hand-fixed Rubio re-planned: beat 2 drops its Jamnagar cut and holds the Ambani photo."""
    return replace(s, beats=[s.beats[0], replace(s.beats[1], shot="photo:10"), *s.beats[2:]])


def test_jaishankar_flags_only_beat_7():
    bad = match.problems(short("39411111185"))
    assert bad and all("beat 7 shows" in p for p in bad)
    rows, _ = planned(short("39411111185"))
    assert rows[6]["plate"] == match.CARD
    assert match.problems(applied(short("39411111185"), rows)) == []


def test_old_jantar_photo_and_card_ceiling():
    s = short("39708703684")
    assert any("98 years old" in p for p in match.problems(s))
    rows, photos = planned(s)
    assert "vet" in photos[3] and all(3 not in r["views"] or r["plate"] for r in rows)
    bad = match.problems(applied(s, rows))  # 4 of 6 beats name nothing showable: blocked, never filled
    assert "text cards: 4 of 6 beats (at most half)" in bad and "text cards: 3 beats in a row from beat 3" in bad


def test_render_views_weigh_map_time():
    """render.json's views give the time shares: the same shots pass or fail on how long the maps are held."""
    s = rehosted(short("39714003987-fixed"))

    def views(map_s):
        t, out = 0.0, []
        for k, i, d in [(0, 7, 2), (0, 8, map_s), (1, 10, 4), (2, 8, 2), (3, 4, 2), (3, 11, 2), (4, 11, 2), (5, 4, 2)]:
            first = not out or out[-1]["beat_k"] != k
            # compose.chip_spans: each chip stamped on the view it comes up over, ending at its cut
            chip = {"chip": [t, min(t + match.CHIP_HOLD, t + d)]} if first and s.beats[k].plate != match.CARD else {}
            out.append({"start": t, "end": t + d, "photo": i, "beat_k": k, "plate": s.beats[k].plate} | chip)
            t += d
        return out

    assert match.problems(s, views(2)) == []  # 4 s of maps in 12 (a card's time is neither map nor picture time)
    assert "pictures: maps fill 53% of the picture time (at most 40%)" in match.problems(s, views(7))  # 9 s in 17


def test_old_short_json_loads(tmp_path):
    """Step 5: an audited short.json, written before plate/cut_word/card_view, loads and round-trips."""
    import json
    raw = json.loads((SYNC / "39714003987.json").read_text(encoding="utf-8"))
    assert not {"plate", "cut_word", "card_view"} & set(raw["beats"][0])
    s = short("39714003987")
    assert [(b.plate, b.cut_word, b.card_view) for b in s.beats] == [("", "", 0)] * len(s.beats)
    assert s.beats[0].shot == "photo:0/8"
    rows, _ = planned(s)
    back = Short.load(applied(s, rows).save(tmp_path / "short.json"))
    assert (back.beats[3].shot, back.beats[3].cut_word, back.beats[3].card_view) == ("photo:2/11", "वनतारा", 1)
    assert back.beats[2].plate == match.CARD
