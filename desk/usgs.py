"""USGS earthquake feed (public domain): which trending earthquake stories are big enough to break.

This desk tells earthquakes as photo stories from their Wikipedia article; USGS supplies the magnitude and PAGER
alert that decide whether one may take the breaking lane.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import net

FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"


@dataclass
class Quake:
    id: str
    mag: float
    place: str
    time: datetime
    lat: float
    lon: float
    depth: float
    alert: str | None
    sig: int
    url: str

    @property
    def age_hours(self) -> float:
        return (datetime.now(timezone.utc) - self.time).total_seconds() / 3600


def _quake(feature: dict) -> Quake:
    p, (lon, lat, depth) = feature["properties"], feature["geometry"]["coordinates"]
    return Quake(feature["id"], float(p["mag"]), p["place"] or "", datetime.fromtimestamp(p["time"] / 1000, timezone.utc),
                 float(lat), float(lon), float(depth), p.get("alert"), int(p.get("sig") or 0), p["url"])


def recent() -> list[Quake]:
    return [_quake(f) for f in net.get_json(FEED)["features"] if f["properties"].get("type") == "earthquake"]
