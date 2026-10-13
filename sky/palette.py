"""Role barev → indexy palety (spec §7)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

RGB = [(255, 255, 255), (0, 0, 0), (255, 0, 0), (255, 255, 0), (0, 0, 255), (0, 255, 0)]
NCOLORS = {"bw": 2, "bwr": 3, "bwry": 4, "spectra": 6}   # spectra = E Ink Spectra 6
ROLES = ("bg", "fg", "star", "line", "label", "planet", "sun",
         "moon_lit", "moon_dark", "iss", "today", "horizon", "ecliptic")


@dataclass(frozen=True)
class Palette:
    colors: str
    mode: str
    index: Mapping[str, int]

    def __getitem__(self, role: str) -> int:
        return self.index[role]

    @property
    def ncolors(self) -> int:
        return NCOLORS[self.colors]

    def flat(self) -> list[int]:
        return [c for rgb in RGB[: self.ncolors] for c in rgb]


def make_palette(colors: str, mode: str) -> Palette:
    bg, fg = (1, 0) if mode == "night" else (0, 1)
    idx = {r: fg for r in ROLES}
    idx["bg"] = bg
    idx["moon_dark"] = bg
    if colors in ("bwr", "bwry", "spectra"):
        for r in ("planet", "sun", "iss", "today"):
            idx[r] = 2
    if colors in ("bwry", "spectra"):
        idx["sun"] = 3            # Měsíc zůstává černobílý: žlutý kotouč není k poznání
    if colors == "spectra":
        idx["iss"] = 5            # zelená
        idx["ecliptic"] = 4       # modrá; na obzoru byla špatně čitelná, u tečkované ekliptiky nevadí
    return Palette(colors, mode, idx)
