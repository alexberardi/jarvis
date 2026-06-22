"""Phase 4 — idempotency + data persistence.

Catches the "second install clobbers things" / "restart loses data" class:
  - re-running `docker compose up -d` is a clean no-op (no container recreation),
  - the data layer (postgres bind mount) survives a container restart, so the
    superuser + registered node created during seed are still there afterward.

Gated: runs only when the workflow sets JARVIS_E2E_PERSISTENCE=1 (it needs the
seeded, running stack + the compose invocation to drive). COMPOSE_PROJECT and
JARVIS_E2E_COMPOSE_ARGS ("-f a.yml -f b.yml ...") come from the workflow.
"""
from __future__ import annotations

import os
import subprocess
import time

import pytest
import requests

PROJECT = os.environ.get("COMPOSE_PROJECT", "jarvis")
COMPOSE_ARGS = os.environ.get("JARVIS_E2E_COMPOSE_ARGS", "").split()
ENABLED = os.environ.get("JARVIS_E2E_PERSISTENCE") == "1"

pytestmark = pytest.mark.skipif(
    not (ENABLED and COMPOSE_ARGS), reason="JARVIS_E2E_PERSISTENCE!=1 / no compose args"
)


def _compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, *COMPOSE_ARGS, *args],
        capture_output=True, text=True, timeout=300,
    )


def _container_ids() -> list[str]:
    return sorted(_compose("ps", "-q").stdout.split())


def _setup_status() -> dict:
    return requests.get("http://localhost:7711/api/setup/status", timeout=10).json()


def _wait(predicate, timeout: float = 120.0, interval: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


def test_up_is_idempotent() -> None:
    """Re-running `up -d` must not recreate containers (a second install/apply
    should converge, not churn)."""
    before = _container_ids()
    assert before, "no running containers found for the project"
    r = _compose("up", "-d")
    assert r.returncode == 0, f"re-up failed: {r.stderr[:300]}"
    after = _container_ids()
    assert before == after, (
        "containers were recreated on a second `up -d` — not idempotent\n"
        f"before={before}\nafter={after}"
    )


def test_data_survives_postgres_restart() -> None:
    """The superuser (auth DB) created during seed must survive a postgres
    restart — i.e. data is on the bind mount, not the container layer."""
    assert _setup_status().get("configured") is True, "not configured before restart"

    r = _compose("restart", "postgres")
    assert r.returncode == 0, f"postgres restart failed: {r.stderr[:300]}"

    # auth + admin reconnect to postgres; give them a moment to recover.
    assert _wait(
        lambda: requests.get("http://localhost:7701/health", timeout=5).status_code == 200
    ), "auth did not recover after postgres restart"
    assert _wait(
        lambda: _setup_status().get("configured") is True
    ), "admin no longer 'configured' after postgres restart — data did not persist"
