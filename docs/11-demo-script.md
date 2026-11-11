# 11 — Three-minute demo script (public deployment)

Deadline: **Fri 2026-11-13 01:30 IST** (Thu Nov 12, 12:00 pm PT). The video is
**20% of the score** and must be public on YouTube.

This script targets the deployed Render app. The same flow works locally with
`docker compose up`; replace the URL in the browser with `http://localhost:3000`.

Rules of thumb:

- Show the product, not slides. At most one title card.
- Every claim on screen must match what the app shows. Replay refunds are labelled
  **simulated (replay)** — say that out loud.
- Do not show `.env.local`, Render env vars, browser autofill, account emails, or
  API keys.
- Record at 1080p, 30 fps. Your voice over the demo. No music that hides speech.
- Keep it under **3:00**. The storyboard below is **2:52**.

---

## Pre-record checklist (10 minutes)

```bash
# 1. wake the free Render services (first request can take 30-60s)
curl https://resolveai-web.onrender.com/login
curl https://resolveai-api.onrender.com/health/ready

# 2. verify the public stack and seed fresh demo data
python scripts/verify_deployment.py \
  --web https://resolveai-web.onrender.com \
  --api https://resolveai-api.onrender.com \
  --seed

# 3. confirm the three cases
#    dashboard should show: 1 resolved, 1 awaiting approval, 1 escalated
```

If you prefer to run the cases during the recording, seed only, then click
**Run agents** on each case on camera. Do not do both.

- Close Slack, email, Render dashboard, and any tab that shows secrets.
- Zoom the browser to 100% at 1920x1080. Hide the bookmarks bar.
- Have three tabs ready:
  1. `https://resolveai-web.onrender.com/`
  2. the `PP-D-91001` detail page
  3. the `PP-D-91002` detail page
- Sign in before recording so the login form is not the first thing viewers see.
  (Optional: show a 3-second login beat if you want to prove auth is real.)
- If you plan a sandbox segment: record it **last** and only if a real sandbox
  refund actually executed.

---

## Storyboard (2:52)

### 0:00 – 0:12 | Hook

**Screen:** dashboard, pointer on the KPI row.

> "A PayPal dispute usually means a support agent reading messages, checking
> policy, and guessing. ResolveAI lets four agents resolve it — while a
> deterministic policy engine keeps the money safe."

### 0:12 – 0:35 | The control tower

**Screen:** dashboard.

- Point at **Exposure at risk** and **Recovered / refunded**.
- Point at **Needs a human decision** — one case waiting.
- Open **Execution envelope**: "$50 autonomous refund cap, $100 offer cap, 80%
  confidence."

> "Every number here is a live query against Postgres. Nothing is a mock. These
> thresholds come from `rules.yaml` through the API — not from the model."

### 0:35 – 1:05 | Case 1 — item not received, autonomous

**Screen:** open `PP-D-91001`.

- Show the buyer message and order facts.
- Click **Run agents** (or show the completed timeline).
- Walk the five steps: Buyer (LLM), Merchant (LLM), Resolution (LLM),
  Policy: allow, Payment plan.
- Scroll to **Refund receipts**: `REPLAY-RF-...`, badge **simulated (replay)**.

> "Forty dollars, confidence 90%, inside the autonomous envelope. The executor
> verified the signed plan and paid. In replay mode the receipt is simulated —
> and labelled as such. Flip one env var and the same path calls the PayPal
> sandbox."

### 1:05 – 1:38 | Case 2 — not as described, human approval

**Screen:** open `PP-D-91002`.

- Timeline ends at **Policy: require_approval**.
- Scroll to **Policy gate**: matched rules, band, ceiling.
- Right column: type a short note, click **Approve & pay**.
- After refresh: receipt appears, status `RESOLVED`, recovered amount increases.

> "Same agents, same model. But this amount is above the autonomous cap, so the
> policy gate stops it. I review the envelope and approve. The plan is signed and
> idempotent — approving twice cannot pay twice."

### 1:38 – 1:58 | Case 3 — unauthorised, refuse to pay

**Screen:** open `PP-D-91003`.

- Decision `DEFEND`, amount `0.00`, no refund card.

> "Fraud reasons are never auto-adjudicated. The agents collect the
> seller-protection facts, the decision is defend, and no payment plan is ever
> created."

### 1:58 – 2:20 | Why this is not a chatbot with a PayPal key

**Screen:** detail page, scroll to transcript and evidence chips (or the README
on GitHub).

- Typed envelopes, evidence refs, tokens/latency per step.
- Mention: 52 backend tests, including the whole graph with the LLM forced
  offline.
- Mention: fallback steps are labelled `fallback` in the trace.

> "Agents cannot call PayPal. They emit a typed plan; the executor verifies an
> HMAC before moving money. Every decision is in a hash-chained audit log."

### 2:20 – 2:38 | Live sandbox (optional, only if verified)

**Screen:** `/api/v1/system/status` or dashboard badge, then the real PayPal
sandbox activity page.

> "The adapter is live: OAuth and the Disputes API are verified against the
> sandbox. This refund [only say this if it happened] is a real sandbox refund,
> id shown in the receipt."

If the live segment is not ready, say instead:

> "The sandbox adapter is implemented and the credentials verified; today's demo
> runs in replay so the recording is deterministic. The switch is
> `PAYPAL_MODE=sandbox`."

### 2:38 – 2:52 | Close

**Screen:** dashboard, then a title card with the repo URL.

> "ResolveAI: autonomous where it is safe, human where it matters. Code, tests,
> and the verification log are in the public repo. MIT licensed."

---

## YouTube upload

- Visibility: **Public** (unlisted does not count for most hackathons).
- Title: `ResolveAI — autonomous PayPal dispute resolution with a policy gate`
- Description: 2–3 sentences, stack, repo URL, and "replay refunds are
  simulated" note.
- Tags: `PayPal`, `AI agents`, `LangGraph`, `FastAPI`, `Next.js`, `dispute
  resolution`.
- Add chapters at 0:00 / 0:12 / 0:35 / 1:05 / 1:38 / 1:58 / 2:38.
- Check the video plays in a private window before submitting the URL.

---

## Claims checklist before publishing

- [ ] I did not say "live PayPal refund" unless a real sandbox refund row exists.
- [ ] The video shows the **simulated (replay)** badge when replay receipts are visible.
- [ ] No secrets, Render env vars, emails, or passwords appear on screen.
- [ ] The repo URL in the description is public and the MIT license is visible.
- [ ] Video is under 3:00.
- [ ] The deployed URL in the description matches the URL shown in the video.
