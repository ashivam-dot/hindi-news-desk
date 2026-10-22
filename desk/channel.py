"""One-off channel setup, done a little at a time by the scheduled run once the owner turns it on (config.CHANNEL_JOBS,
the repository variable DESK_UNTAG): the About text, keywords, language and country, and series playlists by topic
family with the channel's published Shorts in them and a Home-tab section each.

YouTube's reviewers read the About and the playlists (YouTube Partner Programme review, 2026-10-22 revenue push), and
the old About promised corrections "in a pinned comment", which the desk never posts, and listed हादसे and युद्ध
as the channel's subjects. Every job is idempotent (`state/channel.json` keeps what is done, and YouTube is read back
before anything is added twice), costs at most RUN_UNITS a run and DAY_UNITS a Pacific day of the project's 10,000
(the state branch shows 10 uploads a day with no quotaExceeded, so publishing leaves this room), stops for the day on a quotaExceeded 403, and reports one health line. The caller
runs it after the publish step and catches everything, so it can never stop a publish.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config, ledger, plan, youtube

STATE = "channel"
PACIFIC = ZoneInfo("America/Los_Angeles")  # YouTube's quota day ends at midnight Pacific time
RUN_UNITS, DAY_UNITS = 600, 1500
COST = {"list": 1, "write": 50}  # every list call 1 unit; channels.update, playlists, playlistItems, channelSections 50

COUNTRY = "IN"
# At most 1,000 characters (YouTube's limit). Only what the code does: the radar (plan.py), the two-owner rule
# (gate.OWNERS_NEEDED, outlets.py's allowlist), the writer's rules and checks (writer.py, gate.py), the retire and
# remake path (retire.json, remakes/). No promise of a pinned correction: nothing posts one.
ABOUT = f"""मतलबनामा — हर ख़बर का मतलब। भारत की बड़ी ख़बरें एक मिनट में: क्या हुआ, क्यों हुआ और आप पर क्या असर। प्राथमिकता: पैसा और महंगाई, नौकरियाँ और परीक्षाएँ, सरकारी योजनाएँ और नियम, विज्ञान और मौसम।

कैसे बनती है:
• ख़बर वही, जिसे लोग आज पढ़ और खोज रहे हैं (Google News, Trends, Wikipedia)।
• हर नाम, तथ्य और संख्या Wikipedia/Wikidata में या कम से कम दो स्वतंत्र समाचार संस्थानों (जैसे The Hindu, Hindustan Times, BBC) की रिपोर्टों में होनी चाहिए।
• संपादकीय नियम इंसानों ने लिखे हैं: निष्पक्षता, हर दावा कहने वाले के नाम से, न अटकल, न सलाह। हर वीडियो इनकी स्वचालित जाँच से गुज़रता है।
• विवरण में स्रोतों के लिंक और तस्वीरों (Wikimedia Commons) का श्रेय।

AI: स्क्रिप्ट AI की मदद से लिखी और AI से दोबारा जाँची जाती है; आवाज़ AI की है। तस्वीरें असली हैं।

सुधार: गलती दिखे तो स्रोत के साथ कमेंट करें या ईमेल करें: {config.CONTACT}। गलती पक्की हो तो वीडियो प्राइवेट होता है, और ख़बर ताज़ा हो तो सुधरा वीडियो आता है।

English: Matlabnama, what India's news means for you, in Hindi. AI voice."""
ABOUT_LIMIT = 1000
KEYWORDS = ["मतलबनामा", "Matlabnama", "हिंदी समाचार", "hindi news", "news explained in hindi", "आज की ताजा खबर", "अर्थव्यवस्था",
            "महंगाई", "RBI", "GST", "नौकरी", "सरकारी योजना", "नए नियम", "विज्ञान",
            "ISRO", "मौसम", "india news", "economy news hindi"]
KEYWORDS_LIMIT = 500

