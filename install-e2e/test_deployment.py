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
import os

import pytest
import requests

from conftest import (
    ALL_CONTAINERS,
    HTTP_SERVICES,
    NON_HTTP_CONTAINERS,
    docker_inspect,
    wait_for_container_health,
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
    admin/web curl-probe-on-a-Node-image bug). Polls the health flip, since
    docker only runs the first probe after the 30s interval."""
    status = wait_for_container_health(container, timeout=180)
    assert status is not None, f"{container} not found (did it fail to create?)"
    if status == "none":
        pytest.skip(f"{container} has no healthcheck")
    assert status == "healthy", f"{container} health is '{status}', expected 'healthy'"


# ── HTTP reachability (ports actually published) ─────────────────────────────


@pytest.mark.parametrize("svc", HTTP_SERVICES, ids=lambda s: s.name)
def test_service_http_reachable(svc) -> None:
    """Every HTTP service must answer on its published host port — this is what
    failed when the admin container came up with no port mapping."""
    assert wait_for_http(svc.port, svc.health, timeout=180), (
        f"{svc.name} not reachable at localhost:{svc.port}{svc.health}"
    )


# ── host exposure of data-plane infra ────────────────────────────────────────
# Loki has NO authentication of its own and it stores voice transcripts, but the
# generators published it on 0.0.0.0:3100 by default — it was grouped with
# grafana as a "dashboard", when in fact grafana is the dashboard (and carries a
# generated admin password) and loki is the raw log API behind it. On a default
# install, anyone on the LAN — or the whole internet on a VPS — could read a
# household's voice history over plain HTTP. postgres/redis are the same class
# of leak.
#
# These must bind to loopback. Only grafana (password-protected) and mosquitto
# (remote nodes must reach it) legitimately stay on all interfaces.

# container -> container-side port that must not be world-published
LOOPBACK_ONLY_INFRA: dict[str, str] = {
    "jarvis-loki": "3100/tcp",
    "jarvis-postgres": "5432/tcp",
    "jarvis-redis": "6379/tcp",
}

WORLD_OPEN_HOST_IPS = {"0.0.0.0", "::", ""}


@pytest.mark.parametrize("container,port", sorted(LOOPBACK_ONLY_INFRA.items()))
def test_data_plane_infra_binds_loopback_only(container: str, port: str) -> None:
    """The generated compose must not publish state/transcript stores off-host."""
    raw = docker_inspect(container, "{{json .NetworkSettings.Ports}}")
    assert raw is not None, f"{container} not found"
    bindings = (json.loads(raw) or {}).get(port) or []

    # Not publishing the port at all is even safer than loopback — that's fine.
    for b in bindings:
        host_ip = b.get("HostIp", "")
        assert host_ip not in WORLD_OPEN_HOST_IPS, (
            f"{container} publishes {port} on {host_ip or '0.0.0.0'}:{b.get('HostPort')} "
            f"— reachable off-host. It must bind 127.0.0.1 "
            f"(JARVIS_INFRA_BIND_HOST is the documented opt-out)."
        )


def test_loki_still_reachable_on_loopback() -> None:
    """Loopback-binding must not have broken Loki itself — jarvis-logs depends
    on it. Guards against 'fixing' the exposure by breaking the service.

    Polls: loki answers /ready with 503 ("ingester not ready") for the first few
    seconds after boot, so a single GET races its warmup.
    """
    assert wait_for_http(3100, "/ready", timeout=120), (
        "loki never became ready on 127.0.0.1:3100 — the loopback bind should "
        "not have changed whether it serves, only on which interface"
    )


def test_logs_service_can_still_query_loki() -> None:
    """The real dependency: jarvis-logs reaches loki over the INTERNAL network
    (http://loki:3100), so the host binding is irrelevant to it. If this breaks,
    the loopback bind went too far."""
    assert wait_for_http(7702, "/health", timeout=120)
    r = requests.get("http://localhost:7702/health", timeout=10)
    assert r.status_code == 200, f"jarvis-logs unhealthy after loki bind change: {r.text}"


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
    service queries for discovery at startup.

    `/services` is OPEN-READ, so it must return exactly 200 with a JSON list of
    registered services. We deliberately do NOT tolerate 401/403/500 here: a
    stale schema (the config-service migration-005 incident — missing
    services.external_host) makes this endpoint 500 fleet-wide, and the old loose
    `200/401/403` check would have swallowed that. A 500 must fail."""
    r = requests.get("http://localhost:7700/services", timeout=10)
    assert r.status_code == 200, (
        f"config-service /services returned {r.status_code}, expected 200 "
        f"(open-read). A 500 here is the stale-schema fleet-outage symptom: "
        f"{r.text[:300]}"
    )
    body = r.json()
    services = body["services"] if isinstance(body, dict) else body
    assert isinstance(services, list), (
        f"/services body is not a JSON list of registered services: {str(body)[:200]}"
    )


def test_infra_containers_present() -> None:
    for c in NON_HTTP_CONTAINERS:
        assert docker_inspect(c, "{{.State.Status}}") == "running", f"{c} not running"


def test_self_heal_reregister_adds_external_coords() -> None:
    """The upgrade / Sync self-heal path: a service registered with ONLY
    container coords (a pre-fix install) is unreachable via ?style=external; a
    re-register WITH external coords (exactly what admin Sync / registerServices
    sends) upserts them so it becomes phone-reachable — no reinstall needed.

    Uses a throwaway service name so it doesn't disturb the real registry.
    """
    # /v1/services/register validates X-Jarvis-Admin-Token against the
    # JARVIS_AUTH_ADMIN_TOKEN config-service holds (gen placeholder: "c"*64).
    token = os.environ.get("JARVIS_AUTH_ADMIN_TOKEN", "c" * 64)
    headers = {"X-Jarvis-Admin-Token": token, "Content-Type": "application/json"}
    name = "e2e-upgrade-probe"

    def register(extra: dict) -> None:
        body = {"services": [{"name": name, "host": "e2e-probe-host", "port": 9999, **extra}]}
        r = requests.post(
            "http://localhost:7700/v1/services/register", headers=headers, json=body, timeout=15
        )
        assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"

    def external_url() -> str:
        r = requests.get("http://localhost:7700/services?style=external", timeout=10)
        assert r.status_code == 200
        svc = {s["name"]: s for s in r.json()["services"]}.get(name)
        assert svc, f"{name} not registered"
        return svc["url"]

    # 1. pre-fix state: container-only coords → external falls back to the
    #    unreachable container host (what broke mobile before the fix)
    register({})
    assert external_url() == "http://e2e-probe-host:9999"

    # 2. self-heal: re-register WITH external coords (admin Sync's payload)
    register({"external_host": "localhost", "external_port": 7701})

    # 3. ?style=external now serves the reachable published coord — upsert worked
    assert external_url() == "http://localhost:7701"


def test_external_discovery_is_phone_reachable() -> None:
    """An off-docker client (the mobile app) must get a reachable URL for auth
    via ?style=external — NOT the internal container coord (jarvis-auth:8000)
    that broke mobile login. Internal (default) style stays container coords so
    container-to-container discovery is unaffected."""
    base = requests.get("http://localhost:7700/services", timeout=10)
    assert base.status_code == 200
    internal = {s["name"]: s for s in base.json()["services"]}
    auth = internal.get("jarvis-auth")
    assert auth, "jarvis-auth not registered in config-service"
    # internal/default style: container coords, unchanged
    assert "jarvis-auth:8000" in auth["url"], f"internal auth url changed: {auth['url']}"

    ext = requests.get("http://localhost:7700/services?style=external", timeout=10)
    assert ext.status_code == 200, "config-service lacks ?style=external (needs >= v0.1.5)"
    auth_ext = {s["name"]: s for s in ext.json()["services"]}["jarvis-auth"]
    # external style: published port, NOT the unreachable container name
    assert "jarvis-auth" not in auth_ext["url"], (
        f"external auth url is still a container coord (mobile can't reach it): {auth_ext['url']}"
    )
    assert ":7701" in auth_ext["url"], (
        f"external auth url not on the published port 7701: {auth_ext['url']}"
    )
