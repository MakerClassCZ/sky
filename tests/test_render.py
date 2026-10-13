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
@pytest.mark.parametrize("colors", ["bw", "bwr", "bwry"])
def test_render_sizes_and_palette(view, w, h, colors):
    img = render(_params(view=view, w=w, h=h, colors=colors), fake_model(), ISS, EVENTS)
    assert img.mode == "P" and img.size == (w, h)
    used = {i for i, c in enumerate(img.histogram()) if c}
    assert max(used) < {"bw": 2, "bwr": 3, "bwry": 4}[colors]
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
