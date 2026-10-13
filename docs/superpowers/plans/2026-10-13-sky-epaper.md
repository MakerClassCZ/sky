# Sky e-paper service – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HTTP služba (a CLI), která z GPS souřadnic, směru a času vykreslí aktuální oblohu se souhvězdími, planetami, Sluncem, Měsícem a ISS plus infopanel (východy/západy, přelet ISS, úkazy z jantichy.cz) jako PNG/BMP v paletách BW/BWR/BWRY pro e-paper.

**Architecture:** Čisté moduly (`params`, `palette`, `projection`, `layout`, `fonts`, `icons`, `geo`, `catalog`, `events.parse`) bez IO, testované jednotkově. Výpočetní modul `astro` (Skyfield) a síťové moduly `iss`, `events`, `netcache` mají diskovou cache s politikou „stará cache lépe než nic“. `render` dostává hotové struktury a kreslí do Pillow obrazu v režimu `P`; `output` kóduje PNG/BMP; `service` skládá pipeline a cachuje výsledky; `app` (FastAPI) a `cli` jsou tenké obálky.

**Tech Stack:** Python 3.12+, Skyfield ≥ 1.49 (+ sgp4), numpy, Pillow ≥ 10, FastAPI + uvicorn, icalendar + recurring-ical-events, timezonefinder, pytest, httpx (TestClient).

**Spec:** `docs/superpowers/specs/2026-10-13-sky-epaper-design.md`

## Global Constraints

- Repo `sky/` je vlastní git repozitář, práce rovnou na `main`, commit po každém tasku. Commit message končí řádkem `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Pracovní adresář všech příkazů: kořen `sky/` (absolutní cesta `C:/Users/IngVladimírSmitka/Documents/prezident/zivy-obraz/sky`). Nikdy neřetězit `cd … && …`.
- Testy: `python -m pytest -q`. Testy označené `@pytest.mark.ephem` vyžadují `de421.bsp` v `SKY_CACHE_DIR` (výchozí `./cache`); stáhne se příkazem `python -m sky warmup`.
- Parametry a jejich rozsahy přesně dle specu §3.1: `lat` −90..90, `lon` −180..180, `view` sky|horizon, `az` 0..360 (výchozí 180), `fov` 30..180 (výchozí 120), `w`,`h` 64..2000 (výchozí 800×480), `colors` bw|bwr|bwry, `rot` 0|90|180|270, `t` ISO 8601, `iss`/`events` 0|1, `lang` cs|en, `token`.
- Paleta indexy: 0 bílá `#FFFFFF`, 1 černá `#000000`, 2 červená `#FF0000`, 3 žlutá `#FFFF00`. Režim `night` = Slunce níž než −0,833°.
- Texty na panelu česky s diakritikou (UTF-8), fonty Spleen (8×16, 12×24, 16×32) vlastním BDF parserem (Pillow `.pil` fonty umí jen 256 znaků).
- Žádné vyhlazování: čáry width 1, text bitmapový, výplně celé indexy.
- Env: `SKY_CACHE_DIR` (`./cache`), `SKY_LAT`, `SKY_LON`, `SKY_TOKEN`, `SKY_EVENTS_URL`, `SKY_TLE_URL`, `SKY_RENDER_CACHE_S` (`300`), `SKY_EVENT_TYPES` (`eye,scope,warn,moon`).
- Síťové volání: timeout 10 s, vždy přes `netcache.fetch_text`; render nikdy nesmí spadnout kvůli síti.

## Review Focus

1. **Souhvězdí přes hranici azimutu ±180° u `horizon`** – segment, jehož body leží po obou stranách protilehlého azimutu, se nesmí nakreslit přes celou šířku; test v Task 4 (`test_horizon_segment_across_back_is_dropped`).
2. **Segment souhvězdí s jedním bodem hluboko pod obzorem u `sky`** – ořez na kružnici, ne čára ven z mapy; test v Task 4 (`test_clip_segment_circle_partial`).
3. **Měsíc bez východu nebo západu v daném dni** – řádek „–“, ne výjimka; test v Task 8 (`test_first_or_none_when_no_event`).
4. **Úkaz s `RECURRENCE-ID` (Tauridy) nesmí být zdvojený ani ztracený** – test v Task 9 (`test_recurrence_override_not_duplicated`).
5. **Příliš malý panel (např. 296×128)** – jen mapa, bez infopanelu, bez výjimky; test v Task 5 (`test_tiny_panel_has_no_info`) a Task 11 (`test_render_tiny_panel`).

---

## File Structure

```
sky/
  pyproject.toml, .gitignore, README.md, Dockerfile
  sky/
    __init__.py, __main__.py
    config.py      # Config z env
    params.py      # Params + parse()
    palette.py     # Palette + make_palette()
    projection.py  # SkyProjection, HorizonProjection, clip_segment_circle/rect
    layout.py      # Rect, Zones, compute()
    fonts.py       # BdfFont, load_font(), draw_text(), fit()
    icons.py       # ICONS, draw_icon()
    geo.py         # tz_for(), fmt_date(), fmt_time(), compass(), tr()
    catalog.py     # Catalog, load_catalog()
    netcache.py    # fetch_text()
    astro.py       # Ephemeris, SkyModel, compute()
    iss.py         # IssInfo, Pass, load_tle(), info()
    events.py      # Event, parse_events(), upcoming()
    render.py      # render()
    output.py      # encode()
    service.py     # build(): pipeline + cache
    app.py         # FastAPI
    cli.py         # render / serve / warmup
    data/  (d3-celestial JSON + LICENSE), fonts/ (Spleen BDF + LICENSE)
  tests/
    test_params.py test_palette.py test_projection.py test_layout.py test_fonts.py
    test_geo.py test_catalog.py test_astro.py test_iss.py test_events.py
    test_render.py test_output.py test_app.py
    data/events_sample.ics, data/iss.tle
```

---

### Task 0: Skeleton projektu, data, fonty

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `sky/__init__.py`, `sky/__main__.py`, `sky/config.py`, `tests/__init__.py`, `tests/test_config.py`
- Already present: `sky/data/*.json`, `sky/data/LICENSE-d3-celestial`, `sky/fonts/*.bdf`, `sky/fonts/LICENSE`

**Interfaces:**
- Produces: `config.Config` (dataclass: `cache_dir: Path, lat: float|None, lon: float|None, token: str|None, events_url: str, tle_url: str, render_cache_s: int, event_types: tuple[str,...]`), `config.load(env=None) -> Config`.

- [ ] **Step 1: pyproject.toml**

```toml
[project]
name = "sky-epaper"
version = "0.1.0"
description = "Aktuální obloha pro e-paper displeje (Živý obraz, Paperboard)"
requires-python = ">=3.12"
dependencies = [
  "skyfield>=1.49",
  "numpy>=1.26",
  "Pillow>=10.0",
  "fastapi>=0.110",
  "uvicorn>=0.29",
  "icalendar>=5.0",
  "recurring-ical-events>=2.1",
  "timezonefinder>=6.5",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["sky*"]

[tool.setuptools.package-data]
sky = ["data/*", "fonts/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["ephem: needs de421.bsp in SKY_CACHE_DIR"]
```

- [ ] **Step 2: .gitignore**

```
cache/
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.pytest_cache/
out/
```

- [ ] **Step 3: Failing test for config**

`tests/test_config.py`:
```python
from pathlib import Path
from sky import config


def test_defaults():
    c = config.load({})
    assert c.cache_dir == Path("cache")
    assert c.lat is None and c.lon is None
    assert c.token is None
    assert c.render_cache_s == 300
    assert c.event_types == ("eye", "scope", "warn", "moon")
    assert "calendar.google.com" in c.events_url
    assert "25544" in c.tle_url


def test_env_override():
    c = config.load({"SKY_CACHE_DIR": "/c", "SKY_LAT": "49.7", "SKY_LON": "13.4",
                     "SKY_TOKEN": "x", "SKY_RENDER_CACHE_S": "10",
                     "SKY_EVENT_TYPES": "eye, moon"})
    assert c.cache_dir == Path("/c")
    assert c.lat == 49.7 and c.lon == 13.4
    assert c.token == "x"
    assert c.render_cache_s == 10
    assert c.event_types == ("eye", "moon")
```

- [ ] **Step 4: Run, expect ImportError**

Run: `python -m pytest -q tests/test_config.py`

- [ ] **Step 5: Implement**

`sky/__init__.py`: `"""Sky – aktuální obloha pro e-paper."""` + `__version__ = "0.1.0"`.

`sky/__main__.py`:
```python
from sky.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

`sky/config.py`:
```python
"""Konfigurace z proměnných prostředí (spec §3.3)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_EVENTS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "c_f45884b2c6eaf4644407e4587ff09bc7205bb9b47cb965f5566c02083578eecb"
    "%40group.calendar.google.com/public/basic.ics"
)
DEFAULT_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle"


@dataclass(frozen=True)
class Config:
    cache_dir: Path
    lat: float | None
    lon: float | None
    token: str | None
    events_url: str
    tle_url: str
    render_cache_s: int
    event_types: tuple[str, ...]


def _float_or_none(v: str | None) -> float | None:
    return None if v in (None, "") else float(v)


def load(env: Mapping[str, str] | None = None) -> Config:
    e = os.environ if env is None else env
    types = tuple(s.strip() for s in e.get("SKY_EVENT_TYPES", "eye,scope,warn,moon").split(",") if s.strip())
    return Config(
        cache_dir=Path(e.get("SKY_CACHE_DIR", "cache")),
        lat=_float_or_none(e.get("SKY_LAT")),
        lon=_float_or_none(e.get("SKY_LON")),
        token=e.get("SKY_TOKEN") or None,
        events_url=e.get("SKY_EVENTS_URL", DEFAULT_EVENTS_URL),
        tle_url=e.get("SKY_TLE_URL", DEFAULT_TLE_URL),
        render_cache_s=int(e.get("SKY_RENDER_CACHE_S", "300")),
        event_types=types,
    )
```

- [ ] **Step 6: Run tests, expect PASS; commit**

```bash
git add -A
git commit -m "chore: project skeleton, d3-celestial data, Spleen fonts, config"
```

---

### Task 1: Parametry (`params.py`)

**Files:** Create `sky/params.py`, `tests/test_params.py`

**Interfaces:**
- Produces: `Params` (frozen dataclass: `lat, lon: float; view: str; az: float; fov: float; w, h: int; colors: str; rot: int; t: datetime|None (aware UTC); iss, events: bool; lang: str; fmt: str`), `parse(q: Mapping[str,str], cfg: Config, fmt: str) -> Params`, `ParamError(ValueError)`, `parse_time(raw) -> datetime`.

- [ ] **Step 1: Failing tests**

```python
from datetime import datetime, timezone
import pytest
from sky import config
from sky.params import Params, ParamError, parse, parse_time

CFG = config.load({})
CFG_LOC = config.load({"SKY_LAT": "49.747", "SKY_LON": "13.378"})


def test_defaults():
    p = parse({"lat": "49.747", "lon": "13.378"}, CFG, "png")
    assert p == Params(lat=49.747, lon=13.378)
    assert p.view == "sky" and p.az == 180.0 and p.fov == 120.0
    assert (p.w, p.h) == (800, 480) and p.colors == "bw" and p.rot == 0
    assert p.t is None and p.iss and p.events and p.lang == "cs" and p.fmt == "png"


def test_env_location_fallback():
    p = parse({}, CFG_LOC, "bmp")
    assert (p.lat, p.lon, p.fmt) == (49.747, 13.378, "bmp")


def test_missing_location():
    with pytest.raises(ParamError):
        parse({}, CFG, "png")


@pytest.mark.parametrize("q", [
    {"lat": "91"}, {"lon": "x"}, {"view": "dome"}, {"az": "361"}, {"fov": "20"},
    {"w": "10"}, {"h": "3000"}, {"colors": "rgb"}, {"rot": "45"}, {"iss": "yes"},
    {"lang": "de"}, {"t": "včera"},
])
def test_invalid(q):
    with pytest.raises(ParamError):
        parse(q, CFG_LOC, "png")


def test_invalid_format():
    with pytest.raises(ParamError):
        parse({}, CFG_LOC, "gif")


def test_full():
    p = parse({"view": "horizon", "az": "200", "fov": "90", "w": "480", "h": "800",
               "colors": "bwry", "rot": "90", "t": "2026-10-13T22:00+02:00",
               "iss": "0", "events": "0", "lang": "en"}, CFG_LOC, "png")
    assert p.view == "horizon" and p.az == 200 and p.fov == 90
    assert (p.w, p.h, p.colors, p.rot) == (480, 800, "bwry", 90)
    assert p.t == datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
    assert not p.iss and not p.events and p.lang == "en"


def test_parse_time_naive_is_utc():
    assert parse_time("2026-01-01T00:00") == datetime(2026, 1, 1, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run, expect failure. Step 3: Implement**

```python
"""Parametry požadavku (spec §3.1), společné pro HTTP i CLI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from sky.config import Config

