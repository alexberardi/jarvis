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
case "$GPU_TYPE" in
  nvidia)
    if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L | grep -q GPU; then
      log "FATAL: no NVIDIA GPU visible in guest (nvidia-smi missing or empty)"
      log "PROVISIONING failure — driver/passthrough problem on this host."
      exit 42
    fi
    nvidia-smi -L
    ;;
  amd|amd-rocm)
    # The generated compose maps /dev/kfd + /dev/dri into the GPU containers;
    # both must exist in the guest or the containers can't start.
    if [ ! -e /dev/kfd ] || [ ! -d /dev/dri ]; then
      log "FATAL: /dev/kfd or /dev/dri missing — amdgpu driver not up in guest."
      log "PROVISIONING failure — this host's VM image lacks the AMD driver."
      ls -la /dev/kfd /dev/dri 2>&1 || true
      exit 42
    fi
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
