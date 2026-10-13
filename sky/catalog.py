"""Hvězdy a souhvězdí z dat d3-celestial (BSD-3), převod lon → RA."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"


def lon_to_ra_hours(lon: float) -> float:
    return (lon % 360.0) / 15.0


def _clean(name: str) -> str:
    """Data používají U+2005 (čtvrtinová mezera); fonty ji nemají."""
    return " ".join(name.replace(" ", " ").split())


@dataclass(frozen=True)
class ConstName:
    id: str
    cs: str
    en: str
    rank: int
    ra_hours: float
    dec: float

    def label(self, lang: str) -> str:
        return self.cs if lang == "cs" else self.en


@dataclass(frozen=True)
class Catalog:
    ra_hours: np.ndarray
    dec_deg: np.ndarray
    mag: np.ndarray
    lines: list[tuple[str, list[np.ndarray]]]
    names: dict[str, ConstName]


@lru_cache(maxsize=None)
def load_catalog(mag_limit: float = 4.5) -> Catalog:
    stars = json.loads((DATA_DIR / "stars.6.json").read_text(encoding="utf-8"))
    ra, dec, mag = [], [], []
    for f in stars["features"]:
        m = float(f["properties"]["mag"])
        if m <= mag_limit:
            lon, lat = f["geometry"]["coordinates"]
            ra.append(lon_to_ra_hours(lon))
            dec.append(lat)
            mag.append(m)

    lines_json = json.loads((DATA_DIR / "constellations.lines.json").read_text(encoding="utf-8"))
    lines = []
    for f in lines_json["features"]:
        segs = [np.array([[lon_to_ra_hours(x), y] for x, y in part], dtype=float)
                for part in f["geometry"]["coordinates"] if len(part) >= 2]
        lines.append((f["id"], segs))

    names_json = json.loads((DATA_DIR / "constellations.json").read_text(encoding="utf-8"))
    names = {}
    for f in names_json["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        names[f["id"]] = ConstName(f["id"], _clean(p.get("cz") or p["name"]), _clean(p.get("en") or p["name"]),
                                   int(p.get("rank", "3")), lon_to_ra_hours(lon), lat)
    return Catalog(np.array(ra), np.array(dec), np.array(mag), lines, names)
