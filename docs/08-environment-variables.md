# 08 — Environment Variables

`.env.example` is committed with dummy values; `.env.local` is git-ignored. `app/core/config.py`
(Pydantic Settings) validates on boot and **refuses to start** on missing required vars, default
placeholders, or an unsafe combination (e.g. `live` without `ALLOW_LIVE_PAYPAL`).

Legend: **R** = required, **S** = secret (generate with `openssl rand -hex 32`), **O** = optional.

## App

| Var | Req | Default | Notes |
|---|---|---|---|
| `APP_ENV` | R | `local` | `local` \| `demo` \| `staging` \| `production`. Gates debug routes. |
| `APP_NAME` | O | `ResolveAI` | |
| `API_BASE_URL` | R | `http://localhost:8000` | Used for building links + OpenAPI servers. |
| `WEB_BASE_URL` | R | `http://localhost:3000` | CORS origin, email links. |
| `API_PORT` | O | `8000` | |
| `LOG_LEVEL` | O | `INFO` | `DEBUG` in dev only. |
| `LOG_FORMAT` | O | `json` | `json` \| `pretty`. |
| `TIMEZONE` | O | `UTC` | Display only; storage is always UTC. |
| `SECRET_KEY` | R **S** | — | JWT signing. Boot fails if it equals the example value. |
| `ACCESS_TOKEN_TTL_MINUTES` | O | `30` | |
| `REFRESH_TOKEN_TTL_DAYS` | O | `7` | |
| `CREDENTIAL_KEK` | R **S** | — | KEK for envelope-encrypting PayPal client secrets. Rotating it requires re-encryption. |
| `PII_HASH_PEPPER` | R **S** | — | For `buyer_email_hash`. Changing it invalidates buyer matching (acceptable in demo). |
| `PLAN_SIGNING_KEY` | R **S** | — | HMAC key for `PaymentPlan` execution tokens. |
| `CORS_ORIGINS` | O | `http://localhost:3000` | Comma-separated, no wildcards with credentials. Not needed when the browser uses the Next.js proxy. |
| `AUTH_COOKIE_SECURE` | O | `false` | Set `true` behind HTTPS (always true when `APP_ENV=production`). |
| `AUTH_COOKIE_SAMESITE` | O | `lax` | `lax` \| `strict` \| `none`. `none` requires HTTPS and is only needed for cross-site API origins. |
| `RATE_LIMIT_ENABLED` | O | `true` | |
| `RATE_LIMIT_REDIS_URL` | O | — | If empty, in-memory limiter (single instance only). |

## Database

| Var | Req | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | R | `postgresql+asyncpg://resolveai:resolveai@db:5432/resolveai` | Async driver. `postgres://` / `postgresql://` and `?sslmode=require` from Render/Heroku are normalized on boot. |
| `DB_POOL_SIZE` | O | `5` | Keep small on Render free Postgres. |
| `DB_MAX_OVERFLOW` | O | `5` | |
| `DB_POOL_RECYCLE_SECONDS` | O | `300` | Recycle before managed-provider idle timeouts. |
| `DB_ECHO` | O | `false` | |
| `PGVECTOR_ENABLED` | O | `false` | Documents intent; the migration enables the `vector` extension on Render. |

## PayPal

