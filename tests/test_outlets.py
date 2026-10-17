"""Trusted outlets beyond Wikipedia: feeds, corroboration by independent owners, nw- stories and Openverse photos.
Every feed, article and API answer here is a fixture; nothing touches the network."""
from datetime import date, datetime, timedelta, timezone

import pytest

from desk import compose, config, gate, media, news, orbitwire, outlets, plan, trends, writer, youtube
from desk.spec import Beat, Fact, Short

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
BY_KEY = {o["key"]: o for o in outlets.OUTLETS}
OPENVERSE_FOR = media.openverse_for  # conftest stubs it for every other test

RSS = """<?xml version="1.0"?><rss><channel>
<item><title><![CDATA[Cloudburst hits Chamoli, roads cut]]></title><link>https://www.thehindu.com/a1</link>
<pubDate>Tue, 13 Oct 2026 09:00:00 +0530</pubDate>
<description><![CDATA[<p>Rescue teams &amp; locals reached the village.</p>]]></description></item>
<item><title>An old story</title><link>https://www.thehindu.com/old</link>
<pubDate>Wed, 07 Oct 2026 09:00:00 +0000</pubDate></item>
<item><title>No date at all</title><link>https://www.thehindu.com/nodate</link></item>
</channel></rss>"""
RDF = """<rdf:RDF><item rdf:about="https://pib.gov.in/x"><title>PM reviews relief work in Chamoli</title>
<link>https://pib.gov.in/PressReleasePage.aspx?PRID=1</link><dc:date>2026-10-13T08:30:00Z</dc:date></item></rdf:RDF>"""


def item(key, title, hours_ago=1.0, url=None, summary="", now=NOW):
    o = BY_KEY[key]
    return {"title": title, "url": url or f"https://{key}.example/{abs(hash(title)) % 10**8}", "outlet": o["name"],
            "outlet_hi": o["name_hi"], "owner": o["owner"], "group": o["group"], "lang": o["lang"], "geo": o["geo"],
            "feed": key, "at": (now - timedelta(hours=hours_ago)).isoformat(), "summary": summary}


def report(key, text, title="Chamoli cloudburst"):
    return item(key, title) | {"text": text}


# --- feeds -------------------------------------------------------------------------------------------------------

def test_an_rss_feed_with_cdata_and_escaped_html_parses_and_old_or_undated_items_drop():
    got = outlets.parse(RSS, BY_KEY["thehindu"], NOW)
    assert [i["title"] for i in got] == ["Cloudburst hits Chamoli, roads cut"]
    assert got[0]["at"] == "2026-10-13T03:30:00+00:00" and got[0]["summary"] == "Rescue teams & locals reached the village."
    assert got[0]["owner"] == "The Hindu Group" and got[0]["group"] == "Indian national"


def test_a_plain_http_link_becomes_https():
    feed = RSS.replace("https://www.thehindu.com/a1", "http://www.thehindu.com/a1")
    assert outlets.parse(feed, BY_KEY["thehindu"], NOW)[0]["url"] == "https://www.thehindu.com/a1"


def test_a_mixed_feed_is_never_an_indian_signal(monkeypatch):
    assert {BY_KEY[k]["geo"] for k in ("toi", "amarujala", "aajtak", "abp")} == {None}
    monkeypatch.setattr(news, "FEEDS", {})
    monkeypatch.setattr(news, "match", lambda h, now=None, lang="en": "2026 Lisbon tram crash")
    hits, _ = news.signals(NOW, outlet_items=[item("toi", "Lisbon tram crash"), item("guardian", "Lisbon tram crash")])
    assert hits["2026 Lisbon tram crash"]["geos"] == {"world"}


def test_an_rdf_feed_with_dc_date_parses():
    got = outlets.parse(RDF, BY_KEY["pib"], NOW)
    assert got[0]["url"].startswith("https://pib.gov.in/") and got[0]["at"] == "2026-10-13T08:30:00+00:00"


