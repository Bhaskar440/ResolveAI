"""Read-only credential verification. Never prints secret values.

Run from apps/api:  uv run python -m scripts.verify_credentials
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import get_settings

settings = get_settings()


def fp(value: str) -> str:
    if not value:
        return "MISSING"
    return f"present(len={len(value)}, sha256:{hashlib.sha256(value.encode()).hexdigest()[:6]})"


async def verify_paypal(out: dict) -> None:
    base = settings.paypal_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=25) as client:
        token_res = await client.post(
            f"{base}/v1/oauth2/token",
            auth=(settings.paypal_client_id, settings.paypal_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        out["paypal_token"] = {
            "status": token_res.status_code,
            "expires_in": token_res.json().get("expires_in") if token_res.status_code == 200 else None,
            "error": None if token_res.status_code == 200 else token_res.text[:220],
        }
        if token_res.status_code != 200:
            return

        token = token_res.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        disputes_res = await client.get(
            f"{base}/v1/customer/disputes?page_size=10", headers=auth
        )
        body = {}
        try:
            body = disputes_res.json()
        except Exception:
            pass
        out["disputes_list"] = {
            "status": disputes_res.status_code,
            "count": len(body.get("items", [])) if isinstance(body, dict) else None,
            "total_items": body.get("total_items") if isinstance(body, dict) else None,
            "error": None if disputes_res.status_code == 200 else disputes_res.text[:220],
        }

        probe = await client.get(f"{base}/v2/payments/captures/0NONEXISTENT", headers=auth)
        out["capture_probe"] = {
            "status": probe.status_code,
            "error_name": (probe.json().get("name") if probe.status_code != 200 else None),
        }


async def verify_llm(out: dict) -> None:
    provider = settings.llm_provider.lower()
    key = settings.llm_api_key
    if provider in ("google", "gemini"):
        async with httpx.AsyncClient(timeout=40) as client:
            models = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key},
                params={"pageSize": 50},
            )
            names = []
            if models.status_code == 200:
                names = [m["name"].split("/")[-1] for m in models.json().get("models", [])]
            out["llm_models"] = {
                "status": models.status_code,
                "count": len(names),
                "has_fast": settings.llm_model_fast in names,
                "has_reasoning": settings.llm_model_reasoning in names,
                "sample": names[:6],
                "error": None if models.status_code == 200 else models.text[:220],
            }
            model = settings.llm_model_fast
            gen = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json={
                    "contents": [{"parts": [{"text": "Reply with exactly: OK"}]}],
                    "generationConfig": {"maxOutputTokens": 16, "temperature": 0},
                },
            )
            text = None
            if gen.status_code == 200:
                try:
                    text = gen.json()["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    text = "<no text>"
            out["llm_generate"] = {
                "status": gen.status_code,
                "model": model,
                "reply": text,
                "error": None if gen.status_code == 200 else gen.text[:220],
            }
    elif provider == "openai":
        async with httpx.AsyncClient(timeout=40) as client:
            models = await client.get(
                "https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"}
            )
            names = [m["id"] for m in models.json().get("data", [])] if models.status_code == 200 else []
            out["llm_models"] = {
                "status": models.status_code,
                "count": len(names),
                "has_fast": settings.llm_model_fast in names,
                "has_reasoning": settings.llm_model_reasoning in names,
                "sample": names[:4],
                "error": None if models.status_code == 200 else models.text[:220],
            }
            gen = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.llm_model_fast,
                    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                    "max_completion_tokens": 16,
                },
            )
            text = None
            if gen.status_code == 200:
                text = gen.json()["choices"][0]["message"]["content"]
            out["llm_generate"] = {
                "status": gen.status_code,
                "model": settings.llm_model_fast,
                "reply": text,
                "error": None if gen.status_code == 200 else gen.text[:220],
            }
    else:
        out["llm_models"] = {"status": None, "error": f"unsupported provider '{settings.llm_provider}'"}


async def main() -> None:
    out: dict = {
        "config": {
            "paypal_mode": settings.paypal_mode,
            "paypal_base_url": settings.paypal_base_url,
            "client_id": fp(settings.paypal_client_id),
            "client_secret": fp(settings.paypal_client_secret),
            "llm_provider": settings.llm_provider or "MISSING",
            "llm_key": fp(settings.llm_api_key),
            "model_fast": settings.llm_model_fast or "MISSING",
            "model_reasoning": settings.llm_model_reasoning or "MISSING",
        }
    }
    if settings.paypal_configured:
        await verify_paypal(out)
    else:
        out["paypal_token"] = {"status": None, "error": "credentials missing"}
    if settings.llm_configured:
        await verify_llm(out)
    else:
        out["llm_models"] = {"status": None, "error": "llm not configured"}
    print(json.dumps(out, indent=2))


asyncio.run(main())