VIEWS = ("sky", "horizon")
COLORS = ("bw", "bwr", "bwry")
ROTS = (0, 90, 180, 270)
LANGS = ("cs", "en")
FORMATS = ("png", "bmp")


class ParamError(ValueError):
    """Nevalidní parametr; text je určen uživateli (HTTP 400)."""


@dataclass(frozen=True)
class Params:
    lat: float
    lon: float
    view: str = "sky"
    az: float = 180.0
    fov: float = 120.0
    w: int = 800
    h: int = 480
    colors: str = "bw"
    rot: int = 0
    t: datetime | None = None
    iss: bool = True
    events: bool = True
    lang: str = "cs"
    fmt: str = "png"


def _num(q, key, default, lo, hi, cast):
    raw = q.get(key)
    if raw is None or raw == "":
        if default is None:
            raise ParamError(f"chybí parametr {key}")
        return default
    try:
        v = cast(raw)
    except ValueError:
        raise ParamError(f"{key}: není číslo") from None
    if not (lo <= v <= hi):
        raise ParamError(f"{key}: mimo rozsah {lo}..{hi}")
    return v


def _choice(q, key, default, allowed, cast=str):
    raw = q.get(key)
    if raw is None or raw == "":
        return default
    try:
        v = cast(raw)
    except ValueError:
        v = raw
    if v not in allowed:
        raise ParamError(f"{key}: povolené hodnoty {', '.join(map(str, allowed))}")
    return v


def _flag(q, key, default):
    raw = q.get(key)
    if raw is None or raw == "":
        return default
    if raw not in ("0", "1"):
        raise ParamError(f"{key}: povolené hodnoty 0, 1")
    return raw == "1"


