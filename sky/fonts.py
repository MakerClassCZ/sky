"""Bitmapové fonty Spleen (BDF) – vlastní parser, Unicode bez omezení na 256 znaků."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

FONT_DIR = Path(__file__).parent / "fonts"
ELLIPSIS = "…"


class BdfFont:
    def __init__(self, width: int, height: int, xoff: int, yoff: int,
                 raw: dict[int, tuple[int, int, int, int, list[str]]]):
        self.width, self.height = width, height
        self._xoff, self._yoff = xoff, yoff
        self._raw = raw                      # cp → (bw, bh, bx, by, hexrows)
        self._cache: dict[int, Image.Image | None] = {}

    def glyph(self, cp: int) -> Image.Image | None:
        """Maska znaku v režimu '1' (255 = kreslit) o velikosti buňky, nebo None."""
        if cp in self._cache:
            return self._cache[cp]
        spec = self._raw.get(cp)
        if spec is None:
            self._cache[cp] = None
            return None
        bw, bh, bx, by, rows = spec
        cell = Image.new("1", (self.width, self.height), 0)
        if bw > 0 and bh > 0 and rows:
            nbytes = (bw + 7) // 8
            data = b"".join(bytes.fromhex(r.ljust(nbytes * 2, "0")[: nbytes * 2]) for r in rows)
            bmp = Image.frombytes("1", (bw, bh), data)
            ascent = self.height + self._yoff
            dx = bx - self._xoff
            dy = ascent - (by + bh)
            cell.paste(bmp, (dx, dy))
        self._cache[cp] = cell
        return cell


def parse_bdf(text: str) -> BdfFont:
    fw = fh = fx = fy = 0
    raw: dict[int, tuple[int, int, int, int, list[str]]] = {}
    enc = None
    bbx = (0, 0, 0, 0)
    rows: list[str] | None = None
    for line in text.splitlines():
        if rows is not None:
            if line == "ENDCHAR":
                if enc is not None and enc >= 0:
                    raw[enc] = (*bbx, rows)
                rows = None
                enc = None
            else:
                rows.append(line.strip())
            continue
        if line.startswith("FONTBOUNDINGBOX "):
            fw, fh, fx, fy = map(int, line.split()[1:5])
        elif line.startswith("ENCODING "):
            enc = int(line.split()[1])
        elif line.startswith("BBX "):
            bbx = tuple(map(int, line.split()[1:5]))  # type: ignore[assignment]
        elif line == "BITMAP":
            rows = []
    return BdfFont(fw, fh, fx, fy, raw)


@lru_cache(maxsize=None)
def load_font(name: str) -> BdfFont:
    path = FONT_DIR / f"spleen-{name}.bdf"
    return parse_bdf(path.read_text(encoding="utf-8", errors="replace"))


def text_width(font: BdfFont, text: str) -> int:
    return len(text) * font.width


def fit(font: BdfFont, text: str, max_w: int) -> str:
    n = max_w // font.width
    if len(text) <= n:
        return text
    if n <= 1:
        return ELLIPSIS[:n]
    return text[: n - 1] + ELLIPSIS


def draw_text(img: Image.Image, xy: tuple[float, float], text: str, font: BdfFont, index: int) -> int:
    x, y = int(xy[0]), int(xy[1])
    for ch in text:
        g = font.glyph(ord(ch)) or font.glyph(0x3F)
        if g is not None:
            img.paste(index, (x, y, x + font.width, y + font.height), mask=g)
        x += font.width
    return len(text) * font.width