| Var | Req | Default | Notes |
|---|---|---|---|
| `PAYPAL_MODE` | R | `replay` | `sandbox` \| `replay` \| `mock`. **Fail-closed default is `replay`.** |
| `PAYPAL_BASE_URL` | O | `https://api-m.sandbox.paypal.com` | Must match `PAYPAL_MODE`. |
| `PAYPAL_CLIENT_ID` | R (sandbox) | — | Sandbox app. Not secret, but not public either. |
| `PAYPAL_CLIENT_SECRET` | R **S** (sandbox) | — | |
| `PAYPAL_WEBHOOK_ID` | R (sandbox) | — | From the webhook subscription; needed for signature verification. |
| `PAYPAL_WEBHOOK_VERIFY` | O | `true` | Skipped only in `replay`/`mock`. |
| `PAYPAL_WEBHOOK_MAX_SKEW_SECONDS` | O | `300` | Replay-window check. |
| `PAYPAL_TIMEOUT_SECONDS` | O | `15` | Per request. |
| `PAYPAL_MAX_RETRIES` | O | `2` | 429/5xx only, jittered backoff. |
| `PAYPAL_TOKEN_REFRESH_SKEW` | O | `300` | Refresh this many seconds before expiry. |
| `PAYPAL_REQUEST_ID_PREFIX` | O | `resolveai` | For `PayPal-Request-Id`. |
| `ALLOW_LIVE_PAYPAL` | O | `false` | Second key required for live mode. |
| `PAYPAL_MERCHANT_ID` | O | — | Sandbox business account payer id (for display/assertions). |
| `PAYPAL_SELLER_EMAIL` | O | — | Smoke-test assertions only. |
| `PAYPAL_FIXTURES_DIR` | O | `fixtures` | Replay mode data. |
| `PAYPAL_REPLAY_SPEED` | O | `1.0` | `2.0` = fixtures progress twice as fast (demo pacing). |
| `PAYPAL_RECONCILE_INTERVAL_SECONDS` | O | `300` | 0 disables. |

## LLM / Agents

| Var | Req | Default | Notes |
|---|---|---|---|
| `LLM_PROVIDER` | R | `openai` | `openai` \| `anthropic` \| `google` \| `openrouter`. |
| `LLM_API_KEY` | R **S** | — | |
| `LLM_BASE_URL` | O | provider default | For gateways/local models. |
| `LLM_MODEL_FAST` | O | `gpt-4.1-mini` | Extraction, classification, routing. |
| `LLM_MODEL_REASONING` | O | `gpt-4.1` | Merchant/Resolution adjudication. |
| `LLM_TEMPERATURE` | O | `0` | |
| `LLM_MAX_OUTPUT_TOKENS` | O | `1600` | |
| `LLM_TIMEOUT_SECONDS` | O | `60` | |
| `LLM_MAX_RETRIES` | O | `2` | Schema-repair retries. |
| `LLM_FALLBACK_PROVIDER` | O | — | Optional second provider on outage. |
| `LLM_TRACING_ENABLED` | O | `false` | Langfuse/LangSmith wiring. |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | O **S** | — | If tracing on. |
| `AGENT_MAX_NEGOTIATION_ROUNDS` | O | `3` | Hard cap. |
| `AGENT_MAX_TOOL_CALLS` | O | `40` | Per run. |
| `AGENT_MAX_WALL_CLOCK_SECONDS` | O | `120` | Per run. |
| `AGENT_MAX_TOKENS_PER_RUN` | O | `250000` | |
| `AGENT_GRAPH_VERSION` | O | `v1` | Recorded on every run. |

## Autonomy / policy

| Var | Req | Default | Notes |
|---|---|---|---|
| `AUTONOMY_ENABLED` | R | `true` | Global kill switch at boot; runtime override via admin API. |
| `AUTO_RESOLVE_CAP_USD` | O | `50` | Merchant row overrides; this is the default seed. |
| `AUTO_OFFER_CAP_USD` | O | `100` | |
| `APPROVAL_EXPIRY_MINUTES` | O | `120` | Pending approvals expire → human queue. |
| `AUTO_APPROVE_CONFIDENCE` | O | `0.80` | Below → human. |
| `ESCALATE_CONFIDENCE` | O | `0.55` | Below → no auto action. |
| `POLICY_RULESET_PATH` | O | `app/agents/policy/rules.yaml` | Versioned rules. |
| `POLICY_RULESET_VERSION` | O | `2026.11.1` | Stamped into evaluations. |
| `FRAUD_REASONS_REQUIRE_APPROVAL` | O | `UNAUTHORISED,DUPLICATE_TRANSACTION` | Comma list. |

## Storage / evidence

