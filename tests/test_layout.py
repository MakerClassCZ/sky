from sky.layout import Rect, compute


def test_sky_landscape_800x480():
    z = compute(800, 480, "sky")
    assert z.map == Rect(0, 0, 480, 480)
    assert z.info == Rect(480, 0, 320, 480)
    assert z.header_big
    assert len(z.columns) == 1 and z.columns[0].x == 480
    assert z.header.bottom == z.columns[0].y


def test_sky_portrait_480x800():
    z = compute(480, 800, "sky")
    assert z.map == Rect(0, 0, 480, 480)
    assert z.info == Rect(0, 480, 480, 320)
    assert z.header_big
    assert len(z.columns) == 2 and z.columns[1].x == 240


def test_horizon_landscape_800x480():
    z = compute(800, 480, "horizon")
    assert z.map == Rect(0, 0, 800, 288)
    assert z.info == Rect(0, 288, 800, 192)
    assert len(z.columns) == 3
    assert z.header_big
    assert z.columns[0].h >= 8 * 16


def test_horizon_portrait_480x800():
    z = compute(480, 800, "horizon")
    assert z.map == Rect(0, 0, 480, 288)
    assert z.info.y == 288 and len(z.columns) == 1


def test_tiny_panel_has_no_info():
    z = compute(296, 128, "sky")
    assert z.map == Rect(0, 0, 128, 128)
    assert z.info is not None and z.info.w == 168  # 168 ≥ 112 → úzký sloupec
    z2 = compute(200, 128, "sky")
    assert z2.info is None and z2.columns == ()
    z3 = compute(128, 200, "sky")
    assert z3.info is None


def test_horizon_tiny_no_info():
    z = compute(296, 128, "horizon")
    assert z.info is None and z.map == Rect(0, 0, 296, 128)
