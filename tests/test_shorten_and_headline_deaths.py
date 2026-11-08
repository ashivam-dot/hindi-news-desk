"""An over-long draft loses a middle beat instead of the story; a famous death is told from the headlines."""
from desk import explain, writer


def beat(words, say=None):
    return {"say": say or " ".join(["शब्द"] * words), "photo": 0, "caption": "", "label": ""}


def test_a_draft_over_the_ceiling_drops_a_middle_beat_without_figures():
    draft = {"names": [{"hi": "मोदी", "en": "Modi"}],
             "beats": [beat(11, "मोदी " + " ".join(["शब्द"] * 10)), beat(12, "2 " + " ".join(["शब्द"] * 11)), beat(12),
                       beat(11), beat(12), beat(10)]}
    dropped = writer.shorten(draft, writer.MAX_WORDS)
    says = [b["say"] for b in draft["beats"]]
    assert len(dropped) == 1 and len(says) == 5 and says[0].startswith("मोदी") and says[1].startswith("2 ")
    assert sum(len(s.split()) for s in says) <= writer.MAX_WORDS


def test_shorten_keeps_hook_last_beat_sole_names_and_the_minimum():
    five = {"names": [], "beats": [beat(14) for _ in range(5)]}
    assert writer.shorten(five, writer.MAX_WORDS) == [] and len(five["beats"]) == 5
    named = {"names": [{"hi": "राहुल", "en": "Rahul"}, {"hi": "शाह", "en": "Shah"}],
             "beats": [beat(12), beat(0, "राहुल " + " ".join(["शब्द"] * 11)),
                       beat(0, "शाह " + " ".join(["शब्द"] * 11)), beat(12), beat(12), beat(12)]}
    writer.shorten(named, writer.MAX_WORDS)
    joined = " ".join(b["say"] for b in named["beats"])
    assert "राहुल" in joined and "शाह" in joined and len(named["beats"]) == 5
    fine = {"names": [], "beats": [beat(10) for _ in range(6)]}
    assert writer.shorten(fine, writer.MAX_WORDS) == []


def test_natural_deaths_are_their_own_category_violent_ones_are_not():
    assert explain.category("Filmmaker Sanjay Gupta dies at 57 in Mumbai") == "death"
    assert explain.category("Veteran actor passes away after prolonged illness") == "death"
    assert explain.category("Director Sanjay Gupta no more: Bollywood mourns") == "death"
    assert explain.category("Man shot dead in Delhi, police probe") is None
    assert explain.category("Singer dies in road accident on highway") != "death"
    assert explain.category("Actor found dead at home, police suspect suicide") != "death"
