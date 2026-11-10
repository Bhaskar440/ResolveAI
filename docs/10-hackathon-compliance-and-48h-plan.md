# 10 — Hackathon Compliance & 48-Hour Plan (REAL constraints)

Source: `https://paypalaihackathon.devpost.com/` + Official Rules you pasted. Captured 2026-11-10.

## 1. Hard constraints (these are pass/fail, not preferences)

| # | Requirement | Status | Owner |
|---|---|---|---|
| C1 | **Submission deadline: Fri 2026-11-13, 01:30 IST** (= Thu Nov 12, 12:00 pm PT) | ⏳ ~2.4 days | — |
| C2 | Project must **integrate the PayPal developer platform (sandbox)** and an AI tool/model | On track | Me |
| C3 | **Public** code repo on GitHub/Bitbucket/GitLab | Blocked on M-05 | You |
| C4 | **Open-source license file**, detectable, visible in the repo **About** section | MIT file ready to add | Me + You (repo setting) |
| C5 | Repo contains **all source, assets, setup instructions** | In progress | Me |
| C6 | **Functional demo**: either runnable setup instructions **or** hosted URL. Mockups/prototypes do **not** qualify | Plan: runnable `docker compose up` in replay mode, no credentials needed | Me |
| C7 | **Video < 3 min**, on **YouTube publicly visible**, shows the project working | Blocked on M-13 | You |
| C8 | Text description of features/functionality | Draft at M-12 | Me → You paste |
| C9 | Testing access: judges may need test creds/sandbox logins documented in README | Plan: demo user login in README | Me |
| C10 | English only | ✅ | — |
| C11 | Video must not contain third-party trademarks/music without permission | Keep to our UI + minimal PayPal screens, no music | You (recording) |
| C12 | Original work, no sponsor funding | ✅ | — |
| C13 | Eligibility: India is **not** excluded; solo entrant allowed | ✅ | — |
| C14 | Devpost registration ("Join Hackathon") | Blocked on M-14 | You |

**Not required (so we drop them):** public hosting, AG Grid/APIMatic/other sponsor tools, PayPal Agent
Toolkit/MCP, custom domain, team representative.

**Judging is 5 equally weighted criteria** (Stage Two): Technological Implementation · Design · Potential
Impact · Innovation · Presentation. → **Design and Presentation are 40% of the score.** A beautiful,
runnable demo with a tight video beats extra backend features. This overrides my earlier 4.5-day plan.

**Prize routes we qualify for without extra work:** all Grand Prizes + Honorable Mentions
(notably **Best Use of Agentic Commerce**, **Best Use of PayPal + AI**) + **Best Use of AG Grid**
($5k / $2k / $1k×3). Rule: 1 Grand **or** 1 Honorable + 1 Sponsor prize. So AG Grid usage must be
*visible and deliberate*, not incidental.

## 2. What I changed in the architecture because of the deadline

| Decision | Change | Why |
|---|---|---|
| M-09 hosting | **Dropped** | Rules explicitly allow setup instructions instead of a hosted demo. |
| Alembic | `create_all` in dev, one Alembic baseline if time allows | 2 days solo; schema churn is faster without migration ceremony. Documented tradeoff. |
| Multi-tenant | Single seeded merchant | Schema already carries `merchant_id`; UI doesn't need org switching. |
| Buyer channel | API-seeded, one demo message thread | Saves a UI surface; still demonstrates "resolve before escalation". |
| `make-offer` / appeals | Proposal + audit only, no live execution | Buyer acceptance stalls; `REFUND_*` is deterministic for the video. |
| Live sandbox | **One** proof segment (real refund), rest in replay | Sandbox flakiness cannot be allowed to kill the submission. |
| AG Grid | Community + custom renderers + theme + live SSE updates + master-detail | Sponsor-prize story without an Enterprise license. |

## 3. Hour-by-hour plan (IST)

| Window | Work | Exit check |
|---|---|---|
| **Now → +1h** | You: join Devpost, PayPal app creds, LLM key. Me: compose + schema + policy engine + fixtures | `pytest` green, Postgres up |
| **+1h → +6h** | API routes (disputes read), replay adapter, seed script, AG Grid dashboard on seeded data | Grid shows 3 disputes with SLA + amounts |
| **+6h → +12h** | LangGraph spine: 4 agents, policy gate, executor, SSE trace | One dispute resolves end-to-end in replay |
| **+12h → +18h** | Detail page: timeline, evidence, negotiation transcript, approval dialog, decision card | Approve → executes → row flips |
| **+18h → +26h** | Live sandbox proof: auth, sync, webhook, one real refund | Real refund ID in UI + PayPal activity |
| **+26h → +34h** | Design pass: theming, empty states, metrics header, kill switch, mode badge | Screenshot-ready |
| **+34h → +40h** | README + LICENSE + `.env.example` + fixture-only quickstart + testing creds | Fresh clone runs without credentials |
| **+40h → +44h** | Video: script, record, edit, upload unlisted→public | <3 min, shows live run |
| **+44h → +47h** | Devpost text + screenshots + submit | Confirmation email |
| **+47h → +50h** | Buffer (only for breakage) | — |

Non-negotiable cut line: at **T+40h feature freeze**, whatever works is what ships.

## 4. Submission checklist (fill at M-12)

- [ ] Public repo URL, MIT license visible in About
- [ ] README: one-command quickstart (replay mode, no secrets), screenshots, architecture diagram
- [ ] README: demo login (`analyst@demo.resolveai.dev` / seeded password) + optional sandbox notes
- [ ] YouTube URL, public, <3 min
- [ ] Text description (features, how PayPal is used, how AI is used)
- [ ] Built-with tags: PayPal REST API, Disputes API, Next.js, FastAPI, LangGraph, PostgreSQL, AG Grid
- [ ] Screenshots (grid, decision card, approval, audit dossier, live refund)
- [ ] "How it was built" / challenges note (judges like specifics)
