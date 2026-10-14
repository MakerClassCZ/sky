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


def test_rockets_url_default_and_override():
    assert "thespacedevs.com" in config.load({}).rockets_url
    assert config.load({"SKY_ROCKETS_URL": "http://x"}).rockets_url == "http://x"


def test_rate_limit_default():
    assert config.load({}).rate_limit == 60
    assert config.load({"SKY_RATE_LIMIT": "0"}).rate_limit == 0


def test_comets_url():
    assert "minorplanetcenter" in config.load({}).comets_url
    assert config.load({"SKY_COMETS_URL": "http://x/c.txt"}).comets_url == "http://x/c.txt"
