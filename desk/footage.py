"""Real footage for a news Short: shots from YouTube videos whose owners licensed them for reuse (Creative Commons
Attribution, YouTube's "CC BY"), found through the desk's YouTube API project, judged by a vision model, cut to a few
seconds, muted, and credited on screen and in the description.

Only CC BY videos from channels big enough to own what they film are used, and no shot showing another outlet's logo.
Footage under YouTube's standard licence (TV channels, agencies, clips from X or Instagram) draws Content ID claims and
copyright strikes; ANI struck YouTubers over clips of a few seconds in 2025, and three strikes delete a channel.
Searched on 26 Oct 2026: CC BY footage existed for 8 of our last 10 stories, from News18's regional channels, ABP Majha,
Hindustan Samachar and the PM's channels (all of PMO India's last 20 uploads are CC BY, 17 of Narendra Modi's, 5 of
Rahul Gandhi's). TV channels' and agencies' own channels (PIB, Sansad TV, ANI, PTI) use the standard licence.

The news channels' CC BY uploads are bulletins: their footage plays in a window among headline bars, side panels and
tickers, beside a reporter at times. So a first look sorts each video's shots from small frames, a second look finds
the footage window on a sharp frame of each promising shot, its edges are moved onto the window's borders, and only
that window is cut, over a blurred copy of itself where it doesn't fill the picture area."""

from __future__ import annotations

import atexit
import base64
import io
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from . import judge as gemini

log = logging.getLogger(__name__)

MOST_CLIPS = 5
PER_VIDEO = 3
CANDIDATES = 3                # videos looked at
# And up to SHORT_EXTRA more uploads of at most SHORT_CLIP seconds, which are often raw footage and cheap to look at:
# ABP Majha's 15-second "Tiger Shroff Car Video" of 19 Oct ranked sixth of 19 by its title.
SHORT_CLIP, SHORT_EXTRA = 90, 3
FOOTAGE_WORDS = re.compile(r"\b(video|cctv|footage)\b|वीडियो|व्हिडिओ|विडियो|सीसीटीवी|कैमरे में कैद", re.I)
SEARCHES = 2                  # search.list calls per Short (a bucket of its own, 100 calls a day)
# The oldest upload a story's footage may come from: a running story's best footage is often its first day's (the
# shots at Tiger Shroff's car on 18 Oct were still news on 26 Oct).
LOOK_BACK = timedelta(days=10)
# A long report is looked at only this far: its field footage comes early.
SOURCE_SECONDS = 240
LONGEST = 40 * 60             # longer uploads are live streams and full bulletins
SHORTEST = 6
# Channels big enough to film their own footage. A small channel's "CC BY" upload is often a TV channel's footage
# passed off as its own, which would draw that channel's claim; the looks turn down any shot with another outlet's
# logo. These official channels are taken at any size. At 250,000 the desk passed over The News Telugu's (123,000)
# reports from the Andhra coast on all of 28 Oct's Cyclone Arnab Shorts.
MIN_SUBSCRIBERS = 100_000
OWNERS = {"UCDS9hpqUEXsXUIcf0qDcBIA": "PMO India", "UC1NF71EwP41VdjAU1iXdLkw": "Narendra Modi",
          "UC1DtEMePmr4O6F2do6BVl7A": "Rahul Gandhi"}
