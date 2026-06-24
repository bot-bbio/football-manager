"""Tests for the ESPN news/injury client against a mocked transport."""

from __future__ import annotations

import httpx
import pytest

from fantasy_assistant.news_client import ESPNClient, ESPNError

from .conftest import ESPN_INJURIES, ESPN_NEWS


def make_client(handler) -> ESPNClient:
    transport = httpx.MockTransport(handler)
    return ESPNClient(client=httpx.Client(transport=transport))


def test_get_news_hits_news_endpoint_with_limit():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=ESPN_NEWS)

    with make_client(handler) as client:
        data = client.get_news(limit=25)

    assert data["articles"][0]["headline"].startswith("Bijan Robinson")
    assert seen["url"].endswith("/news?limit=25")


def test_get_injuries_hits_injuries_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/injuries")
        return httpx.Response(200, json=ESPN_INJURIES)

    with make_client(handler) as client:
        data = client.get_injuries()

    assert len(data["injuries"]) == 2


def test_http_error_raises_espn_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    with make_client(handler) as client:
        with pytest.raises(ESPNError):
            client.get_news()


def test_not_found_raises_espn_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    with make_client(handler) as client:
        with pytest.raises(ESPNError):
            client.get_injuries()
