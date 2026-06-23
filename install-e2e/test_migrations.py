"""Migrations actually ran — the keystone assertion for the 2026-06 incident.

config-service shipped Alembic migration 005 (services.external_host) but its
running container never executed `alembic upgrade head` (the image used
Base.metadata.create_all(), which never ALTERs an existing table). So the prod
schema was stale and every `/services` query 500'd fleet-wide — yet the old
install-e2e stayed GREEN because it only probed shallow `/health` (which never
touches the DB) and only stood up the installer's EXPORT compose.

This suite closes that hole, generator-agnostically: for every migrate-set
service the harness brought up, assert the DB is at the alembic HEAD revision
(`alembic current` == `alembic heads`, both non-empty). A service that skipped
its migrations has an empty/behind `current` → it FAILS here. We do NOT trust
`/health`; we ask the database what revision it's actually at.

PLUS the exact symptom endpoint: config-service `GET /services` (open-read) must
return HTTP 200 and a JSON list. A stale schema makes that endpoint 500.
"""
from __future__ import annotations

import pytest
import requests

from conftest import (
    MIGRATE_SET,
    AlembicExecError,
    Service,
    alembic_state,
    docker_inspect,
    wait_for_container_health,
    wait_for_http,
)


def _is_up(container: str) -> bool:
    return docker_inspect(container, "{{.State.Status}}") == "running"


@pytest.mark.parametrize("svc", MIGRATE_SET, ids=lambda s: s.name)
def test_migrations_ran(svc: Service) -> None:
    """Every migrate-set container that's up must have its DB at alembic HEAD.

    This is the assertion the old suite lacked: it FAILS for a service that came
    up without running `alembic upgrade head` (empty `current` / `current` behind
    `heads`) — exactly the config-service stale-schema bug. Services not enabled
    in this stack are skipped, not failed.
    """
    if not _is_up(svc.container):
        pytest.skip(f"{svc.name} ({svc.container}) not enabled in this stack")

    # The migrate entrypoint runs `alembic upgrade head` before the app serves,
    # so by the time the container is healthy/reachable, migrations have run.
    # Wait on that so we don't race a slow first-boot upgrade.
    wait_for_container_health(svc.container, timeout=180)

    try:
        current, heads, debug = alembic_state(svc.container)
    except AlembicExecError as e:
        pytest.fail(
            f"{svc.name}: could not query alembic state in-container — the exec "
            f"itself failed (not a clean 'no revision'). This is a hard error, "
            f"not a pass.\n{e}"
        )

    assert heads, (
        f"{svc.name}: could not read alembic heads in-container — is alembic "
        f"installed / alembic.ini present?\n{debug}"
    )
    assert current, (
        f"{svc.name}: DB has NO alembic revision stamped — the container came up "
        f"without running `alembic upgrade head` (the exact config-service "
        f"stale-schema bug).\n{debug}"
    )
    assert current == heads, (
        f"{svc.name}: DB is BEHIND head — migrations did not fully run. "
        f"current={sorted(current)} head={sorted(heads)}\n{debug}"
    )


def test_config_services_endpoint_200_and_list() -> None:
    """The exact symptom endpoint: config-service `/services` is open-read, so it
    must return HTTP 200 with a JSON list. A stale schema (missing
    services.external_host) makes this 500 — the fleet-wide outage. This is
    deliberately STRICTER than the loose 200/401/403 the deployment test allowed:
    a real schema 500 must fail here, not be tolerated as 'auth-gated'."""
    assert wait_for_http(7700, "/services", timeout=180), (
        "config-service /services never returned 200 — likely a stale schema "
        "(the config-service migration-005 incident) or service down"
    )
    r = requests.get("http://localhost:7700/services", timeout=10)
    assert r.status_code == 200, (
        f"config-service /services returned {r.status_code} (expected 200). "
        f"A schema 500 here is the fleet-wide-outage symptom: {r.text[:300]}"
    )
    body = r.json()
    # config-service returns {"services": [...]}; the list is the registry rows
    # that every other service queries for discovery — proves the table is
    # both present (migrated) and serving.
    services = body["services"] if isinstance(body, dict) else body
    assert isinstance(services, list), (
        f"config-service /services body is not a JSON list: {str(body)[:200]}"
    )
