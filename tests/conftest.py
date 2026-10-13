"""Testy nikdy nesmí na síť: stažení selže a moduly použijí cache nebo „nedostupné“."""
import pytest

from sky import netcache

REAL_DOWNLOAD = netcache._download     # pro test limitu velikosti, který síť simuluje sám


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(url, timeout):
        raise OSError(f"síť je v testech vypnutá ({url[:40]})")
    monkeypatch.setattr(netcache, "_download", _blocked)
