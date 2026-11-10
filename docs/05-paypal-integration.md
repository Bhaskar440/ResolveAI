# 05 — PayPal Integration

Everything in this document is **sandbox-first**. Items marked **[verify]** must be confirmed in the
developer dashboard on Day 0 — they are the known sources of wasted hackathon hours.

## 1. Environments & credentials

| | Sandbox | Live |
|---|---|---|
| Base URL | `https://api-m.sandbox.paypal.com` | `https://api-m.paypal.com` |
| Webhook cert host | `api.sandbox.paypal.com` | `api.paypal.com` |
| Credentials | App client_id/secret from a **sandbox** app | Live app (out of scope) |

Two sandbox account types are needed: **business (merchant)** and **personal (buyer)**.
`PAYPAL_MODE=sandbox` is enforced at boot; `PAYPAL_MODE=live` additionally requires
`ALLOW_LIVE_PAYPAL=true` **and** appears in an allowlist of environment names. The app refuses to start
with live credentials unless both are set (fails loudly, logged as a security event).

## 2. Authentication

Client-credentials OAuth2, cached in memory per worker.

```
POST /v1/oauth2/token
Authorization: Basic base64(client_id:secret)
Content-Type: application/x-www-form-urlencoded
grant_type=client_credentials            (optionally: &response_type=client_token for JS SDK, not needed)
→ { access_token, token_type: "Bearer", expires_in: 32400, app_id }
```
Rules: refresh when `now > issued_at + expires_in - 300s`; single-flight lock so 20 concurrent requests
produce one token call; on `401` invalidate and retry **once**; token never leaves the process (never in a
response body, never in logs, never in the DB).

## 3. Capability matrix (what we actually call)

| Capability | Method & path | Agent use | Write | Notes |
|---|---|---|---|---|
| Create order (demo checkout) | `POST /v2/checkout/orders` | seed script | ✓ | Used to generate demo transactions. |
| Capture order | `POST /v2/checkout/orders/{id}/capture` | seed script | ✓ | Creates the capture we later refund. |
| Order details | `GET /v2/checkout/orders/{id}` | Payment (read) | — | Amount, items, payer. |
| Capture details | `GET /v2/payments/captures/{id}` | Payment (read) | — | `seller_protection`, `dispute_ids`, `status`. |
| Refund capture | `POST /v2/payments/captures/{id}/refund` | via executor | ✓ | Partial allowed; multiple partials until capture amount. |
| Refund status | `GET /v2/payments/refunds/{id}` | Payment (verify) | — | Post-execution verification. |
| List disputes | `GET /v1/customer/disputes` | reconciliation | — | Paginated; filter by state/date. |
| Dispute details | `GET /v1/customer/disputes/{id}` | all agents (read) | — | Source of truth for status/reason/deadline/messages. |
| Accept claim | `POST /v1/customer/disputes/{id}/accept-claim` | Resolution→exec | ✓ | Full refund of disputed amount. |
| Make offer | `POST /v1/customer/disputes/{id}/make-offer` | Resolution→exec | ✓ | Buyer must accept; can sit for days. |
| Provide evidence | `POST /v1/customer/disputes/{id}/provide-evidence` | Resolution→exec | ✓ | `multipart/form-data`, evidence type + files. |
| Send message | `POST /v1/customer/disputes/{id}/send-message` | merchant thread | ✓ | Buyer-visible text. |
| Escalate to claim | `POST /v1/customer/disputes/{id}/escalate` | Resolution→exec | ✓ | Moves inquiry → chargeback. |
| Grant external refund | `POST /v1/customer/disputes/{id}/grant-external-refund` | executor | ✓ | **After** refunding via Payments API, tell PayPal. |
| Update dispute status | `POST /v1/customer/disputes/{id}/update-dispute-status` | executor | ✓ | **[verify]** availability/permissions. |
| Webhook subscribe | `POST /v1/notifications/webhooks` | setup script | ✓ | One-time; store `webhook_id`. |
| Webhook verify | `POST /v1/notifications/verify-webhook-signature` | webhook handler | ✓ (idempotent) | Network call on every event. |

**Hard rule:** agents get only `GET` tools. All ✓ write rows are reachable **exclusively** through
`execution_service` with a signed `PaymentPlan` + gate approval token.

## 4. Flows

### 4.1 Read / fact verification
```
1. token (cached)
2. GET /v1/customer/disputes/{id}       → status, reason, lifecycle stage, amount, respond_by, messages
3. GET /v1/customer/disputes/{id}?  (disputed_transactions) → capture/order ids
4. GET /v2/payments/captures/{capture}  → seller_protection, status, refundable amount
5. GET /v2/checkout/orders/{order}      → items, shipping, payer country
6. retry policy: 429/5xx → 2 retries, jitter; 4xx (non-401) → typed domain error, no retry
7. every call recorded in tool_invocations (status, latency, request id, result digest)
```
Cached for 60s per dispute to keep a 4-agent run inside rate limits; cache invalidated on webhook.

