"""Identity-pinned YouTube publishing: upload private, verify, then make public (or schedule).

Every write is refused unless the OAuth token belongs to config.CHANNEL_ID, so the desk can never post to another
channel; while CHANNEL_ID is still TBD nothing can be published at all. Every upload declares altered or synthetic
content (the narration is an AI voice) and says so in Hindi in the description.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import config, gate, ledger, media
from .spec import Short

TOKEN_FILE = Path(__file__).resolve().parents[1] / "secrets" / "token.json"
CATEGORY = config.CATEGORY
MARKER = config.MARKER  # uploads before 2026-10-22 carry it as a tag; find() still reads it, nothing writes it
DESCRIPTION_BYTES = 5000  # the API counts UTF-8 bytes, and a Devanagari letter is three of them
VOICE_LINE = {
    "gemini-sulafat": "आवाज़: AI (Google Gemini TTS की Sulafat आवाज़)",
    "chatterbox-sulafat-clone": "आवाज़: AI (Chatterbox Multilingual, Gemini की Sulafat आवाज़ के नमूने से)",
}


class WrongChannel(RuntimeError):
    pass


def client(service: str = "youtube", version: str = "v3"):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    raw = os.environ.get("YOUTUBE_OAUTH_JSON") or (TOKEN_FILE.read_text() if TOKEN_FILE.exists() else "")
    if not raw:
        raise RuntimeError("no YouTube sign-in: set YOUTUBE_OAUTH_JSON or create secrets/token.json")
    creds = Credentials.from_authorized_user_info(json.loads(raw))
    if not creds.valid:
        creds.refresh(Request())
    return build(service, version, credentials=creds, cache_discovery=False)


def check_identity(items: list[dict]) -> dict:
    """The channel the token signs in to, if and only if it is the configured one."""
    if not config.channel_id_ready():
        raise WrongChannel("the channel id is not configured (DESK_CHANNEL_ID): refusing every write")
    if len(items) != 1 or items[0].get("id") != config.CHANNEL_ID:
        raise WrongChannel("signed in to the wrong channel: refusing every write")
    return items[0]


def identity(api) -> dict:
    return check_identity(api.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
                          .get("items", []))


def recent(api, channel: dict, limit: int = 50) -> list[dict]:
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    rows = api.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=limit).execute().get("items", [])
    ids = [r["contentDetails"]["videoId"] for r in rows]
    if not ids:
        return []
    return api.videos().list(part="snippet,status,statistics", id=",".join(ids)).execute().get("items", [])


def find(api, channel: dict, short_id: str, title: str | None = None) -> dict | None:
    """The upload already made for this story, so a story is never uploaded twice: the id the ledger kept when it
    was uploaded, else an older upload's public marker tag, else one of the channel's recent uploads that no ledger
    row owns and whose title is this story's."""
    videos = recent(api, channel)
    kept = ledger.load("uploads", {}).get(short_id)
    if kept:
        hit = next((v for v in videos if v["id"] == kept), None)
        if hit:
            return hit
    hits = [v for v in videos if MARKER + short_id in (v["snippet"].get("tags") or [])]
    if not hits and title:
        owned = set(ledger.load("uploads", {}).values()) | {r.get("video_id") for r in ledger.published()}
        hits = [v for v in videos if v["id"] not in owned and v["snippet"].get("title") == title]
    if len(hits) > 1:
        raise RuntimeError(f"{short_id} is on the channel twice: resolve by hand before publishing again")
    return hits[0] if hits else None


def remember(short_id: str, video_id: str) -> None:
    """Keep the upload's id the moment YouTube returns it: the state branch is saved even when the run fails, so a
    Short still processing is found again by the next run without any tag on the video."""
    uploads = ledger.load("uploads", {})
    uploads[short_id] = video_id
    ledger.save("uploads", uploads)


def hashtag(text: str) -> str:
    """#हिंदीसमाचार style: letters, vowel signs and digits only (Devanagari marks are not \\w in Python)."""
    return re.sub(r"[^0-9A-Za-z\u0900-\u097F]", "", text.replace("।", ""))


def photo_credits(photos: list[dict]) -> str:
    """Every photo's author under its licence, on one line: an advisory's list leaves little room in the description."""
    by_licence: dict[str, list[str]] = {}
    for p in photos:
        names = by_licence.setdefault(p["license"], [])
        if p["author"] not in names:
            names.append(p["author"])
    return "तस्वीरें (Wikimedia Commons): " + "; ".join(f"{', '.join(n)} ({lic})" for lic, n in by_licence.items())


