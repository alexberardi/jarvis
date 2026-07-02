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

import re
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

# ── Migrate-set ──────────────────────────────────────────────────────────────
# Services the installer registry flags `migrate: true` — they MUST run
# `alembic upgrade head` on startup (via the generated migrate entrypoint / image
# CMD) and so their DB must be at the alembic HEAD revision once they're up.
#
# This is the keystone of the 2026-06 incident: config-service shipped migration
# 005 but its container never ran `alembic upgrade head`, so the prod schema was
# stale and every `/services` query 500'd fleet-wide — while the old install-e2e
# stayed green because it only probed shallow `/health`. `test_migrations_ran`
# asserts cur==head for each of these, so a service that skips its migrations
# FAILS here.
#
# Kept in sync with the installer registry's `migrate: true` set and the admin
# compose-generator's MIGRATE_SET unit test. Only jarvis-logs is intentionally
# DEFERRED (its image doesn't ship alembic yet) and is NOT here.
MIGRATE_SET: list[Service] = [
    s for s in HTTP_SERVICES
    if s.container in {
        "jarvis-config-service",
        "jarvis-auth",
        "jarvis-command-center",
        "jarvis-llm-proxy-api",
        "jarvis-whisper-api",
        "jarvis-notifications",
        "jarvis-tts",
    }
]

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


def docker_exec(container: str, argv: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess | None:
    """Run `docker exec <container> <argv...>` and return the CompletedProcess,
    or None if docker/the container is unavailable.

    We exec by the fixed container_name (the generator always emits one) rather
    than `docker compose exec`, so we don't need the compose project/file args —
    same convention as `docker_inspect` above. Equivalent to the
    `docker compose exec -T <svc> ...` the incident write-up calls for: -T
    (no TTY) is implicit for `docker exec` without -t.
    """
    try:
        return subprocess.run(
            ["docker", "exec", container, *argv],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


# A revision line from `alembic current` / `alembic heads` is the revision id
# followed by optional markers, e.g.:
#   "005 (head)"            (config-service/whisper/notifications use short ids)
#   "a3b4c5d6e7f8 (head)"   (auth/command-center/llm-proxy use 12-char hashes)
#   "a3b4c5d6e7f8"          (current, no marker)
# Revision ids are alphanumeric (NOT purely the level words below). alembic also
# prints "INFO [alembic...]" / "WARNING ..." log lines to the same merged stream;
# those are skipped explicitly so a short numeric id like "005" isn't confused
# with — nor a hash missed by — an over-tight pattern.
_ALEMBIC_LOG_LEVELS = ("INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL")
# A revision id token: 1+ alphanumerics, then end-of-token (space/paren/EOL).
_ALEMBIC_REV_RE = re.compile(r"^([0-9A-Za-z]+)(?:\s|\(|$)")


def _alembic_revisions(output: str) -> set[str]:
    """Parse the revision id(s) out of `alembic current`/`heads` output.

    Handles BOTH short numeric ids ("005") and long hashes ("a3b4c5d6e7f8"),
    and ignores the "INFO [alembic...]" log lines alembic emits to the same
    (merged) stream. Returns a set so branched histories (multiple heads)
    compare correctly. Empty set ⇒ no revision (e.g. an unstamped DB / a skipped
    migration)."""
    revs: set[str] = set()
    for line in (output or "").splitlines():
        line = line.strip()
        if not line or line.startswith(_ALEMBIC_LOG_LEVELS):
            continue
        m = _ALEMBIC_REV_RE.match(line)
        # Guard: a bare level word with no bracket (unlikely) — skip non-ids.
        if m and m.group(1) not in _ALEMBIC_LOG_LEVELS:
            revs.add(m.group(1))
    return revs


class AlembicExecError(RuntimeError):
    """`docker exec ... alembic` itself failed (no such container, daemon error,
    alembic missing). Distinct from a successful run that reports no revision —
    we must NOT parse a daemon/error stream as if it were a revision id, or a
    failed exec could spuriously look 'at head'."""


def alembic_state(container: str) -> tuple[set[str], set[str], str]:
    """Return (current_revs, head_revs, debug) for a container, via
    `python -m alembic current` / `... heads`. Empty current_revs (with a
    SUCCESSFUL exec) means the DB was never stamped — i.e. the service skipped
    its migrations.

    A container at HEAD satisfies `current_revs == head_revs` (and non-empty).

    Raises AlembicExecError if either exec fails (rc != 0 or docker unavailable),
    so a transient daemon error is never mistaken for a revision."""
    cur = docker_exec(container, ["python", "-m", "alembic", "current"])
    head = docker_exec(container, ["python", "-m", "alembic", "heads"])
    cur_out = (cur.stdout if cur else "") + (cur.stderr if cur else "")
    head_out = (head.stdout if head else "") + (head.stderr if head else "")
    debug = (
        f"alembic current rc={cur.returncode if cur else 'n/a'}:\n{cur_out.strip()}\n"
        f"alembic heads   rc={head.returncode if head else 'n/a'}:\n{head_out.strip()}"
    )
    if cur is None or head is None or cur.returncode != 0 or head.returncode != 0:
        raise AlembicExecError(
            f"`alembic current`/`heads` exec failed for {container}:\n{debug}"
        )
    return _alembic_revisions(cur_out), _alembic_revisions(head_out), debug


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