### 4.2 Refund (the most common write)
```
gate → approval_token
execution_service:
  1. re-read capture (final preflight — never trust a 5-minute-old snapshot)
  2. compute refundable = capture.amount - sum(completed refunds)
  3. assert plan.amount <= refundable && plan.amount == approved_amount
  4. POST /v2/payments/captures/{cap}/refund
       PayPal-Request-Id: {idempotency_key}          ← native idempotency
       { amount:{currency_code, value}, note_to_payer, invoice_id }
  5. store refund row + tool_invocation; update dispute → RESOLVED (partial if amount < disputed)
  6. POST /v1/customer/disputes/{id}/grant-external-refund   { refund_ids:[...] }   [verify shape]
  7. GET /v2/payments/refunds/{id} → verify COMPLETED (poll 3× with backoff for PENDING)
  8. reconcile: re-read dispute status; if still OPEN → schedule follow-up, notify
```
Failure handling: duplicate `PayPal-Request-Id` → PayPal returns the original result (treat as success);
`INSUFFICIENT_FUNDS`/negative balance → mark `FAILED`, alert human (sandbox accounts go negative easily);
`CAPTURE_FULLY_REFUNDED` → reconcile, close as superseded.

### 4.3 Provide evidence
```
1. resolve evidence_files → presigned or local reads
2. multipart POST /v1/customer/disputes/{id}/provide-evidence
     evidence_type=PROOF_OF_FULFILLMENT|PROOF_OF_DELIVERY_SIGNATURE|TRACKING_INFO|RECEIPT|OTHER  [verify enum]
     notes=<grounded summary, ≤ 2000 chars>
     file_1..n=<binary>
3. 200/204 → store evidence_submission row, mark files "submitted" (immutable thereafter)
4. 422 (bad evidence type for reason code) → surface to human with PayPal's message (do not retry blindly)
```
Limits/pitfalls: multipart size and file-type restrictions apply; evidence types are **reason-code
dependent**; the sandbox validates less strictly than production, so never assume "accepted" == "winnable".

### 4.4 Make offer vs. refund-then-grant
Two distinct strategies, chosen by the Resolution Agent:
- **`OFFER_PARTIAL`** → `make-offer` (no money moves until the buyer accepts; slow, buyer-dependent).
- **`REFUND_PARTIAL`** → refund via Payments API then `grant-external-refund` (immediate, deterministic, better for demos).
MVP default: `REFUND_*` for demo reliability; `make-offer` implemented but used only when amount is large
and the merchant wants buyer acceptance.

## 5. Webhooks

Subscription events (minimum): `CUSTOMER.DISPUTE.CREATED`, `CUSTOMER.DISPUTE.UPDATED`, `CUSTOMER.DISPUTE.RESOLVED`,
`CUSTOMER.DISPUTE.ESCALATED`, `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.REFUNDED`, `PAYMENT.CAPTURE.DENIED`.
`CUSTOMER.DISPUTE.APPEAL.*` **[verify]** availability in sandbox.

Handler:
```
POST /webhooks/paypal
 1. read RAW body (no middleware mutation — FastAPI: await request.body() before parsing)
 2. headers: PAYPAL-TRANSMISSION-ID, -TIME, -SIG, PAYPAL-CERT-URL, PAYPAL-AUTH-ALGO
 3. reject if |now - transmission_time| > 5 min            (replay window)
 4. verify via POST /v1/notifications/verify-webhook-signature (cache cert-derived result per transmission_id)
 5. dedupe: UNIQUE (provider, event_id)  → duplicates return 200 immediately
 6. insert webhook_deliveries(status=received) + outbox row
 7. return 200 in <300ms — never process inline
worker: map event → dispute upsert / status transition / run trigger; failures retried (max 8, exponential)
```
Signature verification **must** be on (except in `replay` mode, where it is skipped and explicitly flagged).
If PayPal's verify endpoint is down, policy = accept-and-flag (`signature_valid=false`, needs reconciliation)
rather than drop events, and alert.

## 6. Sandbox limitations & enablement checklist

Run this on Day 0, before any UI work. Each failure here costs the most hours.

