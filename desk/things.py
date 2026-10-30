"""Things a beat names get their own real picture: the tricolour, Parliament, the Supreme Court, a ship, an animal.

Owner, 2026-10-22, on CAPraPdXvns (Raihan Vadra's exhibition): "where is tiranga picture if you are saying about
tiranga". The beat "रेहान ने तिरंगे की तस्वीरें हटाने से साफ मना किया" stood over a map of New Delhi: only people and
places had pictures, so a thing the voice named was never on screen. Here a thing is a cast member (kind "thing")
like a place: a small hand lexicon of everyday Hindi visual nouns, matched as whole words in every inflected form the
lexicon lists (hindi.find, visuals.located), and the script's own English names when their Wikipedia article is a
thing (a ship, an aircraft, a species, a dish, a medal, a monument). Its pictures are free Commons photos only:
Wikidata's image (P18) and the item's Commons category through media's licence, size and credit checks, or files an
editor chose (media.picks) where P18 is a drawing (the Flag of India's is an SVG, and NOT_PHOTO bans "flag").

Never a work (a film, a book cover, a poster, an album, a painting), a logo or trademark (a company, a party, an
app), a social-media screenshot, or a photo with a featured face (someone a beat does not name). A beat shows a
thing only when it names it (match.problems: shown is said).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from . import hindi, media, wiki

log = logging.getLogger(__name__)

THING_PHOTOS = 2
MAX_THINGS = 3
# Hindi forms (whole words; every inflection listed, hindi.find matches whole words only) -> the English Wikipedia
# article, and for an item whose Wikidata image is a drawing, Commons photos checked by eye (2026-10-22, licences
# re-read at runtime by media.picks). india: shown only in an Indian story ("संसद" in a story about Britain is
# Westminster); every form is also refused after a foreign country's name ("अमेरिका के सुप्रीम कोर्ट"). An india
# entry's forms, and an entry's "generic" forms (any country has a national flag), are words every country uses: they
# are also refused after any foreign word earlier in the beat ("ईरान में प्रदर्शनकारियों ने राष्ट्रीय ध्वज जलाया",
# "जयशंकर ने ब्रिटेन में संसद को संबोधित किया") and after "X की/के/का" for an X that is not India (BY_INDIA: "पोलैंड
# की संसद"). Review round 1 (2026-10-23) found each of these putting India's flag, Parliament or Supreme Court on
# screen in a foreign story. not_before / not_after: the word right after / before a form that makes it another
# thing (an idiom, a brand, a programme): "वंदे भारत मिशन" is an evacuation flight, not the train; "ताज महल पैलेस
# होटल" is Mumbai's hotel; "सफेद हाथी" is an idiom; "बाघ बकरी" is a tea. needs: a word the beat must also say
# ("राम मंदिर" alone may be any village's temple; Ayodhya's is "अयोध्या ... राम मंदिर").
LEXICON = (
    {"hi": "तिरंगा", "forms": ("तिरंगा", "तिरंगे", "तिरंगों", "भारतीय ध्वज", "भारतीय झंडा", "भारतीय झंडे", "राष्ट्रीय ध्वज",
                              "राष्ट्रध्वज", "राष्ट्रीय झंडा", "राष्ट्रीय झंडे"),
     "generic": ("राष्ट्रीय ध्वज", "राष्ट्रध्वज", "राष्ट्रीय झंडा", "राष्ट्रीय झंडे"),
     "en": "Flag of India", "india": False, "not_after": ("फिल्म", "फ़िल्म", "मूवी"),
     "files": ("File:Flag of India, New Delhi.jpg", "File:Shiny Indian flag on high rise.jpg",
               "File:Flag of India Kodaikanal Tamil Nadu 20060126.jpg", "File:INS Kadmatt - Indian Flag.jpg")},
    {"hi": "संसद", "forms": ("संसद", "संसद भवन", "नई संसद", "नए संसद भवन", "नया संसद भवन"),
     "en": "Parliament House, New Delhi", "india": True},
    {"hi": "सुप्रीम कोर्ट", "forms": ("सुप्रीम कोर्ट", "सर्वोच्च न्यायालय", "उच्चतम न्यायालय", "शीर्ष अदालत"),
     "en": "Supreme Court of India", "india": True},
    {"hi": "लाल किला", "forms": ("लाल किला", "लाल किले", "लालकिला", "लालकिले"), "en": "Red Fort", "india": True,
     "not_before": ("मेट्रो", "स्टेशन")},
    {"hi": "इंडिया गेट", "forms": ("इंडिया गेट",), "en": "India Gate", "india": True},
    {"hi": "राष्ट्रपति भवन", "forms": ("राष्ट्रपति भवन",), "en": "Rashtrapati Bhavan", "india": True},
    {"hi": "ताजमहल", "forms": ("ताजमहल", "ताज महल"), "en": "Taj Mahal", "india": False,
     "not_before": ("पैलेस", "होटल")},
    {"hi": "राम मंदिर", "forms": ("राम मंदिर", "अयोध्या राम मंदिर"), "en": "Ram Mandir", "india": True,
     "needs": ("अयोध्या",)},
    {"hi": "वंदे भारत", "forms": ("वंदे भारत", "वंदे भारत एक्सप्रेस", "वंदे भारत ट्रेन", "वंदे भारत ट्रेनों"),
     "en": "Vande Bharat Express", "india": True, "stand_in": True,
     "not_before": ("मिशन", "अभियान", "उड़ान", "उड़ानों", "फ्लाइट")},
    {"hi": "बाघ", "forms": ("बाघ", "बाघों", "बाघिन", "बाघिनों"), "en": "Bengal tiger", "india": False, "stand_in": True,
     "not_before": ("बकरी", "एक्सप्रेस", "मेल", "एक्सप्रेसवे")},
    {"hi": "तेंदुआ", "forms": ("तेंदुआ", "तेंदुए", "तेंदुओं"), "en": "Indian leopard", "india": False, "stand_in": True},
    {"hi": "हाथी", "forms": ("हाथी", "हाथियों"), "en": "Indian elephant", "india": False, "stand_in": True,
     "not_after": ("सफेद", "सफ़ेद")},
    # The vehicles the news names every day (owner, 2026-10-23: "if it is talking about train then train image should
    # be displayed, if talking about flight then flight must be displayed"). Stand-ins: a free photo of the kind of
    # thing, never the one in the story, so each says so on screen (STAND_IN) and the script's own vehicle, when
    # Wikipedia has it, takes these words instead (visuals.cast_for: "cls", what its description must say). Files
    # checked by eye on Commons, 2026-10-23 (licences re-read at runtime by media.picks); an aircraft, never an
    # airline's own: "एयर इंडिया का विमान" is a plane, and an airline is a brand (WORK). India: an Indian train or bus,
    # never under "पाकिस्तान में ट्रेन हाईजैक". not_after also reads "X के/की/का" ("पानी के टैंकर" is a lorry,
    # "नौसेना के जहाज" a warship).
    {"hi": "ट्रेन", "forms": ("ट्रेन", "ट्रेनें", "ट्रेनों", "रेलगाड़ी", "रेलगाड़ियां", "रेलगाड़ियों", "यात्री ट्रेन",
                            "मालगाड़ी"),
     "en": "Train", "india": True, "stand_in": True, "cls": r"\b(?:train|locomotive|multiple unit|railcar)\b",
     "not_before": ("मिशन", "अभियान"), "not_after": ("भारत", "मेट्रो", "बुलेट", "खिलौना"),
     "files": ("File:SNSI - COA Exp. (29778715606).jpg", "File:Ramgiri Pass. (32683016748).jpg",
               "File:12717 Ratnachal Express at Marripalem 04.jpg")},
    {"hi": "विमान", "forms": ("विमान", "विमानों", "फ्लाइट", "फ्लाइट्स", "फ़्लाइट", "फ़्लाइट्स", "उड़ान", "उड़ानें",
                             "उड़ानों", "हवाई जहाज", "हवाई जहाज़", "हवाई जहाजों", "हवाई जहाज़ों", "प्लेन", "यात्री विमान"),
     "en": "Airplane", "india": False, "stand_in": True,
     "cls": r"\b(?:airliner|aeroplane|airplane|aircraft(?! carrier)|jet airliner|aircraft type)\b",
     "not_before": ("योजना", "स्कीम", "मिशन", "अभियान"),
     "not_after": ("लड़ाकू", "जंगी", "सैन्य", "टोही", "ड्रोन", "सपनों", "ऊंची", "नई"),
     "files": ("File:Airbus A380.jpg", "File:ANA Cargo, Frankfurt am Main (P1090462).jpg")},
    {"hi": "जहाज", "forms": ("जहाज", "जहाज़", "जहाजों", "जहाज़ों", "पोत", "पोतों", "मालवाहक जहाज", "कार्गो जहाज",
                           "मालवाहक पोत"),
     "en": "Ship", "india": False, "stand_in": True,
     "cls": r"\b(?:ship|vessel|tanker|aircraft carrier|frigate|destroyer|corvette|warship|submarine|ferry)\b",
     "not_after": ("हवाई", "जंगी", "नौसेना", "नौसैनिक", "युद्ध"),
     "files": ("File:Container ship in Koper 2013.jpg", "File:00 0883 Container Ship MARUS.jpg")},
    {"hi": "तेल टैंकर", "forms": ("तेल टैंकर", "तेल टैंकरों", "टैंकर जहाज", "टैंकर", "टैंकरों", "ऑयल टैंकर"),
     "en": "Oil tanker", "india": False, "stand_in": True, "cls": r"\b(?:tanker|oil tanker|crude carrier)\b",
     "not_after": ("पानी", "दूध", "गैस", "एलपीजी", "डीजल", "पेट्रोल", "केमिकल", "हवाई"),
     "files": ("File:Tanker Destine.JPG", "File:Euronav tanker on the Saint Lawrence at Quebec City.jpg")},
    {"hi": "हेलीकॉप्टर", "forms": ("हेलीकॉप्टर", "हेलिकॉप्टर", "हेलीकाप्टर", "हेलीकॉप्टरों", "हेलिकॉप्टरों", "चॉपर"),
     "en": "Helicopter", "india": False, "stand_in": True, "cls": r"\bhelicopter\b",
     "files": ("File:Tengboche, Helicopter in flight, Mountains of Nepal.jpg",
               "File:Airbus Helicopters EC725 Super Cougar in Brazilian flight in recife bay.jpg")},
    {"hi": "मिसाइल", "forms": ("मिसाइल", "मिसाइलों", "मिसाइलें"), "en": "Missile", "india": False, "stand_in": True,
     "cls": r"\b(?:missile|rocket)\b", "not_before": ("मैन",),  # "मिसाइल मैन" is Abdul Kalam
     "files": ("File:USS Lake Erie (CG 70) missile test.jpg", "File:Pershing II missile test launch in 1982.JPEG")},
    # Never a bare "बस": it is "just" far more often than a bus.
    {"hi": "बसें", "forms": ("बसें", "बसों", "सरकारी बस", "रोडवेज बस", "यात्री बस", "बस हादसा", "बस हादसे",
                           "बस दुर्घटना", "बस पलटी", "बस खाई"),
     "en": "Bus", "india": True, "stand_in": True, "cls": r"\bbus\b",
     "files": ("File:Telangana State Road Transport Corporation bus.jpg", "File:APSRTC Bus 07122014.jpg")},
    {"hi": "पद्म श्री", "forms": ("पद्म श्री", "पद्मश्री"), "en": "Padma Shri", "india": True},
    # Rivers the news names by their own name ("यमुना सफाई", dry run 39794659993: the Yamuna was said and never
    # shown). Yamuna's Wikidata image includes the Taj Mahal: these Delhi photos were checked by eye (2026-10-23).
    {"hi": "यमुना", "forms": ("यमुना", "यमुना नदी"), "en": "Yamuna", "india": False,
     "not_before": ("एक्सप्रेसवे", "एक्सप्रेस-वे", "एक्सप्रेस", "विहार", "नगर", "बैंक", "पुश्ता", "प्राधिकरण", "अथॉरिटी"),
     "files": ("File:Sasha India, Yamuna river, view from Majnu-ka-tilla (2).jpg", "File:Seagulls at Yamuna 1.jpg",
               "File:Delhi-Huetten am Yamuna-06-Sonnenaufgang-2016-gje.jpg")},
    {"hi": "गंगा", "forms": ("गंगा", "गंगा नदी"), "en": "Ganges", "india": False,
     "not_before": ("एक्सप्रेसवे", "एक्सप्रेस-वे", "एक्सप्रेस", "देवी", "प्रसाद", "राम", "नगर", "विहार", "सिंह"),
     "not_after": ("मां", "माँ")},
    # What price news names every day (owner, 2026-10-29, on 9MrOG5OYxdc, "Nandini milk ₹8 costlier" over a map of
    # Karnataka: "where is the milk picture"). Files checked by eye on Commons, 2026-10-29. Nandini is the story's own
    # product, a packet and a booth, only beside the milk it sells; सोना alone is also "to sleep", so gold is matched
    # only in its price phrases.
    {"hi": "नंदिनी", "forms": ("नंदिनी", "नंदिनी दूध", "नंदिनी ब्रांड"), "en": "Karnataka Milk Federation",
     "india": True, "needs": ("दूध",),
     "files": ("File:Kmfmilkcurd1.jpg", "File:Milk Booth Nandini Siddhartha Mysore May24 A7CR 00081-2 Pano.jpg")},
    {"hi": "दूध", "forms": ("दूध", "दूध के", "दूध की", "दूध का", "पैकेट वाला दूध", "पैकेट दूध"), "en": "Milk",
     "india": False, "stand_in": True, "not_before": ("टैंकर", "टैंकरों"),
     "files": ("File:India - Kolkata milkman - 4090.jpg", "File:A Milkmans cycle, Varanasi.jpg")},
    # Owner, 2026-10-29: "why kisan picture is not visible" (the same Short: "किसानों ने 10 रुपये की बढ़ोतरी माँगी").
    # People seen from afar or from behind only: a stand-in never features a face.
    {"hi": "डेयरी", "forms": ("डेयरी", "डेयरी कोऑपरेटिव", "डेयरी कोऑपरेटिव्स", "दुग्ध संघ", "दुग्ध उत्पादक", "दूध उत्पादक",
                            "दूध उत्पादकों", "पशुपालक", "पशुपालकों", "डेयरी किसान", "डेयरी किसानों"),
     "en": "Dairy farming", "india": False, "stand_in": True,
     "files": ("File:Cow Milking.jpg", "File:Cow milking, near Mehsana, Gujarat, India.jpg")},
    {"hi": "किसान", "forms": ("किसान", "किसानों", "किसानो", "अन्नदाता"), "en": "Farmer", "india": False,
     "stand_in": True, "not_before": ("सम्मान", "निधि", "क्रेडिट", "आंदोलन", "नेता", "मोर्चा", "यूनियन"),
     "files": ("File:Women Farmers Sowing in Karnataka, India.jpg", "File:Anegundi - Rice Farmers - 1.jpg",
               "File:Indian farmers.jpg")},
    {"hi": "रसोई गैस", "forms": ("रसोई गैस", "एलपीजी", "एलपीजी सिलेंडर", "गैस सिलेंडर", "गैस सिलेंडरों", "सिलेंडर",
                               "सिलेंडरों", "LPG"),
     "en": "Liquefied petroleum gas", "india": True, "stand_in": True, "not_before": ("टैंकर", "टैंकरों", "विस्फोट"),
     "files": ("File:Cylinder,gas, LPG,bharat,Tamil Nadu457.jpeg", "File:Kitchen-LPG cooking gas cylinder.JPG",
               "File:LPG cylinder (2013).jpg")},
    {"hi": "पेट्रोल", "forms": ("पेट्रोल", "डीजल", "डीज़ल", "पेट्रोल-डीजल", "पेट्रोल-डीज़ल", "पेट्रोल पंप", "पेट्रोल पंपों"),
     "en": "Gasoline", "india": False, "stand_in": True, "not_before": ("टैंकर", "टैंकरों", "बम"),
     "files": ("File:Fueling Car.jpg", "File:Shankar Nagar Petrol Pump, Nagpur.jpg")},
    {"hi": "सोना", "forms": ("सोने का भाव", "सोने के भाव", "सोने की कीमत", "सोने के दाम", "सोना महंगा", "सोना सस्ता",
                           "सोने-चांदी", "सोना-चांदी", "सोने के गहने", "गोल्ड"),
     "en": "Gold", "india": False, "stand_in": True,
     "files": ("File:Bridal gold jewellery in Bangladeshi wedding.jpg",)},
    {"hi": "प्याज", "forms": ("प्याज", "प्याज़"), "en": "Onion", "india": False, "stand_in": True,
     "files": ("File:India - Koyambedu Market - Onions 08 (3987045248).jpg",
               "File:India - Koyambedu Market - Onions 06 (3987043646).jpg")},
    {"hi": "टमाटर", "forms": ("टमाटर", "टमाटरों"), "en": "Tomato", "india": False, "stand_in": True,
     "files": ("File:India - Koyambedu Market - Tomatoes 02 (3987058522).jpg",
               "File:India - Koyambedu Market - Tomatoes 06 (3986306253).jpg")},
)
# What may stand before an india form as "X की/के/का": India itself, never another country ("पोलैंड की संसद").
BY_INDIA = ("भारत", "देश", "हिंदुस्तान", "हिन्दुस्तान", "इंडिया", "हमारे", "हमारी", "हमारा", "अपने", "अपनी", "अपना", "दिल्ली",
            "केंद्र", "सरकार")
# A country's adjective right before a word every country uses ("पोलिश संसद", "यूरोपीय संसद", "कनाडाई संसद").
FOREIGN_ADJ = re.compile(r"(?:ीय|िश|ियन|ाई|ेनी|ाली)$")
INDIAN_ADJ = {"भारतीय", "केंद्रीय", "राष्ट्रीय", "स्थानीय", "क्षेत्रीय", "संसदीय", "भाई"}
# The Indian titles a FIGURE goes by when the story is about them ("गृह मंत्री ने यमुना सफाई ...", dry run
# 39794659993: Amit Shah's beat showed a card over Rahul Gandhi). Only for the story's subject (visuals.titles), and
# never after "X के" or a foreign word (match.names: "पोलैंड के प्रधानमंत्री" is Tusk) or "पूर्व" (a former one).
ROLES = {"Narendra Modi": ("प्रधानमंत्री", "प्रधान मंत्री", "पीएम"),
         "Amit Shah": ("गृह मंत्री", "गृहमंत्री", "केंद्रीय गृह मंत्री"),
         "S. Jaishankar": ("विदेश मंत्री",), "Rajnath Singh": ("रक्षा मंत्री",),
         "Nirmala Sitharaman": ("वित्त मंत्री",), "Droupadi Murmu": ("राष्ट्रपति",)}
# People the news names in nearly every Indian story, by their full Hindi names (never a bare surname: "ललित मोदी"),
# in case the script's names list leaves them out. Dry run 39817474353 (Donald Tusk in Delhi, 2026-10-22) said
# "प्रधानमंत्री नरेंद्र मोदी" in all five beats, listed only Tusk, Poland and New Delhi, and showed Modi in none.
FIGURES = (
    ("Narendra Modi", ("नरेंद्र मोदी", "नरेन्द्र मोदी", "प्रधानमंत्री मोदी", "पीएम मोदी")),
    ("Amit Shah", ("अमित शाह", "गृह मंत्री शाह")),
    ("Rahul Gandhi", ("राहुल गांधी", "राहुल गाँधी")),
    ("Droupadi Murmu", ("द्रौपदी मुर्मू", "राष्ट्रपति मुर्मू")),
    ("Rajnath Singh", ("राजनाथ सिंह",)),
    ("S. Jaishankar", ("एस जयशंकर", "एस. जयशंकर", "विदेश मंत्री जयशंकर")),
    ("Nirmala Sitharaman", ("निर्मला सीतारमण",)),
    ("Yogi Adityanath", ("योगी आदित्यनाथ",)),
    ("Mallikarjun Kharge", ("मल्लिकार्जुन खड़गे", "मल्लिकार्जुन खरगे")),
    ("Sonia Gandhi", ("सोनिया गांधी", "सोनिया गाँधी")),
    ("Priyanka Gandhi", ("प्रियंका गांधी", "प्रियंका गाँधी")),
    ("Arvind Kejriwal", ("अरविंद केजरीवाल",)),
    ("Mamata Banerjee", ("ममता बनर्जी",)),
    ("Nitish Kumar", ("नीतीश कुमार",)),
    ("Devendra Fadnavis", ("देवेंद्र फडणवीस", "देवेन्द्र फडणवीस")),
)


def figures_said(beats: list[dict]) -> list[dict]:
    """The FIGURES the beats name, as script names: [{"en", "hi", "alias"}], hi the form first said."""
    out = []
    for en, forms in FIGURES:
        hits = sorted((at, w) for w in forms for b in beats if (at := said_at(b.get("say") or "", (w,))) >= 0)
        if hits:
            hi = hits[0][1]
            out.append({"en": en, "hi": hi, "alias": [w for w in forms if w != hi]})
    return out


# A country, its people or its adjective (Hindi spellings the news uses; review round 1 found "इजरायल", "पोलैंड",
# "यूरोपीय", "इटली" and "दक्षिण कोरिया" missing): right before a thing it is another country's ("अमेरिकी सुप्रीम
# कोर्ट", "ब्रिटेन की संसद"), and anywhere earlier in the beat it makes an india form another country's.
FOREIGN = ("अमेरिका", "अमेरिकी", "अमरीका", "अमरीकी", "यूएस", "US", "पाकिस्तान", "पाकिस्तानी", "पाक", "ब्रिटेन", "ब्रिटिश", "इंग्लैंड",
           "चीन", "चीनी", "रूस", "रूसी", "नेपाल", "नेपाली", "बांग्लादेश", "बांग्लादेशी", "श्रीलंका", "श्रीलंकाई", "इजराइल",
           "इज़राइल", "इजरायल", "इज़रायल", "इस्राइल", "इसराइल", "इजरायली", "इज़रायली", "इजराइली", "ईरान", "ईरानी", "इराक",
           "इराकी", "जापान", "जापानी", "कनाडा", "कनाडाई", "फ्रांस", "फ्रांसीसी", "फ्रेंच", "जर्मनी", "जर्मन", "यूक्रेन", "यूक्रेनी",
           "पोलैंड", "पोलिश", "यूरोप", "यूरोपीय", "यूरोपियन", "इटली", "इतालवी", "इटैलियन", "स्पेन", "स्पेनिश", "पुर्तगाल",
           "नीदरलैंड", "बेल्जियम", "स्वीडन", "स्वीडिश", "नॉर्वे", "डेनमार्क", "फिनलैंड", "स्विट्जरलैंड", "ऑस्ट्रिया", "ग्रीस",
           "हंगरी", "तुर्की", "तुर्किये", "कोरिया", "कोरियाई", "दक्षिण कोरिया", "उत्तर कोरिया", "ताइवान", "सिंगापुर", "मलेशिया",
           "इंडोनेशिया", "थाईलैंड", "वियतनाम", "फिलीपींस", "अफगानिस्तान", "अफ़ग़ानिस्तान", "अफगान", "ऑस्ट्रेलिया",
           "ऑस्ट्रेलियाई", "न्यूजीलैंड", "दक्षिण अफ्रीका", "अफ्रीका", "अफ्रीकी", "नाइजीरिया", "केन्या", "मिस्र", "सऊदी",
           "सऊदी अरब", "यूएई", "कतर", "कुवैत", "ओमान", "बहरीन", "सीरिया", "लेबनान", "जॉर्डन", "यमन", "फलस्तीन",
           "फिलिस्तीन", "फिलिस्तीनी", "गाजा", "ब्राजील", "ब्राज़ील", "अर्जेंटीना", "मेक्सिको", "मालदीव", "भूटान", "म्यांमार",
           "विदेशी",
           # Foreign capitals and big cities the Hindi news names alone ("ढाका में सुप्रीम कोर्ट ने ...", "काठमांडू में
           # संसद भवन में आग", review round 2 put India's Supreme Court and Parliament there).
           "ढाका", "इस्लामाबाद", "लाहौर", "कराची", "रावलपिंडी", "पेशावर", "काठमांडू", "काठमांडो", "कोलंबो", "थिम्पू",
           "काबुल", "लंदन", "वॉशिंगटन", "वाशिंगटन", "न्यूयॉर्क", "न्यूयार्क", "बीजिंग", "मॉस्को", "मास्को", "तेहरान",
           "दुबई", "अबू धाबी", "रियाद", "तेल अवीव", "यरुशलम", "येरुशलम", "पेरिस", "बर्लिन", "टोक्यो", "सियोल",
           "कीव", "ओटावा", "टोरंटो", "सिडनी", "मेलबर्न", "वारसॉ", "वारसा", "ब्रसेल्स", "जिनेवा", "बैंकॉक", "यंगून")
# What an English article about a thing says it is (its Wikidata description).
THING = re.compile(r"\b(ship|vessel|tanker|aircraft|airliner|helicopter|fighter|jet|submarine|aircraft carrier|"
                   r"frigate|destroyer|corvette|warship|train|locomotive|missile|rocket|launch vehicle|rifle|tank|"
                   r"vehicle|automobile|motorcycle|species|subspecies|breed|animal|mammal|bird|reptile|fish|dish|food|"
                   r"sweet|dessert|bread|beverage|civilian award|gallantry award|military award|medal|decoration|"
                   r"national flag|flag of|monument|memorial|building|bridge|dam|fort|fortress|palace|temple|mosque|"
                   r"church|gurdwara|stadium|statue|tower|parliament|courthouse)\b", re.I)
# Never a thing with a picture: works (their pictures are covers and posters), bodies whose pictures are logos, and
# brands: an airline ("flag carrier of India") is a company in its livery, and an award's statuette (a Grammy) is a
# copyrighted sculpture (review round 1).
WORK = re.compile(r"\b(film|movie|album|song|single|book|novel|series|television|TV|show|painting|magazine|"
                  r"newspaper|journal|company|organi[sz]ation|political party|party|brand|band|video game|game|"
                  r"software|website|app|application|logo|manufacturer|corporation|business|startup|conglomerate|"
                  r"agency|ministry|department|union|association|club|team|league|government|court case|case|"
                  r"election|event|protest|scheme|programme|program|law|act|bill|airline|flag carrier|operator|"
                  r"franchise|music award|film award|award for|statuette|trophy)\b", re.I)
# A file that shows a work, a logo or a screen, never the thing: a book cover, a poster, an app's screenshot.
NOT_THING = re.compile(r"\b(cover|poster|album|screenshot|screen ?shot|logo|wordmark|trademark|paintings?|"
                       r"drawings?|illustrations?|cartoons?|render(?:ing)?|model kit|toy|stamp|coin|banknote|tweet|"
                       r"instagram|facebook|miniature|watercolou?r|engraving|lithograph|artworks?|mughal art|"
                       r"company painting|statuette)\b", re.I)
# Before photographs were common, a picture of a thing is a painting or an engraving (the Red Fort's Commons category
# gave a Ghulam Ali Khan painting of 1852): a Short shows a photo of the thing as it is.
PHOTO_YEAR = 1900


def _foreign(word: str) -> bool:
    w = hindi.norm(word)
    return any(w == hindi.norm(f) for f in FOREIGN)


def foreign_before(say: str, at: int) -> bool:
    """A country or its adjective stands right before `at` in say, or as "X की/के/का" before it."""
    head = re.sub(r"\s+(?:की|के|का)\s*$", " ", say[:at].rstrip() + " ").rstrip()
    return any(hindi.norm(head).endswith(hindi.norm(w)) and hindi.find(head, w.split()[-1]) >= 0 for w in FOREIGN)


def abroad(say: str, at: int, by=()) -> bool:
    """A word every country uses at `at` (an india form) is another country's: foreign_before, any FOREIGN word
    earlier in the beat ("ईरान में ... राष्ट्रीय ध्वज"), "X की/के/का" before it for an X that is not India's (BY_INDIA,
    or by: "अयोध्या के राम मंदिर"), or a country's adjective right before it ("पोलिश संसद", "यूरोपीय संसद")."""
    head = say[:at]
    if foreign_before(say, at) or any(hindi.find(head, w) >= 0 for w in FOREIGN):
        return True
    words = re.findall(r"[\u0900-\u097F]+", head)
    if len(words) >= 2 and words[-1] in ("की", "के", "का"):
        return hindi.norm(words[-2]) not in {hindi.norm(w) for w in (*BY_INDIA, *by)}
    return bool(words) and words[-1] not in INDIAN_ADJ and bool(FOREIGN_ADJ.search(words[-1])) \
        and words[-1] not in hindi.FUNCTION_WORDS


