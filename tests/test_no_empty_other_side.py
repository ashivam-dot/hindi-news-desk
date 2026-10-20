"""Owner review 2026-10-16: a Sensex Short said "रिपोर्टों में अन्य पक्षों की प्रतिक्रिया नहीं है", a filler line
about an unnamed side a market story does not have; 2026-10-20 a Tiger Shroff Short said "रिपोर्टों में हमलावरों की
प्रतिक्रिया नहीं है"."""
from desk import writer


def test_no_filler_line_about_a_reply_the_reports_do_not_carry():
    assert writer.NOBODY_REPLIED.search("रिपोर्टों में अन्य पक्षों की प्रतिक्रिया नहीं है और बाजार के जानकार नजर बनाए हुए हैं।")
    assert writer.NOBODY_REPLIED.search("रिपोर्टों में दूसरे पक्ष की कोई प्रतिक्रिया नहीं है।")
    assert writer.NOBODY_REPLIED.search("रिपोर्टों में कांग्रेस की प्रतिक्रिया नहीं है।")
    assert writer.NOBODY_REPLIED.search("रिपोर्टों में हमलावरों की प्रतिक्रिया नहीं है, उधर पुलिस जांच कर रही है।")
    assert not writer.NOBODY_REPLIED.search("विदेश मंत्रालय ने इस पर कोई प्रतिक्रिया नहीं दी है।")


def test_a_news_short_keeps_to_the_news_not_a_biography():
    assert writer.BIOGRAPHY.search("टाइगर एक्टर जैकी श्रॉफ के बेटे हैं और उन्होंने 2014 में फिल्म हीरोपंती से करियर शुरू किया था।")
    assert not writer.BIOGRAPHY.search("पुलिस के मुताबिक तीनों आरोपी कोटा स्टेशन पर पकड़े गए।")


def test_the_explainer_brief_asks_for_the_span_of_a_change_in_the_title():
    assert "4 दिन में" in writer.EXPLAINER_BRIEF and "always for a crime or an attack" in writer.EXPLAINER_BRIEF
