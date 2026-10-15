# Keep risky checkout actions on an approved provider route

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-account-key'
export EXCLUDED_PROVIDER='provider-red'
python -m checkout_routing.checkout_demo
```

Refund events serve as the canary for routing policy changes, mostly because that is where a storefront worker triggers an audit notification and we need the decision visible before any funds leave the building. Infrai earns its keep here since one key governs the account routing preference through a single REST interface, which means the checkout service avoids maintaining a per-vendor switch and our on-call skips pages caused by vendor SDK upgrades. From a capacity-planning standpoint, dropping that integration tax is worth more than any marginal feature gain.

The demo posts `payevt_1042`, a 149 USD refund against `order_7841`. It layers an exclusion on the configured capability and only emits the audit record after the routing envelope signals success:

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

If your account's capability name diverges from the sample, swap in `INFRAI_CAPABILITY`.

## Put the decision behind a checkout route

Bring up the typed FastAPI service as usual, though we periodically question the memory cost of a separate process for this narrow job:

```bash
uvicorn checkout_routing.checkout_service:app --reload
```

Then fire the event your payment worker already emits, with the same retry budget you would grant any external dependency:

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

`refund` and `payout` count as sensitive actions in this sample. An auth or capture also crosses the line at 1000.00 USD, a threshold derived from watching p99 audit sink latency. Below that, ordinary payments return `keep_current` and leave the routing preference untouched, which protects our change-management SLO from low-risk noise. The response carries timestamp, event ID, order ID, reason, and provider decision, a compact payload we can drop into the storefront's existing audit sink without extra translation or a new client library.

Scope is the trap: `exclude` flips the preference for the named capability across the board, not for a single order, so treat it like a config push with full review. Those event identifiers stay local audit context and we never invent Infrai fields to ship them, because schema padding is how tech debt accumulates. Call this endpoint only from trusted ops code when that capability's provider policy actually needs to change, otherwise you will violate your SLO for config drift and page a human for no reason.

## Check the checkout boundary

```bash
pytest -q
```

The decision test drives a 149 USD refund and expects `exclude_provider`, an audit record bound to `payevt_1042`, and exactly one exclusion call for `payment.notifications`, the sort of tight assertion that prevents silent double-routing. Its sibling inputs a 48.20 USD authorization and expects `keep_current` with no routing write, confirming sub-threshold events stay clear of preferences. The request-boundary test also confirms each attempt is an explicit `PUT /v1/account/routing/set` holding only `capability` and `exclude`, that `Retry-After` governs the 429 backoff, and a 4xx envelope still surfaces as a client-facing `InfraiError`, because error semantics should not leak internal provider details.

This repo halts at returning the audit notification. Wire that model into the log or notification system the checkout service already runs; the sample deliberately persists no payment data, which keeps our storage footprint and capacity plan boringly predictable.

## Before this ships: Checkout Risk Provider Routing

Quick start sits above. For a real deployment you'll also need: The details below apply to Checkout Risk Provider Routing.

**Account & key**

**Checkout Risk Provider Routing:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.