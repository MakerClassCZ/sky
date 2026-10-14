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
    assert "cloud_cover" in url and "cloud_cover_low" in url and "visibility" in url


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
    assert weather.line("cs", tz, info, 20) == "Oblačnost 44 %"
    assert weather.line("en", tz, info, 40) == "Night clouds 44 %, min 10 % at 04:00"


def _json(total, low, mid, high, vis, day="2026-10-20"):
    import json
    times = [f"{day}T{h:02d}:00" for h in range(18, 24)]
    return json.dumps({"hourly": {"time": times, "cloud_cover": total, "cloud_cover_low": low,
                                  "cloud_cover_mid": mid, "cloud_cover_high": high, "visibility": vis}})


START, END = datetime(2026, 10, 20, 17, 30, tzinfo=UTC), datetime(2026, 10, 21, 5, 0, tzinfo=UTC)


def test_layers_high_clouds_and_best_hour_by_effective_cover():
    js = _json([100, 100, 80, 70, 55, 45], [98, 100, 16, 2, 0, 6], [0] * 6, [98, 95, 69, 68, 55, 41], [20000] * 6)
    info = weather.night_cloud(js, START, END)
    assert info.layer == "high" and info.mean == 75
    assert info.best_at == datetime(2026, 10, 20, 23, 0, tzinfo=UTC) and info.best == 45


def test_layers_low_wins_when_over_half():
    js = _json([90] * 6, [60] * 6, [0] * 6, [90] * 6, [20000] * 6)
    assert weather.night_cloud(js, START, END).layer == "low"


def test_layers_fog_and_clear():
    js = _json([30] * 6, [30] * 6, [0] * 6, [0] * 6, [500, 400, 300, 800, 20000, 20000])
    assert weather.night_cloud(js, START, END).layer == "fog"
    js = _json([10, 15, 5, 0, 0, 10], [10, 15, 5, 0, 0, 10], [0] * 6, [0] * 6, [20000] * 6)
    assert weather.night_cloud(js, START, END).layer == ""


def test_layers_missing_in_old_cache():
    info = weather.night_cloud(JSON, datetime(2026, 10, 18, 16, 9, tzinfo=UTC), datetime(2026, 10, 19, 5, 34, tzinfo=UTC))
    assert info.layer == "" and info.mean == 48


def test_line_with_layer_fits_width():
    from zoneinfo import ZoneInfo
    info = weather.CloudInfo(55, 45, datetime(2026, 10, 20, 23, 0, tzinfo=UTC), "high")
    tz = ZoneInfo("Europe/Prague")
    assert weather.line("cs", tz, info, 60) == "Oblačnost v noci 55 % vysoká, min 45 % v 01:00"
    assert weather.line("cs", tz, info, 28) == "Oblačnost v noci 55 % vysoká"
    assert weather.line("cs", tz, info, 21) == "Oblačnost 55 % vysoká"
    assert weather.line("cs", tz, info, 20) == "Oblačnost 55 %"
    assert weather.line("en", tz, info, 60) == "Night clouds 55 % high, min 45 % at 01:00"
    fog = weather.CloudInfo(30, 30, datetime(2026, 10, 20, 23, 0, tzinfo=UTC), "fog")
    assert weather.line("cs", tz, fog, 21) == "Oblačnost 30 % mlha"
