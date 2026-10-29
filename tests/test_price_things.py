from desk import things

# kh-20261029-Q1185 (9MrOG5OYxdc): "Nandini milk ₹8 costlier" stood over a map of Karnataka.
MILK = [{"say": "कर्नाटक में नंदिनी दूध आठ रुपये प्रति लीटर महंगा हो गया है।"},
        {"say": "डेयरी कोऑपरेटिव्स को एक रुपये प्रति लीटर ज़्यादा मिलेगा।"}]


def hits(beats, india=True):
    return {h["en"] for h in things.lexicon_hits(beats, india)}


def test_a_milk_price_story_shows_milk_and_the_brand_it_names():
    assert {"Milk", "Karnataka Milk Federation"} <= hits(MILK)


def test_the_milk_storys_farmers_and_dairies_get_their_pictures():
    assert "Dairy farming" in hits([{"say": "डेयरी कोऑपरेटिव्स को एक रुपये प्रति लीटर ज़्यादा मिलेगा।"}])
    assert "Farmer" in hits([{"say": "किसानों ने 10 रुपये की बढ़ोतरी की माँग की थी।"}])
    assert "Farmer" not in hits([{"say": "किसान सम्मान निधि की किस्त आई।"}])


def test_the_brand_needs_its_milk_and_gold_needs_its_price():
    assert "Karnataka Milk Federation" not in hits([{"say": "नंदिनी ने कहा कि वह जल्द लौटेगी।"}])
    assert "Gold" not in hits([{"say": "बच्चे रात को सोने से पहले पढ़ते हैं।"}])
    assert "Gold" in hits([{"say": "आज सोने का भाव दो हज़ार रुपये चढ़ गया।"}])


def test_fuel_and_gas_prices_get_their_pictures_but_a_tanker_stays_a_tanker():
    assert {"Gasoline", "Liquefied petroleum gas"} <= hits([{"say": "पेट्रोल-डीजल के बाद गैस सिलेंडर भी महंगा हुआ।"}])
    assert "Milk" not in hits([{"say": "हाईवे पर दूध टैंकर पलट गया।"}])
