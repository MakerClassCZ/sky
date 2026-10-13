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
