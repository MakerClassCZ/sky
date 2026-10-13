import io

from PIL import Image

from sky.output import encode
from sky.palette import make_palette


def _img(colors, mode="night"):
    p = make_palette(colors, mode)
    im = Image.new("P", (40, 20), p["bg"])
    im.putpalette(p.flat())
    im.putpixel((1, 1), p["fg"])
    return im


def test_png_bw_is_two_colors():
    data, mime = encode(_img("bw"), "png", 0)
    assert mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n"
    back = Image.open(io.BytesIO(data))
    assert back.size == (40, 20) and back.mode in ("P", "1")
    assert len(back.getcolors()) == 2
    assert data[24] == 1          # IHDR bit depth = 1


def test_png_bwry_palette_order():
    data, _ = encode(_img("bwry"), "png", 0)
    back = Image.open(io.BytesIO(data))
    assert back.mode == "P"
    assert back.getpalette()[:12] == [255, 255, 255, 0, 0, 0, 255, 0, 0, 255, 255, 0]
    assert data[24] == 2          # IHDR bit depth = 2


def test_bmp_bw_is_1bpp():
    data, mime = encode(_img("bw"), "bmp", 0)
    assert mime == "image/bmp" and data[:2] == b"BM"
    assert int.from_bytes(data[28:30], "little") == 1
    back = Image.open(io.BytesIO(data))
    assert back.size == (40, 20)
    assert back.convert("RGB").getpixel((1, 1)) == (255, 255, 255)
    assert back.convert("RGB").getpixel((5, 5)) == (0, 0, 0)


def test_bmp_bwr_keeps_palette():
    data, _ = encode(_img("bwr"), "bmp", 0)
    back = Image.open(io.BytesIO(data))
    assert back.mode == "P" and back.getpalette()[:9] == [255, 255, 255, 0, 0, 0, 255, 0, 0]


def test_rotation_swaps_size_and_keeps_pixel():
    data, _ = encode(_img("bw"), "png", 90)
    back = Image.open(io.BytesIO(data))
    assert back.size == (20, 40)
    # pixel (1,1) z originálu se po otočení o 90° po směru hodin dostane na (20-1-1, 1) = (18, 1)
    assert back.convert("RGB").getpixel((18, 1)) == (255, 255, 255)
    assert back.convert("RGB").getpixel((1, 1)) == (0, 0, 0)


def test_png_spectra_palette():
    data, _ = encode(_img("spectra"), "png", 0)
    back = Image.open(io.BytesIO(data))
    assert back.mode == "P" and back.getpalette()[:18] == [255, 255, 255, 0, 0, 0, 255, 0, 0, 255, 255, 0, 0, 0, 255, 0, 255, 0]
    assert data[24] == 4          # IHDR bit depth = 4 (6 barev)
