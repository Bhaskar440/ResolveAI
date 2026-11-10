# 09 — Manual Actions, Credentials & Approvals Checklist

> Running document. I update the status board after every action and after every verification.
> **Statuses: `NOT STARTED` · `WAITING FOR ME` · `COMPLETED`** ("ME" = you, the human).

---

## 0. Environment audit (measured, 2026-11-10, this machine)

| Item | Result | Consequence |
|---|---|---|
| Project contents | Only `docs/` (9 design docs). No code, no `.git` | Greenfield scaffold needed |
| Git | `2.48.1.windows.1` | ✅ usable |
| Node / npm | `v22.14.0` / `11.4.2` | ✅ Next.js 15 OK |
| Python | `3.13.2` (`py` launcher present) | ✅ FastAPI OK |
| uv | `0.13.5` | ✅ dependency installs verified below |
| Docker | CLI `29.5.3`, engine was **down** → I started Docker Desktop, engine now responds (`server=29.5.3`) | ✅ Postgres via compose OK, **no manual action needed** |
| cloudflared / ngrok | **not installed** | I will download `cloudflared.exe` into `tools/` (no account, no admin) |
| psql / openssl | not installed | Not needed — use Docker Postgres + Python `secrets` |
| Egress → `api-m.sandbox.paypal.com` | HTTP **401** (expected: no token) | ✅ network path to PayPal works |
| Egress → `developer.paypal.com` | HTTP **200** | ✅ |
| Egress → `api.openai.com` | HTTP **401** (expected) | ✅ |
| Egress → `generativelanguage.googleapis.com` | HTTP **403** (expected: no key) | ✅ |
| Egress → `api.github.com` | HTTP 403/200 (rate-limited shared IP) | ⚠️ reachable, unauthenticated limit |
| Egress → PyPI | `uv pip compile fastapi` resolved `fastapi==0.162.2` + 7 deps | ✅ installs work |

**Not verified (and I will not claim otherwise):** whether your PayPal app has the Disputes
feature enabled, whether sandbox webhooks reach us, whether any LLM key works, whether a repo
exists, whether anything is deployed.

---

## 1. Status board

### 1a. Blocking — I need these from you

| ID | Task | Owner | Status | Blocks |
|---|---|---|---|---|
| **M-01** | Read the Devpost rules; capture deadline, deliverables, judging criteria, eligibility | You | **WAITING FOR ME** | Scope + M-12 |
| **M-02** | PayPal Developer app with **Disputes** feature → Client ID + Secret | You | **WAITING FOR ME** | Everything PayPal |
| **M-03** | Confirm sandbox business + personal (buyer) accounts and their logins | You | **WAITING FOR ME** | Dispute filing, live demo |
| **M-04** | LLM API key (Gemini **or** OpenAI) | You | **WAITING FOR ME** | All agent work |
| **M-05** | GitHub repo (private) + one-time push authorization | You | **WAITING FOR ME** | Delivery, Devpost repo link |
| **M-06** | Approve autonomy numbers + the 3 demo scenarios | You | **WAITING FOR ME** | Policy rules (M2) |

### 1b. Needed later (not blocking build)

| ID | Task | Owner | Status | When |
|---|---|---|---|---|
| **M-07** | File 3 real sandbox disputes via Resolution Center | You | **WAITING FOR ME** (only after I seed transactions) | Before live demo |
| **M-08** | Check/fund sandbox balances (avoid negative balance) | You | **WAITING FOR ME** | 24 h before demo |
| **M-09** | Hosting accounts (Vercel + Render + Neon) — **only if we deploy** | You | **WAITING FOR ME** (decision) | After M4 |
| **M-10** | **Conditional:** request Disputes API access if I get HTTP 403 | You | `NOT STARTED` (only if triggered) | On my report |
| **M-11** | Optional: PayPal Agent Toolkit / MCP authorization — **only if your track requires it** | You | `NOT STARTED` | If confirmed |
| **M-12** | Devpost final submission (your account) | You | `NOT STARTED` | Last 2 h |

### 1c. Mine — completed

