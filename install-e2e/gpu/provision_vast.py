#!/usr/bin/env python3
"""Vast.ai VM provisioner for the GPU install-e2e lanes.

Thin wrapper over the official `vastai` CLI (pip install vastai) with the
narrow interface the workflow needs — deliberately small so the provider can
be swapped per-lane if Vast's AMD/VM inventory dries up:

    provision  --lane cuda --ssh-pubkey PATH --out provision.json
    destroy    --instance-id 12345          (or --from provision.json)
    janitor    --max-age-hours 3

Design notes:
- Only VM offers qualify (`vms_enabled=true`): the install pattern is docker
  compose, and only Vast's KVM VMs support nested containers. Container
  offers are useless here.
- Every instance is labeled LABEL so the janitor can reap leaks — a leaked
  GPU instance is a money leak, so janitor runs at the start AND end of every
  workflow run, and destroys anything labeled older than --max-age-hours.
- Offers are tried cheapest-first; marketplace create races (someone rents
  the offer first) fall through to the next candidate.
- stdout is machine-readable JSON only; progress goes to stderr.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lanes import LANES  # noqa: E402

# All instances are labeled with this prefix (janitor matches on it). Each
# provision call appends lane + run id so concurrent matrix lanes can find
# their own instance by label — the ground truth when create's stdout is
# unparseable (observed live: `create instance` can exit 0 with EMPTY stdout
# while the instance IS created — parse-and-pray leaks rented GPUs).
LABEL = "jarvis-gpu-e2e"
# Per-lane VM template images live in lanes.py (fully-qualified
# docker.io/vastai/kvm:* tags — VM offers accept nothing else). VAST_VM_IMAGE /
# --vm-image overrides for experimentation.
VM_IMAGE_OVERRIDE = os.environ.get("VAST_VM_IMAGE", "")
DEFAULT_SSH_USER = os.environ.get("VAST_SSH_USER", "root")
CREATE_ATTEMPTS = 6  # offers to try before giving up
# Strategy learned across runs 4-7 (11 boot attempts): broken/cold hosts stall
# in loading/created FOREVER, while every host that ever worked reached
# "running" in <7 min. So: short per-offer budgets, more offers, and an
# overall wall-clock cap — fail fast through the junk to find a warm host.
RUNNING_TIMEOUT_S = 10 * 60
# "running" means KVM started — the guest OS + cloud-init are still booting
# inside; observed refusals past 6 min. The overall PROVISION_DEADLINE_S is
# the real cap.
SSH_AFTER_RUNNING_TIMEOUT_S = 12 * 60
PROVISION_DEADLINE_S = 60 * 60
# The cheapest offers are adversely selected (they're cheap because nobody can
# use them). Empirically the CN-hosted 3090s never finished a single image
# pull — try them last, not first.
DEPRIORITIZED_GEO_SUFFIXES = (", CN", ", HK")


def log(msg: str) -> None:
    print(f"[provision-vast] {msg}", file=sys.stderr, flush=True)


def vastai(*args: str, raw: bool = True, confirm: bool = False) -> Any:
    """Run the vastai CLI; parse --raw JSON output.

    confirm=True feeds 'y' on stdin: destructive subcommands (destroy) prompt
    interactively — in CI the prompt silently defaults to No while the CLI
    still exits 0, which is how 29 instances once leaked behind green steps."""
    cmd = ["vastai", *args]
    if raw:
        cmd.append("--raw")
    api_key = os.environ.get("VAST_API_KEY", "")
    if api_key:
        cmd += ["--api-key", api_key]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180,
        input="y\n" if confirm else None,
    )
    # The vastai CLI is loose with exit codes and often reports API errors on
    # stderr while exiting 0 — always surface stderr so failures aren't silent.
    if proc.stderr.strip():
        log(f"vastai stderr: {redact(proc.stderr.strip()[:800])}")
    if proc.returncode != 0:
        redacted = " ".join(a for a in cmd if a != api_key)
        raise RuntimeError(
            f"`{redacted}` failed (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    if not raw:
        return proc.stdout
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def offer_query(lane_key: str) -> str:
    lane = LANES[lane_key]
    names = ", ".join(lane.gpu_names)
    return (
        f"gpu_name in [{names}] "
        f"num_gpus=1 rentable=true verified=true vms_enabled=true "
        # direct_port_count: VMs need a DIRECT ssh port — observed live that a
        # VM on a proxy-only host reaches `running` with direct_port_start=-1
        # and the ssh proxy never accepts (Connection refused, forever).
        # inet_down>=500: hosts must pull the multi-GB KVM image before boot;
        # slow pipes blow the running-timeout.
        f"direct_port_count>=1 reliability>0.98 inet_down>=500 "
        f"disk_space>={lane.disk_gb} dph_total<={lane.max_dph}"
    )


def search_offers(lane_key: str) -> list[dict]:
    query = offer_query(lane_key)
    log(f"searching offers: {query}")
    offers = vastai("search", "offers", query, "--order", "dph_total") or []
    # One offer per machine (a broken host is broken for all its offers), and
    # deprioritized geos go to the back of the cheapest-first order.
    seen_machines: set = set()
    preferred, deprioritized = [], []
    for o in offers:
        mid = o.get("machine_id")
        if mid in seen_machines:
            continue
        seen_machines.add(mid)
        geo = str(o.get("geolocation") or "")
        (deprioritized if geo.endswith(DEPRIORITIZED_GEO_SUFFIXES) else preferred).append(o)
    ordered = preferred + deprioritized
    log(f"{len(offers)} qualifying offer(s) → {len(ordered)} distinct machines "
        f"({len(deprioritized)} deprioritized by geo)")
    return ordered


def register_account_ssh_key(pubkey: str) -> int | None:
    """VM creates hard-require an ACCOUNT-level SSH key ([no_ssh_key_for_vm])
    — post-create `attach ssh` is too late. Register the run's ephemeral key
    and return its id so teardown can delete it."""
    try:
        out = vastai("create", "ssh-key", pubkey, raw=False)
        log(f"registered account ssh-key: {out.strip() or '(no output)'}")
    except Exception as e:  # noqa: BLE001 — may already exist; the lookup decides
        log(f"create ssh-key: {e}")
    try:
        for key in vastai("show", "ssh-keys") or []:
            if (key.get("public_key") or "").strip() == pubkey:
                return int(key["id"])
    except Exception as e:  # noqa: BLE001
        log(f"show ssh-keys failed: {e}")
    return None


def delete_account_ssh_key(key_id: int) -> None:
    try:
        vastai("delete", "ssh-key", str(key_id), raw=False, confirm=True)
        log(f"deleted account ssh-key {key_id}")
    except Exception as e:  # noqa: BLE001 — hygiene only; never fail teardown on it
        log(f"delete ssh-key {key_id} failed: {e}")


def ssh_url(instance_id: int) -> tuple[str, str, int] | None:
    """`vastai ssh-url` returns the CLI's canonical ssh://user@host:port —
    it knows the proxy-vs-direct rules better than we do."""
    try:
        out = vastai("ssh-url", str(instance_id), raw=False).strip()
        m = re.search(r"ssh://([^@]+)@([^:]+):(\d+)", out)
        if m:
            return m.group(1), m.group(2), int(m.group(3))
    except Exception as e:  # noqa: BLE001
        log(f"ssh-url failed: {e}")
    return None


def find_instance_by_label(label: str) -> dict | None:
    """Authoritative lookup: the label we passed to create is the one thing we
    control end-to-end, regardless of what create printed."""
    for inst in vastai("show", "instances") or []:
        if inst.get("label") == label:
            return inst
    return None


def parse_created_id(create_output: str) -> int | None:
    """Best-effort: create historically prints `{'success': True,
    'new_contract': 12345}` (python-repr, NOT json) or nothing at all."""
    m = re.search(r"new_contract['\"\s:=]+(\d+)", create_output)
    return int(m.group(1)) if m else None


def redact(text: str) -> str:
    """create's output includes a per-instance `instance_api_key` — never let
    a credential (even an instance-scoped, dies-with-the-instance one) reach
    the public Actions log."""
    return re.sub(
        r"(instance_api_key['\"]?\s*[:=]\s*['\"]?)[0-9a-fA-F]+", r"\1<redacted>", text
    )


def ssh_probe(host: str, port: int, user: str, key_path: str | None) -> tuple[bool, str]:
    """One SSH attempt; returns (ok, stderr) so failures are diagnosable
    (Connection refused = sshd not up yet; Permission denied = key problem;
    timeout = wrong host/port or firewall)."""
    cmd = [
        "ssh",
        "-p", str(port),
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
    ]
    if key_path:
        cmd += ["-i", key_path]
    cmd += [f"{user}@{host}", "true"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return proc.returncode == 0, (proc.stderr or "").strip()


def wait_ssh(instance_id: int, user: str, key_path: str | None) -> dict:
    """Two phases (budgeted separately — see the constants): wait for the VM
    to reach `running`, then wait for sshd to accept our key."""
    running_deadline = time.time() + RUNNING_TIMEOUT_S
    last_status = ""
    info: dict = {}
    while True:
        if time.time() > running_deadline:
            raise TimeoutError(
                f"instance {instance_id} stuck in '{last_status}' after "
                f"{RUNNING_TIMEOUT_S}s (host still pulling the VM image?) — "
                "PROVISIONING failure, not a test failure"
            )
        info = vastai("show", "instance", str(instance_id)) or {}
        status = info.get("actual_status") or "?"
        if status != last_status:
            log(f"instance {instance_id}: {status}")
            last_status = status
        if status == "running" and info.get("ssh_host") and info.get("ssh_port"):
            break
        time.sleep(20)

    log(
        f"instance {instance_id} running; port fields: "
        f"ssh={info.get('ssh_host')}:{info.get('ssh_port')} "
        f"public_ipaddr={info.get('public_ipaddr')} "
        f"direct_port_start={info.get('direct_port_start')} "
        f"machine_dir_ssh_port={info.get('machine_dir_ssh_port')} "
        f"ports={json.dumps(info.get('ports'))[:400]}"
    )
    ssh_deadline = time.time() + SSH_AFTER_RUNNING_TIMEOUT_S
    last_err = ""
    seen: set = set()
    while time.time() < ssh_deadline:
        # The proxy record (ssh_host/ssh_port, also what ssh-url returns) has
        # refused connections for entire windows on live VMs, so probe EVERY
        # plausible endpoint each round and take the first that answers.
        info = vastai("show", "instance", str(instance_id)) or info
        candidates: list[tuple[str, int]] = []
        url = ssh_url(instance_id)
        if url:
            candidates.append((url[1], url[2]))
        pub = info.get("public_ipaddr")
        port_map = info.get("ports") or {}
        for binding in port_map.get("22/tcp") or []:
            if pub and binding.get("HostPort"):
                candidates.append((pub, int(binding["HostPort"])))
        if pub and info.get("machine_dir_ssh_port"):
            candidates.append((pub, int(info["machine_dir_ssh_port"])))
        if info.get("ssh_host") and info.get("ssh_port"):
            candidates.append((str(info["ssh_host"]), int(info["ssh_port"])))
        seen: set = set()
        for host, port in candidates:
            if (host, port) in seen:
                continue
            seen.add((host, port))
            ok, err = ssh_probe(host, port, user, key_path)
            if ok:
                log(f"instance {instance_id} SSH-ready at {user}@{host}:{port}")
                return {"ssh_host": host, "ssh_port": port}
            if err and err != last_err:
                log(f"ssh not ready ({user}@{host}:{port}): {err.splitlines()[-1][:200]}")
                last_err = err
        time.sleep(20)
    raise TimeoutError(
        f"instance {instance_id} running but SSH never accepted on any of "
        f"{sorted(seen)} (last error: {last_err.splitlines()[-1][:200] if last_err else 'none'}) "
        "— PROVISIONING failure, not a test failure"
    )


def provision(lane_key: str, ssh_pubkey: str, vm_image: str | None, ssh_user: str,
              out_path: str, ssh_key_path: str | None) -> dict:
    lane = LANES[lane_key]
    vm_image = vm_image or VM_IMAGE_OVERRIDE or lane.vm_image
    log(f"VM template image: {vm_image}")
    offers = search_offers(lane_key)
    if not offers:
        raise SystemExit(
            f"PROVISIONING: no qualifying VM offers for lane '{lane_key}' "
            f"(query: {offer_query(lane_key)}). Marketplace may be dry — "
            "see spike_availability.py / the PRD's fallback options."
        )

    pubkey = open(ssh_pubkey).read().strip()
    ssh_key_id = register_account_ssh_key(pubkey)
    run_label = f"{LABEL}-{lane_key}-{os.environ.get('GITHUB_RUN_ID', 'local')}"
    provision_deadline = time.time() + PROVISION_DEADLINE_S
    last_err: Exception | None = None
    for offer in offers[:CREATE_ATTEMPTS]:
        if time.time() > provision_deadline:
            log("overall provisioning deadline reached; giving up")
            break
        offer_id = offer["id"]
        dph = offer.get("dph_total")
        gpu = offer.get("gpu_name")
        log(f"trying offer {offer_id}: {gpu} @ ${dph}/hr")
        instance_id: int | None = None
        try:
            out = vastai(
                "create", "instance", str(offer_id),
                "--image", vm_image,
                "--disk", str(lane.disk_gb),
                "--label", run_label,
                "--ssh", "--direct",
                raw=False,
            )
            log(f"create output: {redact(out.strip()) or '(empty)'}")
            instance_id = parse_created_id(out)
        except Exception as e:  # noqa: BLE001 — offer races are expected; try next
            log(f"create on offer {offer_id} failed: {e}")
            last_err = e
        if instance_id is None:
            # stdout was useless — the label is the source of truth. Give the
            # API a moment to show it, then look it up.
            time.sleep(10)
            inst = find_instance_by_label(run_label)
            if inst:
                instance_id = int(inst["id"])
                log(f"create output unparseable but instance {instance_id} "
                    f"exists with label {run_label}")
        if instance_id is None:
            log(f"offer {offer_id}: no instance materialized; next offer")
            continue

        log(f"created instance {instance_id}; attaching SSH key")
        try:
            # Belt-and-braces: the account key above is what VMs actually use;
            # attach is instance-level and may be a no-op for VM templates.
            try:
                vastai("attach", "ssh", str(instance_id), pubkey, raw=False)
            except Exception as e:  # noqa: BLE001
                log(f"attach ssh (non-fatal): {e}")
            conn = wait_ssh(instance_id, ssh_user, ssh_key_path)
        except Exception as e:  # noqa: BLE001 — don't leak a half-up instance
            log(f"instance {instance_id} never became usable ({e}); destroying")
            try:
                destroy(instance_id)  # verified — raises if it survives
            except Exception as de:  # noqa: BLE001
                log(f"destroy of {instance_id} FAILED ({de}) — clean-gate will flag it")
            last_err = e
            continue

        result = {
            "instance_id": instance_id,
            "lane": lane_key,
            "label": run_label,
            "gpu_name": gpu,
            "dph_total": dph,
            "ssh_user": ssh_user,
            "ssh_key_id": ssh_key_id,
            **conn,
        }
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result))
        return result

    raise SystemExit(f"PROVISIONING: all {CREATE_ATTEMPTS} offer attempts failed: {last_err}")


def instance_alive(instance_id: int) -> bool:
    try:
        info = vastai("show", "instance", str(instance_id))
    except Exception:  # noqa: BLE001 — a lookup blip must not report "gone"
        return True
    # A destroyed contract comes back empty/None or without an id.
    return bool(info) and info.get("id") is not None


def destroy(instance_id: int) -> None:
    """VERIFIED destroy. Learned the hard way (29 leaked instances, account
    drained): `vastai destroy instance` can exit 0 with empty stderr while
    destroying NOTHING — its stdout carries the real result. Never trust the
    exit code; confirm the instance is actually gone, retry once, and raise
    loudly if it survives so no green step ever hides a billing leak."""
    for attempt in (1, 2):
        out = vastai("destroy", "instance", str(instance_id), raw=False, confirm=True)
        log(f"destroy {instance_id} (attempt {attempt}) stdout: {redact(out.strip()) or '(empty)'}")
        # Observed live: slow hosts take >60s to actually reap a destroyed
        # contract (two false "SURVIVED" alarms whose instances were gone by
        # clean-gate time). 3 min per attempt keeps the check honest without
        # crying wolf.
        deadline = time.time() + 180
        while time.time() < deadline:
            if not instance_alive(instance_id):
                log(f"instance {instance_id} confirmed destroyed")
                return
            time.sleep(5)
        log(f"instance {instance_id} STILL ALIVE after destroy attempt {attempt}")
    raise RuntimeError(
        f"instance {instance_id} SURVIVED two destroy attempts — it is still "
        "billing. Destroy it manually at https://cloud.vast.ai/instances/"
    )


def list_labeled_instances() -> list[dict]:
    return [
        inst for inst in (vastai("show", "instances") or [])
        if str(inst.get("label") or "").startswith(LABEL)
    ]


def janitor(max_age_hours: float) -> None:
    """Destroy any labeled instance older than max_age_hours (leak guard).
    Exits NONZERO if anything it tried to reap is still alive — a leaked
    instance bills forever; silence must never look like success."""
    now = time.time()
    reaped, survivors = 0, 0
    for inst in list_labeled_instances():
        start = inst.get("start_date") or 0
        age_h = (now - float(start)) / 3600 if start else float("inf")
        if age_h > max_age_hours:
            log(f"janitor: reaping {inst['id']} (age {age_h:.1f}h, "
                f"status {inst.get('actual_status')})")
            try:
                destroy(int(inst["id"]))
                reaped += 1
            except Exception as e:  # noqa: BLE001 — keep reaping the rest first
                log(f"janitor: {e}")
                survivors += 1
    log(f"janitor: {reaped} reaped, {survivors} SURVIVED")
    if survivors:
        raise SystemExit(
            f"janitor: {survivors} labeled instance(s) could not be destroyed "
            "and are still billing — destroy manually at "
            "https://cloud.vast.ai/instances/"
        )


def clean_gate() -> None:
    """End-of-run gate: FAIL if any instance created by THIS workflow run
    (label carries GITHUB_RUN_ID; sibling matrix lanes share it, so the gate
    runs per-lane but a sibling's still-active instance is filtered by lane)
    is still alive. The teardown steps individually verify, but this is the
    single backstop that makes 'this run left nothing billing' an asserted
    fact instead of an assumption."""
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    lane = os.environ.get("LANE", "")
    marker = f"{LABEL}-{lane}-{run_id}" if lane else f"-{run_id}"
    leaked = []
    for inst in list_labeled_instances():
        label = str(inst.get("label") or "")
        if not (label.endswith(f"-{run_id}") and (not lane or label == marker)):
            continue
        leaked.append(f"{inst['id']} (label {label}, "
                      f"status {inst.get('actual_status')})")
    if leaked:
        raise SystemExit(
            "CLEAN GATE FAILED — this run's instance(s) still alive and billing:\n  "
            + "\n  ".join(leaked)
            + "\nDestroy manually at https://cloud.vast.ai/instances/"
        )
    log(f"clean gate: no live instances for {marker}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("provision", help="search + create VM + wait for SSH")
    pp.add_argument("--lane", required=True, choices=sorted(LANES))
    pp.add_argument("--ssh-pubkey", required=True)
    pp.add_argument("--ssh-key", help="private key path for the SSH-ready probe")
    pp.add_argument("--vm-image", default=None, help="override the lane's VM template image")
    pp.add_argument("--ssh-user", default=DEFAULT_SSH_USER)
    pp.add_argument("--out", default="provision.json")

    dp = sub.add_parser("destroy", help="destroy one instance")
    dp.add_argument("--instance-id", type=int)
    dp.add_argument("--from", dest="from_file", help="provision.json to read the id from")

    jp = sub.add_parser("janitor", help="reap labeled instances older than --max-age-hours")
    jp.add_argument("--max-age-hours", type=float, default=3.0)

    sub.add_parser("clean-gate", help="fail if this run (GITHUB_RUN_ID + LANE) left instances alive")

    sp = sub.add_parser("search", help="print qualifying offers for a lane (JSON)")
    sp.add_argument("--lane", required=True, choices=sorted(LANES))

    args = p.parse_args()
    if not os.environ.get("VAST_API_KEY"):
        raise SystemExit("VAST_API_KEY is not set")

    if args.cmd == "provision":
        provision(args.lane, args.ssh_pubkey, args.vm_image, args.ssh_user,
                  args.out, args.ssh_key)
    elif args.cmd == "destroy":
        instance_id = args.instance_id
        ssh_key_id = None
        if instance_id is None:
            if not args.from_file:
                raise SystemExit("destroy: need --instance-id or --from")
            info = json.load(open(args.from_file))
            instance_id = int(info["instance_id"])
            ssh_key_id = info.get("ssh_key_id")
        destroy(instance_id)
        if ssh_key_id:
            delete_account_ssh_key(int(ssh_key_id))
    elif args.cmd == "janitor":
        janitor(args.max_age_hours)
    elif args.cmd == "clean-gate":
        clean_gate()
    elif args.cmd == "search":
        print(json.dumps(search_offers(args.lane), indent=2))


if __name__ == "__main__":
    main()