def test_recent_reports_a_failed_feed_and_keeps_the_rest(monkeypatch):
    def feed(outlet):
        if outlet["key"] == "bbc-world":
            raise TimeoutError("timed out")
        return RSS if outlet["key"] in ("thehindu", "ht") else "<rss></rss>"

    monkeypatch.setattr(outlets, "_feed", feed)
    items, errors = outlets.recent(now=NOW)
    assert errors == ["outlet bbc-world: TimeoutError: timed out"]
    assert len(items) == 1  # one URL in two feeds is one article
    assert outlets.recent(now=NOW, langs=("hi",))[0] == []


def test_sister_brands_count_once():
    assert BY_KEY["ht"]["owner"] == BY_KEY["livehindustan"]["owner"] == "HT Media"
    assert BY_KEY["bbc-world"]["owner"] == BY_KEY["bbc-hindi"]["owner"] == "BBC"
    assert BY_KEY["pib"]["owner"] == BY_KEY["pib-hi"]["owner"]
    assert outlets.owners([item("bbc-world", "a"), item("bbc-india", "b"), item("thehindu", "c")]) == \
        ["BBC", "The Hindu Group"]


def test_article_text_is_cached_short_pages_drop_and_the_budget_holds(monkeypatch):
    calls = []
    monkeypatch.setattr(outlets, "_extract", lambda url: calls.append(url) or ("x" * 400 if "long" in url else "short"))
    assert outlets.text("https://a/long") == "x" * 400 and outlets.text("https://a/long") == "x" * 400
    assert outlets.text("https://a/teaser") is None and len(calls) == 2
    monkeypatch.setattr(outlets, "MAX_TEXTS", 3)
    outlets.text("https://b/long")
    assert outlets.text("https://c/long") is None and len(calls) == 3


def test_reporting_takes_one_article_per_owner_strong_outlets_first(monkeypatch):
    monkeypatch.setattr(outlets, "_extract", lambda url: "Chamoli cloudburst report. " * 20)
    items = [item("ht", "Chamoli cloudburst", 0.5), item("livehindustan", "चमोली में बादल फटा", 0.4),
             item("bbc-india", "Chamoli cloudburst", 2), item("thehindu", "Chamoli cloudburst", 1)]
    got = outlets.reporting(items)
    assert [r["owner"] for r in got] == ["BBC", "HT Media", "The Hindu Group"] and all(r["text"] for r in got)
    assert outlets.reporting(items[:2]) == []  # one owner corroborates nothing


def test_about_finds_the_items_naming_a_story():
    items = [item("bbc-world", "Chamoli cloudburst: villages cut off"), item("dw", "Floods in Europe"),
             item("amarujala", "चमोली में बादल फटा, गाँव कटे")]
    got = outlets.about("2026 Chamoli cloudburst", items, hi="चमोली")
    assert [i["feed"] for i in got] == ["bbc-world", "amarujala"]


# --- discovery ---------------------------------------------------------------------------------------------------

def test_outlet_headlines_weigh_a_story_by_independent_owners(monkeypatch):
    monkeypatch.setattr(news, "FEEDS", {})
    monkeypatch.setattr(news, "match", lambda h, now=None, lang="en": "2026 Chamoli cloudburst" if lang == "en" else
                        "2026 चमोली बादल फटना")
    monkeypatch.setattr(news.wiki, "hi_to_en", lambda titles: {"2026 चमोली बादल फटना": "2026 Chamoli cloudburst"})
    got = [item("bbc-world", "Chamoli cloudburst kills"), item("bbc-india", "Chamoli cloudburst: what we know"),
           item("thehindu", "Cloudburst in Chamoli"), item("amarujala", "चमोली में बादल फटा")]
    hits, errors = news.signals(NOW, outlet_items=got)
    row = hits["2026 Chamoli cloudburst"]
    assert errors == [] and row["owners"] == ["BBC", "The Hindu Group", "Amar Ujala"]
    assert row["news"] == 3 * news.HEADLINE_FAME
    assert row["hindi_news"] == 1 and row["hindi_headlines"] == ["चमोली में बादल फटा"]
    assert len(row["reports"]) == 4 and all(i.get("matched") == "2026 Chamoli cloudburst" for i in got)


# --- corroboration -----------------------------------------------------------------------------------------------

