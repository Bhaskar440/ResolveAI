# 11 - Demo video script (under 3 minutes)

Deadline: **Fri 2026-11-13 01:30 IST** (Thu Nov 12, 12:00 pm PT). The video is **20% of the score**
and must be public on YouTube.

Rules of thumb:

- Show the product, not slides. At most one title card.
- Every claim on screen must match what the app shows. Replay refunds are labelled
  **simulated (replay)** - say that out loud.
- Do not show `.env.local`, browser autofill, account emails or API keys.
- Record at 1080p, 30 fps. Your voice over the demo. No background music that hides speech.

---

## Pre-record checklist (10 minutes)

```bash
# 1. clean state, exactly what the video will show
curl -X POST http://localhost:8000/api/v1/demo/reset
curl -X POST http://localhost:8000/api/v1/demo/seed

# 2. run the three cases (or run INR + SNAD in the UI during recording)
cd apps/api && uv run python -m scripts.run_demo

# 3. confirm the dashboard shows: 1 resolved, 1 awaiting approval, 1 escalated
curl http://localhost:8000/api/v1/metrics
```

- Close Slack, email, and any tab that shows secrets.
- Zoom the browser to 100% at 1920x1080. Hide the bookmarks bar.
- Have the three tabs ready: `/`, `/disputes/<INR id>`, `/disputes/<SNAD id>`.
- If you plan a sandbox segment: record it **last** and only if a real refund actually executed.

---

## Storyboard (2:45)

### 0:00 - 0:15 | Hook

Screen: dashboard, pointer on the KPI row.

> "A PayPal dispute usually means a support agent reading messages, checking policy, and guessing.
> ResolveAI lets four agents resolve it - while a deterministic policy engine keeps the money safe."

### 0:15 - 0:40 | The control tower

Screen: dashboard.

- Point at **Exposure at risk** and **Recovered / refunded**.
- Point at **Needs a human decision** - one case waiting.
- Open **Execution envelope** card: "$50 autonomous refund cap, $250 hard cap, 80% confidence" -
  "these numbers come from `rules.yaml` through the API, not from the model."

> "Every number here is a live query against Postgres. Nothing is a mock."

### 0:40 - 1:10 | Case 1 - item not received, autonomous

Screen: open PP-D-91001 detail.

- Show the buyer message and order facts.
- Click **Run agents** (if already run, show the timeline).
- Walk the five steps: Buyer (LLM), Merchant (LLM), Resolution (LLM), Policy: allow, Payment plan.
- Scroll to **Refund receipts**: `REPLAY-RF-...`, badge **simulated (replay)**.

> "Forty dollars, confidence 90%, inside the autonomous envelope. The executor verified the signed
> plan and paid. In replay mode the receipt is simulated - and labelled as such. Flip one env var and
> the same path calls the PayPal sandbox."

### 1:10 - 1:45 | Case 2 - not as described, human approval

Screen: open PP-D-91002.

- Timeline ends at **Policy: require_approval**.
- Scroll to **Policy gate**: show matched rules, band, ceiling.
- Right column: type a note, click **Approve & pay**.
- After refresh: receipt appears, status `RESOLVED`, dashboard recovered amount increases.

> "Same agents, same model. But 140 dollars is above the autonomous cap, so the policy gate stops it.
> I review the envelope and approve. The plan is signed and idempotent - approving twice cannot pay
> twice."

### 1:45 - 2:05 | Case 3 - unauthorised, refuse to pay

Screen: open PP-D-91003.

- Decision `DEFEND`, amount `0.00`, no refund card.

> "Fraud reasons are never auto-adjudicated. The agents collect the seller-protection facts, the
> decision is defend, and no payment plan is ever created."

### 2:05 - 2:25 | Why this is not a chatbot with a PayPal key

Screen: detail page, scroll to transcript and evidence chips (or README on GitHub).

- Typed envelopes, evidence refs, tokens/latency per step.
- Mention: 19 backend tests, including the whole graph with the LLM forced offline.
- Mention: fallback steps are labelled `fallback` in the trace.

> "Agents cannot call PayPal. They emit a typed plan; the executor verifies an HMAC before moving
> money. Every decision is in a hash-chained audit log."

### 2:25 - 2:45 | Live sandbox (optional, only if verified)

Screen: `/api/v1/system/status` or dashboard badge, then the real PayPal sandbox activity page.

> "The adapter is live: OAuth and the Disputes API are verified against the sandbox. This refund
> [only say this if it happened] is a real sandbox refund, id shown in the receipt."

If the live segment is not ready, say instead:

> "The sandbox adapter is implemented and the credentials verified; today's demo runs in replay so
> the recording is deterministic. The switch is `PAYPAL_MODE=sandbox`."

### 2:45 - 2:55 | Close

> "ResolveAI: autonomous where it is safe, human where it matters. Code, tests and the verification
> log are in the public repo."

---

## YouTube upload

- Visibility: **Public** (unlisted does not count for most hackathons).
- Title: `ResolveAI - autonomous PayPal dispute resolution with a policy gate`
- Description: 2-3 sentences, stack, repo URL, "replay refunds are simulated" note.
- Tags: `PayPal`, `AI agents`, `LangGraph`, `FastAPI`, `Next.js`, `dispute resolution`.
- Add chapters at 0:00 / 0:40 / 1:10 / 1:45 / 2:05.
- Check the video plays in a private window before submitting the URL.

## Claims checklist before publishing

- [ ] I did not say "live PayPal refund" unless a real sandbox refund row exists.
- [ ] The video shows the **simulated (replay)** badge when replay receipts are visible.
- [ ] No secrets, emails or passwords appear on screen.
- [ ] The repo URL in the description is public and the MIT license is visible.
- [ ] Video is under 3:00.