def parse_time(raw: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise ParamError("t: očekáván čas ISO 8601, např. 2026-10-13T22:00+02:00") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse(q: Mapping[str, str], cfg: Config, fmt: str = "png") -> Params:
    if fmt not in FORMATS:
        raise ParamError(f"formát: povolené png, bmp")
    t_raw = q.get("t")
    return Params(
        lat=_num(q, "lat", cfg.lat, -90.0, 90.0, float),
        lon=_num(q, "lon", cfg.lon, -180.0, 180.0, float),
        view=_choice(q, "view", "sky", VIEWS),
        az=_num(q, "az", 180.0, 0.0, 360.0, float),
        fov=_num(q, "fov", 120.0, 30.0, 180.0, float),
        w=_num(q, "w", 800, 64, 2000, int),
        h=_num(q, "h", 480, 64, 2000, int),
        colors=_choice(q, "colors", "bw", COLORS),
        rot=_choice(q, "rot", 0, ROTS, int),
        t=parse_time(t_raw) if t_raw else None,
        iss=_flag(q, "iss", True),
        events=_flag(q, "events", True),
        lang=_choice(q, "lang", "cs", LANGS),
        fmt=fmt,
    )
```

- [ ] **Step 4: Tests pass; commit** `feat(params): request parameters with validation`

---

### Task 2: Paleta (`palette.py`)

**Files:** Create `sky/palette.py`, `tests/test_palette.py`

**Interfaces:**
- Produces: `ROLES`, `RGB`, `Palette(colors, mode, index)` with `__getitem__(role) -> int`, `ncolors`, `flat() -> list[int]`; `make_palette(colors: str, mode: str) -> Palette`.

- [ ] **Step 1: Failing tests**

```python
import pytest
from sky.palette import ROLES, make_palette


def test_bw_night_inverts():
    p = make_palette("bw", "night")
    assert p["bg"] == 1 and p["fg"] == 0 and p["star"] == 0 and p["planet"] == 0
    assert p["moon_dark"] == 1
    assert p.ncolors == 2 and p.flat() == [255, 255, 255, 0, 0, 0]


def test_bw_day():
    p = make_palette("bw", "day")
    assert p["bg"] == 0 and p["fg"] == 1 and p["label"] == 1


def test_bwr_roles():
    p = make_palette("bwr", "night")
    assert p["planet"] == 2 and p["sun"] == 2 and p["iss"] == 2 and p["today"] == 2
    assert p["moon_lit"] == 0 and p.ncolors == 3


def test_bwry_roles():
    p = make_palette("bwry", "day")
    assert p["sun"] == 3 and p["moon_lit"] == 3 and p["planet"] == 2
    assert p.ncolors == 4 and len(p.flat()) == 12


def test_all_roles_defined():
    p = make_palette("bwry", "night")
    for r in ROLES:
        assert isinstance(p[r], int)
```

- [ ] **Step 2–3: Implement**

```python
"""Role barev → indexy palety (spec §7)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

RGB = [(255, 255, 255), (0, 0, 0), (255, 0, 0), (255, 255, 0)]
NCOLORS = {"bw": 2, "bwr": 3, "bwry": 4}
ROLES = ("bg", "fg", "star", "line", "label", "planet", "sun",
         "moon_lit", "moon_dark", "iss", "today", "horizon")


@dataclass(frozen=True)
class Palette:
    colors: str
    mode: str
    index: Mapping[str, int]

    def __getitem__(self, role: str) -> int:
        return self.index[role]

    @property
    def ncolors(self) -> int:
        return NCOLORS[self.colors]

    def flat(self) -> list[int]:
        return [c for rgb in RGB[: self.ncolors] for c in rgb]


def make_palette(colors: str, mode: str) -> Palette:
    bg, fg = (1, 0) if mode == "night" else (0, 1)
    idx = {r: fg for r in ROLES}
    idx["bg"] = bg
    idx["moon_dark"] = bg
    if colors in ("bwr", "bwry"):
        for r in ("planet", "sun", "iss", "today"):
            idx[r] = 2
    if colors == "bwry":
        idx["sun"] = 3
        idx["moon_lit"] = 3
    return Palette(colors, mode, idx)
```

- [ ] **Step 4: Tests pass; commit** `feat(palette): BW/BWR/BWRY role palettes`

---

### Task 3: Projekce (`projection.py`)

**Files:** Create `sky/projection.py`, `tests/test_projection.py`

**Interfaces:**
- Produces: `normalize_daz(d) -> float` (−180..180), `SkyProjection(size:int, az_down:float, margin:int=18)` with `.center -> (cx,cy)`, `.radius`, `.project(alt, az) -> (x,y)`, `.inside(x,y) -> bool`; `HorizonProjection(width:int, height:int, az_center:float, fov:float)` with `.alt_max`, `.project(alt, az)`, `.visible(alt, az) -> bool`; `clip_segment_circle(p0, p1, center, r) -> tuple[p,p]|None`; `clip_segment_rect(p0, p1, w, h) -> tuple[p,p]|None`.

- [ ] **Step 1: Failing tests**

```python
import math
import pytest
from sky.projection import (HorizonProjection, SkyProjection, clip_segment_circle,
                            clip_segment_rect, normalize_daz)


def test_normalize_daz():
    assert normalize_daz(190) == -170
    assert normalize_daz(-190) == 170
    assert normalize_daz(45) == 45


def test_sky_zenith_center():
    p = SkyProjection(480, 180)
    assert p.project(90, 123) == pytest.approx((240, 240))
    assert p.radius == 240 - 18


def test_sky_az_down_is_bottom_east_left():
    p = SkyProjection(480, 180)
    x, y = p.project(0, 180)
    assert (x, y) == pytest.approx((240, 240 + p.radius))
    x, y = p.project(0, 90)           # východ při pohledu na jih vlevo
    assert (x, y) == pytest.approx((240 - p.radius, 240))
    x, y = p.project(0, 0)
    assert (x, y) == pytest.approx((240, 240 - p.radius))


def test_sky_inside():
    p = SkyProjection(480, 0)
    assert p.inside(240, 240)
    assert not p.inside(0, 0)


def test_horizon_center_and_scale():
    p = HorizonProjection(800, 300, 180, 120)
    assert p.alt_max == pytest.approx(45)
    assert p.project(0, 180) == pytest.approx((400, 300))
    assert p.project(45, 180) == pytest.approx((400, 0))
    assert p.project(0, 120) == pytest.approx((0, 300))
    assert p.visible(10, 200) and not p.visible(50, 180) and not p.visible(10, 10)


def test_horizon_wraps_azimuth():
    p = HorizonProjection(800, 300, 10, 120)
    x, _ = p.project(0, 350)
    assert x == pytest.approx(400 - 20 / 120 * 800)


def test_horizon_segment_across_back_is_dropped():
    # body na az 100 a 260 vůči středu 180 jsou oba mimo pole a leží „za zády“
    p = HorizonProjection(800, 300, 180, 120)
    assert clip_segment_rect(p.project(10, 100), p.project(10, 260), 800, 300) is None


def test_clip_segment_circle_partial():
    c, r = (100, 100), 50
    seg = clip_segment_circle((100, 100), (300, 100), c, r)
    assert seg is not None
    (x0, y0), (x1, y1) = seg
    assert (x0, y0) == pytest.approx((100, 100))
    assert (x1, y1) == pytest.approx((150, 100))


def test_clip_segment_circle_outside():
    assert clip_segment_circle((200, 200), (300, 300), (0, 0), 10) is None


def test_clip_segment_circle_inside_untouched():
    seg = clip_segment_circle((10, 10), (20, 20), (0, 0), 100)
    assert seg == ((10, 10), (20, 20))


def test_clip_segment_rect():
    seg = clip_segment_rect((-10, 50), (50, 50), 100, 100)
    assert seg is not None and seg[0] == pytest.approx((0, 50))
    assert clip_segment_rect((-10, -10), (-5, -5), 100, 100) is None
```

- [ ] **Step 2–3: Implement**

```python
"""Projekce alt/az → pixely a ořez úseček (spec §5.2, §5.3)."""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]


def normalize_daz(d: float) -> float:
    return ((d + 180.0) % 360.0) - 180.0


@dataclass(frozen=True)
class SkyProjection:
    """Azimutální ekvidistantní, zenit uprostřed, `az_down` dole, východ vlevo."""
    size: int
    az_down: float
    margin: int = 18

    @property
    def center(self) -> Point:
        return (self.size / 2.0, self.size / 2.0)

    @property
    def radius(self) -> float:
        return self.size / 2.0 - self.margin

    def project(self, alt: float, az: float) -> Point:
        cx, cy = self.center
        r = (90.0 - alt) / 90.0 * self.radius
        th = math.radians(az - self.az_down)
        return (cx + r * math.sin(th), cy + r * math.cos(th))

    def inside(self, x: float, y: float) -> bool:
        cx, cy = self.center
        return (x - cx) ** 2 + (y - cy) ** 2 <= self.radius ** 2 + 1e-6


@dataclass(frozen=True)
class HorizonProjection:
    """Rovnoběžná azimut × výška: obzor dole, `az_center` uprostřed."""
    width: int
    height: int
    az_center: float
    fov: float

    @property
    def alt_max(self) -> float:
        return self.fov * self.height / self.width

    def project(self, alt: float, az: float) -> Point:
        daz = normalize_daz(az - self.az_center)
        x = (daz / self.fov + 0.5) * self.width
        y = self.height - alt / self.alt_max * self.height
        return (x, y)

    def visible(self, alt: float, az: float) -> bool:
        daz = normalize_daz(az - self.az_center)
        return 0.0 <= alt <= self.alt_max and abs(daz) <= self.fov / 2.0


def clip_segment_circle(p0: Point, p1: Point, center: Point, r: float):
    """Část úsečky uvnitř kruhu, nebo None."""
    cx, cy = center
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    fx, fy = p0[0] - cx, p0[1] - cy
    a = dx * dx + dy * dy
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    if a == 0.0:
        return (p0, p1) if c <= 0 else None
    disc = b * b - 4.0 * a * c
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    t0 = max(0.0, (-b - sq) / (2.0 * a))
    t1 = min(1.0, (-b + sq) / (2.0 * a))
    if t0 > t1:
        return None
    q0 = (p0[0] + dx * t0, p0[1] + dy * t0)
    q1 = (p0[0] + dx * t1, p0[1] + dy * t1)
    return (q0, q1)


def clip_segment_rect(p0: Point, p1: Point, w: float, h: float):
    """Liang–Barsky ořez na obdélník [0,w]×[0,h], nebo None."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, p0[0]), (dx, w - p0[0]), (-dy, p0[1]), (dy, h - p0[1])):
        if p == 0.0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return ((p0[0] + dx * t0, p0[1] + dy * t0), (p0[0] + dx * t1, p0[1] + dy * t1))
```

- [ ] **Step 4: Tests pass; commit** `feat(projection): sky and horizon projections with clipping`

---

### Task 4: Rozložení (`layout.py`)

**Files:** Create `sky/layout.py`, `tests/test_layout.py`

**Interfaces:**
- Produces: `U = 16`, `MARGIN = 8`, `Rect(x, y, w, h)` with `.right`, `.bottom`; `Zones(map: Rect, info: Rect|None, header: Rect|None, columns: tuple[Rect,...], header_big: bool)`; `compute(w: int, h: int, view: str) -> Zones`.

- [ ] **Step 1: Failing tests**

```python
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
    assert not z.header_big


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
```

- [ ] **Step 2–3: Implement**

```python
"""Rozložení panelu (spec §5.4)."""
from __future__ import annotations

from dataclasses import dataclass

U = 16          # výška řádku fontu 8×16
MARGIN = 8
MIN_INFO_W = 112    # 14 znaků 8 px
WIDE_COL_W = 160    # min. šířka sloupce při více sloupcích
WIDE3_COL_W = 200


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


@dataclass(frozen=True)
class Zones:
    map: Rect
    info: Rect | None
    header: Rect | None
    columns: tuple[Rect, ...]
    header_big: bool


def _split(info: Rect, header_big: bool) -> tuple[Rect, tuple[Rect, ...]]:
    hh = (32 if header_big else 16) + U + MARGIN
    header = Rect(info.x, info.y, info.w, hh)
    body = Rect(info.x, header.bottom, info.w, max(0, info.bottom - header.bottom))
    if body.w > body.h and body.w >= 3 * WIDE3_COL_W:
        n = 3
    elif body.w > body.h and body.w >= 2 * WIDE_COL_W:
        n = 2
    else:
        n = 1
    cw = body.w // n
    cols = tuple(Rect(body.x + i * cw, body.y, cw, body.h) for i in range(n))
    return header, cols


def compute(w: int, h: int, view: str) -> Zones:
    if view == "sky":
        if w >= h:
            m = Rect(0, 0, h, h)
            info = Rect(h, 0, w - h, h) if w - h >= MIN_INFO_W else None
        else:
            m = Rect(0, 0, w, w)
            info = Rect(0, w, w, h - w) if h - w >= 6 * U else None
    else:
        if w >= h:
            mh = max(int(h * 0.6), h - 12 * U)
        else:
            mh = int(w * 0.6)
        if h - mh >= 3 * U:
            m = Rect(0, 0, w, mh)
            info = Rect(0, mh, w, h - mh)
        else:
            m = Rect(0, 0, w, h)
            info = None
    if info is None:
        return Zones(m, None, None, (), False)
    big = info.h >= 128 and info.w >= 224
    header, cols = _split(info, big)
    return Zones(m, info, header, cols, big)
```

- [ ] **Step 4: Tests pass; commit** `feat(layout): zones for sky/horizon, landscape/portrait`

---

### Task 5: Fonty a ikony (`fonts.py`, `icons.py`)

**Files:** Create `sky/fonts.py`, `sky/icons.py`, `tests/test_fonts.py`

**Interfaces:**
- Produces: `BdfFont` (`width`, `height`, `glyph(cp) -> Image|None`), `load_font(name: str) -> BdfFont` (name `"8x16" | "12x24" | "16x32"`, cached), `text_width(font, text) -> int`, `fit(font, text, max_w) -> str`, `draw_text(img, xy, text, font, index) -> int` (returns width); `ICONS: dict[str, tuple[str,...]]` (16 řádků po 16 znacích `#`/`.`), `icon_mask(name) -> Image`, `draw_icon(img, xy, name, index)`.

- [ ] **Step 1: Failing tests**

```python
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


def test_icons_shape_and_draw():
    for name, rows in ICONS.items():
        assert len(rows) == 16 and all(len(r) == 16 for r in rows), name
    img = Image.new("P", (16, 16), 0)
    draw_icon(img, (0, 0), "sun", 1)
    assert img.getpixel((7, 7)) == 1
```

- [ ] **Step 2–3: Implement**

`sky/fonts.py`:
```python
"""Bitmapové fonty Spleen (BDF) – vlastní parser, Unicode bez omezení na 256 znaků."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

FONT_DIR = Path(__file__).parent / "fonts"
ELLIPSIS = "…"


class BdfFont:
    def __init__(self, width: int, height: int, xoff: int, yoff: int,
                 raw: dict[int, tuple[int, int, int, int, list[str]]]):
        self.width, self.height = width, height
        self._xoff, self._yoff = xoff, yoff
        self._raw = raw                      # cp → (bw, bh, bx, by, hexrows)
        self._cache: dict[int, Image.Image | None] = {}

    def glyph(self, cp: int) -> Image.Image | None:
        """Maska znaku v režimu '1' (255 = kreslit) o velikosti buňky, nebo None."""
        if cp in self._cache:
            return self._cache[cp]
        spec = self._raw.get(cp)
        if spec is None:
            self._cache[cp] = None
            return None
        bw, bh, bx, by, rows = spec
        cell = Image.new("1", (self.width, self.height), 0)
        if bw > 0 and bh > 0 and rows:
            nbytes = (bw + 7) // 8
            data = b"".join(bytes.fromhex(r.ljust(nbytes * 2, "0")[: nbytes * 2]) for r in rows)
            bmp = Image.frombytes("1", (bw, bh), data)
            ascent = self.height + self._yoff
            dx = bx - self._xoff
            dy = ascent - (by + bh)
            cell.paste(bmp, (dx, dy))
        self._cache[cp] = cell
        return cell


def parse_bdf(text: str) -> BdfFont:
    fw = fh = fx = fy = 0
    raw: dict[int, tuple[int, int, int, int, list[str]]] = {}
    enc = None
    bbx = (0, 0, 0, 0)
    rows: list[str] | None = None
    for line in text.splitlines():
        if rows is not None:
            if line == "ENDCHAR":
                if enc is not None and enc >= 0:
                    raw[enc] = (*bbx, rows)
                rows = None
                enc = None
            else:
                rows.append(line.strip())
            continue
        if line.startswith("FONTBOUNDINGBOX "):
            fw, fh, fx, fy = map(int, line.split()[1:5])
        elif line.startswith("ENCODING "):
            enc = int(line.split()[1])
        elif line.startswith("BBX "):
            bbx = tuple(map(int, line.split()[1:5]))  # type: ignore[assignment]
        elif line == "BITMAP":
            rows = []
    return BdfFont(fw, fh, fx, fy, raw)


@lru_cache(maxsize=None)
def load_font(name: str) -> BdfFont:
    path = FONT_DIR / f"spleen-{name}.bdf"
    return parse_bdf(path.read_text(encoding="utf-8", errors="replace"))


def text_width(font: BdfFont, text: str) -> int:
    return len(text) * font.width


def fit(font: BdfFont, text: str, max_w: int) -> str:
    n = max_w // font.width
    if len(text) <= n:
        return text
    if n <= 1:
        return ELLIPSIS[:n]
    return text[: n - 1] + ELLIPSIS


def draw_text(img: Image.Image, xy: tuple[int, int], text: str, font: BdfFont, index: int) -> int:
    x, y = int(xy[0]), int(xy[1])
    for ch in text:
        g = font.glyph(ord(ch)) or font.glyph(0x3F)
        if g is not None:
            img.paste(index, (x, y, x + font.width, y + font.height), mask=g)
        x += font.width
    return len(text) * font.width
```

`sky/icons.py` – ikony 16×16 (`#` = pixel):
```python
"""Pixelové ikony 16×16 pro infopanel."""
from __future__ import annotations

from functools import lru_cache

from PIL import Image

ICONS: dict[str, tuple[str, ...]] = {
    "sun": (
        ".......##.......",
        ".......##.......",
        "..#....##....#..",
        "...#...##...#...",
        "....#......#....",
        ".....######.....",
        "....########....",
        "##.##########.##",
        "##.##########.##",
        "....########....",
        ".....######.....",
        "....#......#....",
        "...#...##...#...",
        "..#....##....#..",
        ".......##.......",
        ".......##.......",
    ),
    "moon": (
        ".....######.....",
        "...####...##....",
        "..###......##...",
        ".###........#...",
        ".###............",
        "###.............",
        "###.............",
        "###.............",
        "###.............",
        "###.............",
        ".###............",
        ".###........#...",
        "..###......##...",
        "...####...##....",
        ".....######.....",
        "................",
    ),
    "iss": (
        "##...........##.",
        "##...........##.",
        "##...........##.",
        "##...........##.",
        "##....###....##.",
        "##...#####...##.",
        "#######.#######.",
        "##...#####...##.",
        "##....###....##.",
        "##...........##.",
        "##...........##.",
        "##...........##.",
        "##...........##.",
        ".......#........",
        "......###.......",
        ".......#........",
    ),
    "eye": (
        "................",
        "................",
        "................",
        ".....######.....",
        "...##......##...",
        "..#....##....#..",
        ".#....####....#.",
        "#....######....#",
        "#....######....#",
        ".#....####....#.",
        "..#....##....#..",
        "...##......##...",
        ".....######.....",
        "................",
        "................",
        "................",
    ),
    "scope": (
        "..............##",
        ".............###",
        "...........###..",
        ".........###....",
        ".......###......",
        ".....####.......",
        "...#####........",
        "..#####.........",
        ".#####..........",
        ".####...........",
        "..##............",
        "...#.#..........",
        "....###.........",
        "...#.#.#........",
        "..#..#..#.......",
        ".#...#...#......",
    ),
    "warn": (
        ".......##.......",
        ".......##.......",
        "......####......",
        "......####......",
        ".....##..##.....",
        ".....##..##.....",
        "....##.##.##....",
        "....##.##.##....",
        "...##..##..##...",
        "...##..##..##...",
        "..##........##..",
        "..##....##..##..",
        ".##.....##...##.",
        ".##############.",
        "################",
        "................",
    ),
    "cal": (
        "................",
        "...#........#...",
        "################",
        "#..............#",
        "################",
        "#..............#",
        "#.##.##.##.##..#",
        "#..............#",
        "#.##.##.##.##..#",
        "#..............#",
        "#.##.##.##.....#",
        "#..............#",
        "#..............#",
        "################",
        "................",
        "................",
    ),
}


@lru_cache(maxsize=None)
def icon_mask(name: str) -> Image.Image:
    rows = ICONS[name]
    img = Image.new("1", (16, 16), 0)
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                px[x, y] = 255
    return img


def draw_icon(img: Image.Image, xy: tuple[int, int], name: str, index: int) -> None:
    x, y = int(xy[0]), int(xy[1])
    img.paste(index, (x, y, x + 16, y + 16), mask=icon_mask(name))
```

- [ ] **Step 4: Tests pass; commit** `feat(fonts,icons): Spleen BDF renderer and pixel icons`

---

### Task 6: Geo a texty (`geo.py`)

**Files:** Create `sky/geo.py`, `tests/test_geo.py`

**Interfaces:**
- Produces: `tz_for(lat, lon) -> ZoneInfo`, `fmt_date(d: date, lang) -> str` (`"út 13. 10."`), `fmt_time(dt: datetime|None, tz) -> str` (`"HH:MM"` / `"–"`), `compass(az, lang) -> str` (8 směrů), `tr(lang, key) -> str`, `fmt_coords(lat, lon) -> str` (`"49.75N 13.38E"`).

- [ ] **Step 1: Failing tests**

```python
from datetime import date, datetime, timezone
from sky.geo import compass, fmt_coords, fmt_date, fmt_time, tr, tz_for


def test_tz_plzen():
    assert tz_for(49.747, 13.378).key == "Europe/Prague"


def test_tz_ocean_fallback_utc():
    assert tz_for(0.0, -140.0).key in ("UTC", "Etc/GMT+9", "Etc/GMT+10")


def test_fmt_date():
    assert fmt_date(date(2026, 10, 13), "cs") == "út 13. 10."
    assert fmt_date(date(2026, 10, 13), "en") == "Tue 13 Oct"


def test_fmt_time():
    tz = tz_for(49.747, 13.378)
    assert fmt_time(datetime(2026, 10, 13, 16, 19, tzinfo=timezone.utc), tz) == "18:19"
    assert fmt_time(None, tz) == "–"


def test_compass():
    assert compass(0, "cs") == "S" and compass(44, "cs") == "SV" and compass(181, "cs") == "J"
    assert compass(350, "en") == "N" and compass(225, "en") == "SW"


def test_tr_and_coords():
    assert tr("cs", "sun") == "Slunce" and tr("en", "sun") == "Sun"
    assert fmt_coords(49.747, 13.378) == "49.75N 13.38E"
    assert fmt_coords(-33.9, -70.6) == "33.90S 70.60W"
```

- [ ] **Step 2–3: Implement**

```python
"""Časová zóna, formátování a texty (cs/en)."""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

DAYS = {"cs": ["po", "út", "st", "čt", "pá", "so", "ne"],
        "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COMPASS = {"cs": ["S", "SV", "V", "JV", "J", "JZ", "Z", "SZ"],
           "en": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]}
TEXTS = {
    "cs": {"sun": "Slunce", "moon": "Měsíc", "iss": "ISS", "events": "Úkazy",
           "rise": "Východ", "set": "Západ", "night_from": "Noc od", "dawn_at": "Svítá v",
           "phase": "Fáze", "waxing": "dorůstá", "waning": "couvá",
           "no_pass": "žádný do 48 h", "unavailable": "nedostupné", "max": "max",
           "none": "nic do 60 dnů", "data_from": "Zdroj: jantichy.cz/ukazy"},
    "en": {"sun": "Sun", "moon": "Moon", "iss": "ISS", "events": "Events",
           "rise": "Rise", "set": "Set", "night_from": "Night from", "dawn_at": "Dawn at",
           "phase": "Phase", "waxing": "waxing", "waning": "waning",
           "no_pass": "none in 48 h", "unavailable": "unavailable", "max": "max",
           "none": "none in 60 days", "data_from": "Source: jantichy.cz/ukazy"},
}


@lru_cache(maxsize=None)
def _finder():
    from timezonefinder import TimezoneFinder
    return TimezoneFinder()


def tz_for(lat: float, lon: float) -> ZoneInfo:
    name = _finder().timezone_at(lat=lat, lng=lon)
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def fmt_date(d: date, lang: str) -> str:
    day = DAYS[lang][d.weekday()]
    if lang == "en":
        return f"{day} {d.day} {MONTHS_EN[d.month - 1]}"
    return f"{day} {d.day}. {d.month}."


def fmt_time(dt: datetime | None, tz: ZoneInfo) -> str:
    if dt is None:
        return "–"
    return dt.astimezone(tz).strftime("%H:%M")


def compass(az: float, lang: str) -> str:
    return COMPASS[lang][int(((az % 360) + 22.5) // 45) % 8]


def tr(lang: str, key: str) -> str:
    return TEXTS[lang][key]


def fmt_coords(lat: float, lon: float) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.2f}{ns} {abs(lon):.2f}{ew}"
```

- [ ] **Step 4: Tests pass; commit** `feat(geo): timezone lookup, date/time formatting, cs/en texts`

---

### Task 7: Katalog hvězd a souhvězdí (`catalog.py`)

**Files:** Create `sky/catalog.py`, `tests/test_catalog.py`

**Interfaces:**
- Produces: `Catalog(ra_hours: np.ndarray, dec_deg: np.ndarray, mag: np.ndarray, lines: list[tuple[str, list[np.ndarray]]]` (každý ndarray tvaru (n,2) = ra_hours, dec), `names: dict[str, ConstName]`), `ConstName(id, cs, en, rank, ra_hours, dec)`, `lon_to_ra_hours(lon) -> float`, `load_catalog(mag_limit=4.5) -> Catalog` (cached).

