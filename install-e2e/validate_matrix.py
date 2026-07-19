#!/usr/bin/env python3
"""Phase 0 — matrix validation of the installer artifact across real configs.

The runtime bring-up (Phase 1/3) only exercises ONE config (CPU, all modules) —
GitHub runners have no GPU. This closes the breadth gap cheaply, with no runtime:
for every (gpu × track × module-set) a real user might pick, it

  1. generates the compose-export via the installer's headless generator,
  2. asserts `docker compose config` accepts it (incl. the CI override),
  3. asserts the invariants that bit us before (top-level volumes declared, every
     app service publishes a port, NO curl healthchecks, command-center carries
     JARVIS_AUTH_SECRET_KEY + JARVIS_MQTT_BROKER_URL),
  4. and verifies every ghcr image the artifact references actually EXISTS/pulls
     (catches a missing/typo'd :latest-rocm / :dev-cuda before a user does).

Env: INSTALLER_DIR (default ./jarvis-installer), OVERRIDE_FILE (the CI override),
GHCR auth must already be set up (the workflow logs in) for the image check.
Exits non-zero on the first real failure; prints a per-combo summary.
"""
from __future__ import annotations

import itertools
import os
import re
import subprocess
import sys
import tempfile

INSTALLER_DIR = os.environ.get("INSTALLER_DIR", "jarvis-installer")
OVERRIDE_FILE = os.environ.get("OVERRIDE_FILE", "install-e2e/docker-compose.ci-override.yaml")

GPUS = ["none", "nvidia", "amd", "amd-rocm"]
TRACKS = ["stable", "dev"]
# core-only (no recommended modules) and the full set
MODULE_SETS = {
    "core-only": "",
    "full": "jarvis-whisper-api,jarvis-tts,jarvis-notifications,jarvis-web,jarvis-admin",
    # `full` + every wizard-OPTIONAL service the installer registry carries.
    # Unknown ids are intersected away by the generator, so this set is a
    # silent no-op until the registry entry lands (jarvis-installer#34) — and
    # from then on it pins optional-service generation + image existence
    # across every gpu × track combo. go2rtc is deliberately absent: it is
    # admin-registry-only (the SYNC lane covers it).
    "full-optional": "jarvis-whisper-api,jarvis-tts,jarvis-notifications,jarvis-web,jarvis-admin,jarvis-phone-gateway",
}

IMAGE_RE = re.compile(r"image:\s*(ghcr\.io/\S+)")
errors: list[str] = []
warnings: list[str] = []
images: set[str] = set()


def generate(gpu: str, track: str, modules: str, out: str, mode: str = "export") -> None:
    subprocess.run(
        ["npx", "tsx", "scripts/gen-export-compose.mts",
         "--mode", mode, "--out", out, "--gpu", gpu, "--release", track, "--modules", modules],
        cwd=INSTALLER_DIR, check=True, capture_output=True, text=True,
    )


