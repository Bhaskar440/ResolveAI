"""Smoke-test a deployed ResolveAI instance.

Examples:
    python scripts/verify_deployment.py \
        --web https://resolveai-web.onrender.com \
        --api https://resolveai-api.onrender.com

    python scripts/verify_deployment.py --web ... --api ... --seed

The script only performs read checks by default. ``--seed`` signs in through the
public web origin (which exercises the Next.js /api/v1 proxy and the session
cookie) and then calls the session-guarded demo seed endpoint.

No secret is printed. Exit code 0 means every requested check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any

DEFAULT_EMAIL = "owner@northwind.example"
DEFAULT_PASSWORD = "resolveai-demo"


class CheckFailed(RuntimeError):
    pass


def _url(base: str, path: str) -> str:
    return urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 45.0,
) -> tuple[int, str, dict[str, str]]:
    data = None
    headers = {"accept": "application/json", "user-agent": "resolveai-verify/1.0"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="replace")
            return res.status, body, {k.lower(): v for k, v in res.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, {k.lower(): v for k, v in exc.headers.items()}
    except urllib.error.URLError as exc:
        raise CheckFailed(f"cannot reach {url}: {exc.reason}") from exc


def _json(body: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise CheckFailed(f"expected JSON, got: {body[:200]!r}") from exc


def _check(name: str, fn) -> None:
    try:
        detail = fn()
    except CheckFailed as exc:
        print(f"FAIL  {name}: {exc}")
        raise
    except Exception as exc:  # noqa: BLE001 - report, do not hide
        print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        raise
    print(f"PASS  {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", required=True, help="Public Next.js origin")
    parser.add_argument("--api", required=True, help="Public FastAPI origin")
    parser.add_argument("--seed", action="store_true", help="Log in and seed demo data")
    parser.add_argument("--email", default=os.getenv("DEMO_USER_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--password", default=os.getenv("DEMO_USER_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    failures = 0

    def check(name: str, fn) -> None:
        nonlocal failures
        try:
            _check(name, fn)
        except Exception:  # noqa: BLE001
            failures += 1

    def api_health_live() -> str:
        status, body, _ = _request(opener, _url(args.api, "/health/live"), timeout=args.timeout)
        if status != 200:
            raise CheckFailed(f"HTTP {status}: {body[:200]}")
        return "ok"

    def api_health_ready() -> str:
        status, body, _ = _request(opener, _url(args.api, "/health/ready"), timeout=args.timeout)
        if status != 200:
            raise CheckFailed(f"HTTP {status}: {body[:300]}")
        data = _json(body)
        if not data.get("db"):
            raise CheckFailed(f"database not ready: {data}")
        return f"db=true mode={data.get('mode')}"

    def api_status() -> str:
        status, body, _ = _request(
            opener, _url(args.api, "/api/v1/system/status"), timeout=args.timeout
        )
        if status != 200:
            raise CheckFailed(f"HTTP {status}: {body[:300]}")
        data = _json(body)
        db = data.get("db") or {}
        if not db.get("connected"):
            raise CheckFailed(f"db.connected is false: {db.get('error')}")
        caps = data.get("capabilities") or {}
        return (
            f"env={data.get('env')} mode={data.get('mode')} "
            f"disputes={data.get('counts', {}).get('disputes')} "
            f"live_paypal={caps.get('live_paypal')}"
        )

    def api_policy() -> str:
        status, body, _ = _request(
            opener, _url(args.api, "/api/v1/policy/rules"), timeout=args.timeout
        )
        if status != 200:
            raise CheckFailed(f"HTTP {status}: {body[:300]}")
        data = _json(body)
        thresholds = data.get("thresholds") or {}
        return f"version={data.get('version')} auto_cap={thresholds.get('auto_resolve_cap')}"

    def web_login_page() -> str:
        status, body, _ = _request(opener, _url(args.web, "/login"), timeout=args.timeout)
        if status != 200:
            raise CheckFailed(f"HTTP {status}")
        if "ResolveAI" not in body:
            raise CheckFailed("page did not contain ResolveAI")
        return "200"

    def web_proxy() -> str:
        status, body, _ = _request(
            opener, _url(args.web, "/api/v1/system/status"), timeout=args.timeout
        )
        if status != 200:
            raise CheckFailed(f"HTTP {status}: {body[:300]}")
        data = _json(body)
        return f"proxy ok, app={data.get('app')} mode={data.get('mode')}"

    def web_root() -> str:
        status, body, headers = _request(opener, _url(args.web, "/"), timeout=args.timeout)
        if status != 200:
            raise CheckFailed(f"HTTP {status}")
        if "ResolveAI" not in body:
            raise CheckFailed("root page did not contain ResolveAI")
        return "200 (auth redirect resolved)"

    check("API /health/live", api_health_live)
    check("API /health/ready", api_health_ready)
    check("API /api/v1/system/status", api_status)
    check("API /api/v1/policy/rules", api_policy)
    check("Web /login", web_login_page)
    check("Web /api/v1 proxy", web_proxy)
    check("Web /", web_root)

    if args.seed:
        def seed() -> str:
            login_status, login_body, _ = _request(
                opener,
                _url(args.web, "/api/v1/auth/login"),
                method="POST",
                payload={"email": args.email, "password": args.password},
                timeout=args.timeout,
            )
            if login_status != 200:
                raise CheckFailed(
                    f"login HTTP {login_status}: {login_body[:300]} "
                    "(set --email/--password or DEMO_USER_* env vars)"
                )
            seed_status, seed_body, _ = _request(
                opener,
                _url(args.web, "/api/v1/demo/seed"),
                method="POST",
                payload={},
                timeout=max(args.timeout, 120.0),
            )
            if seed_status != 200:
                raise CheckFailed(f"seed HTTP {seed_status}: {seed_body[:300]}")
            data = _json(seed_body)
            return f"disputes={data.get('disputes')} mode={data.get('mode')}"

        check("Login + seed via web proxy", seed)

    print()
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("All deployment checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
