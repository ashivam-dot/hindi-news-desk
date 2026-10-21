"""The editorial desk: which story to make next, and whether the channel may publish now.

The channel covers what India and the world are already looking at (see CHANNEL.md): incidents, protests and
movements that newsrooms lead with, famous deaths, and big earthquakes. India stories come first, then world stories
with an India connection, then the rest.

Timing is the channel: a story goes out while people are looking at it, not hours later. Priority is fame (Google
News lead stories in English and Hindi, Google Trends traffic, Wikipedia views) decayed by age, times the India boost,
so a fresh story beats a bigger stale one, times its place in Google News India's top stories (desk/top.py); a story
in none of those lists, not searched in India, not breaking and not very famous (an explainer's fame only counts
headlines, so it never counts as famous) is dropped (unpopular), and so is a world explainer the Hindi lists do not
carry (White House, Pope and Starlink statements drew 0-35 views). A story Google News India leads with gets
follow-up parts (follow_up) from new reporting. A story older than STALE_H is dropped unless a live signal (Google Trends
traffic, or a lead headline under LIVE_NEWS_H old) shows it is trending right now; Wikipedia's most-read list is a
day behind and never keeps an old story alive. Regular Shorts go out 07:00-24:00 IST as soon as they are made, at
most MAX_PER_DAY an IST day (retired and replaced Shorts not counted) and MIN_GAP apart, EVENING_RESERVE of them kept
for after EVENING_IST; a case's angles at most CASE_MAX_PER_DAY a day and CASE_MAX_TOTAL in all. A breaking story
(huge fame or BREAKING_OWNERS independent outlets on one incident, and under 12 hours old, or a quake USGS
rates orange or red or magnitude 7+) goes out at any hour with no gap, up to BREAKING_EXTRA beyond the cap; wars never
take the breaking lane. An ongoing story comes back at most once in COOLDOWN_DAYS, however its id changes. No more
than two loss stories in any three consecutive uploads. Stories Orbitwire covers are skipped or told differently
(desk/orbitwire.py). A Short the owner wants made again (remakes/*.json) comes back while its story is still on the
radar, ahead of the other ready stories; once the new version is public the old one is made private.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import hindi, ledger, news, orbitwire, outlets, trends, usgs
from .stories import km_between

IST = timezone(timedelta(hours=5, minutes=30))
# YouTube refuses this channel's uploads past about ten a day ("exceeded the number of videos they may upload" after
# 10, 10 and 9 on 15-17 Oct 2026): the eleventh story was made and lost. Every upload counts, retired or not, and the
# regular and case lanes stop BREAKING_EXTRA short of it, so breaking news always has room. The desk counts IST days;
# YouTube's own day may start elsewhere (likely midnight Pacific), and that margin also covers the overlap.
YOUTUBE_DAILY_UPLOADS = 10
# Owner, 2026-10-21: "No need to cover each and every incidents but those which are really high profile cases or
# incidents those should be cover properly on time with max efforts." Fewer regular Shorts; the spare slots go to
# breaking news and to a big case's angles.
MAX_PER_DAY = 6
BREAKING_EXTRA = 2  # set to 0 to make MAX_PER_DAY a hard cap even for breaking news
MIN_GAP = timedelta(minutes=20)
BREAKING_GAP = timedelta(0)
BREAKING_FAME = 400_000
# Or this many independent outlets on one incident, BREAKING_STRONG of them official, public or international: a big
# story hours before Wikipedia's page views show it.
BREAKING_OWNERS, BREAKING_STRONG = 5, 2
BREAKING_MAX_AGE_H = 12
STALE_H = 48
LIVE_NEWS_H = 24
HALF_LIFE_H = {"death": 36, "protest": 18, "movement": 18, "conflict": 12, "earthquake": 18, "explainer": 10}
# One person or institution is explained at most once in this many hours, whatever the story.
EXPLAIN_REPEAT_H = 20
DEFAULT_HALF_LIFE_H = 24
WINDOW_IST = (7.0, 24.0)
INDIA_BOOST, LINK_BOOST = 1.6, 1.25
QUAKE_BIG_MAG = 7.0
COOLDOWN_DAYS = {"protest": 6, "movement": 6}
# Owner, 2026-10-15: only the most popular news. A story must be in Google News India's top stories (desk/top.py),
# trending in India's searches, breaking, or very famous; the higher its place, the sooner it goes out.
TOP_WEIGHT = 2.0
# Sport and film stories qualify only this high in the lists (about top 10 of a front page).
TOP_ONLY_SCORE = 0.55
# Any other story must be at least this high (about the top 13 of a front page, or a Nation section's top 9), and a
# kind Hindi viewers rarely watch (DEMAND under LOW_DEMAND) about the top 6.
MIN_PLACE, LOW_DEMAND, LOW_DEMAND_PLACE = 0.35, 0.8, 0.75
# What Hindi viewers watch, by kind: crime and security interest 84% of Hindi news users and entertainment 75%,
# business 38% (Google/Kantar 2023, n=4,622); on this channel a star's death (1,301 views) and political rows
# (596) led while economy, diplomacy and world explainers drew 10-60 (Oct 2026). Multiplies the ranking.
DEMAND = {"death": 1.4, "entertainment": 1.4, "attack": 1.4, "disaster": 1.3, "accident": 1.2, "aviation": 1.2,
          "rail": 1.2, "flood": 1.2, "earthquake": 1.2, "cyclone": 1.1, "politics": 1.1, "court": 1.0, "news": 1.0,
          "weather": 1.0, "sport": 1.0, "health": 0.9, "policy": 0.9, "defence": 0.9, "protest": 0.8,
          "movement": 0.8, "science": 0.7, "conflict": 0.7, "economy": 0.6, "diplomacy": 0.6, "world": 0.5}
# Ad suitability (2026-10-22, for YouTube's Partner Programme): advertisers avoid crime, court, communal and
# accident stories, so a story about them ranks at AD_SENSITIVE of its priority, and an economy, jobs, exams,
# schemes, tech-rules, infrastructure, science or neutral foreign-policy story at AD_FRIENDLY. A multiplier, never a
# ban, and breaking news is told whatever it is about. On this channel attack (median 85 views) and court (112)
# outdrew economy (29), so this trades a few views for ads; it stays mild. Sensitive wins when both match; a death
# is not sensitive unless it was an accident. Read from the title, story and headlines in English and Hindi.
AD_SENSITIVE, AD_FRIENDLY = 0.8, 1.2
AD_SENSITIVE_KINDS = ("attack", "explosion", "court", "accident")
AD_FRIENDLY_KINDS = ("economy", "science", "diplomacy", "policy")
# A Hindi word must start a word ("सोना" is not "सोनाक्षी") but may take any ending (हादसे, गिरफ्तारी), except
# where a longer word is another word: दौरान ("during", in most headlines) is no दौरा, दामाद no दाम, नियमित no नियम,
# and "दिल का दौरा" is a heart attack. English words that fit any story (talks, visits, prices, projects) need a
# pairing word; a market crash is economy, not an accident.
HI_START = r"(?<![\u0900-\u097F])"
AD_SENSITIVE_WORDS = re.compile(
    r"\b(shootings?|shot (dead|at)|firing|gunfire|gunned|gunmen|murder\w*|kill(ed|ing|ings)?|stabb\w*|"
    r"bomb\w*|blasts?|terror\w*|(?<!cardiac )arrest(s|ed)?|detain\w*|custody|bail|courts?|judges?|verdict|"
    r"chargesheet|communal|riots?|sectarian|blasphemy|desecrat\w*|lynch\w*|stone-pelting|violen(ce|t)|clash(es)?|"
    r"arson|accidents?|(?<!market )(?<!Sensex )(?<!Nifty )crash(es|ed)?|derail\w*|stampede|drown\w*|"
    r"(building|bridge|roof|wall) collapsed?|hit-and-run)\b"
    rf"|{HI_START}(गोली|फायरिंग|फ़ायरिंग|हत्या|हत्याकांड|मर्डर|चाकू|आतंक|धमाक|विस्फोट|गिरफ्तार|गिरफ़्तार|हिरासत|"
    r"जमानत|ज़मानत|अदालत|कोर्ट|हाईकोर्ट|सुनवाई|सांप्रदायिक|दंगा|दंगे|हिंसा|हिंसक|झड़प|आगजनी|पथराव|हादस|दुर्घटना|"
    r"भगदड़|डूबने|डूबकर)", re.I)
AD_FRIENDLY_WORDS = re.compile(
    r"\b(petrol|diesel|fuel prices?|gold (prices?|rates?)|GST|RBI|repo rate|EMI|(home|car|education|personal) loans?|"
    r"loan (rates?|waiver)|tax(es)?|income tax|budget|inflation|price (hike|cut|rise)s?|rupee|jobs?|recruitment|"
    r"vacanc(y|ies)|hiring|exams?|NEET|JEE|UPSC|SSC|CBSE|schemes?|yojana|pension|ration|subsidy|telecom|TRAI|5G|UPI|"
    r"Aadhaar|new rules?|metro|highway|expressway|airport|bridge|infrastructure|ISRO|space (mission|agency|station)|"
    r"satellite|science|research|summit|(state|official|bilateral) visits?|(trade|peace|bilateral|border) talks|"
    r"agreement|trade deal|tariffs?|treaty|MoU|GDP|economy|Sensex|internet|broadband|"
    r"(infrastructure|rail|road|power) projects?)\b"
    rf"|{HI_START}(पेट्रोल|डीजल|डीज़ल|सोने-चांदी|सोना-चांदी|सोने (का|के|की) (भाव|दाम|कीमत)|जीएसटी|आरबीआई|"
    r"रिज़र्व बैंक|रिजर्व बैंक|ईएमआई|लोन|टैक्स|आयकर|बजट|महंगाई|मुद्रास्फीति|कीमत(?!ी)|दाम(?!ाद|न)|नौकरी|"
    r"पदों पर भर्ती|भर्ती (परीक्षा|प्रक्रिया|अभियान)|परीक्षा|योजना|पेंशन|राशन|सब्सिडी|टेलीकॉम|यूपीआई|आधार कार्ड|"
    r"नियम(?!ित)|मेट्रो|हाईवे|एक्सप्रेसवे|एयरपोर्ट|इसरो|अंतरिक्ष|सैटेलाइट|विज्ञान|(?<!दिल का )दौर(ा(?!न)|े)(?! पड़)|"
    r"(विदेश|राजकीय|आधिकारिक) यात्रा|(शांति|द्विपक्षीय|सीमा) (वार्ता|बातचीत)|समझौत|शिखर सम्मेलन|टैरिफ|व्यापार|"
    r"जीडीपी|अर्थव्यवस्था|सेंसेक्स|इंटरनेट|परियोजना)", re.I)
# The day's biggest stories may be told in parts: a follow-up when the story is still this high, with reporting
# from at least two owners that no earlier part used, SERIES_GAP after the last part, up to SERIES_PARTS in all.
# Off 2026-10-18 (every part 2 drew 4-8 views while its first part drew 16-95); back on 2026-10-20 for outlet
# (nw-) stories too, owner: "this tiger shrof case is in very lime light you can cover multiple sories of it with
# facts". Each part leads with what is new; every fact still needs two owners.
SERIES_SCORE = 0.9
SERIES_PARTS = 4
SERIES_GAP = timedelta(hours=2)
# A case's angles go out ahead of other stories but this far apart, so the day's other news still runs between them.
# They may take the spare (breaking) slot, but never at night or within MIN_GAP: owner, 2026-10-20, of the Tiger
# Shroff case, "publish few more".
CASE_GAP = timedelta(minutes=30)
# One template on one case all day reads as mass-produced (review-latest.json, 2026-10-21: inauthentic risk "medium",
# eleven angles on the Tiger Shroff case): at most CASE_MAX_PER_DAY of a case's angles an IST day and CASE_MAX_TOTAL
# on the channel in all; the other angles wait. An angle made again replaces its old Short, so it is never over the
# total. Retired and replaced Shorts are not on the channel and do not count.
CASE_MAX_PER_DAY = 3
CASE_MAX_TOTAL = 6
# Hindi viewers watch most in the evening: before EVENING_IST the regular and case lanes leave EVENING_RESERVE of
# the day's MAX_PER_DAY slots free for it. Breaking news is not held.
EVENING_IST = 18.0
EVENING_RESERVE = 2


REMAKES = Path(__file__).resolve().parents[1] / "remakes"


def remakes(at: datetime | None = None) -> list[dict]:
    """Remake requests still current whose old video no published row has replaced yet. A request is
    {"story": published id, "replaces": its YouTube id, "until": ISO time, "why": text, optionally "draft": a
    reviewed script the writer checks first}."""
    at = at or datetime.now(timezone.utc)
    done = {r.get("replaces") for r in ledger.published()}
    specs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(REMAKES.glob("*.json"))]
    return [s for s in specs if s["replaces"] not in done
            and at < datetime.fromisoformat(s["until"].replace("Z", "+00:00"))]


CASES = Path(__file__).resolve().parents[1] / "cases"


def cases(at: datetime | None = None) -> list[dict]:
    """Case files still current: one story the channel follows angle by angle, each angle its own Short from
    reporting chosen for it ({"name", "story": an id of the story, "until", "cand": the story's radar candidate, used
    once it leaves the radar, "region" (the radar may call an Indian story "world"), "status": where the case stands
    now, which no angle may contradict, "names_ok": [...], "never": [an accused's
    or a gang's name, English and Hindi, the script may not contain], "angles": [{"key",
    "focus", "reports": [outlet items], "arrests": bool, "names_ok": [...], "words": [names the angle's excerpts
    keep sentences about], "hook": its opening card's Hindi line, a reported fact and never a question, optionally
    "replaces": the YouTube id of the angle's earlier Short, which a "<key>-r2" angle makes again, and "draft": a
    reviewed script the writer checks first}]})."""
    at = at or datetime.now(timezone.utc)
    specs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES.glob("*.json"))]
    return [s for s in specs if at < datetime.fromisoformat(s["until"].replace("Z", "+00:00"))]


def case_of(cand: dict, specs: list[dict]) -> dict | None:
    return next((s for s in specs if same_case(cand["id"], s["story"])), None)


def angles_of(cand: dict, specs: list[dict], rows: list[dict], at: datetime | None = None) -> list[dict]:
    """The angles of the case this candidate belongs to that are not on the channel yet, in the file's order; none
    until CASE_GAP after the case's last Short."""
    at = at or datetime.now(timezone.utc)
    for s in specs:
        if not same_case(cand["id"], s["story"]):
            continue
        gone = {r["replaced"] for r in rows if r.get("replaced")}
        told = sorted((r for r in rows if r.get("video_id") not in gone and (
            same_case(r["id"], s["story"]) or r.get("case") == s["name"])), key=lambda r: r["published_at"])
        if told and at - datetime.fromisoformat(told[-1]["published_at"].replace("Z", "+00:00")) < CASE_GAP:
            return []
        earlier = [r.get("title") or "" for r in told]
        live = on_channel([r for r in rows if same_case(r["id"], s["story"]) or r.get("case") == s["name"]])
        wait = case_wait(live, at)
        stem = SUFFIX.sub("", s["story"])
        never = s.get("never", [])
        # A headline naming an accused or a gang would steer the writer and the excerpts towards them.
        lines = {k: [h for h in cand[k] if not (isinstance(h, str) and any(hindi.contains(h, w) for w in never))]
                 for k in ("headlines", "hindi_headlines") if isinstance(cand.get(k), list)}
        where = {"region": s["region"]} if s.get("region") else {}
        return [cand | lines | where | {"id": f"{stem}-{a['key']}", "case": s["name"], "case_story": s["story"],
                                        "angle": a["key"], "focus": a["focus"], "reports": a["reports"],
                                        "arrests": bool(a.get("arrests")), "earlier": earlier,
                                        "names_ok": s.get("names_ok", []) + a.get("names_ok", []),
                                        "case_words": a.get("words", []), "never": never,
                                        "case_status": s.get("status"), "case_hurt": s.get("hurt"), "hook": a.get("hook")}
                | ({"replaces": a["replaces"], "remake_of": f"{stem}-{a['key'].removesuffix('-r2')}"}
                   if a.get("replaces") else {}) | ({"draft": a["draft"]} if a.get("draft") else {})
                | ({"case_wait": w} if (w := wait[0] or (None if a.get("replaces") else wait[1])) else {})
                for a in s["angles"] if not ledger.is_done(f"{stem}-{a['key']}")
                and not (a.get("replaces") and a["replaces"] in gone)]
    return []


