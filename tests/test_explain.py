"""India explainers (kh- ids): which headlines qualify, how they group into one story, what the story is about, and
how the desk schedules and shows them. Every feed and API answer here is a fixture; nothing touches the network."""
from datetime import datetime, timedelta, timezone

import pytest

from desk import compose, config, explain, gate, news, outlets, plan, wiki, writer
from desk.spec import Beat, Short

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
BY_KEY = {o["key"]: o for o in outlets.OUTLETS}


def item(key, title, hours_ago=1.0):
    o = BY_KEY[key]
    return {"title": title, "url": f"https://{key}.example/{abs(hash(title)) % 10**8}", "outlet": o["name"],
            "outlet_hi": o["name_hi"], "owner": o["owner"], "group": o["group"], "lang": o["lang"], "geo": o["geo"],
            "feed": key, "at": (NOW - timedelta(hours=hours_ago)).isoformat(), "summary": ""}


MURUGAN = [
    item("ht", "L Murugan resigns as union minister, Rajya Sabha member: 'Want to strengthen BJP in Tamil Nadu'"),
    item("indianexpress", "L Murugan resigns as Minister of State, Rajya Sabha member", 2),
    item("news18", "Want To Strengthen Tamil Nadu BJP: L Murugan Quits Govt, Thanks PM", 3),
    item("thehindu", "Union Minister L Murugan resigns from Rajya Sabha", 4),
]


@pytest.mark.parametrize("title, cat", [
    ("RBI keeps repo rate unchanged at 5.5%", "economy"),
    ("Ladakh integral part of India, Chinese denial cannot change fact: MEA", "diplomacy"),
    ("SC stays defamation proceedings against Rahul Gandhi", "court"),
    ("ISRO to launch PSLV with EOS satellite on Friday", "science"),
    ("L Murugan resigns as union minister", "politics"),
    ("L Murugan resigns, wishes to return to Tamil Nadu as union minister quits", "politics"),
    ("PM Modi wishes nation on Diwali, union minister joins", None),
    ("Merchant fee on UPI payments to be imposed after Diwali", "policy"),
    ("IMD issues orange alert for heavy rain in Kerala", "weather"),
    ("BJP releases first list of candidates for Bihar polls", None),
        ("India vs Australia: Rohit Sharma's century wins the match", "sport"),
        ("Jailer 2 box office: Rajinikanth starrer opens big", "entertainment"),
        ("Salman Khan opens up about marriage on Koffee With Karan", None),
        ("Supreme Court stays release of film over censor row", "court"),
    ("Man arrested for murder of neighbour in Pune", None),
    ("Bus falls into gorge in Himachal, 12 dead", None),
    ("Gold Rate Today, October 13: check prices in Delhi", None),
    ("How the RBI decides the repo rate", None),
    ("HT Evening Brief October 13: India rejects China's Ladakh claims", None),
])
def test_category_keeps_explainable_topics_and_skips_the_rest(title, cat):
    assert explain.category(title) == cat


def test_one_story_from_four_owners_with_its_full_name():
    found = [c for c in explain.clusters(MURUGAN, NOW) if len(c["owners"]) >= 3]
    assert len(found) == 1 and len(found[0]["owners"]) == 3  # "quits" matches 1 of 3 headlines: under half
    key = explain.centre(found[0])
    assert key == "murugan"
    assert explain.phrase([i["title"] for i in found[0]["items"]], key) == "L Murugan"


def test_title_case_headlines_join_by_the_other_headlines_names():
    rows = [item("ht", "L Murugan resigns as union minister, wishes to return to Tamil Nadu"),
            item("news18", "L Murugan Resigns As Minister, PM Modi's Cabinet Reshuffle Imminent Before Diwali", 2),
            item("ndtv", "Wish To Return To Grassroots: L Murugan Resigns As Union Minister", 3)]
    assert explain.title_case(rows[1]["title"]) and not explain.title_case(rows[0]["title"])
    [c] = explain.clusters(rows, NOW)
    assert explain.centre(c) == "murugan"
    assert explain.phrase([i["title"] for i in c["items"]], "murugan") == "L Murugan"
    apart = [item("news18", "PM Modi Inaugurates New Airport Terminal In Navi Mumbai"),
             item("ndtv", "PM Modi Speaks To Canada PM Mark Carney On Trade Ties", 2)]
    assert all(len(c["items"]) == 1 for c in explain.clusters(apart, NOW))


