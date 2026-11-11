# ResolveAI

Autonomous PayPal dispute resolution with a deterministic policy gate, human approval, and a
signed-plan executor. Built for the [PayPal AI Hackathon](https://paypalaihackathon.devpost.com/).

Four agents read one shared case file, argue both sides, and propose a remedy. A **deterministic
policy engine** - not the model - decides what may execute. Anything outside the envelope becomes a
human approval. Money only moves through a signed payment plan consumed by the executor.

**Mode:** `replay` by default (fixtures, zero credentials, refunds explicitly marked
`simulated`). `PAYPAL_MODE=sandbox` switches the same code path to the live PayPal REST API.

## Live demo

| | |
|---|---|
| **App** | `https://resolveai-web.onrender.com` *(replace after your Render deploy)* |
| **API health** | `https://resolveai-api.onrender.com/health/ready` |
| **Login** | `owner@northwind.example` / `resolveai-demo` |
| **Mode** | `replay` — refunds are **simulated (replay)**, no real money moves |

The public demo is provisioned from [`render.yaml`](render.yaml): Next.js web
service, FastAPI API service, and Render Postgres 16 with pgvector. The browser
only talks to the Next.js origin; `/api/v1` is proxied to the API, so the session
cookie is first-party. See [docs/13-deployment-render.md](docs/13-deployment-render.md)
for the full runbook.

> The deployment is prepared and locally verified. Creating the Render resources
> requires your Render account authorization — the exact steps are in docs/13.

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
| Render deployment (web + API + Postgres) | Blueprint, production Dockerfiles, migration-on-boot, smoke test prepared; create the resources with your Render account ([docs/13](docs/13-deployment-render.md)) |

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

### Deploy to Render

1. Push the repo to a **public GitHub repository**.
2. Render Dashboard → **New +** → **Blueprint** → select the repo.
3. Render reads [`render.yaml`](render.yaml) and creates:
   - `resolveai-web` — Next.js dashboard (Docker)
   - `resolveai-api` — FastAPI + LangGraph (Docker, runs Alembic on boot)
   - `resolveai-db` — Postgres 16 with pgvector
4. Paste `LLM_API_KEY` when prompted. PayPal sandbox values are optional for the
   replay-only demo.
5. After the first deploy, verify:

```bash
python scripts/verify_deployment.py \
  --web https://resolveai-web.onrender.com \
  --api https://resolveai-api.onrender.com \
  --seed
```

`APP_ENV=production` makes the API refuse to boot with missing/weak secrets.
Render generates `SECRET_KEY`, `CREDENTIAL_KEK`, `PII_HASH_PEPPER`, and
`PLAN_SIGNING_KEY` automatically. `DEMO_ENDPOINTS_ENABLED=true` keeps the
session-guarded seed/reset controls available for the public demo; set it to
`false` for a hardened deployment.

**PayPal sandbox webhook:** after creating the sandbox app, add
`https://<your-api-host>/api/v1/webhooks/paypal` in the PayPal Developer
Dashboard, copy the webhook ID to `PAYPAL_WEBHOOK_ID`, and set
`PAYPAL_MODE=sandbox`. Full steps and event types are in
[docs/13-deployment-render.md](docs/13-deployment-render.md#6-paypal-sandbox--webhook).

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
cd apps/api && uv run pytest -q          # 52 tests
cd apps/web && npm run typecheck && npm run build

# no credential in tracked files or git history
python scripts/check_secrets.py --history

# deployed stack: health, DB, policy, Next.js proxy, optional login + seed
python scripts/verify_deployment.py \
  --web https://resolveai-web.onrender.com \
  --api https://resolveai-api.onrender.com \
  --seed
```

Credential checks without exposing secrets:

```bash
cd apps/api && uv run python -m scripts.verify_credentials
```

It prints masked fingerprints, the OAuth result, the Disputes API response, and a real model reply.

Sandbox read path through the application adapter (no write endpoints):

```bash
cd apps/api
PAYPAL_MODE=sandbox uv run python -m scripts.verify_sandbox_adapter
```

## Honest limits

- Replay refunds are **simulated**. `live_paypal` stays `false` until `PAYPAL_MODE=sandbox` and a
  real refund has been executed.
- The sandbox end-to-end segment (filing real disputes, live refund) needs the manual steps tracked
  as M-03 / M-07 / M-08 in [docs/09](docs/09-manual-actions-checklist.md).
- Webhook signature verification is implemented; it is only meaningful in sandbox mode.
- The demo is single-operator with no auth. Production would put approvals behind SSO and RBAC.
- The free-tier Gemini key can return `503` under load. Runs then use the labelled deterministic
  fallback rather than retrying forever.

## Secrets and repository hygiene

- Only `.env.example` is committed. `.env`, `.env.*`, keys, PEM files, and local
  evidence are git-ignored.
- `python scripts/check_secrets.py --history` fails if a credential pattern or a
  value from `.env.local` appears in tracked files or git history.
- Render generates the four app-internal secrets (`SECRET_KEY`, `CREDENTIAL_KEK`,
  `PII_HASH_PEPPER`, `PLAN_SIGNING_KEY`) and stores them outside Git.
- PayPal and Gemini credentials are entered in the Render dashboard
  (`sync: false`), never in `render.yaml`.
- `APP_ENV=production` fails closed on missing or weak secrets, and on
  `PAYPAL_MODE=sandbox` without client credentials.
- The public demo account is intentionally known (`owner@northwind.example` /
  `resolveai-demo`) and runs in replay mode. It is not a production identity.

## Submission

- [docs/13-deployment-render.md](docs/13-deployment-render.md) — Render runbook,
  Postgres/pgvector, PayPal sandbox + webhook, verification, troubleshooting.
- [docs/11-demo-script.md](docs/11-demo-script.md) — three-minute video script.
- [docs/14-submission-checklist.md](docs/14-submission-checklist.md) — Devpost
  fields, final checks, screenshots, honest limits.
- [LICENSE](LICENSE) — MIT.

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
scripts/          verify_deployment.py, check_secrets.py
docs/             architecture, schema, API, agents, PayPal, security, operations,
                  Render deployment, demo script, submission checklist
fixtures/         replay PayPal payloads (3 scenarios)
render.yaml       Render Blueprint: web + API + Postgres
docker-compose.yml local Postgres + API + web
```

## Documentation

[docs/README.md](docs/README.md) is the index. Most relevant:
[docs/01 architecture](docs/01-system-architecture.md),
[docs/04 agents](docs/04-agents.md),
[docs/05 PayPal integration](docs/05-paypal-integration.md),
[docs/09 verification log](docs/09-manual-actions-checklist.md),
[docs/11 demo script](docs/11-demo-script.md),
[docs/13 Render deployment](docs/13-deployment-render.md),
[docs/14 submission checklist](docs/14-submission-checklist.md).

## License

MIT - see [LICENSE](LICENSE).
