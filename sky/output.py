"""Kódování výsledného obrazu: PNG / BMP, rotace (spec §7)."""
from __future__ import annotations

import io

from PIL import Image

MIME = {"png": "image/png", "bmp": "image/bmp"}


def encode(img: Image.Image, fmt: str, rot: int) -> tuple[bytes, str]:
    """`rot` je otočení po směru hodin v násobcích 90°."""
    if rot:
        img = img.rotate(-rot, expand=True)
    buf = io.BytesIO()
    if fmt == "bmp":
        palette = img.getpalette() or []
        if len(palette) // 3 <= 2:
            # 1 bpp: index 0 = bílá, 1 = černá → převod přes RGB drží barvy, ne indexy
            bw = img.convert("RGB").convert("L").point(lambda v: 255 if v >= 128 else 0)
            bw.convert("1", dither=Image.Dither.NONE).save(buf, "BMP")
        else:
            img.save(buf, "BMP")
    else:
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue(), MIME[fmt]
