from desk import explain, plan

SPEC = {"story": "kh-20261029-Q11041431", "replaces": "9MrOG5OYxdc", "until": "2026-10-31T18:00:00+00:00", "why": "x"}


def test_an_explainer_remake_matches_its_centre_on_the_next_days_radar():
    again = plan.remake_of({"id": "kh-20261030-Q11041431", "title": "t"}, [SPEC])
    assert again["id"] == "kh-20261030-Q11041431" and again["replaces"] == "9MrOG5OYxdc"
    assert plan.remake_of({"id": "kh-20261029-Q11041431"}, [SPEC])["id"] == "kh-20261029-Q11041431-r2"
    assert plan.remake_of({"id": "kh-20261030-Q1185"}, [SPEC]) is None
    assert plan.remake_of({"id": "kh-20261105-Q11041431"}, [SPEC]) is None


def test_nandini_is_its_makers_article():
    assert explain.ALIASES["nandini"] == "Karnataka Milk Federation"
