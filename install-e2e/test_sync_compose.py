"""SYNC-path lane — the actual hole the 2026-06 incident slipped through.

The harness stands up the INSTALLER's export compose. But the bug that 500'd the
fleet lived in the ADMIN SYNC / reconcile compose (jarvis-admin's
compose-generator / compose-upgrader), which the harness never exercised. The
export compose migrated config-service; the sync/reconcile compose was the path
that didn't — so the export-only e2e stayed green while prod was broken.

This suite closes that gap WITHOUT requiring a second full stack bring-up in the
default run: it regenerates the admin SYNC compose via the real `generateCompose`
(the function admin's reconcile calls) and asserts STATICALLY that every
migrate-set service block carries the alembic migrate entrypoint. If the sync
generator ever stops emitting the migrate wrapper for a DB-backed service (the
exact class of bug), this fails.

The LIVE sync bring-up (up the sync compose, then run the SAME migrations-ran +
/services==200 assertions against it) is scaffolded as a documented, opt-in job
in install-e2e.yml — heavy for one pass, so best-effort there.

Generation runs `npx tsx install-e2e/gen-sync-compose.mts` against the
jarvis-admin/server checkout. If that checkout isn't present (local dev without
it), the suite SKIPS rather than failing — CI provides it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

# Registry `migrate: true` set, mirrored from conftest.MIGRATE_SET (which keys
# off container names) but expressed as the service IDs the sync compose emits.
MIGRATE_SET_IDS: list[str] = [
    "jarvis-config-service",
    "jarvis-auth",
    "jarvis-command-center",
    "jarvis-llm-proxy-api",
    "jarvis-whisper-api",
    "jarvis-notifications",
    "jarvis-tts",
]

# DB-backed but intentionally DEFERRED — its image doesn't ship alembic yet, so
# the sync generator must NOT wrap it in a migrate entrypoint. (jarvis-tts now
# ships alembic + has DATABASE_URL wired, so it moved to MIGRATE_SET_IDS above.)
DEFERRED_IDS: list[str] = ["jarvis-logs"]

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
# Admin server checkout: CI checks it out as `jarvis-admin`; locally it lives as
# a sibling of the umbrella repo. ADMIN_SERVER_DIR overrides both.
_ADMIN_CANDIDATES = [
    Path(os.environ["ADMIN_SERVER_DIR"]) if os.environ.get("ADMIN_SERVER_DIR") else None,
    _REPO_ROOT / "jarvis-admin" / "server",
    _REPO_ROOT.parent / "jarvis-admin" / "server",
]


def _admin_server_dir() -> Path | None:
    for c in _ADMIN_CANDIDATES:
        if c and (c / "src" / "services" / "generators" / "compose-generator.ts").exists():
            return c
    return None


@pytest.fixture(scope="module")
def sync_compose() -> dict:
    """Regenerate the admin SYNC compose and return its parsed `services` map.

    Skips if the jarvis-admin/server checkout or tsx isn't available (so local
    runs without the installer/admin checkout don't hard-fail) — CI provides
    both."""
    admin = _admin_server_dir()
    if admin is None:
        pytest.skip(
            "jarvis-admin/server checkout not found "
            "(set ADMIN_SERVER_DIR or check it out next to the umbrella repo)"
        )
    if shutil.which("npx") is None:
        pytest.skip("npx/tsx not available to run the admin SYNC generator")

    out = _HERE / "docker-compose.sync.yaml"
    script = _HERE / "gen-sync-compose.mts"
    res = subprocess.run(
        ["npx", "tsx", str(script), "--out", str(out)],
        cwd=str(admin), capture_output=True, text=True, timeout=180,
    )
    if res.returncode != 0:
        pytest.skip(
            f"admin SYNC generator did not run (deps not installed?):\n{res.stderr[:400]}"
        )
    with out.open() as fh:
        doc = yaml.safe_load(fh)
    services = doc.get("services") if isinstance(doc, dict) else None
    assert services, f"sync compose has no services block:\n{out.read_text()[:300]}"
    return services


def _entrypoint_text(block: dict) -> str:
    ep = block.get("entrypoint")
    if ep is None:
        return ""
    return ep if isinstance(ep, str) else " ".join(map(str, ep))


@pytest.mark.parametrize("svc_id", MIGRATE_SET_IDS)
def test_sync_compose_migrate_entrypoint(sync_compose: dict, svc_id: str) -> None:
    """Each migrate-set service in the ADMIN SYNC compose must carry the alembic
    migrate entrypoint — the wrapper that runs `alembic upgrade head` before the
    app serves. This is the SYNC-path equivalent of the bug that 500'd the fleet:
    the export compose migrated config-service, the sync/reconcile path is the one
    that must too."""
    block = sync_compose.get(svc_id)
    if block is None:
        pytest.skip(f"{svc_id} not enabled in the sync compose")
    ep = _entrypoint_text(block)
    assert "alembic upgrade head" in ep, (
        f"{svc_id}: admin SYNC compose block has NO alembic migrate entrypoint — "
        f"this service would come up on a stale schema (the fleet-outage bug). "
        f"entrypoint={block.get('entrypoint')!r}"
    )
    assert "jarvis-migrate" in ep, (
        f"{svc_id}: migrate entrypoint missing the `jarvis-migrate` exec arg "
        f"(the original CMD won't be exec'd after migrations). "
        f"entrypoint={block.get('entrypoint')!r}"
    )


@pytest.mark.parametrize("svc_id", MIGRATE_SET_IDS)
def test_sync_compose_migrate_has_command(sync_compose: dict, svc_id: str) -> None:
    """Each migrate-set service in the ADMIN SYNC compose must ALSO carry a
    non-empty command. Overriding entrypoint clears the image CMD, so a migrate
    service with no command execs "" and exits right after migrating — the exact
    migrate-exit bug. Asserting only the entrypoint (above) is NOT enough; that's
    how the broken admin generator passed this lane. SYNC-path mirror of the
    installer's migrate-entrypoint INVARIANT."""
    block = sync_compose.get(svc_id)
    if block is None:
        pytest.skip(f"{svc_id} not enabled in the sync compose")
    cmd = block.get("command")
    assert cmd, (
        f"{svc_id}: admin SYNC compose gives it the migrate entrypoint but NO "
        f'command — it execs "" and exits after migrating (restart-loop, no '
        f"server). This is what a Sync would do to the running stack."
    )


