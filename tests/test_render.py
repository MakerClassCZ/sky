from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from sky import config
from sky.astro import Body, MoonInfo, SkyModel, SunInfo
from sky.events import Event
from sky.iss import IssInfo, Pass
from sky.params import parse
from sky.render import render

T = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)


def fake_model(mode="night"):
    stars = np.array([[50.0, 0.0, 2.0], [30.0, 180.0, 0.5], [-10.0, 90.0, 1.0], [70.0, 270.0, 4.4]])
    lines = [("UMa", [np.array([[50.0, 0.0], [55.0, 10.0], [60.0, 20.0]]),
                      np.array([[20.0, 170.0], [-5.0, 175.0]]),
                      np.array([[10.0, 350.0], [10.0, 10.0]])])]
    labels = [("Velká medvědice", 52.0, 5.0), ("Orion", 15.0, 150.0), ("Pod obzorem", -20.0, 0.0)]
    planets = [Body("mars", "Mars", 25.0, 200.0), Body("venus", "Venuše", -3.0, 250.0)]
    sun = SunInfo(-30.0 if mode == "night" else 30.0, 180.0, T, T, T, T)
    moon = MoonInfo(40.0, 120.0, 100.0, 0.6, T, None)
    return SkyModel(T, ZoneInfo("Europe/Prague"), 49.747, 13.378, mode, stars, lines, labels, planets, sun, moon)


ISS = IssInfo(True, 35.0, 220.0, Pass(T, T, 61.0, 180.0))
EVENTS = [Event(T.date(), "Uran v opozici", "scope"), Event(T.date(), "Úplněk", "moon")]
CFG = config.load({})


def _params(**q):
    base = {"lat": "49.747", "lon": "13.378"}
    base.update({k: str(v) for k, v in q.items()})
    return parse(base, CFG, "png")


@pytest.mark.parametrize("view", ["sky", "horizon"])
@pytest.mark.parametrize("w,h", [(800, 480), (480, 800)])
@pytest.mark.parametrize("colors", ["bw", "bwr", "bwry", "spectra"])
def test_render_sizes_and_palette(view, w, h, colors):
    img = render(_params(view=view, w=w, h=h, colors=colors), fake_model(), ISS, EVENTS)
    assert img.mode == "P" and img.size == (w, h)
    used = {i for i, c in enumerate(img.histogram()) if c}
    assert max(used) < {"bw": 2, "bwr": 3, "bwry": 4, "spectra": 6}[colors]
    assert len(used) >= 2


def test_night_background_is_black_index():
    img = render(_params(), fake_model("night"), ISS, EVENTS)
    assert img.getpixel((2, 2)) == 1
    img = render(_params(), fake_model("day"), ISS, EVENTS)
    assert img.getpixel((2, 2)) == 0


def test_horizon_segment_behind_observer_not_drawn():
    # segment az 350→10 při pohledu na jih (180) nesmí nakreslit čáru přes mapu
    p = _params(view="horizon", w=800, h=480, events=0, iss=0)
    m = fake_model()
    m_no = SkyModel(m.t, m.tz, m.lat, m.lon, m.mode, np.zeros((0, 3)), [], [], [], m.sun,
                    MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))
    m_seg = SkyModel(m.t, m.tz, m.lat, m.lon, m.mode, np.zeros((0, 3)),
                     [("X", [np.array([[10.0, 350.0], [10.0, 10.0]])])], [], [], m.sun,
                     MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))
    a = render(p, m_no, IssInfo(False, None, None, None), None)
    b = render(p, m_seg, IssInfo(False, None, None, None), None)
    assert a.tobytes() == b.tobytes()


def test_render_tiny_panel():
    img = render(_params(w=296, h=128), fake_model(), ISS, EVENTS)
    assert img.size == (296, 128)
    img = render(_params(w=200, h=128, view="horizon"), fake_model(), ISS, None)
    assert img.size == (200, 128)


def test_unavailable_sections_do_not_crash():
    img = render(_params(), fake_model(), IssInfo(False, None, None, None), None)
    assert img.size == (800, 480)
    img = render(_params(iss=0, events=0, lang="en"), fake_model(), ISS, [])
    assert img.size == (800, 480)