- [ ] **Step 1: Failing tests**

```python
import numpy as np
from sky.catalog import load_catalog, lon_to_ra_hours


def test_lon_to_ra():
    assert lon_to_ra_hours(0) == 0
    assert lon_to_ra_hours(180) == 12
    assert lon_to_ra_hours(-90) == 18


def test_catalog_loaded():
    c = load_catalog()
    assert 300 < len(c.mag) < 1200
    assert c.mag.max() <= 4.5
    assert len(c.lines) == 88
    assert c.ra_hours.min() >= 0 and c.ra_hours.max() < 24
    uma = c.names["UMa"]
    assert uma.cs == "Velká medvědice" and uma.en == "Great Bear" and uma.rank == 1
    assert 8 < uma.ra_hours < 14
    assert all(seg.shape[1] == 2 for _, segs in c.lines for seg in segs)
```

- [ ] **Step 2–3: Implement**

```python
"""Hvězdy a souhvězdí z dat d3-celestial (BSD-3), převod lon → RA."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"


def lon_to_ra_hours(lon: float) -> float:
    return (lon % 360.0) / 15.0


@dataclass(frozen=True)
class ConstName:
    id: str
    cs: str
    en: str
    rank: int
    ra_hours: float
    dec: float

    def label(self, lang: str) -> str:
        return self.cs if lang == "cs" else self.en


@dataclass(frozen=True)
class Catalog:
    ra_hours: np.ndarray
    dec_deg: np.ndarray
    mag: np.ndarray
    lines: list[tuple[str, list[np.ndarray]]]
    names: dict[str, ConstName]


@lru_cache(maxsize=None)
def load_catalog(mag_limit: float = 4.5) -> Catalog:
    stars = json.loads((DATA_DIR / "stars.6.json").read_text(encoding="utf-8"))
    ra, dec, mag = [], [], []
    for f in stars["features"]:
        m = float(f["properties"]["mag"])
        if m <= mag_limit:
            lon, lat = f["geometry"]["coordinates"]
            ra.append(lon_to_ra_hours(lon))
            dec.append(lat)
            mag.append(m)

    lines_json = json.loads((DATA_DIR / "constellations.lines.json").read_text(encoding="utf-8"))
    lines = []
    for f in lines_json["features"]:
        segs = [np.array([[lon_to_ra_hours(x), y] for x, y in part], dtype=float)
                for part in f["geometry"]["coordinates"] if len(part) >= 2]
        lines.append((f["id"], segs))

    names_json = json.loads((DATA_DIR / "constellations.json").read_text(encoding="utf-8"))
    names = {}
    for f in names_json["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        names[f["id"]] = ConstName(f["id"], p.get("cz") or p["name"], p.get("en") or p["name"],
                                   int(p.get("rank", "3")), lon_to_ra_hours(lon), lat)
    return Catalog(np.array(ra), np.array(dec), np.array(mag), lines, names)
```

- [ ] **Step 4: Tests pass; commit** `feat(catalog): load d3-celestial stars and constellation lines`

---

### Task 8: Astronomie (`astro.py`) + `netcache.py`

**Files:** Create `sky/netcache.py`, `sky/astro.py`, `tests/test_netcache.py`, `tests/test_astro.py`

**Interfaces:**
- `netcache.fetch_text(url: str, path: Path, max_age_s: int, timeout: float = 10.0) -> str|None` – vrátí čerstvou cache, jinak stáhne a uloží, při chybě vrátí starou cache, jinak None.
- `astro.Ephemeris(cache_dir: Path)` s `.eph`, `.ts`, `.available: bool`; `astro.get_ephemeris(cache_dir) -> Ephemeris` (cached per dir); `astro.ensure_ephemeris(cache_dir) -> Path` (stáhne de421).
- Datové třídy: `Body(key: str, name: str, alt: float, az: float)`, `SunInfo(alt, az, rise, set, next_rise, next_set)` (datetimes aware nebo None), `MoonInfo(alt, az, phase_deg: float, fraction: float, rise, set)`, `SkyModel(t: datetime, tz: ZoneInfo, lat, lon, mode: str, stars: np.ndarray (n,3) [alt, az, mag], lines: list[tuple[str, list[np.ndarray]]] (n,2) [alt, az], labels: list[tuple[str, float, float]], planets: list[Body], sun: SunInfo, moon: MoonInfo)`.
- `astro.compute(params: Params, eph: Ephemeris, catalog: Catalog, lang: str, t: datetime) -> SkyModel`; `astro.NIGHT_SUN_ALT = -0.8333`; `astro.first_or_none(times, oks) -> datetime|None`.

- [ ] **Step 1: Failing tests**

`tests/test_netcache.py`:
```python
import time
from pathlib import Path
import pytest
from sky import netcache


def test_fresh_cache_not_refetched(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("old", encoding="utf-8")
    monkeypatch.setattr(netcache, "_download", lambda url, timeout: (_ for _ in ()).throw(AssertionError("fetched")))
    assert netcache.fetch_text("http://x", p, 3600) == "old"


def test_stale_cache_refetched(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("old", encoding="utf-8")
    import os
    os.utime(p, (time.time() - 10_000, time.time() - 10_000))
    monkeypatch.setattr(netcache, "_download", lambda url, timeout: "new")
    assert netcache.fetch_text("http://x", p, 3600) == "new"
    assert p.read_text(encoding="utf-8") == "new"


def test_failure_returns_stale(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("old", encoding="utf-8")
    import os
    os.utime(p, (0, 0))
    monkeypatch.setattr(netcache, "_download", lambda url, timeout: (_ for _ in ()).throw(OSError("net")))
    assert netcache.fetch_text("http://x", p, 3600) == "old"


def test_failure_without_cache_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(netcache, "_download", lambda url, timeout: (_ for _ in ()).throw(OSError("net")))
    assert netcache.fetch_text("http://x", tmp_path / "none.txt", 3600) is None
```

`tests/test_astro.py`:
```python
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
        def __init__(self, d): self._d = d
        def utc_datetime(self): return self._d
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
    # Polárka: nejjasnější hvězda s dec > 89
    cat = load_catalog()
    i = int(np.argmax(cat.dec_deg))
    alt, az, _ = m.stars[i]
    assert abs(alt - 49.7) < 1.0 and (az < 1.5 or az > 358.5)
    assert m.tz.key == "Europe/Prague"
    assert len(m.planets) == 5 and all(isinstance(b.alt, float) for b in m.planets)
    assert any(lbl == "Velká medvědice" for lbl, _, _ in m.labels)


@ephem
def test_sun_times_plzen():
    e = astro.get_ephemeris(CACHE)
    p = parse(PLZEN, config.load({}), "png")
    t = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    m = astro.compute(p, e, load_catalog(), "cs", t)
    assert m.mode == "day"
    s = m.sun.set.astimezone(m.tz)
    assert (s.hour, 10 <= s.minute <= 30) == (18, True)
    r = m.sun.rise.astimezone(m.tz)
    assert r.hour == 7
    assert m.sun.next_rise > t
    assert 0.0 <= m.moon.fraction <= 1.0
```

- [ ] **Step 2–3: Implement**

`sky/netcache.py`:
```python
"""Stažení textu s diskovou cache: čerstvá cache → síť → stará cache → None."""
from __future__ import annotations

import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)


def _download(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "sky-epaper/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_text(url: str, path: Path, max_age_s: int, timeout: float = 10.0) -> str | None:
    if path.exists() and time.time() - path.stat().st_mtime < max_age_s:
        return path.read_text(encoding="utf-8")
    try:
        text = _download(url, timeout)
    except Exception as exc:  # noqa: BLE001 – síť nikdy nesmí shodit render
        if path.exists():
            log.warning("%s: stažení selhalo (%s), používám starou cache", url, exc)
            return path.read_text(encoding="utf-8")
        log.warning("%s: stažení selhalo (%s), cache není", url, exc)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text
```