def case_wait(live: list[dict], at: datetime) -> tuple[str | None, str | None]:
    """Why a case's next angle waits: (over the day's CASE_MAX_PER_DAY, over CASE_MAX_TOTAL), each None when it is
    not. `live` is the case's Shorts still on the channel; an angle made again is held only by the first."""
    day = [r for r in live if ist_day(datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))) == ist_day(at)]
    return (f"{len(day)} of the case's angles today (IST), {CASE_MAX_PER_DAY} a day" if len(day) >= CASE_MAX_PER_DAY
            else None,
            f"{len(live)} of the case's Shorts on the channel, {CASE_MAX_TOTAL} at most" if len(live) >= CASE_MAX_TOTAL
            else None)


def remake_of(cand: dict, specs: list[dict]) -> dict | None:
    """The candidate as the remake of a published Short, under a new id, so find() never takes the old upload for it."""
    for s in specs:
        if cand["id"] == s["story"] or outlets.same_story(cand["id"], s["story"]):
            new = cand["id"] + "-r2" if cand["id"] == s["story"] else cand["id"]
            return cand | {"id": new, "replaces": s["replaces"], "remake_of": s["story"]} \
                | ({"draft": s["draft"]} if s.get("draft") else {})
    return None


def ist_day(t: datetime) -> str:
    return t.astimezone(IST).date().isoformat()


