# ResolveAI

Autonomous PayPal dispute resolution with a deterministic policy gate, human approval, and a
signed-plan executor. Built for the [PayPal AI Hackathon](https://paypalaihackathon.devpost.com/).

Four agents read one shared case file, argue both sides, and propose a remedy. A **deterministic
policy engine** - not the model - decides what may execute. Anything outside the envelope becomes a
human approval. Money only moves through a signed payment plan consumed by the executor.

**Mode:** `replay` by default (fixtures, zero credentials, refunds explicitly marked
`simulated`). `PAYPAL_MODE=sandbox` switches the same code path to the live PayPal REST API.

---

## What works end-to-end today

| Capability | Status |
|---|---|
| Dispute ingestion (adapter, idempotent upsert, message dedupe) | working - replay fixtures |
| LangGraph spine: Buyer + Merchant in parallel -> Resolution -> policy gate -> Payment | working |
| Deterministic policy envelope, evaluated twice, with matched-rule evidence | working |
| Signed plan + idempotent executor + hash-chained audit log | working |
| Postgres-backed approvals (approve / reject survives restarts) | working |
| AG Grid 36 dashboard (infinite row model, server pagination) + case file + agent transcript | working |
| Replay refunds | working, `simulated=true` in API and UI |
| Live PayPal sandbox refund / webhook | adapter implemented; execution pending sandbox disputes (see [docs/09](docs/09-manual-actions-checklist.md)) |

Verified claims and exact commands are logged in
[docs/09-manual-actions-checklist.md](docs/09-manual-actions-checklist.md) (V1-V31). Nothing here is
marked working unless that log shows the check that passed.

## Demo outcomes (replay)

`uv run python -m scripts.seed && uv run python -m scripts.run_demo`

| Case | Reason | Agent outcome | Money |
|---|---|---|---|
| PP-D-91001 | Item not received | `REFUND_FULL` $40.00, confidence 0.90, policy `allow` | executed autonomously (simulated refund) |
| PP-D-91002 | Not as described | `REFUND_PARTIAL` / `REFUND_FULL` inside the band, policy `require_approval` | waits for a human; approving executes exactly one refund |
| PP-D-91003 | Unauthorised | `DEFEND`, confidence 0.62, fraud reason | never auto-paid; no plan, no refund row |

Agent choices vary slightly between runs because the LLM adjudicates inside the envelope. The
envelope itself - caps, bands, fraud rules, approval requirements - never varies.

## Quickstart

### Docker (recommended)

```bash
docker compose up --build
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health/ready

Then seed the three demo disputes from the dashboard (`seed`) or:

```bash
cd apps/api
uv run python -m scripts.seed
uv run python -m scripts.run_demo          # runs every unresolved dispute
```

No credentials are required. `PAYPAL_MODE` defaults to `replay`; the schema is applied by
`alembic upgrade head` on API start.

### Local development

Prerequisites: Python 3.12+, `uv`, Node 22+, Docker.

```bash
docker compose up -d db

cp .env.example .env.local
python -c "import secrets;print(secrets.token_hex(32))"   # run 4x for SECRET_KEY,
                                                          # CREDENTIAL_KEK, PII_HASH_PEPPER,
                                                          # PLAN_SIGNING_KEY

cd apps/api
uv sync
uv run alembic upgrade head
uv run pytest -q
uv run uvicorn app.main:app --reload --port 8000

# new terminal
cd apps/web
npm install
npm run dev
```

Add `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `LLM_API_KEY` to `.env.local` for real model calls
and the sandbox adapter. Secrets are git-ignored; `.env.example` documents every variable.

## Architecture

```
PayPal (replay fixtures | sandbox REST)
        |
        v
  adapter -> ingestion -> Postgres (disputes, orders, captures, messages, runs, steps, ...)
                              |
                              v
        LangGraph:  Buyer  ||  Merchant        (parallel, no anchoring)
                         \   /
                      Resolution                (may only pick from the envelope)
                          |
                 deterministic policy gate      (allow | require_approval | deny)
                    |                    |
                 allow                approval
                    |                    |
              signed payment plan -> Postgres approval row -> human
                    |                    |
                    +-------> executor <--+
                                  |
                     PayPal refund (or replay receipt) + audit log
```

Key invariants, enforced in code:

- Agents never call PayPal write endpoints. They emit a `PaymentPlan`; `execution_service` verifies
  the HMAC signature and is the only writer.
- The policy envelope is computed with a provisional confidence to constrain Resolution, then again
  with the real confidence to decide allow / approve / deny.
- Refunds are idempotent on a stable key; re-approving returns `409` and never pays twice.
- Every LLM step has a deterministic fallback that is labelled `fallback` in the run trace. It is
  never presented as model output.
- Replay receipts carry `simulated=true`, surfaced as **simulated (replay)** in the UI.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15.5 (App Router, TypeScript, Tailwind v4), AG Grid Community 36.3 |
| Backend | FastAPI, SQLAlchemy 2.0 async, Pydantic v2 |
| Agents | LangGraph 1.x, Gemini 3.5 Flash / Flash-Lite with deterministic fallbacks |
| Database | PostgreSQL 16 (Docker), Alembic migrations (19 tables) |
| Platform | Docker Compose |

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/system/status` | live DB latency, counts, capability flags |
| GET | `/api/v1/policy/rules` | exact ruleset the gate uses (no UI duplication) |
| GET | `/api/v1/disputes` | filters, search, sorting, pagination |
| GET | `/api/v1/disputes/{id}` | case file, transcript, decision, policy, approvals, receipts |
| POST | `/api/v1/disputes/{id}/run` | run the four-agent graph |
| GET | `/api/v1/runs/{id}` | ordered steps + typed agent messages |
| GET | `/api/v1/approvals` | pending / decided approvals |
| POST | `/api/v1/approvals/{id}/decide` | approve (execute plan) or reject |
| GET | `/api/v1/metrics` | exposure, recovered, auto vs human, medians |
| POST | `/api/v1/webhooks/paypal` | signature-verified webhook intake (live path) |
| POST | `/api/v1/demo/seed` / `reset` | demo helpers (disabled when `APP_ENV=production`) |

Errors use one envelope: `{error:{code,message,details,request_id,retryable}}`, with the same
`request_id` as the `X-Request-ID` response header.

## Verify it yourself

```bash
curl http://localhost:8000/health/ready
curl http://localhost:8000/api/v1/system/status
curl http://localhost:8000/api/v1/metrics
cd apps/api && uv run pytest -q          # 19 tests
cd apps/web && npx tsc --noEmit && npm run build
```

Credential checks without exposing secrets:

```bash
cd apps/api && uv run python -m scripts.verify_credentials
```

It prints masked fingerprints, the OAuth result, the Disputes API response, and a real model reply.

## Honest limits

- Replay refunds are **simulated**. `live_paypal` stays `false` until `PAYPAL_MODE=sandbox` and a
  real refund has been executed.
- The sandbox end-to-end segment (filing real disputes, live refund) needs the manual steps tracked
  as M-03 / M-07 / M-08 in [docs/09](docs/09-manual-actions-checklist.md).
- Webhook signature verification is implemented; it is only meaningful in sandbox mode.
- The demo is single-operator with no auth. Production would put approvals behind SSO and RBAC.
- The free-tier Gemini key can return `503` under load. Runs then use the labelled deterministic
  fallback rather than retrying forever.

## Layout

```
apps/api/app/
  agents/         contracts, llm client, LangGraph nodes/graph, policy engine + rules.yaml
  api/v1/         system, policy, disputes, runs, approvals, metrics, webhooks, demo
  core/           config, logging, errors, middleware, security (HMAC, PII hashing)
  db/             models (19 tables), session, base
  paypal/         base Protocol, replay adapter, sandbox adapter, factory
  services/       ingestion, orchestrator, execution, audit
apps/api/scripts/ seed, run_demo, verify_credentials
apps/web/src/
  app/            dashboard + /disputes/[id] case file
  components/     AG Grid, actions, demo controls, UI primitives
  lib/api.ts      typed client, no fabricated fallbacks
docs/             architecture, schema, API, agents, PayPal, security, operations
fixtures/         replay PayPal payloads (3 scenarios)
```

## Documentation

[docs/README.md](docs/README.md) is the index. Most relevant:
[docs/01 architecture](docs/01-system-architecture.md),
[docs/04 agents](docs/04-agents.md),
[docs/05 PayPal integration](docs/05-paypal-integration.md),
[docs/09 verification log](docs/09-manual-actions-checklist.md).

## License

MIT - see [LICENSE](LICENSE).