def test_a_number_needs_two_independent_owners():
    one = [report("bbc-world", "Rescuers reached 14 villages."), report("bbc-india", "Rescuers reached 14 villages.")]
    two = one + [report("thehindu", "Teams reached 14 villages by evening.")]
    assert "14" not in gate.corroborated_values(one) and "14" in gate.corroborated_values(two)
    assert gate.reported("Chamoli", [report("ht", "In Chamoli district..."), report("toi", "Chamoli's roads")]) == \
        ["Bennett, Coleman & Co.", "HT Media"]


@pytest.mark.parametrize("texts, wikidata, want", [
    (["12 people were killed in the cloudburst.", "The death toll rose to 12."], None, (12, ["BBC", "The Hindu Group"])),
    (["12 people were killed.", "At least 15 people died."], None, None),  # a hedged or rising count disagrees
    (["12 people were killed.", "14 people were killed."], None, None),
    (["12 people were killed.", "Officials said 12 people were killed."], {15}, None),  # Wikidata disagrees
    (["12 people were killed.", "Rescue work continues."], {12}, (12, ["BBC"])),  # one owner and Wikidata agree
    (["12 people were killed.", "Rescue work continues."], None, None),  # one owner alone is never enough
    (["बादल फटने से 12 लोगों की मौत हो गई।", "12 people were killed."], None, (12, ["BBC", "The Hindu Group"])),
])
def test_a_reported_death_toll(texts, wikidata, want):
    reports = [report("bbc-hindi" if "मौत" in texts[0] else "bbc-world", texts[0]), report("thehindu", texts[1])]
    assert gate.reported_toll(reports, wikidata) == want


def test_a_reported_toll_never_overrides_the_infobox():
    reports = [report("bbc-world", "12 people were killed."), report("thehindu", "12 people were killed.")]
    assert writer.reported_toll(reports, {}, "15 (est.)") is None
    assert writer.reported_toll(reports, {}, None) == (12, ["BBC", "The Hindu Group"])


def _short(facts, reporting, outlets_named=("BBC", "The Hindu")):
    return Short(id="wk-Q1", kind="incident", title="t", beats=[Beat("x", "photo:0")], facts=facts,
                 sources=["https://en.wikipedia.org/wiki/X"], loss=False,
                 scene={"reporting": reporting, "outlets": list(outlets_named)})


def test_the_gate_refuses_a_fact_only_one_owner_reports():
    reps = [outlets.compact(item("bbc-world", "a", url="https://bbc/1")),
            outlets.compact(item("bbc-india", "b", url="https://bbc/2")),
            outlets.compact(item("thehindu", "c", url="https://hindu/1"))]
    one = Fact("source-14", "14", "https://bbc/1", ["14"], "reported by BBC", owners=["BBC"])
    two = Fact("source-14", "14", "https://bbc/1", ["14"], "reported by BBC, The Hindu Group",
               owners=["BBC", "The Hindu Group"])
    bare = Fact("source-9", "9", "https://hindu/1", ["9"], "")
    assert gate._reported(_short([two], reps)) == []
    assert gate._reported(_short([one], reps)) == ["fact source-14: 1 independent outlet(s) report it (want 2)"]
    assert gate._reported(_short([bare], reps)) == ["fact source-9: 0 independent outlet(s) report it (want 2)"]
    assert gate._reported(_short([two], reps, ())) == ["sources: the outlets the facts come from are not named"]


TEXT_A = "The cloudburst struck Chamoli on Monday. Rescuers reached 14 villages and the Alaknanda rose."
TEXT_B = "In Chamoli, teams reached 14 villages by evening as the Alaknanda river swelled."
TEXT_C = "Officials in Chamoli said 9 bridges were damaged."


def _incident_draft(say):
    return {"title": "चमोली में बादल फटा: पूरा मामला", "names": [{"hi": "चमोली", "en": "Chamoli"}],
            "beats": [{"say": s, "photo": i % 3, "caption": "चमोली"} for i, s in enumerate(say)]}


def _validate(d, reports):
    photos = [{"file": f"File:{i}.jpg", "description": "Chamoli"} for i in range(3)]
    return writer.validate(d, photos, {"en": "Chamoli", "hi": "चमोली", "person": False}, "Place: Chamoli.", "",
                           {"Chamoli": "चमोली"}, [], "incident", False, reports=reports)