# Series playlists by topic family, from the categories plan.py and explain.py give every story (the ledger keeps
# each Short's). Only ad-friendly families: crime, court, attack, protest and death stories get none, and a Short
# plan.ad_class calls sensitive (an arrest, a court) stays out of every playlist whatever its category.
FAMILIES = {
    "economy": ("पैसा, महंगाई और अर्थव्यवस्था | मतलबनामा", ("economy",),
                "पेट्रोल, सोना, GST, RBI, बाज़ार और व्यापार की बड़ी ख़बरें: क्या हुआ और क्यों।"),
    "policy": ("नियम, योजनाएँ और नौकरियाँ | मतलबनामा", ("policy",),
               "नए नियम, सरकारी योजनाएँ, परीक्षाएँ और नौकरियाँ: क्या बदला और किस पर असर।"),
    # No "health": on the 2026-10-22 ledger its only Shorts were two hospital discharges, which are not science.
    "science": ("विज्ञान और अंतरिक्ष | मतलबनामा", ("science",),
                "ISRO, अंतरिक्ष और विज्ञान की ख़बरें, आसान हिंदी में।"),
    "world": ("भारत और दुनिया | मतलबनामा", ("diplomacy", "world", "defence"),
              "विदेश नीति, समझौते और दुनिया की वे ख़बरें जिनका भारत से वास्ता है।"),
    "weather": ("मौसम की ख़बरें | मतलबनामा", ("weather", "cyclone"),
                "बारिश, अलर्ट, चक्रवात और हवा की गुणवत्ता: क्या हुआ और क्यों।"),
    "aviation": ("उड़ानें और हवाई सफ़र | मतलबनामा", ("aviation",),
                 "उड़ानें, हवाई अड्डे और हवाई सफ़र की ख़बरें: क्या हुआ और क्यों।"),
}
MIN_VIDEOS = 2  # a family gets its playlist (and section) once it has this many Shorts
DAY_REASONS = {"quotaExceeded", "dailyLimitExceeded"}  # a rate limit only ends this run's share
FINAL = (400, "400", 404, "404")  # YouTube refuses this very request: the same one would be refused again
UNSORTED = {"manualSortRequired", "invalidPlaylistItemPosition"}  # position 0 needs a hand-sorted playlist


class Capped(Exception):
    """This run's or today's unit cap is reached: the rest waits for the next run."""


class Budget:
    """Units spent this run and this Pacific day, kept in the state so 60-odd runs a day share DAY_UNITS."""

    def __init__(self, state: dict, now: datetime | None = None):
        self.state = state
        self.day = (now or datetime.now(PACIFIC)).astimezone(PACIFIC).date().isoformat()
        units = state.get("units") or {}
        self.today = units.get("spent", 0) if units.get("day") == self.day else 0
        self.run = 0

    def take(self, kind: str) -> None:
        cost = COST[kind]
        if self.run + cost > RUN_UNITS or self.today + cost > DAY_UNITS:
            raise Capped()
        self.run += cost
        self.today += cost
        self.state["units"] = {"day": self.day, "spent": self.today}


def about_version() -> str:
    raw = json.dumps([ABOUT, keywords(), config.LANGUAGE, COUNTRY], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def keywords() -> str:
    """Channel keywords as YouTube stores them: space-separated, a phrase in double quotes, within KEYWORDS_LIMIT."""
    out = ""
    for k in KEYWORDS:
        word = f'"{k}"' if " " in k else k
        if len(out) + len(word) + 1 > KEYWORDS_LIMIT:
            break
        out = f"{out} {word}".strip()
    return out


def _same_text(a, b) -> bool:
    """YouTube may store the About with other whitespace or line ends; the words are what must match."""
    def flat(t):
        return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t or "")).strip()
    return flat(a) == flat(b)


def _about_settled(state: dict, version: str) -> bool:
    """This version of the About is done, or YouTube refused it once (never asked again: a change of ABOUT is)."""
    return version in ((state.get("about") or {}).get("version"), (state.get("about_failed") or {}).get("version"))


def set_about(api, state: dict, budget: Budget) -> str:
    """Read-modify-write brandingSettings: channels.update replaces the whole part, and its title is required, so
    everything YouTube returns is sent back with only the description, keywords, language and country changed. A
    version YouTube refuses (HTTP 400) or does not read back is recorded in about_failed and not written again."""
    version = about_version()
    if (state.get("about") or {}).get("version") == version:
        return "about: done"
    if (failed := state.get("about_failed") or {}).get("version") == version:
        return f"about: not retried ({failed.get('reason')}); change channel.ABOUT to try again"
    budget.take("list")
    items = api.channels().list(part="brandingSettings", id=config.CHANNEL_ID).execute().get("items") or []
    if len(items) != 1 or items[0].get("id") != config.CHANNEL_ID:
        raise youtube.WrongChannel("brandingSettings: not this channel")
    branding = dict(items[0].get("brandingSettings") or {})
    current = dict(branding.get("channel") or {})
    if not current.get("title"):
        raise RuntimeError("brandingSettings.channel has no title: refusing to write it")
    wanted = current | {"description": ABOUT, "keywords": keywords(), "defaultLanguage": config.LANGUAGE,
                        "country": COUNTRY}
    if wanted != current:
        budget.take("write")
        try:
            api.channels().update(part="brandingSettings", body={
                "id": config.CHANNEL_ID, "brandingSettings": branding | {"channel": wanted}}).execute()
        except Exception as exc:
            if youtube.quota_spent(exc) or youtube.status_of(exc) not in FINAL:
                raise
            reason = f"HTTP {youtube.status_of(exc)} {youtube.error_reason(exc) or ''}".strip()
            state["about_failed"] = {"version": version, "reason": reason, "at": ledger.now()}
            return f"about: YouTube refused it ({reason}); not retried"
        budget.take("list")
        back = api.channels().list(part="brandingSettings", id=config.CHANNEL_ID).execute()["items"][0]
        got = back.get("brandingSettings", {}).get("channel", {})
        if not _same_text(got.get("description"), ABOUT) or got.get("title") != current["title"]:
            state["about_failed"] = {"version": version, "reason": "read back differs", "at": ledger.now()}
            return "about: YouTube does not read back the new About text; not retried"
    state["about"] = {"version": version, "at": ledger.now()}
    return "about: set and read back" if wanted != current else "about: already so"