def _entry(en: str) -> dict | None:
    return next((e for e in LEXICON if e["en"] == en), None)


def _neighbours(say: str, at: int, form: str) -> tuple[str, str]:
    """The words right before and right after the form said at `at`."""
    before = re.findall(r"[\u0900-\u097F]+", say[:at])
    after = re.findall(r"[\u0900-\u097F]+", say[at + len(form):])
    return (before[-1] if before else ""), (after[0] if after else "")


def _owner(say: str, at: int) -> str:
    """X in "X के/की/का <form>" (and "X के एक <form>"), else ""."""
    words = re.findall(r"[\u0900-\u097F]+", say[:at])
    if words and words[-1] == "एक":
        words = words[:-1]
    return words[-2] if len(words) >= 2 and words[-1] in ("की", "के", "का") else ""


def blocked(say: str, at: int, en: str = "", form: str = "") -> bool:
    """Whether the thing said at `at` is not this thing: another country's (foreign_before; for an india or generic
    form also abroad), an idiom or a brand by the word beside it (not_before, not_after), or a beat without the word
    it needs. en: the thing's English name, for its LEXICON entry; form: the words said there (else the entry's
    longest form said at `at`). A thing with no entry is refused only after a foreign country's name."""
    from .visuals import _finds

    e = _entry(en)
    if e is None:
        return foreign_before(say, at)
    if not form:
        form = max((f for f in e["forms"] if at in _finds(say, f)), key=len, default=e["hi"])
    local = e["india"] or hindi.norm(form) in {hindi.norm(f) for f in e.get("generic") or ()}
    # Any country's missile is a missile: a stand-in of the world is never refused by whose it is.
    if foreign_before(say, at) and (local or not e.get("stand_in")) or local and abroad(say, at, e.get("needs") or ()):
        return True
    before, after = _neighbours(say, at, form)
    if after and any(hindi.norm(after) == hindi.norm(w) for w in e.get("not_before") or ()):
        return True
    if any(w and any(hindi.norm(w) == hindi.norm(x) for x in e.get("not_after") or ()) for w in (before, _owner(say, at))):
        return True
    return any(hindi.find(say, w) < 0 for w in e.get("needs") or ())


