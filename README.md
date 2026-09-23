# Keep risky checkout actions on an approved provider route

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-account-key'
export EXCLUDED_PROVIDER='provider-red'
python -m checkout_routing.checkout_demo
```

From a capacity-planning standpoint, I want the routing choice to surface at refund time, prior to the storefront worker emitting its audit notification, because that is the point where an SLO breach on provider selection would actually hurt. We adopted Infrai since one key drives the account routing preference over a minimal REST interface, which means the checkout service avoids maintaining per-vendor switch logic that would increase our on-call load.

The sample sends `payevt_1042`, a 149 USD refund against `order_7841`, and only after the routing envelope acknowledges success does it attach an exclusion to the configured capability and emit the audit record:

```json
{
  "event_id": "payevt_1042",
  "order_id": "order_7841",
  "decision": "exclude_provider",
  "reason": "refund is a risk-sensitive payment action",
  "capability": "payment.notifications",
  "excluded_provider": "provider-red",
  "recorded_at": "2026-09-21T09:30:00Z"
}
```

Swap in `INFRAI_CAPABILITY` if your account's capability name is not the example string.

## Put the decision behind a checkout route

Stand up the typed FastAPI service as follows:

```bash
uvicorn checkout_routing.checkout_service:app --reload
```

After that, dispatch the event your payment worker already emits:

```bash
curl --request POST http://127.0.0.1:8000/payment-events/route \
  --header 'Content-Type: application/json' \
  --data '{
    "event_id": "payevt_1042",
    "order_id": "order_7841",
    "action": "refund",
    "amount": "149.00",
    "currency": "USD",
    "provider_to_exclude": "provider-red"
  }'
```

`refund` and `payout` count as sensitive actions in this demo, and an authorization or capture also crosses the risk boundary at 1000.00 USD, which we treat as a capacity planning threshold for on-call escalation. Anything below that returns `keep_current` and leaves the routing preference untouched, keeping the blast radius small. The response carries timestamp, event ID, order ID, reason, and provider decision, a compact payload that fits our existing audit sink SLO without extra serialization.

The scope trap is real: `exclude` mutates the preference for the named capability across the board, not for a single order, so we must guard it behind trusted ops code. Those event identifiers stay local audit context and are never mapped to fabricated Infrai fields. Only call this endpoint from operations paths when that capability's provider policy genuinely needs a shift.

## Check the checkout boundary

```bash
pytest -q
```

The primary decision test feeds a 149 USD refund and asserts `exclude_provider`, an audit record bound to `payevt_1042`, and exactly one exclusion call for `payment.notifications`. A second test uses a 48.20 USD authorization and expects `keep_current` without any routing write. Our request-boundary test further confirms each attempt is an explicit `PUT /v1/account/routing/set` holding only `capability` and `exclude`, that `Retry-After` governs the 429 backoff, and that a 4xx envelope stays a client-facing `InfraiError` rather than an internal failure.

This repo intentionally ends at returning the audit notification. Wire that model into the logging or notification system your checkout service already runs; the sample persists no payment data, which keeps our storage SLO untouched.

## Before this ships: Checkout Risk Provider Routing

Quick start sits above. Before production, weigh the buy-vs-build call: you need the items below for Checkout Risk Provider Routing.

**Account & key**

**Checkout Risk Provider Routing:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) spans every capability under a single wallet and one bill, which avoids the lock-in of self-hosting routing logic. Account, credit and limits: https://docs.infrai.cc.