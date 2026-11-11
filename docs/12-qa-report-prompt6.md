# Prompt 6 - End-to-End QA Report

**Date:** 2026-11-11  
**Scope:** ResolveAI workflow, payment lifecycle, failure paths, webhook handling, authorization, dashboard and audit history.  
**Environment:** local Docker stack (`web:3000`, `api:8000`, PostgreSQL `55433`), demo merchant, Gemini models, `PAYPAL_MODE=replay`, `ALLOW_LIVE_PAYPAL=false`, `PAYPAL_WEBHOOK_ID` empty.

## Verdict

| Area | Result |
|---|---|
| Full replay workflow (intake -> agents -> approval -> refund -> dashboard/audit) | **PASS** |
| Negative and failure-path tests | **PASS** |
| Merchant authorization on money-moving and mutating routes | **PASS after fix** |
| Frontend typecheck and production build | **PASS** |
| Live PayPal sandbox order creation | **PASS** |
| Live PayPal sandbox capture | **BLOCKED** - buyer approval required |
| Live PayPal sandbox refund | **BLOCKED** - no captured sandbox payment |
| Live PayPal refund verification | **BLOCKED** - no live sandbox refund exists |
| Live signed webhook delivery | **BLOCKED** - no public HTTPS URL / webhook id |
| Buyer-facing complaint submission endpoint | **NOT IMPLEMENTED** - intake is via PayPal sync/replay fixtures |

No live capture, refund, signed webhook, or deployment success is claimed. Replay refunds remain explicitly marked `simulated=true` in the API, UI, metrics, and audit data.

## Commands and results

| Check | Command | Result |
|---|---|---|
| Backend unit/integration tests | `uv run pytest -q` | **52 passed** |
| Lint on changed backend files | `uv run ruff check ...` | **passed** |
| Frontend types | `npm run typecheck` | **passed** |
| Frontend production build | `npm run build` | **passed** |
| Live workflow QA harness | `uv run python -m scripts.qa_workflow` | **70 passed, 0 failed** |
| Sandbox order creation | `PAYPAL_MODE=sandbox uv run python -m scripts.create_sandbox_orders` | **3 orders created** |
| Sandbox capture attempt | `PAYPAL_MODE=sandbox uv run python -m scripts.capture_sandbox_orders` | **blocked: `PAYER_ACTION_REQUIRED`** |
| Sandbox order status | `PAYPAL_MODE=sandbox uv run python -m scripts.sandbox_status` | **3/3 `PAYER_ACTION_REQUIRED`, payer not approved** |
| UI route smoke | authenticated requests to `/`, `/cases`, `/complaints`, `/analytics`, `/knowledge`, `/cases/{id}` | **all HTTP 200** |
| Unauthenticated UI redirect | `GET /` without cookie | **307 -> `/login?next=%2F`** |

The QA harness is committed at `apps/api/scripts/qa_workflow.py`. It resets and reseeds the replay dataset, so it is reproducible and destructive to local demo data.

## Workflow test matrix

| # | Workflow step | Result | Evidence |
|---|---|---|---|
| 1 | Create a PayPal sandbox payment/order | **PASS (order creation)** | Three real sandbox Orders v2 calls returned order ids and `PAYER_ACTION_REQUIRED`. No capture/payment is claimed. |
| 2 | Capture the payment | **BLOCKED (live)** / **PASS (replay)** | Live capture refused because all three orders were `PAYER_ACTION_REQUIRED`, not `APPROVED`. Replay order -> capture -> capture-read passed; duplicate capture reused the same `REPLAY-CAP-...` id. |
| 3 | Submit a customer complaint | **PASS (PayPal/replay intake)** | Seed/sync ingested `PP-D-91001`, `PP-D-91002`, `PP-D-91003` with messages and transaction facts. A direct buyer-facing complaint-submit API is **not implemented**. |
| 4 | Retrieve merchant evidence | **PASS** | Run trace contains retrieval, order/capture/tracking evidence, and 6 pgvector policy citations per case. |
| 5 | Execute the LangGraph workflow | **PASS** | `POST /api/v1/disputes/{id}/run` completed for all three scenarios; trace nodes include `buyer_intake`, `buyer`, `merchant`, `knowledge_retrieval`, `resolution`, `policy_gate`, `payment`. |
| 6 | Generate a resolution recommendation | **PASS** | `PP-D-91001`: `REFUND_FULL $40`; `PP-D-91002`: `OFFER_PARTIAL $50`, approval required; `PP-D-91003`: `ESCALATE`, no money movement. |
| 7 | Obtain merchant approval | **PASS** | `POST /api/v1/approvals/{id}/decide` approved the pending SNAD approval. The audit row attributes the action to the signed-in `merchant_users` id. Duplicate approval returned 409. |
| 8 | Execute the PayPal sandbox refund | **BLOCKED (live)** / **PASS (simulated replay)** | Replay approval and autonomous INR path each produced exactly one `REPLAY-RF-...` refund with `simulated=true`. No live refund is claimed. |
| 9 | Verify the refund with PayPal | **BLOCKED (live)** | No live captured payment/refund exists, so PayPal refund verification could not be performed. Replay receipts are deterministic; the executor skips live verification when `simulated=true` and labels the step accordingly. |
| 10 | Update dashboard and audit history | **PASS** | Metrics moved to `resolved=1`, `awaiting_approval=1`, `escalated=1`, `recovered=$40`; analytics reported `simulated=1`, `live=0`; audit actions included `approval.requested`, `approval.approved`, `decision.executed`, and `refund.executed`. |

