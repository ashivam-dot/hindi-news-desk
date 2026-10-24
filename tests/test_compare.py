from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from desk import compare, gate, hindi, voice, writer

AT = datetime(2026, 10, 24, 11, 0, tzinfo=timezone.utc)
# The World Bank's WDI as of 2026-10-24.
WB_ROWS = {
    compare.TROOPS: {"IND": {2020: 3068000, 2019: 3045000}, "PAK": {2020: 943000, 2019: 943000},
                     "USA": {2020: 1395000}, "RUS": {2020: 1454000}},
    compare.LABOUR: {"IND": {2020: 0.576119558133425}, "PAK": {2020: 1.25177962110476},
                     "USA": {2020: 0.85}, "RUS": {2020: 1.94}},
    compare.GDP: {"IND": {2025: 3956067115771.63, 2024: 3.9e12}, "PAK": {2025: 407307214476.222, 2024: 3.7e11},
                  "USA": {2025: 3.0e13}, "RUS": {2025: 2.1e12}},
    compare.PEOPLE: {"IND": {2025: 1463865525}, "PAK": {2025: 255219554}, "USA": {2025: 341784857},
                     "RUS": {2025: 143513328}},
}
CC_BY = {c: "CC BY-4.0" for c in compare.INDICATORS}


def fake_get(url, params=None, timeout=None, rows=WB_ROWS, licence=CC_BY):
    if "/metadata" in url:
        code = url.split("/series/")[1].split("/")[0]
        return {"source": [{"concept": [{"variable": [{"metatype": [{"id": "License_Type", "value": licence[code]}]}]}]}]}
    code = url.rsplit("/", 1)[1]
    codes = url.split("/country/")[1].split("/")[0].split(";")
    return [{}, [{"countryiso3code": k, "date": str(y), "value": v} for k in codes
                 for y, v in rows[code].get(k, {}).items()]]


def fake_photos(iso3, folder, taken, recent=frozenset(), want=5):
    en = compare.COUNTRIES[iso3][0]
    return [{"file": f"File:{en} forces {i}.jpg", "page": f"https://commons.wikimedia.org/wiki/File:{en}_{i}.jpg",
             "license": "CC BY 4.0", "credit": "फ़ोटो: A / CC BY 4.0 / Wikimedia Commons", "path": "", "year": 2023,
             "description": f"{en} Army parade"} for i in range(want)]


@pytest.fixture
def work(monkeypatch, tmp_path):
    monkeypatch.setattr(writer, "WORK", tmp_path)
    monkeypatch.setattr(writer, "recent_photos", lambda: set())


def test_a_comparison_is_licensed_published_numbers_each_with_its_year(work):
    short = compare.build(compare.from_target("compare:PAK-IND", AT), get=fake_get, photos_for=fake_photos)
    assert short.id == "cmp-20261024-IND-PAK-forces"  # never the retired cmp-20261024-IND-PAK
    assert short.title == "भारत बनाम पाकिस्तान: सेना में भारत 3.3 गुना, अर्थव्यवस्था में भारत 9.7 गुना"
    said = " ".join(b.text for b in short.beats)
    for words in ("2020 के आंकड़ों में भारत के सशस्त्र बल पाकिस्तान से 3.3 गुना बड़े थे", "30.7 लाख", "9.4 लाख",
                  "अर्धसैनिक बल मिलाकर", "पाकिस्तान आगे था: 1.3 प्रतिशत, भारत 0.6 प्रतिशत",
                  "2025 में अर्थव्यवस्था में भारत पाकिस्तान से 9.7 गुना बड़ा है", "भारत 146.4 करोड़, पाकिस्तान 25.5 करोड़"):
        assert words in said
    assert "सिपरी" not in said and "खर्च" not in said  # no SIPRI data: not licensed for a monetized channel
    backed = {n for f in short.facts for n in f.numbers}
    assert {v for v, _ in hindi.numbers(said + " " + short.title)} <= backed
    assert all(f.source.startswith("https://data.worldbank.org/indicator/") and "CC BY 4.0" in f.evidence
               for f in short.facts)
    assert "IISS" in short.credits[0] and "UN World Population Prospects" in short.summary
    assert all(p["tag"] in ("भारत", "पाकिस्तान") and "who" not in p for p in short.scene["photos"])
    assert gate.check(short) == [] and gate.said_is_shown(short) == []


def test_a_comparison_is_paced_on_the_words_the_narrator_says(work):
    short = compare.build(compare.from_target("compare:IND-PAK", AT), get=fake_get, photos_for=fake_photos)
    written = sum(len(b.text.split()) for b in short.beats)
    assert voice.said_words(short) > written * 1.25  # '2020' is 'दो हज़ार बीस', '30.7' is 'तीस दशमलव सात'
    assert voice.said_words(SimpleNamespace(id="20261024-abc", beats=short.beats)) is None


def test_data_without_a_commercial_licence_is_refused():
    sipri = CC_BY | {compare.GDP: "SIPRI terms and conditions"}
    with pytest.raises(ValueError, match="not licensed for commercial use"):
        compare.figures(("IND", "PAK"), lambda *a, **k: fake_get(*a, licence=sipri, **k))


def test_figures_never_mix_years():
    data = compare.figures(("IND", "PAK"), fake_get)
    assert data[compare.TROOPS][0] == 2020 and data[compare.GDP][0] == 2025
    lone = {k: {c: dict(v) for c, v in t.items()} for k, t in WB_ROWS.items()}
    lone[compare.GDP]["PAK"] = {2024: 3.7e11}
    assert compare.figures(("IND", "PAK"), lambda *a, **k: fake_get(*a, rows=lone, **k))[compare.GDP][0] == 2024