def family_of(row: dict) -> str | None:
    """The playlist family of a published Short: a public, unreplaced, ad-friendly story of a family's category."""
    if row.get("kind") == "advisory" or row.get("privacy") != "public" or row.get("retired_at"):
        return None
    if plan.ad_class(row) == "sensitive":
        return None
    return next((f for f, (_, cats, _) in FAMILIES.items() if row.get("category") in cats), None)


def eligible() -> dict[str, list[str]]:
    """family -> video ids in publishing order, without Shorts a newer version replaced."""
    rows = ledger.published()
    replaced = {r["replaced"] for r in rows if r.get("replaced")}
    out: dict[str, list[str]] = {}
    for r in rows:
        family = family_of(r)
        if family and r.get("video_id") and r["video_id"] not in replaced:
            out.setdefault(family, []).append(r["video_id"])
    return out


def _left(row: dict, ids: list[str]) -> list[str]:
    """The family's Shorts not yet in its playlist (and not refused by YouTube)."""
    there, failed = set(row.get("videos") or []), row.get("failed") or {}
    return [v for v in ids if v not in there and v not in failed]


def pending(state: dict, jobs) -> bool:
    """Whether any job has work left, read from the state alone: a finished setup costs no unit at all."""
    if "about" in jobs and not _about_settled(state, about_version()):
        return True
    if "playlists" not in jobs:
        return False
    fams = state.get("playlists") or {}
    for f, ids in eligible().items():
        row = fams.get(f) or {}
        if len(ids) >= MIN_VIDEOS and (not row.get("id") or _left(row, ids) or (
                not row.get("section") and len(row.get("videos") or []) >= MIN_VIDEOS)):
            return True
    return False


def _all(api, budget: Budget, call, **kwargs) -> list[dict]:
    items, token = [], None
    while True:
        budget.take("list")
        page = call(**kwargs, maxResults=50, **({"pageToken": token} if token else {})).execute()
        items += page.get("items") or []
        token = page.get("nextPageToken")
        if not token:
            return items


def playlists(api, state: dict, budget: Budget, notes: list[str]) -> None:
    """Make each family's playlist once it has MIN_VIDEOS Shorts, add its Shorts (newest first), then give it a
    Home-tab section. A playlist made before the state was saved is found again by its title; videos already in a
    playlist are read from YouTube before any is added. A video YouTube refuses (HTTP 400/404, e.g. deleted) is
    noted and not retried; a 5xx or a timeout ends the run and the video is tried again next run."""
    fams = state.setdefault("playlists", {})
    want = {f: ids for f, ids in eligible().items() if len(ids) >= MIN_VIDEOS}
    made = added = sections = 0
    try:
        if any(not (fams.get(f) or {}).get("id") for f in want):
            mine = _all(api, budget, api.playlists().list, part="snippet", mine=True)
            by_title = {p["snippet"]["title"]: p["id"] for p in mine}
            for f in want:
                row = fams.setdefault(f, {})
                if not row.get("id") and by_title.get(FAMILIES[f][0]):
                    row["id"] = by_title[FAMILIES[f][0]]
        for f, ids in want.items():
            row = fams.setdefault(f, {})
            title, _, about = FAMILIES[f]
            if not row.get("id"):
                budget.take("write")
                made_pl = api.playlists().insert(part="snippet,status", body={
                    "snippet": {"title": title, "description": about, "defaultLanguage": config.LANGUAGE},
                    "status": {"privacyStatus": "public"}}).execute()
                row.update(id=made_pl["id"], at=ledger.now(), videos=[], read_back=True)  # new, so empty; a read
                # this soon is refused with a 404 (2026-10-22: PLH0zK2WnEu4E)
                ledger.save(STATE, state)
                made += 1
            failed = row.setdefault("failed", {})
            todo = _left(row, ids)
            if todo and not row.get("read_back"):
                there = _all(api, budget, api.playlistItems().list, part="contentDetails", playlistId=row["id"])
                row["videos"] = list(dict.fromkeys((row.get("videos") or [])
                                                   + [i["contentDetails"]["videoId"] for i in there]))
                row["read_back"] = True
                todo = [v for v in todo if v not in row["videos"]]
            for vid in todo:
                budget.take("write")
                snippet = {"playlistId": row["id"], "resourceId": {"kind": "youtube#video", "videoId": vid}}
                try:
                    try:
                        api.playlistItems().insert(part="snippet", body={"snippet": snippet | (
                            {} if row.get("unsorted") else {"position": 0})}).execute()
                    except Exception as exc:
                        if row.get("unsorted") or youtube.error_reason(exc) not in UNSORTED:
                            raise
                        row["unsorted"] = True  # added at the end from now on
                        budget.take("write")
                        api.playlistItems().insert(part="snippet", body={"snippet": snippet}).execute()
                except Exception as exc:
                    if youtube.quota_spent(exc) or youtube.status_of(exc) not in FINAL:
                        raise
                    failed[vid] = f"{type(exc).__name__}: {youtube.error_reason(exc) or exc}"[:200]
                    continue
                row.setdefault("videos", []).append(vid)
                ledger.save(STATE, state)
                added += 1
        sections = _sections(api, state, budget, want)
    finally:  # what was done is said even when the cap or the quota stopped it halfway
        left = sum(len(_left(fams.get(f) or {}, ids)) for f, ids in want.items())
        notes.append(f"playlists: {made} made, {added} Shorts added, {sections} sections, {left} Shorts left")