SCENE_CHANGE = 0.3            # ffmpeg's scene score for a cut between shots
SHOT_LEAST = 2.2              # a shot shorter than this is a flash, too short for a scene
CLIP_MOST = 4.6               # a scene runs at most 4.2 s (render.SCENE_MAX)
SHOTS_PER_VIDEO = 6           # each video's longest shots, shown to the first look
# Frames in one first-look request. Gemma 4 answered 20 or more with HTTP 500, and judged worse in batches of 9: the
# frames of ABP Majha's video of Tiger Shroff's car after the attack were promising alone, and not among 8 others.
BATCH = 5
SECOND_LOOKS = 6              # promising shots looked at again, one sharp frame each
LEAST_RELEVANCE = 6
MEDIA = (1080, 1500)          # render.MEDIA
# A footage window is enlarged up to ZOOM times past fitting the picture area, but never past UPSCALE_MOST times, its
# sides cropped, and a blurred copy fills the rest. A window that needs more than UPSCALE_MOST just to fit the picture
# area is too small to look sharp.
ZOOM = 1.5
UPSCALE_MOST = 2.2
EDGE, BORDER, REACH, INSET = 28, 0.6, 0.08, 0.006  # see snap()
SAMPLE_EVERY = 8              # seconds between the frames that show which parts of a video's layout stay put
STEADY, OVER = 0.5, 0.5       # see trim()
DEADLINE = 300                # seconds for the looks and cuts once a video is read; past it the step keeps what it has
# YouTube asks a cloud host's yt-dlp to sign in ("not a bot") for every video, and CircleCI's addresses stay refused.
# So after a refusal the step goes through Cloudflare's free WARP this long. A WARP exit is an address shared with many
# WARP users, which YouTube refuses now and then for seconds to minutes: on 28 Oct the footage VM's exit was refused and
# served again within a minute, a burst of six lookups was served, and three new VM devices all kept the same address.
# Two quick tries 20 s apart lost the footage of 4 of that day's 12 Shorts. So the first video is asked for again after
# each of ROUTE_WAITS, through the other exits in turn (_reroute), within PATIENCE; only when all are refused does the
# step rest WARP_REST, short enough that the desk's next run tries again.
REFUSED_REST = timedelta(hours=12)
WARP_REST = timedelta(minutes=5)
ROUTE_WAITS = (20, 40, 60, 90)
PATIENCE = 240
YT_DLP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
# wgcf registers a WARP device and writes its WireGuard profile; wireproxy runs it in user space as an HTTP proxy, with
# no root or tunnel device, for yt-dlp and ffmpeg alone.
WGCF = "https://github.com/ViRb3/wgcf/releases/download/v2.3.1/wgcf_2.3.1_{system}_{arch}"
WIREPROXY = "https://github.com/whyvl/wireproxy/releases/download/v1.1.3/wireproxy_{system}_{arch}.tar.gz"
WARP_PORT = 25345
# Cloudflare's WARP endpoints by address, tried after the profile's own when it doesn't connect: from a GitHub runner on
# 29 Oct these all connected and YouTube served a video it refused the runner itself (scripts/warp_probe.py).
ENDPOINTS = ("162.159.192.1:2408", "162.159.195.1:2408", "162.159.192.1:4500", "162.159.192.1:500")
# The footage VM (Oracle Always Free, Mumbai) runs the same WARP proxy on its own 127.0.0.1:WARP_PORT. The desk reaches
# it through SSH (FOOTAGE_HOST, FOOTAGE_SSH_KEY in base64, FOOTAGE_HOST_KEY) with a key that may only forward that port
# or run its forced command, which gives the VM a new WARP device. YouTube served that exit (BOM) on 27 Oct, when it
# refused CircleCI's own address and CircleCI's WARP exit.
VM_PORT = 25346
VM_URL, LOCAL_URL = f"http://127.0.0.1:{VM_PORT}", f"http://127.0.0.1:{WARP_PORT}"
TRACE = "https://www.cloudflare.com/cdn-cgi/trace"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pal-pal-desk"
LICENCE = "CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/)"
# Gemma only: each Gemini model gives the desk about 20 requests a day, which writing and fact-checking need, and Gemma
# about 1,500.
JUDGE_MODELS = gemini.GEMMA_MODELS
JUDGE_TIMEOUT = 45            # seconds a judge request may take; Gemma answers in 5-10, or hangs
# Which found videos report the story's own event. Matching names in titles let in ABP Majha's "Meenakshi Shinde At
# Crime Branch" for 28 Oct's UP council election Short (its description named the elections), and the looks rated its
# woman by a car 10 of 10; and it turned away CNEWS Bharat's Hindi titles on the counting itself.
MATCH = """You check which YouTube videos report the same news event as a Hindi news Short, so that their footage
can be shown in it. Each video is numbered, with its title, channel, upload time and the start of its description.

A video matches when it reports this Short's own event: the same incident, match or innings, case, announcement,
result, film or person in this news. A video only on the same broad subject does not: another election or seat,
another match, another crime or case, another film, a different place, or a roundup of the day's headlines.

Answer as {"videos": [{"n": 1, "same_event": true}]}, one entry for every video."""
FIRST_LOOK = """You choose real news footage for a Hindi news Short. The frames come from YouTube news videos, one
frame from each shot, each labelled "Frame <n>, video <v>" with its uploader. News channels often play their footage in
a window inside a layout of headline bars, side and text panels, tickers and logos, sometimes beside a second window
with a reporter or anchor. Judge each frame by the picture window that best shows the story.

For each frame give:
- kind: what that window shows: "footage" (real camera footage of people, places or events, CCTV included),
  "studio" (an anchor, a reporter talking to the camera, or a panel), "photo" (a still photograph or selfie shown on
  screen), "graphic" (an illustration, map, animation, collage or text card), or "other"
- relevance: 0-10, how well it shows this story's people, place or event (10: the event itself, or its main person in
  this story's setting; 0: unrelated, such as another story's footage)
- foreign_logo: true if the window shows the logo or watermark of a news agency or channel other than the frame's
  uploader (ANI, PTI, IANS, Reuters, AP, AFP, another TV channel), or was filmed off a TV, phone or computer screen
  (its edges, glare or pixels show), or is a screenshot of a social post. The uploader's own logo, in any script, is
  fine, and so is shaky or vertical phone footage.
- graphic_content: true for blood, open wounds, people lying hurt or dead, a weapon aimed at someone, nudity, or a
  child's face (a bandage alone is fine)
- what: what the window shows, up to 8 words

Answer as {"frames": [{"n": 1, "kind": "footage", "relevance": 7, "foreign_logo": false, "graphic_content": false,
"what": "..."}]}"""
SECOND_LOOK = """You check one frame of a YouTube news video for a Hindi news Short. News channels often play footage
in a window inside a layout of headline bars, side and text panels, tickers and logos, sometimes beside another window
with a reporter or anchor.

Find the window that shows real camera footage of the story: people, places or events, CCTV included. Not a reporter
or anchor talking to the camera, not a still photo or selfie, not a graphic.

Answer as {"found": true, "box": [ymin, xmin, ymax, xmax], "kind": "footage", "relevance": 7, "foreign_logo": false,
"text_heavy": false, "graphic_content": false, "what": "up to 8 words"}
- box: the clear footage's edges, each from 0 to 1000 of the frame's height or width; [0, 0, 1000, 1000] if clear
  footage fills the frame. Leave out the graphics around it and any other window. Where a graphic panel, photo, logo,
  caption bar or text box is drawn over part of the footage, the box stops at that graphic's edge, so that none of
  it is inside.
- kind: what the window shows: "footage", "studio" (an anchor or reporter talking to the camera), "photo", "graphic"
  or "other". found: false, with the main picture's kind, if no window shows footage.
- relevance: 0-10, how well it shows this story's people, place or event (10: the event itself; 0: unrelated)
- foreign_logo: a logo or watermark of an agency or channel other than the uploader (ANI, PTI, IANS, Reuters, AP,
  AFP, another channel) inside the window, or the window was filmed off a TV, phone or computer screen (its edges,
  glare or pixels show), or is a screenshot of a social post. The uploader's own logo, in any script, is fine, and so
  is shaky or vertical phone footage.
- text_heavy: large text over much of the window
- graphic_content: blood, open wounds, people lying hurt or dead, a weapon aimed at someone, nudity, or a child's
  face (a bandage alone is fine)"""


class ff:
    """ffmpeg on the PATH (the run installs it with apt)."""

    @staticmethod
    def exe() -> str:
        return shutil.which("ffmpeg") or "ffmpeg"


def keyword(title: str) -> str:
    """What the title is about in Latin letters: the name or story it leads with ("Tiger Shroff Firing Case: ..."),
    or the name after an older title's "|"."""
    if "|" in title:
        return title.rsplit("|", 1)[-1].strip()
    head = title.split(":", 1)[0].strip()
    return head if ":" in title and re.fullmatch(r"[A-Za-z0-9 .&'\-]+", head) else ""


def _client():
    from . import youtube

    return youtube.client()