| # | Limitation | Impact | Mitigation |
|---|---|---|---|
| L1 | **No API to create a dispute** — a buyer must file via the Resolution Center; there is no public "create dispute" endpoint. | Can't seed disputes programmatically. | Documented manual seed path (§7) + fixture replay. Confirm in dashboard whether a dispute testing tool is exposed **[verify]**. |
| L2 | Dispute **state timers are compressed/unrealistic**; `respond_by` may be hours away. | Runs may be forced to decide with thin evidence; deadlines can look absurd in the UI. | Deadline-aware routing; display real dates; don't hardcode SLA assumptions. |
| L3 | `make-offer` requires **buyer acceptance**, which does not happen automatically. | Offers sit in `WAITING_FOR_BUYER_RESPONSE` for the whole demo. | Prefer `REFUND_*` in the demo; accept-offer only in a narrated branch. |
| L4 | **Webhooks are delayed or occasionally dropped** in sandbox. | Dashboard appears "stuck". | Reconciliation poll every 5 min + `POST /disputes/{id}/sync` + manual refresh button. |
| L5 | **No public HTTPS → no webhook delivery.** | Silent failure on localhost. | Cloudflare Tunnel/ngrok with a stable domain; verify with the dashboard simulator on Day 0. |
| L6 | **Disputes feature/scope may not be enabled** on the app; calls can return `PERMISSION_DENIED`. | Whole integration blocked. | Enable "Disputes" in app features; if still 403, open a ticket immediately and switch to replay mode for the demo. Surface it in `scripts/smoke_paypal.py`. |
| L7 | **Seller protection often `NOT_ELIGIBLE`/unknown** for sandbox transactions. | Merchant Agent's best argument is untrustworthy. | Treat as `UNKNOWN` → policy fallback (never auto-decide on protection assumption). |
| L8 | Sandbox **balances go negative**; further captures/refunds fail. | Demo breaks mid-pitch. | Fresh buyer/seller sandbox accounts, top-up via "Add funds" sandbox tool, and a pre-demo balance check in `smoke_paypal.py`. |
| L9 | Evidence upload validates files/types **more loosely** than production. | Overconfidence in the "evidence accepted" path. | Log PayPal's exact response; never claim a win, only "submitted". |
| L10 | **Reason-code coverage is incomplete** (unauthorised/chargeback flows need specific funding instruments). | The "fraud" scenario may be unreproducible. | Make the fraud scenario a fixture/replay scenario; don't promise live sandbox for it. |
| L11 | Sandbox data can be **reset or rate-limited**; accounts lock after repeated failed logins. | Sudden 401s. | Token auto-refresh already; keep a second app + accounts; never script buyer logins repeatedly. |
| L12 | **No sandbox for arbitration/appeals** outcome timelines. | Can't demo the appeal flow. | Out of MVP scope; show as roadmap. |
| L13 | Idempotency (`PayPal-Request-Id`) **support varies per endpoint** **[verify]**. | Double refund risk on retry. | Our own `idempotency_key` unique constraint + preflight re-read; treat PayPal idempotency as a bonus. |

## 7. Seeding a real sandbox dispute (manual, ~10 min, script-assisted)

1. Create sandbox business + personal accounts; note logins (from dashboard, not from code).
2. `scripts/smoke_paypal.py` → creates order + capture as the business account (amounts $25 / $80 / $140),
   prints order IDs and a **buyer checkout link**.
3. Log in to `sandbox.paypal.com` as the buyer, pay via the link (this is where the buyer's funding source
   matters for `UNAUTHORISED` scenarios).
4. As the buyer, open **Resolution Center → Report a problem** on that transaction; choose the reason
   (item not received / not as described); submit.
5. Confirm the dispute appears via `GET /v1/customer/disputes` and that `CUSTOMER.DISPUTE.CREATED` hit our
   tunnel. **If step 5 fails, stop and fix before writing UI code.**
6. Record the payloads into `fixtures/disputes/` for replay mode.

Repeat for the 3 demo scenarios. Budget: 30–45 min total, once. Everything after that uses fixtures.

## 8. Replay adapter (why it matters)

`integrations/paypal/replay.py` implements the identical client interface against `fixtures/`:
recorded dispute JSON, capture JSON, refund responses, and a scripted state progression
(`CREATED → UPDATED → RESOLVED`) emitted on a timer by the fixture driver. Result: the demo is
deterministic, offline, fast, and identical in the UI (badge shows `REPLAY`). Live sandbox is then used only
to prove the integration is real — one extra 2-minute segment in the pitch.

## 9. Reconciliation job

Every 5 minutes: list disputes updated since `last_synced_at - 10 min` from PayPal, diff against DB,
apply missing transitions, and re-trigger stranded runs (`RUNNING` > 10 min, `AWAITING_APPROVAL` past
expiry). Emits `reconciliation.mismatch` metrics — a nice "production-grade" talking point.
