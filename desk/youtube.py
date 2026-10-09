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

from . import config, gate
from .spec import Short

TOKEN_FILE = Path(__file__).resolve().parents[1] / "secrets" / "token.json"
CATEGORY = config.CATEGORY
MARKER = config.MARKER  # published uploads carry it, so it must not change
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


def find(api, channel: dict, short_id: str) -> dict | None:
    hits = [v for v in recent(api, channel) if MARKER + short_id in (v["snippet"].get("tags") or [])]
    if len(hits) > 1:
        raise RuntimeError(f"{short_id} is on the channel twice: resolve by hand before publishing again")
    return hits[0] if hits else None


def hashtag(text: str) -> str:
    """#हिंदीसमाचार style: letters, vowel signs and digits only (Devanagari marks are not \\w in Python)."""
    return re.sub(r"[^0-9A-Za-z\u0900-\u097F]", "", text.replace("।", ""))


def description(short: Short, voice: dict) -> str:
    lines = [short.summary, "", " ".join(b.text for b in short.beats[:-1]), ""]
    lines += ["स्रोत:"] + short.sources + [""]
    lines += ["यह वीडियो AI आवाज़ से बना है। तस्वीरें असली हैं (Wikimedia Commons), उन पर हल्की 3D कैमरा मूवमेंट जोड़ी "
              "गई है। स्क्रिप्ट की हर पंक्ति ऊपर दिए स्रोतों से मिलाकर जाँची गई है।",
              VOICE_LINE.get(voice.get("engine"), "आवाज़: AI"),
              "कोई गलती दिखे तो स्रोत के साथ कमेंट करें, हम सुधार करेंगे।", ""]
    lines += ["श्रेय:"] + [f"• {c}" for c in short.credits] + [""]
    tags = [hashtag(h) for h in short.hashtags]
    lines.append(" ".join("#" + t for t in dict.fromkeys(tags) if t))
    text = "\n".join(lines)
    # YouTube rejects < and > in descriptions.
    return text.replace("<", "‹").replace(">", "›")[:4900]


def tags(short: Short) -> list[str]:
    marker = MARKER + short.id
    out, total = [], len(marker) + 2
    for t in short.tags + [n for n in (config.NAME, config.NAME_HI) if n]:
        t = t.replace("<", "").replace(">", "").replace(",", " ").strip()
        if not t or t in out:
            continue
        if total + len(t) + 2 > 480:
            break
        out.append(t)
        total += len(t) + 2
    return out + [marker]


def publish(short: Short, mp4: Path, voice: dict, max_wait: int = 900, publish_at: str | None = None) -> dict:
    """Upload and make public now, or with publish_at (ISO UTC, in the future) leave it private for YouTube to
    release at that time."""
    from googleapiclient.http import MediaFileUpload

    refused = gate.voice_ok(voice)
    if refused:
        raise ValueError(refused)
    api = client()
    channel = identity(api)
    existing = find(api, channel, short.id)
    if existing:
        video_id = existing["id"]
    else:
        body = {
            "snippet": {"title": short.title, "description": description(short, voice), "tags": tags(short),
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
                "title": final["snippet"]["title"], "privacy": "scheduled", "publish_at": final["status"]["publishAt"],
                "synthetic_declared": True}
    if video["status"]["privacyStatus"] != "public":
        api.videos().update(part="status", body={"id": video_id, "status": {
            "privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
            "embeddable": True, "publicStatsViewable": True}}).execute()
    final = api.videos().list(part="status,snippet", id=video_id).execute()["items"][0]
    if final["status"]["privacyStatus"] != "public":
        raise RuntimeError(f"video {video_id} did not go public ({final['status']['privacyStatus']})")
    # containsSyntheticMedia is write-only in practice: videos.list omits it even though Studio shows "AI use: Yes".
    return {"video_id": video_id, "url": f"https://www.youtube.com/shorts/{video_id}", "title": final["snippet"]["title"],
            "privacy": "public", "synthetic_declared": True}
