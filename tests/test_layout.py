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
    from sky.layout import LINE_HEADER_H
    z = compute(800, 480, "horizon")
    # jednořádková hlavička a tři sloupce: Slunce+ISS | Měsíc | úkazy (min. 6 řádků)
    assert z.header_line and not z.header_big and z.header.h == LINE_HEADER_H
    assert len(z.columns) == 3
    assert z.columns[0].h >= 2 * 20 + 5 * 16 + 2 * 8      # Slunce + ISS
    assert z.columns[2].h >= 20 + 6 * 16                  # úkazy: titulek + 6 řádků
    assert z.map.h > 288 and z.map.h + z.info.h == 480


def test_horizon_portrait_480x800():
    from sky.layout import HORIZON_BAR
    z = compute(480, 800, "horizon")
    # obsahové rozložení: mapa dostane maximum, tedy strop 90° (4 px/° při 120° na 480 px)
    assert z.map == Rect(0, 0, 480, 480 * 90 // 120 + HORIZON_BAR)
    assert z.info.y == z.map.h and len(z.columns) == 1


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


def test_horizon_portrait_grows_map_without_events():
    full = compute(480, 800, "horizon", fov=90)     # fov 90: strop 90° je až na 504 px
    z = compute(480, 800, "horizon", sections=("sun", "moon", "iss"), fov=90)
    assert z.map.h > full.map.h
    assert z.info is not None and z.info.h < full.info.h
    assert z.map.h + z.info.h == 800
    # první sloupec (Slunce + Měsíc) má místo na 2 tituly, 6 řádků a mezery
    assert z.columns[0].h >= 2 * 20 + 6 * 16 + 2 * 8
    z2 = compute(480, 800, "horizon", sections=("sun", "moon"), fov=90)
    assert z2.map.h >= z.map.h            # obě mohou narazit na strop 90°


def test_horizon_landscape_never_shrinks_map_without_events():
    full = compute(800, 480, "horizon")
    z = compute(800, 480, "horizon", sections=("sun", "moon"))
    assert z.map.h >= full.map.h


def test_horizon_portrait_header_stays_big():
    z = compute(480, 800, "horizon")
    assert z.header_big and not z.header_line


def test_column_groups():
    from sky.layout import column_groups
    assert column_groups(1) == (("sun", "moon", "iss", "events"),)
    assert column_groups(2) == (("sun", "moon"), ("iss", "events"))
    assert column_groups(3) == (("sun", "iss"), ("moon",), ("events",))


def test_horizon_map_capped_at_90_degrees():
    from sky.layout import HORIZON_BAR
    # 480 px široký výsek 120° má 4 px/°, obzor→zenit je tedy max 360 px + pás světových stran
    z = compute(480, 800, "horizon", sections=("sun", "moon"), fov=120)
    assert z.map.h <= 480 * 90 // 120 + HORIZON_BAR
    assert z.info.bottom == 800
    # při fov 180 se strop uplatní i ve výchozím rozložení
    z = compute(480, 800, "horizon", fov=180)
    assert z.map.h <= 480 * 90 // 180 + HORIZON_BAR
