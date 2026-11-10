# ResolveAI — Architecture & Design Set

**Status:** DRAFT v0.1 — awaiting approval. No application code written yet.
**Scope:** PayPal AI Hackathon MVP. Autonomous dispute resolution with a human approval gate.

| Doc | Contents |
|---|---|
| [01-system-architecture.md](01-system-architecture.md) | System context, components, folder structure, dispute state machine, LangGraph topology |
| [02-database-schema.md](02-database-schema.md) | ERD, entity/column specification, indexes, invariants |
| [03-api-spec.md](03-api-spec.md) | REST endpoints, contracts, errors, pagination, idempotency, SSE |
| [04-agents.md](04-agents.md) | The 4 agents, tool permissions, message protocol, autonomy matrix, guardrails |
| [05-paypal-integration.md](05-paypal-integration.md) | OAuth, read/write flows, webhooks, seeding, sandbox limitations, reconciliation |
| [06-security.md](06-security.md) | Threat model, secret handling, tenant isolation, audit, prompt-injection defense |
| [07-milestones-and-risks.md](07-milestones-and-risks.md) | M0–M5 plan with exit criteria, risk register, demo script |
| [08-environment-variables.md](08-environment-variables.md) | Full env var list with secret/optional flags |
| [09-manual-actions-checklist.md](09-manual-actions-checklist.md) | Every action that needs you: accounts, credentials, approvals, status board, verification log |
| [10-hackathon-compliance-and-48h-plan.md](10-hackathon-compliance-and-48h-plan.md) | **Binding rules, pass/fail requirements, hour-by-hour plan for the Nov 13 deadline** |

---

## 1. One-paragraph summary

ResolveAI ingests PayPal disputes (webhook + polling reconciliation), builds a factual case file
(order, capture, tracking, policy, prior buyer contact), runs a **LangGraph** case graph where four
specialist agents — **Buyer**, **Merchant**, **Resolution**, **Payment** — negotiate over a *typed
message protocol* rather than free text, produces a **decision with a confidence score and cited
evidence**, and then executes it against the PayPal Disputes API (accept claim, provide evidence,
make offer, refund) **only after passing a deterministic policy gate** and, above a configured
threshold, a **human approval**. Every step is persisted, replayable and auditable. A Next.js +
AG Grid dashboard is the merchant control tower.

---

## 2. Decisions that define the build (read these first)

| # | Decision | Why | Reversible? |
|---|---|---|---|
| D1 | **Agents never call PayPal write endpoints directly.** They emit `ProposedAction` objects; a policy gate + executor performs them. | Removes the "LLM refunded $4,000" failure mode entirely; makes actions testable without an LLM. | No |
| D2 | **Deterministic policy engine first, LLM second.** Rules decide eligibility/envelope; the LLM reasons, gathers evidence, and writes rationale. | Judges will probe "is this just a chatbot?" Rules give a defensible answer. | No |
| D3 | **Dual-mode PayPal adapter: `live` (sandbox API) and `replay` (recorded fixtures).** Same interface. | Sandbox disputes are slow, rate-limited and sometimes unavailable during a demo. Replay guarantees the demo runs. | No |
| D4 | **Typed agent envelopes, bounded negotiation (max 3 rounds), no agent-to-agent free chat.** | Prevents infinite loops, runaway cost, and unparseable transcripts. | No |
| D5 | **Human-in-the-loop via LangGraph `interrupt()` + Postgres checkpointer**, not an ad-hoc approval table. | Durable pause/resume across restarts; the pause is part of the graph. | Yes |
| D6 | **OpenAPI is the contract**; TS types for the frontend are generated from it. | One source of truth, no drift between FastAPI and Next.js. | Yes |
| D7 | **AG Grid Community + server-side pagination for MVP** (no Enterprise SSM). | Enterprise server-side row model needs a license; Community cannot do it. | Yes |
| D8 | **Single-tenant demo, multi-tenant schema.** Every row carries `merchant_id`. | Cheap now, no painful migration later. | No |

---

## 3. MVP scope: in / out

**In (must work end-to-end)**
- Dispute arrives via PayPal webhook (and via reconciliation poll) → persisted once (idempotent).
- Case file assembled from order/capture/dispute data + merchant policy + uploaded evidence.
- Four agents produce: buyer claim summary, merchant defense, resolution decision, payment plan.
- Decision → policy gate → (approval if needed) → execution in PayPal sandbox → dashboard updates.
- Three demo scenarios: INR auto-refund, SNAD partial offer, unauthorized/escalate.
- Full audit trail + per-agent trace visible in the UI.
- Kill switch and per-merchant autonomy thresholds.

**Out (explicitly deferred)**
- Real buyer channel (email/IMAP ingestion, buyer portal auth) — buyer side is simulated/API-seeded.
- Multi-currency, non-USD, localization, appeals, arbitration representation.
- Billing, org management, SSO/SAML, mobile app.
- Model fine-tuning, RAG over a large document corpus (MVP: small curated KB).
- Production PayPal live credentials.

---

## 4. Approved-demo definition of done

> From a webhook arriving to a resolved dispute in the dashboard in **under 5 minutes**, with the
> refund visible in the PayPal sandbox seller activity, with zero manual DB edits, and a replayable
> trace. Above-threshold actions must block in `AWAITING_APPROVAL` until a human clicks Approve.

---

## 5. Open questions I need answered before M1

1. **Timeline & team size** — how many dev-days, and who owns frontend vs backend? (Plan assumes ~4.5 dev-days, 2 engineers, parallel tracks.)
2. **LLM access** — OpenAI/Anthropic/Google key available? Which model families are allowed? Gateway preference (direct vs OpenRouter)?
3. **PayPal app scopes** — is the sandbox app provisioned with the Disputes feature enabled? (This is the #1 blocker; see 05 §6.)
4. **AG Grid** — confirm Community is acceptable (no server-side row model) or provide an Enterprise license key.
5. **Hosting for the demo** — local Docker + Cloudflare/ngrok tunnel, or deployed (Vercel + Fly/Render)? Webhooks need a public URL.
6. **Branding bar** — do we need the buyer-facing experience to look like a real product surface, or is API-seeded buyer simulation enough?