def _model_with(labels, planets, mode="night"):
    m = fake_model(mode)
    return SkyModel(m.t, m.tz, m.lat, m.lon, m.mode, np.zeros((0, 3)), [], labels, planets, m.sun,
                    MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))


def test_constellation_label_yields_to_planet():
    # popisek souhvězdí na místě planety se vynechá; obrázek je stejný jako bez popisku
    p = _params(events=0, iss=0)
    planet = [Body("mars", "Mars", 52.0, 5.0)]
    a = render(p, _model_with([("Velká medvědice", 52.0, 5.0)], planet), IssInfo(False, None, None, None), None)
    b = render(p, _model_with([], planet), IssInfo(False, None, None, None), None)
    assert a.tobytes() == b.tobytes()
    # ale bez planety se popisek nakreslí
    c = render(p, _model_with([("Velká medvědice", 52.0, 5.0)], []), IssInfo(False, None, None, None), None)
    assert c.tobytes() != b.tobytes()


def test_choose_box_avoids_placed():
    from sky.render import choose_box
    placed = [(100, 100, 140, 116)]
    inside = lambda b: b[0] >= 0 and b[1] >= 0
    # první kandidát koliduje, druhý je volný
    assert choose_box(placed, 40, 16, [(110, 100), (50, 100)], inside) == (50, 100, 90, 116)
    # žádný kandidát nevyhovuje (kolize nebo mimo hranice)
    assert choose_box(placed, 40, 16, [(110, 100), (-5, 100)], inside) is None
    assert len(placed) == 1


def test_two_planet_labels_do_not_overlap():
    p = _params(events=0, iss=0)
    two = [Body("mercury", "Merkur", 30.0, 180.0), Body("venus", "Venuše", 30.5, 180.5)]
    img = render(p, _model_with([], two), IssInfo(False, None, None, None), None)
    one = render(p, _model_with([], two[:1]), IssInfo(False, None, None, None), None)
    # pixely prvního popisku (vpravo od glyfu) zůstaly nedotčené a druhý popisek přibyl jinde
    from sky.projection import SkyProjection
    proj = SkyProjection(480, 180)
    x, y = proj.project(30.0, 180.0)
    region = (int(x) + 6, int(y) - 8, int(x) + 6 + 6 * 8, int(y) + 8)
    assert img.crop(region).tobytes() == one.crop(region).tobytes()
    assert img.tobytes() != one.tobytes()


def test_small_map_has_no_constellation_labels():
    p = _params(w=296, h=128, events=0, iss=0)
    a = render(p, _model_with([("Rak", 85.0, 0.0)], []), IssInfo(False, None, None, None), None)
    b = render(p, _model_with([], []), IssInfo(False, None, None, None), None)
    assert a.tobytes() == b.tobytes()


def test_line_styles_reduce_ink():
    # jedna dlouhá spojnice; čárkovaná má méně bodů než plná, tečkovaná ještě méně
    def ink(lines):
        p = _params(events=0, iss=0, view="horizon", lines=lines)
        m = fake_model()
        model = SkyModel(m.t, m.tz, m.lat, m.lon, m.mode, np.zeros((0, 3)),
                         [("X", [np.array([[10.0, 150.0], [30.0, 210.0]])])], [], [], m.sun,
                         MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))
        img = render(p, model, IssInfo(False, None, None, None), None)
        return img.crop((0, 0, 800, 260)).histogram()[0]   # bílé body v mapě (noc: 0 = bílá)
    solid, dashed, dotted = ink("solid"), ink("dashed"), ink("dotted")
    assert solid > dashed > dotted > 0
    assert dashed < 0.75 * solid and dotted < 0.5 * solid


def test_event_time_is_rendered():
    p = _params(iss=0)
    with_time = render(p, fake_model(), ISS, [Event(T.date(), "Zhuque-2E", "rocket", "13:40")])
    without = render(p, fake_model(), ISS, [Event(T.date(), "Zhuque-2E", "rocket")])
    assert with_time.tobytes() != without.tobytes()


