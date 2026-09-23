from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from checkout_routing.infrai_routing import InfraiError, InfraiRoutingClient


def test_routing_request_retries_429_and_keeps_exact_body() -> None:
    requests: list[httpx.Request] = []
    delays: list[float] = []

    async def no_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={
                    "ok": False,
                    "data": None,
                    "error": {"code": "RATE_LIMITED", "message": "Retry later"},
                    "metadata": {},
                },
            )
        return httpx.Response(
            200,
            json={
                "ok": True,
                "data": {"updated": True},
                "error": None,
                "metadata": {},
            },
        )

    async def exercise() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = InfraiRoutingClient("test-key", http=http, sleep=no_sleep)
            return dict(
                await client.exclude_provider(
                    "payment.notifications", "provider-red"
                )
            )

    result = asyncio.run(exercise())

    assert result == {"updated": True}
    assert delays == [2.0]
    assert [request.method for request in requests] == ["PUT", "PUT"]
    assert all(request.url.path == "/v1/account/routing/set" for request in requests)
    assert json.loads(requests[0].content) == {
        "capability": "payment.notifications",
        "exclude": ["provider-red"],
    }
    assert requests[0].headers["Authorization"] == "Bearer test-key"


def test_business_rejection_surfaces_envelope_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "ok": False,
                "data": None,
                "error": {"code": "INVALID_ARGUMENT", "message": "Check capability"},
                "metadata": {},
            },
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = InfraiRoutingClient("test-key", http=http)
            await client.exclude_provider("payment.notifications", "provider-red")

    with pytest.raises(InfraiError) as caught:
        asyncio.run(exercise())

    assert caught.value.status_code == 400
    assert caught.value.code == "INVALID_ARGUMENT"