def on_channel(rows: list[dict]) -> list[dict]:
    """The published rows still public: not retired (retire.json, once the ledger records it private) and not
    replaced by a remake, so a Short and its remake count once."""
    gone = {r["replaced"] for r in rows if r.get("replaced")}
    return [r for r in rows if not r.get("retired_at") and not (r.get("video_id") and r["video_id"] in gone)]


def can_publish(at: datetime | None = None, breaking: bool = False, spare: bool = False) -> str | None:
    """Why no Short may go out now, or None. A breaking story may take the spare slot at once; with `spare` (a case
    angle) it may take it MIN_GAP after the last Short. The daily cap counts the Shorts still on the channel; every
    upload, retired or not, counts toward YouTube's own limit, whose last BREAKING_EXTRA uploads only breaking news
    may take."""
    at = at or datetime.now(timezone.utc)
    rows = ledger.published()
    uploads = [r for r in rows if ist_day(datetime.fromisoformat(r["published_at"])) == ist_day(at)]
    if len(uploads) >= YOUTUBE_DAILY_UPLOADS:
        return f"already {len(uploads)} uploads today (IST), YouTube's limit"
    if not breaking and len(uploads) >= YOUTUBE_DAILY_UPLOADS - BREAKING_EXTRA:
        return (f"already {len(uploads)} uploads today (IST); the last {BREAKING_EXTRA} before YouTube's limit wait "
                "for breaking news")
    today = on_channel(uploads)
    if len(today) >= MAX_PER_DAY + (BREAKING_EXTRA if breaking or spare else 0):
        return f"already {len(today)} Shorts today (IST)"
    gap = BREAKING_GAP if breaking else MIN_GAP
    times = [datetime.fromisoformat(r["published_at"]) for r in rows]
    past, scheduled = [t for t in times if t <= at], [t for t in times if t > at]
    if past and at - max(past) < gap:
        return f"last Short went out {(at - max(past)).total_seconds() / 3600:.1f} h ago"
    if scheduled and min(scheduled) - at < gap:
        return f"a scheduled Short goes out in {(min(scheduled) - at).total_seconds() / 3600:.1f} h"
    local = at.astimezone(IST)
    if not breaking and local.hour + local.minute / 60 < EVENING_IST and len(today) >= MAX_PER_DAY - EVENING_RESERVE:
        return f"{len(today)} Shorts today; the last {EVENING_RESERVE} wait for {EVENING_IST:02.0f}:00 IST"
    return None


