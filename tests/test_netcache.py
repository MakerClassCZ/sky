import os
import time

from sky import netcache


def _raise(exc):
    def _f(url, timeout):
        raise exc
    return _f


def test_fresh_cache_not_refetched(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("old", encoding="utf-8")
    monkeypatch.setattr(netcache, "_download", _raise(AssertionError("fetched")))
    assert netcache.fetch_text("http://x", p, 3600) == "old"


def test_stale_cache_refetched(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("old", encoding="utf-8")
    os.utime(p, (time.time() - 10_000, time.time() - 10_000))
    monkeypatch.setattr(netcache, "_download", lambda url, timeout: "new")
    assert netcache.fetch_text("http://x", p, 3600) == "new"
    assert p.read_text(encoding="utf-8") == "new"


def test_failure_returns_stale(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("old", encoding="utf-8")
    os.utime(p, (0, 0))
    monkeypatch.setattr(netcache, "_download", _raise(OSError("net")))
    assert netcache.fetch_text("http://x", p, 3600) == "old"


def test_failure_without_cache_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(netcache, "_download", _raise(OSError("net")))
    assert netcache.fetch_text("http://x", tmp_path / "none.txt", 3600) is None
