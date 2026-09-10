"""Guards on the lane's own configuration, not on the stack it installs.

Two mistakes here have already cost real debugging time, and neither shows up as
a red build -- they show up as a GREEN build that tested less than you think:

1. The workflow_dispatch `modules` input default disagreed with the fallback in
   the generate step, so a manual dispatch ran a smaller stack than a scheduled
   one. The recipes lane was added to the fallback only, went green on a manual
   dispatch, and skipped all nine of its tests because the containers were never
   deployed.

2. The release track defaulted to stable, which installs whatever :latest holds.
   jarvis-recipes-server is on v0.1.5 (+31 commits) and jarvis-ocr-service on
   v0.1.1 (+35), and those images lack alembic.ini and worker.py that the
   generated compose depends on -- so the stack could not come up at all, for
   reasons unrelated to the commit under test.

These parse the workflow rather than run it, so they cost nothing and fail
loudly when the config drifts back.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
E2E = WORKFLOWS / "install-e2e.yml"
GPU = WORKFLOWS / "install-e2e-gpu.yml"

# Services whose containers the presence-gated suites need in order to assert
# anything. If they leave the module list, those tests skip silently.
REQUIRED_MODULES = ("jarvis-recipes-server", "jarvis-ocr-service")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _generate_step_script(workflow: dict) -> str:
    """Every `run:` block in the workflow, concatenated."""
    scripts = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []) or []:
            if isinstance(step.get("run"), str):
                scripts.append(step["run"])
    return "\n".join(scripts)


@pytest.mark.parametrize("path", [E2E, GPU], ids=["install-e2e", "install-e2e-gpu"])
def test_workflow_exists_and_parses(path):
    assert path.is_file(), f"{path} is missing"
    assert _load(path), f"{path} parsed empty"


@pytest.mark.parametrize("path", [E2E, GPU], ids=["install-e2e", "install-e2e-gpu"])
def test_release_track_defaults_to_dev(path):
    """dev is current main for every service; stable pins releases far behind it."""
    script = _generate_step_script(_load(path))
    assert "inputs.release || 'dev'" in script, (
        f"{path.name} does not default its release track to dev. Stable installs "
        "the published :latest images, which for recipes/ocr are ~30 commits "
        "behind main and missing files the generated compose requires."
    )
    assert "inputs.release || 'stable'" not in script, (
        f"{path.name} still has a stable fallback; the two would disagree."
    )


@pytest.mark.parametrize("path", [E2E, GPU], ids=["install-e2e", "install-e2e-gpu"])
def test_release_input_default_matches_the_step_fallback(path):
    """The exact class of bug the modules input already caused: two defaults."""
    workflow = _load(path)
    # PyYAML parses the `on:` key as boolean True.
    triggers = workflow.get("on") or workflow.get(True) or {}
    inputs = (triggers.get("workflow_dispatch") or {}).get("inputs") or {}
    if "release" not in inputs:
        pytest.skip(f"{path.name} has no release input")

    declared = inputs["release"].get("default")
    assert declared == "dev", (
        f"{path.name} declares release default {declared!r} but the generate "
        "step falls back to 'dev' -- a dispatch would test a different track "
        "than a schedule, silently."
    )


def test_modules_list_is_single_sourced():
    """A `modules` input default would disagree with the step fallback again."""
    workflow = _load(E2E)
    triggers = workflow.get("on") or workflow.get(True) or {}
    inputs = (triggers.get("workflow_dispatch") or {}).get("inputs") or {}
    assert "modules" in inputs, "the modules input disappeared"
    assert "default" not in inputs["modules"], (
        "the modules input has a default again. It disagreed with the fallback "
        "in the generate step once already, and a manual dispatch silently ran "
        "a smaller stack than the nightly."
    )


def _modules_argument(script: str) -> str:
    """The value passed to --modules, not merely text mentioning a service.

    Searching the whole script is not enough: the surrounding comments name
    these services when explaining the release track, so a substring check
    passes even after the modules are removed.
    """
    match = re.search(r"--modules\s+\"([^\"]*)\"", script)
    assert match, "the generate step no longer passes --modules"
    return match.group(1)


def test_the_canonical_module_list_still_deploys_the_gated_services():
    """Presence-gated suites assert nothing if their containers are absent."""
    modules = _modules_argument(_generate_step_script(_load(E2E)))
    for module in REQUIRED_MODULES:
        assert module in modules, (
            f"{module} left the canonical module list ({modules!r}). Its tests "
            "are presence-gated, so they will skip rather than fail -- a green "
            "run that checked nothing."
        )