def age_hours(cand: dict, at: datetime) -> float:
    """Hours since the story broke. An ongoing story is as old as its newest lead headline; any other story is as old
    as the event itself, however fresh a follow-up headline is."""
    if cand.get("age_h") is not None:
        return float(cand["age_h"])
    ages = []
    if cand.get("news_at"):
        ages.append((at - datetime.fromisoformat(cand["news_at"])).total_seconds() / 3600)
    if cand.get("date") and cand.get("category") not in trends.ONGOING:
        day = datetime.fromisoformat(cand["date"]).replace(tzinfo=timezone.utc) + timedelta(hours=12)
        ages.append((at - day).total_seconds() / 3600)
    return max([0.0, *ages])


def boost(cand: dict) -> float:
    if cand.get("region") == "india":
        return INDIA_BOOST
    return LINK_BOOST if cand.get("india_link") else 1.0


def demand(cand: dict) -> float:
    return DEMAND.get(cand.get("category"), DEMAND.get(cand.get("kind"), 1.0))


def ad_text(cand: dict) -> str:
    return " ".join([cand.get("title") or "", cand.get("story") or ""] + list(cand.get("headlines") or [])[:6]
                    + list(cand.get("hindi_headlines") or [])[:6])


def ad_class(cand: dict) -> str | None:
    """"sensitive", "friendly" or None, for advertisers (see AD_SENSITIVE)."""
    text = ad_text(cand)
    if cand.get("category") in AD_SENSITIVE_KINDS or AD_SENSITIVE_WORDS.search(text):
        return "sensitive"
    return "friendly" if cand.get("category") in AD_FRIENDLY_KINDS or AD_FRIENDLY_WORDS.search(text) else None