SAY = ["उत्तराखंड के चमोली में बादल फटने के बाद राहत का काम तेज़ी से चल रहा है और टीमें लगातार पहुँच रही हैं।",
       "राहत दल अब तक 14 गाँवों तक पहुँच चुके हैं, जहाँ लोगों को सुरक्षित जगहों पर ले जाया जा रहा है।",
       "अलकनंदा नदी का जलस्तर बढ़ गया है और आसपास के इलाकों में लोगों को सावधान रहने को कहा गया है।",
       "प्रशासन ने कहा है कि सड़कों को खोलने का काम जारी है और हालात पर लगातार नज़र रखी जा रही है।"]


def test_the_writer_may_use_what_two_owners_report():
    reports = [report("bbc-world", TEXT_A), report("thehindu", TEXT_B)]
    d = _incident_draft(SAY)
    d["names"].append({"hi": "अलकनंदा", "en": "Alaknanda"})
    problems, _ = _validate(d, reports)
    assert problems == []


def test_the_writer_may_not_use_what_one_owner_reports():
    reports = [report("bbc-world", TEXT_A), report("thehindu", TEXT_C)]
    d = _incident_draft(SAY)
    d["names"].append({"hi": "अलकनंदा", "en": "Alaknanda"})
    problems, _ = _validate(d, reports)
    assert any("14" in p and "one outlet" in p for p in problems)
    assert any("Alaknanda" in p and "only one outlet" in p for p in problems)


def test_reports_lose_casualty_and_suspect_sentences_before_the_writer_sees_them():
    got = writer.clean_reports([report("bbc-world", "A blast hit Chamoli market. 12 people were killed. Police named "
                                                    "the suspect as a local man. Shops reopened on Tuesday.")],
                               ["Chamoli"], perpetrators=True)[0]
    assert "killed" not in got["text"] and "suspect" not in got["text"] and "Shops reopened" in got["excerpt"]
    died = writer.clean_reports([report("bbc-world", "A bus fell near Chamoli. Twelve people died and 12 bodies were "
                                                     "recovered. Police arrested the driver. The road reopened."),
                                 report("thehindu", "A bus fell near Chamoli. 12 people died. The road reopened.")],
                                ["Chamoli"], perpetrators=True)
    assert all(r["text"] == "A bus fell near Chamoli. The road reopened." for r in died)
    assert "12" not in gate.corroborated_values(died)


def test_an_agreed_toll_never_lets_another_reported_count_through():
    # Infobox and Wikidata agree on 12; two outlets say "at least 15 killed, 30 injured".
    kept = writer.clean_reports([report("bbc-world", "A blast hit Chamoli. At least 15 people were killed and 30 "
                                                     "injured, officials said. Markets shut."),
                                 report("thehindu", "A blast hit Chamoli. At least 15 people were killed, 30 injured. "
                                                    "Markets shut.")], ["Chamoli"], perpetrators=True)
    assert not {"15", "30"} & gate.corroborated_values(kept)
    d = _incident_draft(SAY[:3] + ["धमाके में 15 लोगों की जान गई और 30 लोग घायल हुए, बाज़ार बंद रहे।"])
    problems, _ = writer.validate(d, [{"file": f"File:{i}.jpg", "description": "Chamoli"} for i in range(3)],
                                  {"en": "Chamoli", "hi": "चमोली", "person": False},
                                  "Official death toll (Wikipedia and Wikidata agree): 12.", "", {"Chamoli": "चमोली"},
                                  [], "incident", True, reports=kept)
    assert any("15" in p for p in problems)


@pytest.mark.parametrize("text", ["12 or more people were killed.", "12 feared dead after the blast.",
                                  "50 से अधिक की मौत हो गई।"])
def test_a_hedge_after_the_number_is_not_an_exact_toll(text):
    n = int(text.split()[0])
    reports = [report("bbc-world", text), report("thehindu", text), report("ht", f"{n} people were killed.")]
    assert gate.reported_toll(reports) is None


