# 13 — Deploy to Render (production profile)

This is the deployment runbook for the public ResolveAI demo. It provisions three
Render resources from one Blueprint:

```
resolveai-web  (Next.js, Docker)  --/api/v1 proxy-->  resolveai-api  (FastAPI, Docker)
                                                              |
                                                              v
                                                       resolveai-db  (Postgres 16 + pgvector)
```

Why the proxy: the browser only talks to the Next.js origin. Next.js forwards
`/api/v1/*` to FastAPI, so the session cookie is first-party (no cross-site
cookie or CORS problems). On the free plan the proxy calls the API's public HTTPS
URL because free web services cannot receive private-network traffic.

---

## 0. What is already prepared in the repo

| File | Purpose |
|---|---|
| `render.yaml` | Blueprint: web + API + Postgres, health checks, env wiring |
| `apps/api/Dockerfile` | Multi-stage runtime, non-root user, Alembic on boot, `$PORT` support |
| `apps/web/Dockerfile` | Production `next build` + standalone server, non-root user, `$PORT` support |
| `apps/web/src/app/api/v1/[...path]/route.ts` | Runtime `/api/v1` proxy to `API_INTERNAL_URL` (not baked at build time) |
| `apps/api/app/core/config.py` | Normalizes Render `postgres://` URLs, fails closed on weak production secrets |
| `scripts/verify_deployment.py` | Public smoke test (health, status, proxy, optional login + seed) |
| `scripts/check_secrets.py` | Blocks committed keys/tokens before you push |

Nothing in the repo contains real credentials. `.env.local` is git-ignored.

---

## 1. Prerequisites (account authorization required)

You need:

1. A **public GitHub repository** containing this code (Render deploys from Git).
2. A **Render account** (free plan is enough for a demo).
3. A **Gemini API key** (optional but recommended; without it the agents use the
   labelled deterministic fallback).
4. A **PayPal Developer sandbox app** with the **Disputes** feature enabled
   (only needed for the live sandbox segment; replay mode needs nothing).

The assistant cannot create these accounts or authorize them on your behalf.

---

## 2. Push the repository

```bash
git add -A
git commit -m "chore: production deployment config for Render"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Before pushing, run the secret check:

```bash
python scripts/check_secrets.py
```

It scans tracked files for common key formats and for values from `.env.local`.
It never prints the secret values.

---

## 3. Create the Blueprint

1. Render Dashboard → **New +** → **Blueprint**.
2. Connect the GitHub repository.
3. Render reads `render.yaml` and shows three resources:
   - `resolveai-db` (Postgres 16)
   - `resolveai-api` (Docker web service)
   - `resolveai-web` (Docker web service)
4. When prompted, paste:
   - `LLM_API_KEY` — your Gemini key.
   - `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` — optional;
     leave blank for replay-only.
5. Click **Apply**.

First deploy takes roughly 5–10 minutes (two Docker builds). The API runs
`alembic upgrade head` before starting.

### Generated secrets

`render.yaml` uses `generateValue: true` for:

- `SECRET_KEY`
- `CREDENTIAL_KEK`
- `PII_HASH_PEPPER`
- `PLAN_SIGNING_KEY`

Render generates strong random values and stores them. They are never in Git.
`APP_ENV=production` makes the API refuse to boot if any of them is missing or
shorter than 32 characters.

---

## 4. Confirm the service URLs

Render assigns names like:

- `https://resolveai-web.onrender.com`
- `https://resolveai-api.onrender.com`

If a name is already taken, Render adds a suffix. In that case update these
values in the API service (Dashboard → Environment):

| Variable | Expected value |
|---|---|
| `API_BASE_URL` | `https://<actual-api-host>` |
| `WEB_BASE_URL` | `https://<actual-web-host>` |
| `CORS_ORIGINS` | `https://<actual-web-host>` |

