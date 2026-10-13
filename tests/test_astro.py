from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from sky import astro, config
from sky.catalog import load_catalog
from sky.params import parse

CACHE = Path("cache")
ephem = pytest.mark.skipif(not (CACHE / "de421.bsp").exists(), reason="de421.bsp missing (python -m sky warmup)")
PLZEN = {"lat": "49.747", "lon": "13.378"}


def test_first_or_none_when_no_event():
    class T:
        def __init__(self, d):
            self._d = d

        def utc_datetime(self):
            return self._d

    d = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert astro.first_or_none([T(d)], [False]) is None
    assert astro.first_or_none([T(d)], [True]) == d
    assert astro.first_or_none([], []) is None


@ephem
def test_night_in_plzen_and_polaris():
    e = astro.get_ephemeris(CACHE)
    p = parse(PLZEN, config.load({}), "png")
    t = datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc)
    m = astro.compute(p, e, load_catalog(), "cs", t)
    assert m.mode == "night"
    assert m.sun.alt < -20
    cat = load_catalog()
    i = int(np.argmax(cat.dec_deg))          # Polárka
    alt, az, _ = m.stars[i]
    assert abs(alt - 49.7) < 1.0 and (az < 1.5 or az > 358.5)
    assert m.tz.key == "Europe/Prague"
    assert len(m.planets) == 7 and all(isinstance(b.alt, float) for b in m.planets)
    assert any(lbl == "Velká medvědice" for lbl, _, _ in m.labels)
    assert len(m.lines) == len(cat.lines)
    assert all(seg.shape[1] == 2 for _, segs in m.lines for seg in segs)


@ephem
def test_sun_times_plzen():
    e = astro.get_ephemeris(CACHE)
    p = parse(PLZEN, config.load({}), "png")
    t = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    m = astro.compute(p, e, load_catalog(), "cs", t)
    assert m.mode == "day"
    s = m.sun.set.astimezone(m.tz)
    assert s.hour == 18 and 10 <= s.minute <= 30
    r = m.sun.rise.astimezone(m.tz)
    assert r.hour == 7
    assert m.sun.next_rise > t
    assert 0.0 <= m.moon.fraction <= 1.0
    assert 0.0 <= m.moon.phase_deg < 360.0


def test_ecliptic_points_cover_sky():
    pts = astro.ecliptic_radec(step_deg=10)
    assert pts.shape == (36, 2)
    assert abs(pts[:, 1]).max() == pytest.approx(23.44, abs=0.1)     # max deklinace = sklon ekliptiky
    assert pts[0, 0] == pytest.approx(0.0) and pts[0, 1] == pytest.approx(0.0)


@ephem
def test_outer_planets_mode_force_and_ecliptic():
    e = astro.get_ephemeris(CACHE)
    p = parse(dict(PLZEN, mode="night"), config.load({}), "png")
    t = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    m = astro.compute(p, e, load_catalog(), "cs", t)
    assert m.mode == "night" and m.sun.alt > 0                 # vynuceno, Slunce je přitom nad obzorem
    assert [b.name for b in m.planets] == ["Merkur", "Venuše", "Mars", "Jupiter", "Saturn", "Uran", "Neptun"]
    assert m.ecliptic.shape[1] == 2 and len(m.ecliptic) >= 72