@pytest.mark.parametrize("svc_id", DEFERRED_IDS)
def test_sync_compose_deferred_have_no_migrate(sync_compose: dict, svc_id: str) -> None:
    """Deferred services (logs/tts) must NOT get a migrate entrypoint — their
    images don't ship alembic, so wrapping them would crash-loop the container.
    Guards against accidentally flagging them migrate:true."""
    block = sync_compose.get(svc_id)
    if block is None:
        pytest.skip(f"{svc_id} not enabled in the sync compose")
    assert "alembic upgrade head" not in _entrypoint_text(block), (
        f"{svc_id} is DEFERRED (no alembic in its image) but the sync compose "
        f"gave it a migrate entrypoint — it would crash-loop"
    )


def _environment(block: dict) -> dict:
    """Return a service block's `environment` as a dict, accepting either the
    mapping (`KEY: value`) or list (`KEY=value`) compose form."""
    env = block.get("environment") or {}
    if isinstance(env, list):
        return dict(e.split("=", 1) for e in env if isinstance(e, str) and "=" in e)
    return env if isinstance(env, dict) else {}


def test_sync_compose_admin_wires_command_center_key(sync_compose: dict) -> None:
    """The jarvis-admin service in the ADMIN SYNC compose must carry
    COMMAND_CENTER_ADMIN_KEY, sourced from the shared ADMIN_API_KEY secret.

    The admin dashboard proxies to command-center's admin API (request traces,
    node detail) with `X-API-Key: COMMAND_CENTER_ADMIN_KEY`. When the reconcile
    compose omitted it, the key resolved to '' and command-center 401'd every
    admin API call — the traces page was dead in prod until this wiring landed.
    SYNC-path guard for that env, mirroring how this suite guards the migrate
    invariant."""
    block = sync_compose.get("jarvis-admin")
    if block is None:
        pytest.skip("jarvis-admin not enabled in the sync compose")
    env = _environment(block)
    assert env.get("COMMAND_CENTER_ADMIN_KEY") == "${ADMIN_API_KEY}", (
        "jarvis-admin SYNC compose is missing COMMAND_CENTER_ADMIN_KEY="
        "${ADMIN_API_KEY} — the admin dashboard would forward an empty admin key "
        "to command-center and every admin API call (traces, node detail) 401s. "
        f"environment={block.get('environment')!r}"
    )


