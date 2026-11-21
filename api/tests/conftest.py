"""Keep every API test off the network: Open-Meteo calls without an injected client fail fast (wind -> config
default; fire weather -> no cap)."""
import httpx
import pytest

from api import fwi, weather


def _offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("network disabled in tests", request=request)


@pytest.fixture(autouse=True)
def no_network_weather(monkeypatch):
    for mod in (weather, fwi):
        monkeypatch.setattr(mod, "_make_client",
                            lambda timeout_s: httpx.AsyncClient(transport=httpx.MockTransport(_offline)))
        mod._cache.clear()
    yield
    weather._cache.clear()
    fwi._cache.clear()
