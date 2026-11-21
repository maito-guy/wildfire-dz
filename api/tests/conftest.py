"""Keep every API test off the network: Open-Meteo calls without an injected client fail fast (-> config default)."""
import httpx
import pytest

from api import weather


def _offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("network disabled in tests", request=request)


@pytest.fixture(autouse=True)
def no_firms_key(monkeypatch):
    """A FIRMS_MAP_KEY in .env must not start the live FIRMS loop in tests (#61). An empty env var wins over .env."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "")


@pytest.fixture(autouse=True)
def no_network_weather(monkeypatch):
    monkeypatch.setattr(weather, "_make_client",
                        lambda timeout_s: httpx.AsyncClient(transport=httpx.MockTransport(_offline)))
    weather._cache.clear()
    yield
    weather._cache.clear()
