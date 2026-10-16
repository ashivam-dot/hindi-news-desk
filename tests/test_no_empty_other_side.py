"""Owner review 2026-10-16: a Sensex Short said "रिपोर्टों में अन्य पक्षों की प्रतिक्रिया नहीं है", a filler line
about an unnamed side a market story does not have."""
from desk import writer


def test_a_reply_line_must_name_who_did_not_reply():
    assert writer.NOBODY_REPLIED.search("रिपोर्टों में अन्य पक्षों की प्रतिक्रिया नहीं है और बाजार के जानकार नजर बनाए हुए हैं।")
    assert writer.NOBODY_REPLIED.search("रिपोर्टों में दूसरे पक्ष की कोई प्रतिक्रिया नहीं है।")
    assert not writer.NOBODY_REPLIED.search("रिपोर्टों में कांग्रेस की प्रतिक्रिया नहीं है।")
    assert not writer.NOBODY_REPLIED.search("विदेश मंत्रालय ने इस पर कोई प्रतिक्रिया नहीं दी है।")


def test_the_explainer_brief_asks_for_the_span_of_a_change_in_the_title():
    assert "4 दिन में" in writer.EXPLAINER_BRIEF and "no other side" in writer.EXPLAINER_BRIEF
