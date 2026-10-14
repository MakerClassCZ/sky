from PIL import Image

from sky.fonts import draw_text, fit, load_font, text_width
from sky.icons import ICONS, draw_icon


def test_font_metrics_and_czech_glyphs():
    f = load_font("8x16")
    assert (f.width, f.height) == (8, 16)
    for ch in "ěščřžýáíéúůťďň…°":
        assert f.glyph(ord(ch)) is not None, ch
    assert text_width(f, "ahoj") == 32


def test_fit_ellipsis():
    f = load_font("8x16")
    assert fit(f, "Meteorický roj Tauridy", 10 * 8) == "Meteorick…"
    assert fit(f, "krátké", 100) == "krátké"


def test_draw_text_sets_pixels():
    f = load_font("8x16")
    img = Image.new("P", (64, 16), 0)
    w = draw_text(img, (0, 0), "A", f, 1)
    assert w == 8
    assert any(img.getpixel((x, y)) == 1 for x in range(8) for y in range(16))
    assert all(img.getpixel((x, y)) == 0 for x in range(8, 64) for y in range(16))


def test_glyph_not_shifted():
    # 'I' (8x16) má svislou čáru uprostřed buňky; horní řádek buňky je prázdný
    f = load_font("8x16")
    g = f.glyph(ord("I"))
    cols = [x for x in range(8) if g.getpixel((x, 8)) == 255]
    assert cols and 2 <= cols[0] <= 4
    assert all(g.getpixel((x, 0)) == 0 for x in range(8))


def test_icons_shape_and_draw():
    for name, rows in ICONS.items():
        assert len(rows) == 16 and all(len(r) == 16 for r in rows), name
    img = Image.new("P", (16, 16), 0)
    draw_icon(img, (0, 0), "sun", 1)
    assert img.getpixel((7, 7)) == 1


def test_draw_text_halo():
    from PIL import Image
    from sky.fonts import draw_text_halo, load_font
    f = load_font("8x16")
    img = Image.new("P", (40, 30), 5)
    w = draw_text_halo(img, (10, 8), "I", f, 0, 7)
    assert w == 8
    px = img.load()
    inked = [(x, y) for x in range(40) for y in range(30) if px[x, y] == 0]
    halo = [(x, y) for x in range(40) for y in range(30) if px[x, y] == 7]
    assert inked and halo
    for x, y in inked:                      # každý sousední pixel kolem písma je obrys nebo písmo
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                assert px[x + dx, y + dy] in (0, 7)
    assert px[2, 2] == 5 and px[38, 28] == 5
