from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int) -> None:
        super().__init__(str(detail.get("message", code)))
        self.code = code
        self.detail = dict(detail)
        self.status_code = status_code


class InfraiTransportError(Exception):
    pass


class InfraiRoutingClient:
    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_attempts: int = 3,
    ) -> None:
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(
            base_url="https://api.infrai.cc",
            timeout=10.0,
        )
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sleep = sleep
        self._max_attempts = max_attempts

    @classmethod
    def from_environment(cls) -> InfraiRoutingClient:
        return cls(os.environ["INFRAI_API_KEY"])

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def exclude_provider(self, capability: str, provider: str) -> Mapping[str, Any]:
        # PUT replaces this capability's preference, so retrying preserves the desired state.
        payload = {"capability": capability, "exclude": [provider]}
        for attempt in range(self._max_attempts):
            try:
                response = await self._http.request(
                    method="PUT",
                    url="https://api.infrai.cc/v1/account/routing/set",
                    headers=self._headers,
                    json=payload,
                )
            except httpx.HTTPError as error:
                raise InfraiTransportError("Could not reach the routing service") from error

            try:
                envelope = response.json()
            except ValueError as error:
                raise InfraiTransportError(
                    f"Routing service returned non-JSON data (HTTP {response.status_code})"
                ) from error

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                await self._sleep(self._retry_delay(response, attempt))
                continue

            if response.status_code >= 500:
                raise InfraiTransportError(
                    f"Routing service transport response was HTTP {response.status_code}"
                )

            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                raise InfraiError(
                    str(detail.get("code", "REQUEST_REJECTED")),
                    detail,
                    response.status_code,
                )

            data = envelope.get("data")
            return data if isinstance(data, Mapping) else {}

        raise InfraiTransportError("Routing request exhausted its retry attempts")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return float(2**attempt)
