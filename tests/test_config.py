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