def test_nearly_equal_forces_are_said_to_be_about_equal():
    s = compare.script(("USA", "RUS"), compare.figures(("USA", "RUS"), fake_get))
    assert s["beats"][0]["say"] == "2020 के आंकड़ों में रूस और अमेरिका के सशस्त्र बल लगभग बराबर थे।"
    assert s["title"] == "रूस बनाम अमेरिका: सेनाएं लगभग बराबर, अर्थव्यवस्था में अमेरिका 14.3 गुना"
    assert s["beats"][3]["say"] == "पर 2025 में अर्थव्यवस्था में अमेरिका रूस से 14.3 गुना बड़ा है।"


def test_a_photo_must_name_its_own_country_and_no_other():
    def p(file, description="", categories=()):
        return SimpleNamespace(file=file, description=description, categories=list(categories))

    assert compare.own(p("File:Pakistan Air Force JF-17 Thunder Block III.jpg"), "PAK")
    # A "Pakistan Army parade" hit: an Indian Army regiment's bicentenary.
    assert not compare.own(p("File:Bicentenary celebrations of The Poona Horse3.jpg",
                             "DECORATED REGIMENT OF INDIAN ARMY CELEBRATED THE BICENTENARY", ["Pakistan"]), "PAK")
    assert not compare.own(p("File:Russian Navy ship in Vladivostok.jpg",
                             "VLADIVOSTOK, Russia (Sept. 22, 2012) Sailors aboard USS Vandegrift"), "RUS")
    assert not compare.own(p("File:Ukrainian MiG-29s.jpg", "A U.S. B-52H Stratofortress and Ukrainian MiG-29s"), "UKR")
    # A city's parade is not the country's forces: Belarus's contingent at Moscow's 2010 parade.
    assert not compare.own(p("File:2010 Moscow Victory Day Parade-9.jpeg",
                             "Военный парад, посвящённый 65-летию Победы"), "RUS")
    assert compare.own(p("File:Sukhoi Su-57 RF-81775 Army-2022.jpg", "Russian Air Force Sukhoi Su-57"), "RUS")
    # A named person is someone the voice never names.
    assert compare.NAMED.search("Christmas Eve photo of Andrii Pilshchykov posted by the Ukrainian Air Force")
    assert not compare.NAMED.search("Ukrainian Air Force MiG-29 in the colours of the Ukrainian Falcons")


def rows_at(*items):
    return [{"id": sid, "published_at": at.isoformat()} for sid, at in items]


def test_a_quiet_channel_gets_the_next_evergreen_pair_once_a_day(monkeypatch):
    monkeypatch.setattr(compare, "ENABLED", True)
    quiet = rows_at(("kh-20261024-Q1", AT - timedelta(hours=3)))
    (c,), _ = compare.candidates([], quiet, AT)
    assert c["id"] == "cmp-20261024-IND-PAK-forces" and c["compare"] and c["why"] == "the channel is quiet"
    busy = rows_at(("kh-20261024-Q1", AT - timedelta(minutes=30)))
    assert compare.candidates([], busy, AT)[0] == []
    ran = quiet + rows_at(("cmp-20261024-IND-CHN-forces", AT - timedelta(hours=4)))
    assert compare.candidates([], ran, AT) == ([], ["compare: one ran today"])
    yesterday = quiet + rows_at(("cmp-20261023-IND-PAK-forces", AT - timedelta(days=1)))
    (c,), _ = compare.candidates([], yesterday, AT)
    assert c["pair"] == ["IND", "CHN"]  # a pair waits PAIR_DAYS


def test_the_retired_short_counts_for_nothing(monkeypatch):
    monkeypatch.setattr(compare, "ENABLED", True)
    rows = rows_at(("kh-20261024-Q1", AT - timedelta(hours=3)), ("cmp-20261024-IND-PAK", AT - timedelta(hours=4)))
    (c,), _ = compare.candidates([], rows, AT)
    assert c["id"] == "cmp-20261024-IND-PAK-forces"


def test_a_pair_in_the_news_runs_even_while_the_channel_is_busy(monkeypatch):
    monkeypatch.setattr(compare, "ENABLED", True)
    busy = rows_at(("kh-20261024-Q1", AT - timedelta(minutes=30)))
    story = {"id": "nw-x", "title": "Israel strikes Iran's air defences", "owners": ["a", "b", "c"],
             "headlines": ["Iran vows response after Israeli strikes"]}
    (c,), _ = compare.candidates([story], busy, AT)
    assert c["pair"] == ["ISR", "IRN"] and c["why"] == "in the news" and c["story"] == "nw-x"
    assert compare.candidates([story | {"owners": ["a"]}], busy, AT)[0] == []


def test_with_the_lane_off_only_the_corrected_india_pakistan_short_runs_once():
    busy = rows_at(("kh-20261024-Q1", AT - timedelta(minutes=30)), ("cmp-20261024-IND-PAK", AT - timedelta(hours=2)))
    story = {"id": "nw-x", "title": "Israel strikes Iran", "owners": ["a", "b", "c"], "headlines": []}
    (c,), _ = compare.candidates([story], busy, AT)
    assert c["id"] == "cmp-20261024-IND-PAK-forces"  # not Israel-Iran, busy or not
    done = busy + rows_at(("cmp-20261024-IND-PAK-forces", AT - timedelta(minutes=10)))
    assert compare.candidates([story], done, AT + timedelta(days=20)) == ([], [])  # then nothing, ever


@pytest.mark.parametrize("n,said", [(1463865525, "146.4 करोड़"), (9800000, "98 लाख"), (943000, "9.4 लाख")])
def test_people_read_in_crore_or_lakh(n, said):
    assert compare.crore(n) == said
