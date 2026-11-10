# ResolveAI

Autonomous PayPal dispute resolution with a deterministic policy gate and a human approval step.
Built for the [PayPal AI Hackathon](https://paypalaihackathon.devpost.com/).

> **Current milestone: scaffold verified.** The frontend, API and database are wired together and
> prove it at runtime. PayPal ingestion and the four agents are the next milestone (see
> [docs/10](docs/10-hackathon-compliance-and-48h-plan.md)).

---

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 (App Router, TypeScript, Tailwind v4) — port `3000` |
| Backend | FastAPI + SQLAlchemy 2.0 async — port `8000` |
| Database | PostgreSQL 16 (Docker) — host port `55433` |
| Migrations | Alembic (async) |
| Orchestration | Docker Compose |

Nothing in the UI is mocked. The dashboard reads `/api/v1/system/status`, which queries Postgres on
every request; if the API is unreachable the page shows the error instead of falling back to numbers.

## Quickstart (Docker)

```bash
docker compose up --build
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health/ready

No credentials are required: `PAYPAL_MODE` defaults to `replay` and the schema is created by
`alembic upgrade head` on API start.

## Local development

Prerequisites: Python 3.12+, `uv`, Node 22+, Docker.

```bash
# 1. database
docker compose up -d db

# 2. secrets + config (git-ignored)
cp .env.example .env.local
python -c "import secrets;print(secrets.token_hex(32))"   # run 4x, fill SECRET_KEY, CREDENTIAL_KEK,
                                                          # PII_HASH_PEPPER, PLAN_SIGNING_KEY

# 3. backend
cd apps/api
uv sync
uv run alembic upgrade head
uv run pytest -q
uv run uvicorn app.main:app --reload --port 8000

# 4. frontend (new terminal)
cd apps/web
npm install
npm run dev
```

## Configuration

Every variable is documented in [`.env.example`](.env.example) and in
[docs/08-environment-variables.md](docs/08-environment-variables.md). Secrets live only in
`.env.local`, which is git-ignored (`git check-ignore -v .env.local`).

Groups: app/auth secrets · database · PayPal (`PAYPAL_MODE=replay|sandbox`) · LLM · autonomy caps ·
evidence storage · frontend (`NEXT_PUBLIC_*`).

## Verify it yourself

```bash
curl http://localhost:8000/health/ready
curl http://localhost:8000/api/v1/system/status
curl http://localhost:8000/api/v1/disputes
```

The status payload reports the measured DB latency, schema table count, row counts and the
environment capability flags (`paypal_credentials`, `live_paypal`, `agents`). Flags are computed from
the environment on every request; `live_paypal` only turns true when `PAYPAL_MODE=sandbox`, so the
replay-first default never overstates what is live.

Verify credentials without exposing them:

```bash
cd apps/api && uv run python -m scripts.verify_credentials
```

It prints masked fingerprints only (length + SHA-256 prefix), the OAuth result, the Disputes API
response, and a real model generation call.

## Layout

```
apps/api/app/
  api/v1/        system.py (status), disputes.py
  core/          config, logging, errors, middleware
  db/            base, session, models (18 tables)
  agents/policy/ deterministic rules engine + rules.yaml
  migrations/    Alembic
apps/web/src/
  app/           layout, page (server component), error boundary
  lib/api.ts     typed fetch, no fallbacks
  components/    client-only widgets
docs/            architecture, schema, API, agents, PayPal, security, plans
fixtures/        replay-mode PayPal payloads (3 demo scenarios)
```

## Design guardrails (already enforced in code)

- Agents will never call PayPal write endpoints; a deterministic gate issues the envelope.
- Every error returns one envelope `{error:{code,message,details,request_id,retryable}}`.
- Request ids are propagated to the client via `X-Request-ID` and included in logs.
- Money is `numeric(12,2)` + explicit currency, never floats.

## Roadmap

1. PayPal replay adapter + dispute ingestion (webhook + reconciliation).
2. LangGraph spine: Buyer · Merchant · Resolution · Payment agents.
3. Execution path: policy gate → signed plan → refund.
4. Dashboard: AG Grid, trace, approval dialog, audit dossier.

## License

MIT — see [LICENSE](LICENSE).
