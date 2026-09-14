"""The GPU gate must WAIT for the driver, not sample it once.

Both bootstrap scripts rent a GPU box and refuse to continue without one -- the
right call, since the lanes exist to build CUDA-linked wheels and a silent CPU
box proves nothing. But the check used to be a single sample taken immediately
after `cloud-init status --wait` returned, and cloud-init can report done before
the driver has attached in the guest.

On 2026-09-14 that gate fired 0.3s after cloud-init returned:

    18:47:44.66  [bootstrap-qs] waiting for cloud-init...
    18:47:44.98  [bootstrap-qs] FATAL: no NVIDIA GPU visible in guest
                 [bootstrap-qs] PROVISIONING failure

twice, on two different hosts, each time burning a rented instance and
reporting `22 failed, 4 passed` because the init phase never ran. A host that
needed five more seconds was indistinguishable from one with broken
passthrough.

These tests execute the gate as it actually ships -- extracted from the real
script between its own section markers -- against a fake nvidia-smi, so they
fail if the retry is removed or if the exit-42 contract is softened.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".github" / "workflows").is_dir():
            return candidate
    raise AssertionError("no .github/workflows above this file")


SCRIPTS = {
    "quickstart": _repo_root() / "install-e2e" / "quickstart" / "bootstrap_quickstart.sh",
    "gpu": _repo_root() / "install-e2e" / "gpu" / "bootstrap_remote.sh",
}


def _extract_gate(script: Path) -> str:
    """The section-2 GPU gate, verbatim from the shipped script.

    Bounded by the script's own `── 2.` / `── 3.` markers. If those move this
    raises instead of silently testing an empty string.
    """
    text = script.read_text()
    start = text.index("# ── 2.")
    end = text.index("# ── 3.", start)
    gate = text[start:end]
    assert "GPU_WAIT_SECS" in gate, f"{script.name}: gate has no wait budget"
    return gate


def _run_gate(script: Path, tmp_path: Path, *, appears_after: int | None, budget: int) -> subprocess.CompletedProcess:
    """Run the gate with a fake nvidia-smi that reports a GPU after N calls.

    appears_after=None means it never appears (a genuinely broken host).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    counter = tmp_path / "calls"
    counter.write_text("0")

    if appears_after is None:
        body = 'echo "No devices were found"\nexit 1\n'
    else:
        body = textwrap.dedent(
            f"""\
            n=$(cat {counter})
            n=$((n + 1))
            echo "$n" > {counter}
            if [ "$n" -ge {appears_after} ]; then
              echo "GPU 0: NVIDIA GeForce RTX 4090 (UUID: GPU-fake)"
              exit 0
            fi
            echo "No devices were found"
            exit 1
            """
        )
    fake = bin_dir / "nvidia-smi"
    fake.write_text("#!/usr/bin/env bash\n" + body)
    fake.chmod(0o755)

    # `sleep` is stubbed so a 120s budget does not take 120s of wall clock; the
    # gate's arithmetic still advances, which is what we are asserting on.
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
    (bin_dir / "sleep").chmod(0o755)

    harness = tmp_path / "gate.sh"
    harness.write_text(
        "set -euo pipefail\n"
        'GPU_TYPE="nvidia"\n'
        f'GPU_WAIT_SECS={budget}\n'
        'log() { echo "[t] $*"; }\n'
        "lspci() { echo 'VGA compatible controller: NVIDIA'; }\n"
        + _extract_gate(script)
    )
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "GPU_WAIT_SECS": str(budget)}
    return subprocess.run(
        ["bash", str(harness)], capture_output=True, text=True, env=env, timeout=60
    )


@pytest.mark.parametrize("lane", sorted(SCRIPTS))
def test_a_driver_that_arrives_late_is_not_a_provisioning_failure(lane, tmp_path):
    # Third poll succeeds: the old one-shot check would already have exited 42.
    result = _run_gate(SCRIPTS[lane], tmp_path, appears_after=3, budget=120)
    assert result.returncode == 0, f"{lane} gate rejected a late driver:\n{result.stdout}\n{result.stderr}"
    assert "GPU visible after" in result.stdout, result.stdout
    assert "PROVISIONING failure" not in result.stdout


@pytest.mark.parametrize("lane", sorted(SCRIPTS))
def test_a_driver_present_immediately_costs_no_wait(lane, tmp_path):
    result = _run_gate(SCRIPTS[lane], tmp_path, appears_after=1, budget=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GPU visible after 0s" in result.stdout, result.stdout


@pytest.mark.parametrize("lane", sorted(SCRIPTS))
def test_a_genuinely_broken_host_still_exits_42(lane, tmp_path):
    # The fail-fast contract the lanes depend on: the workflow reads 42 as
    # "provisioning, not a test failure". Waiting must not soften that.
    result = _run_gate(SCRIPTS[lane], tmp_path, appears_after=None, budget=15)
    assert result.returncode == 42, f"{lane} exited {result.returncode}:\n{result.stdout}\n{result.stderr}"
    assert "PROVISIONING failure" in result.stdout, result.stdout


@pytest.mark.parametrize("lane", sorted(SCRIPTS))
def test_the_failure_says_how_long_it_waited(lane, tmp_path):
    # Without the elapsed time, a red night cannot be told apart from the race
    # that caused this test to exist.
    result = _run_gate(SCRIPTS[lane], tmp_path, appears_after=None, budget=15)
    assert "after 15s" in result.stdout, result.stdout