`sky/astro.py`:
```python
"""Výpočet oblohy přes Skyfield (spec §4, §5.1, §6.1)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from skyfield import almanac
from skyfield.api import Loader, Star, wgs84

from sky.catalog import Catalog
from sky.geo import tz_for
from sky.params import Params

log = logging.getLogger(__name__)

NIGHT_SUN_ALT = -0.8333
EPHEMERIS = "de421.bsp"
PLANETS = [("mercury", "Merkur", "Mercury"), ("venus", "Venuše", "Venus"), ("mars", "Mars", "Mars"),
           ("jupiter barycenter", "Jupiter", "Jupiter"), ("saturn barycenter", "Saturn", "Saturn")]


class Ephemeris:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.load = Loader(str(self.cache_dir), verbose=False)
        self.ts = self.load.timescale(builtin=True)
        self.available = (self.cache_dir / EPHEMERIS).exists()
        self.eph = self.load(EPHEMERIS) if self.available else None


@lru_cache(maxsize=4)
def get_ephemeris(cache_dir: Path) -> Ephemeris:
    return Ephemeris(Path(cache_dir))


def ensure_ephemeris(cache_dir: Path) -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    Loader(str(cache_dir), verbose=False)(EPHEMERIS)   # stáhne, pokud chybí
    get_ephemeris.cache_clear()
    return cache_dir / EPHEMERIS


@dataclass(frozen=True)
class Body:
    key: str
    name: str
    alt: float
    az: float


@dataclass(frozen=True)
class SunInfo:
    alt: float
    az: float
    rise: datetime | None
    set: datetime | None
    next_rise: datetime | None
    next_set: datetime | None


@dataclass(frozen=True)
class MoonInfo:
    alt: float
    az: float
    phase_deg: float
    fraction: float
    rise: datetime | None
    set: datetime | None


@dataclass(frozen=True)
class SkyModel:
    t: datetime
    tz: ZoneInfo
    lat: float
    lon: float
    mode: str
    stars: np.ndarray
    lines: list[tuple[str, list[np.ndarray]]]
    labels: list[tuple[str, float, float]]
    planets: list[Body]
    sun: SunInfo
    moon: MoonInfo


def first_or_none(times, oks) -> datetime | None:
    for ti, ok in zip(times, oks):
        if ok:
            return ti.utc_datetime()
    return None


def _altaz(observer_at, target):
    alt, az, _ = observer_at.observe(target).apparent().altaz(temperature_C=10.0, pressure_mbar=1010.0)
    return float(alt.degrees), float(az.degrees)


def compute(params: Params, eph: Ephemeris, catalog: Catalog, lang: str, t: datetime) -> SkyModel:
    ts, e = eph.ts, eph.eph
    tz = tz_for(params.lat, params.lon)
    topos = wgs84.latlon(params.lat, params.lon)
    observer = e["earth"] + topos
    tt = ts.from_datetime(t)
    at = observer.at(tt)

    # Hvězdy (jeden vektorový výpočet, bez refrakce)
    star = Star(ra_hours=catalog.ra_hours, dec_degrees=catalog.dec_deg)
    alt, az, _ = at.observe(star).apparent().altaz()
    stars = np.column_stack([alt.degrees, az.degrees, catalog.mag])

    # Čáry souhvězdí: všechny vrcholy najednou
    flat = np.concatenate([seg for _, segs in catalog.lines for seg in segs]) if catalog.lines else np.zeros((0, 2))
    lstar = Star(ra_hours=flat[:, 0], dec_degrees=flat[:, 1])
    lalt, laz, _ = at.observe(lstar).apparent().altaz()
    lines, i = [], 0
    for cid, segs in catalog.lines:
        out = []
        for seg in segs:
            n = len(seg)
            out.append(np.column_stack([lalt.degrees[i:i + n], laz.degrees[i:i + n]]))
            i += n
        lines.append((cid, out))

    # Popisky souhvězdí
    ids = list(catalog.names)
    cstar = Star(ra_hours=np.array([catalog.names[k].ra_hours for k in ids]),
                 dec_degrees=np.array([catalog.names[k].dec for k in ids]))
    calt, caz, _ = at.observe(cstar).apparent().altaz()
    labels = [(catalog.names[k].label(lang), float(calt.degrees[j]), float(caz.degrees[j]))
              for j, k in enumerate(ids) if catalog.names[k].rank <= 2]

    planets = []
    for key, cs, en in PLANETS:
        a, z = _altaz(at, e[key])
        planets.append(Body(key, cs if lang == "cs" else en, a, z))

    sun_alt, sun_az = _altaz(at, e["sun"])
    moon_alt, moon_az = _altaz(at, e["moon"])
    mode = "night" if sun_alt < NIGHT_SUN_ALT else "day"

    local = t.astimezone(tz)
    day0 = ts.from_datetime(local.replace(hour=0, minute=0, second=0, microsecond=0))
    day1 = ts.from_datetime(local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
    t48 = ts.from_datetime(t + timedelta(hours=48))

    sun = SunInfo(
        sun_alt, sun_az,
        rise=first_or_none(*almanac.find_risings(observer, e["sun"], day0, day1)),
        set=first_or_none(*almanac.find_settings(observer, e["sun"], day0, day1)),
        next_rise=first_or_none(*almanac.find_risings(observer, e["sun"], tt, t48)),
        next_set=first_or_none(*almanac.find_settings(observer, e["sun"], tt, t48)),
    )
    moon = MoonInfo(
        moon_alt, moon_az,
        phase_deg=float(almanac.moon_phase(e, tt).degrees),
        fraction=float(almanac.fraction_illuminated(e, "moon", tt)),
        rise=first_or_none(*almanac.find_risings(observer, e["moon"], day0, day1)),
        set=first_or_none(*almanac.find_settings(observer, e["moon"], day0, day1)),
    )
    return SkyModel(t, tz, params.lat, params.lon, mode, stars, lines, labels, planets, sun, moon)
```

- [ ] **Step 4: `python -m sky warmup` není ještě k dispozici → stáhnout efemeridu ručně:** `python -c "from sky.astro import ensure_ephemeris; ensure_ephemeris('cache')"`. Spustit testy, PASS; commit `feat(astro): Skyfield sky model, sun/moon times, net cache`

---

### Task 9: ISS (`iss.py`)

**Files:** Create `sky/iss.py`, `tests/test_iss.py`, `tests/data/iss.tle` (aktuální TLE z Celestrak uložené při implementaci; test používá čas = epocha TLE)

**Interfaces:**
- Produces: `Pass(start: datetime, end: datetime, max_alt: float, max_az: float)`, `IssInfo(available: bool, alt: float|None, az: float|None, next_pass: Pass|None)`, `parse_tle(text) -> tuple[str,str,str]|None` (name, l1, l2), `load_tle(cfg) -> tuple|None`, `tle_epoch(l1) -> datetime`, `compute(params, eph, tle, t) -> IssInfo`, `find_visible_passes(sat, observer, topos, eph, t0, t1) -> list[Pass]`.

- [ ] **Step 1: Failing tests**

```python
from datetime import timedelta
from pathlib import Path
import pytest
from sky import astro, config, iss
from sky.params import parse

CACHE = Path("cache")
ephem = pytest.mark.skipif(not (CACHE / "de421.bsp").exists(), reason="de421.bsp missing")
TLE_TEXT = Path("tests/data/iss.tle").read_text(encoding="utf-8")


def test_parse_tle():
    name, l1, l2 = iss.parse_tle(TLE_TEXT)
    assert name.startswith("ISS") and l1.startswith("1 25544") and l2.startswith("2 25544")
    assert iss.parse_tle("garbage") is None
    assert iss.parse_tle("1 25544U\n2 25544 ") is None


def test_unavailable_without_tle():
    p = parse({"lat": "49.747", "lon": "13.378"}, config.load({}), "png")
    info = iss.compute(p, None, None, None)
    assert info == iss.IssInfo(False, None, None, None)


@ephem
def test_passes_near_epoch():
    p = parse({"lat": "49.747", "lon": "13.378"}, config.load({}), "png")
    e = astro.get_ephemeris(CACHE)
    tle = iss.parse_tle(TLE_TEXT)
    t = iss.tle_epoch(tle[1])
    info = iss.compute(p, e, tle, t)
    assert info.available and info.alt is not None and -90 <= info.alt <= 90
    if info.next_pass is not None:
        assert t <= info.next_pass.start <= t + timedelta(hours=48)
        assert info.next_pass.max_alt >= 10
```

- [ ] **Step 2: Uložit fixture**: `curl -sSL "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle" -o tests/data/iss.tle` (3 řádky).

- [ ] **Step 3: Implement**

```python
"""ISS: TLE z Celestrak s cache, aktuální poloha, nejbližší viditelný přelet (spec §6.2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from skyfield.api import EarthSatellite, wgs84

from sky.config import Config
from sky.netcache import fetch_text
from sky.params import Params

TLE_MAX_AGE_S = 86400
MIN_ALT = 10.0
CIVIL_DUSK = -6.0


@dataclass(frozen=True)
class Pass:
    start: datetime
    end: datetime
    max_alt: float
    max_az: float


@dataclass(frozen=True)
class IssInfo:
    available: bool
    alt: float | None
    az: float | None
    next_pass: Pass | None


def parse_tle(text: str) -> tuple[str, str, str] | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            if len(ln) < 60 or len(lines[i + 1]) < 60:
                return None
            name = lines[i - 1] if i > 0 else "ISS"
            return (name, ln, lines[i + 1])
    return None


def load_tle(cfg: Config) -> tuple[str, str, str] | None:
    text = fetch_text(cfg.tle_url, cfg.cache_dir / "iss.tle", TLE_MAX_AGE_S)
    return parse_tle(text) if text else None


def tle_epoch(line1: str) -> datetime:
    yy = int(line1[18:20])
    doy = float(line1[20:32])
    year = 2000 + yy if yy < 57 else 1900 + yy
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1)


def find_visible_passes(sat, observer, topos, eph, t0, t1) -> list[Pass]:
    times, events = sat.find_events(topos, t0, t1, altitude_degrees=MIN_ALT)
    passes: list[Pass] = []
    start = culm = None
    for ti, ev in zip(times, events):
        if ev == 0:
            start, culm = ti, None
        elif ev == 1:
            culm = ti
        elif ev == 2 and start is not None and culm is not None:
            sunlit = bool(sat.at(culm).is_sunlit(eph.eph))
            sun_alt = observer.at(culm).observe(eph.eph["sun"]).apparent().altaz()[0].degrees
            if sunlit and sun_alt < CIVIL_DUSK:
                alt, az, _ = (sat - topos).at(culm).altaz()
                passes.append(Pass(start.utc_datetime(), ti.utc_datetime(),
                                   float(alt.degrees), float(az.degrees)))
            start = culm = None
    return passes


def compute(params: Params, eph, tle, t: datetime | None) -> IssInfo:
    if tle is None or eph is None or not eph.available or t is None:
        return IssInfo(False, None, None, None)
    name, l1, l2 = tle
    sat = EarthSatellite(l1, l2, name, eph.ts)
    topos = wgs84.latlon(params.lat, params.lon)
    observer = eph.eph["earth"] + topos
    tt = eph.ts.from_datetime(t)
    alt, az, _ = (sat - topos).at(tt).altaz()
    passes = find_visible_passes(sat, observer, topos, eph, tt, eph.ts.from_datetime(t + timedelta(hours=48)))
    return IssInfo(True, float(alt.degrees), float(az.degrees), passes[0] if passes else None)
```

- [ ] **Step 4: Tests pass; commit** `feat(iss): TLE cache, position and next visible pass`

---

### Task 10: Úkazy (`events.py`)

**Files:** Create `sky/events.py`, `tests/test_events.py`, `tests/data/events_sample.ics`

**Interfaces:**
- Produces: `Event(date: date, title: str, kind: str)`, `classify(summary) -> tuple[str, str]` (kind, title), `parse_events(ics_text, start: date, days=60) -> list[Event]`, `select(events, kinds, n) -> list[Event]`, `upcoming(cfg, today, n=12) -> list[Event]|None` (None = nedostupné).