def test_shared_institution_alone_never_joins_two_stories():
    rows = [item("ht", "Supreme Court stays proceedings against Rahul Gandhi"),
            item("thehindu", "Supreme Court to hear plea on stray dogs in Delhi", 2),
            item("ndtv", "Supreme Court notice to Centre on air pollution plea", 3)]
    assert all(len(c["items"]) == 1 for c in explain.clusters(rows, NOW))


def test_old_and_hindi_items_do_not_form_stories():
    rows = [dict(i, at=(NOW - timedelta(hours=30)).isoformat()) for i in MURUGAN]
    assert explain.clusters(rows, NOW) == []
    assert explain.clusters([item("bhaskar", "एल मुरुगन का इस्तीफा")], NOW) == []


def test_a_loose_link_never_chains_two_stories():
    rows = [item("ht", "Kerala Congress fires staffer over CJI resignation post"),
            item("thehindu", "Kerala Congress disagrees with demand for CJI resignation", 2),
            item("ndtv", "Kerala hotels say they will stop accepting UPI payments above Rs 2,000", 3)]
    sizes = sorted(len(c["items"]) for c in explain.clusters(rows, NOW))
    assert sizes == [1, 2]


def test_hindi_spellings_drop_abbreviation_dots_but_never_use_a_bare_surname():
    assert explain.hindi_names_of("एल. मुरुगन") == ["एल. मुरुगन", "एल मुरुगन"]
    assert explain.hindi_names_of("लद्दाख़") == ["लद्दाख़"]
    assert explain.hindi_names_of(None) == []


def test_two_stories_about_one_person_stay_apart():
    rows = [item("ht", "Rahul Gandhi slams Centre over GST"),
            item("thehindu", "Priyanka Gandhi Vadra writes to PM on Waqf Bill", 2),
            item("ndtv", "Rahul Gandhi meets Opposition leaders", 3)]
    assert all(len(c["items"]) == 1 for c in explain.clusters(rows, NOW))


def test_institution_led_headlines_cluster_and_acronyms_name_their_article():
    rows = [item("ht", "RBI keeps repo rate unchanged at 5.5%"),
            item("thehindu", "RBI holds repo rate unchanged, cuts GDP forecast", 2),
            item("ndtv", "RBI MPC: repo rate unchanged for third time", 3)]
    big = [c for c in explain.clusters(rows, NOW) if len(c["owners"]) == 3]
    assert big and explain.centre(big[0]) == "rbi"
    assert explain.names_article("Reserve Bank of India", "rbi", "RBI")
    assert not explain.names_article("Governor", "rbi", "RBI")


def _stub_wiki(monkeypatch, qid="Q123", kinds=("Q5",), extra=None):
    monkeypatch.setattr(wiki, "search", lambda q, lang="en": "L. Murugan")
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"title": t, "qid": qid} for t in titles})
    claims = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": k}}}} for k in kinds],
              "P27": [{"mainsnak": {"datavalue": {"value": {"id": "Q668"}}}}]} | (extra or {})
    ent = {"labels": {"en": {"value": "L. Murugan"}, "hi": {"value": "एल. मुरुगन"}}, "claims": claims}
    monkeypatch.setattr(wiki, "entities", lambda qids: {qid: ent})
    monkeypatch.setattr(news, "headlines", lambda feed, now=None: (
        [{"title": "एल मुरुगन ने दिया इस्तीफा", "outlets": 3}] if feed in news.HINDI_FEEDS else
        [{"title": "L Murugan resigns from Union Cabinet", "outlets": 4}]))


def test_find_makes_an_india_explainer_with_hindi_and_lead_signals(monkeypatch):
    _stub_wiki(monkeypatch)
    hindi = [item("bhaskar", "केंद्रीय मंत्री एल मुरुगन का इस्तीफा")]
    cands, notes = explain.find(MURUGAN + hindi, NOW)
    assert notes == [] and len(cands) == 1
    c = cands[0]
    assert c["id"] == "kh-20261013-Q123" and c["story_keys"]
    assert c["kind"] == "explainer" and c["person"] and c["region"] == "india" and c["category_hi"] == "राजनीति"
    assert "DB Corp" in c["owners"] and len(c["owners"]) == 4
    assert c["hindi_news"] >= 2 and c["headlines"][-1] == "L Murugan resigns from Union Cabinet"
    # one lead headline counts once however many feeds carry it: 4 English outlets + 3 Hindi ones
    assert c["fame"] == news.HEADLINE_FAME * (4 + 4 + 3)