def said_at(say: str, forms) -> int:
    """Where say first names one of forms as whole words, never after a foreign country's name, else -1."""
    from .visuals import _finds

    hits = [a for w in forms for a in _finds(say, w) if not foreign_before(say, a)]
    return min(hits, default=-1)


def entry_at(say: str, e: dict) -> int:
    """Where say first names a LEXICON entry as that thing (blocked never), else -1."""
    from .visuals import _finds

    return min((a for w in e["forms"] for a in _finds(say, w) if not blocked(say, a, e["en"], w)), default=-1)


def lexicon_hits(beats: list[dict], india: bool) -> list[dict]:
    """The LEXICON entries the beats name: [{"en", "hi", "kind": "thing", "alias", "files"}]. An india entry, and
    an entry's generic forms, only in an Indian story."""
    out = []
    for e in LEXICON:
        if e["india"] and not india:
            continue
        mine = e if india else e | {"forms": tuple(f for f in e["forms"] if f not in (e.get("generic") or ()))}
        if any(entry_at(b.get("say") or "", mine) >= 0 for b in beats):
            out.append({"en": e["en"], "hi": e["hi"], "kind": "thing", "title": e["en"],
                        "alias": [f for f in mine["forms"] if f != e["hi"]], "files": list(e.get("files") or ()),
                        **({"stand_in": True, "cls": e.get("cls") or ""} if e.get("stand_in") else {})})
    return out


