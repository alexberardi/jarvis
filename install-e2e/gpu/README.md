# install-e2e/gpu — nightly GPU lanes on rented VMs

Proves the install pattern **works on real GPUs** — both generators (installer
export compose AND admin SYNC/reconcile compose), all three Linux GPU flavors —
by renting a Vast.ai KVM VM per lane, standing the stack up remotely, and
asserting real inference ran **on the device** (not a silent CPU fallback).

Workflow: [`.github/workflows/install-e2e-gpu.yml`](../../.github/workflows/install-e2e-gpu.yml).
(Full design rationale lives in the maintainer's local `prds/gpu-install-e2e.md`.)

| Lane | `--gpu` | LLM/whisper images | Rented GPU |
|---|---|---|---|
| `cuda` | `nvidia` | `latest-cuda` | RTX 4090 / 3090 |
| `vulkan` | `amd` | `latest-vulkan` | RX 7900 XTX / XT |
| `rocm` | `amd-rocm` | `latest-rocm` | RX 7900 XTX / XT (gfx1100 — in the image's GPU_TARGETS; MI300X/gfx942 is NOT) |

Apple Silicon / Metal stays manual.

## How it runs

The GitHub runner stays the brain; the VM is a disposable docker host:

- `provision_vast.py` rents the cheapest qualifying **VM** offer
  (`vms_enabled=true` — container offers can't run compose), labels it
  `jarvis-gpu-e2e`, waits for SSH. `janitor` reaps leaked instances (runs at
  start + end of every workflow run).
- `bootstrap_remote.sh` fails fast if the GPU isn't visible in the guest,
  installs docker if missing, downloads the small test model
  (Qwen2.5-0.5B GGUF) into `/var/lib/jarvis/models`.
- `DOCKER_HOST=ssh://` points compose/`docker logs` at the VM; SSH `-L`
  tunnels let the existing `install-e2e` pytest phases hit `localhost` ports
  unchanged.
- `docker-compose.gpu-ci-override.yaml` only points `JARVIS_MODEL_NAME` at the
  test model — unlike the CPU lane's override it does **not** swap to the
  REST/OpenAI backend, because exercising the real local backend is the point.
- `test_gpu_inference.py` (Phase G) is the new value: real chat completion,
  tts→whisper round trip, and ggml backend-init log markers
  (`lanes.py`) proving device init + `offloaded N/M layers to GPU` with N>0.

## Enabling (one-time)

1. Create a Vast.ai account + API key; fund modestly (~$25/mo covers nightly).
2. Verify marketplace inventory — **especially the AMD×VM intersection**:
   `VAST_API_KEY=... python install-e2e/gpu/spike_availability.py`
   Also confirm `DEFAULT_VM_IMAGE` / `DEFAULT_SSH_USER` in `provision_vast.py`
   against the current Vast VM template docs.
3. Add repo secret `VAST_API_KEY` to `alexberardi/jarvis`.
4. Dispatch `install-e2e-gpu` with `lanes: cuda` once and watch it, then let
   the nightly schedule take over. Without the secret, lanes no-op green.

**AMD status (spike 2026-07-02): Vast had ZERO rentable AMD offers
marketplace-wide** (`gpu_arch=amd` → 0, bare `gpu_name in [RX_7900_XTX, RX_7900_XT]`
→ 0), so the nightly runs `cuda` only and the nightly spike keeps watching.
When AMD supply appears, widen the schedule default in the workflow's plan
job. Fallbacks if it never does: an hourly dedicated 7900 XTX host behind the
same narrow provisioner interface (search/create/wait/destroy is all the
workflow uses), or a self-hosted runner on a real RDNA box.

## Failure triage

- **`PROVISIONING:` / bootstrap exit 42** — marketplace/passthrough flake, not
  a Jarvis regression. Re-run; if persistent, run the spike.
- **Phase 1/1.5 red** — the install pattern itself broke on this GPU flavor
  (same meaning as the CPU workflow's phases).
- **Phase G red** — the stack is up but the GPU didn't do the work: missing
  device marker or `offloaded 0/N` means the image fell back to CPU; a failed
  chat/round-trip means the backend broke on this hardware (the RDNA4 class).
- **SYNC steps red with export steps green** — the admin generator lags the
  installer for GPU config (the 2026-06 outage shape, GPU edition).
