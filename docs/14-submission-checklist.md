# 14 — Devpost submission checklist

Use this in the last hour. Do not edit code after the video is recorded unless the
public deployment is broken.

---

## 1. Hard requirements

| # | Requirement | Where | Done |
|---|---|---|---|
| 1 | Public GitHub repository | Repo URL | [ ] |
| 2 | MIT license file visible in repo | `LICENSE` + repo About | [ ] |
| 3 | All source, assets, setup instructions in repo | `README.md`, `docs/` | [ ] |
| 4 | Functional demo: hosted URL **or** runnable setup | Render URL + `docker compose up` | [ ] |
| 5 | Video under 3 minutes, public on YouTube | `docs/11-demo-script.md` | [ ] |
| 6 | Text description of features | Section 3 below | [ ] |
| 7 | PayPal developer platform integration | sandbox adapter + webhook | [ ] |
| 8 | AI model integration | Gemini agents + labelled fallback | [ ] |
| 9 | English only | all docs/UI | [ ] |
| 10 | No third-party trademarks/music without permission | video | [ ] |

---

## 2. Final verification commands

```bash
# secrets: no credential in tracked files or history
python scripts/check_secrets.py --history

# backend tests
cd apps/api && uv run pytest -q

# frontend typecheck + production build
cd apps/web && npm run typecheck && npm run build

# public deployment smoke test
python scripts/verify_deployment.py \
  --web https://resolveai-web.onrender.com \
  --api https://resolveai-api.onrender.com
```

Expected: secret scan passes, tests pass, typecheck/build pass, every deployment
check passes.

---

## 3. Devpost text (paste and adjust)

### Tagline

> Autonomous PayPal dispute resolution with a deterministic policy gate.

### Short description

> ResolveAI is a merchant control tower for PayPal disputes. Four specialist
> agents — Buyer, Merchant, Resolution, and Payment — read one shared case file,
> argue both sides, and propose a remedy. A deterministic policy engine, not the
> model, decides what may execute. Above the autonomous envelope, a human
> approval is required. Money only moves through a signed payment plan consumed
> by an idempotent executor. Every step is persisted in PostgreSQL with a
> hash-chained audit log.

### What it does

- Ingests PayPal disputes through a replay fixture adapter or the live sandbox
  REST API.
- Builds a case file from order, capture, messages, tracking, and policy.
- Runs a LangGraph workflow with four typed agents and bounded negotiation.
- Evaluates a versioned policy ruleset twice: once to constrain the agents, once
  to decide allow / require approval / deny.
- Executes only signed, idempotent refunds; re-approving cannot pay twice.
- Shows the full transcript, policy citations, evidence gaps, and refund
  receipts in a Next.js + AG Grid dashboard.
- Labels replay refunds **simulated (replay)** and labels deterministic fallbacks
  **fallback** — no fabricated model output.

### How PayPal is used

- OAuth client-credentials flow against `api-m.sandbox.paypal.com`.
- Disputes API read path; Payments API order/capture/refund lifecycle.
- Webhook intake with PayPal signature verification (`PAYPAL_WEBHOOK_ID`).
- Sandbox credentials are supplied through environment variables and never
  committed. Replay mode is the fail-closed default so the demo is deterministic.

### How AI is used

- Gemini 3.5 Flash / Flash-Lite via the REST API with strict JSON output.
- LangGraph orchestrates Buyer ∥ Merchant → Resolution → policy gate → Payment.
- The model proposes; the deterministic policy engine disposes. Agents cannot
  call PayPal write endpoints.
- Free-tier 503/429 falls back to a deterministic, clearly labelled path.

### Built with

`PayPal REST API`, `PayPal Disputes API`, `Next.js`, `TypeScript`, `FastAPI`,
`SQLAlchemy`, `PostgreSQL`, `pgvector`, `LangGraph`, `Gemini`, `AG Grid`,
`Docker`, `Render`.

### Demo credentials

```
URL:      https://resolveai-web.onrender.com
Email:    owner@northwind.example
Password: resolveai-demo
```

The public deployment runs in replay mode. Refunds are simulated and labelled.
No real money moves.

### Repo / video

```
Repo:  https://github.com/<you>/<repo>
Video: https://youtu.be/<id>
```

---

## 4. Screenshots to capture

1. Dashboard KPI row + execution envelope.
2. `PP-D-91001` timeline + simulated refund receipt.
3. `PP-D-91002` policy gate with matched rules + approval dialog.
4. `PP-D-91003` defend decision, no refund.
5. Agent transcript with evidence refs and tokens/latency.
6. `/api/v1/system/status` showing DB connected and mode.

Blur or avoid anything with real emails, API keys, or Render env vars.

---

## 5. Submission sequence

1. Run `python scripts/check_secrets.py --history`.
2. Push the final commit. Confirm the GitHub repo is public and `LICENSE` is
   detected in the About section.
3. Open the deployed URL in a private window. Sign in. Run the three cases.
4. Upload the video to YouTube as **Public**. Watch it once in a private window.
5. Fill the Devpost form: title, tagline, description, built-with tags, repo URL,
   video URL, screenshots, demo credentials.
6. Add the deployed URL and demo credentials to the README.
7. Submit. Save the confirmation email/screenshot.
8. Do not change the repo or deployment during judging unless something is
   broken; if you must, note it in the Devpost update.

---

## 6. Known honest limits (state them if asked)

- Replay refunds are simulated; `live_paypal` is false until a real sandbox
  refund has executed.
- The public demo is single-operator. Production would add SSO/RBAC and
  per-tenant authorization.
- Evidence files on Render are ephemeral; production would use S3.
- Free Render services cold-start after idle. The video opens the app once before
  recording.
- The free Gemini tier can return 503; the fallback is labelled in the trace.