| ID | Task | Status | Evidence |
|---|---|---|---|
| A-01 | Architecture & design set (docs 01–08) | **COMPLETED** | 1,257 lines, `docs/` |
| A-02 | Toolchain audit | **COMPLETED** | §0 |
| A-03 | Network egress verification to PayPal/LLM/GitHub/PyPI | **COMPLETED** | §0 HTTP codes |
| A-04 | Env-secret safety: `.gitignore` + `.env.example` (no secrets committed) | **COMPLETED** | `.gitignore`, `.env.example` |
| A-05 | Start Docker engine (was down) | **COMPLETED** | `docker info` → `server=29.5.3` |
| A-06 | Local git repo init + first commit (docs only) | **COMPLETED** | `git log` |

### 1d. Mine — queued, no dependency on you

| ID | Task | Status |
|---|---|---|
| A-07 | Download `cloudflared.exe` to `tools/` + verify a quick tunnel (no account) | `NOT STARTED` |
| A-08 | Monorepo scaffold, `docker-compose.yml` (Postgres), FastAPI app factory, Alembic baseline | `NOT STARTED` |
| A-09 | DB models/migrations per doc 02 + seed script with fixture data | `NOT STARTED` |
| A-10 | PayPal adapter skeleton with `replay` mode + fixtures (works with **zero** credentials) | `NOT STARTED` |
| A-11 | Policy engine + `rules.yaml` + unit tests (pure, no LLM) | `NOT STARTED` |
| A-12 | Next.js shell + AG Grid with replay data | `NOT STARTED` |

---

## 2. Secret-handling protocol (do this instead of pasting secrets in chat)

**Where secrets go:** `D:\Paypal_hackathon_AI\.env.local` (created by you, from `.env.example`).

```
Copy-Item .env.example .env.local      # then edit .env.local
```

- `.gitignore` already excludes `.env*` (only `.env.example` is allow-listed). I will confirm with
  `git check-ignore -v .env.local` **and** `git status --porcelain` after you add secrets.
- **Never** paste a Client Secret, API key, or password into this chat. If you do by accident, rotate
  it immediately in the provider dashboard and tell me "rotated" — I will not echo it.
- I will only ever report: variable **present/absent**, length, and a 6-char SHA-256 fingerprint.
  Never the value.
- I never write secrets into `docs/`, `fixtures/`, logs, screenshots, or commit messages.

---

## 3. Task detail

### M-01 — Read the hackathon rules (10 min, no credentials)

**What:** Read the official Devpost page and capture the rules that constrain the build.
**Why:** Deadline, required tech, judging weights and "is a public repo required" change the plan
(cut list, whether M-09 is mandatory, whether M-11 is a bonus). I do not know these and will not guess.
**URL:** the Devpost page for the PayPal AI Hackathon — **you must paste the link to me** (I have not
verified any URL for this event and will not invent one).
**Steps:**
1. Open the page, screenshot or copy: submission deadline (date + time + timezone), team size limit,
   eligibility, required deliverables (video? live demo? repo public?), judging criteria + weights,
   required/sponsored technologies, and any "use PayPal APIs" mandate.
2. Paste the rules text (not credentials) into chat.
**Hand back:** the rules text + URL.
**Verification:** I restate the constraints as a numbered list and you confirm/correct.
**How I use it:** adjust M-07/M-12, decide whether M-09 and M-11 are mandatory, and lock the demo script.

---

### M-02 — PayPal Developer app + credentials (15 min) ← *the critical one*

**What:** Create/confirm a PayPal **Developer** account and a **Sandbox** REST app with the
**Disputes** capability, then put Client ID + Secret in `.env.local`.
**Why:** every PayPal read (order, capture, dispute) and write (refund, evidence, offer) is
authenticated by this app's OAuth2 client-credentials token. Without it I can only run replay mode.
**URL:** `https://developer.paypal.com/` (then Dashboard → **Apps & Credentials** → toggle **Sandbox**)
**Steps:**
1. Log in. If you have no PayPal account at all, create one (email + phone verification is required by
   PayPal — only you can do that).
2. Dashboard → **Apps & Credentials** → make sure the **Sandbox** toggle is selected → **Create App**.
3. Name: `ResolveAI`. Type: **Merchant**.
4. In the feature list, **tick `Disputes`** (also tick `Accept payments` / `Checkout` if offered).
   *If `Disputes` is not listed, stop and tell me — that is the blocking case in M-10.*
5. Create → copy the **Client ID** and **Secret** (Secret is masked; click *Show*; it may be shown only once).
6. In `D:\Paypal_hackathon_AI\.env.local` set:
   ```
   PAYPAL_MODE=sandbox
   PAYPAL_CLIENT_ID=<paste>
   PAYPAL_CLIENT_SECRET=<paste>
   ```
