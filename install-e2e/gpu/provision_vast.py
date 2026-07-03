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
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lanes import LANES  # noqa: E402

LABEL = "jarvis-gpu-e2e"
# Vast KVM VM template image (VM offers only accept docker.io/vastai/kvm:*).
# Overridable via --vm-image / VAST_VM_IMAGE — the spike validates the exact
# tag before the nightly is enabled.
DEFAULT_VM_IMAGE = os.environ.get("VAST_VM_IMAGE", "vastai/kvm:ubuntu_22.04-ssh")
DEFAULT_SSH_USER = os.environ.get("VAST_SSH_USER", "root")
CREATE_ATTEMPTS = 5  # cheapest-first offers to try before giving up
SSH_READY_TIMEOUT_S = 15 * 60


def log(msg: str) -> None:
    print(f"[provision-vast] {msg}", file=sys.stderr, flush=True)


def vastai(*args: str, raw: bool = True) -> Any:
    """Run the vastai CLI; parse --raw JSON output."""
    cmd = ["vastai", *args]
    if raw:
        cmd.append("--raw")
    api_key = os.environ.get("VAST_API_KEY", "")
    if api_key:
        cmd += ["--api-key", api_key]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
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
        f"reliability>0.98 inet_down>=200 "
        f"disk_space>={lane.disk_gb} dph_total<={lane.max_dph}"
    )


def search_offers(lane_key: str) -> list[dict]:
    query = offer_query(lane_key)
    log(f"searching offers: {query}")
    offers = vastai("search", "offers", query, "--order", "dph_total") or []
    log(f"{len(offers)} qualifying offer(s)")
    return offers


def ssh_ready(host: str, port: int, user: str, key_path: str | None) -> bool:
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
    return subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0


def wait_ssh(instance_id: int, user: str, key_path: str | None) -> dict:
    """Poll the instance until it is running AND accepts SSH; return conn info."""
    deadline = time.time() + SSH_READY_TIMEOUT_S
    last_status = ""
    while time.time() < deadline:
        info = vastai("show", "instance", str(instance_id))
        status = (info or {}).get("actual_status") or "?"
        if status != last_status:
            log(f"instance {instance_id}: {status}")
            last_status = status
        host = (info or {}).get("ssh_host")
        port = (info or {}).get("ssh_port")
        if status == "running" and host and port:
            if ssh_ready(host, int(port), user, key_path):
                log(f"instance {instance_id} SSH-ready at {user}@{host}:{port}")
                return {"ssh_host": host, "ssh_port": int(port)}
            log("running but SSH not ready yet")
        time.sleep(20)
    raise TimeoutError(
        f"instance {instance_id} not SSH-ready within {SSH_READY_TIMEOUT_S}s "
        "(classify as PROVISIONING failure, not a test failure)"
    )


def provision(lane_key: str, ssh_pubkey: str, vm_image: str, ssh_user: str,
              out_path: str, ssh_key_path: str | None) -> dict:
    lane = LANES[lane_key]
    offers = search_offers(lane_key)
    if not offers:
        raise SystemExit(
            f"PROVISIONING: no qualifying VM offers for lane '{lane_key}' "
            f"(query: {offer_query(lane_key)}). Marketplace may be dry — "
            "see spike_availability.py / the PRD's fallback options."
        )

    pubkey = open(ssh_pubkey).read().strip()
    last_err: Exception | None = None
    for offer in offers[:CREATE_ATTEMPTS]:
        offer_id = offer["id"]
        dph = offer.get("dph_total")
        gpu = offer.get("gpu_name")
        log(f"trying offer {offer_id}: {gpu} @ ${dph}/hr")
        try:
            res = vastai(
                "create", "instance", str(offer_id),
                "--image", vm_image,
                "--disk", str(lane.disk_gb),
                "--label", LABEL,
                "--ssh", "--direct",
            )
            instance_id = int(res["new_contract"])
        except Exception as e:  # noqa: BLE001 — offer races are expected; try next
            log(f"offer {offer_id} failed: {e}")
            last_err = e
            continue

        log(f"created instance {instance_id}; attaching SSH key")
        try:
            vastai("attach", "ssh", str(instance_id), pubkey, raw=False)
            conn = wait_ssh(instance_id, ssh_user, ssh_key_path)
        except Exception as e:  # noqa: BLE001 — don't leak a half-up instance
            log(f"instance {instance_id} never became usable ({e}); destroying")
            try:
                vastai("destroy", "instance", str(instance_id), raw=False)
            except Exception as de:  # noqa: BLE001
                log(f"destroy of {instance_id} ALSO failed ({de}) — janitor will reap")
            last_err = e
            continue

        result = {
            "instance_id": instance_id,
            "lane": lane_key,
            "gpu_name": gpu,
            "dph_total": dph,
            "ssh_user": ssh_user,
            **conn,
        }
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result))
        return result

    raise SystemExit(f"PROVISIONING: all {CREATE_ATTEMPTS} offer attempts failed: {last_err}")


def destroy(instance_id: int) -> None:
    log(f"destroying instance {instance_id}")
    vastai("destroy", "instance", str(instance_id), raw=False)


def janitor(max_age_hours: float) -> None:
    """Destroy any labeled instance older than max_age_hours (leak guard)."""
    instances = vastai("show", "instances") or []
    now = time.time()
    reaped = 0
    for inst in instances:
        if inst.get("label") != LABEL:
            continue
        start = inst.get("start_date") or 0
        age_h = (now - float(start)) / 3600 if start else float("inf")
        if age_h > max_age_hours:
            log(f"janitor: reaping {inst['id']} (age {age_h:.1f}h)")
            try:
                destroy(int(inst["id"]))
                reaped += 1
            except Exception as e:  # noqa: BLE001 — best-effort; next run retries
                log(f"janitor: destroy {inst['id']} failed: {e}")
    log(f"janitor: {reaped} instance(s) reaped")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("provision", help="search + create VM + wait for SSH")
    pp.add_argument("--lane", required=True, choices=sorted(LANES))
    pp.add_argument("--ssh-pubkey", required=True)
    pp.add_argument("--ssh-key", help="private key path for the SSH-ready probe")
    pp.add_argument("--vm-image", default=DEFAULT_VM_IMAGE)
    pp.add_argument("--ssh-user", default=DEFAULT_SSH_USER)
    pp.add_argument("--out", default="provision.json")

    dp = sub.add_parser("destroy", help="destroy one instance")
    dp.add_argument("--instance-id", type=int)
    dp.add_argument("--from", dest="from_file", help="provision.json to read the id from")

    jp = sub.add_parser("janitor", help="reap labeled instances older than --max-age-hours")
    jp.add_argument("--max-age-hours", type=float, default=3.0)

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
        if instance_id is None:
            if not args.from_file:
                raise SystemExit("destroy: need --instance-id or --from")
            instance_id = int(json.load(open(args.from_file))["instance_id"])
        destroy(instance_id)
    elif args.cmd == "janitor":
        janitor(args.max_age_hours)
    elif args.cmd == "search":
        print(json.dumps(search_offers(args.lane), indent=2))


if __name__ == "__main__":
    main()
