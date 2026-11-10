# 01 — System Architecture

## 1. Context

```
                    ┌──────────────────────────────────────────────┐
  PayPal sandbox    │  Buyers (simulated / seeded)                 │
  ┌──────────────┐  │  Merchant ops / risk analyst (human)         │
  │ Orders v2    │  └───────────────┬──────────────────────────────┘
  │ Payments v2  │                  │ HTTPS (Next.js dashboard)
  │ Disputes v1  │                  ▼
  │ Webhooks     │        ┌────────────────────┐
  └──────┬───────┘        │  apps/web          │  Next.js 15 App Router
         │ webhook/HTTPS  │  AG Grid, SSE      │
         ▼                └─────────┬──────────┘
  ┌─────────────────────────────────┼──────────────────────────────┐
  │  Cloudflare Tunnel / ngrok      │  REST /api/v1  +  SSE        │
  │                                 ▼                              │
  │  ┌──────────────────────────────────────────────────────────┐  │
  │  │  apps/api  (FastAPI, async)                              │  │
  │  │  Routers → Services → Repositories → Postgres            │  │
  │  │         ↘ Orchestrator (LangGraph)                        │  │
  │  │              Buyer · Merchant · Resolution · Payment      │  │
  │  │         ↘ Policy engine (deterministic)                   │  │
  │  │         ↘ PayPal adapter (live | replay)                  │  │
  │  └──────────────────────────────────────────────────────────┘  │
  │            │ Postgres 16 (+pgvector)      │ Redis (optional)   │
  └────────────┼──────────────────────────────┼────────────────────┘
               │                              │
        durable state, checkpoints,     rate limit, SSE fan-out,
        audit log, outbox              job queue (only if needed)
```

**Why one API service and not microservices:** a hackathon needs one `docker compose up`. The API is
internally modular (routers / services / repositories / agents / integrations) so the seams are real,
but the deployment is a single container plus Postgres.

## 2. Component responsibilities

| Component | Owns | Must NOT do |
|---|---|---|
| `apps/web` (Next.js) | Merchant dashboard, AG Grid dispute explorer, dispute detail, agent trace, approval UI, metrics | Talk to PayPal; hold PayPal secrets; compute policy |
| `apps/api` HTTP layer | Authn/z, validation, tenant scoping, idempotency, SSE, OpenAPI | Contain agent reasoning logic |
| `services/dispute_service` | Case lifecycle, state transitions, timeline writes | Call the LLM |
| `services/orchestrator` | Start/resume/cancel LangGraph runs, map run events → DB + SSE | Make business decisions itself |
| `agents/*` (LangGraph) | Reasoning, evidence planning, proposals, rationale | Execute money movement; bypass policy |
| `agents/policy` | Deterministic eligibility + envelope + approval requirement | Use an LLM |
| `integrations/paypal` | OAuth, retries, idempotency, typed models, webhook verification | Contain business policy |
| `outbox` + worker | Reliable webhook processing, reconciliation, notifications | — |
| Postgres | Source of truth for cases, runs, audit | Store raw PayPal secrets |

## 3. Folder structure