# A stand-in's label (Matlabnama audit R2, 2026-10-23): a free photo of the kind of thing a beat names (a train, a
# plane), never the one in the story, says so on screen beside its credit and in the description's credits, as
# Hindi news labels a file photo. match.problems refuses a stand-in shown without it.
STAND_IN = "प्रतीकात्मक तस्वीर"


def label(p: dict) -> dict:
    """A stand-in photo row, labelled once: "stand_in" stamped and STAND_IN before its credit."""
    if p.get("stand_in") and (p.get("credit") or "").startswith(STAND_IN):
        return p
    return p | {"stand_in": True, "credit": f"{STAND_IN} · {p.get('credit') or ''}"}


def roles(subject_hi: str) -> tuple[str, ...]:
    """The ROLES of the FIGURE whose Hindi name is subject_hi, else ()."""
    name = hindi.norm(subject_hi or "")
    for en, forms in FIGURES:
        if name and any(hindi.norm(f) == name for f in forms):
            return ROLES.get(en, ())
    return ()


def thing_like(ent: dict) -> bool:
    """A thing with a picture of its own (THING), never a work, a body or a brand (WORK), a person, a place a map
    shows (coordinates with people) or a disambiguation page."""
    kinds = {c["value"] for c in wiki.claims(ent, "P31")}
    if wiki.HUMAN in kinds or wiki.DISAMBIGUATION in kinds or wiki.claims(ent, "P1082"):
        return False
    desc = ((ent.get("descriptions") or {}).get("en") or {}).get("value", "")
    return bool(THING.search(desc)) and not WORK.search(desc)


