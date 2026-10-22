"""What a Short is made of: the facts it may state (each with its source), the narration beats, and the scene."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Fact:
    key: str
    value: str
    source: str
    # Numbers the narration may say because of this fact, written as the narration writes them ("6.3", "8,700").
    numbers: list[str] = field(default_factory=list)
    # The field or sentence in the source that the value came from.
    evidence: str = ""
    # For a fact taken from outlet reporting: the independent owners whose articles state it (two or more).
    owners: list[str] = field(default_factory=list)


@dataclass
class Beat:
    text: str
    shot: str  # "photo:3", "photo:3/7" (a long beat cuts to photo 7 halfway) or "outro"
    card: dict | None = None
    pause_after: float = 0.3
    # The anchored matcher (desk/match.py): "card" when the beat names nothing that can be shown (an honest text card
    # over the shot's photo as backdrop, never a filler picture); the word of the beat that names the cut's picture
    # (a Hindi string: whisper's words drift from the beat's); the view (0 or 1) the beat's card sits over. Old
    # short.json files have none of them and load as before.
    plate: str = ""
    cut_word: str = ""
    card_view: int = 0
    cut_at: int = -1  # where in text cut_word is said (match.plan): compose cuts on that time, not its first one


def shot_photos(shot: str) -> list[int]:
    """The photo indices a beat's shot shows, in order ([] for the outro or a malformed shot)."""
    if not shot.startswith("photo:"):
        return []
    try:
        return [int(p) for p in shot.split(":", 1)[1].split("/")]
    except ValueError:
        return []


@dataclass
class Short:
    id: str
    kind: str
    title: str
    beats: list[Beat]
    facts: list[Fact]
    sources: list[str]
    loss: bool
    scene: dict
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    event_time: str = ""
    credits: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=1, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Short":
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["beats"] = [Beat(**b) for b in raw["beats"]]
        raw["facts"] = [Fact(**f) for f in raw["facts"]]
        return cls(**raw)

    @property
    def narration(self) -> str:
        return " ".join(b.text for b in self.beats)