```
Paypal_hackathon_AI/
├── apps/
│   ├── api/                                  # FastAPI
│   │   ├── app/
│   │   │   ├── main.py                       # app factory, router mounting, lifespan
│   │   │   ├── api/
│   │   │   │   ├── deps.py                   # db session, current_user, merchant scope
│   │   │   │   └── v1/
│   │   │   │       ├── auth.py  disputes.py  runs.py  evidence.py
│   │   │   │       ├── payments.py  webhooks.py  metrics.py
│   │   │   │       ├── buyer.py              # simulated buyer channel
│   │   │   │       └── admin.py              # kill switch, replay, seed
│   │   │   ├── core/
│   │   │   │   ├── config.py                 # pydantic-settings, env validation
│   │   │   │   ├── security.py               # JWT, password hashing, RBAC
│   │   │   │   ├── crypto.py                 # envelope encryption for creds
│   │   │   │   ├── logging.py  errors.py  idempotency.py  ratelimit.py
│   │   │   │   └── observability.py          # OTel traces, token/cost accounting
│   │   │   ├── db/
│   │   │   │   ├── session.py  base.py
│   │   │   │   ├── models/                   # SQLAlchemy 2.0 ORM
│   │   │   │   └── repositories/             # dispute, run, evidence, audit
│   │   │   ├── schemas/                      # Pydantic request/response DTOs
│   │   │   ├── services/
│   │   │   │   ├── dispute_service.py  evidence_service.py
│   │   │   │   ├── orchestrator.py           # LangGraph entrypoints
│   │   │   │   ├── execution_service.py      # approved action → PayPal call
│   │   │   │   ├── reconciliation.py         # poll PayPal for missed webhooks
│   │   │   │   ├── notification_service.py
│   │   │   │   └── outbox.py
│   │   │   ├── agents/
│   │   │   │   ├── state.py                  # DisputeState TypedDict + reducers
│   │   │   │   ├── contracts.py              # AgentEnvelope, Finding, Proposal
│   │   │   │   ├── graph.py                  # topology, checkpointer, interrupt
│   │   │   │   ├── routing.py  budgets.py    # conditional edges, loop/cost limits
│   │   │   │   ├── nodes/                    # ingest, verify, plan, gate, execute, notify
│   │   │   │   ├── subgraphs/                # buyer.py merchant.py resolution.py payment.py
│   │   │   │   ├── tools/                    # paypal_read.py paypal_write.py
│   │   │   │   │                             # evidence.py policy_lookup.py notify.py
│   │   │   │   ├── policy/engine.py + rules.yaml + thresholds.py
│   │   │   │   └── prompts/                  # versioned .md prompts (one per agent)
│   │   │   └── integrations/paypal/
│   │   │       ├── client.py  auth.py  models.py
│   │   │       ├── disputes.py  payments.py  orders.py
│   │   │       ├── webhooks.py                # verify + map event → domain
│   │   │       └── replay.py                  # fixture-backed adapter
│   │   ├── migrations/                        # Alembic
│   │   ├── tests/  (unit · integration · contract · evals)
│   │   ├── pyproject.toml   Dockerfile
│   ├── web/                                   # Next.js 15, TS, App Router
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── (dashboard)/disputes/page.tsx
│   │   │   │   ├── (dashboard)/disputes/[id]/page.tsx
│   │   │   │   ├── (dashboard)/metrics/page.tsx
│   │   │   │   ├── (dashboard)/settings/page.tsx
│   │   │   │   └── (auth)/login/page.tsx
│   │   │   ├── components/
│   │   │   │   ├── grid/DisputeGrid.tsx  grid/cellRenderers.tsx
│   │   │   │   ├── dispute/{Timeline,AgentTrace,EvidencePanel,DecisionCard}.tsx
│   │   │   │   ├── approval/ApprovalDialog.tsx
│   │   │   │   └── ui/                        # shadcn/ui primitives
│   │   │   ├── lib/{api-client.ts, sse.ts, auth.ts, format.ts}
│   │   │   └── types/api.d.ts                 # generated from OpenAPI
│   │   ├── next.config.ts  tailwind.config.ts  package.json  Dockerfile
├── packages/
│   └── contracts/                             # openapi.json (exported), fixtures schema notes
├── fixtures/
│   ├── disputes/                              # replay-mode PayPal payloads
│   ├── webhooks/                              # recorded CUSTOMER.DISPUTE.* events
│   └── demo/                                  # 3 scripted scenarios
├── scripts/
│   ├── seed.py  smoke_paypal.py  replay.py  tunnel.ps1  export_openapi.py
├── infra/
│   ├── docker-compose.yml  Dockerfile.api  Dockerfile.web  init.sql
├── docs/                                      # this design set
├── .env.example  Makefile  README.md
```