def resolve_thing(en: str) -> tuple[str, str, dict] | None:
    """(QID, title, item) for the English Wikipedia article titled exactly `en` when it is a thing (thing_like)."""
    try:
        page = wiki.page_info([en]).get(en) or {}
        ent = wiki.entities([page["qid"]]).get(page["qid"]) if page.get("qid") else None
    except Exception:
        return None
    return (page["qid"], page.get("title") or en, ent) if ent and thing_like(ent) else None


def lookup(entry: dict) -> dict | None:
    """A lexicon entry with its Wikidata item ({qid, ent} added), or None when Wikipedia has no such article."""
    try:
        page = wiki.page_info([entry["en"]]).get(entry["en"]) or {}
        ent = wiki.entities([page["qid"]]).get(page["qid"]) if page.get("qid") else None
    except Exception as exc:
        log.info("things: %s not looked up (%s)", entry["en"], exc)
        return None
    if not ent:
        return None
    return entry | {"qid": page["qid"], "title": page.get("title") or entry["en"], "ent": ent}


def has_picture(c: dict) -> bool:
    """Whether a thing could be shown, without a Commons download (visuals.showable): an editor's photos, or a
    Wikidata image that is a photo (P18 not a drawing)."""
    if c.get("files"):
        return True
    return any(not media.NOT_PHOTO.search(v["value"]) for v in wiki.claims(c.get("ent") or {}, "P18"))


