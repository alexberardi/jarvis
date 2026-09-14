#!/usr/bin/env bash
# Bootstrap a freshly-provisioned Vast.ai VM for the GPU install-e2e.
# Runs ON the VM (piped over SSH: `ssh host 'bash -s' -- <gpu_type> <model_url>`).
#
# Fails FAST and LOUD if the GPU isn't actually visible in the guest — a VM
# without working passthrough must be a PROVISIONING failure at bootstrap,
# never a mystery test failure 20 minutes later.
set -euo pipefail

GPU_TYPE="${1:?usage: bootstrap_remote.sh <nvidia|amd|amd-rocm> <model_url>}"
MODEL_URL="${2:?model url required}"
STORAGE_PATH="${STORAGE_PATH:-/var/lib/jarvis}"

log() { echo "[bootstrap] $*"; }

# ── 1. Wait out cloud-init / apt locks (fresh VMs race their own provisioning) ──
if command -v cloud-init >/dev/null 2>&1; then
  log "waiting for cloud-init..."
  cloud-init status --wait >/dev/null 2>&1 || true
fi
for _ in $(seq 1 30); do
  if ! fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; then break; fi
  sleep 5
done

# ── 2. GPU visibility — the whole point of renting this box ──
# A bounded WAIT, not a one-shot check. `cloud-init status --wait` can return
# before the GPU driver has attached in the guest: on 2026-09-14 this gate fired
# 0.3s after cloud-init returned and threw the run away as a passthrough
# failure, twice on two different hosts. A genuinely broken host still exits 42,
# it just takes GPU_WAIT_SECS longer to say so -- and the elapsed time in the log
# is what tells the two cases apart next time, which a one-shot check never could.
GPU_WAIT_SECS="${GPU_WAIT_SECS:-120}"

gpu_visible() {
  case "$GPU_TYPE" in
    nvidia)       command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L 2>/dev/null | grep -q GPU ;;
    amd|amd-rocm) [ -e /dev/kfd ] && [ -d /dev/dri ] ;;
    *)            return 1 ;;
  esac
}

case "$GPU_TYPE" in
  nvidia|amd|amd-rocm) ;;
  *) log "FATAL: unknown gpu type '$GPU_TYPE'"; exit 2 ;;
esac

gpu_waited=0
until gpu_visible; do
  if [ "$gpu_waited" -ge "$GPU_WAIT_SECS" ]; then
    log "FATAL: no $GPU_TYPE GPU visible in guest after ${gpu_waited}s"
    log "PROVISIONING failure — driver/passthrough problem on this host."
    case "$GPU_TYPE" in
      amd|amd-rocm) ls -la /dev/kfd /dev/dri 2>&1 || true ;;
    esac
    exit 42
  fi
  sleep 5
  gpu_waited=$((gpu_waited + 5))
done
log "GPU visible after ${gpu_waited}s"

case "$GPU_TYPE" in
  nvidia)
    nvidia-smi -L
    ;;
  amd|amd-rocm)
    # The generated compose maps /dev/kfd + /dev/dri into the GPU containers;
    # the wait above is what proves both exist.
    if ! lspci | grep -qiE 'vga|display.*amd|amd.*(vga|display)|\[amd/ati\]'; then
      log "WARNING: lspci shows no AMD display device; continuing on /dev/kfd evidence"
    fi
    ls -la /dev/dri
    ;;
  *)
    log "FATAL: unknown gpu type '$GPU_TYPE'"; exit 2 ;;
esac

# ── 3. Docker (KVM templates may or may not ship it) ──
if ! command -v docker >/dev/null 2>&1; then
  log "installing docker..."
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
docker version --format 'docker {{.Server.Version}}'
if ! docker compose version >/dev/null 2>&1; then
  log "installing docker compose plugin..."
  apt-get update -qq && apt-get install -y -qq docker-compose-plugin
fi
docker compose version

# ── 4. Host storage the generated compose bind-mounts ──
mkdir -p "$STORAGE_PATH/models"
chmod -R 777 "$STORAGE_PATH"

# ── 5. Test model (small GGUF; idempotent, resumable) ──
MODEL_FILE="$STORAGE_PATH/models/$(basename "$MODEL_URL")"
if [ ! -s "$MODEL_FILE" ]; then
  log "downloading test model → $MODEL_FILE"
  curl -fL --retry 4 --retry-delay 5 -C - -o "$MODEL_FILE" "$MODEL_URL"
fi
ls -lh "$MODEL_FILE"

log "READY gpu=$GPU_TYPE storage=$STORAGE_PATH"