def source_lines(short: Short) -> list[str]:
    """The sources block: "स्रोत: Wikipedia, BBC, The Hindu" naming who the facts come from (when trusted outlets'
    reporting backs any), then every source URL."""
    named = short.scene.get("outlets") or []
    if not named:
        return ["स्रोत:"] + short.sources + [""]
    wiki = ["Wikipedia"] if any("wikipedia.org" in s or "wikidata.org" in s for s in short.sources) else []
    return ["स्रोत: " + ", ".join(wiki + named)] + short.sources + [""]


def description(short: Short, voice: dict) -> str:
    """The full description; when it passes YouTube's limit, without the narration (the video says it), then with
    the photo credits grouped by licence. The sources and the AI disclosure always stay."""
    for narration, grouped in ((True, False), (False, False), (False, True)):
        text = _description(short, voice, narration, grouped)
        if len(text.encode()) <= DESCRIPTION_BYTES:
            return text
    raise ValueError(f"description is {len(text.encode())} bytes; YouTube allows {DESCRIPTION_BYTES}")


def hashtag_line(short: Short) -> str:
    return " ".join("#" + t for t in dict.fromkeys(hashtag(h) for h in short.hashtags) if t)


TITLE_LIMIT = 100


def upload_title(short: Short) -> str:
    """The title with #shorts and the subject's hashtag after it, as Hindi news channels title their Shorts, when it
    fits YouTube's 100 characters. The on-screen headline and the ledger keep the plain title."""
    tags = [t for t in dict.fromkeys(["shorts"] + [hashtag(h) for h in short.hashtags[:1]]) if t]
    for n in range(len(tags), 0, -1):
        title = short.title + " " + " ".join("#" + t for t in tags[:n])
        if len(title) <= TITLE_LIMIT:
            return title
    return short.title


def _description(short: Short, voice: dict, narration: bool, grouped: bool) -> str:
    # Hashtags near the top: YouTube shows the first three above the title.
    tags = hashtag_line(short)
    lines = ([short.summary] if short.kind == "advisory" else [short.title]) + ([tags] if tags else []) + [""]
    if short.kind != "advisory" and narration:
        lines += [" ".join(b.text for b in short.beats[:-1]), ""]
    else:
        for b in short.beats:
            card = b.card or {}
            if card.get("kind") == "list":
                lines += [card["big"] + ":", ", ".join(card["items"]), ""]
    lines += source_lines(short)
    made = ("यह सूची ऊपर दी गई रिपोर्टों में बताई गई DMRC, रेलवे और पुलिस की सूचनाओं से हाथ से मिलाकर बनाई गई है। "
            + ("तस्वीरें असली हैं। " if short.scene.get("photos") else "") + "आवाज़ AI की है।"
            if short.kind == "advisory" else
            f"यह वीडियो AI आवाज़ से बना है। तस्वीरें असली हैं ({media.hosts(short.scene.get('photos') or [])}), उन पर "
            "हल्की 3D कैमरा मूवमेंट जोड़ी गई है। स्क्रिप्ट की हर पंक्ति ऊपर दिए स्रोतों से मिलाकर जाँची गई है।")
    lines += [made,
              VOICE_LINE.get(voice.get("engine"), "आवाज़: AI"),
              "कोई गलती दिखे तो स्रोत के साथ कमेंट करें, हम सुधार करेंगे।", ""]
    if (short.kind == "advisory" or grouped) and short.scene.get("photos"):
        lines += ["श्रेय:", f"• {short.credits[0]}", f"• {photo_credits(short.scene['photos'])}", ""]
    elif short.kind != "advisory":
        lines += ["श्रेय:"] + [f"• {c}" for c in short.credits] + [""]
    # YouTube rejects < and > in descriptions.
    return "\n".join(lines).rstrip("\n").replace("<", "‹").replace(">", "›")


def tags(short: Short) -> list[str]:
    """The story's topic tags and the channel's name, within YouTube's 500 characters. No machine tag: viewers and
    reviewers see tags, and the desk finds its own uploads by video id (find)."""
    out, total = [], 0
    for t in short.tags + [n for n in (config.NAME, config.NAME_HI) if n]:
        t = t.replace("<", "").replace(">", "").replace(",", " ").strip()
        if not t or t in out:
            continue
        if total + len(t) + 2 > 480:
            break
        out.append(t)
        total += len(t) + 2
    return out


UNTAG_PER_RUN = 5