def _sections(api, state: dict, budget: Budget, want: dict) -> int:
    """One singlePlaylist section per family playlist, on the channel's Home tab, unless one already shows it. A
    refusal (HTTP 400/403/404: YouTube allows few sections) is noted on the family and never retried; a 5xx or a
    timeout is tried again next run."""
    fams = state["playlists"]
    todo = [f for f in want if (fams.get(f) or {}).get("id") and len(fams[f].get("videos") or []) >= MIN_VIDEOS
            and not fams[f].get("section")]
    if not todo:
        return 0
    budget.take("list")
    shown = {p for s in api.channelSections().list(part="contentDetails", mine=True).execute().get("items") or []
             for p in (s.get("contentDetails") or {}).get("playlists") or []}
    done = 0
    for f in todo:
        row = fams[f]
        if row["id"] in shown:
            row["section"] = "already shown"
            continue
        budget.take("write")
        try:
            got = api.channelSections().insert(part="snippet,contentDetails", body={
                "snippet": {"type": "singlePlaylist"}, "contentDetails": {"playlists": [row["id"]]}}).execute()
        except Exception as exc:
            if youtube.quota_spent(exc) or youtube.status_of(exc) not in FINAL + (403, "403"):
                raise
            row["section"] = f"refused: {youtube.error_reason(exc) or type(exc).__name__}"[:200]
            continue
        row["section"] = got.get("id") or "made"
        ledger.save(STATE, state)
        done += 1
    return done


def run(jobs: frozenset[str] | set[str], now: datetime | None = None) -> str:
    """Do what is left of jobs ("about", "playlists") within the caps; the one health line saying what happened."""
    state = ledger.load(STATE, {})
    budget = Budget(state, now)
    stopped = state.get("stopped") or {}
    if stopped.get("day") == budget.day:
        return f"channel: stopped for today ({stopped.get('why')}); the setup goes on tomorrow (Pacific)"
    if not pending(state, jobs):
        return f"channel: {', '.join(sorted(jobs))} done; nothing left to do"
    listed = youtube.scopes()
    if listed is not None and not listed & youtube.WRITE_SCOPES:
        return ("channel: the YouTube sign-in has no youtube or youtube.force-ssl scope; the About and playlists wait "
                "until the owner re-consents the token with it")
    notes = []
    try:
        api = youtube.client()
        budget.take("list")
        youtube.identity(api)
        if "about" in jobs:
            notes.append(set_about(api, state, budget))
        if "playlists" in jobs:
            playlists(api, state, budget, notes)
    except Capped:
        notes.append(f"unit cap reached ({RUN_UNITS} a run, {DAY_UNITS} a day); the rest goes on next run")
    except Exception as exc:
        reason = youtube.error_reason(exc)
        if youtube.quota_spent(exc):
            if reason in DAY_REASONS:
                state["stopped"] = {"day": budget.day, "why": f"quota: {reason}"}
            notes.append(f"YouTube's quota is spent ({reason}); stopped "
                         + ("until tomorrow" if reason in DAY_REASONS else "for this run"))
        elif youtube.status_of(exc) in (403, "403"):  # the same write would be refused again all day
            state["stopped"] = {"day": budget.day, "why": f"HTTP 403 {reason or ''}".strip()}
            notes.append(f"YouTube refused the write (HTTP 403 {reason or ''}); stopped until tomorrow")
        else:
            notes.append(f"{type(exc).__name__}: {exc}")
    finally:
        ledger.save(STATE, state)
    return (f"channel: {'; '.join(notes)} ({budget.run} units this run, {budget.today} today)")[:400]
