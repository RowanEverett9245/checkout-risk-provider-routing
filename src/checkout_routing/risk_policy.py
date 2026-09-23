from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .infrai_routing import InfraiRoutingClient


class PaymentAction(str, Enum):
    AUTHORIZE = "authorize"
    CAPTURE = "capture"
    REFUND = "refund"
    PAYOUT = "payout"


class PaymentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    action: PaymentAction
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    provider_to_exclude: str = Field(min_length=1)


class AuditNotification(BaseModel):
    event_id: str
    order_id: str
    decision: Literal["keep_current", "exclude_provider"]
    reason: str
    capability: str
    excluded_provider: str | None
    recorded_at: datetime


SENSITIVE_ACTIONS = {PaymentAction.REFUND, PaymentAction.PAYOUT}
HIGH_VALUE_BOUNDARY = Decimal("1000.00")


def assess_payment(event: PaymentEvent, capability: str) -> AuditNotification:
    if event.action in SENSITIVE_ACTIONS:
        decision = "exclude_provider"
        reason = f"{event.action.value} is a risk-sensitive payment action"
    elif event.amount >= HIGH_VALUE_BOUNDARY:
        decision = "exclude_provider"
        reason = f"amount reached the {HIGH_VALUE_BOUNDARY} review boundary"
    else:
        decision = "keep_current"
        reason = "payment stayed below the routing review boundary"

    return AuditNotification(
        event_id=event.event_id,
        order_id=event.order_id,
        decision=decision,
        reason=reason,
        capability=capability,
        excluded_provider=(
            event.provider_to_exclude if decision == "exclude_provider" else None
        ),
        recorded_at=datetime.now(timezone.utc),
    )


async def route_payment_event(
    event: PaymentEvent,
    capability: str,
    client: InfraiRoutingClient,
) -> AuditNotification:
    notification = assess_payment(event, capability)
    if notification.decision == "exclude_provider":
        await client.exclude_provider(capability, event.provider_to_exclude)
    return notification