def untag(limit: int = UNTAG_PER_RUN) -> int:
    """Take the old public marker tag off up to `limit` of the channel's recent uploads, keeping their story ids in
    the ledger first so find() still knows them. Title, description, category and topic tags stay as they are."""
    api = client()
    channel = identity(api)
    uploads = ledger.load("uploads", {})
    done = 0
    for v in recent(api, channel):
        snippet = v["snippet"]
        old = snippet.get("tags") or []
        marks = [t for t in old if t.startswith(MARKER)]
        if not marks:
            continue
        if done >= limit:
            break
        if snippet.get("channelId") != config.CHANNEL_ID:
            raise WrongChannel(f"{v['id']} is on another channel")
        for t in marks:
            uploads.setdefault(t[len(MARKER):], v["id"])
        ledger.save("uploads", uploads)
        body = {"id": v["id"], "snippet": {
            "title": snippet["title"], "description": snippet.get("description", ""),
            "categoryId": snippet.get("categoryId", CATEGORY), "tags": [t for t in old if t not in marks]}}
        for key in ("defaultLanguage", "defaultAudioLanguage"):
            if snippet.get(key):
                body["snippet"][key] = snippet[key]
        api.videos().update(part="snippet", body=body).execute()
        done += 1
    return done


def retire(video_id: str) -> None:
    """Make one of this channel's videos private (a version that was replaced); never touches another channel's."""
    api = client()
    identity(api)
    items = api.videos().list(part="snippet,status", id=video_id).execute().get("items", [])
    if not items or items[0]["status"]["privacyStatus"] == "private":
        return
    if items[0]["snippet"]["channelId"] != config.CHANNEL_ID:
        raise WrongChannel(f"{video_id} is on another channel")
    api.videos().update(part="status", body={"id": video_id, "status": {
        "privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
        "embeddable": True, "publicStatsViewable": True}}).execute()


def publish(short: Short, mp4: Path, voice: dict, max_wait: int = 900, publish_at: str | None = None) -> dict:
    """Upload and make public now, or with publish_at (ISO UTC, in the future) leave it private for YouTube to
    release at that time."""
    from googleapiclient.http import MediaFileUpload

    refused = gate.voice_ok(voice)
    if refused:
        raise ValueError(refused)
    api = client()
    channel = identity(api)
    existing = find(api, channel, short.id, upload_title(short))
    if existing:
        video_id = existing["id"]
    else:
        body = {
            "snippet": {"title": upload_title(short), "description": description(short, voice), "tags": tags(short),
                        "categoryId": CATEGORY, "defaultLanguage": config.LANGUAGE,
                        "defaultAudioLanguage": config.LANGUAGE},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
        }
        media = MediaFileUpload(str(mp4), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
        request = api.videos().insert(part="snippet,status", body=body, notifySubscribers=True, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk(num_retries=3)
        video_id = response["id"]
        remember(short.id, video_id)
    deadline = time.monotonic() + max_wait
    while True:
        video = api.videos().list(part="snippet,status,processingDetails", id=video_id).execute()["items"][0]
        if video["snippet"]["channelId"] != config.CHANNEL_ID:
            raise WrongChannel("uploaded video is on another channel")
        status = video["status"]
        processing = video.get("processingDetails", {}).get("processingStatus")
        if status.get("uploadStatus") in ("failed", "rejected", "deleted") or processing in ("failed", "terminated"):
            raise RuntimeError(f"YouTube rejected the upload: {status.get('rejectionReason') or status.get('failureReason')}")
        if status.get("uploadStatus") == "processed" or processing == "succeeded":
            break
        if time.monotonic() > deadline:
            raise RuntimeError("still processing; the next run will finish publishing it")
        time.sleep(15)
    if publish_at:
        api.videos().update(part="status", body={"id": video_id, "status": {
            "privacyStatus": "private", "publishAt": publish_at, "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True, "embeddable": True, "publicStatsViewable": True}}).execute()
        final = api.videos().list(part="status,snippet", id=video_id).execute()["items"][0]
        if not final["status"].get("publishAt"):
            raise RuntimeError(f"video {video_id} was not scheduled")
        return {"video_id": video_id, "url": f"https://www.youtube.com/shorts/{video_id}",
                "youtube_title": final["snippet"]["title"], "privacy": "scheduled",
                "publish_at": final["status"]["publishAt"], "synthetic_declared": True}
    if video["status"]["privacyStatus"] != "public":
        api.videos().update(part="status", body={"id": video_id, "status": {
            "privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
            "embeddable": True, "publicStatsViewable": True}}).execute()
    # videos.list can report the old privacy for a while after the update.
    for wait in (0, 5, 10, 20, 30):
        time.sleep(wait)
        final = api.videos().list(part="status,snippet", id=video_id).execute()["items"][0]
        if final["status"]["privacyStatus"] == "public":
            break
    else:
        raise RuntimeError(f"video {video_id} did not go public ({final['status']['privacyStatus']})")
    # containsSyntheticMedia is write-only in practice: videos.list omits it even though Studio shows "AI use: Yes".
    return {"video_id": video_id, "url": f"https://www.youtube.com/shorts/{video_id}",
            "youtube_title": final["snippet"]["title"], "privacy": "public", "synthetic_declared": True}