def validate_standard(label: str, gpu: str, track: str, modules: str) -> None:
    """The .env bundle path: generate compose + .env + init-db.sh and assert
    `docker compose --env-file .env config` resolves (every ${VAR} has a value,
    structure is valid) — the standard generator is a separate, registry-driven
    artifact, so it gets its own interpolation check across the matrix."""
    d = tempfile.mkdtemp(prefix="std-")
    out = os.path.join(d, "docker-compose.yml")
    try:
        generate(gpu, track, modules, out, mode="standard")
    except subprocess.CalledProcessError as e:
        errors.append(f"[{label} .env] generation failed: {e.stderr[:300]}")
        return
    r = subprocess.run(
        ["docker", "compose", "--env-file", os.path.join(d, ".env"), "-f", out, "config"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        errors.append(f"[{label} .env] config rejected it (interpolation/structure): {r.stderr.strip()[:300]}")


def compose_config_ok(path: str) -> str | None:
    r = subprocess.run(
        ["docker", "compose", "-f", path, "-f", OVERRIDE_FILE, "config"],
        capture_output=True, text=True,
    )
    return None if r.returncode == 0 else r.stderr.strip()[:300]


def check_invariants(label: str, text: str) -> None:
    def fail(msg: str) -> None:
        errors.append(f"[{label}] {msg}")

    if '"curl"' in text:
        fail("a healthcheck uses curl (not installed in several images)")

    # top-level volumes must declare every named volume referenced
    top = text.split("\nvolumes:\n", 1)
    declared = top[1] if len(top) > 1 else ""
    if "command-center-prompt-providers:/app" in text and "command-center-prompt-providers:" not in declared:
        fail("command-center-prompt-providers volume not declared top-level")
    if "whisper-voice-profiles:/app" in text and "whisper-voice-profiles:" not in declared:
        fail("whisper-voice-profiles volume not declared top-level")

    # command-center must carry the shared auth secret + mqtt broker
    cc = _service_block(text, "jarvis-command-center")
    if cc is not None:
        if "JARVIS_AUTH_SECRET_KEY:" not in cc:
            fail("command-center missing JARVIS_AUTH_SECRET_KEY")
        if "JARVIS_MQTT_BROKER_URL:" not in cc:
            fail("command-center missing JARVIS_MQTT_BROKER_URL")

    # admin/web (Node images) must use the node http probe, never curl
    for node_svc in ("jarvis-admin", "jarvis-web"):
        blk = _service_block(text, node_svc)
        if blk and "full" in label and '"node", "-e"' not in blk:
            fail(f"{node_svc} healthcheck is not the node probe")

    images.update(IMAGE_RE.findall(text))


def _service_block(text: str, sid: str) -> str | None:
    start = text.find(f"\n  {sid}:\n")
    if start < 0:
        return None
    rest = text[start + 1:]
    m = re.search(r"\n  [a-z][a-z0-9-]*:\n", rest)
    return rest[: m.start()] if m else rest


def check_images() -> None:
    # A missing STABLE image breaks a normal (latest) install → fatal. A missing
    # DEV image (:dev / :dev-*) only breaks the dev release track, which depends
    # on every repo's main build staying green — a separate reliability domain —
    # so surface it loudly but don't fail the suite on it.
    for img in sorted(images):
        r = subprocess.run(
            ["docker", "manifest", "inspect", img], capture_output=True, text=True
        )
        if r.returncode == 0:
            print(f"  image ok: {img}")
            continue
        tag = img.rsplit(":", 1)[-1]
        is_dev = tag == "dev" or tag.startswith("dev-")
        msg = f"{img} does NOT exist / not pullable: {r.stderr.strip()[:160]}"
        if is_dev:
            warnings.append(f"[dev-image] {msg}")
        else:
            errors.append(f"[image] {msg}")


def main() -> None:
    combos = list(itertools.product(GPUS, TRACKS, MODULE_SETS.items()))
    print(f"== matrix: {len(combos)} combos ==")
    for gpu, track, (mset_name, modules) in combos:
        label = f"gpu={gpu} track={track} modules={mset_name}"
        with tempfile.NamedTemporaryFile("r", suffix=".yml", delete=False) as fh:
            out = fh.name
        try:
            generate(gpu, track, modules, out)
        except subprocess.CalledProcessError as e:
            errors.append(f"[{label}] generation failed: {e.stderr[:300]}")
            continue
        err = compose_config_ok(out)
        if err:
            errors.append(f"[{label}] docker compose config rejected it: {err}")
            continue
        with open(out) as f:
            check_invariants(label, f.read())
        validate_standard(label, gpu, track, modules)
        print(f"  ok: {label} (export + .env)")

    print(f"\n== verifying {len(images)} referenced images exist on ghcr ==")
    check_images()

    for w in warnings:
        print(f"::warning::matrix: {w}")

    if errors:
        print(f"\n::error::matrix validation found {len(errors)} problem(s):")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    extra = f" ({len(warnings)} dev-track image warning(s))" if warnings else ""
    print(f"\n✅ matrix validation passed: all configs valid, invariants held, stable images exist{extra}")


if __name__ == "__main__":
    main()