@pytest.mark.parametrize("name,key,first,second,want", [
    ("Greece", "greece", "Greece", "Greece–India relations", None),
    ("Supreme Court", "court", "Supreme Court of the United States", "Supreme Court of India", "Supreme Court of India"),
    ("UPI", "upi", "UPI", "Unified Payments Interface", "Unified Payments Interface"),
])
def test_the_india_search_counts_only_for_the_indian_article_itself(monkeypatch, name, key, first, second, want):
    _stub_wiki(monkeypatch)
    monkeypatch.setattr(wiki, "search", lambda q, lang="en": second if q.endswith("of India") else first)
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"title": t, "qid": "Q123"} for t in titles
                                                           if t != first})
    got = explain.resolve(name, key)
    assert (got and got[0]) == want


def test_a_centre_that_is_not_indian_tells_a_world_story(monkeypatch):
    _stub_wiki(monkeypatch, extra={"P27": [{"mainsnak": {"datavalue": {"value": {"id": "Q30"}}}}]})
    c = explain.find(MURUGAN, NOW)[0][0]
    assert c["region"] == "world" and c["geos"] == []
    assert c["india_link"]  # Hindi lead headlines name it


def test_festivals_and_peoples_are_never_the_centre(monkeypatch):
    _stub_wiki(monkeypatch)
    ent = wiki.entities(["Q123"])["Q123"] | {"descriptions": {"en": {"value": "Hindu festival of lights"}}}
    monkeypatch.setattr(wiki, "entities", lambda qids: {"Q123": ent})
    monkeypatch.setattr(wiki, "search", lambda q, lang="en": "Diwali")
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"title": t, "qid": "Q123"} for t in titles})
    assert explain.resolve("Diwali", "diwali") is None


def test_aliases_go_straight_to_the_indian_institution(monkeypatch):
    _stub_wiki(monkeypatch)
    monkeypatch.setattr(wiki, "search", lambda q, lang="en": pytest.fail("aliases never search"))
    monkeypatch.setattr(wiki, "page_info", lambda titles: {t: {"title": t, "qid": "Q123"} for t in titles})
    assert explain.resolve("Railway", "railway")[0] == "Indian Railways"


def test_a_headline_with_no_special_topic_is_still_news():
    assert explain.category("IDBI Bank strategic sale gets final nod") == "economy"
    assert explain.category("Air India Frankfurt-Delhi flight diverted to Jaipur") == "aviation"
    assert explain.category("Pope Leo XIV to undergo knee surgery") in ("health", "world")
    assert explain.category("Odisha cabinet approves new textbooks") == "politics"
    assert explain.category("Centre names new panel on river linking") == explain.FALLBACK
    assert explain.category("Virat Kohli scores century in Test match") == "sport"


def test_find_skips_the_dead_disambiguations_and_known_items(monkeypatch):
    _stub_wiki(monkeypatch, extra={"P570": [{"mainsnak": {"datavalue": {"value": {"time": "+2026-10-12T00:00:00Z"}}}}]})
    assert explain.find(MURUGAN, NOW)[0] == []
    _stub_wiki(monkeypatch, kinds=(explain.DISAMBIGUATION,))
    assert explain.find(MURUGAN, NOW)[0] == []
    _stub_wiki(monkeypatch)
    assert explain.find(MURUGAN, NOW, skip_qids={"Q123"})[0] == []


def test_explainers_never_take_the_breaking_lane_and_never_repeat_their_centre():
    cand = {"id": "kh-20261013-l-murugan-politics", "kind": "explainer", "qid": "Q123", "fame": 10**7,
            "news_at": NOW.isoformat(), "reports": [{"url": "https://ht.example/1"}]}
    assert not plan.is_breaking(cand, NOW)
    recent = {"id": "kh-20261013-l-murugan-court", "qid": "Q123", "published_at": (NOW - timedelta(hours=5)).isoformat()}
    assert plan.told_before(cand, [recent], NOW)
    older = recent | {"published_at": (NOW - timedelta(hours=30)).isoformat()}
    assert not plan.told_before(cand, [older], NOW)
    shared = {"id": "nw-20261013-chennai-protest", "report_urls": ["https://ht.example/1"],
              "published_at": (NOW - timedelta(hours=30)).isoformat()}
    assert plan.told_before(cand, [shared], NOW)