# ── Wizard-OPTIONAL services (post-install add via admin Sync Compose) ───────
# The SYNC/reconcile path is the ONLY surface that adds an optional service to
# an existing install (admin ReconcilePage → POST /api/install/reconcile →
# the same generateCompose this fixture drives), so optional-service emission
# is pinned HERE. gen-sync-compose.mts enables go2rtc + jarvis-phone-gateway
# in its --modules default; each test skips-with-reason while the admin
# registry checked out in CI lacks the entry (phone-gateway until
# jarvis-admin#78), and pins the block from then on.


def test_sync_compose_go2rtc_block(sync_compose: dict) -> None:
    """go2rtc must be emitted by the SYNC generator when enabled: third-party
    image + its config-file bind. The bind is the sharp edge — the reconcile
    engine historically never seeded go2rtc.yaml, so a post-install add came up
    with Docker binding an EMPTY DIRECTORY where the config file belongs
    (fixed in jarvis-admin#78 by seeding on both generate and reconcile; the
    seed itself is unit-tested there — this lane pins the compose side)."""
    block = sync_compose.get("go2rtc")
    if block is None:
        pytest.skip("go2rtc not in the admin registry of this checkout")
    image = block.get("image", "")
    assert image.startswith("alexxit/go2rtc"), (
        f"go2rtc SYNC block has unexpected image {image!r}"
    )
    volumes = [str(v) for v in (block.get("volumes") or [])]
    assert any("go2rtc.yaml" in v and "/config/go2rtc.yaml" in v for v in volumes), (
        f"go2rtc SYNC block is missing the go2rtc.yaml config bind — a "
        f"post-install add would boot without config. volumes={volumes!r}"
    )
    assert "alembic upgrade head" not in _entrypoint_text(block), (
        "go2rtc is a third-party image — a migrate entrypoint would crash-loop it"
    )


def test_sync_compose_phone_gateway_block(sync_compose: dict) -> None:
    """jarvis-phone-gateway (wizard-optional, phone-calls PRD) must be emitted
    by the SYNC generator when enabled: first-party ghcr image, port 7713, and
    NO migrate entrypoint (the gateway owns no Postgres — CC owns
    phone_call_sessions; flagging it migrate:true would crash-loop it)."""
    block = sync_compose.get("jarvis-phone-gateway")
    if block is None:
        pytest.skip(
            "jarvis-phone-gateway not in the admin registry of this checkout "
            "(lands with jarvis-admin#78)"
        )
    image = block.get("image", "")
    assert image.startswith("ghcr.io/alexberardi/jarvis-phone-gateway"), (
        f"phone-gateway SYNC block has unexpected image {image!r}"
    )
    ports = [str(p) for p in (block.get("ports") or [])]
    assert any("7713" in p for p in ports), (
        f"phone-gateway SYNC block does not publish 7713: ports={ports!r}"
    )
    assert "alembic upgrade head" not in _entrypoint_text(block), (
        "jarvis-phone-gateway owns no database — the sync compose gave it a "
        "migrate entrypoint, which would crash-loop the container"
    )
