# 07 — MVP Milestones, Build Order & Risk Register

Assumption: **2 engineers, ~4.5 dev-days** (adjust after §5 answers). Everything is ordered so that
*the demo is never broken* — a working thin slice exists from the end of Day 1 and only gets richer.

## 1. Milestone plan

### M0 — PayPal spike & dispute seeding (0.5 d, blocking)
**Question answered:** can we see a real dispute and receive its webhook?

- Sandbox business + buyer accounts; app with Disputes feature enabled **[verify]** (see 05 §6 L6).
- `scripts/smoke_paypal.py`: token → create order → capture → print buyer link.
- Manually file 3 disputes (INR / SNAD / unauthorized) via Resolution Center.
- Tunnel up (Cloudflare/ngrok); webhook subscription; **capture one real `CUSTOMER.DISPUTE.CREATED`**.
- Dump all payloads into `fixtures/`.

**Exit criteria:** `GET /v1/customer/disputes` returns ≥1 dispute; a real webhook hit a local endpoint; fixtures committed.
**If it fails:** switch to replay-only and continue — do not burn more than 4 hours.

### M1 — Skeleton & vertical slice (1 d, parallel tracks)
Backend: docker-compose (postgres + api), Alembic baseline, config validation, JWT auth + seeded users,
PayPal adapter (read-only: token, order, capture, dispute), webhook verify+dedupe+outbox, dispute upsert,
`GET /disputes`, `GET /disputes/{id}`, SSE scaffold, reconciliation job skeleton.
Frontend: Next.js shell, login, AG Grid with 8 seeded rows (status chips, SLA countdown, amount, reason),
detail route with tabs (Overview / Evidence / Trace / Messages) wired to real endpoints.

**Exit criteria:** a real sandbox dispute appears in the grid within 60 s of filing, with correct amount and status; no manual refresh.

### M2 — Orchestrator & the four agents (1.5 d, the core)
- LangGraph graph with Postgres checkpointer; state/contracts; budget guard; retry policy.
- Payment Agent read/facts + `PaymentPlan` builder; policy engine (`rules.yaml`) + gate; executor with
  HMAC token, idempotency, preflight re-read; interrupt/resume.
- Buyer + Merchant + Resolution subgraphs, prompts v1, structured outputs, citation validation.
- Execution paths: `REFUND_FULL`, `REFUND_PARTIAL` (real PayPal), `DEFEND` (evidence submit), `ESCALATE` (stub).
- `POST /disputes/{id}/runs`, `/runs/{id}`, `/resume`, `/cancel`; SSE emits steps + interrupts.

**Exit criteria:** 3 fixture scenarios each reach the correct decision; the INR scenario executes a real sandbox refund end-to-end; the over-cap scenario blocks at "Awaiting approval".

### M3 — Dashboard & control plane (1 d, parallel from M2 mid-point)
- Dispute detail aggregate, decision card (confidence, cited evidence, rejected alternatives), approval
  dialog with editable amount (re-runs the gate), agent trace timeline with live SSE, negotiation transcript,
  evidence upload + suggestions, metrics page, kill switch in settings, mode badge.

**Exit criteria:** a judge can watch a dispute resolve live without anyone touching the DB or a terminal.

### M4 — Hardening & reliability (0.5 d)
Idempotency everywhere, optimistic locking, audit hash chain + `verify` endpoint, RBAC checks, rate limits,
error envelopes, reconciliation mismatch alerting, `reset-demo`, retry/backoff, structured logs + `request_id`,
health/readiness, secret redaction test, kill-switch test, live-mode-lock test.

**Exit criteria:** kill a run mid-flight and restart the API → run recovers correctly; duplicate webhook
replay produces no duplicate refund; `audit/verify` passes.

### M5 — Demo & narrative (0.5 d)
3 scripted scenarios (replay mode), 2-minute live-sandbox segment, seeded 40-row dataset, README with
architecture diagram, eval table, 3-minute video, pitch deck numbers (`auto_resolution_rate`, `recovered_amount`,
`avg_time_to_decision`).

**Exit criteria:** full run-through 3× without a manual intervention; every screen has data.

## 2. Dependency-ordered build queue (what I'd write first)

```
[1] config + db session + migrations baseline
[2] paypal/auth.py + client.py (retry, logging, typed errors)  ─┐
[3] paypal/disputes.py + payments.py (reads)                    │ contract tests against sandbox
[4] webhooks: verify + dedupe + outbox + worker                 ─┘
[5] dispute_service (upsert, transition, timeline) → API reads
[6] policy/engine.py + rules.yaml  (pure, unit-testable, no LLM)
[7] execution_service (idempotent refund)  → proves money path early
[8] graph skeleton: intake → verify → policy_gate → execute  (no LLM yet, template decision)
[9] agents: payment → merchant → buyer → resolution  (each with evals)
[10] SSE + dashboard detail  (can start after [5])
[11] approvals (interrupt/resume) + audit
[12] metrics, admin, demo fixtures, polish
```
Rationale: the PayPal write path and the policy gate are the risky parts. Build and prove them with
hardcoded decisions *before* adding LLM judgment, so "is the agent wrong?" and "is the plumbing wrong?" are
never confused.