def ad_factor(cand: dict, at: datetime) -> float:
    """AD_SENSITIVE or AD_FRIENDLY of the ranking, 1.0 for anything else and for breaking news."""
    if is_breaking(cand, at):
        return 1.0
    return {"sensitive": AD_SENSITIVE, "friendly": AD_FRIENDLY}.get(ad_class(cand), 1.0)


def ad_note(cands: list[dict], at: datetime | None = None) -> str | None:
    """The health line naming the candidates ad_factor moved, kept apart from lineup's hold notes so it never
    pushes one of them out of the health log."""
    at = at or datetime.now(timezone.utc)
    down = [c["id"] for c in cands if ad_factor(c, at) < 1]
    up = [c["id"] for c in cands if ad_factor(c, at) > 1]
    if not (down or up):
        return None
    return (f"ad-suitability x{AD_SENSITIVE} (crime, court, communal, accident; not breaking): "
            f"{', '.join(down[:6]) or '-'}; x{AD_FRIENDLY} (economy, jobs, schemes, tech, science, "
            f"diplomacy): {', '.join(up[:6]) or '-'}")[:400]


def priority(cand: dict, at: datetime) -> float:
    """Fame halved every half-life, times the India boost, the channel's own learned lift, what Hindi viewers watch
    and what advertisers accept: what this desk would lead with right now."""
    from . import learn

    half = HALF_LIFE_H.get(cand.get("kind"), HALF_LIFE_H.get(cand.get("category"), DEFAULT_HALF_LIFE_H))
    return cand.get("fame", 0) * 0.5 ** (age_hours(cand, at) / half) * boost(cand) * learn.factor(cand) \
        * demand(cand) * ad_factor(cand, at) * (1 + TOP_WEIGHT * (cand.get("top_score") or 0))


