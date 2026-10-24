from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from desk import compare, gate, hindi, writer

AT = datetime(2026, 10, 24, 11, 0, tzinfo=timezone.utc)
DATA = {  # World Bank WDI, 2025 (personnel 2020)
    "IND": {compare.SPEND: 92057013588.16, compare.SHARE: 2.3, compare.TROOPS: 3066000, compare.PEOPLE: 1463865525},
    "PAK": {compare.SPEND: 11871380866.11, compare.SHARE: 2.91, compare.TROOPS: 943000, compare.PEOPLE: 255219554},
}


def fake_get(url, params=None, timeout=None):
    code = url.rsplit("/", 1)[1]
    year = "2020" if code == compare.TROOPS else "2025"
    return [{}, [{"countryiso3code": k, "date": year, "value": v[code]} for k, v in DATA.items()]]


def fake_photos(iso3, folder, taken, recent=frozenset(), want=5):
    en = compare.COUNTRIES[iso3][0]
    return [{"file": f"File:{en} forces {i}.jpg", "page": f"https://commons.wikimedia.org/wiki/File:{en}_{i}.jpg",
             "license": "CC BY 4.0", "credit": f"फ़ोटो: A / CC BY 4.0 / Wikimedia Commons", "path": "", "year": 2023,
             "description": f"{en} Army parade"} for i in range(want)]


def test_a_comparison_is_the_published_numbers_and_passes_every_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(writer, "WORK", tmp_path)
    monkeypatch.setattr(writer, "recent_photos", lambda: set())
    short = compare.build(compare.from_target("compare:PAK-IND", AT), get=fake_get, photos_for=fake_photos)
    assert short.title == "भारत बनाम पाकिस्तान: रक्षा खर्च में 7.8 गुना का फ़र्क"  # the bigger spender leads
    said = " ".join(b.text for b in short.beats)
    for words in ("7.8 गुना", "92.1 अरब डॉलर", "11.9 अरब डॉलर", "पाकिस्तान आगे है: 2.9 प्रतिशत", "30.7 लाख",
                  "9.4 लाख", "63 डॉलर", "47 डॉलर", "विश्व बैंक"):
        assert words in said
    backed = {n for f in short.facts for n in f.numbers}
    assert {v for v, _ in hindi.numbers(said + " " + short.title)} <= backed
    assert all(f.source.startswith("https://data.worldbank.org/") for f in short.facts)
    assert gate.check(short) == [] and gate.said_is_shown(short) == []


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


def rows_at(*items):
    return [{"id": sid, "published_at": at.isoformat()} for sid, at in items]


def test_a_quiet_channel_gets_the_next_evergreen_pair_once_a_day():
    quiet = rows_at(("kh-20261024-Q1", AT - timedelta(hours=3)))
    (c,), _ = compare.candidates([], quiet, AT)
    assert c["id"] == "cmp-20261024-IND-PAK" and c["compare"] and c["why"] == "the channel is quiet"
    busy = rows_at(("kh-20261024-Q1", AT - timedelta(minutes=30)))
    assert compare.candidates([], busy, AT)[0] == []
    ran = quiet + rows_at(("cmp-20261024-IND-PAK", AT - timedelta(hours=4)))
    assert compare.candidates([], ran, AT) == ([], ["compare: one ran today"])
    yesterday = quiet + rows_at(("cmp-20261023-IND-PAK", AT - timedelta(days=1)))
    (c,), _ = compare.candidates([], yesterday, AT)
    assert c["pair"] == ["IND", "CHN"]  # a pair waits PAIR_DAYS


def test_a_pair_in_the_news_runs_even_while_the_channel_is_busy():
    busy = rows_at(("kh-20261024-Q1", AT - timedelta(minutes=30)))
    story = {"id": "nw-x", "title": "Israel strikes Iran's air defences", "owners": ["a", "b", "c"],
             "headlines": ["Iran vows response after Israeli strikes"]}
    (c,), _ = compare.candidates([story], busy, AT)
    assert c["pair"] == ["ISR", "IRN"] and c["why"] == "in the news" and c["story"] == "nw-x"
    assert compare.candidates([story | {"owners": ["a"]}], busy, AT)[0] == []


@pytest.mark.parametrize("usd,said", [(92057013588, "92.1 अरब डॉलर"), (278000000, "27.8 करोड़ डॉलर")])
def test_money_reads_in_arab_or_crore(usd, said):
    assert compare.money(usd) == said