| Var | Req | Default | Notes |
|---|---|---|---|
| `STORAGE_BACKEND` | O | `local` | `local` \| `s3`. |
| `STORAGE_LOCAL_DIR` | O | `./var/evidence` | Git-ignored. |
| `S3_ENDPOINT_URL` / `S3_BUCKET` / `S3_REGION` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | O **S** | — | Required when `STORAGE_BACKEND=s3`. |
| `MAX_EVIDENCE_MB` | O | `10` | |
| `SIGNED_URL_TTL_SECONDS` | O | `300` | |

## Frontend (Next.js — only `NEXT_PUBLIC_*` reaches the browser)

| Var | Req | Default | Notes |
|---|---|---|---|
| `API_INTERNAL_URL` | R (deployed) | `http://localhost:8000` | Server-side only. Next.js proxies `/api/v1/*` here and server components call it directly. On Render free plan, use the API's public HTTPS URL (`fromService.envVarKey: RENDER_EXTERNAL_URL`). Paid private networking can use `fromService.hostport`. |
| `NEXT_PUBLIC_API_URL` | O | empty | Browser override. Leave empty so the browser uses the same-origin `/api/v1` proxy (first-party cookie). Set only when the API is on a different origin. |
| `NEXT_PUBLIC_APP_NAME` | O | `ResolveAI` | |
| `NEXT_PUBLIC_DEMO_MODE` | O | `true` | Shows the sandbox/replay badge and "reset demo" affordance. |
| `NEXT_PUBLIC_SSE_URL` | O | derived | If the SSE origin differs from the API. |
| `AG_GRID_LICENSE_KEY` | O **S** | — | Server-side only, only if Enterprise is purchased. Never `NEXT_PUBLIC`. |
| `NEXT_SERVER_API_TOKEN` | O **S** | — | Only if SSR prefetch needs a service token. |

## Feature flags / demo

| Var | Req | Default | Notes |
|---|---|---|---|
| `FEATURE_BUYER_CHANNEL` | O | `true` | Simulated buyer API. |
| `FEATURE_WEBHOOK_SIMULATOR` | O | `true` (local/demo only) | 404 elsewhere. |
| `FEATURE_AUTO_EXECUTE` | O | `true` | If false, everything stops at approval (safe rehearsal mode). |
| `FEATURE_EVIDENCE_SUBMIT` | O | `true` | Toggle the PayPal evidence write. |
| `ALLOW_ADMIN_RESET` | O | `true` (local/demo only) | Guards `POST /admin/reset-demo`. |
| `DEMO_MERCHANT_SLUG` | O | `demo-store` | Seed target. |
| `DEMO_ENDPOINTS_ENABLED` | O | unset | Unset = on outside production, off in production. The public Render demo sets `true` explicitly; routes remain session-guarded. |

## Ops

| Var | Req | Default | Notes |
|---|---|---|---|
| `SENTRY_DSN` | O **S** | — | Error tracking. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | O | — | Traces. |
| `REQUEST_ID_HEADER` | O | `X-Request-ID` | |
| `HEALTHCHECK_TOKEN` | O **S** | — | If health endpoints must be protected. |

## Minimal `.env.local` to boot the demo (replay mode, no PayPal account needed)

```
APP_ENV=local
PAYPAL_MODE=replay
DATABASE_URL=postgresql+asyncpg://resolveai:resolveai@localhost:5432/resolveai
SECRET_KEY=<32 bytes hex>
CREDENTIAL_KEK=<32 bytes hex>
PII_HASH_PEPPER=<32 bytes hex>
PLAN_SIGNING_KEY=<32 bytes hex>
LLM_PROVIDER=google
LLM_API_KEY=<key>
API_INTERNAL_URL=http://localhost:8000
# NEXT_PUBLIC_API_URL stays empty: the browser uses the Next.js /api/v1 proxy.
```
Everything else has a safe default. Sandbox mode adds `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`,
`PAYPAL_WEBHOOK_ID`, `PAYPAL_MERCHANT_ID`.