Conventions: Python 3.12 + `uv`, SQLAlchemy 2.0 async, Pydantic v2 everywhere, `ruff`+`mypy`.
TypeScript strict, TanStack Query for server state, no client-side secret.

## 4. Dispute lifecycle state machine (internal)

PayPal's statuses are too coarse; we keep our own and mirror PayPal's.

```
 RECEIVED ──▶ TRIAGED ──▶ INVESTIGATING ──▶ NEGOTIATING ──┬─▶ DECIDED
    │            │                                       │
    │            └─▶ OUT_OF_SCOPE (auto-close, notify)   ├─▶ AWAITING_APPROVAL ─▶ DECIDED
    │                                                    │
    └─▶ DUPLICATE / IGNORED                              └─▶ ESCALATE_TO_PAYPAL ─▶ AWAITING_PAYPAL
                                                                          │
 DECIDED ──▶ EXECUTING ──▶ RESOLVED | PARTIALLY_RESOLVED | FAILED ──▶ (retry | human)
```

Rules:
- Transitions are **guarded** in `dispute_service.transition(dispute, to, actor, reason)`; illegal transitions raise `409 STATE_CONFLICT`. All transitions write `dispute_status_history` + `audit_log`.
- Terminal states: `RESOLVED`, `PARTIALLY_RESOLVED`, `OUT_OF_SCOPE`, `FAILED_PERMANENT`.
- `version` column + `If-Match` on the approval endpoint prevents double-spend from two browser tabs.
- PayPal-originated changes (`CUSTOMER.DISPUTE.RESOLVED`) always win over internal state: they force a transition and cancel in-flight runs.

## 5. LangGraph topology

```
            ┌──────────────┐
   START ──▶│ intake_router│  (intent: new_dispute | buyer_message | status_query)
            └──────┬───────┘
                   ▼
            ┌──────────────┐   read-only PayPal facts (order, capture, dispute, tracking)
            │  verify_facts│──▶ missing facts → request_info / pause
            └──────┬───────┘
                   ▼
            ┌──────────────┐   deterministic rules → eligibility, envelope, reason code
            │  policy_scan │
            └──────┬───────┘
                   ▼
            ┌──────────────┐   fan-out (LangGraph Send)
            │ evidence_plan│───────────────┬───────────────┐
            └──────┬───────┘               ▼               ▼
                   │              ┌────────────────┐ ┌──────────────────┐
                   │              │ buyer_agent    │ │ merchant_agent   │
                   │              │ claim + remedy │ │ defense + policy │
                   │              └───────┬────────┘ └────────┬─────────┘
                   │                      └──────┬────────────┘
                   ▼                             ▼
            ┌──────────────────────────────────────────┐
            │ resolution_agent  (judge/mediator)       │  ≤3 negotiation rounds
            │ findings → decision + confidence + cites │  then forced decision
            └──────┬───────────────────────────────────┘
                   ▼
            ┌──────────────┐  deterministic gate: allowed action? amount cap?
            │ policy_gate  │  approval needed? → interrupt() → resume
            └──────┬───────┘
                   ▼
            ┌──────────────┐  payment_agent proposes; executor calls PayPal
            │  execute     │  (accept-claim | provide-evidence | make-offer | refund)
            └──────┬───────┘
                   ▼
            ┌──────────────┐
            │ notify + END │  dashboard SSE, audit, metrics
            └──────────────┘
```

