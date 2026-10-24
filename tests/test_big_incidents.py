from datetime import datetime, timezone

from desk import orbitwire, plan

AT = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def test_a_famous_world_shooting_is_told_off_indias_front_pages():
    trappes = {"id": "wk-Q141820360", "kind": "incident", "category": "attack", "region": "world", "fame": 75_000,
               "owners": ["AFP"], "top": {}, "top_score": 0.0, "title": "2026 Trappes and La Verrière shootings"}
    assert plan.big_incident(trappes) and plan.unpopular(trappes, AT) is None
    small = trappes | {"id": "nw-20261024-lyon-attack", "fame": 75_000, "owners": ["AFP", "BBC"]}
    assert not plan.big_incident(small)  # two owners and no article of its own: not big yet
    assert "not in Google News India" in plan.unpopular(small, AT)


def test_three_owners_make_any_accident_crime_or_war_big():
    jordan = {"id": "nw-20261023-jordan-attack", "kind": "incident", "category": "attack", "region": "world",
              "owners": ["BBC", "Al Jazeera", "DW"], "fame": 75_000, "top": {}, "top_score": 0.0, "title": "Jordan"}
    assert "3 independent owners" in plan.big_incident(jordan) and plan.unpopular(jordan, AT) is None
    statement = jordan | {"category": "politics", "title": "White House statement"}
    assert plan.big_incident(statement) is None


def test_a_war_reported_by_three_owners_needs_no_india_link(monkeypatch):
    monkeypatch.setattr(orbitwire, "india_connection", lambda c: None)
    war = {"id": "kh-20261024-Q432473", "kind": "explainer", "category": "world", "region": "world",
           "title": "Melania Trump", "story": "Russia-Ukraine war: Melania Trump brokers localised ceasefire in Oleshky",
           "headlines": [], "owners": ["BBC", "DW", "NPR"], "top": {}, "top_score": 0.0, "fame": 75_000}
    assert not plan.foreign_only(war) and plan.unpopular(war, AT) is None


def test_orbitwire_telling_a_big_world_incident_never_keeps_it_off_the_hindi_channel(monkeypatch):
    shared = [{"id": "wk-Q9", "qid": "Q9", "kind": "incident", "category": "attack", "fame": 75_000, "region": "world",
               "owners": []}, {"id": "wk-Q8", "qid": "Q8", "kind": "death", "fame": 60_000, "region": "world"}]
    monkeypatch.setattr(orbitwire, "fetch", lambda: {})
    monkeypatch.setattr(orbitwire, "overlap", lambda qid, *a, **k: {"status": "published", "orbitwire_id": f"wk-{qid}"})
    monkeypatch.setattr(orbitwire, "india_connection", lambda c: None)
    kept, notes = plan.apply_orbitwire(shared, AT)
    assert [c["id"] for c in kept] == ["wk-Q9"] and kept[0]["orbitwire"]["high_profile"].startswith("a big attack")
    assert any("skip wk-Q8" in n for n in notes)