- [ ] **Step 1: Fixture** `tests/data/events_sample.ics`:

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//sky//CS
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261024
DTEND;VALUE=DATE:20261025
UID:a1
SUMMARY:⛒ Dolní konjunkce Venuše
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261026
DTEND;VALUE=DATE:20261027
UID:a2
SUMMARY:🌕 Úplněk
DESCRIPTION:Řekněte o tomto kalendáři i ostatním! <a href="https://x">odkaz</a>
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20251105
DTEND;VALUE=DATE:20251106
RRULE:FREQ=YEARLY
UID:taur
SUMMARY:👁️ Meteorický roj Tauridy
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261106
DTEND;VALUE=DATE:20261107
RECURRENCE-ID;VALUE=DATE:20261105
UID:taur
SUMMARY:👁️ Meteorický roj Tauridy (maximum)
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261013
DTEND;VALUE=DATE:20261014
UID:a3
SUMMARY:🔭 Uran v opozici
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261001
DTEND;VALUE=DATE:20261002
UID:a4
SUMMARY:ℹ️ Něco starého
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260812
DTEND;VALUE=DATE:20260813
UID:a5
SUMMARY:⚠️ Zatmění Slunce
END:VEVENT
END:VCALENDAR
```

- [ ] **Step 2: Failing tests**

```python
from datetime import date
from pathlib import Path
from sky.events import Event, classify, parse_events, select

ICS = Path("tests/data/events_sample.ics").read_text(encoding="utf-8")
TODAY = date(2026, 10, 13)


def test_classify():
    assert classify("👁️ Meteorický roj Tauridy") == ("eye", "Meteorický roj Tauridy")
    assert classify("🔭 Uran v opozici") == ("scope", "Uran v opozici")
    assert classify("⚠️ Zatmění") == ("warn", "Zatmění")
    assert classify("🌕 Úplněk") == ("moon", "Úplněk")
    assert classify("🌓 První čtvrt") == ("moon", "První čtvrt")
    assert classify("⛒ Konjunkce") == ("none", "Konjunkce")
    assert classify("ℹ️ Info") == ("info", "Info")
    assert classify("Bez emoji") == ("other", "Bez emoji")


def test_parse_window_and_order():
    ev = parse_events(ICS, TODAY, days=60)
    dates = [e.date for e in ev]
    assert dates == sorted(dates)
    assert ev[0] == Event(date(2026, 10, 13), "Uran v opozici", "scope")
    assert all(TODAY <= e.date <= date(2026, 12, 12) for e in ev)
    assert not any(e.title == "Něco starého" for e in ev)


def test_recurrence_override_not_duplicated():
    ev = parse_events(ICS, TODAY, days=60)
    taur = [e for e in ev if "Tauridy" in e.title]
    assert taur == [Event(date(2026, 11, 6), "Meteorický roj Tauridy (maximum)", "eye")]


def test_select_filters_kinds_and_limits():
    ev = parse_events(ICS, TODAY, days=60)
    out = select(ev, ("eye", "scope", "warn", "moon"), 2)
    assert [e.kind for e in out] == ["scope", "moon"]
    assert not any(e.kind in ("none", "info") for e in select(ev, ("eye", "scope", "warn", "moon"), 10))
```

- [ ] **Step 3: Implement**

```python
"""Kalendář úkazů (ICS Google kalendáře Jana Tichého), spec §6.3."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import icalendar
import recurring_ical_events

from sky.config import Config
from sky.netcache import fetch_text

log = logging.getLogger(__name__)
ICS_MAX_AGE_S = 86400
WINDOW_DAYS = 60

# (prefix, kind) – pořadí záleží: delší/specifičtější první
EMOJI_KINDS = [
    ("👁", "eye"), ("🔭", "scope"), ("⚠", "warn"),
    ("🌑", "moon"), ("🌒", "moon"), ("🌓", "moon"), ("🌔", "moon"),
    ("🌕", "moon"), ("🌖", "moon"), ("🌗", "moon"), ("🌘", "moon"),
    ("⛒", "none"), ("ℹ", "info"),
]
_STRIP = "\ufe0f\u200d \t"


@dataclass(frozen=True)
class Event:
    date: date
    title: str
    kind: str


def classify(summary: str) -> tuple[str, str]:
    s = summary.strip()
    for prefix, kind in EMOJI_KINDS:
        if s.startswith(prefix):
            return kind, s[len(prefix):].lstrip(_STRIP)
    return "other", s


def parse_events(ics_text: str, start: date, days: int = WINDOW_DAYS) -> list[Event]:
    cal = icalendar.Calendar.from_ical(ics_text)
    end = start + timedelta(days=days)
    seen: set[tuple[date, str]] = set()
    out: list[Event] = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        d = comp.get("DTSTART").dt
        if isinstance(d, datetime):
            d = d.date()
        kind, title = classify(str(comp.get("SUMMARY", "")))
        key = (d, title)
        if key in seen or not title:
            continue
        seen.add(key)
        out.append(Event(d, title, kind))
    out.sort(key=lambda e: (e.date, e.title))
    return out


def select(events: list[Event], kinds: tuple[str, ...], n: int) -> list[Event]:
    return [e for e in events if e.kind in kinds][:n]


def upcoming(cfg: Config, today: date, n: int = 12) -> list[Event] | None:
    text = fetch_text(cfg.events_url, cfg.cache_dir / "events.ics", ICS_MAX_AGE_S)
    if not text:
        return None
    try:
        return select(parse_events(text, today), cfg.event_types, n)
    except Exception as exc:  # noqa: BLE001
        log.warning("ICS parse failed: %s", exc)
        return None
```

- [ ] **Step 4: Tests pass; commit** `feat(events): ICS parsing with recurrence, emoji classification`

---

### Task 11: Vykreslení (`render.py`)

**Files:** Create `sky/render.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `SkyModel`, `IssInfo`, `list[Event]|None`, `Params`, `layout.compute`, `palette.make_palette`, `fonts`, `icons`, `geo`, `projection`.
- Produces: `render(params: Params, model: SkyModel, iss_info: IssInfo, events: list[Event]|None) -> Image.Image` (mode `P`, size `w×h`, paleta nastavená).

- [ ] **Step 1: Failing tests** (model bez sítě a bez efemeridy – ručně sestavený)

```python
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
                      np.array([[20.0, 170.0], [-5.0, 175.0]])])]
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
```

- [ ] **Step 2–3: Implement**

```python
"""Kreslení mapy a infopanelu do obrazu v režimu P (spec §5)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from sky import layout
from sky.astro import SkyModel
from sky.events import Event
from sky.fonts import BdfFont, draw_text, fit, load_font, text_width
from sky.geo import compass, fmt_coords, fmt_date, fmt_time, tr
from sky.icons import draw_icon
from sky.iss import IssInfo
from sky.layout import Rect, Zones
from sky.palette import Palette, make_palette
from sky.params import Params
from sky.projection import HorizonProjection, SkyProjection, clip_segment_circle, clip_segment_rect

STAR_SIZES = ((1.0, 5), (2.0, 4), (3.0, 3), (4.0, 2), (99.0, 1))
LINE_MIN_ALT = -15.0
LABEL_MIN_ALT = 10.0
HORIZON_BAR = 24          # pás pod obzorem u `horizon` pro světové strany
EVENT_KIND_ICON = {"eye": "eye", "scope": "scope", "warn": "warn", "moon": "moon"}


@dataclass
class Ctx:
    img: Image.Image
    d: ImageDraw.ImageDraw
    pal: Palette
    lang: str
    small: BdfFont
    mid: BdfFont
    big: BdfFont


def render(params: Params, model: SkyModel, iss_info: IssInfo, events: list[Event] | None) -> Image.Image:
    pal = make_palette(params.colors, model.mode)
    img = Image.new("P", (params.w, params.h), pal["bg"])
    img.putpalette(pal.flat())
    ctx = Ctx(img, ImageDraw.Draw(img), pal, params.lang, load_font("8x16"), load_font("12x24"), load_font("16x32"))
    zones = layout.compute(params.w, params.h, params.view)
    if params.view == "sky":
        _draw_sky(ctx, zones.map, params, model, iss_info)
    else:
        _draw_horizon(ctx, zones.map, params, model, iss_info)
    if zones.info is not None:
        _draw_info(ctx, zones, params, model, iss_info, events)
    return img


# ---------- mapa ----------

def _star_size(mag: float) -> int:
    for lim, px in STAR_SIZES:
        if mag <= lim:
            return px
    return 1


def _dot(ctx: Ctx, x: float, y: float, px: int, idx: int) -> None:
    if px <= 1:
        ctx.d.point((round(x), round(y)), fill=idx)
    elif px == 2:
        ctx.d.rectangle((round(x), round(y), round(x) + 1, round(y) + 1), fill=idx)
    else:
        r = px / 2.0
        ctx.d.ellipse((x - r, y - r, x + r, y + r), fill=idx)


def _planet(ctx: Ctx, x: float, y: float, name: str) -> None:
    ctx.d.ellipse((x - 3.5, y - 3.5, x + 3.5, y + 3.5), fill=ctx.pal["planet"], outline=ctx.pal["fg"])
    draw_text(ctx.img, (x + 6, y - 8), name, ctx.small, ctx.pal["label"])


def _moon(ctx: Ctx, x: float, y: float, phase_deg: float, r: int = 8) -> None:
    """Kotouč s fází: dorůstá (0–180°) osvětlen vpravo, couvá vlevo."""
    ctx.d.ellipse((x - r, y - r, x + r, y + r), fill=ctx.pal["moon_dark"], outline=ctx.pal["fg"])
    ph = phase_deg % 360.0
    cosp = math.cos(math.radians(ph))
    for yy in range(-r + 1, r):
        c = math.sqrt(r * r - yy * yy)
        if ph < 180.0:
            x0, x1 = c * cosp, c
        else:
            x0, x1 = -c, -c * cosp
        if x1 - x0 >= 1.0:
            ctx.d.line((x + x0, y + yy, x + x1, y + yy), fill=ctx.pal["moon_lit"])
    ctx.d.ellipse((x - r, y - r, x + r, y + r), outline=ctx.pal["fg"])


def _sun(ctx: Ctx, x: float, y: float, r: int = 5) -> None:
    for k in range(8):
        a = math.radians(k * 45)
        ctx.d.line((x + (r + 2) * math.cos(a), y + (r + 2) * math.sin(a),
                    x + (r + 5) * math.cos(a), y + (r + 5) * math.sin(a)), fill=ctx.pal["sun"])
    ctx.d.ellipse((x - r, y - r, x + r, y + r), fill=ctx.pal["sun"], outline=ctx.pal["fg"])


def _iss_marker(ctx: Ctx, x: float, y: float) -> None:
    c = ctx.pal["iss"]
    ctx.d.line((x - 4, y, x + 4, y), fill=c)
    ctx.d.line((x, y - 4, x, y + 4), fill=c)
    draw_text(ctx.img, (x + 6, y - 8), "ISS", ctx.small, c)


def _place_label(ctx: Ctx, placed: list[tuple[int, int, int, int]], x: float, y: float, text: str, bounds) -> None:
    w, h = text_width(ctx.small, text), ctx.small.height
    x0, y0 = int(x - w / 2), int(y - h / 2)
    box = (x0, y0, x0 + w, y0 + h)
    if not bounds(box):
        return
    for b in placed:
        if box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1]:
            return
    placed.append(box)
    draw_text(ctx.img, (x0, y0), text, ctx.small, ctx.pal["label"])


def _draw_bodies(ctx: Ctx, project, visible, model: SkyModel, iss_info: IssInfo, params: Params) -> None:
    for b in model.planets:
        if visible(b.alt, b.az):
            _planet(ctx, *project(b.alt, b.az), b.name)
    if visible(model.moon.alt, model.moon.az):
        _moon(ctx, *project(model.moon.alt, model.moon.az), model.moon.phase_deg)
    if model.mode == "day" and visible(model.sun.alt, model.sun.az):
        _sun(ctx, *project(model.sun.alt, model.sun.az))
    if params.iss and iss_info.available and iss_info.alt is not None and visible(iss_info.alt, iss_info.az):
        _iss_marker(ctx, *project(iss_info.alt, iss_info.az))