7. Tell me: "M-02 done", the app name, and **whether a `Disputes` checkbox existed** (yes/no).
**Hand back (in chat):** only "done" + checkbox answer. **Never the secret.**
**My verification (concrete):**
1. `git check-ignore -v .env.local` → must print a match; `git status --porcelain` → `.env.local` absent.
2. OAuth call to `/v1/oauth2/token` → expect `200` + `access_token`; report only success + `expires_in`.
3. `GET /v1/customer/disputes?page_size=1` → expect `200` → **Disputes API confirmed**.
   `403 PERMISSION_DENIED` → I report it, mark M-10 as triggered, and continue in replay mode.
4. `GET /v2/payments/captures/{nonexistent}` → expect `404` (proves auth + endpoint shape, no side effects).
**How I use it:** live sandbox mode: dispute sync, reconciliation, refund execution, webhook creation.
I will create the webhook subscription via API myself once a public tunnel is up — you don't need to
click anything for `PAYPAL_WEBHOOK_ID`.

---

### M-03 — Confirm sandbox test accounts (5 min)

**What:** Verify the auto-created **business** (merchant) and **personal** (buyer) sandbox accounts
exist, and set passwords you can log in with.
**Why:** the buyer account is the *only* way to file a sandbox dispute (there is no create-dispute API);
the business account is where the refund must visibly appear during the demo.
**URL:** `https://developer.paypal.com/dashboard/accounts` (Dashboard → **Accounts**; if that path 404s,
navigate from the dashboard menu — PayPal renames menus often).
**Steps:**
1. Confirm one `BUSINESS` and one `PERSONAL` account exist (create one of each if not).
2. Click an account → **View/Edit account** → note the **email**, click **Change password**, set a
   password *you* control, and store it in your password manager.
3. Do the same for the business account.
4. Log in once at `https://www.sandbox.paypal.com/` with each to prove the credentials work.
**Hand back:** the two **emails**, the business account's **Payer ID / Merchant ID** if shown, and
"both logins work". **No passwords.**
**My verification:** I call `GET /v2/checkout/orders` capabilities and later match the merchant ID in
`/v2/payments/captures` responses against what you gave me.
**How I use it:** seed data attribution, and demo assertions ("refund appears in *this* business account").

---

### M-04 — LLM API key (5 min)

**What:** one API key for the agent models.
**Why:** Buyer/Merchant/Resolution agents + structured-output extraction need it. Without it I can build
and test everything with stubs, but cannot run a real agent.
**URL (choose one):**
- Google AI Studio (recommended: free tier, fast, low friction): `https://aistudio.google.com/apikey`
- OpenAI: `https://platform.openai.com/api-keys`
**Steps (Gemini):** sign in with a Google account → **Create API key** → select/create a project →
copy → in `.env.local`:
```
LLM_PROVIDER=google
LLM_API_KEY=<paste>
LLM_MODEL_FAST=gemini-2.5-flash
LLM_MODEL_REASONING=gemini-2.5-pro
```
**Steps (OpenAI):** `Create new secret key` → copy → `LLM_PROVIDER=openai`, `LLM_MODEL_FAST=gpt-4.1-mini`,
`LLM_MODEL_REASONING=gpt-4.1`.
**Hand back:** only "done, provider = google|openai". If the provider requires a payment method, tell me —
we can stay on a free tier instead.
**My verification:** `GET /v1beta/models` (or `/v1/models`) → `200`; then one 8-token structured-output
call; then report exact model IDs available, latency, and cost per 1k tokens. If the model name differs
from the default, I update config and tell you.
**How I use it:** agent subgraphs; I will show measured $/decision in the UI.

---

### M-05 — GitHub repo + push access (5 min)

**What:** an empty **private** repo (or public, if the rules require it — see M-01).
**Why:** backup, Devpost submission link, and lets me hand you reviewable commits.
**URL:** `https://github.com/new`
**Steps:**
1. Repository name `resolveai`, **Private**, do **not** initialize with README/`.gitignore`.
2. Create → copy the HTTPS URL (`https://github.com/<you>/resolveai.git`).
3. Paste the URL in chat. I will run `git remote add origin …`.
4. On my first `git push`, Git Credential Manager will open a browser window — **you** complete that
   one-time authorization (or give me a fine-grained PAT with `contents:write`, placed *only* in
   `.env.local` as `GITHUB_TOKEN`, never in chat).