def _seconds(iso: str) -> int:
    found = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not found:
        return 0
    days, hours, minutes, seconds = (int(g or 0) for g in found.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def queries(pkg: dict) -> list[str]:
    """What to search for: the title's English name, then the main people or places by name."""
    names = [str(s.get("name", "")).strip() for s in pkg.get("subjects", []) if isinstance(s, dict)]
    out = [keyword(pkg.get("title", "")), " ".join(n for n in names[:2] if n)]
    return list(dict.fromkeys(q for q in out if q))[:SEARCHES] or [pkg.get("headline", "")]


def _terms(pkg: dict) -> tuple[list[str], list[str]]:
    """Full names (Latin) and single words (Latin words of the title's name and the subjects' Hindi anchor words) that
    a relevant video's title would carry."""
    names = [str(s.get("name", "")).strip() for s in pkg.get("subjects", []) if isinstance(s, dict)]
    words = [w for w in re.findall(r"[A-Za-z]{4,}", keyword(pkg.get("title", "")))
             if w.lower() not in {"case", "news", "live", "update", "video", "with", "from", "says"}]
    words += [str(s.get("anchor", "")).strip() for s in pkg.get("subjects", [])
              if isinstance(s, dict) and len(str(s.get("anchor", "")).strip()) >= 3]
    return [n for n in names if n], list(dict.fromkeys(words))


def relevance(video: dict, names: list[str], words: list[str]) -> int:
    """How strongly a video's title and description name the story: 2 for each full name, 1 for each other word."""
    text = f"{video['title']} {video.get('description', '')[:300]}"
    score = sum(2 for n in names if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", text, re.I))
    return score + sum(1 for w in words if re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", text, re.I))


def search(youtube, terms: list[str], after: datetime) -> list[dict]:
    """CC BY videos on YouTube for each search, with their length, licence, channel and the channel's subscribers."""
    hits: dict[str, int] = {}
    for query in terms:
        found = youtube.search().list(part="id", q=query, type="video", videoLicense="creativeCommon",
                                      publishedAfter=after.strftime("%Y-%m-%dT%H:%M:%SZ"), regionCode="IN",
                                      relevanceLanguage="hi", maxResults=20, safeSearch="moderate").execute()
        for rank, item in enumerate(found.get("items", [])):
            hits.setdefault(item["id"]["videoId"], rank)
    if not hits:
        return []
    items = youtube.videos().list(part="snippet,contentDetails,status,statistics",
                                  id=",".join(list(hits)[:50])).execute().get("items", [])
    channel_ids = sorted({v["snippet"]["channelId"] for v in items})
    subscribers = {c["id"]: 0 if c["statistics"].get("hiddenSubscriberCount") else int(c["statistics"].get("subscriberCount", 0))
                   for c in youtube.channels().list(part="statistics", id=",".join(channel_ids[:50])).execute().get("items", [])}
    return [{"id": v["id"], "rank": hits[v["id"]], "title": v["snippet"]["title"],
             "description": v["snippet"].get("description", ""), "channel": v["snippet"]["channelTitle"],
             "channel_id": v["snippet"]["channelId"], "published": v["snippet"]["publishedAt"],
             "live": v["snippet"].get("liveBroadcastContent", "none"), "licence": v["status"].get("license", ""),
             "seconds": _seconds(v["contentDetails"].get("duration", "")),
             "views": int(v.get("statistics", {}).get("viewCount", 0)),
             "subscribers": subscribers.get(v["snippet"]["channelId"], 0)} for v in items]


def refusal(video: dict) -> str:
    """Why a found video can't be used ("" if it can)."""
    if video["licence"] != "creativeCommon":
        return "not CC BY"
    if video["live"] != "none":
        return "live"
    if not SHORTEST <= video["seconds"] <= LONGEST:
        return f"{video['seconds']} s long"
    if video["channel_id"] not in OWNERS and video["subscribers"] < MIN_SUBSCRIBERS:
        return f"a small channel ({video['subscribers']} subscribers)"
    return ""


def same_story(videos: list[dict], pkg: dict) -> set[str] | None:
    """The ids of the videos that report the story's own event (MATCH); None if the judge didn't answer."""
    if not videos:
        return set()
    listing = "\n".join(f"{n}. \"{v['title']}\" by {v['channel']}, uploaded {v.get('published', '')[:16]}: "
                        f"{' '.join(v.get('description', '').split())[:200]}" for n, v in enumerate(videos, 1))
    try:
        answer = gemini.text_json(MATCH, f"{_story(pkg)}\n\nThe videos:\n{listing}", temperature=0.1,
                                  models=JUDGE_MODELS, timeout=JUDGE_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - the titles' names decide instead
        log.warning("footage: the story check failed, so names in titles decide: %s", _quiet(exc))
        return None
    picked = {int(v["n"]) for v in answer.get("videos") or [] if isinstance(v, dict)
              and str(v.get("n", "")).isdigit() and _yes(v, "same_event")}
    return {v["id"] for n, v in enumerate(videos, 1) if n in picked}


def choose(found: list[dict], pkg: dict) -> list[dict]:
    """The usable videos that report the story (same_story; without its answer, those whose titles name it), the
    best first: most relevant (a title that promises video counts one more), then official, then YouTube's order."""
    names, words = _terms(pkg)
    allowed = []
    for video in found:
        if why := refusal(video):
            log.info("footage: passed over %s (%s, %s): %s", video["id"], video["channel"], video["title"][:60], why)
        else:
            allowed.append(video)
    same = same_story(allowed, pkg)
    usable = []
    for video in allowed:
        score = relevance(video, names, words)
        if (video["id"] not in same) if same is not None else score < 2:
            log.info("footage: passed over %s (%s, %s): %s", video["id"], video["channel"], video["title"][:60],
                     "another story" if same is not None else "doesn't name the story")
            continue
        usable.append({**video, "score": score + bool(FOOTAGE_WORDS.search(video["title"]))})
    return sorted(usable, key=lambda v: (-v["score"], v["channel_id"] not in OWNERS, v["rank"], -v["views"]))


class Refused(RuntimeError):
    """YouTube asked yt-dlp to sign in: the host's address is taken for a bot, so no other video will come either."""


_refused_until: datetime | None = None       # YouTube refused this host's own address: WARP until then
_warp_refused_until: datetime | None = None  # and WARP's too: no footage until then
_warp_profile: str | None = None
_warp_proc: subprocess.Popen | None = None
_tunnel_proc: subprocess.Popen | None = None
_proxy: str | None = None
_yt_dlp_lock = threading.Lock()              # prepare() runs for several videos at once


def restore(state: dict) -> None:
    """Carry the refusals and the WARP profile over from the desk's state, which outlives each run. A WARP rest is
    never longer than WARP_REST from now."""
    global _refused_until, _warp_refused_until, _warp_profile
    _refused_until, _warp_refused_until = (datetime.fromisoformat(state[k]) if state.get(k) else None
                                           for k in ("footage_refused", "footage_warp_refused"))
    if _warp_refused_until:
        _warp_refused_until = min(_warp_refused_until, datetime.now(timezone.utc) + WARP_REST)
    _warp_profile = state.get("footage_warp")


def save(state: dict) -> None:
    now = datetime.now(timezone.utc)
    for key, until in (("footage_refused", _refused_until), ("footage_warp_refused", _warp_refused_until)):
        state[key] = until.isoformat() if until and until > now else None
    state["footage_warp"] = _warp_profile


def _download(url: str, path: Path) -> None:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    if url.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(resp.content)) as tar:
            data = tar.extractfile(next(m for m in tar.getmembers() if m.name.endswith(path.name))).read()
    else:
        data = resp.content
    path.write_bytes(data)
    path.chmod(0o755)


def _stop_warp() -> None:
    """Stops wireproxy and waits for it, so that the next one can take its port."""
    global _proxy, _warp_proc
    if _warp_proc:
        _warp_proc.kill()
        _warp_proc.wait()
    _warp_proc = _proxy = None


def _exit(url: str) -> str | None:
    """Cloudflare's exit (its colo) when the proxy at `url` goes out through WARP, else None."""
    try:
        trace = requests.get(TRACE, proxies={"https": url}, timeout=5).text
    except requests.RequestException:
        return None
    if "warp=on" not in trace:
        return None
    colo = re.search(r"^colo=(\w+)", trace, re.M)
    return colo.group(1) if colo else "unknown"


def _vm(fresh: bool) -> str:
    """The footage VM's WARP proxy through an SSH tunnel, opened once a run; with `fresh`, the VM gets a new WARP
    device first."""
    global _proxy, _tunnel_proc
    folder = CACHE / "vm"
    folder.mkdir(parents=True, exist_ok=True)
    key, hosts = folder / "key", folder / "known_hosts"
    key.write_bytes(base64.b64decode(os.environ["FOOTAGE_SSH_KEY"]))
    key.chmod(0o600)
    hosts.write_text(os.environ["FOOTAGE_HOST_KEY"].strip() + "\n")
    ssh = ["ssh", "-i", str(key), "-o", f"UserKnownHostsFile={hosts}", "-o", "StrictHostKeyChecking=yes",
           "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    host = os.environ["FOOTAGE_HOST"]
    if fresh:
        subprocess.run([*ssh, host], capture_output=True, timeout=120, check=True)
    if not _tunnel_proc or _tunnel_proc.poll() is not None:
        _tunnel_proc = subprocess.Popen([*ssh, "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
                                         "-L", f"127.0.0.1:{VM_PORT}:127.0.0.1:{WARP_PORT}", host],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        atexit.register(_tunnel_proc.terminate)
    url = f"http://127.0.0.1:{VM_PORT}"
    for _ in range(20):
        time.sleep(1)
        if _tunnel_proc.poll() is not None:
            break
        if colo := _exit(url):
            _proxy = url
            log.info("footage: through the footage VM's WARP (%s, exit %s)", "a new device" if fresh else "its device",
                     colo)
            return url
    raise RuntimeError("the footage VM's WARP didn't answer")


def _warp(fresh: bool = False, local: bool = False) -> str:
    """An HTTP proxy through Cloudflare's WARP, started once a run: the footage VM's when the desk has one and not
    `local`, else this host's own, with the kept device profile or a new one; a new device in any case when `fresh`."""
    global _proxy, _warp_profile, _warp_proc
    vm = bool(os.environ.get("FOOTAGE_HOST")) and not local
    if _proxy and not fresh and (_proxy == VM_URL) == vm:
        return _proxy
    if vm:
        try:
            return _vm(fresh)
        except Exception as exc:  # noqa: BLE001 - this host's own WARP instead
            log.warning("footage: the footage VM failed: %s", _quiet(exc))
    _stop_warp()
    system = "darwin" if sys.platform == "darwin" else "linux"
    arch = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine().lower()]
    folder = CACHE / "warp"
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in (("wgcf", WGCF), ("wireproxy", WIREPROXY)):
        if not (folder / name).exists():
            _download(url.format(system=system, arch=arch), folder / name)
    profile = folder / "wgcf-profile.conf"
    (folder / "wireproxy.conf").write_text(f"WGConfig = {profile}\n\n[http]\nBindAddress = 127.0.0.1:{WARP_PORT}\n")
    url, said = f"http://127.0.0.1:{WARP_PORT}", ""
    for new in ((True,) if fresh or not _warp_profile else (False, True)):
        if new:
            (folder / "wgcf-account.toml").unlink(missing_ok=True)
            for step in (["register", "--accept-tos"], ["generate"]):
                subprocess.run([str(folder / "wgcf"), *step], cwd=folder, capture_output=True, timeout=60, check=True)
            _warp_profile = profile.read_text()
        for endpoint in [None, *ENDPOINTS]:
            profile.write_text(_warp_profile if endpoint is None else
                               re.sub(r"(?m)^Endpoint\s*=.*$", f"Endpoint = {endpoint}", _warp_profile))
            out = folder / "wireproxy.log"
            with out.open("wb") as sink:
                _warp_proc = subprocess.Popen([str(folder / "wireproxy"), "-c", str(folder / "wireproxy.conf")],
                                              stdout=sink, stderr=subprocess.STDOUT)
            atexit.register(_warp_proc.terminate)
            for _ in range(15):
                time.sleep(1)
                if colo := _exit(url):
                    _proxy = url
                    log.info("footage: through WARP (%s profile, endpoint %s, exit %s)", "a new" if new else "the kept",
                             endpoint or "its own", colo)
                    return url
                if _warp_proc.poll() is not None:
                    break
            _stop_warp()
            said = out.read_text(errors="replace").strip()[-200:]
    raise RuntimeError(f"WARP didn't connect: {said}")


def _yt_dlp() -> list[str]:
    """yt-dlp's newest release (a Python zipapp), fetched again once a day: YouTube changes often, and a three-month-
    old yt-dlp was refused the 1080p streams that the newest one gets."""
    path = CACHE / "yt-dlp"
    with _yt_dlp_lock:
        if not path.exists() or time.time() - path.stat().st_mtime > 86400:
            CACHE.mkdir(parents=True, exist_ok=True)
            resp = requests.get(YT_DLP, timeout=60)
            resp.raise_for_status()
            part = path.with_suffix(".part")
            part.write_bytes(resp.content)
            part.replace(path)
    js = ["--js-runtimes", "node"] if not shutil.which("deno") and shutil.which("node") else []
    return [sys.executable, str(path), *js]


def streams(video: dict) -> dict:
    """yt-dlp's account of the video: its formats with their stream URLs, the headers to fetch them with and the proxy
    they were asked for through (YouTube's stream URLs work only from the address that asked for them)."""
    proxy = _proxy
    proc = subprocess.run(_yt_dlp() + (["--proxy", proxy] if proxy else []) +
                          ["-j", "--no-playlist", "--no-warnings", f"https://www.youtube.com/watch?v={video['id']}"],
                          capture_output=True, text=True, timeout=150)
    if proc.returncode:
        message = proc.stderr.strip()[-500:]
        if re.search(r"Sign in to confirm|not a bot", message):
            raise Refused(message)
        raise RuntimeError(f"yt-dlp exited {proc.returncode}: {message}")
    info = json.loads(proc.stdout)
    for fmt in info.get("formats") or []:
        fmt["proxy"] = proxy
    return info


def candidates(info: dict, side: int) -> list[dict]:
    """The video streams whose shorter side is at most `side`, the best first: HLS before plain HTTPS, then the
    largest, H.264 before VP9 before AV1. ffmpeg opens YouTube's HLS streams and seeks in them segment by segment;
    the TV client's HTTPS streams answer it 403."""
    found = [f for f in info.get("formats", []) if f.get("url") and f.get("vcodec") not in (None, "none")
             and str(f.get("protocol", "")).startswith(("http", "m3u8")) and f.get("width") and f.get("height")
             and min(f["width"], f["height"]) <= side]
    codec = lambda f: 2 if str(f["vcodec"]).startswith("avc1") else 1 if str(f["vcodec"]).startswith("vp") else 0  # noqa: E731
    return sorted(found, key=lambda f: (str(f["protocol"]).startswith("m3u8"), min(f["width"], f["height"]), codec(f),
                                        f.get("tbr") or 0), reverse=True)


def _source(fmt: dict) -> list[str]:
    """ffmpeg's input options for a stream URL: the headers yt-dlp would send, a limit on each network wait, and the
    proxy yt-dlp went through (streams())."""
    headers = "".join(f"{k}: {v}\r\n" for k, v in (fmt.get("http_headers") or {}).items())
    proxy = fmt["proxy"] if "proxy" in fmt else _proxy
    return ((["-headers", headers] if headers else []) + (["-http_proxy", proxy] if proxy else []) +
            ["-rw_timeout", "20000000", "-i", fmt["url"]])


def _quiet(exc: BaseException) -> str:
    """An error without the stream URLs in it, which are long and signed."""
    return re.sub(r"https?://\S+", "<url>", str(exc))[-400:]


def _ffmpeg(*args: str | Path, timeout: float = 120) -> bytes:
    """ffmpeg with a time limit (a stalled stream would otherwise hold the run); its output, for a pipe."""
    cmd = [ff.exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffmpeg ran past {timeout:.0f} s") from exc
    if proc.returncode:
        raise RuntimeError(f"ffmpeg exited {proc.returncode}: {proc.stderr.decode(errors='replace').strip()[-600:]}")
    return proc.stdout


def fetch(streams_: list[dict], make) -> dict:
    """The first stream for which make(stream) works; the error of the last one if none does."""
    error: Exception = RuntimeError("no video stream")
    for fmt in streams_[:4]:
        try:
            make(fmt)
            return fmt
        except RuntimeError as exc:
            error = exc
            log.info("footage: stream %s (%s) failed: %s", fmt.get("format_id"), fmt.get("protocol"), _quiet(exc))
    raise RuntimeError(_quiet(error))


def probe(path: Path) -> tuple[float, int, int]:
    """Length in seconds, width and height."""
    proc = subprocess.run([ff.exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=60)
    length = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    size = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", proc.stderr)
    if not length or not size:
        raise RuntimeError(f"can't read {path.name}: {proc.stderr[-300:]}")
    h, m, s = length.groups()
    return int(h) * 3600 + int(m) * 60 + float(s), int(size.group(1)), int(size.group(2))


def shots(path: Path, length: float) -> list[tuple[float, float]]:
    """The video's shots at least SHOT_LEAST long, as (start, end), from ffmpeg's scene-change detection."""
    proc = subprocess.run([ff.exe(), "-hide_banner", "-nostdin", "-i", str(path), "-an", "-vf",
                           f"scale=320:-2,select='gt(scene,{SCENE_CHANGE})',metadata=print:file=-", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=300)
    cuts = sorted({round(float(t), 3) for t in re.findall(r"pts_time:([\d.]+)", proc.stdout)})
    edges = [0.0] + [t for t in cuts if 0 < t < length] + [length]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b - a >= SHOT_LEAST]


def moment(shot: tuple[float, float]) -> float:
    """The moment of a shot that is judged: a second in, or its middle if it is shorter."""
    return min(shot[0] + 1.0, (shot[0] + shot[1]) / 2)


def frame_at(*source: str, at: float, timeout: float = 60) -> Image.Image | None:
    """One frame at `at` seconds of a file or stream (the ffmpeg input options in `source`)."""
    try:
        png = _ffmpeg("-ss", f"{at:.2f}", *source, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-",
                      timeout=timeout)
    except RuntimeError:
        return None
    return Image.open(io.BytesIO(png)).convert("RGB") if png else None


def _jpeg(image: Image.Image) -> dict:
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=86)
    return {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def _story(pkg: dict) -> str:
    names = ", ".join(str(s.get("name", "")) for s in pkg.get("subjects", []) if isinstance(s, dict))
    return (f"Our Short: {pkg.get('headline', '')} ({pkg.get('title', '')})\nWhat it says: {pkg.get('script', '')}\n"
            f"People and places: {names}; {pkg.get('location', '')}")


def prepare(video: dict, folder: Path, info: dict | None = None) -> dict:
    """A video's streams (`info`, if already asked for), a 240p copy of its first SOURCE_SECONDS, its longest shots and
    a frame of each, and grey frames from all through the copy (see trim())."""
    info = info or streams(video)
    source = folder / f"{video['id']}-preview.mp4"
    fetch(candidates(info, 240), lambda fmt: _ffmpeg(*_source(fmt), "-t", str(SOURCE_SECONDS), "-an", "-c", "copy",
                                                     source, timeout=150))
    length, width, height = probe(source)
    longest = sorted(sorted(shots(source, length), key=lambda s: s[0] - s[1])[:SHOTS_PER_VIDEO])
    kept, frames = [], []
    for shot in longest:
        if image := frame_at("-i", str(source), at=moment(shot)):
            kept.append(shot)
            frames.append(image)
    grey = _ffmpeg("-i", source, "-vf", f"fps=1/{SAMPLE_EVERY},format=gray", "-f", "rawvideo", "-", timeout=120)
    samples = np.frombuffer(grey, dtype=np.uint8)[:len(grey) // (width * height) * width * height]
    return {"video": video, "info": info, "shots": kept, "frames": frames,
            "samples": samples.reshape(-1, height, width)}


def first_look(prepared: list[dict], pkg: dict) -> list[tuple[int, int, dict]]:
    """The first look's verdict on every shot, as (video index, shot index, verdict)."""
    every = [(v, s) for v, p in enumerate(prepared) for s in range(len(p["shots"]))]
    videos = "\n".join(f"Video {v + 1}: \"{p['video']['title']}\" uploaded by {p['video']['channel']}"
                       for v, p in enumerate(prepared))

    def ask(batch: list[tuple[int, int]], split: bool = True) -> list[tuple[int, int, dict]]:
        media = []
        for n, (v, s) in enumerate(batch, 1):
            media += [{"text": f"Frame {n}, video {v + 1} (uploaded by {prepared[v]['video']['channel']}):"},
                      _jpeg(prepared[v]["frames"][s])]
        try:
            answer = gemini.text_json(FIRST_LOOK, f"{_story(pkg)}\n{videos}\n\nJudge all {len(batch)} frames.",
                                      temperature=0.2, models=JUDGE_MODELS, media=media, timeout=JUDGE_TIMEOUT)
        except gemini.Exhausted as exc:
            # Both Gemma models answered one batch of 9 with four 500s running, and its frames from the shooting went
            # unjudged: some frame can fail a whole request, so each half goes again without the other.
            if not split or len(batch) < 2:
                raise
            log.warning("footage: a first look at %d frames failed, so each half goes again: %s", len(batch),
                        _quiet(exc))
            half = len(batch) // 2
            out = []
            for part in (batch[:half], batch[half:]):
                try:
                    out += ask(part, split=False)
                except gemini.Exhausted as again:
                    log.warning("footage: a first look at %d frames failed again: %s", len(part), _quiet(again))
            return out
        verdicts = {int(f["n"]): f for f in answer.get("frames") or [] if isinstance(f, dict)
                    and str(f.get("n", "")).isdigit()}
        log.info("footage: first look at %d frames by %s", len(batch), answer.get("_model"))
        return [(v, s, verdicts[n]) for n, (v, s) in enumerate(batch, 1) if n in verdicts]

    batches = [every[i:i + BATCH] for i in range(0, len(every), BATCH)]
    out = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in [pool.submit(ask, b) for b in batches]:
            try:
                out += future.result()
            except Exception as exc:  # noqa: BLE001 - the other batch may still have answered
                log.warning("footage: a first look failed: %s", _quiet(exc))
    return out


def score(verdict: dict) -> float:
    """The verdict's relevance as a number (a model may write "8")."""
    try:
        return float(verdict.get("relevance") or 0)
    except (TypeError, ValueError):
        return 0.0


def _yes(verdict: dict, key: str) -> bool:
    value = verdict.get(key)
    return value is True or str(value).strip().lower() in ("true", "yes", "1")


def promising(verdict: dict) -> bool:
    return (str(verdict.get("kind", "")).lower() == "footage" and score(verdict) >= LEAST_RELEVANCE - 1
            and not _yes(verdict, "foreign_logo") and not _yes(verdict, "graphic_content"))


def usable(verdict: dict) -> bool:
    return (_yes(verdict, "found") and str(verdict.get("kind", "")).lower() == "footage"
            and score(verdict) >= LEAST_RELEVANCE and not _yes(verdict, "foreign_logo")
            and not _yes(verdict, "text_heavy") and not _yes(verdict, "graphic_content"))


def window(box, width: int, height: int) -> tuple[int, int, int, int] | None:
    """The judge's [ymin, xmin, ymax, xmax] (0-1000) as pixels (x0, y0, x1, y1), or None if it isn't a sane box."""
    if not isinstance(box, list) or len(box) != 4:
        return None
    try:
        y0, x0, y1, x1 = (min(1000.0, max(0.0, float(b))) for b in box)
    except (TypeError, ValueError):
        return None
    if x1 - x0 < 150 or y1 - y0 < 150:
        return None
    return round(x0 * width / 1000), round(y0 * height / 1000), round(x1 * width / 1000), round(y1 * height / 1000)


def _run(shares: np.ndarray) -> int:
    """How far in from the start a steady band reaches: the last entry of at least OVER before three below it."""
    end = misses = 0
    for i, share in enumerate(shares):
        if share >= OVER:
            end, misses = i + 1, 0
        else:
            misses += 1
            if misses > 2:
                break
    return end


def trim(samples: np.ndarray, frame: Image.Image, shot: tuple[float, float], box: tuple[int, int, int, int],
         size: tuple[int, int]) -> tuple[int, int, int, int]:
    """The box without the graphics drawn over the edges of its footage (a side panel, a caption bar): bands along
    its sides that look the same in at least STEADY of the video's other shots with this layout, while footage
    changes from shot to shot. Frames with this layout match the shot's 240p `frame` outside the box at least 3/4 as
    well as the three best do (tickers and headlines change there too). Bands taking half the box are left alone:
    that is footage shown again, not a graphic."""
    if samples is None or len(samples) < 6:
        return box
    sh, sw = samples.shape[1:]
    g = np.asarray(frame.convert("L").resize((sw, sh)), dtype=np.int16)
    fx, fy = sw / size[0], sh / size[1]
    x0, y0, x1, y1 = box
    a0, b0 = int(x0 * fx), int(y0 * fy)
    a1, b1 = max(a0 + 6, min(sw, int(np.ceil(x1 * fx)))), max(b0 + 6, min(sh, int(np.ceil(y1 * fy))))
    same = np.abs(samples.astype(np.int16) - g) < 12
    outside = np.ones((sh, sw), dtype=bool)
    outside[b0:b1, a0:a1] = False
    if outside.mean() < 0.1:
        return box
    times = np.arange(len(samples)) * SAMPLE_EVERY
    other = (times < shot[0]) | (times > shot[1])
    match = np.where(other, same[:, outside].mean(axis=1), 0.0)
    best = np.sort(match)[-3:]
    alike = other & (match >= 0.75 * float(np.median(best))) & (match > 0.15)
    if alike.sum() < 3:
        return box
    steady = same[alike].mean(axis=0) >= STEADY
    cols = steady[b0 + (b1 - b0) // 6: b1 - (b1 - b0) // 6, a0:a1].mean(axis=0)
    rows = steady[b0:b1, a0 + (a1 - a0) // 6: a1 - (a1 - a0) // 6].mean(axis=1)
    left, right, top, bottom = _run(cols), _run(cols[::-1]), _run(rows), _run(rows[::-1])
    if left + right > 0.5 * (a1 - a0):
        left = right = 0
    if top + bottom > 0.5 * (b1 - b0):
        top = bottom = 0
    return round(x0 + left / fx), round(y0 + top / fy), round(x1 - right / fx), round(y1 - bottom / fy)


def snap(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """The box with each side moved in onto a border, then pulled in by INSET of the frame: a border is a column (or
    row) up to REACH inside the side, or a hair outside it, where the brightness jumps by more than EDGE along at least
    BORDER of the side's length. A side with no border near it stays. Sides only move in: a box a little too small
    loses a sliver of footage, one a little too big shows the channel's graphics."""
    g = np.asarray(image.convert("L"), dtype=np.int16)
    h, w = g.shape
    x0, y0, x1, y1 = box
    cols = (np.abs(np.diff(g, axis=1)) > EDGE)[y0 + (y1 - y0) // 6: y1 - (y1 - y0) // 6].mean(axis=0)
    rows = (np.abs(np.diff(g, axis=0)) > EDGE)[:, x0 + (x1 - x0) // 6: x1 - (x1 - x0) // 6].mean(axis=1)

    def near(scores: np.ndarray, lo: int, hi: int, now: int) -> int:
        lo, hi = max(0, lo), min(len(scores), hi + 1)
        if hi <= lo:
            return now
        i = lo + int(np.argmax(scores[lo:hi]))
        return i + 1 if scores[i] >= BORDER else now   # the jump between pixels i and i + 1

    rx, ry, hx, hy = int(w * REACH), int(h * REACH), int(w * 0.01), int(h * 0.01)
    nx0, nx1 = near(cols, x0 - hx, x0 + rx, x0), near(cols, x1 - rx, x1 + hx, x1)
    ny0, ny1 = near(rows, y0 - hy, y0 + ry, y0), near(rows, y1 - ry, y1 + hy, y1)
    if nx1 - nx0 < (x1 - x0) * 0.6 or ny1 - ny0 < (y1 - y0) * 0.6:
        nx0, ny0, nx1, ny1 = box
    dx, dy = round(w * INSET), round(h * INSET)
    return nx0 + dx, ny0 + dy, nx1 - dx, ny1 - dy


def layout(width: int, height: int, media: tuple[int, int] = MEDIA) -> tuple[int, int, int, int, float]:
    """How a footage window of width x height is shown in a picture area of `media`: scaled to (fw, fh), of which the
    middle (cw, ch) is shown over the blurred fill; and the scale."""
    fit = min(media[0] / width, media[1] / height)
    scale = min(max(media[0] / width, media[1] / height), fit * ZOOM, max(fit, UPSCALE_MOST))
    fw, fh = round(width * scale / 2) * 2, round(height * scale / 2) * 2
    return fw, fh, min(fw, media[0]), min(fh, media[1]), scale


def second_look(prepared: dict, s: int, first: dict, pkg: dict) -> dict | None:
    """A sharp frame of shot `s` judged again on its own; with the footage window it found, without graphics over its
    edges and snapped to its borders, if it is usable footage. Its relevance is the mean of both looks': the same
    frame drew a 10 and a 5 from the second look in two runs."""
    hint = str(first.get("what", ""))
    shot = prepared["shots"][s]
    sharp = candidates(prepared["info"], 1080)
    image, fmt = None, None
    for fmt in sharp[:3]:
        if image := frame_at(*_source(fmt), at=moment(shot)):
            break
    if image is None:
        return None
    video = prepared["video"]
    answer = gemini.text_json(SECOND_LOOK, f"{_story(pkg)}\nThe video: \"{video['title']}\" uploaded by "
                                           f"{video['channel']}. A first look saw: {hint}",
                              temperature=0.2, models=JUDGE_MODELS, media=[_jpeg(image.resize((960, 540)))],
                              timeout=JUDGE_TIMEOUT)
    answer["relevance"] = (score(answer) + score(first)) / 2
    box = window(answer.get("box"), *image.size)
    if not usable(answer) or box is None:
        log.info("footage: %s at %.1f s not taken: %s", video["id"], moment(shot),
                 {k: answer.get(k) for k in ("found", "kind", "relevance", "foreign_logo", "text_heavy", "what")})
        return None
    x0, y0, x1, y1 = snap(image, trim(prepared.get("samples"), prepared["frames"][s], shot, box, image.size))
    scale = layout(x1 - x0, y1 - y0)[4]
    if scale > UPSCALE_MOST:
        log.info("footage: %s at %.1f s: its window (%dx%d) is too small", video["id"], moment(shot), x1 - x0, y1 - y0)
        return None
    return {"verdict": answer, "fmt": fmt, "box": (x0, y0, x1, y1), "scale": round(scale, 2)}


def cut(fmt: dict, start: float, seconds: float, box: tuple[int, int, int, int], out: Path,
        media: tuple[int, int] = MEDIA) -> Path:
    """`seconds` of the stream from `start` (ffmpeg fetches only those segments): the footage window, enlarged as
    layout() says for a picture area of `media` over a blurred, darkened copy of itself, at 30 fps and without
    sound."""
    x0, y0, x1, y1 = box
    w, h = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
    fw, fh, cw, ch, _ = layout(w, h, media)
    bw, bh = round(media[0] / 8) * 2, round(media[1] / 8) * 2  # the fill is blurred at a quarter of the size
    graph = (f"[0:v]crop={w}:{h}:{x0}:{y0},setsar=1,split[a][b];"
             f"[b]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},gblur=sigma=7,"
             f"scale={media[0]}:{media[1]},eq=brightness=-0.08:saturation=0.85[bg];"
             f"[a]scale={fw}:{fh}:flags=lanczos,crop={cw}:{ch}[fg];"
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v]")
    _ffmpeg("-ss", f"{start:.3f}", *_source(fmt), "-t", f"{seconds:.3f}", "-filter_complex", graph, "-map", "[v]",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-movflags", "+faststart", out, timeout=150)
    return out


def credit(video: dict) -> str:
    return f"वीडियो: {video['channel']} / YouTube (CC BY)"


def cite(video: dict) -> str:
    """The description's attribution, as CC BY asks: who, what, where, the licence and what was changed."""
    return (f"वीडियो: {video['channel']}, “{video['title'][:90]}”, https://youtu.be/{video['id']}, {LICENCE}; "
            "छोटे हिस्से, काटकर और बिना आवाज़")


def attribution(clips: list[dict]) -> list[str]:
    """cite() for many clips in fewer bytes: the licence and what was changed once, then each video's channel, title
    and link, once a video."""
    videos: dict[str, dict] = {}
    for clip in clips:
        if clip.get("video"):
            videos.setdefault(clip["video"], clip)
    if not videos:
        return []
    return [f"वीडियो (YouTube, {LICENCE}; छोटे हिस्से, काटकर और बिना आवाज़):"] + [
        f"{c['channel']}, {'“' + c['title'][:70] + '”, ' if c.get('title') else ''}https://youtu.be/{v}"
        for v, c in videos.items()]


def _through_warp(fresh: bool = False, local: bool = False) -> bool:
    try:
        _warp(fresh, local)
        return True
    except Exception as exc:  # noqa: BLE001 - no footage this time; the Short goes on with photos
        log.warning("footage: WARP failed: %s", _quiet(exc))
        return False


def _route() -> str:
    return "the footage VM's WARP" if _proxy == VM_URL else "this host's WARP" if _proxy else "this host"


def _reroute(n: int) -> None:
    """The exit for the n-th try again of a refused video: from this host's own address, its WARP; with the footage VM,
    a new VM device, then this host's WARP (another exit), then the VM's again, then this host's on a new device;
    without the VM, this host's WARP on a new device."""
    global _refused_until
    if not _proxy:
        _refused_until = datetime.now(timezone.utc) + REFUSED_REST
        _through_warp(local=True)
    elif os.environ.get("FOOTAGE_HOST"):
        fresh, local = ((True, False), (False, True), (False, False), (True, True))[(n - 1) % 4]
        _through_warp(fresh, local)
    else:
        _through_warp(fresh=True, local=True)


def _prepare_all(picked: list[dict], folder: Path, until: float) -> tuple[list[dict], bool]:
    """The videos prepare() could read, and whether YouTube refused any of them. The first video is asked for alone,
    and on a refusal again after each of ROUTE_WAITS through the next exit (_reroute) while `until` allows; once one is
    served, the rest go at once."""
    infos: dict[str, dict] = {}
    queue, refused, tries = list(picked), False, 0
    while queue and not infos:
        video = queue[0]
        try:
            infos[video["id"]] = streams(video)
        except Refused as exc:
            refused = True
            log.warning("footage: YouTube refused %s for %s: %s", _route(), video["id"], _quiet(exc))
            if tries == len(ROUTE_WAITS) or time.time() + ROUTE_WAITS[tries] > until:
                return [], True
            log.info("footage: asking again in %d s through another exit", ROUTE_WAITS[tries])
            time.sleep(ROUTE_WAITS[tries])
            tries += 1
            _reroute(tries)
        except Exception as exc:  # noqa: BLE001 - another video may still be read
            log.warning("footage from %s failed: %s", video["id"], _quiet(exc))
            queue.pop(0)
    if tries:
        log.info("footage: served through %s after %d tries again", _route(), tries)
    prepared = []
    with ThreadPoolExecutor(max_workers=max(1, len(queue))) as pool:
        for video, future in [(v, pool.submit(prepare, v, folder, infos.get(v["id"]))) for v in queue]:
            try:
                p = future.result()
                if p["frames"]:
                    prepared.append(p)
            except Refused as exc:
                refused = True
                log.warning("footage: YouTube refused %s for %s: %s", _route(), video["id"], _quiet(exc))
            except Exception as exc:  # noqa: BLE001
                log.warning("footage from %s failed: %s", video["id"], _quiet(exc))
    return prepared, refused


def for_story(pkg: dict, folder: Path, now: datetime, since: datetime | None = None,
              media: dict[str, tuple[int, int]] | None = None) -> list[dict]:
    """Up to MOST_CLIPS clips of real footage for the story, the most relevant first; [] when there is none we may use,
    or a step fails (the Short goes on with photos). With `media` ({name: picture area}), each clip is cut once for
    each picture area, in "paths" by name; "path" is the first."""
    global _refused_until, _warp_refused_until
    if not os.environ.get("YOUTUBE_OAUTH_JSON"):
        return []
    if _warp_refused_until and now < _warp_refused_until:
        log.info("footage: none until %s, as YouTube takes this host and WARP for bots", _warp_refused_until)
        return []
    if ((_refused_until and now < _refused_until) or os.environ.get("FOOTAGE_HOST")) and not _through_warp():
        return []
    after = max(now - LOOK_BACK, (since or now) - timedelta(hours=12))
    try:
        found = search(_client(), queries(pkg), after.astimezone(timezone.utc))
    except Exception as exc:  # noqa: BLE001 - footage is a bonus; the Short goes on without it
        log.warning("footage search failed: %s", exc)
        return []
    usable = choose(found, pkg)
    picked = usable[:CANDIDATES] + [v for v in usable[CANDIDATES:] if v["seconds"] <= SHORT_CLIP][:SHORT_EXTRA]
    log.info("footage: %d CC BY videos found, %d looked at: %s", len(found), len(picked),
             [(v["id"], v["channel"], v["title"][:50]) for v in picked])
    if not picked:
        return []
    folder.mkdir(parents=True, exist_ok=True)
    prepared, refused = _prepare_all(picked, folder, time.time() + PATIENCE)
    if not prepared:
        if refused:
            _warp_refused_until = datetime.now(timezone.utc) + WARP_REST
        log.info("footage: no video could be read%s", " (YouTube took us for a bot)" if refused else "")
        return []
    begun = time.time()  # the looks and cuts get DEADLINE of their own, however long a refusal took to pass
    looks = sorted((x for x in first_look(prepared, pkg) if promising(x[2])), key=lambda x: (-score(x[2]), x[0], x[1]))
    chosen: list[tuple[int, int, dict]] = []
    for v, s, verdict in looks:
        if sum(1 for c in chosen if c[0] == v) < PER_VIDEO and len(chosen) < SECOND_LOOKS:
            chosen.append((v, s, verdict))
    log.info("footage: %d promising shots, looking again at %d: %s", len(looks), len(chosen),
             [(prepared[v]["video"]["id"], round(moment(prepared[v]["shots"][s]), 1), x.get("relevance"), x.get("what"))
              for v, s, x in chosen])
    if time.time() - begun > DEADLINE:
        return []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [(v, s, pool.submit(second_look, prepared[v], s, x, pkg)) for v, s, x in chosen]
        taken = []
        for v, s, future in futures:
            try:
                if seen := future.result():
                    taken.append((v, s, seen))
            except Exception as exc:  # noqa: BLE001
                log.warning("footage: a second look failed: %s", _quiet(exc))
    taken.sort(key=lambda t: (-score(t[2]["verdict"]), t[0], t[1]))
    taken = taken[:MOST_CLIPS]
    if time.time() - begun > DEADLINE:
        return []

    def make(n: int, v: int, s: int, seen: dict) -> dict:
        video, (start, end) = prepared[v]["video"], prepared[v]["shots"][s]
        begin = start + 0.25 if end - start - 0.25 >= SHOT_LEAST else start  # past a dissolve from the shot before
        seconds = round(min(CLIP_MOST, end - begin - 0.1), 2)
        paths = {}
        for name, size in (media or {"": MEDIA}).items():
            path = folder / f"clip{n}-{video['id']}{'-' + name if name else ''}.mp4"
            paths[name] = str(cut(seen["fmt"], begin, seconds, seen["box"], path, size))
        return {"path": next(iter(paths.values())), **({"paths": paths} if media else {}), "seconds": seconds,
                "video": video["id"], "channel": video["channel"], "title": video["title"][:90],
                "start": round(begin, 2), "box": list(seen["box"]),
                "scale": seen["scale"], "what": str(seen["verdict"].get("what", ""))[:80],
                "relevance": score(seen["verdict"]), "credit": credit(video), "cite": cite(video)}

    clips = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in [pool.submit(make, n, v, s, seen) for n, (v, s, seen) in enumerate(taken)]:
            try:
                clips.append(future.result())
            except Exception as exc:  # noqa: BLE001
                log.warning("footage: a cut failed: %s", _quiet(exc))
    log.info("footage: %d clips in %.0f s: %s", len(clips), time.time() - begun,
             [(c["video"], c["start"], c["relevance"], c["what"]) for c in clips])
    return clips