def _draw_sky(ctx: Ctx, m: Rect, params: Params, model: SkyModel, iss_info: IssInfo) -> None:
    proj = SkyProjection(m.w, params.az, margin=18 if m.w >= 200 else 10)
    cx, cy = proj.center
    R = proj.radius
    ox, oy = m.x, m.y

    def project(alt, az):
        x, y = proj.project(alt, az)
        return (x + ox, y + oy)

    def visible(alt, az):
        return alt >= 0.0

    fg = ctx.pal["fg"]
    for _, segs in model.lines:
        for seg in segs:
            for (a0, z0), (a1, z1) in zip(seg[:-1], seg[1:]):
                if a0 < LINE_MIN_ALT and a1 < LINE_MIN_ALT:
                    continue
                clipped = clip_segment_circle(proj.project(a0, z0), proj.project(a1, z1), (cx, cy), R)
                if clipped:
                    (x0, y0), (x1, y1) = clipped
                    ctx.d.line((x0 + ox, y0 + oy, x1 + ox, y1 + oy), fill=ctx.pal["line"], width=1)
    for alt, az, mag in model.stars:
        if alt >= 0.0:
            x, y = project(alt, az)
            _dot(ctx, x, y, _star_size(mag), ctx.pal["star"])
    placed: list[tuple[int, int, int, int]] = []
    for text, alt, az in model.labels:
        if alt >= LABEL_MIN_ALT:
            x, y = project(alt, az)
            _place_label(ctx, placed, x, y, text,
                         lambda b: all(proj.inside(px - ox, py - oy) for px, py in ((b[0], b[1]), (b[2], b[3]), (b[0], b[3]), (b[2], b[1]))))
    _draw_bodies(ctx, project, visible, model, iss_info, params)
    ctx.d.ellipse((cx - R + ox, cy - R + oy, cx + R + ox, cy + R + oy), outline=ctx.pal["horizon"], width=1)
    font = ctx.mid if m.w >= 300 else ctx.small
    for az in (0, 90, 180, 270):
        lbl = compass(az, ctx.lang)
        x, y = proj.project(-90.0 * (proj.margin - 2) / R * 0.5 - 0.0, az)  # těsně vně kružnice
        x, y = proj.project(0.0, az)
        dxn, dyn = (x - cx) / R, (y - cy) / R
        px = x + dxn * (proj.margin / 2 + 1) + ox - text_width(font, lbl) / 2
        py = y + dyn * (proj.margin / 2 + 1) + oy - font.height / 2
        draw_text(ctx.img, (px, py), lbl, font, fg)


def _draw_horizon(ctx: Ctx, m: Rect, params: Params, model: SkyModel, iss_info: IssInfo) -> None:
    bar = HORIZON_BAR if m.h >= 4 * HORIZON_BAR else 0
    mh = m.h - bar
    proj = HorizonProjection(m.w, mh, params.az, params.fov)
    ox, oy = m.x, m.y

    def project(alt, az):
        x, y = proj.project(alt, az)
        return (x + ox, y + oy)

    for _, segs in model.lines:
        for seg in segs:
            for (a0, z0), (a1, z1) in zip(seg[:-1], seg[1:]):
                if a0 < LINE_MIN_ALT and a1 < LINE_MIN_ALT:
                    continue
                clipped = clip_segment_rect(proj.project(a0, z0), proj.project(a1, z1), m.w, mh)
                if clipped:
                    (x0, y0), (x1, y1) = clipped
                    ctx.d.line((x0 + ox, y0 + oy, x1 + ox, y1 + oy), fill=ctx.pal["line"], width=1)
    for alt, az, mag in model.stars:
        if proj.visible(alt, az):
            x, y = project(alt, az)
            _dot(ctx, x, y, _star_size(mag), ctx.pal["star"])
    placed: list[tuple[int, int, int, int]] = []
    for text, alt, az in model.labels:
        if alt >= LABEL_MIN_ALT and proj.visible(alt, az):
            x, y = project(alt, az)
            _place_label(ctx, placed, x, y, text,
                         lambda b: b[0] >= ox and b[2] <= ox + m.w and b[1] >= oy and b[3] <= oy + mh)
    _draw_bodies(ctx, project, proj.visible, model, iss_info, params)
    hy = oy + mh - 1
    ctx.d.line((ox, hy, ox + m.w - 1, hy), fill=ctx.pal["horizon"], width=1)
    if bar:
        font = ctx.small
        for az in range(0, 360, 45):
            if abs(((az - params.az + 180) % 360) - 180) <= params.fov / 2:
                x, _ = project(0.0, az)
                ctx.d.line((x, hy - 4, x, hy + 3), fill=ctx.pal["horizon"])
                lbl = compass(az, ctx.lang)
                draw_text(ctx.img, (x - text_width(font, lbl) / 2, hy + 5), lbl, font, ctx.pal["fg"])


# ---------- infopanel ----------

class Cursor:
    def __init__(self, ctx: Ctx, col: Rect):
        self.ctx, self.col = ctx, col
        self.x = col.x + layout.MARGIN
        self.y = col.y
        self.w = col.w - 2 * layout.MARGIN
        self.bottom = col.bottom

    def room(self, lines: int = 1) -> bool:
        return self.y + lines * layout.U <= self.bottom

    def line(self, text: str, idx: int | None = None, box: bool = False) -> bool:
        if not self.room():
            return False
        f = self.ctx.small
        t = fit(f, text, self.w)
        draw_text(self.ctx.img, (self.x, self.y), t, f, self.ctx.pal["fg"] if idx is None else idx)
        if box:
            self.ctx.d.rectangle((self.x - 2, self.y - 1, self.x + text_width(f, t) + 1, self.y + f.height - 1),
                                 outline=self.ctx.pal["fg"])
        self.y += layout.U
        return True

    def title(self, icon: str, text: str) -> bool:
        if not self.room(2):
            return False
        draw_icon(self.ctx.img, (self.x, self.y), icon, self.ctx.pal["fg"])
        draw_text(self.ctx.img, (self.x + 20, self.y), fit(self.ctx.small, text, self.w - 20), self.ctx.small, self.ctx.pal["fg"])
        self.ctx.d.line((self.x, self.y + 17, self.x + self.w - 1, self.y + 17), fill=self.ctx.pal["fg"])
        self.y += layout.U + 4
        return True

    def gap(self) -> None:
        self.y += layout.U // 2


def _draw_header(ctx: Ctx, z: Zones, params: Params, model: SkyModel) -> None:
    h = z.header
    local = model.t.astimezone(model.tz)
    x, y = h.x + layout.MARGIN, h.y + layout.MARGIN // 2
    font = ctx.big if z.header_big else ctx.small
    draw_text(ctx.img, (x, y), fit(font, fmt_date(local.date(), ctx.lang), h.w - 2 * layout.MARGIN), font, ctx.pal["fg"])
    y += font.height
    draw_text(ctx.img, (x, y), fit(ctx.small, f"{local.strftime('%H:%M')}  {fmt_coords(model.lat, model.lon)}", h.w - 2 * layout.MARGIN),
              ctx.small, ctx.pal["fg"])


def _sec_sun(c: Cursor, model: SkyModel) -> None:
    L, tz = c.ctx.lang, model.tz
    if not c.title("sun", tr(L, "sun")):
        return
    c.line(f"{tr(L, 'rise'):<7}{fmt_time(model.sun.rise, tz)}")
    c.line(f"{tr(L, 'set'):<7}{fmt_time(model.sun.set, tz)}")
    if model.mode == "night":
        c.line(f"{tr(L, 'dawn_at')} {fmt_time(model.sun.next_rise, tz)}")
    else:
        c.line(f"{tr(L, 'night_from')} {fmt_time(model.sun.next_set, tz)}")
    c.gap()


def _sec_moon(c: Cursor, model: SkyModel) -> None:
    L, tz = c.ctx.lang, model.tz
    if not c.title("moon", tr(L, "moon")):
        return
    c.line(f"{tr(L, 'rise'):<7}{fmt_time(model.moon.rise, tz)}")
    c.line(f"{tr(L, 'set'):<7}{fmt_time(model.moon.set, tz)}")
    trend = tr(L, "waxing") if model.moon.phase_deg % 360 < 180 else tr(L, "waning")
    c.line(f"{tr(L, 'phase')} {round(model.moon.fraction * 100):d} % {trend}")
    c.gap()


def _sec_iss(c: Cursor, model: SkyModel, info: IssInfo) -> None:
    L, tz = c.ctx.lang, model.tz
    if not c.title("iss", tr(L, "iss")):
        return
    if not info.available:
        c.line(tr(L, "unavailable"))
    elif info.next_pass is None:
        c.line(tr(L, "no_pass"))
    else:
        p = info.next_pass
        s = p.start.astimezone(tz)
        c.line(f"{fmt_date(s.date(), L)} {s.strftime('%H:%M')}–{p.end.astimezone(tz).strftime('%H:%M')}")
        c.line(f"{tr(L, 'max')} {round(p.max_alt)}° {compass(p.max_az, L)}")
    c.gap()


def _sec_events(c: Cursor, model: SkyModel, events: list[Event] | None) -> None:
    L = c.ctx.lang
    if not c.title("cal", tr(L, "events")):
        return
    if events is None:
        c.line(tr(L, "unavailable"))
        return
    if not events:
        c.line(tr(L, "none"))
        return
    today = model.t.astimezone(model.tz).date()
    for e in events:
        if not c.room():
            break
        is_today = e.date == today
        idx = c.ctx.pal["today"] if is_today else None
        box = is_today and c.ctx.pal.ncolors == 2
        c.line(f"{e.date.day:>2}. {e.date.month:>2}. {e.title}", idx=idx, box=box)


def _draw_info(ctx: Ctx, z: Zones, params: Params, model: SkyModel, iss_info: IssInfo, events: list[Event] | None) -> None:
    _draw_header(ctx, z, params, model)
    sections = [("sun", lambda c: _sec_sun(c, model)), ("moon", lambda c: _sec_moon(c, model))]
    if params.iss:
        sections.append(("iss", lambda c: _sec_iss(c, model, iss_info)))
    if params.events:
        sections.append(("events", lambda c: _sec_events(c, model, events)))
    n = len(z.columns)
    if n >= 3:
        groups = [[s for s in sections if s[0] in ("sun", "moon")],
                  [s for s in sections if s[0] == "iss"],
                  [s for s in sections if s[0] == "events"]]
    elif n == 2:
        groups = [[s for s in sections if s[0] in ("sun", "moon")],
                  [s for s in sections if s[0] in ("iss", "events")]]
    else:
        groups = [sections]
    for col, group in zip(z.columns, groups):
        cur = Cursor(ctx, col)
        for _, fn in group:
            fn(cur)
```

- [ ] **Step 4: Tests pass; commit** `feat(render): sky/horizon map and info panel`

---

### Task 12: Výstup (`output.py`)

**Files:** Create `sky/output.py`, `tests/test_output.py`

**Interfaces:**
- Produces: `encode(img: Image.Image, fmt: str, rot: int) -> tuple[bytes, str]` (bytes, MIME `image/png` / `image/bmp`).

- [ ] **Step 1: Failing tests**

```python
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


def test_png_bw_is_1bit_and_two_colors():
    data, mime = encode(_img("bw"), "png", 0)
    assert mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n"
    back = Image.open(io.BytesIO(data))
    assert back.size == (40, 20) and back.mode in ("P", "1")
    assert len(back.getcolors()) == 2


def test_png_bwry_has_small_palette():
    data, _ = encode(_img("bwry"), "png", 0)
    back = Image.open(io.BytesIO(data))
    assert back.mode == "P" and len(back.getpalette()) // 3 <= 4 or back.getpalette()[:12] == [255, 255, 255, 0, 0, 0, 255, 0, 0, 255, 255, 0]


def test_bmp_bw_is_1bpp():
    data, mime = encode(_img("bw"), "bmp", 0)
    assert mime == "image/bmp" and data[:2] == b"BM"
    assert int.from_bytes(data[28:30], "little") == 1
    back = Image.open(io.BytesIO(data))
    assert back.size == (40, 20)


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
```

- [ ] **Step 2–3: Implement**

```python
"""Kódování výsledného obrazu: PNG / BMP, rotace (spec §7)."""
from __future__ import annotations

import io

from PIL import Image

MIME = {"png": "image/png", "bmp": "image/bmp"}


