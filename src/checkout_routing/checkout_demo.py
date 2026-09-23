from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal

from .infrai_routing import InfraiRoutingClient
from .risk_policy import PaymentAction, PaymentEvent, route_payment_event


async def run() -> None:
    event = PaymentEvent(
        event_id="payevt_1042",
        order_id="order_7841",
        action=PaymentAction.REFUND,
        amount=Decimal("149.00"),
        currency="USD",
        provider_to_exclude=os.environ["EXCLUDED_PROVIDER"],
    )
    capability = os.environ.get("INFRAI_CAPABILITY", "payment.notifications")
    client = InfraiRoutingClient.from_environment()
    try:
        notification = await route_payment_event(event, capability, client)
    finally:
        await client.close()
    print(json.dumps(notification.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(run())

