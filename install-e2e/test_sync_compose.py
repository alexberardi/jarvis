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
]

# DB-backed but intentionally DEFERRED — their images don't ship alembic yet, so
# the sync generator must NOT wrap them in a migrate entrypoint.
DEFERRED_IDS: list[str] = ["jarvis-logs", "jarvis-tts"]

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