The web service's `API_INTERNAL_URL` is wired to the API's
`RENDER_EXTERNAL_URL`, so it follows the actual public hostname automatically.
On a paid plan you can switch it to `fromService.hostport` for private-network
traffic. The free plan must use the public URL.

Redeploy the API after changing `API_BASE_URL` / `WEB_BASE_URL` / `CORS_ORIGINS`.

---

## 5. Verify the public application

```bash
python scripts/verify_deployment.py \
  --web https://resolveai-web.onrender.com \
  --api https://resolveai-api.onrender.com
```

Checks:

- `GET /health/live` and `GET /health/ready` on the API
- `GET /api/v1/system/status` (DB connected, mode, capability flags)
- `GET /api/v1/policy/rules`
- `GET /login` on the web service
- `GET <web>/api/v1/system/status` — proves the Next.js proxy works
- `GET <web>/` — follows the auth redirect and confirms the app is reachable

Then seed the demo through the UI (sign in → **Seed demo**) or:

```bash
python scripts/verify_deployment.py \
  --web https://resolveai-web.onrender.com \
  --api https://resolveai-api.onrender.com \
  --seed
```

`--seed` signs in with `DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD` (defaults:
`owner@northwind.example` / `resolveai-demo`), then calls
`POST /api/v1/demo/seed`. Use `--email` / `--password` to override. Prefer
environment variables in shared shells:

```bash
export DEMO_USER_EMAIL=owner@northwind.example
export DEMO_USER_PASSWORD=resolveai-demo
```

Expected dashboard state after `seed` + running the three cases:

| Case | State |
|---|---|
| `PP-D-91001` | resolved, simulated refund `REPLAY-RF-...` |
| `PP-D-91002` | awaiting approval |
| `PP-D-91003` | escalated, no refund |

---

## 6. PayPal sandbox + webhook

### 6.1 Create/locate the sandbox app

1. <https://developer.paypal.com/dashboard/applications/sandbox>
2. Create an app (type **Merchant**) or open the existing one.
3. Enable **Disputes** under the app's features if it is not already enabled.
4. Copy **Client ID** and **Secret**.

### 6.2 Set the API environment

Render Dashboard → `resolveai-api` → **Environment**:

| Variable | Value |
|---|---|
| `PAYPAL_MODE` | `sandbox` |
| `PAYPAL_CLIENT_ID` | sandbox client ID |
| `PAYPAL_CLIENT_SECRET` | sandbox secret |
| `PAYPAL_WEBHOOK_ID` | from step 6.3 |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` |
| `PAYPAL_WEBHOOK_VERIFY` | `true` |
| `ALLOW_LIVE_PAYPAL` | `false` (sandbox only) |

`APP_ENV=production` + `PAYPAL_MODE=sandbox` fails closed if the client ID or
secret is missing, which is intentional.

### 6.3 Create the webhook

PayPal Developer Dashboard → your app → **Webhooks** → **Add webhook**:

- **URL:** `https://<actual-api-host>/api/v1/webhooks/paypal`
- **Event types:**
  - `CUSTOMER.DISPUTE.CREATED`
  - `CUSTOMER.DISPUTE.UPDATED`
  - `CUSTOMER.DISPUTE.RESOLVED`
  - `PAYMENT.CAPTURE.COMPLETED`
  - `PAYMENT.CAPTURE.REFUNDED`
  - `PAYMENT.CAPTURE.REVERSED`
- Save, then copy the **Webhook ID** into `PAYPAL_WEBHOOK_ID`.

The endpoint verifies the PayPal signature in sandbox mode and rejects invalid
signatures with `400 INVALID_SIGNATURE`. In replay mode it stores the delivery
honestly with `signature_valid=false` and performs no side effects.

### 6.4 Verify credentials without exposing them

From a machine with the sandbox values in `.env.local`:

```bash
cd apps/api
uv run python -m scripts.verify_credentials
PAYPAL_MODE=sandbox uv run python -m scripts.verify_sandbox_adapter
```

