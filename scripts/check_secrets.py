"""Fail if a credential is present in tracked files or Git history.

Usage:
    python scripts/check_secrets.py
    python scripts/check_secrets.py --history

The scanner prints file names and line numbers, never the matched value.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".md", ".txt", ".env", ".example", ".sql", ".sh",
    ".ps1", ".dockerfile", ".gitignore", ".gitattributes", "",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next", ".pytest_cache", ".ruff_cache"}

# Deliberately conservative: these formats have very low false-positive rates.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("PayPal client secret assignment", re.compile(r"PAYPAL_CLIENT_SECRET[ \t]*=[ \t]*[^\s#\n]{8,}")),
    ("LLM API key assignment", re.compile(r"LLM_API_KEY[ \t]*=[ \t]*[^\s#\n]{8,}")),
]

PLACEHOLDER = re.compile(r"^(|changeme|change-me|replace-me|your[-_]|example|dummy|xxx+|<.*>)$", re.I)


def _tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"FAIL cannot list tracked files: {exc}")
        raise SystemExit(2) from exc
    return [ROOT / p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def _sensitive_env_values() -> dict[str, str]:
    path = ROOT / ".env.local"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if not re.search(r"SECRET|KEY|PEPPER|TOKEN|PASSWORD", key, re.I):
            continue
        if key.startswith("DEMO_USER_PASSWORD"):
            continue
        if len(value) < 16 or PLACEHOLDER.match(value):
            continue
        if value.startswith("postgresql") or value.startswith("postgres://"):
            continue
        values[key] = value
    return values


def scan_files(files: list[Path], env_values: dict[str, str]) -> list[str]:
    findings: list[str] = []
    for path in files:
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {".env.example"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(ROOT)
        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line_no}: {label}")
        for key, value in env_values.items():
            if value in text:
                findings.append(f"{rel}: contains the value of {key} from .env.local")
    return findings


def scan_history(env_values: dict[str, str]) -> list[str]:
    if not env_values:
        return []
    try:
        history = subprocess.run(
            ["git", "log", "-p", "--all", "--", "."],
            cwd=ROOT,
            check=False,
            capture_output=True,
        ).stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return []
    findings: list[str] = []
    for key, value in env_values.items():
        if value in history:
            findings.append(f"git history contains the value of {key} from .env.local")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="also scan git log -p --all")
    args = parser.parse_args()

    env_values = _sensitive_env_values()
    findings = scan_files(_tracked_files(), env_values)
    if args.history:
        findings.extend(scan_history(env_values))

    if findings:
        print("FAIL potential secrets found:")
        for finding in findings:
            print(f"  - {finding}")
        print("\nRemove the value, rotate the credential, and rewrite history if it was committed.")
        return 1

    print("PASS no committed credentials detected.")
    if env_values:
        print(f"     checked {len(env_values)} sensitive values from .env.local")
    if args.history:
        print("     git history scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