**Hand back:** repo URL; then complete the browser auth when it appears.
**My verification:** `git ls-remote origin` succeeds; `git push -u origin main` exits 0; `git log` on
GitHub matches local.
**How I use it:** versioned delivery + Devpost repo URL.
**Cost note:** private repos are free; no plan upgrade needed.

---

### M-06 — Approve autonomy numbers & demo scenarios (5 min, no URL)

**What:** confirm the business rules I will hard-code into the policy engine.
**Why:** these are *your* risk decisions, not technical ones. They decide what the AI may do without a human.
**Proposed defaults (confirm or change):**
| Rule | Proposed |
|---|---|
| Auto-refund without human | ≤ **$50** |
| Auto partial offer | ≤ **$100** |
| Human approval required | amount > cap, **or** confidence < 0.80 |
| Never auto-adjudicated | reason `UNAUTHORISED`, `DUPLICATE_TRANSACTION` |
| Hard stop (always human) | any refund > $250 |
| Demo scenarios | ① INR $80 → auto-refund ② SNAD $140 → 50% offer, human edits ③ UNAUTHORISED $260 → escalate, no money moves |
**Hand back:** "approved as-is" or the changed numbers.
**How I use it:** `rules.yaml` + `merchants.auto_resolve_cap`; the UI shows these numbers on the settings page.

---

### M-07 — File 3 real sandbox disputes (20 min, **after** I seed transactions)

**What:** as the **buyer**, open a Resolution Center case on each of the 3 transactions I create.
**Why:** PayPal exposes **no public API to create a dispute**. This is the only legitimate way to get a
real sandbox dispute. I will not fake one and call it real.
**URL:** `https://www.sandbox.paypal.com/` (log in as the **personal** sandbox account from M-03)
**Steps (per transaction):**
1. I run `scripts/seed_transactions.py` and give you 3 order IDs + a checkout link each.
2. Log in as the buyer → open the checkout link → pay (test funding source) → return.
3. **Activity** → find the payment → **Report a problem** → choose the reason:
   - txn 1 → *Item not received*
   - txn 2 → *Item not as described*
   - txn 3 → *Unauthorized / payment I don't recognize*
4. Submit. Repeat for all 3.
5. Tell me "3 disputes filed" + the three case numbers if shown.
**My verification:** `GET /v1/customer/disputes` returns 3 with the expected reason codes and amounts;
the webhook log shows `CUSTOMER.DISPUTE.CREATED` (or reconciliation picks them up within 5 min).
**How I use it:** the 3 demo scenarios become real disputes; payloads are recorded into `fixtures/` so the
demo also runs in **replay** mode if sandbox misbehaves.
**Known sandbox limitation:** if the *Unauthorized* option is unavailable for the funding source used, we
demo scenario ③ from the fixture and label it clearly as simulated — the other two stay real.

---

### M-08 — Sandbox balances (5 min, 24 h before demo)

**What:** confirm the business account is not negative and the buyer has funds.
**Why:** negative sandbox balances make refunds fail with `INSUFFICIENT_FUNDS` mid-pitch; this is the
single most common live-demo failure.
**URL:** `https://www.sandbox.paypal.com/` (business login) → Wallet/Balance
**Steps:** log in, check balance; if negative, use the sandbox **Add funds** / test bank flow, or tell me
and I will re-run the smoke script against a fresh account pair.
**Hand back:** "balance positive" or the error you see.
**My verification:** a $0.01 test refund in a throwaway capture, then I report the refund ID.

---

### M-09 — Hosting accounts (**only if we deploy**)