def test_one_owner_and_one_of_several_wikidata_tolls_is_not_a_toll():
    reports = [report("bbc-world", "12 people were killed."), report("thehindu", "Rescue work continues.")]
    assert gate.reported_toll(reports, {12, 15}) is None


def test_the_reporting_block_names_each_outlet_and_owner():
    block = writer.reporting_block([report("bbc-world", TEXT_A) | {"excerpt": TEXT_A}])
    assert "BBC (owner: BBC)" in block and "two reports from DIFFERENT owners" in block and TEXT_A in block


# --- stories Wikipedia has no article for yet (nw-) --------------------------------------------------------------

def _cluster(now=NOW):
    return [item("bbc-world", "Chamoli cloudburst: villages cut off in Uttarakhand", 3, now=now),
            item("thehindu", "Cloudburst in Chamoli leaves villages cut off", 2, now=now),
            item("toi", "Chamoli cloudburst: rescue teams reach cut off villages", 1, now=now)]


def test_three_owners_with_a_strong_one_make_an_nw_story():
    got = outlets.stories(_cluster(), NOW)
    assert len(got) == 1
    c = got[0]
    assert c["id"] == "nw-20261013-chamoli-flood" and c["name"] == "Chamoli" and c["category"] == "flood"
    assert c["owners"] == ["BBC", "The Hindu Group", "Bennett, Coleman & Co."] and c["emerging"]
    assert c["title"].startswith("Chamoli cloudburst") and len(c["reports"]) == 3


def test_an_nw_story_needs_three_owners_a_strong_one_and_fresh_reports():
    two = _cluster()[:2] + [item("bbc-india", "Chamoli cloudburst: villages cut off", 1)]
    assert outlets.stories(two, NOW) == []  # BBC twice is one owner
    weak = [item("thehindu", "Chamoli cloudburst leaves villages cut off", 2),
            item("toi", "Chamoli cloudburst: villages cut off", 1),
            item("ht", "Chamoli cloudburst: cut off villages wait", 1)]
    assert outlets.stories(weak, NOW) == []  # no official, public broadcaster or international outlet
    old = [i | {"at": (NOW - timedelta(hours=30)).isoformat()} for i in _cluster()]
    assert outlets.stories(old, NOW) == []


def test_sport_politics_and_matched_headlines_never_make_an_nw_story():
    sport = [item(k, "Cloudburst hits Chamoli cricket match, players cut off", 1) for k in ("bbc-world", "thehindu", "toi")]
    assert outlets.stories(sport, NOW) == []
    matched = [i | {"matched": "2026 Chamoli cloudburst"} for i in _cluster()]
    assert outlets.stories(matched, NOW, known=["2026 Chamoli cloudburst"]) == []
    assert outlets.stories(_cluster(), NOW, known=["2026 Chamoli cloudburst"]) == []
    listed = [i | {"matched": "List of floods in India"} for i in _cluster()]
    assert len(outlets.stories(listed, NOW, known=["2026 Erie shooting"])) == 1  # a list tells no story


def test_headlines_sharing_only_a_country_and_the_kind_are_different_stories():
    mixed = [item("bbc-world", "India 'cockroach' leaders detained after entering barricaded protest site", 3),
             item("aljazeera", "Dozens of journalists in India detained while covering anti-gov't protests", 2),
             item("thehindu", "Delhi's new designated protest site Ramlila Maidan not free till end of 2026", 2),
             item("aljazeera", "How protests have shaped India: From anti-Hindi agitation to farm laws", 1),
             item("ht", "Delhi HC seeks Centre's response on SOPs to regulate protests", 1),
             item("dw", "India opposition to huddle over tea after thousands march in their Delhi protest", 2),
             item("aljazeera", "Police detain leaders of India's 'cockroach' movement at New Delhi protest", 2),
             item("ht", "'Not the official stance': Harvard Club of India clarifies after alumni statement on Delhi "
                        "protest", 1)]
    assert outlets.stories(mixed, NOW) == []
    assert outlets.headline_kind("How protests have shaped India") is None
    assert outlets.headline_kind("Delhi HC seeks Centre's response on SOPs to regulate protests") is None


