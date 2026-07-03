#!/usr/bin/env python3
"""One-shot marketplace spike — run BEFORE enabling the nightly GPU lanes.

Answers the design's open questions with live data:
  1. Do VM-capable (vms_enabled) offers exist for every lane — especially the
     AMD lanes, where the VM×consumer-AMD intersection is the known risk?
  2. What do they cost vs. our per-lane dph caps?

Usage:
    VAST_API_KEY=... python install-e2e/gpu/spike_availability.py

If an AMD lane shows 0 VM offers, don't enable that lane's schedule — see the
fallback options in prds/gpu-install-e2e.md (hourly dedicated 7900 XTX host
behind the same provisioner interface, or a self-hosted runner on the RDNA4
box).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lanes import LANES  # noqa: E402
from provision_vast import offer_query, vastai  # noqa: E402


def main() -> None:
    if not os.environ.get("VAST_API_KEY"):
        raise SystemExit("VAST_API_KEY is not set")

    exit_code = 0
    for key, lane in LANES.items():
        query = offer_query(key)
        offers = vastai("search", "offers", query, "--order", "dph_total") or []
        # Same query WITHOUT the VM constraint, to show whether vms_enabled is
        # the limiting filter (container offers exist but VMs don't).
        no_vm_query = query.replace("vms_enabled=true ", "")
        no_vm = vastai("search", "offers", no_vm_query, "--order", "dph_total") or []

        print(f"\n=== lane {key} ({lane.gpu_type} / whisper {lane.whisper_backend}) ===")
        print(f"query: {query}")
        print(f"VM offers: {len(offers)}   (without vms_enabled: {len(no_vm)})")
        for o in offers[:8]:
            print(
                f"  offer {o['id']}: {o.get('gpu_name')} ${o.get('dph_total'):.3f}/hr "
                f"disk={o.get('disk_space', 0):.0f}GB down={o.get('inet_down', 0):.0f}Mbps "
                f"rel={o.get('reliability2', o.get('reliability', 0)):.3f} "
                f"geo={o.get('geolocation', '?')}"
            )
        if not offers:
            print(f"  !! NO VM OFFERS — lane '{key}' cannot run on Vast right now")
            exit_code = 1

    if exit_code:
        print("\nSPIKE RESULT: at least one lane has no VM inventory — do not "
              "enable its nightly schedule; see PRD fallbacks.")
    else:
        print("\nSPIKE RESULT: all lanes have VM inventory. Safe to enable.")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
