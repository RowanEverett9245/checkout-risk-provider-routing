from __future__ import annotations

import os
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException

from .infrai_routing import InfraiError, InfraiRoutingClient, InfraiTransportError
from .risk_policy import AuditNotification, PaymentEvent, route_payment_event


app = FastAPI(title="Checkout risk routing")


async def routing_client() -> AsyncIterator[InfraiRoutingClient]:
    client = InfraiRoutingClient.from_environment()
    try:
        yield client
    finally:
        await client.close()


@app.post("/payment-events/route", response_model=AuditNotification)
async def apply_payment_routing(
    event: PaymentEvent,
    client: InfraiRoutingClient = Depends(routing_client),
) -> AuditNotification:
    capability = os.environ.get("INFRAI_CAPABILITY", "payment.notifications")
    try:
        return await route_payment_event(event, capability, client)
    except InfraiError as error:
        status = error.status_code if 400 <= error.status_code < 500 else 502
        raise HTTPException(
            status_code=status,
            detail={"code": error.code, "message": str(error)},
        ) from error
    except InfraiTransportError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