Both scripts print masked fingerprints, never the secret values.

> **Honest limit:** a real sandbox refund requires a real sandbox dispute and a
> buyer/capture that can be refunded. The public demo runs in replay mode by
> default; replay refunds are labelled `simulated (replay)` everywhere.

---

## 7. Hardened production profile

The public hackathon deployment intentionally keeps demo controls enabled:

```
APP_ENV=production
DEMO_ENDPOINTS_ENABLED=true
PAYPAL_MODE=replay
```

For a real merchant deployment, change:

```
DEMO_ENDPOINTS_ENABLED=false
PAYPAL_MODE=sandbox          # or live only after a separate security review
DEMO_USER_PASSWORD=<strong, unique>
```

Also add SSO/RBAC, per-tenant authorization, rate limiting backed by Redis,
durable evidence storage (S3), and a real secret manager. See
[docs/06-security.md](06-security.md).

---

## 8. Operational notes

| Topic | Behaviour |
|---|---|
| Cold starts | Render free web services spin down after ~15 minutes idle. First request can take ~1 minute. Open the dashboard once before recording the demo. |
| Migrations | `alembic upgrade head` runs on every API boot; migrations are idempotent. |
| Database | Render Postgres free plan. The migration runs `CREATE EXTENSION IF NOT EXISTS vector`; Render supports pgvector on Postgres 13+. **Free Postgres expires 30 days after creation** — upgrade or recreate before a longer judging window. |
| Evidence files | `STORAGE_LOCAL_DIR=/app/var/evidence` is ephemeral. Uploaded evidence does not survive a redeploy. Use S3 for persistence. |
| Logs | `LOG_FORMAT=json`; request IDs are in `X-Request-ID` and the error envelope. |
| Health | API `/health/ready`; web `/login`. Render restarts a service that fails its health check. |
| Rollback | Render Dashboard → service → **Deploys** → **Rollback** to the previous image. |
| Cost | Free plan: both web services + Postgres. They sleep when idle. |

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| API boot fails with `APP_ENV=production requires...` | A generated secret was removed/too short | Re-add all four 32+ char secrets in Render |
| API boot fails at `alembic upgrade head` | `DATABASE_URL` wrong or DB still provisioning | Wait for Postgres to be available; check the connection string |
| Web shows `Cannot reach /api/v1/...` | `API_INTERNAL_URL` wrong or points at a private address on the free plan | Set it to the API public URL (`https://resolveai-api.onrender.com`) and redeploy |
| Login succeeds but dashboard redirects to `/login` | Cookie not stored | Confirm both services are HTTPS; `AUTH_COOKIE_SECURE=true`; browser is not blocking cookies |
| `502` on web | The `/api/v1` proxy could not reach the API | Check API health and `API_INTERNAL_URL` |
| Agents always show `fallback` | `LLM_API_KEY` missing or Gemini 503 | Add a valid key; fallback is expected and labelled |
| Webhook returns `INVALID_SIGNATURE` | Wrong `PAYPAL_WEBHOOK_ID` or body modified by a proxy | Re-copy the webhook ID; send the raw body unchanged |
| `live_paypal=false` | `PAYPAL_MODE` is still `replay` | Switch to `sandbox` and provide credentials |

---

## 10. Post-deploy checklist

- [ ] `scripts/verify_deployment.py` passes all checks
- [ ] Dashboard loads over HTTPS and login works
- [ ] Seed creates three disputes
- [ ] `PP-D-91001` executes a simulated refund
- [ ] `PP-D-91002` waits for approval; approving executes exactly one refund
- [ ] `PP-D-91003` is escalated with no refund
- [ ] `/api/v1/system/status` shows `db.connected=true` and the expected mode
- [ ] No secret appears in the browser bundle or network responses
- [ ] Render env vars contain no placeholder values
- [ ] Repo has `LICENSE` (MIT) and the README setup section
- [ ] Demo video URL is public and under 3:00
