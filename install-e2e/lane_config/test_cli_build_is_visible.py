"""`./jarvis start` must not go silent while docker builds.

These dev composes use `build: .`, so `up -d` builds an image inline when it is
missing. The CLI used to capture that output into a variable:

    compose_output=$(cd "$dir" && docker compose ... up -d $build_flag 2>&1)

which means a build prints NOTHING until it finishes. jarvis-llm-proxy-api's
CUDA image took ~115 minutes of exactly that, and install-e2e-quickstart's log
simply stopped after "START jarvis-command-center" and sat there until the job
timeout killed it -- every night from 2026-09-08. It read as a hang for a week,
and the actual cause was a Dockerfile installing vLLM that nothing selects.

A silent build and a wedged process look identical, and that is the whole bug:
the lane could not tell us what it was waiting for.

This is a source guard because nothing else covers `jarvis` at all -- both
workflow PR triggers are filtered to install-e2e paths, so a change to the
script that starts the entire stack runs no CI. This file lives here so it does.
"""
from pathlib import Path

import pytest


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".github" / "workflows").is_dir():
            return candidate
    raise AssertionError("no .github/workflows above this file")


CLI = _repo_root() / "jarvis"


@pytest.fixture(scope="module")
def cli() -> str:
    return CLI.read_text()


def test_the_cli_is_there_and_starts_services(cli):
    # If this fails the guards below are watching nothing.
    assert "docker compose" in cli and "up -d" in cli


def test_the_build_capable_start_does_not_capture_its_output(cli):
    """The specific shape that hid a two-hour build.

    Scoped to the path that can BUILD -- the one taking $build_flag, where the
    service composes use `build: .` so `up -d` compiles an image inline. The
    other two captured `up -d` calls are a prebuilt-image pull
    (jarvis-data-services) and a --force-recreate restart; neither builds, and
    both already print their captured output on failure. If a silent multi-minute
    PULL ever becomes the mystery this was, the same treatment applies there.
    """
    offenders = [
        line.strip()
        for line in cli.splitlines()
        if "up -d" in line and "$build_flag" in line and "=$(" in line
    ]
    assert offenders == [], (
        "a build's output is captured instead of streamed, so a slow build is "
        f"indistinguishable from a hang: {offenders}"
    )


def test_compose_output_goes_somewhere_readable(cli):
    # Streaming to a log keeps the failure path diagnosable -- the old code
    # printed the captured text on failure, so replacing it must not lose that.
    assert "-compose.log" in cli, "compose output has nowhere to go"


def test_a_long_build_reports_progress(cli):
    """Something must be printed WHILE the build runs, not only after it."""
    assert "building," in cli, "no progress is reported during a build"
    # And it must RESCHEDULE itself, not merely mention a variable: a first
    # version of this asserted `"next_tick" in cli`, which the declaration alone
    # satisfied, so deleting the reschedule left a two-hour build as one message
    # followed by silence -- and the guard stayed green.
    assert "next_tick=$((waited +" in cli, (
        "the progress report is not rescheduled, so it prints once and goes quiet"
    )


def test_a_failed_build_still_shows_what_went_wrong(cli):
    assert "docker compose up failed" in cli
    assert 'tail -20 "$compose_log"' in cli, (
        "the failure path no longer surfaces the build output"
    )
