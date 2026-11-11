"""Live QA harness for the ResolveAI workflow.

Run this from ``apps/api`` while the API, web and PostgreSQL containers are up:

    uv run python -m scripts.qa_workflow

The harness is destructive by design: it resets and reseeds the replay dataset so
the result is reproducible. It never touches PayPal's live API and never prints
secrets. Sandbox order creation/capture is covered by the separate
``create_sandbox_orders`` / ``capture_sandbox_orders`` scripts because it needs a
human buyer approval.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.contracts import PaymentPlan
from app.api.v1 import webhooks as webhook_routes
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    AgentRun,
    AuditLog,
    Dispute,
    Merchant,
    Refund,
    WebhookDelivery,
)
from app.db.session import SessionLocal
from app.services import execution, orchestrator

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append(("PASS" if ok else "FAIL", name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def expect_status(name: str, response: httpx.Response, status: int) -> dict[str, Any] | None:
    ok = response.status_code == status
    body: dict[str, Any] | None
    try:
        body = response.json()
    except ValueError:
        body = None
    record(name, ok, f"HTTP {response.status_code} (expected {status})")
    return body


async def login(client: httpx.AsyncClient) -> bool:
    settings = get_settings()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.demo_user_email, "password": settings.demo_user_password},
    )
    body = expect_status("merchant login", response, 200)
    if body is None:
        return False
    record(
        "session mode is replay",
        body.get("mode") == settings.paypal_mode,
        f"mode={body.get('mode')}",
    )
    return True


async def unauth_guard_checks(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as anon:
        attempts = [
            ("seed", "POST", "/api/v1/demo/seed", {}),
            ("reset", "POST", "/api/v1/demo/reset", {}),
            (
                "agent run",
                "POST",
                f"/api/v1/disputes/{uuid.uuid4()}/run",
                None,
            ),
            (
                "approval",
                "POST",
                f"/api/v1/approvals/{uuid.uuid4()}/decide",
                {"approve": True},
            ),
            (
                "payment order",
                "POST",
                "/api/v1/payments/orders",
                {
                    "amount": "1.00",
                    "currency": "USD",
                    "description": "unauthorised probe",
                    "invoice_id": f"QA-UNAUTH-{uuid.uuid4().hex[:8]}",
                },
            ),
            ("knowledge ingest", "POST", "/api/v1/knowledge/ingest", {}),
            ("knowledge search", "POST", "/api/v1/knowledge/search", {"query": "refund"}),
        ]
        for label, method, path, body in attempts:
            response = await anon.request(method, path, json=body)
            expect_status(f"unauthenticated {label} blocked", response, 401)


async def run_workflow(client: httpx.AsyncClient) -> dict[str, str]:
    ids: dict[str, str] = {}

    reset = await client.post("/api/v1/demo/reset")
    expect_status("demo reset", reset, 200)
    seed = await client.post("/api/v1/demo/seed")
    seed_body = expect_status("demo seed", seed, 200)
    if seed_body:
        record(
            "seed loaded replay disputes",
            seed_body.get("mode") == "replay" and seed_body.get("disputes", 0) >= 3,
            f"mode={seed_body.get('mode')} disputes={seed_body.get('disputes')}",
        )

    listed = await client.get("/api/v1/disputes", params={"limit": 100})
    body = expect_status("list disputes", listed, 200)
    if body:
        for item in body.get("items", []):
            ids[item["paypal_case_number"]] = item["id"]
    record(
        "complaint intake has three cases",
        {"PP-D-91001", "PP-D-91002", "PP-D-91003"}.issubset(ids),
        f"case_numbers={sorted(ids)}",
    )

    # Payment lifecycle in replay: order -> capture -> idempotent recapture.
    invoice = f"QA-{uuid.uuid4().hex[:10]}"
    created = await client.post(
        "/api/v1/payments/orders",
        json={
            "amount": "12.34",
            "currency": "USD",
            "description": "QA replay order",
            "invoice_id": invoice,
        },
    )
    order = expect_status("create replay payment order", created, 201)
    paypal_order_id = (order or {}).get("paypal_order_id")
    record(
        "replay order is clearly simulated",
        bool(order and order.get("simulated") is True),
        f"order_id={paypal_order_id} simulated={order.get('simulated') if order else None}",
    )
    if paypal_order_id:
        captured = await client.post(
            f"/api/v1/payments/orders/{paypal_order_id}/capture",
            params={"idempotency_key": "qa-capture-key"},
        )
        capture_body = expect_status("capture replay payment", captured, 200)
        capture = (capture_body or {}).get("capture") or {}
        record(
            "capture is completed and simulated",
            capture.get("status") == "COMPLETED" and capture.get("simulated") is True,
            f"capture={capture.get('paypal_capture_id')} status={capture.get('status')}",
        )
        recaptured = await client.post(
            f"/api/v1/payments/orders/{paypal_order_id}/capture",
            params={"idempotency_key": "qa-capture-key"},
        )
        recapture_body = expect_status("duplicate capture is idempotent", recaptured, 200)
        record(
            "duplicate capture reuses the same capture id",
            ((recapture_body or {}).get("capture") or {}).get("paypal_capture_id")
            == capture.get("paypal_capture_id"),
            f"first={capture.get('paypal_capture_id')} second={((recapture_body or {}).get('capture') or {}).get('paypal_capture_id')}",
        )

    # 91001: INR within the autonomous cap -> agent refunds in replay.
    case_91001 = ids.get("PP-D-91001")
    if case_91001:
        started = await client.post(f"/api/v1/disputes/{case_91001}/run")
        run = expect_status("execute LangGraph workflow (91001)", started, 200)
        record(
            "agent completed autonomous INR case",
            bool(run and run.get("status") == "COMPLETED"),
            f"run_status={(run or {}).get('status')} run_id={(run or {}).get('id')}",
        )
        detail = await client.get(f"/api/v1/disputes/{case_91001}")
        detail_body = expect_status("read 91001 case detail", detail, 200) or {}
        dispute = detail_body.get("dispute") or {}
        refunds = detail_body.get("refunds") or []
        record(
            "91001 resolved with one simulated refund",
            dispute.get("status") == "RESOLVED"
            and len(refunds) == 1
            and refunds[0].get("simulated") is True,
            f"status={dispute.get('status')} refunds={len(refunds)} simulated={refunds[0].get('simulated') if refunds else None}",
        )
        record(
            "replay refund id is labelled REPLAY-RF",
            bool(refunds and str(refunds[0].get("paypal_refund_id", "")).startswith("REPLAY-RF-")),
            f"refund_id={refunds[0].get('paypal_refund_id') if refunds else None}",
        )
        if run and run.get("id"):
            run_detail = await client.get(f"/api/v1/runs/{run['id']}")
            trace = expect_status("read agent run trace", run_detail, 200) or {}
            nodes = {step.get("node") for step in trace.get("steps", [])}
            record(
                "trace includes evidence retrieval and merchant evidence",
                {"knowledge_retrieval", "merchant", "resolution", "payment"}.issubset(nodes),
                f"nodes={sorted(nodes)}",
            )
            decision = detail_body.get("decision") or {}
            citations = decision.get("policy_citations") or []
            record(
                "recommendation cites retrieved policy",
                bool(decision.get("decision_code")) and len(citations) > 0,
                f"decision={decision.get('decision_code')} citations={len(citations)}",
            )

        # Duplicate execution at the executor boundary: same signed plan twice.
        async with SessionLocal() as session:
            run_row = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.dispute_id == uuid.UUID(case_91001))
                    .order_by(AgentRun.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            dispute_row = await session.get(Dispute, uuid.UUID(case_91001))
            if run_row and dispute_row:
                plan_row = None
                from app.db.models import AgentStep

                step = (
                    await session.execute(
                        select(AgentStep)
                        .where(AgentStep.run_id == run_row.id, AgentStep.node == "payment")
                        .order_by(AgentStep.seq.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if step:
                    plan_row = (step.payload or {}).get("plan")
                if plan_row:
                    before = (
                        await session.execute(
                            select(func.count()).select_from(Refund).where(
                                Refund.dispute_id == dispute_row.id
                            )
                        )
                    ).scalar_one()
                    again = await execution.execute_plan(
                        session,
                        plan=PaymentPlan(**plan_row),
                        dispute=dispute_row,
                        initiated_by="qa",
                    )
                    after = (
                        await session.execute(
                            select(func.count()).select_from(Refund).where(
                                Refund.dispute_id == dispute_row.id
                            )
                        )
                    ).scalar_one()
                    record(
                        "duplicate signed refund is idempotent",
                        again is not None and before == after == 1,
                        f"refunds_before={before} refunds_after={after}",
                    )

        rerun = await client.post(f"/api/v1/disputes/{case_91001}/run")
        expect_status("re-running a resolved dispute is rejected", rerun, 409)

    # 91002: approval gate + human-executed simulated refund.
    case_91002 = ids.get("PP-D-91002")
    if case_91002:
        started = await client.post(f"/api/v1/disputes/{case_91002}/run")
        run = expect_status("execute LangGraph workflow (91002)", started, 200)
        record(
            "91002 waits for merchant approval",
            bool(run and run.get("status") == "WAITING_APPROVAL"),
            f"run_status={(run or {}).get('status')}",
        )
        detail = await client.get(f"/api/v1/disputes/{case_91002}")
        detail_body = expect_status("read 91002 case detail", detail, 200) or {}
        approval = next(
            (a for a in detail_body.get("approvals", []) if a.get("status") == "pending"),
            None,
        )
        record(
            "approval request is pending",
            approval is not None,
            f"approval_id={(approval or {}).get('id')}",
        )
        if approval:
            # Unauthenticated refund attempt must not create a refund.
            async with httpx.AsyncClient(base_url=str(client.base_url), timeout=60.0) as anon:
                denied = await anon.post(
                    f"/api/v1/approvals/{approval['id']}/decide",
                    json={"approve": True, "note": "QA unauthorised attempt"},
                )
                expect_status("unauthorised refund attempt blocked", denied, 401)
            after_denied = await client.get(f"/api/v1/disputes/{case_91002}")
            denied_body = expect_status("read 91002 after denied attempt", after_denied, 200) or {}
            record(
                "denied attempt did not move money",
                len(denied_body.get("refunds", [])) == 0,
                f"refunds={len(denied_body.get('refunds', []))}",
            )

            approved = await client.post(
                f"/api/v1/approvals/{approval['id']}/decide",
                json={"approve": True, "note": "QA approval"},
            )
            approval_body = expect_status("merchant approves refund", approved, 200)
            record(
                "approval is recorded",
                bool(approval_body and approval_body.get("status") == "approved"),
                f"status={(approval_body or {}).get('status')}",
            )
            after = await client.get(f"/api/v1/disputes/{case_91002}")
            after_body = expect_status("read 91002 after approval", after, 200) or {}
            refunds = after_body.get("refunds", [])
            record(
                "approved refund is simulated in replay",
                len(refunds) == 1 and refunds[0].get("simulated") is True,
                f"refunds={len(refunds)} simulated={refunds[0].get('simulated') if refunds else None}",
            )
            duplicate = await client.post(
                f"/api/v1/approvals/{approval['id']}/decide",
                json={"approve": True, "note": "QA duplicate approval"},
            )
            expect_status("duplicate approval/refund rejected", duplicate, 409)

    # Invalid transactions / ids.
    invalid_uuid = str(uuid.uuid4())
    checks = [
        ("unknown dispute run", "POST", f"/api/v1/disputes/{invalid_uuid}/run", None, 404),
        ("malformed dispute id", "GET", "/api/v1/disputes/not-a-uuid", None, 422),
        ("unknown order", "GET", f"/api/v1/payments/orders/UNKNOWN-{uuid.uuid4().hex}", None, 404),
        ("unknown capture", "GET", f"/api/v1/payments/captures/UNKNOWN-{uuid.uuid4().hex}", None, 404),
        ("unknown refund", "GET", f"/api/v1/payments/refunds/UNKNOWN-{uuid.uuid4().hex}", None, 404),
        (
            "unknown approval",
            "POST",
            f"/api/v1/approvals/{invalid_uuid}/decide",
            {"approve": True},
            404,
        ),
    ]
    for label, method, path, payload, status in checks:
        response = await client.request(method, path, json=payload)
        expect_status(label, response, status)

    # Dashboard and audit history update.
    metrics = await client.get("/api/v1/metrics")
    metrics_body = expect_status("dashboard metrics", metrics, 200) or {}
    analytics = await client.get("/api/v1/metrics/analytics")
    analytics_body = expect_status("dashboard analytics", analytics, 200) or {}
    record(
        "dashboard counts a resolved case",
        metrics_body.get("resolved", 0) >= 1,
        f"resolved={metrics_body.get('resolved')} escalated={metrics_body.get('escalated')}",
    )
    refund_summary = analytics_body.get("refunds") or {}
    record(
        "analytics separates simulated from live refunds",
        refund_summary.get("simulated", 0) >= 1 and refund_summary.get("live", 0) == 0,
        f"simulated={refund_summary.get('simulated')} live={refund_summary.get('live')}",
    )

    async with SessionLocal() as session:
        actions = (
            (
                await session.execute(
                    select(AuditLog.action).order_by(AuditLog.id.asc())
                )
            )
            .scalars()
            .all()
        )
        record(
            "immutable audit trail recorded approval and refund",
            "approval.approved" in actions and "refund.executed" in actions,
            f"actions={sorted(set(actions))}",
        )
        approval_actor = (
            await session.execute(
                select(AuditLog.actor_id, AuditLog.actor_type)
                .where(AuditLog.action == "approval.approved")
                .order_by(AuditLog.id.desc())
                .limit(1)
            )
        ).first()
        record(
            "approval audit attributes the signed-in merchant user",
            bool(approval_actor and approval_actor[0] and approval_actor[1] == "human"),
            f"actor_type={approval_actor[1] if approval_actor else None} actor_id={'set' if approval_actor and approval_actor[0] else 'missing'}",
        )

    return ids


async def webhook_checks(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        invalid = await client.post(
            "/api/v1/webhooks/paypal",
            content=b"{",
            headers={"content-type": "application/json"},
        )
        expect_status("webhook rejects malformed JSON", invalid, 400)

        event_id = f"QA-WH-{uuid.uuid4().hex}"
        event = {
            "id": event_id,
            "event_type": "CUSTOMER.DISPUTE.CREATED",
            "resource": {"dispute_id": "PP-D-QA-WEBHOOK"},
        }
        first = await client.post("/api/v1/webhooks/paypal", json=event)
        first_body = expect_status("replay webhook receipt is stored", first, 200) or {}
        record(
            "replay webhook reports signature_valid=false honestly",
            first_body.get("signature_valid") is False,
            f"signature_valid={first_body.get('signature_valid')} status={first_body.get('status')}",
        )
        second = await client.post("/api/v1/webhooks/paypal", json=event)
        second_body = expect_status("duplicate webhook is detected", second, 200) or {}
        record(
            "duplicate webhook is not processed twice",
            second_body.get("status") == "duplicate",
            f"status={second_body.get('status')} event_id={event_id}",
        )

    # Verify the sandbox-only signature gate and the failed-processing handler at
    # the route boundary. These checks do not call PayPal or the live API.
    original_mode = webhook_routes.settings.paypal_mode
    original_get_adapter = webhook_routes.get_adapter

    class _Request:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload
            self.headers: dict[str, str] = {}

        async def body(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    class _Adapter:
        def __init__(self, valid: bool) -> None:
            self.valid = valid

        async def verify_webhook(self, headers, event) -> bool:
            return self.valid

    try:
        webhook_routes.settings.paypal_mode = "sandbox"
        webhook_routes.get_adapter = lambda: _Adapter(False)  # type: ignore[assignment]
        try:
            await webhook_routes.paypal_webhook(_Request({}), None)  # type: ignore[arg-type]
            record("sandbox webhook rejects invalid signature", False, "no exception raised")
        except AppError as exc:
            record(
                "sandbox webhook rejects invalid signature",
                exc.status_code == 400 and exc.code == "INVALID_SIGNATURE",
                f"HTTP {exc.status_code} {exc.code}",
            )

        webhook_routes.get_adapter = lambda: _Adapter(True)  # type: ignore[assignment]
        fail_event = {
            "id": f"QA-WH-FAIL-{uuid.uuid4().hex}",
            "event_type": "CUSTOMER.DISPUTE.CREATED",
            "resource": {
                "dispute_id": f"QA-WH-FAIL-{uuid.uuid4().hex[:8]}",
                "disputed_transactions": [
                    {"transaction_amount": {"value": "not-a-number", "currency_code": "USD"}}
                ],
            },
        }
        async with SessionLocal() as session:
            result = await webhook_routes.paypal_webhook(
                _Request(fail_event), session  # type: ignore[arg-type]
            )
            record(
                "webhook processing failure is persisted, not swallowed",
                result.get("status") == "failed",
                f"status={result.get('status')}",
            )
            row = (
                await session.execute(
                    select(WebhookDelivery).where(
                        WebhookDelivery.event_id == fail_event["id"]
                    )
                )
            ).scalar_one_or_none()
            record(
                "failed webhook delivery has an error record",
                bool(row and row.status == "failed" and row.last_error),
                f"delivery_status={row.status if row else None} last_error={'set' if row and row.last_error else 'missing'}",
            )
    finally:
        webhook_routes.settings.paypal_mode = original_mode
        webhook_routes.get_adapter = original_get_adapter


async def missing_evidence_check() -> None:
    async with SessionLocal() as session:
        merchant = (await session.execute(select(Merchant).limit(1))).scalar_one()
        dispute = Dispute(
            merchant_id=merchant.id,
            paypal_dispute_id=f"QA-MISSING-{uuid.uuid4().hex[:10]}",
            paypal_case_number=f"QA-MISSING-{uuid.uuid4().hex[:10]}",
            reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            reason_detail="QA case intentionally has no order, capture or tracking.",
            status="OPEN",
            paypal_status="WAITING_FOR_SELLER_RESPONSE",
            lifecycle_stage="INQUIRY",
            amount=Decimal("20.00"),
            currency="USD",
            raw={"qa": True},
        )
        session.add(dispute)
        await session.commit()
        await session.refresh(dispute)
        run = await orchestrator.run_dispute(session, dispute.id, trigger="qa")
        await session.refresh(dispute)
        record(
            "missing evidence stops adjudication without money movement",
            run.status == "NEEDS_INFO" and dispute.status == "AWAITING_INFO",
            f"run_status={run.status} dispute_status={dispute.status}",
        )
        refund_count = (
            await session.execute(
                select(func.count()).select_from(Refund).where(Refund.dispute_id == dispute.id)
            )
        ).scalar_one()
        record(
            "missing evidence case has no refund",
            refund_count == 0,
            f"refunds={refund_count}",
        )


async def agent_failure_check() -> None:
    async with SessionLocal() as session:
        dispute = (
            await session.execute(
                select(Dispute)
                .where(Dispute.paypal_case_number == "PP-D-91003")
                .limit(1)
            )
        ).scalar_one_or_none()
        if dispute is None:
            record("agent failure leaves a recoverable case", False, "91003 not found")
            return
        prior = dispute.status
        original_graph = orchestrator.GRAPH

        class _BrokenGraph:
            async def ainvoke(self, *args, **kwargs):
                raise RuntimeError("QA forced agent graph failure")

        orchestrator.GRAPH = _BrokenGraph()  # type: ignore[assignment]
        raised = False
        try:
            await orchestrator.run_dispute(session, dispute.id, trigger="qa-failure")
        except RuntimeError:
            raised = True
        finally:
            orchestrator.GRAPH = original_graph
        await session.refresh(dispute)
        failed_run = (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.dispute_id == dispute.id)
                .order_by(AgentRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        record(
            "agent failure is surfaced and case status restored",
            raised
            and failed_run is not None
            and failed_run.status == "FAILED"
            and failed_run.error_code == "GRAPH_ERROR"
            and dispute.status == prior,
            f"raised={raised} run={failed_run.status if failed_run else None} dispute={dispute.status}",
        )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--skip-service-failure-checks",
        action="store_true",
        help="skip the in-process missing-evidence and graph-failure probes",
    )
    args = parser.parse_args()

    await unauth_guard_checks(args.base_url)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=240.0) as client:
        bad_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@northwind.example", "password": "definitely-wrong"},
        )
        expect_status("wrong password rejected", bad_login, 401)
        if not await login(client):
            print("cannot continue without a session")
            return 2
        await run_workflow(client)

    await webhook_checks(args.base_url)
    if not args.skip_service_failure_checks:
        await missing_evidence_check()
        await agent_failure_check()

    # Leave the demo in the documented clean state after destructive probes.
    async with httpx.AsyncClient(base_url=args.base_url, timeout=240.0) as client:
        if await login(client):
            reset = await client.post("/api/v1/demo/reset")
            expect_status("restore demo reset", reset, 200)
            seed = await client.post("/api/v1/demo/seed")
            expect_status("restore demo seed", seed, 200)

    failed = [row for row in RESULTS if row[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed, {len(RESULTS)} checks")
    for status, name, detail in RESULTS:
        print(f"{status:4} {name}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
