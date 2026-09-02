"""Fixtures for the QUICKSTART install-e2e.

Sibling to ``install-e2e/conftest.py``, deliberately separate: that suite asserts
the installer's prebuilt-image artifact, this one asserts the SOURCE-DEV path a
contributor actually runs (``clone-repos.sh`` → ``./jarvis init`` →
``./jarvis start --all``) on a clean machine.

The workflow runs ``run_quickstart.sh`` on a rented GPU VM, opens SSH tunnels for
the service ports, and copies the run's ``$RESULT_DIR`` back to the runner. Tests
address ``localhost`` (tunnelled) and read run artifacts from
``JARVIS_QS_RESULTS`` (default ``./qs-results``).

Run locally against an already-up source stack:
    JARVIS_QS_RESULTS=/opt/jarvis-e2e pytest install-e2e/quickstart -v
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests

RESULTS = Path(os.environ.get("JARVIS_QS_RESULTS", "qs-results"))
BASE_URL = "http://localhost"


@dataclass(frozen=True)
class Service:
    name: str
    port: int
    health: str


# Ports come from the ./jarvis SERVICES registry (source-dev publishes on the
# host), NOT from the installer's generated compose — they differ (e.g. admin is
# 7710 here, 7711 there), which is itself part of why the two suites are separate.
HTTP_SERVICES: list[Service] = [
    Service("config-service", 7700, "/health"),
    Service("auth", 7701, "/health"),
    Service("logs", 7702, "/health"),
    Service("command-center", 7703, "/health"),
    Service("llm-proxy", 7704, "/health"),
    Service("whisper", 7706, "/health"),
    Service("tts", 7707, "/health"),
    Service("settings-server", 7708, "/health"),
    Service("admin", 7710, "/health"),
    Service("notifications", 7712, "/health"),
    Service("recipes-server", 7030, "/health"),
    Service("ocr-service", 7031, "/health"),
    Service("web", 7722, "/"),
]

# Known-unhealthy in the source stack as of 2026-09; asserted separately with
# xfail so they're visible without failing the lane. jarvis-mcp is flagged
# "potentially deprecated" in CLAUDE.md and crashes on an MCP SDK API change
# (Server.list_tools removed); jarvis-node-setup never produces a container.
KNOWN_BROKEN: dict[str, str] = {
    "mcp": "jarvis-mcp: Server.list_tools removed from the MCP SDK (repo flagged deprecated)",
    "node-setup": "jarvis-node-setup: no container produced by ./jarvis start --all",
}

CORE_READY = [("config-service", 7700, "/health"), ("auth", 7701, "/health")]


# ── Run artifacts ────────────────────────────────────────────────────────────
def result_text(name: str) -> str:
    """Contents of a run artifact, or '' when the phase never produced it."""
    p = RESULTS / name
    return p.read_text(errors="replace") if p.is_file() else ""


def result_lines(name: str) -> list[str]:
    return [ln.strip() for ln in result_text(name).splitlines() if ln.strip()]


def result_rc(name: str) -> int | None:
    """Exit code a phase recorded, or None when the phase never ran."""
    raw = result_text(name).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def env_values(service: str) -> dict[str, str]:
    """Parsed, pre-redacted .env snapshot for a service (see run_quickstart.sh)."""
    out: dict[str, str] = {}
    for line in result_text(f"env.{service}").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k] = v
    return out


SET_RE = re.compile(r"^<set:len=(\d+)>$")


def secret_state(value: str | None) -> str:
    """Classify a redacted secret: missing / empty / placeholder / set."""
    if value is None:
        return "missing"
    if value == "<empty>":
        return "empty"
    if value.startswith("<placeholder:"):
        return "placeholder"
    if SET_RE.match(value):
        return "set"
    return "unknown"


# ── HTTP helpers ─────────────────────────────────────────────────────────────
def http_status(port: int, path: str, timeout: float = 8.0) -> int | None:
    try:
        return requests.get(f"{BASE_URL}:{port}{path}", timeout=timeout).status_code
    except requests.RequestException:
        return None


def http_ok(port: int, path: str, timeout: float = 8.0) -> bool:
    return http_status(port, path, timeout) == 200


def wait_for_http(port: int, path: str, timeout: float = 300.0, interval: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if http_ok(port, path):
            return True
        time.sleep(interval)
    return False


@pytest.fixture(scope="session", autouse=True)
def _stack_ready() -> None:
    """Block on the control plane so tests assert behaviour, not startup races.

    Does NOT fail the session when the stack never comes up: the phase-level
    tests (init/start exit codes) are the ones that should report that, with the
    captured logs attached. Failing here would mask the actual diagnosis.
    """
    for name, port, path in CORE_READY:
        if not wait_for_http(port, path, timeout=300.0):
            print(f"[conftest] WARNING: {name} never became ready on :{port}{path}")
