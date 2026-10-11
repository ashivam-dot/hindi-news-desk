import numpy as np

from desk import faces, media, music, stories, wiki


def amount_claims(*values, preferred=None):
    return [{"rank": "preferred" if v == preferred else "normal", "mainsnak": {"datavalue": {"value": {"amount": f"+{v}"}}}}
            for v in values]


def test_toll_needs_both_sources_to_agree():
    ent = {"claims": {"P1120": amount_claims(269, 229, 260)}}
    assert stories.agreed("260", ent, "P1120", need_wikidata=True) == 260
    assert stories.agreed("241 (plus 19 on the ground)", ent, "P1120", need_wikidata=True) is None
    assert stories.agreed("6+", {"claims": {"P1339": amount_claims(6)}}, "P1339", need_wikidata=True) is None
    assert stories.agreed("At least 12", {"claims": {"P1120": amount_claims(12)}}, "P1120", need_wikidata=True) is None
    assert stories.agreed("180", {"claims": {}}, "P1120", need_wikidata=True) is None
    assert stories.agreed("180", {"claims": {}}, "P1132", need_wikidata=False) == 180


def test_infobox_date():
    from datetime import date
    assert stories.infobox_date({"date": "9 October 2026 (2026-10-09) 14:05 EDT"}) == date(2026, 10, 9)
    assert stories.infobox_date({"date": "October 9, 2026"}) == date(2026, 10, 9)
    assert stories.infobox_date({"date": "9–10 October 2026"}) == date(2026, 10, 9)
    assert stories.infobox_date({"date": "October 2026"}) is None
    assert stories.infobox_date({}) is None
    assert stories.infobox_date({"formed": "September 28, 2026", "dissipated": "October 12, 2026"}) == date(2026, 9, 28)


def test_single_number_prefers_preferred_rank():
    assert wiki.single_number({"claims": {"P1120": amount_claims(269, 260, preferred=260)}}, "P1120") == 260
    assert wiki.single_number({"claims": {"P1120": amount_claims(269, 260)}}, "P1120") is None


def test_leading_number():
    assert wiki.leading_number("260 (241 on board, 19 on ground)") == 260
    assert wiki.leading_number("1,234") == 1234
    assert wiki.leading_number("Unknown") is None


def test_place_names():
    assert stories.city_of("Dubai International Airport, Dubai, United Arab Emirates") == "Dubai"
    assert stories.city_of("Newark, New Jersey, U.S.") == "Newark"


def test_speculative_summaries_are_not_read_out():
    assert stories.SPECULATIVE.search("Suspected hijacking, terrorism, and suicide attempt; under investigation")
    assert not stories.SPECULATIVE.search("Runway excursion on landing")


def test_wikidata_hindi_labels_and_sitelinks():
    ent = {"labels": {"en": {"value": "Varanasi"}, "hi": {"value": "वाराणसी"}},
           "sitelinks": {"hiwiki": {"title": "वाराणसी"}, "enwiki": {"title": "Varanasi"}}}
    assert wiki.label(ent, "hi") == "वाराणसी" and wiki.label(ent) == "Varanasi"
    assert wiki.sitelink(ent) == "वाराणसी" and wiki.sitelink({}) is None
    assert wiki.url("वाराणसी", "hi") == "https://hi.wikipedia.org/wiki/वाराणसी"


def test_photo_relevance_keys():
    assert media._text('Unknown author<span style="display: none;">Unknown author</span>') == "Unknown author"
    assert media._text('<a href="//x">Jane &amp; Co</a> <span class="v">2010</span>') == "Jane & Co 2010"
    assert media._keys("Hurricane Isaias (2026)") == {"isaias"}
    assert media._keys("Nana Patekar") == {"nana", "patekar"}
    assert media._names("Nana Patekar at IFFI Goa, 2017", {"nana", "patekar"})
    assert not media._names("Cine star Waheeda Rehman at IFFI 2009", {"nana", "patekar"})
    assert media._shoot("File:Nana Patekar (Image 2), at IFFI Goa, 2017.jpg") == \
        media._shoot("File:Nana Patekar (Image 3), at IFFI Goa, 2017.jpg")


def test_licences():
    for ok in ("CC BY-SA 4.0", "CC BY 2.0", "CC0", "Public domain", "CC BY-SA 3.0 igo"):
        assert media.FREE.match(ok), ok
    for bad in ("CC BY-NC-SA 2.0", "CC BY-ND 4.0", "Fair use", "All rights reserved"):
        assert not media.FREE.match(bad), bad


def test_graphic_files_are_never_picked():
    assert media.GRAPHIC.search("Victims of the crash.jpg")
    assert media.GRAPHIC.search("Funeral of the actor.jpg")
    assert not media.GRAPHIC.search("Nana Patekar at IFFI Goa.jpg")
    assert media.NOT_PHOTO.search("File:2026 Iran war collage 2.jpg")


def test_excluded_photos_are_skipped(monkeypatch):
    info = {f"File:{n}.jpg": {"width": 2000, "height": 1500, "mime": "image/jpeg", "url": f"https://x/{n}.jpg",
                               "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{n}.jpg", "sha1": n,
                               "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"},
                                               "ImageDescription": {"value": "Nana Patekar"},
                                               "Artist": {"value": "A"}}} for n in ("a", "b", "c")}
    monkeypatch.setattr(media, "_info", lambda files: {f: info[f] for f in files if f in info})
    ordered = [(f, "article") for f in info]
    picked = media._usable(ordered, {"nana", "patekar"}, 5, exclude={"File:b.jpg"})
    assert [p.file for p in picked] == ["File:a.jpg", "File:c.jpg"]
    assert all(p.credit.startswith("फ़ोटो: ") and p.credit.endswith("Wikimedia Commons") for p in picked)


def test_subject_face_is_the_one_that_recurs():
    me, other, stranger = np.eye(3)[0], np.eye(3)[1], np.eye(3)[2]
    per = [[{"box": (0, 0, 9, 9), "feature": other}, {"box": (0, 0, 5, 5), "feature": me}],
           [{"box": (0, 0, 5, 5), "feature": me}],
           [{"box": (0, 0, 5, 5), "feature": stranger}]]
    picks = faces.subject(per)
    assert picks[0]["feature"] is me and picks[1]["feature"] is me
    assert picks[2] is None


def test_music_fits_any_length():
    for mood in ("tribute", "news"):
        for seconds in (20.0, 31.3, 37.8, 44.6, 52.1):
            bed = music.score(seconds, mood, f"{mood}{seconds}")
            assert bed.shape == (int(seconds * music.SR), 2)


def test_article_keeps_the_outcome_at_the_end_of_a_long_lead(monkeypatch):
    lead = "The protest began in June. " * 100 + "The minister resigned on 25 July."
    extract = lead + "\n== Background ==\n" + "Earlier history. " * 300
    seen = []
    monkeypatch.setattr(wiki.net, "get_json", lambda url, **k: seen.append(url) or
                        {"query": {"pages": [{"extract": extract}]}})
    text = wiki.article_text("X")
    assert "resigned on 25 July" in text and "## Background" in text
    wiki.article_text("एक्स", lang="hi")
    assert seen[-1].startswith("https://hi.wikipedia.org/")
