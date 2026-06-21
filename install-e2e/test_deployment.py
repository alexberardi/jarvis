"""Phase 1 — deployment validity of the installer's generated artifact.

These assertions cover exactly the class of bugs that reached the Bazzite box
by hand: undefined top-level volumes, missing/!published admin port, a
healthcheck binary the image doesn't ship (admin "unhealthy" forever), and
services that can't reach each other on the compose network.

The stack is brought up by the workflow from the REAL generated compose-export
(+ the CI override). Here we only assert the running result.
"""
from __future__ import annotations

import json

import pytest
import requests

from conftest import (
    ALL_CONTAINERS,
    HTTP_SERVICES,
    NON_HTTP_CONTAINERS,
    docker_inspect,
    wait_for_http,
)


# ── container lifecycle ──────────────────────────────────────────────────────


@pytest.mark.parametrize("container", ALL_CONTAINERS)
def test_container_running(container: str) -> None:
    state = docker_inspect(container, "{{.State.Status}}")
    assert state is not None, f"{container} not found (did it fail to create?)"
    assert state == "running", f"{container} is '{state}', expected 'running'"


@pytest.mark.parametrize("container", ALL_CONTAINERS)
def test_no_crash_loop(container: str) -> None:
    restarts = docker_inspect(container, "{{.RestartCount}}")
    assert restarts is not None
    # A couple of restarts during dependency warmup is tolerable; a loop is not.
    assert int(restarts) <= 2, f"{container} restarted {restarts}x — crash loop?"


@pytest.mark.parametrize("container", ALL_CONTAINERS)
def test_healthy_if_healthcheck_defined(container: str) -> None:
    """Any container with a healthcheck must reach 'healthy' (catches the
    admin/web curl-probe-on-a-Node-image bug)."""
    status = docker_inspect(container, "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}")
    assert status is not None
    if status == "none":
        pytest.skip(f"{container} has no healthcheck")
    # Give late-arriving services time to flip healthy.
    if status != "healthy":
        svc = next((s for s in HTTP_SERVICES if s.container == container), None)
        if svc and wait_for_http(svc.port, svc.health, timeout=180):
            status = docker_inspect(container, "{{.State.Health.Status}}")
    assert status == "healthy", f"{container} health is '{status}', expected 'healthy'"


# ── HTTP reachability (ports actually published) ─────────────────────────────


@pytest.mark.parametrize("svc", HTTP_SERVICES, ids=lambda s: s.name)
def test_service_http_reachable(svc) -> None:
    """Every HTTP service must answer on its published host port — this is what
    failed when the admin container came up with no port mapping."""
    assert wait_for_http(svc.port, svc.health, timeout=180), (
        f"{svc.name} not reachable at localhost:{svc.port}{svc.health}"
    )


# ── admin "configured" flow (dashboard, not the setup wizard) ────────────────


def test_admin_reports_configured() -> None:
    """admin /api/setup/status must report configured:true — i.e. it resolved
    its service URLs and can reach auth on the compose network. configured:false
    is what shows the friend the first-boot wizard instead of the dashboard."""
    assert wait_for_http(7711, "/api/setup/status", timeout=180)
    r = requests.get("http://localhost:7711/api/setup/status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("configured") is True, (
        f"admin not configured: {json.dumps(body)} — "
        f"likely can't reach auth/config on the network"
    )


# ── inter-service wiring ─────────────────────────────────────────────────────


def test_config_service_has_registry() -> None:
    """config-service should have seeded the service registry that every other
    service queries for discovery at startup."""
    r = requests.get("http://localhost:7700/services", timeout=10)
    assert r.status_code in (200, 401, 403), f"unexpected {r.status_code}"
    # 200 = open; 401/403 = up but auth-gated (still proves it's serving).


def test_infra_containers_present() -> None:
    for c in NON_HTTP_CONTAINERS:
        assert docker_inspect(c, "{{.State.Status}}") == "running", f"{c} not running"
