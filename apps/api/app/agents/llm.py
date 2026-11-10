"""Minimal Gemini REST client with strict JSON output and honest failure reporting.

No SDK, no hidden retries. If the model is unavailable (quota, 503, timeout) the
caller gets `data=None` plus the error, and falls back to deterministic reasoning.
The UI shows which path was taken — a fallback is never disguised as an LLM result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("resolveai.llm")

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass
class LLMResult:
    data: dict[str, Any] | None
    text: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
    return None


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def available(self) -> bool:
        return bool(self._settings.llm_configured and self._settings.llm_model_fast)

    @property
    def provider(self) -> str:
        return self._settings.llm_provider

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        if not self.available:
            return LLMResult(data=None, error="llm not configured")

        model = model or self._settings.llm_model_fast
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self._settings.llm_temperature
                if temperature is None
                else temperature,
                "maxOutputTokens": max_tokens or self._settings.llm_max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        budget: dict[str, Any] = {}
        if "lite" not in model:
            budget = {"thinkingBudget": 0}

        headers = {"x-goog-api-key": self._settings.llm_api_key}

        async def call(gen_config_extra: dict[str, Any], use_model: str) -> httpx.Response:
            body = {
                **payload,
                "generationConfig": {**payload["generationConfig"], **gen_config_extra},
            }
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.llm_timeout_seconds, connect=10.0)
            ) as client:
                return await client.post(
                    f"{API_ROOT}/{use_model}:generateContent", headers=headers, json=body
                )

        try:
            res = await call(budget, model)
            if res.status_code == 400 and budget:
                # some models reject thinkingConfig; retry once without it
                res = await call({}, model)
            if res.status_code in (429, 503):
                # free-tier spikes are common; one bounded retry keeps runs honest
                await asyncio.sleep(0.9)
                res = await call(budget, model)
            if res.status_code in (429, 503) and (
                self._settings.llm_model_reasoning
                and self._settings.llm_model_reasoning != model
            ):
                model = self._settings.llm_model_reasoning
                budget = {} if "lite" in model else {"thinkingBudget": 0}
                res = await call(budget, model)
        except Exception as exc:
            return LLMResult(
                data=None,
                model=model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"{type(exc).__name__}: {str(exc)[:160]}",
            )

        latency = int((time.perf_counter() - started) * 1000)
        if res.status_code != 200:
            try:
                err = res.json().get("error", {})
                message = f"{res.status_code} {err.get('status', '')}: {str(err.get('message', ''))[:160]}"
            except Exception:
                message = f"{res.status_code}: {res.text[:160]}"
            logger.warning("llm call failed model=%s %s", model, message)
            return LLMResult(data=None, model=model, latency_ms=latency, error=message)

        body = res.json()
        usage = body.get("usageMetadata") or {}
        parts = (
            ((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        )
        text = "".join(p.get("text", "") for p in parts)
        data = _extract_json(text)
        return LLMResult(
            data=data,
            text=text,
            model=model,
            tokens_in=int(usage.get("promptTokenCount") or 0),
            tokens_out=int(usage.get("candidatesTokenCount") or 0)
            + int(usage.get("thoughtsTokenCount") or 0),
            latency_ms=latency,
            error=None if data is not None else "model returned non-JSON output",
            raw=body,
        )


@lru_cache(maxsize=1)
def get_llm() -> LLMClient:
    return LLMClient()