def photos(c: dict, folder: Path, exclude: set[str], recent: set[str] | None = None,
           keep: int = THING_PHOTOS) -> list[dict]:
    """A thing's own free Commons photos: the editor's files, then its Wikidata image and Commons category (media's
    licence, size and decency checks, each with its author's credit), never a work, a logo or a screen (NOT_THING),
    never one with a featured face. Its Hindi name on screen; role "thing"."""
    import cv2

    from . import faces, visuals, writer

    found = media.picks(c["files"], limit=keep + 2) if c.get("files") else []
    if len(found) < keep and c.get("ent"):
        found += [p for p in media.find(c["title"], c["ent"], limit=keep + 2, exclude=exclude)
                  if p.file not in {f.file for f in found}]
    found = [p for p in found if p.file not in (exclude or set())
             and not NOT_THING.search(f"{p.file} {p.description} {p.categories}")
             and not (p.year and p.year < PHOTO_YEAR) and (c.get("statue") or not media.NOT_PERSON.search(p.file))
             and not media.branded(p)]
    out = []
    for r in visuals.fresh_first(media.as_dicts(media.download(found, folder)), recent):
        img = cv2.imread(r["path"])
        if img is None or writer.featured_face(img, faces.detect(img)):
            continue
        row = r | {"focus": None, "role": "thing", "who": c["hi"]}
        out.append(label(row) if c.get("stand_in") else row)
    return out[:keep]
