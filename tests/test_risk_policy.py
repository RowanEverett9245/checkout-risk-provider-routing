import asyncio
from decimal import Decimal

from checkout_routing.risk_policy import (
    PaymentAction,
    PaymentEvent,
    route_payment_event,
)


class RecordingRoutingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def exclude_provider(self, capability: str, provider: str) -> dict[str, str]:
        self.calls.append((capability, provider))
        return {"capability": capability, "exclude": provider}


def payment_event(*, action: PaymentAction, amount: str) -> PaymentEvent:
    return PaymentEvent(
        event_id="payevt_1042",
        order_id="order_7841",
        action=action,
        amount=Decimal(amount),
        currency="USD",
        provider_to_exclude="provider-red",
    )


def test_refund_excludes_provider_and_records_audit_decision() -> None:
    client = RecordingRoutingClient()

    notification = asyncio.run(
        route_payment_event(
            payment_event(action=PaymentAction.REFUND, amount="149.00"),
            "payment.notifications",
            client,  # type: ignore[arg-type]
        )
    )

    assert notification.decision == "exclude_provider"
    assert notification.event_id == "payevt_1042"
    assert notification.excluded_provider == "provider-red"
    assert client.calls == [("payment.notifications", "provider-red")]


def test_small_authorization_keeps_current_route() -> None:
    client = RecordingRoutingClient()

    notification = asyncio.run(
        route_payment_event(
            payment_event(action=PaymentAction.AUTHORIZE, amount="48.20"),
            "payment.notifications",
            client,  # type: ignore[arg-type]
        )
    )

    assert notification.decision == "keep_current"
    assert notification.excluded_provider is None
    assert client.calls == []
