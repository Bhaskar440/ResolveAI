# ResolveAI - Architecture & Design Set

**Status:** IMPLEMENTED in replay mode, verified end-to-end 2026-11-10 (see
[09](09-manual-actions-checklist.md) V25-V31). Live sandbox execution is the remaining segment and
depends on the manual steps M-03 / M-07 / M-08.
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
| [11-demo-script.md](11-demo-script.md) | **Three-minute demo storyboard for the public deployment, pre-record checklist, YouTube upload steps, claims checklist** |
| [13-deployment-render.md](13-deployment-render.md) | **Render Blueprint, production env, Postgres + pgvector, PayPal sandbox webhook, verification, troubleshooting** |
| [14-submission-checklist.md](14-submission-checklist.md) | **Devpost text, video/repo/license checks, final submission sequence** |

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
| D3 | **Dual-mode PayPal adapter: `sandbox` (live REST API) and `replay` (recorded fixtures).** Same interface. | Sandbox disputes are slow, rate-limited and sometimes unavailable during a demo. Replay guarantees the demo runs. | No |
| D4 | **Typed agent envelopes, bounded negotiation (max 2 rounds), no agent-to-agent free chat.** | Prevents infinite loops, runaway cost, and unparseable transcripts. | No |
| D5 | **Human-in-the-loop implemented as a durable Postgres `approval` row + executor-on-approve**, not a LangGraph `interrupt()`. | The pause survives API restarts without a checkpoint dependency, and the approval is a first-class row the dashboard can query. The graph still produces the proposal; execution stays outside it. | Yes |
| D6 | **Pydantic response models are the contract; TypeScript types mirror them in `lib/api.ts`.** | One reviewable surface, no build-time codegen step for a 2.5-day build. Drift is caught by typechecking the pages. | Yes |
| D7 | **AG Grid Community 36 + infinite row model calling the paginated disputes API** (no Enterprise SSM). | Enterprise server-side row model needs a license; Community's infinite model gives real server pagination. | Yes |
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

## 5. Resolved before the build

1. **Timeline & team size** - solo developer, ~2.5 days. Scope cut to replay-first with one optional live segment.
2. **LLM access** - Google Gemini via REST; `gemini-3.5-flash-lite` fast, `gemini-3.5-flash` reasoning. Free-tier 503/429 is handled by one bounded retry, then a labelled deterministic fallback.
3. **PayPal app scopes** - Disputes + Payments verified against the sandbox (OAuth 200, disputes list 200, captures probe 404-not-403). M-10 not triggered.
4. **AG Grid** - Community 36.3 confirmed; infinite row model + server pagination.
5. **Hosting** - dropped (rules allow runnable setup instructions). Docker Compose is the demo surface; webhooks only matter in sandbox mode.
6. **Branding** - merchant control tower only; buyer side stays simulated/API-seeded, stated in the video.