def test_an_nw_story_is_told_only_from_two_owners_reporting(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "NEW_STORIES", True)
    cand = outlets.stories(_cluster(), NOW)[0]
    texts = {"bbc-world": TEXT_A, "thehindu": TEXT_B, "toi": TEXT_C}
    monkeypatch.setattr(outlets, "_extract", lambda url: texts[url.split("/")[2].split(".")[0]] + " " * 300)
    monkeypatch.setattr(writer, "WORK", tmp_path)
    monkeypatch.setattr(writer, "story_place", lambda name: ("Q1", {"labels": {"hi": {"value": "चमोली"}}}))
    monkeypatch.setattr(writer.wiki, "claims", lambda ent, pid: [])
    monkeypatch.setattr(writer.wiki, "hindi_names", lambda ent: {"Chamoli": "चमोली"})
    photos = [{"file": f"File:{i}.jpg", "description": "Chamoli", "credit": "फ़ोटो: A / CC BY 2.0 / Openverse (Flickr)",
               "page": f"https://flickr/{i}", "host": "Openverse (Flickr)", "license": "CC BY 2.0"} for i in range(3)]
    monkeypatch.setattr(writer, "fill_photos", lambda qids, folder, exclude, need=3, scene=None: photos)
    seen = {}

    def write(kind, subject, pronoun, facts, source_en, source_hi, photos, hi_names, **kw):
        seen.update(kw, facts=facts, source_en=source_en)
        return _incident_draft(SAY), [], ["model"]

    monkeypatch.setattr(writer, "write", write)
    short = writer.build(cand)
    assert short.id == cand["id"] and source_free(seen) and len(seen["reports"]) == 3
    assert all("excerpt" in r and r["text"] for r in seen["reports"])
    assert short.scene["outlets"] == ["BBC", "Times of India", "The Hindu"] and short.scene["article"] is None
    assert set(short.sources) == {r["url"] for r in cand["reports"]}
    assert "रिपोर्टिंग: BBC, Times of India, The Hindu" in short.credits[0] and "Openverse" in short.credits[0]
    assert "Wikipedia" not in short.credits[0]
    fourteen = next(f for f in short.facts if f.key == "source-14")
    assert fourteen.owners == ["BBC", "The Hindu Group"] and gate._reported(short) == []
    assert youtube.source_lines(short)[0] == "स्रोत: BBC, Times of India, The Hindu"


def source_free(seen):
    return seen["source_en"] == "" and not seen["agreed_toll"]


def test_an_nw_story_with_one_readable_report_is_refused(monkeypatch):
    monkeypatch.setattr(config, "NEW_STORIES", True)
    cand = outlets.stories(_cluster(), NOW)[0]
    monkeypatch.setattr(outlets, "_extract", lambda url: (TEXT_A + " " * 300) if "bbc" in url else None)
    with pytest.raises(ValueError, match="fewer than 2 independent outlets"):
        writer.build(cand)
    monkeypatch.setattr(outlets, "_extract", lambda url: (TEXT_B + " " * 300) if "thehindu" in url else
                        "Rescue work went on. " * 20)
    outlets.reset()
    with pytest.raises(ValueError, match="fewer than 2 independent outlets' articles name Chamoli"):
        writer.build(cand)


def test_an_nw_story_is_not_built_while_the_setting_is_off(monkeypatch):
    monkeypatch.setattr(config, "NEW_STORIES", False)
    with pytest.raises(ValueError, match="DESK_NEW_STORIES"):
        writer.build(outlets.stories(_cluster(), NOW)[0])


