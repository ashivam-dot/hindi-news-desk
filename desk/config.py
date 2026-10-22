"""Everything that names the channel. Placeholders stay until the coordinator supplies the real values; the upload
step refuses to run while CHANNEL_ID is not a real YouTube channel id."""
from __future__ import annotations

import os
import re

# Channel identity. NAME is shown on the end card only once it is set; None keeps the card brand-free.
NAME: str | None = os.environ.get("DESK_CHANNEL_NAME") or None  # TBD
NAME_HI: str | None = os.environ.get("DESK_CHANNEL_NAME_HI") or None  # TBD, the name in Devanagari for the end card
HANDLE: str | None = os.environ.get("DESK_CHANNEL_HANDLE") or None  # TBD, e.g. "@example"
CHANNEL_ID: str = os.environ.get("DESK_CHANNEL_ID") or "TBD"  # "UC..." of the Hindi channel
REPO = "ashivam-dot/hindi-news-desk"  # temporary slug; may be renamed
SITE = f"https://github.com/{REPO}"
CONTACT = "aksh.shivam17@gmail.com"

# Uploads before 2026-10-22 carry MARKER + story id as a public tag; new uploads carry none (the ledger keeps their
# video ids, see youtube.find). Keep it unchanged so the old uploads are still found.
MARKER = "hindi-news-desk:"
# Repository variable DESK_UNTAG=true lets each live run take the old marker tag off a few uploads (youtube.untag),
# after the ledger has kept their ids. Off by default: it is a YouTube write the owner turns on.
# The same variable switches on the one-off channel jobs (desk/channel.py), since it is the one the run workflow
# already passes for channel writes: a list of words, "untag" (or "true"), "about" (the About text, keywords,
# language and country) and "playlists" (series playlists and their Home-tab sections), e.g. "untag about playlists".
_JOBS = {w for w in re.split(r"[\s,]+", os.environ.get("DESK_UNTAG", "").lower()) if w}
UNTAG = bool(_JOBS & {"true", "untag"})
CHANNEL_JOBS = frozenset(_JOBS & {"about", "playlists"})
CATEGORY = "25"  # News & Politics
LANGUAGE = "hi"

# The English sister channel whose stories this desk must not duplicate (see desk/orbitwire.py).
ORBITWIRE_REPO = "ashivam-dot/rebuilt-in-3d"
ORBITWIRE_STATE = f"https://raw.githubusercontent.com/{ORBITWIRE_REPO}/state"

# Stories Wikipedia has no article for yet (nw- ids, told only from trusted outlets' reporting; see CHANNEL.md). Off
# by default: the radar still finds and records them; the repository variable DESK_NEW_STORIES=true lets them run.
NEW_STORIES = os.environ.get("DESK_NEW_STORIES", "").lower() == "true"
# India explainers (desk/explain.py, kh- ids) are found and recorded every run; DESK_EXPLAINERS=true lets them run.
EXPLAINERS = os.environ.get("DESK_EXPLAINERS", "").lower() == "true"
# A dry run that tries only one kind of candidate ("explainer"); ignored by runs that can publish.
DRY_KIND = os.environ.get("DESK_DRY_KIND") or None

# How pictures are put to beats (SYNC-AUDIT 4.1 step 3): "anchored" shows only what a beat names, else a text card
# (desk/match.py); "legacy" is the old name-then-fill assignment (visuals.assign_legacy), kept as a rollback switch.
MATCHER = (os.environ.get("DESK_MATCHER") or "anchored").strip().lower()  # run.yml: vars.DESK_MATCHER

CHANNEL_ID_FORMAT = re.compile(r"^UC[0-9A-Za-z_-]{22}$")


def channel_id_ready() -> bool:
    return bool(CHANNEL_ID_FORMAT.match(CHANNEL_ID))