def test_sun_glyph_size():
    # kotouč Slunce má průměr 15 px (poloměr 7) + paprsky; měřeno na prázdném modelu ve dne
    p = _params(events=0, iss=0)
    m = fake_model("day")
    model = SkyModel(m.t, m.tz, m.lat, m.lon, "day", np.zeros((0, 3)), [], [], [], SunInfo(60.0, 180.0, T, T, T, T),
                     MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))
    img = render(p, model, IssInfo(False, None, None, None), None)
    from sky.projection import SkyProjection
    x, y = SkyProjection(480, 180).project(60.0, 180.0)
    row = [img.getpixel((int(x) + dx, int(y))) for dx in range(-12, 13)]
    disc = sum(1 for v in row[12 - 8:12 + 9] if v != 0)     # vyplněné pixely kolem středu
    assert disc >= 15


def test_saturn_has_ring():
    # Saturn se kreslí s elipsou prstence: širší než ostatní planety na stejném místě
    p = _params(events=0, iss=0)
    m = fake_model()

    def width_of(key):
        model = SkyModel(m.t, m.tz, m.lat, m.lon, m.mode, np.zeros((0, 3)), [], [], [Body(key, "X", 60.0, 180.0)],
                         m.sun, MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))
        img = render(p, model, IssInfo(False, None, None, None), None)
        from sky.projection import SkyProjection
        x, y = SkyProjection(480, 180).project(60.0, 180.0)
        return sum(1 for dx in range(-14, 15) if img.getpixel((int(x) + dx, int(y))) != 1 and dx < 5)  # vlevo od popisku

    assert width_of("saturn barycenter") > width_of("mars")


def test_events_title_is_contextual():
    from sky.render import events_title
    assert events_title("cs", True, False) == "Úkazy"
    assert events_title("cs", True, True) == "Úkazy a starty"
    assert events_title("cs", False, True) == "Starty"
    assert events_title("en", True, True) == "Events and launches"
    assert events_title("en", False, True) == "Launches"


def test_iss_lines_join_when_wide():
    from sky.render import iss_lines
    tz = ZoneInfo("Europe/Prague")
    wide = iss_lines("cs", tz, ISS, 50)
    assert wide == ["út 13. 10. 22:00–22:00, max 61° J"]
    narrow = iss_lines("cs", tz, ISS, 25)
    assert narrow == ["út 13. 10. 22:00–22:00", "max 61° J"]
    assert iss_lines("cs", tz, IssInfo(True, 1.0, 2.0, None), 50) == ["žádný do 48 h"]
    assert iss_lines("en", tz, IssInfo(False, None, None, None), 50) == ["unavailable"]


def test_moon_lit_side_faces_sun():
    # pohled na sever (az=0): Slunce na JZ je na mapě dole vlevo... osvětlená strana musí mířit ke Slunci
    from sky.render import moon_lit_direction
    from sky.projection import SkyProjection
    proj = SkyProjection(480, 0)
    mx, my = proj.project(40.0, 120.0)
    sx, sy = proj.project(-10.0, 240.0)
    dx, dy = moon_lit_direction((mx, my), (sx, sy))
    assert abs(dx * dx + dy * dy - 1.0) < 1e-6
    assert (sx - mx) * dx + (sy - my) * dy > 0


def test_horizon_compass_labels_stay_inside():
    # fov 90 směrem na sever: SV a SZ leží přesně na krajích, popisek se nesmí oříznout
    p = _params(view="horizon", az=0, fov=90, events=0, iss=0)
    m = fake_model()
    model = SkyModel(m.t, m.tz, m.lat, m.lon, m.mode, np.zeros((0, 3)), [], [], [], m.sun,
                     MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))
    img = render(p, model, IssInfo(False, None, None, None), None)
    from sky.layout import compute
    z = compute(800, 480, "horizon", ("sun", "moon"), 90)
    bar_y = z.map.h - 24 + 5
    # v pravém krajním sloupci 16 px musí být kresba (druhé písmeno "V" ze "SV")
    right = sum(1 for x in range(784, 800) for y in range(bar_y, bar_y + 16) if img.getpixel((x, y)) == 0)
    left = sum(1 for x in range(0, 16) for y in range(bar_y, bar_y + 16) if img.getpixel((x, y)) == 0)
    assert right > 0 and left > 0


