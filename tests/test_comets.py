from datetime import datetime, timezone
from pathlib import Path

import pytest

from sky import astro, comets

CACHE = Path("cache")
ephem = pytest.mark.skipif(not (CACHE / "de421.bsp").exists(), reason="de421.bsp missing")
TEXT = Path("tests/data/comets_sample.txt").read_text(encoding="utf-8")


def test_parse_elements_fixed_columns():
    els = comets.parse_elements(TEXT)
    names = [c.name for c in els]
    assert "C/1995 O1 (Hale-Bopp)" in names and "161P/Hartley-IRAS" in names
    assert "garbage" not in " ".join(names)
    hb = next(c for c in els if "Hale-Bopp" in c.name)
    assert hb.perihelion_year == 1997 and hb.perihelion_month == 3 and abs(hb.perihelion_day - 29.0289) < 1e-4
    assert abs(hb.perihelion_distance_au - 0.925868) < 1e-6 and abs(hb.eccentricity - 0.994895) < 1e-6
    assert abs(hb.argument_of_perihelion_degrees - 130.7303) < 1e-4
    assert abs(hb.longitude_of_ascending_node_degrees - 281.8089) < 1e-4
    assert abs(hb.inclination_degrees - 89.7339) < 1e-4
    assert hb.h == -2.0 and hb.g == 4.0
    assert hb["designation"] == hb.name          # Skyfield čte označení přes []
    assert comets.parse_elements("") == []


def test_short_name():
    assert comets.short_name("C/1995 O1 (Hale-Bopp)") == "Hale-Bopp"
    assert comets.short_name("P/2026 R2 (Leonard)") == "Leonard"
    assert comets.short_name("161P/Hartley-IRAS") == "161P/Hartley-IRAS"
    assert comets.short_name("12P/Pons-Brooks") == "12P/Pons-Brooks"
    assert comets.short_name("C/2025 A6") == "C/2025 A6"


def test_magnitude_formula():
    assert comets.magnitude(-2.0, 4.0, 1.0, 1.0) == pytest.approx(-2.0)
    assert comets.magnitude(-2.0, 4.0, 2.0, 1.0) == pytest.approx(-2.0 + 5 * 0.30103, abs=1e-3)
    assert comets.magnitude(10.0, 4.0, 1.0, 2.0) == pytest.approx(10.0 + 10 * 0.30103, abs=1e-3)


@ephem
def test_compute_positions_and_limit():
    eph = astro.get_ephemeris(CACHE)
    t = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)
    els = comets.parse_elements(TEXT)
    found = comets.compute(els, eph, 49.747, 13.378, t, limit=20.0)
    assert found and all(-90 <= c.alt <= 90 and 0 <= c.az < 360 for c in found)
    assert [c.mag for c in found] == sorted(c.mag for c in found)
    hartley = next(c for c in found if c.name == "161P/Hartley-IRAS")
    assert 8.0 < hartley.mag < 11.5
    assert comets.compute(els, eph, 49.747, 13.378, t, limit=-5.0) == []
    assert all(c.mag <= 10.0 for c in comets.compute(els, eph, 49.747, 13.378, t, limit=10.0))


@ephem
def test_hale_bopp_1997_matches_history():
    # 1. 4. 1997 (perihel): Hale-Bopp v Andromedě/Perseu, RA ~2 h, Dec ~+43°, jasnost kolem −1 mag
    eph = astro.get_ephemeris(CACHE)
    hb = next(c for c in comets.parse_elements(TEXT) if "Hale-Bopp" in c.name)
    tt = eph.ts.from_datetime(datetime(1997, 4, 1, tzinfo=timezone.utc))
    orbit = eph.eph["sun"] + comets.comet_orbit(hb, eph.ts)
    ra, dec, dist = eph.eph["earth"].at(tt).observe(orbit).radec()
    assert 1.8 < ra.hours < 2.4 and 41 < dec.degrees < 45
    found = comets.compute([hb], eph, 49.747, 13.378, datetime(1997, 4, 1, tzinfo=timezone.utc), limit=20.0)
    assert found[0].name == "Hale-Bopp" and -2.5 < found[0].mag < -1.0


def test_import_does_not_pull_pandas():
    # skyfield.data.mpc importuje pandas; v obrazu není a nechceme ho (desítky MB)
    import subprocess, sys
    code = "import sys, sky.comets; sys.exit(1 if 'pandas' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code], cwd=".").returncode == 0