def unpopular(cand: dict, at: datetime) -> str | None:
    """Why a story is not top news for this channel, or None. A story the lists could not be read for (top None)
    is not judged."""
    from . import explain

    if cand.get("top") is None:
        return None
    place = cand.get("top_score") or 0
    if cand.get("category") in explain.TOP_ONLY:
        return None if place >= TOP_ONLY_SCORE else \
            f"a {cand['category']} story goes out only when it is a top-10 story (place {place:.2f})"
    if "IN" in (cand.get("geos") or []) and cand.get("traffic", 0) > 0 or is_breaking(cand, at):
        return None
    if cand.get("kind") != "explainer" and cand.get("fame", 0) >= BREAKING_FAME:
        return None
    if place <= 0:
        return "not in Google News India's top stories (English or Hindi), India's searches, breaking or famous"
    if cand.get("kind") == "explainer" and cand.get("region") != "india" \
            and not any(feed in news.HINDI_FEEDS for feed in cand["top"]):
        return "a world story Hindi newsrooms do not lead with (not in Google News India's Hindi top stories)"
    if place < MIN_PLACE:
        return f"too low in Google News India's top stories (place {place:.2f}, needs {MIN_PLACE})"
    if demand(cand) < LOW_DEMAND and place < LOW_DEMAND_PLACE:
        return (f"a {cand.get('category') or cand.get('kind')} story goes out only near the top of the lists "
                f"(place {place:.2f}, needs {LOW_DEMAND_PLACE})")
    return None


SUFFIX = re.compile(r"-[pr]\d+$")


def same_case(row_id: str, base: str) -> bool:
    """A published id is this story or one of its parts or remakes; an nw- story's date shifts between runs."""
    stem = SUFFIX.sub("", row_id)
    return stem == base or (base.startswith("nw-") and outlets.same_story(stem, base))


def follow_up(cand: dict, rows: list[dict], at: datetime) -> dict | None:
    """The next part of a story Google News India leads with (SERIES_SCORE), told from reporting no earlier part
    used, or None. A replaced version is not a part."""
    from . import gate

    base = cand["id"]
    if not base.startswith(("kh-", "nw-")) or (cand.get("top_score") or 0) < SERIES_SCORE:
        return None
    gone = {r["replaced"] for r in rows if r.get("replaced")}
    told = [r for r in rows
            if same_case(r["id"], base) or (r.get("case_story") and same_case(r["case_story"], base))]
    parts = sorted((r for r in told if r.get("video_id") not in gone), key=lambda r: r["published_at"])
    if not parts or len(parts) >= SERIES_PARTS:
        return None
    if at - datetime.fromisoformat(parts[-1]["published_at"]) < SERIES_GAP:
        return None
    used = {u for r in told for u in r.get("report_urls") or []}  # a replaced version was public too
    fresh = [r for r in cand.get("reports") or [] if r["url"] not in used]
    if len(outlets.owners(fresh)) < gate.OWNERS_NEEDED:
        return None
    n = len(parts) + 1
    return cand | {"id": f"{base}-p{n}", "part": n, "earlier": [r.get("title") or "" for r in parts],
                   "reports": fresh}


def is_breaking(cand: dict, at: datetime) -> bool:
    if age_hours(cand, at) > BREAKING_MAX_AGE_H or cand.get("category") == "conflict" or cand.get("kind") == "explainer":
        return False
    if cand.get("category") == "earthquake" and cand.get("mag"):
        return cand.get("mag", 0) >= QUAKE_BIG_MAG or (cand.get("alert") or "") in ("orange", "red")
    who = cand.get("owners") or []
    if cand.get("kind") == "incident" and cand.get("category") not in trends.ONGOING and len(who) >= BREAKING_OWNERS \
            and len(outlets.strong(who)) >= BREAKING_STRONG:
        return True
    return cand.get("fame", 0) >= BREAKING_FAME


def cooling(cand: dict, at: datetime, rows: list[dict]) -> bool:
    """True when this ongoing story already went out within its cool-down, under any id (weekly or series part)."""
    days = COOLDOWN_DAYS.get(cand.get("category"))
    if not days or not cand.get("qid"):
        return False
    stem = f"wk-{cand['qid']}"
    return any(r["id"] == stem or r["id"].startswith(stem + "-")
               for r in rows if at - datetime.fromisoformat(r["published_at"]) < timedelta(days=days))


TOLD_DAYS = 7