def test_sun_drawn_in_forced_night():
    p = _params(mode="night", events=0, iss=0)
    m = fake_model("day")
    model = SkyModel(m.t, m.tz, m.lat, m.lon, "night", np.zeros((0, 3)), [], [], [], SunInfo(60.0, 180.0, T, T, T, T),
                     MoonInfo(-10.0, 0.0, 0.0, 0.0, None, None))
    img = render(p, model, IssInfo(False, None, None, None), None)
    from sky.projection import SkyProjection
    x, y = SkyProjection(480, 180).project(60.0, 180.0)
    assert img.getpixel((int(x), int(y))) != 1


def test_iss_track_drawn():
    p = _params(events=0, colors="bwr")
    track = tuple((10.0 + i * 8.0, 120.0 + i * 15.0) for i in range(8))
    with_track = render(p, fake_model(), IssInfo(True, -20.0, 0.0, Pass(T, T, 70.0, 180.0), track), [])
    without = render(p, fake_model(), IssInfo(True, -20.0, 0.0, Pass(T, T, 70.0, 180.0)), [])
    assert with_track.tobytes() != without.tobytes()
    assert with_track.histogram()[2] > without.histogram()[2]      # přibyly červené body (dráha v barvě ISS)


def test_weather_line_in_sun_section():
    from sky.weather import CloudInfo
    p = _params(events=0, iss=0)
    a = render(p, fake_model(), IssInfo(False, None, None, None), [], CloudInfo(44, 10, T))
    b = render(p, fake_model(), IssInfo(False, None, None, None), [], None)
    assert a.tobytes() != b.tobytes()


def test_moon_direction_follows_great_circle():
    from sky.render import step_toward
    # krok 1° z (alt 40, az 180) směrem k bodu na az 180, alt -30: míří přímo dolů (k obzoru)
    a, z = step_toward(40.0, 180.0, -30.0, 180.0, 1.0)
    assert a == pytest.approx(39.0, abs=1e-6) and z == pytest.approx(180.0, abs=1e-6)
    # krok směrem k bodu o 90° azimutu dál na stejné výšce vede po velké kružnici, azimut roste
    a, z = step_toward(40.0, 180.0, 40.0, 270.0, 1.0)
    assert z > 180.0 and a > 40.0        # velká kružnice mezi dvěma body na alt 40 se vyklene výš
    # nulová vzdálenost nesmí spadnout
    assert step_toward(10.0, 10.0, 10.0, 10.0, 1.0) == pytest.approx((10.0, 10.0))


def test_body_label_clears_big_glyph():
    from sky.render import Ctx, _body_label
    from sky.fonts import load_font
    from sky.palette import make_palette
    from PIL import Image, ImageDraw
    img = Image.new("P", (200, 100))
    ctx = Ctx(img, ImageDraw.Draw(img), make_palette("bw", "night"), "cs", load_font("8x16"), load_font("12x24"),
              load_font("16x32"))
    placed = [(100 - 14, 50 - 14, 100 + 15, 50 + 15)]        # registrovaný glyf Slunce
    _body_label(ctx, placed, 100, 50, "Slunce", 0, lambda b: True, gap=16)
    assert len(placed) == 3                                  # glyf + popisek
    assert not any(placed[2][0] < b[2] and placed[2][2] > b[0] and placed[2][1] < b[3] and placed[2][3] > b[1]
                   for b in placed[:2])


def test_sunmoon_labels_change_image():
    a = render(_params(view="horizon", az=120, mode="day", iss=0, events=0), fake_model("day"), ISS, None)
    b = render(_params(view="horizon", az=120, mode="day", iss=0, events=0, sunmoon=1), fake_model("day"), ISS, None)
    assert a.tobytes() != b.tobytes()


def test_star_names_drawn_when_model_has_them():
    m = fake_model()
    named = SkyModel(m.t, m.tz, m.lat, m.lon, m.mode, m.stars, m.lines, m.labels, m.planets, m.sun, m.moon,
                     m.ecliptic, [("Vega", 50.0, 0.0, 2.0), ("Sirius", 30.0, 180.0, 0.5)])
    a = render(_params(iss=0, events=0), m, ISS, None)
    b = render(_params(iss=0, events=0), named, ISS, None)
    assert a.tobytes() != b.tobytes()