**What:** Vercel (frontend) + Render or Fly (API) + Neon or Supabase (Postgres).
**Why:** only needed if we want a public URL for judges. **A cloudflared tunnel gives a public HTTPS URL
with no account**, which is enough for webhooks and usually enough for a live demo. My recommendation:
**skip this entirely for the MVP** unless the rules require a hosted link.
**URLs if you decide yes:** `https://vercel.com/new` · `https://dashboard.render.com/` ·
`https://console.neon.tech/`
**Steps:** sign up with GitHub → import the repo → paste env vars from `.env.local` into the provider UI →
deploy. **You** must do this: the provider needs your account authorization; I cannot create accounts.
**Hand back:** the deployed URLs (no secrets in chat — put them in the provider's env UI).
**My verification:** `GET /health/ready` returns 200 from the public URL, a webhook test lands, and the
dashboard loads over HTTPS. I will only say "deployed" after those pass.
**Note:** if we deploy, Vercel's serverless runtime is a poor fit for long-lived SSE and background
workers — that's why the API goes to Render/Fly, not Vercel. I'll confirm before you create anything.

---

### M-10 — Conditional: Disputes API access (only if I report HTTP 403)

**What:** request/enable the Disputes capability on the app.
**Why:** PayPal gates the Disputes API behind an app feature flag and, in some account types, an approval
step. If it's off, every `/v1/customer/disputes` call returns `403 PERMISSION_DENIED`.
**URL:** start from `https://developer.paypal.com/` → your app's settings; if there is no toggle, use the
**Support** entry in the developer dashboard (I will confirm the exact support path from the dashboard UI
before sending you there — I have not verified a deep link and won't invent one).
**Steps:** re-check the app's feature list; if absent, open a support case stating: sandbox REST app,
merchant integration, need `https://uri.paypal.com/services/disputes/read-buyer` and
`.../update-seller` scopes for a hackathon demo.
**Hand back:** the ticket/reference number and whether the toggle appeared.
**Interim:** I keep building against `PAYPAL_MODE=replay` and demo the payments/refund path live.

---

### M-11 — Optional: PayPal Agent Toolkit / MCP (only if your track requires it)

**What:** authorize PayPal's agent-facing tooling if the hackathon track expects it.
**Why:** some tracks give bonus credit for using PayPal's own agent tooling instead of raw REST.
**Honest status:** I have **not verified** the current package, MCP endpoint, or auth flow for this, and I
will not guess at install commands or URLs. Tell me whether M-01's rules mention it; if yes, I will
research the current official docs first and then give you exact steps.
**Default plan:** we use the REST API directly (fully documented above), which satisfies "PayPal integration"
on its own.

---

### M-12 — Devpost submission (last 2 h)

**What:** register/submit with your account.
**Why:** only you can authenticate and accept the terms; eligibility attestations are personal.
**Steps:** I will prepare a submission pack — project name, 200-word description, tech list, repo URL,
3-minute video URL, screenshots, "what we learned", and a demo script. You paste, upload, and submit.
**Hand back:** the submission confirmation screenshot.
**My verification:** I re-read the submitted text against M-01's checklist line by line.

---

## 4. What I can do with zero input from you (starting now)

Repo scaffold · docker-compose Postgres · schema + migrations · FastAPI app + auth stub · **replay-mode
PayPal adapter + fixtures** · policy engine + rules + unit tests · LangGraph topology with stubbed agents ·
Next.js shell + AG Grid on replay data · SSE plumbing · audit log + hash chain · `cloudflared` quick tunnel ·
seed/reset scripts · OpenAPI → TS type generation.

## 5. What I can do only after credentials

Live PayPal auth · dispute sync · real refund/evidence calls · webhook subscription + signature
verification · real LLM agent runs · measured cost/latency · GitHub push · deployment.

## 6. What only you can do (I will never attempt)

Create/verify accounts (phone, email, CAPTCHA, 2FA) · accept ToS · log in as sandbox buyer · file disputes ·
authorize Git/hosting OAuth · record the pitch video · submit on Devpost · approve refund thresholds.

---

## 7. Verification log (append-only)

| # | Claim | Method | Result |
|---|---|---|---|
| V1 | Docker engine usable | `docker info --format` | ✅ `server=29.5.3` (after I started Docker Desktop) |
| V2 | PayPal API reachable from this machine | `GET /v1/oauth2/token` unauthenticated | ✅ HTTP 401 (expected) |
| V3 | Python deps installable | `uv pip compile fastapi` | ✅ resolved 8 packages |
| V4 | `.env.local` cannot be committed | `git check-ignore -v .env.local` | ✅ ignored by `.gitignore:3`; `.env.example` correctly **not** ignored (re-checked after you create the file) |
| V5 | Disputes API enabled on your app | authenticated `GET /v1/customer/disputes` | ⏳ blocked on M-02 |
| V6 | LLM key valid | `GET /v1beta/models` + 8-token call | ⏳ blocked on M-04 |

*Nothing in this file is marked COMPLETED until the corresponding check above actually passes.*