def told_before(cand: dict, rows: list[dict], at: datetime) -> bool:
    """True when this story went out in the last TOLD_DAYS under another id: first told from outlet reporting (nw-)
    and now from its Wikipedia article, or the other way round. One story shares a report URL, or its nw- ids name
    the same place and kind, or an nw- story's headlines name the article."""
    urls = {r["url"] for r in cand.get("reports") or []}
    for r in rows:
        age = at - datetime.fromisoformat(r["published_at"])
        if age > timedelta(days=TOLD_DAYS):
            continue
        if cand["id"].startswith("kh-") or r["id"].startswith("kh-"):
            if urls & set(r.get("report_urls") or []):
                return True
            if cand["id"].startswith("kh-") and cand.get("qid") and r.get("qid") == cand["qid"] \
                    and age < timedelta(hours=EXPLAIN_REPEAT_H):
                return True
            continue
        if not (r["id"].startswith("nw-") or cand["id"].startswith("nw-")):
            continue  # stories told from Wikipedia on both sides are matched by their ids already
        if urls & set(r.get("report_urls") or []) or outlets.same_story(cand["id"], r["id"]):
            return True
        if r.get("article") and r["article"] in (cand.get("title"), cand.get("article")):
            return True  # told from the reporting while its article was too new to use
        if r["id"].startswith("nw-") and not cand["id"].startswith("nw-"):
            heads, title = r.get("headlines") or [], cand.get("title")
        elif cand["id"].startswith("nw-") and not r["id"].startswith("nw-"):
            heads, title = cand.get("headlines") or [], r.get("article")
        else:
            continue
        if title and any(news.reverse(h, [news.pool_item(title)]) for h in heads):
            return True
    return False


def in_window(at: datetime) -> bool:
    local = at.astimezone(IST)
    hour = local.hour + local.minute / 60
    return WINDOW_IST[0] <= hour < WINDOW_IST[1]


def trending_live(cand: dict, at: datetime) -> bool:
    if cand.get("traffic", 0) > 0:
        return True
    news_at = cand.get("news_at")
    return bool(news_at) and (at - datetime.fromisoformat(news_at)).total_seconds() / 3600 <= LIVE_NEWS_H


def stale(cand: dict, at: datetime) -> str | None:
    """Why a story has missed its moment, or None while people are still looking at it."""
    age = age_hours(cand, at)
    if age <= STALE_H or trending_live(cand, at):
        return None
    return f"{age:.0f} h old and no longer trending live"


def lineup(cands: list[dict], at: datetime | None = None) -> tuple[list[dict], list[str]]:
    """Candidates the desk would publish now, best first, and a note for each one it is holding back or dropping."""
    at = at or datetime.now(timezone.utc)
    regular, urgent, spare = can_publish(at), can_publish(at, breaking=True), can_publish(at, spare=True)
    ready, notes = [], []
    for c in sorted(cands, key=lambda c: -priority(c, at)):
        # A case angle runs until its file's "until": the owner chose to follow that story.
        if why := None if c.get("case") else stale(c, at) or unpopular(c, at):
            notes.append(f"drop {c['id']}: {why}")
            continue
        breaking = is_breaking(c, at)
        wait = urgent if breaking else (spare if c.get("case") else regular) or (
            None if in_window(at) else "outside 07:00-24:00 IST")
        wait = c.get("case_wait") or wait or orbitwire.wait(c.get("orbitwire"), at)
        if wait:
            notes.append(f"hold {c['id']}: {wait}")
        else:
            ready.append(c | {"breaking": breaking, "priority": round(priority(c, at))})
    ready.sort(key=lambda c: (not c.get("replaces"), not c.get("case")))
    return ready, notes


def _quake_facts(cands: list[dict]) -> list[str]:
    """Give trending earthquake stories their USGS magnitude and PAGER alert (they decide the breaking lane)."""
    try:
        quakes = [q for q in usgs.recent() if q.mag >= 6.0]
    except Exception as exc:
        return [f"usgs: {type(exc).__name__}: {exc}"[:200]]
    for c in cands:
        if c.get("category") != "earthquake" or not c.get("coords") or not c.get("date"):
            continue
        day = datetime.fromisoformat(c["date"]).date()
        match = [q for q in quakes if abs((q.time.date() - day).days) <= 1
                 and km_between(tuple(c["coords"]), (q.lat, q.lon)) < 300]
        if match:
            q = max(match, key=lambda q: q.mag)
            c.update(mag=q.mag, alert=q.alert, usgs=q.url)
    return []