PERSON = {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}}
PLACE = {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q515"}}}}],
                    "P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 30.4, "longitude": 79.3}}}}]}}


def test_an_nw_story_place_is_never_a_person(monkeypatch):
    monkeypatch.setattr(writer.wiki, "search", lambda name: "Imran Khan" if name == "Khan" else "Chamoli district")
    monkeypatch.setattr(writer.wiki, "page_info", lambda titles: {t: {"qid": "Q1"} for t in titles})
    monkeypatch.setattr(writer.wiki, "entities", lambda qids: {"Q1": PERSON})
    assert writer.story_place("Khan") == (None, {})
    monkeypatch.setattr(writer.wiki, "entities", lambda qids: {"Q1": PLACE})
    assert writer.story_place("Chamoli") == ("Q1", PLACE)


def test_openverse_is_searched_only_for_places(monkeypatch):
    asked = []
    monkeypatch.setattr(media.wiki, "entities", lambda qids: {"Q1": PERSON | {"labels": {"en": {"value": "A Singer"}}},
                                                              "Q2": PLACE | {"labels": {"en": {"value": "Chamoli"}}}})
    monkeypatch.setattr(media, "openverse", lambda q, exclude=None: asked.append(q) or [])
    OPENVERSE_FOR(["Q1", "Q2"])
    assert asked == ["Chamoli"]


def test_discovery_reports_must_name_the_story(monkeypatch):
    monkeypatch.setattr(outlets, "_extract", lambda url: "Chamoli report. " * 30)
    cand = {"reports": [item("bbc-world", "Chamoli cloudburst: villages cut off"),
                        item("thehindu", "Cloudburst in Chamoli leaves villages cut off"),
                        item("ht", "Uttarakhand assembly session adjourned")]}
    got = writer._reporting(cand, "2026 Chamoli cloudburst", search=False)
    assert sorted(outlets.owners(got)) == ["BBC", "HT Media", "The Hindu Group"]  # nw- clusters are the story
    got = writer._reporting(cand, "2026 Chamoli cloudburst", search=True)
    assert sorted(outlets.owners(got)) == ["BBC", "The Hindu Group"]


def test_nw_ids_for_one_story_match_across_runs():
    assert outlets.same_story("nw-20261013-chamoli-flood", "nw-20261012-chamoli-flood")
    assert not outlets.same_story("nw-20261013-chamoli-flood", "nw-20261013-chamoli-landslide")
    assert not outlets.same_story("nw-20261013-chamoli-flood", "nw-20261001-chamoli-flood")


def test_a_story_told_from_reporting_is_not_told_again_from_its_new_article():
    rows = [{"id": "nw-20261013-chamoli-flood", "published_at": "2026-10-13T10:00:00+00:00",
             "headlines": ["Chamoli cloudburst: villages cut off in Uttarakhand"], "report_urls": ["https://bbc/1"]}]
    wk = {"id": "wk-Q99", "title": "2026 Chamoli cloudburst", "reports": []}
    assert plan.told_before(wk, rows, NOW)
    assert not plan.told_before({"id": "wk-Q98", "title": "2026 Kerala boat accident"}, rows, NOW)
    assert plan.told_before({"id": "wk-Q97", "title": "x", "reports": [{"url": "https://bbc/1"}]}, rows, NOW)
    assert not plan.told_before(wk, [r | {"published_at": "2026-10-01T10:00:00+00:00"} for r in rows], NOW)
    assert not plan.told_before(wk, [r | {"id": "wk-Q5"} for r in rows], NOW)  # Wikipedia stories match by id


def test_orbitwire_sharing_works_for_nw_stories():
    state = {"published": [{"id": "nw-20261012-chamoli-flood", "published_at": "2026-10-13T08:00:00+00:00",
                            "report_urls": ["https://bbc/1"], "title": "Chamoli"}], "candidates": {}}
    assert orbitwire.overlap(None, state, NOW, story_id="nw-20261013-chamoli-flood")["status"] == "published"
    assert orbitwire.overlap("Q99", state, NOW, reports=["https://bbc/1"])["orbitwire_id"] == \
        "nw-20261012-chamoli-flood"
    wk = {"published": [{"id": "wk-Q5", "published_at": "2026-10-13T08:00:00+00:00", "report_urls": ["https://bbc/1"]}],
          "candidates": {}}
    assert orbitwire.overlap("Q99", wk, NOW, reports=["https://bbc/1"]) is None  # Wikipedia stories match by QID


def test_nw_stories_wait_behind_the_setting(monkeypatch):
    now = datetime.now(timezone.utc)

    def signals():
        trends.READ.extend(_cluster(now))
        return {}, []

    monkeypatch.setattr(trends, "_signals", signals)
    monkeypatch.setattr(config, "NEW_STORIES", False)
    got = trends.radar()
    assert [c["id"] for c in got["emerging"]] and got["candidates"] == []
    assert got["outlets"]["headlines"] == 3 and got["outlets"]["owners"] == 3
    monkeypatch.setattr(config, "NEW_STORIES", True)
    assert [c["id"] for c in trends.radar()["candidates"]] == [c["id"] for c in got["emerging"]]


def test_the_plan_note_reports_outlet_counts():
    note = plan.outlet_note({"headlines": 120, "feeds": 16, "owners": 13, "matched": 30, "corroborated": 4},
                            [{"id": "nw-1"}])
    assert "120 headlines" in note and "16 feeds" in note and "4 candidates with 2+ owners" in note
    assert "1 nw- stories" in note and "DESK_NEW_STORIES" in note


# --- Openverse photos --------------------------------------------------------------------------------------------

OPENVERSE = {"results": [
    {"id": "a", "title": "Chamoli valley", "license": "by", "license_version": "2.0", "url": "https://live.staticflickr.com/a.jpg",
     "filetype": "jpg", "width": 2000, "height": 1300, "creator": "Asha", "source": "flickr",
     "foreign_landing_url": "https://www.flickr.com/photos/asha/1"},
    {"id": "b", "title": "Chamoli river", "license": "by-nc", "url": "https://x/b.jpg", "filetype": "jpg",
     "width": 2000, "height": 1300, "creator": "B"},
    {"id": "c", "title": "Chamoli bridge", "license": "pdm", "url": "https://x/c.jpg", "filetype": "jpg",
     "width": 2000, "height": 1300, "creator": "C"},
    {"id": "d", "title": "Chamoli temple", "license": "by-sa", "license_version": "4.0", "url": "https://x/d.jpg",
     "filetype": "jpg", "width": 2000, "height": 1300, "creator": "D", "foreign_landing_url": "https://x/page-d"},
    {"id": "e", "title": "Holiday snap", "license": "cc0", "url": "https://x/e.jpg", "filetype": "jpg",
     "width": 2000, "height": 1300, "creator": "E"},
    {"id": "f", "title": "Chamoli map", "license": "cc0", "url": "https://x/f.png", "filetype": "png",
     "width": 2000, "height": 1300, "creator": "F"},
]}


def test_openverse_keeps_only_cc0_by_and_by_sa_photos_naming_the_place(monkeypatch):
    asked = {}
    monkeypatch.setattr(media.net, "get_json", lambda url, params=None, **k: asked.update(params) or OPENVERSE)
    got = media.openverse("Chamoli", limit=5)
    assert asked["license_type"] == "commercial,modification" and asked["excluded_source"] == "wikimedia"
    assert [p.file for p in got] == ["openverse:a", "openverse:d"]
    assert got[0].license == "CC BY 2.0" and got[0].credit == "फ़ोटो: Asha / CC BY 2.0 / Openverse (Flickr)"
    assert got[0].page == "https://www.flickr.com/photos/asha/1"
    assert all(media.FREE.match(p.license) for p in got)


def test_openverse_photos_are_named_on_the_end_card_and_in_the_description():
    photos = [{"host": "Wikimedia Commons"}, {"host": "Openverse (Flickr)"}]
    assert compose.disclosure(photos) == "असली तस्वीरें: Wikimedia Commons, Openverse · आवाज़: AI"
    assert compose.disclosure(photos[:1]) == compose.DISCLOSURE


def test_the_description_names_the_outlets_behind_the_facts():
    short = Short(id="wk-Q1", kind="incident", title="t", beats=[], facts=[], loss=False,
                  sources=["https://en.wikipedia.org/wiki/X", "https://www.bbc.com/news/1"],
                  scene={"outlets": ["BBC", "The Hindu", "PIB"]})
    assert youtube.source_lines(short)[0] == "स्रोत: Wikipedia, BBC, The Hindu, PIB"
    assert youtube.source_lines(short)[1:3] == short.sources
    short.scene["outlets"] = []
    assert youtube.source_lines(short)[0] == "स्रोत:"
