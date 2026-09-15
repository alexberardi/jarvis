"""A rented box with no visible GPU must cost one offer, not the whole run.

Both bootstrap scripts check for a GPU and exit 42 if there isn't one. That is
the right contract, but it runs in a LATER workflow step -- by then the offer
loop has committed to the host, so the workflow destroys the instance and
abandons the run. On 2026-09-14 the quickstart lane did that twice in a row on
the SAME machine (offer 46900072, host 194.228.55.129, two different instances),
because only 2 offers qualified and the loop orders cheapest-first. A sick host
that is cheap keeps winning.

Vast already documents this shape in excluded_machines(): "a host can pass the
SSH-ready probe and then hang minutes later (machine 97012 killed two runs on
2026-07-19 exactly this way)".

So provisioning now asks the GPU question itself, while it still has other
offers to try. These tests drive the real offer loop with every Vast call
stubbed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".github" / "workflows").is_dir():
            return candidate
    raise AssertionError("no .github/workflows above this file")


SCRIPT = _repo_root() / "install-e2e" / "gpu" / "provision_vast.py"


@pytest.fixture
def pv():
    spec = importlib.util.spec_from_file_location("provision_vast_under_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def stubbed(pv, monkeypatch, tmp_path):
    """The offer loop with every outbound call stubbed; returns the call log."""
    calls: dict[str, list] = {"created": [], "destroyed": []}
    offers = [
        {"id": 46900072, "machine_id": 111, "dph_total": 1.03, "gpu_name": "RTX 5090"},
        {"id": 50816787, "machine_id": 222, "dph_total": 1.11, "gpu_name": "RTX 5090"},
    ]
    monkeypatch.setattr(pv, "search_offers", lambda lane_key: list(offers))
    monkeypatch.setattr(pv, "register_account_ssh_key", lambda pubkey: 7)
    monkeypatch.setattr(pv, "delete_account_ssh_key", lambda key_id: None)

    def fake_vastai(*args, **kwargs):
        if args[:2] == ("create", "instance"):
            offer_id = int(args[2])
            instance_id = 900_000 + offer_id % 1000
            calls["created"].append((offer_id, instance_id))
            return f"Started. {{'success': True, 'new_contract': {instance_id}}}"
        return ""

    monkeypatch.setattr(pv, "vastai", fake_vastai)
    monkeypatch.setattr(pv, "wait_ssh", lambda i, u, k: {"ssh_host": "h", "ssh_port": 22})
    monkeypatch.setattr(pv, "destroy", lambda i: calls["destroyed"].append(i))

    pubkey = tmp_path / "id.pub"
    pubkey.write_text("ssh-ed25519 AAAA test\n")
    calls["pubkey"] = str(pubkey)  # type: ignore[assignment]
    calls["out"] = str(tmp_path / "provision.json")  # type: ignore[assignment]
    return calls


def _provision(pv, stubbed):
    return pv.provision(
        "cuda-quickstart", stubbed["pubkey"], None, "root", stubbed["out"], None  # type: ignore[arg-type]
    )


def test_a_gpu_less_host_is_destroyed_and_the_next_offer_tried(pv, stubbed, monkeypatch):
    # Machine 111 answers SSH but shows no GPU; 222 is healthy.
    seen: list[str] = []

    def fake_probe(conn, user, key_path, gpu_type):
        seen.append(gpu_type)
        return len(seen) > 1

    monkeypatch.setattr(pv, "gpu_visible_over_ssh", fake_probe)

    result = _provision(pv, stubbed)

    assert [o for o, _ in stubbed["created"]] == [46900072, 50816787], (
        "the loop did not move on to the second offer"
    )
    first_instance = stubbed["created"][0][1]
    assert stubbed["destroyed"] == [first_instance], (
        f"the sick host was not destroyed (destroyed={stubbed['destroyed']})"
    )
    assert result["machine_id"] == 222
    assert result["instance_id"] == stubbed["created"][1][1]


def test_a_healthy_host_is_accepted_without_renting_a_second(pv, stubbed, monkeypatch):
    monkeypatch.setattr(pv, "gpu_visible_over_ssh", lambda *a: True)

    result = _provision(pv, stubbed)

    assert len(stubbed["created"]) == 1, "rented more than one box for a healthy first offer"
    assert stubbed["destroyed"] == []
    assert result["machine_id"] == 111


def test_the_machine_id_is_logged_so_a_bad_host_can_be_pinned(pv, stubbed, monkeypatch, capsys):
    # VAST_EXCLUDE_MACHINES is keyed by machine, so the machine id has to reach
    # the log or a repeat offender cannot be identified from a failed run.
    monkeypatch.setattr(pv, "gpu_visible_over_ssh", lambda *a: False)
    with pytest.raises(SystemExit):
        _provision(pv, stubbed)
    captured = capsys.readouterr()
    out = captured.out + captured.err  # log() writes to stderr
    assert "machine 111" in out and "machine 222" in out
    assert "VAST_EXCLUDE_MACHINES" in out, "the log does not say how to pin a sick host"


def test_every_offer_being_sick_is_a_provisioning_failure(pv, stubbed, monkeypatch):
    # Must stay a PROVISIONING failure, which the workflows read as "not a test
    # failure" -- retrying hosts must not turn a dead marketplace into a red suite.
    monkeypatch.setattr(pv, "gpu_visible_over_ssh", lambda *a: False)
    with pytest.raises(SystemExit, match="PROVISIONING"):
        _provision(pv, stubbed)
    assert len(stubbed["destroyed"]) == 2, "sick hosts were left running"


def test_the_provisioning_budget_leaves_room_for_the_bring_up(pv):
    # The job budget is 150 min and a quickstart bring-up is ~60-70 of it. An
    # hour of provisioning (the old value) could and did eat the difference.
    assert pv.PROVISION_DEADLINE_S <= 25 * 60, (
        f"provisioning may consume {pv.PROVISION_DEADLINE_S / 60:.0f} min of the job budget"
    )


def test_the_gpu_wait_agrees_with_the_bootstrap_scripts(pv):
    """Both places wait for the driver; they must mean the same thing by it."""
    for script in ("quickstart/bootstrap_quickstart.sh", "gpu/bootstrap_remote.sh"):
        text = (_repo_root() / "install-e2e" / script).read_text()
        marker = 'GPU_WAIT_SECS="${GPU_WAIT_SECS:-'
        assert marker in text, f"{script} has no GPU_WAIT_SECS default"
        default = int(text.split(marker, 1)[1].split("}", 1)[0])
        assert default == pv.GPU_PROBE_WAIT_S, (
            f"{script} waits {default}s but provisioning waits {pv.GPU_PROBE_WAIT_S}s"
        )


def test_the_machine_id_is_logged_even_when_the_host_is_accepted(pv, stubbed, monkeypatch, capsys):
    """A successful provision must still name the machine it took.

    excluded_machines() exists for hosts that pass every probe and then hang
    mid-test -- machine 97012 killed two runs that way on 2026-07-19. Those
    never reach a failure path, so the id has to be on the line where the offer
    is taken, or the only run that needs pinning is the one that cannot be.
    """
    monkeypatch.setattr(pv, "gpu_visible_over_ssh", lambda *a: True)
    _provision(pv, stubbed)
    captured = capsys.readouterr()
    assert "machine 111" in captured.out + captured.err


@pytest.mark.parametrize(
    "workflow", ["install-e2e-quickstart.yml", "install-e2e-gpu.yml"]
)
def test_the_provision_step_is_capped_in_the_workflow(workflow):
    """A backstop above the script's own deadline.

    provision_vast.py caps itself, but only where it can still report; a hang in
    the vastai CLI or an SSH wait it does not own would otherwise spend the job
    budget silently. The cap must stay ABOVE VAST_PROVISION_DEADLINE_S so the
    script's readable PROVISIONING message wins the race in the normal case.
    """
    import yaml

    spec = yaml.safe_load((_repo_root() / ".github" / "workflows" / workflow).read_text())
    steps = [
        step
        for job in spec["jobs"].values()
        for step in (job.get("steps") or [])
        if step.get("id") == "provision"
    ]
    assert steps, f"{workflow} has no step id 'provision'"
    for step in steps:
        cap = step.get("timeout-minutes")
        assert cap is not None, f"{workflow}: the provision step has no timeout-minutes"
        assert 20 < cap <= 30, (
            f"{workflow}: provision cap of {cap} min should sit just above the "
            f"script's own 20-minute deadline"
        )