def apply_orbitwire(cands: list[dict], at: datetime) -> tuple[list[dict], list[str]]:
    """Skip what Orbitwire covers unless it is high-profile and (MIRROR_NEEDS_INDIA) India's too; mark the shared
    stories kept for a new angle."""
    try:
        state = orbitwire.fetch()
    except Exception as exc:
        # Without Orbitwire's ledger the desk cannot tell what it would duplicate: hold everything this run.
        return [], [f"hold all: Orbitwire's state is unreadable ({type(exc).__name__}: {exc})"[:300]]
    fame = [c.get("fame", 0) for c in cands]
    kept, notes = [], []
    for c in cands:
        ov = orbitwire.overlap(c.get("qid"), state, at, title=c.get("title"), story_id=c.get("id"),
                               reports=[r["url"] for r in c.get("reports") or []])
        if not ov:
            kept.append(c)
            continue
        why = high_profile(c, fame)
        if not why:
            notes.append(f"skip {c['id']}: Orbitwire {ov['status'].replace('_', ' ')} ({ov['orbitwire_id']}), not "
                         f"high-profile enough to tell again")
            continue
        india = orbitwire.india_connection(c)
        if orbitwire.MIRROR_NEEDS_INDIA and not india:
            notes.append(f"skip {c['id']}: Orbitwire {ov['status'].replace('_', ' ')} ({ov['orbitwire_id']}) and no "
                         f"India connection: not told again in Hindi")
            continue
        kind = "protest" if c.get("category") in trends.ONGOING else c.get("kind", "incident")
        # An India story's own angle is not "its India connection"; a world story India is part of tells that. With
        # MIRROR_NEEDS_INDIA off, a world story with no India connection keeps its own angle (no ungrounded India line).
        link = bool(c.get("india_link")) or (c.get("region") != "india" and bool(india))
        ov |= {"high_profile": why, "india": india, "angle": orbitwire.angle_for(kind, link)}
        kept.append(c | {"orbitwire": ov})
    return kept, notes


def outlet_note(stats: dict, emerging: list[dict]) -> str:
    from . import config

    lane = "on" if config.NEW_STORIES else "off: DESK_NEW_STORIES"
    return (f"outlets: {stats['headlines']} headlines from {stats['feeds']} feeds ({stats['owners']} owners), "
            f"{stats['matched']} matched to articles, {stats['corroborated']} candidates with 2+ owners, "
            f"{len(emerging)} nw- stories ({lane})" + (f": {', '.join(c['id'] for c in emerging[:3])}" if emerging else ""))


def explainer_note(found: list[dict], dropped: list[str]) -> str:
    from . import config

    lane = "on" if config.EXPLAINERS else "off: DESK_EXPLAINERS"
    return (f"explainers: {len(found)} kh- stories ({lane})"
            + (f": {', '.join(c['id'] for c in found[:4])}" if found else "")
            + (f"; dropped: {'; '.join(dropped[:3])}" if dropped else ""))


def high_profile(cand: dict, fame: list[float]) -> str | None:
    return orbitwire.high_profile(cand, fame)


def watch(save: bool = True) -> dict:
    """Everything the watcher sees this run, written to state/candidates.json for the record (unless save=False)."""
    found = {"at": ledger.now(), "trending": [], "candidates": [], "notes": []}
    try:
        radar = trends.radar()
        found["trending"] = radar["candidates"]
        if radar["errors"]:
            found["trend_errors"] = radar["errors"]
        if radar.get("outlets"):
            found["outlets"] = radar["outlets"]
            found["emerging"] = radar.get("emerging", [])
            found["notes"].append(outlet_note(radar["outlets"], found["emerging"]))
            found["explainers"] = radar.get("explainers", [])
            found["notes"].append(explainer_note(found["explainers"], radar.get("explainer_notes", [])))
    except Exception as exc:
        found["trend_errors"] = [f"{type(exc).__name__}: {exc}"[:200]]
    found["notes"] += _quake_facts(found["trending"])
    at = datetime.now(timezone.utc)
    rows = ledger.published()
    stories, redo, open_cases = [], remakes(at), cases(at)
    for c in found["trending"]:
        # An open case owns its story: its angles are the follow-ups.
        if case := case_of(c, open_cases):
            open_cases = [s for s in open_cases if s is not case]
            stories += angles_of(c, [case], rows, at)
            continue
        if again := remake_of(c, redo):
            redo = [s for s in redo if s["replaces"] != again["replaces"]]
            if not ledger.is_done(again["id"]):
                stories.append(again)
            continue
        if cooling(c, at, rows) or ledger.is_done(trends.article_id(c["title"])):
            continue
        if ledger.is_done(c["id"]) or told_before(c, rows, at):
            part = follow_up(c, rows, at)
            if part and not ledger.is_done(part["id"]):
                stories.append(part)
            continue
        stories.append(c)
    for s in open_cases:
        # A case outlives the story's hours on the radar: its file keeps the candidate the angles are built on.
        if s.get("cand"):
            stories += angles_of(s["cand"], [s], rows, at)
    stories, notes = apply_orbitwire(stories, at)
    found["notes"] += notes
    found["candidates"] = sorted(stories, key=lambda c: -priority(c, at))
    if save:
        ledger.save("candidates", found)
    return found