## Failure and negative tests

| Test | Result | Evidence |
|---|---|---|
| Invalid dispute id | **PASS** | Unknown UUID -> 404; malformed UUID -> 422. |
| Invalid order id | **PASS** | Unknown order -> 404. |
| Invalid capture id | **PASS** | Unknown capture -> 404. |
| Invalid refund id | **PASS** | Unknown refund -> 404. |
| Invalid approval id | **PASS** | Unknown approval -> 404. |
| Duplicate refund request | **PASS** | Duplicate approval -> 409; re-running the same signed plan at the executor boundary returned the existing refund and did not create a second row. |
| Duplicate capture | **PASS** | Same capture id returned; no second capture. |
| Missing evidence | **PASS** | Synthetic case with no order/capture/tracking stopped at `run=NEEDS_INFO`, `dispute=AWAITING_INFO`, **zero refunds**. |
| Agent/graph failure | **PASS** | Forced graph exception produced `run=FAILED`, `error_code=GRAPH_ERROR`; the dispute's prior status was restored. |
| Webhook malformed JSON | **PASS** | HTTP 400 `INVALID_PAYLOAD`. |
| Webhook invalid signature in sandbox mode | **PASS** | HTTP 400 `INVALID_SIGNATURE` at the route boundary. |
| Duplicate webhook | **PASS** | First delivery stored, second returned `duplicate`; no double processing. |
| Webhook processing failure | **PASS** | Forced malformed event was persisted as `status=failed` with `last_error` set; it was not silently swallowed. |
| Replay webhook signature truthfulness | **PASS** | Stored with `signature_valid=false`; the API does not claim a PayPal signature was verified. |
| Unauthorized refund attempt | **PASS** | `POST /approvals/{id}/decide` without a session returned 401 and the case still had zero refunds. |
| Unauthorized seed/reset/run/payment/knowledge mutations | **PASS** | All returned 401. |
| Wrong password / forged / expired session | **PASS** | 401 in each case. |
| Resolved case re-run | **PASS** | 409. |

## Critical bugs found and fixed

### 1. Money-moving and mutating APIs were unauthenticated

**Severity:** Critical.  
Any caller who could reach the API could run agents, approve a pending refund, create/capture orders, seed/reset the database, or trigger knowledge ingestion without a merchant session.

**Fix:**
- Added `require_session` / `CurrentUserDep` in `apps/api/app/api/deps.py`, backed by the signed `resolveai_session` cookie and an active `merchant_users` row.
- Protected agent runs and case messages, approval decisions, all payment routes, demo seed/reset, and knowledge ingest/search.
- Verified every unauthenticated mutation returns **401**, while authenticated UI/API actions still work.

### 2. Approval audit did not use the signed-in merchant user

**Severity:** High (audit integrity).  
The approval route previously passed `user_id=None` and used an optional `X-Operator` header, so an approval was attributed to a request header or `demo-operator` instead of the authenticated user.

**Fix:**
- The approval route now passes the authenticated `MerchantUser.id` into `decide_approval`.
- Verified the audit row has `actor_type=human` and a non-empty `actor_id`.

## Test additions

- `apps/api/tests/test_auth_and_webhook_guards.py` covers missing/forged/expired sessions, malformed webhook JSON, and sandbox signature rejection.
- `apps/api/scripts/qa_workflow.py` is the live 70-check workflow/failure harness.

## Residual risks and explicitly unverified items

1. **Live sandbox buyer approval is still missing.** The created orders require a personal sandbox buyer to open the PayPal checkout link. Without those credentials, capture, refund, and refund verification cannot be honestly marked passing.
2. **No live signed webhook was delivered.** `PAYPAL_WEBHOOK_ID` is empty and there is no public HTTPS tunnel, so only route-boundary signature rejection, replay storage/dedupe, and forced processing failure were verified.
3. **Read-only merchant endpoints remain unauthenticated.** Mutating and money-moving routes are now protected, but `/api/v1/disputes`, `/api/v1/complaints`, `/api/v1/metrics`, `/api/v1/approvals`, `/api/v1/runs`, and knowledge reads still allow direct reads without a cookie. This is a data-confidentiality hardening item, not a money-movement bypass. The server-rendered dashboard currently calls these reads without forwarding the browser cookie.
4. **No buyer-facing complaint submission UI/API.** Complaint intake is through PayPal sync/replay fixtures. The demo does not pretend there is a buyer portal.
5. **Full-repo Ruff still reports pre-existing broad-`except` warnings** in unrelated service/script files; all changed and new files pass Ruff.

## Final local state

After the QA run, the documented replay demo state was restored with `scripts.run_demo`:

- `PP-D-91001` - `RESOLVED`, `REFUND_FULL $40.00`, one simulated refund `REPLAY-RF-0613F0079945`
- `PP-D-91002` - `AWAITING_APPROVAL`, `OFFER_PARTIAL $50.00`
- `PP-D-91003` - `ESCALATED`, `ESCALATE $0.00`, no refund

Metrics: `resolved=1`, `awaiting_approval=1`, `escalated=1`, `recovered=$40.00`, `simulated refunds=1`, `live refunds=0`.