def test_explainer_decorum_allows_no_casualties_without_an_agreed_toll():
    assert gate.decorum("इस हादसे में 3 लोगों की मौत हुई", "explainer", False)
    assert not gate.decorum("मंत्री ने इस्तीफ़ा दिया", "explainer", False)


def test_the_lane_is_off_unless_switched_on(monkeypatch):
    monkeypatch.setattr(config, "EXPLAINERS", False)
    with pytest.raises(ValueError, match="DESK_EXPLAINERS"):
        writer.build_explainer({"id": "kh-x", "category": "politics", "qid": "Q1", "title": "X"})


def _short(**scene):
    return Short(id="kh-20261013-l-murugan-politics", kind="explainer", title="एल. मुरुगन ने इस्तीफ़ा क्यों दिया?",
                 beats=[Beat("एल. मुरुगन ने इस्तीफ़ा दिया।", "photo:0", {"big": "इस्तीफ़ा", "small": ""})], facts=[],
                 sources=["https://en.wikipedia.org/wiki/L._Murugan"], loss=False, scene=scene,
                 event_time="2026-10-13", tags=[], summary="", credits=[], hashtags=[])


def test_screen_shows_the_category_and_the_sources():
    s = _short(category_hi="राजनीति", reporting=[{"outlet": "BBC", "outlet_hi": "बीबीसी"},
                                                 {"outlet": "The Hindu", "outlet_hi": "द हिंदू"}])
    assert compose.label_for(s) == "राजनीति"
    assert compose.sources_line(s) == "स्रोत: बीबीसी · द हिंदू · Wikipedia"
    assert compose.label_for(_short()) == "क्या और क्यों"


def test_long_titles_wrap_into_two_even_lines():
    lines = compose.wrap2("एल. मुरुगन ने केंद्रीय मंत्री पद और राज्यसभा से इस्तीफ़ा क्यों दिया?", "Bold", 58, compose.W - 140)
    assert len(lines) == 2 and all(lines)
    assert compose.wrap2("छोटा शीर्षक", "Bold", 58, compose.W - 140) == ["छोटा शीर्षक"]


def test_progress_bar_fills_with_time():
    import numpy as np

    frame = np.full((compose.H, compose.W, 3), 200, dtype=np.uint8)
    compose._progress(frame, 0.5, (90, 200, 255))
    assert tuple(frame[2, 10]) == (90, 200, 255) and tuple(frame[2, compose.W - 10]) == (90, 90, 90)
    assert tuple(frame[compose.PROGRESS_H + 1, 10]) == (200, 200, 200)


def test_agency_copy_and_repeated_text_count_as_one_owner(monkeypatch):
    body_a = ("New Delhi, Oct 13 (PTI) Union minister L Murugan on Monday resigned from the Union Council of Ministers "
              "and the Rajya Sabha. He said he wanted to strengthen the party organisation in Tamil Nadu. " * 3)
    body_b = "L Murugan resigned on Monday, the party said in a statement issued in Chennai late in the evening. " * 4
    texts = {"https://a/1": body_a, "https://b/2": body_a.replace("(PTI)", ""), "https://c/3": body_b,
             "https://d/4": body_a}
    monkeypatch.setattr(outlets, "text", lambda url: texts[url])
    rows = [item("ht", "x") | {"url": "https://a/1"}, item("thehindu", "y") | {"url": "https://b/2"},
            item("ndtv", "z") | {"url": "https://c/3"}, item("indianexpress", "w") | {"url": "https://d/4"}]
    got = outlets.reporting(rows)
    owners = [r["owner"] for r in got]
    assert owners.count("PTI (news agency)") == 1 and "NDTV" in owners and len(owners) == 2
    assert outlets.wire("नई दिल्ली (भाषा) केंद्रीय मंत्री ने इस्तीफा दिया") == "PTI"
    assert outlets.wire("Our correspondent reports from Chennai.") is None


def test_captions_do_not_break_after_an_initial():
    words = [{"text": t, "start": i, "end": i + 1} for i, t in enumerate("एल. मुरुगन ने इस्तीफ़ा दिया है. फिर".split())]
    chunks = [" ".join(w["text"] for w in c) for c in compose._chunks(words)]
    assert chunks[0].startswith("एल. मुरुगन") and any(c.endswith("है.") for c in chunks)