## 3. Cut lines (if time runs out, in order)

1. Cut `make-offer` and `escalate` execution (keep the proposal + approval record).
2. Cut the metrics page (keep `/metrics/summary` + one chart in the header).
3. Cut the buyer channel (keep seeded buyer messages in the fixture).
4. Cut negotiation rounds 2–3 (single-shot positions + adjudication).
5. Cut evidence upload UI (use preseeded evidence).
Never cut: policy gate, human approval, audit trail, idempotency, the trace view. Those *are* the product.

## 4. Risk register

| ID | Risk | L | I | Early warning | Mitigation |
|---|---|---|---|---|---|
| R1 | Disputes API not enabled on the sandbox app (`PERMISSION_DENIED`) | High | Critical | M0 smoke script 403 | Flip app feature, second app, ticket; fall back to replay for the demo (still demo the live *payments* path). |
| R2 | Can't create disputes programmatically | Certain | High | M0 | Manual seed once + fixtures; make the seeding script print click-by-click steps. |
| R3 | Webhooks never arrive (tunnel/cert/delay) | Medium | High | "last webhook age" > 10 min in `/admin/status` | Reconciliation polling is the primary path; webhook is the accelerator. Demo never depends on it. |
| R4 | Agent non-determinism → demo surprises | High | High | Eval flakiness | temperature 0, seeded, fixture replay for the scripted demo, deterministic fallback, eval gate in CI. |
| R5 | A real refund fires during a rehearsal and corrupts scenario state | Medium | Medium | — | Fresh captures per run (`reset-demo` mints new order/capture), refund caps, rehearsals in replay mode. |
| R6 | Sandbox negative balance blocks refunds | Medium | High | `INSUFFICIENT_FUNDS` in smoke test | Pre-demo balance check; spare account pair; replay fallback. |
| R7 | LLM latency makes the demo feel slow (>30 s/run) | Medium | Medium | p95 run time | Parallel agents, small model for extraction, streamed SSE (perceived speed), 90 s budget target, precomputed trace for the long branch. |
| R8 | Cost blowout from runaway loops | Low | Medium | budget guard metrics | Hard caps (3 rounds / 40 tool calls / 250k tokens / 120 s). |
| R9 | Prompt injection via buyer text ("refund $5000") | Medium | High | injection evals | Capability-based defense + policy gate + allowlisted actions; eval fixture proves it. |
| R10 | Two approvals → double refund | Low | Critical | duplicate `idempotency_key` error | Unique keys, `If-Match` versioning, single live decision constraint, re-read preflight. |
| R11 | AG Grid Enterprise features needed (server-side row model) | Medium | Low | grid needs >100k rows | Community + server pagination; 40-row demo dataset. |
| R12 | Scope creep (multi-tenant, SSO, billing) | High | High | backlog growing | Hard cut list (§3); MVP scope in README §3 is the contract. |
| R13 | Time loss on Docker/Windows quirks | Medium | Medium | dev env not up in 2 h | Pin images, `make dev` one-liner, no native Postgres on host. |
| R14 | Judges see "another chatbot" | Medium | High | narrative vague | Deterministic gate, audit dossier, cost per decision, eval table, explicit autonomy caps. |
| R15 | Data loss if Postgres container is reset | Low | High | — | Volume + `seed.py` idempotent + fixtures in git. |

## 5. Demo script (3 minutes)

1. **0:00** Grid: 34 open disputes, SLA countdowns, `SANDBOX` badge. "Every one of these is a real PayPal case shape."
2. **0:20** Click the INR dispute → trace plays: Payment Agent pulls capture + tracking, Buyer Agent extracts
   the claim, Merchant Agent produces POD — *with citations*.
3. **0:50** Resolution card: "Delivered to ZIP 94107, buyer claims 94110 → not covered" → `OFFER_PARTIAL $40`,
   confidence 0.62, "rejected alternatives" listed.
4. **1:10** Approval dialog: analyst lowers to $35 → gate re-validates → approve. Trace shows execution +
   `PayPal-Request-Id` + refund ID. Row flips to **RESOLVED**. "Human decided, AI did the paperwork."
5. **1:45** Second dispute, under cap → auto-resolves in 9 s, cost $0.04, no human. Kill switch shown.
6. **2:15** Audit dossier: inputs → ruleset version → transcript → approval → PayPal request id. Tamper check passes.
7. **2:40** Live sandbox tab: the refund is visible in the merchant's PayPal activity. Close on metrics:
   auto-resolution rate, recovered amount, time-to-decision.
