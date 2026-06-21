"""Shared fixtures + service inventory for the install E2E.

The GitHub workflow generates the *real* compose-export artifact, brings the
stack up, then runs this suite against `localhost` (ports published by the
generated compose). The autouse `_stack_ready` fixture blocks until the core
control plane answers, so individual tests assert behavior rather than racing
startup.

Run locally against an already-up stack:
    pytest install-e2e -v
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import pytest
import requests

# ── Service inventory ────────────────────────────────────────────────────────
# Host ports come straight from the generated compose-export. `container` is the
# fixed container_name the generator emits; `health` is the HTTP path that should
# return 200 once the service is up.


@dataclass(frozen=True)
class Service:
    name: str
    container: str
    port: int
    health: str


# HTTP services (have a published host port + health endpoint)
HTTP_SERVICES: list[Service] = [
    Service("config-service", "jarvis-config-service", 7700, "/health"),
    Service("auth", "jarvis-auth", 7701, "/health"),
    Service("logs", "jarvis-logs", 7702, "/health"),
    Service("command-center", "jarvis-command-center", 7703, "/health"),
    Service("llm-proxy", "jarvis-llm-proxy-api", 7704, "/health"),
    Service("whisper", "jarvis-whisper-api", 7706, "/health"),
    Service("tts", "jarvis-tts", 7707, "/health"),
    Service("settings-server", "jarvis-settings-server", 7708, "/health"),
    Service("admin", "jarvis-admin", 7711, "/health"),
    Service("notifications", "jarvis-notifications", 7712, "/health"),
    Service("web", "jarvis-web", 7722, "/"),
]

# Containers with no published HTTP port we still expect running (infra + worker)
NON_HTTP_CONTAINERS: list[str] = [
    "jarvis-postgres",
    "jarvis-redis",
    "jarvis-loki",
    "jarvis-grafana",
    "jarvis-mosquitto",
    "llm-proxy-worker",
]

ALL_CONTAINERS: list[str] = [s.container for s in HTTP_SERVICES] + NON_HTTP_CONTAINERS

# The control plane the rest of the stack (and these tests) depend on. We block
# on these before running any assertions.
CORE_READY = [
    ("config-service", 7700, "/health"),
    ("auth", 7701, "/health"),
    ("admin", 7711, "/health"),
]

BASE_URL = "http://localhost"


def http_ok(port: int, path: str, timeout: float = 5.0) -> bool:
    try:
        r = requests.get(f"{BASE_URL}:{port}{path}", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def wait_for_http(port: int, path: str, timeout: float = 240.0, interval: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if http_ok(port, path):
            return True
        time.sleep(interval)
    return False


def docker_inspect(container: str, fmt: str) -> str | None:
    """Return `docker inspect -f <fmt> <container>` output, or None if absent."""
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", fmt, container],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def container_health(container: str) -> str | None:
    """'healthy' | 'unhealthy' | 'starting' | 'none' (no healthcheck), or None
    if the container doesn't exist."""
    return docker_inspect(
        container,
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
    )


def wait_for_container_health(container: str, timeout: float = 180.0, interval: float = 3.0) -> str | None:
    """Poll until the container is 'healthy' (or has no healthcheck), else return
    the last status seen. Healthchecks run on a 30s interval, so a freshly-upped
    service sits in 'starting' for a bit before flipping — polling avoids a
    flaky too-eager assertion while still failing on a genuinely broken probe."""
    deadline = time.time() + timeout
    last = container_health(container)
    while time.time() < deadline:
        if last in ("healthy", "none", None):
            return last
        time.sleep(interval)
        last = container_health(container)
    return last


@pytest.fixture(scope="session", autouse=True)
def _stack_ready() -> None:
    """Block until the core control plane is healthy, else fail fast with a hint."""
    for name, port, path in CORE_READY:
        if not wait_for_http(port, path):
            pytest.fail(
                f"core service '{name}' (localhost:{port}{path}) never came up. "
                f"Is the stack running? Check `docker compose ps` / `logs`."
            )