Implementation notes:
- **Checkpointer:** `AsyncPostgresSaver` (`langgraph-checkpoint-postgres`) keyed by `thread_id = dispute.id`. Run rows reference `thread_id` + `checkpoint_id` so the UI can resume or replay.
- **HITL:** the gate node calls `interrupt({...approval_payload})`. The API exposes `POST /runs/{id}/resume` with the human verdict; the graph continues from the checkpoint. Notifications fire *before* the interrupt so the UI shows the pending approval.
- **Budgets:** every node increments `state.budget` (tokens, tool calls, wall clock). `routing.py` has a `budget_guard` edge that forces `decision` or `escalate` when exceeded. Hard caps: 3 negotiation rounds, 40 tool calls, 120s wall clock per run, 250k tokens.
- **Retries:** node-level `RetryPolicy` on transient tool errors; agent-level fallback to a cheaper model on schema-validation failure, then to a deterministic template (never a crash).
- **Determinism:** `temperature=0` for extraction/decision nodes; `seed` recorded in `agent_runs` for replay.
- **Structured output:** every agent returns a Pydantic `AgentEnvelope` via function/tool calling with a JSON schema; free-form text is only allowed in `rationale` and is truncated to 2k chars before storage.
- **No cross-agent tool sharing:** each subgraph has its own allowlist (see 04 §3). The Buyer agent physically cannot call `refund`.

## 6. Request/data flow: happy path (INR, auto-refund under threshold)

```
PayPal ──CUSTOMER.DISPUTE.CREATED──▶ POST /webhooks/paypal
  → verify signature (cert + CRC) → 202 in <300ms → insert webhook_deliveries (unique event_id)
  → outbox row → worker: map to dispute, upsert, transition RECEIVED→TRIAGED
  → enqueue run → orchestrator starts graph (thread_id = dispute.id)
  → SSE event: dispute.created  → AG Grid row appears (live)
graph: verify_facts (Payment Agent read: order $80, capture settled, tracking "delivered") 
  → policy_scan: reason=INR, tracking confirms delivery, seller protection eligible, amount < $100 cap
  → buyer_agent: extracts claim, confirms "not received" (confidence .86)
  → merchant_agent: assembles POD (carrier + tracking + delivery scan), argues no refund
  → resolution_agent: conflict → confidence .62 → strategy = OFFER_PARTIAL (50%) or REFUND
  → policy_gate: action=REFUND $80 → exceeds auto cap? no → allowed, approval not required
  → execute: POST /v2/payments/captures/{id}/refund (Idempotency-Key = run_id:step)
  → PayPal 201 → dispute status → RESOLVED, refund_id stored
  → notify: SSE + audit + metrics (recovered/time-to-resolve)
```

## 7. Reliability patterns

| Pattern | Where | Note |
|---|---|---|
| Webhook fast-ack + outbox | `webhooks.py` → `outbox_events` | PayPal retries non-2xx for days; never do work inline. |
| Dedupe | `webhook_deliveries.event_id` unique | PayPal delivers at-least-once. |
| Idempotent writes | `Idempotency-Key` on all PayPal POSTs, stored in `tool_invocations` | Replay of a run must not double-refund. |
| Reconciliation | worker every 5 min: `GET /v1/customer/disputes?status=...` diff vs DB | Catches missed webhooks — essential for demos. |
| Optimistic locking | `disputes.version`, `If-Match` | Two analysts approving simultaneously. |
| Circuit breaker | PayPal adapter (5 failures → open 30s) | Sandbox flakiness. |
| Kill switch | `AUTONOMY_ENABLED=false` env + admin endpoint | Stops all execution instantly, keeps reads. |
| Run recovery | On API boot, mark `RUNNING` runs older than 10 min as `INTERRUPTED`, offer retry | Container restarts mid-graph. |

## 8. Mode matrix

| Mode | `PAYPAL_MODE` | LLM | Use |
|---|---|---|---|
| `sandbox` | live sandbox API | real model | M0 spike, integration tests, final demo if stable |
| `replay` | fixtures under `fixtures/` | real model | Default demo path, offline dev, CI |
| `mock` | in-memory fake | stubbed | Unit tests, no network |

The adapter is selected at startup by config; the frontend shows the active mode in the header
(`SANDBOX` / `REPLAY`) so judges always know what they're seeing.
