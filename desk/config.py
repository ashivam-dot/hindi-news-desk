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

# Every upload carries MARKER + story id as a tag, so a story is never uploaded twice. Never change it after the
# first public upload.
MARKER = "hindi-news-desk:"
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

CHANNEL_ID_FORMAT = re.compile(r"^UC[0-9A-Za-z_-]{22}$")


def channel_id_ready() -> bool:
    return bool(CHANNEL_ID_FORMAT.match(CHANNEL_ID))
