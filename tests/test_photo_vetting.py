"""Photo vetting metadata (SYNC-AUDIT 4.1 step 1), on the pools of audited Shorts: the Rubio Short (39714003987)
opened on his 1989 yearbook photo, Mukesh Ambani came from a 2023 gala, the Jantar Mantar Short showed a 1928 photo,
and 7 of the 8 Tiger Shroff photos carry a paparazzi agency's watermark."""
import json
from pathlib import Path

from desk import media

SYNC = Path(__file__).parent / "fixtures" / "sync"


def photos(name):
    return json.loads((SYNC / f"{name}.json").read_text(encoding="utf-8"))["scene"]["photos"]


RUBIO, TIGER, JANTAR = photos("39714003987"), photos("39411041538"), photos("39708703684")


def test_parse_year():
    assert media.parse_year("circa 1988-1989") == 1988
    assert media.parse_year("circa 1980's") == 1980
    assert media.parse_year("2011-01-28") == 2011
    assert media.parse_year("2025-01-23 08:56:09") == 2025
    assert media.parse_year("1928") == 1928
    assert media.parse_year("") is None and media.parse_year("IMG_7877") is None


def test_era_reject_rubio_pool():
    pool = RUBIO[:8]  # the story's own photos; Rubio was born in 1971 (P569)
    why = {i: media.era_reject(p, 2026, born=1971, role="person", pool=pool) for i, p in enumerate(pool)}
    assert "childhood" in why[0] and "childhood" in why[5]  # the 1989 yearbook, "in 6th Grade"
    assert not any(why[i] for i in (1, 3, 4, 7))
    assert "before adulthood" in media.era_reject({"file": "File:Marco Rubio.jpg", "date": "1987"}, 2026, born=1971)


def test_old_person_photo_only_when_a_newer_one_exists():
    gala, wef = RUBIO[9], RUBIO[10]  # Mukesh Ambani: 2023 gala, 2007 World Economic Forum
    assert media.era_reject(wef, 2026, pool=[gala, wef]) == ""  # 19 years: kept
    assert "while a newer photo exists" in media.era_reject(wef, 2040, pool=[gala, wef])
    assert media.era_reject(wef, 2040, pool=[wef]) == ""  # the only photo of him: a pool never empties on age


def test_place_photo_over_forty_years_out():
    assert "98 years old" in media.era_reject(JANTAR[3], 2026, role="place")  # Jantar Mantar at Jaipur - 1928
    assert media.era_reject(JANTAR[1], 2026, role="place") == ""  # 2002: a heritage photo stays


def test_event_kind():
    assert media.event_kind(RUBIO[9]) == "gala"  # Nita Mukesh Ambani Cultural Centre Gala
    assert media.event_kind(TIGER[7]) == "filmfare"
    assert media.event_kind(TIGER[4]) == "spotted"
    assert media.event_kind(RUBIO[3]) == "" and media.event_kind(RUBIO[10]) == ""
    assert media.event_kind({"categories": "Bharatiya Janata Party politicians"}) == ""
    assert media.event_kind({"description": "a speech to the political party's workers"}) == ""
    assert media.event_kind({"description": "Shroff at a birthday party in Bandra"}) == "party"
    # Finding 7: a politician's party in any wording is not a party he was photographed at, nor "Baby John" a baby.
    for text in ("BJP party workers at the rally", "Congress Party leader Rahul Gandhi", "Aam Aadmi Party office"):
        assert media.event_kind({"description": text}) == "", text
    assert media.event_kind({"file": "File:Varun Dhawan at the wrap party of Baby John.jpg"}) == "party"
    assert not media.CHILD.search("Varun Dhawan promoting Baby John in Mumbai")
    assert media.CHILD.search("Tiger Shroff as a baby") and media.CHILD.search("a baby photo of him")


def test_branded_downranked_not_dropped():
    pool = TIGER[:8]
    assert [media.branded(p) for p in pool].count(True) == 7  # Bollywood Hungama, all but the Mumbai FC photo
    kept = [p for p in pool if not media.era_reject(p, 2026, role="person", pool=pool) and not media.event_kind(p)]
    assert len(kept) >= 2 and sum(media.branded(p) for p in kept) >= 2  # never a ban
    ranked = sorted(pool, key=media.branded)
    assert len(ranked) == 8 and ranked[0]["file"] == TIGER[6]["file"]


def test_watermark_from_categories(monkeypatch):
    """Commons' extmetadata already carries Categories, Credit and the date: _usable keeps them on the Photo."""
    meta = {"LicenseShortName": {"value": "CC BY 3.0"}, "ImageDescription": {"value": "Shroff in Bandra"},
            "Artist": {"value": "A Commons uploader"}, "DateTimeOriginal": {"value": "2016-12-06"},
            "Categories": {"value": "Tiger Shroff|Images from Bollywood Hungama"},
            "Credit": {"value": "<a href='https://www.bollywoodhungama.com/'>Bollywood Hungama</a>"}}
    info = {"File:Tiger Shroff in Bandra.jpg": {"mime": "image/jpeg", "width": 800, "height": 1200, "sha1": "a",
                                                "url": "u", "descriptionurl": "d", "extmetadata": meta}}
    monkeypatch.setattr(media, "_info", lambda files: info)
    [p] = media.picks(["Tiger Shroff in Bandra.jpg"])
    assert p.year == 2016 and "Bollywood Hungama" in p.categories and p.source_credit == "Bollywood Hungama"
    assert media.branded({"author": p.author, "categories": p.categories})  # the author alone says nothing
    row = media.as_dicts([p])[0]
    assert row["categories"] == p.categories and row["year"] == 2016
    assert row["credit"] == "फ़ोटो: A Commons uploader / CC BY 3.0 / Wikimedia Commons"  # the on-screen credit


def test_not_itself():
    iskcon = photos("39560243173")[8]  # "ISKCON Temple, Juhu, Mumbai" under "जुहू में कार पर फायरिंग"
    flyover = photos("39505534156-family")[11] | {"description": "Andheri flyover, on the Western Express Highway"}
    assert media.not_itself(iskcon, "Juhu")
    assert media.not_itself(flyover, "Andheri") and media.not_itself(flyover, "Andheri railway station")
    assert not media.not_itself(photos("39505534156-family")[11], "Juhu")  # "Juhu and Juhu Beach"
    assert not media.not_itself({"file": "File:Andheri station platform.jpg"}, "Andheri railway station")