def encode(img: Image.Image, fmt: str, rot: int) -> tuple[bytes, str]:
    if rot:
        img = img.rotate(-rot, expand=True)
    buf = io.BytesIO()
    if fmt == "bmp":
        if len(img.getpalette()) // 3 <= 2:
            bw = img.convert("RGB").convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1", dither=Image.Dither.NONE)
            bw.save(buf, "BMP")
        else:
            img.save(buf, "BMP")
    else:
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue(), MIME[fmt]
```

- [ ] **Step 4: Tests pass; commit** `feat(output): PNG/BMP encoding with rotation`

---

### Task 13: Služba, HTTP a CLI (`service.py`, `app.py`, `cli.py`)

**Files:** Create `sky/service.py`, `sky/app.py`, `sky/cli.py`, `tests/test_app.py`

**Interfaces:**
- `service.Result(data: bytes, mime: str, mode: str)`, `service.build(params: Params, cfg: Config, now: datetime|None = None) -> Result` (cache dle `cfg.render_cache_s`, klíč = params + t zaokrouhlené na 5 min), `service.EphemerisMissing(RuntimeError)`.
- `app.app` (FastAPI) s `/health`, `/sky.{fmt}`; `app.create_app(cfg: Config|None = None) -> FastAPI`.
- `cli.main(argv=None) -> int`: `render`, `serve`, `warmup`.

- [ ] **Step 1: Failing tests** (bez efemeridy testujeme validaci a token; s efemeridou plný render)

```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sky import config
from sky.app import create_app

CACHE = Path("cache")
ephem = pytest.mark.skipif(not (CACHE / "de421.bsp").exists(), reason="de421.bsp missing")


def client(env):
    return TestClient(create_app(config.load(env)))


def test_health():
    r = client({"SKY_CACHE_DIR": "cache"}).get("/health")
    assert r.status_code == 200 and "ephemeris" in r.json()


def test_bad_params_400():
    c = client({"SKY_CACHE_DIR": "cache"})
    assert c.get("/sky.png?lat=99&lon=1").status_code == 400
    assert c.get("/sky.gif?lat=49&lon=13").status_code == 400
    assert c.get("/sky.png").status_code == 400


def test_token_403():
    c = client({"SKY_CACHE_DIR": "cache", "SKY_TOKEN": "s3cret"})
    assert c.get("/sky.png?lat=49&lon=13").status_code == 403
    assert c.get("/sky.png?lat=49&lon=13&token=wrong").status_code == 403


@ephem
def test_render_png_and_bmp(monkeypatch):
    from sky import service
    monkeypatch.setattr(service.iss, "load_tle", lambda cfg: None)
    monkeypatch.setattr(service.events, "upcoming", lambda cfg, today, n=12: [])
    c = client({"SKY_CACHE_DIR": "cache"})
    r = c.get("/sky.png?lat=49.747&lon=13.378&t=2026-10-13T22:00%2B02:00")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["x-sky-mode"] == "night" and r.content[:4] == b"\x89PNG"
    r = c.get("/sky.bmp?lat=49.747&lon=13.378&view=horizon&az=200&colors=bwry&w=480&h=800&t=2026-10-13T12:00Z")
    assert r.status_code == 200 and r.content[:2] == b"BM" and r.headers["x-sky-mode"] == "day"
```

- [ ] **Step 2–3: Implement**

`sky/service.py`:
```python
"""Pipeline: parametry → model → render → bytes, s paměťovou cache."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from sky import astro, events, iss, output, render
from sky.catalog import load_catalog
from sky.config import Config
from sky.params import Params

log = logging.getLogger(__name__)
_cache: dict[tuple, tuple[float, "Result"]] = {}


class EphemerisMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class Result:
    data: bytes
    mime: str
    mode: str


def _key(p: Params, t: datetime) -> tuple:
    return (p, t.replace(second=0, microsecond=0, minute=t.minute - t.minute % 5))


def build(params: Params, cfg: Config, now: datetime | None = None) -> Result:
    t = params.t or now or datetime.now(timezone.utc)
    key = _key(params, t)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < cfg.render_cache_s:
        return hit[1]
    eph = astro.get_ephemeris(cfg.cache_dir)
    if not eph.available:
        raise EphemerisMissing(f"chybí {astro.EPHEMERIS} v {cfg.cache_dir}; spusť `python -m sky warmup`")
    t0 = time.perf_counter()
    model = astro.compute(params, eph, load_catalog(), params.lang, t)
    iss_info = iss.compute(params, eph, iss.load_tle(cfg), t) if params.iss else iss.IssInfo(False, None, None, None)
    evs = events.upcoming(cfg, t.astimezone(model.tz).date()) if params.events else []
    img = render.render(params, model, iss_info, evs)
    data, mime = output.encode(img, params.fmt, params.rot)
    log.info("render %s %dx%d %s %s mode=%s %.0f ms", params.view, params.w, params.h, params.colors,
             params.fmt, model.mode, (time.perf_counter() - t0) * 1000)
    res = Result(data, mime, model.mode)
    if len(_cache) > 256:
        _cache.clear()
    _cache[key] = (time.time(), res)
    return res
```

`sky/app.py`:
```python
"""HTTP rozhraní (spec §3.1)."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from sky import astro, config, service
from sky.params import ParamError, parse

log = logging.getLogger(__name__)


def create_app(cfg: config.Config | None = None) -> FastAPI:
    cfg = cfg or config.load()
    app = FastAPI(title="sky-epaper", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health():
        eph = astro.get_ephemeris(cfg.cache_dir)
        return {"status": "ok" if eph.available else "degraded",
                "ephemeris": "ok" if eph.available else "missing"}

    @app.get("/sky.{fmt}")
    def sky(fmt: str, request: Request):
        q = dict(request.query_params)
        if cfg.token and q.get("token") != cfg.token:
            return PlainTextResponse("forbidden", status_code=403)
        try:
            params = parse(q, cfg, fmt)
        except ParamError as exc:
            return PlainTextResponse(str(exc), status_code=400)
        try:
            res = service.build(params, cfg)
        except service.EphemerisMissing as exc:
            return PlainTextResponse(str(exc), status_code=503)
        return Response(res.data, media_type=res.mime,
                        headers={"Cache-Control": "no-store", "X-Sky-Mode": res.mode})

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
```

`sky/cli.py`:
```python
"""CLI: render / serve / warmup (spec §3.2)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sky import config, service
from sky.params import ParamError, parse


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sky")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="vykreslí obrázek do souboru")
    for k in ("lat", "lon", "view", "az", "fov", "w", "h", "colors", "rot", "t", "lang"):
        r.add_argument(f"--{k}")
    r.add_argument("--no-iss", action="store_true")
    r.add_argument("--no-events", action="store_true")
    r.add_argument("--out", required=True)

    s = sub.add_parser("serve", help="spustí HTTP službu")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8080)

    sub.add_parser("warmup", help="stáhne efemeridu do cache")

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    cfg = config.load()

    if a.cmd == "warmup":
        from sky.astro import ensure_ephemeris
        print(ensure_ephemeris(cfg.cache_dir))
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("sky.app:app", host=a.host, port=a.port)
        return 0

    q = {k: v for k, v in vars(a).items() if k in ("lat", "lon", "view", "az", "fov", "w", "h", "colors", "rot", "t", "lang") and v}
    if a.no_iss:
        q["iss"] = "0"
    if a.no_events:
        q["events"] = "0"
    fmt = Path(a.out).suffix.lstrip(".").lower() or "png"
    try:
        params = parse(q, cfg, fmt)
        res = service.build(params, cfg)
    except (ParamError, service.EphemerisMissing) as exc:
        print(f"chyba: {exc}", file=sys.stderr)
        return 2
    Path(a.out).write_bytes(res.data)
    print(f"{a.out}: {len(res.data)} B, mode={res.mode}")
    return 0
```

- [ ] **Step 4: Tests pass; commit** `feat(service,app,cli): HTTP service, CLI and render cache`

---

### Task 14: Ruční vizuální ověření a doladění

**Files:** Modify `sky/render.py` podle nálezů; Create `out/` (gitignored)

- [ ] **Step 1: Vyrenderovat sadu náhledů**

```bash
python -m sky render --lat 49.747 --lon 13.378 --t 2026-10-13T22:00+02:00 --out out/sky-night-bw.png
python -m sky render --lat 49.747 --lon 13.378 --t 2026-10-13T14:00+02:00 --colors bwry --out out/sky-day-bwry.png
python -m sky render --lat 49.747 --lon 13.378 --t 2026-10-13T22:00+02:00 --view horizon --az 200 --colors bwr --out out/horizon-night-bwr.png
python -m sky render --lat 49.747 --lon 13.378 --t 2026-10-13T22:00+02:00 --w 480 --h 800 --out out/sky-portrait.png
python -m sky render --lat 49.747 --lon 13.378 --t 2026-10-13T22:00+02:00 --view horizon --w 480 --h 800 --out out/horizon-portrait.bmp
python -m sky render --lat 49.747 --lon 13.378 --t 2026-10-13T22:00+02:00 --w 296 --h 128 --out out/tiny.png
```

- [ ] **Step 2: Prohlédnout obrázky (Read tool), zkontrolovat:** čitelnost popisků, kolize, Měsíc se správnou fází, světové strany na správné straně (při `az=180` sever nahoře, východ vlevo), infopanel bez přetečení, dnešní úkaz zvýrazněný.
- [ ] **Step 3: Opravit nálezy v `render.py`, znovu testy, commit** `fix(render): visual tuning after preview`

---

### Task 15: Dockerfile a README

**Files:** Create `Dockerfile`, `README.md`

- [ ] **Step 1: Dockerfile**

```dockerfile
# Sky e-paper – nasazení v Coolify (Dockerfile zdroj). Kód je v image.
FROM python:3.12-slim
WORKDIR /app
ENV SKY_CACHE_DIR=/cache PYTHONUNBUFFERED=1
COPY pyproject.toml README.md ./
COPY sky ./sky
RUN pip install --no-cache-dir . \
 && mkdir -p /app/cache-seed \
 && SKY_CACHE_DIR=/app/cache-seed python -m sky warmup
EXPOSE 8080
# Při startu doplní efemeridu do (prázdného) svazku /cache a spustí server.
CMD ["sh", "-c", "mkdir -p $SKY_CACHE_DIR && cp -n /app/cache-seed/*.bsp $SKY_CACHE_DIR/ 2>/dev/null; uvicorn sky.app:app --host 0.0.0.0 --port 8080"]
```

- [ ] **Step 2: README.md** – česky: účel, URL a tabulka parametrů (§3.1 specu), CLI příklady, env proměnné, nasazení v Coolify (Dockerfile, volume `/cache`, port 8080, `SKY_TOKEN`), zapojení do Živého obrazu (obrázek z URL), zdroje dat a licence (d3-celestial BSD-3, Spleen BSD-2, Skyfield MIT, kalendář úkazů Jan Tichý – jantichy.cz/ukazy, Celestrak TLE), testy (`python -m pytest -q`, `python -m sky warmup` pro ephem testy).

- [ ] **Step 3: Ověřit build lokálně, pokud je Docker k dispozici:** `docker build -t sky-epaper .` a `docker run --rm -p 8080:8080 sky-epaper`, `curl "http://localhost:8080/sky.png?lat=49.747&lon=13.378" -o /tmp/x.png`. Bez Dockeru krok přeskočit a uvést v závěrečné zprávě.
- [ ] **Step 4: Commit** `docs: README and Dockerfile for Coolify`

---

## Self-review

- **Spec coverage:** §3.1 parametry → Task 1, 13; §3.2 CLI → 13; §3.3 env → 0; §4 režimy → 8 (mode), 11 (barvy, texty „Noc od / Svítá v“); §5.1 objekty → 11; §5.2/5.3 projekce → 3, 11; §5.4 layout → 4, 11; §6.1 → 7, 8; §6.2 → 9; §6.3 → 10; §6.4 cache → 13; §7 palety/výstup → 2, 12; §8 architektura → struktura souborů; §9 chyby → 8 (netcache), 9/10 (unavailable), 13 (400/403/503); §10 testy → každý task; §11 nasazení → 15.
- **Typy:** `IssInfo(available, alt, az, next_pass)` shodně v 9, 11, 13; `Event(date, title, kind)` v 10, 11; `SkyModel` pole shodná v 8 a 11; `Zones.columns` tuple v 4 a 11; `encode(img, fmt, rot)` v 12 a 13; `parse(q, cfg, fmt)` v 1, 11, 13.
- **Review Focus:** 1 → `test_horizon_segment_across_back_is_dropped` (Task 3); 2 → `test_clip_segment_circle_partial` (Task 3); 3 → `test_first_or_none_when_no_event` (Task 8); 4 → `test_recurrence_override_not_duplicated` (Task 10); 5 → `test_tiny_panel_has_no_info` (Task 4) a `test_render_tiny_panel` (Task 11).
