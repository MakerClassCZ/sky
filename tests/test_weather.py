from datetime import datetime, timezone
from pathlib import Path

from sky import config, weather

JSON = Path("tests/data/openmeteo_sample.json").read_text(encoding="utf-8")
UTC = timezone.utc


def test_round_coords_and_url():
    cfg = config.load({})
    assert weather.cache_key(49.747, 13.378) == "49.75_13.40"
    assert weather.cache_key(-33.91, 151.21) == "-33.90_151.20"
    url = weather.build_url(cfg, 49.747, 13.378)
    assert "api.open-meteo.com" in url and "latitude=49.75" in url and "longitude=13.4" in url
    assert "cloud_cover" in url


def test_night_cloud_summary():
    start = datetime(2026, 10, 18, 16, 9, tzinfo=UTC)      # západ
    end = datetime(2026, 10, 19, 5, 34, tzinfo=UTC)        # východ
    info = weather.night_cloud(JSON, start, end)
    assert info is not None
    assert info.mean == 48                                 # průměr hodin 17..29 UTC: 620/13
    assert info.best == 10 and info.best_at == datetime(2026, 10, 19, 2, 0, tzinfo=UTC)


def test_night_cloud_garbage_and_no_overlap():
    assert weather.night_cloud("nope", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)) is None
    assert weather.night_cloud(JSON, datetime(2027, 1, 1, tzinfo=UTC), datetime(2027, 1, 2, tzinfo=UTC)) is None


def test_lines_fit_width():
    from zoneinfo import ZoneInfo
    info = weather.CloudInfo(44, 10, datetime(2026, 10, 19, 2, 0, tzinfo=UTC))
    tz = ZoneInfo("Europe/Prague")
    assert weather.line("cs", tz, info, 40) == "Oblačnost v noci 44 %, min 10 % v 04:00"
    assert weather.line("cs", tz, info, 20) == "Oblačnost v noci 44 %"
    assert weather.line("en", tz, info, 40) == "Night clouds 44 %, min 10 % at 04:00"
