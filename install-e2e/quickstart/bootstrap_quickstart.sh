#!/usr/bin/env bash
# Bootstrap a freshly-provisioned Vast.ai VM for the QUICKSTART install-e2e.
# Runs ON the VM (piped over SSH: `ssh host 'bash -s' -- <gpu_type> <ref>`).
#
# This installs PREREQUISITES ONLY. It deliberately does NOT touch the jarvis
# repos, clone anything, or run ./jarvis — those are the SUBJECT of this suite,
# driven by run_quickstart.sh so a failure there is a real finding rather than
# setup noise.
#
# Fails FAST and LOUD if the GPU isn't visible: the whole reason this lane rents
# a GPU box is that jarvis-llm-proxy-api / jarvis-whisper-api / jarvis-tts BUILD
# CUDA-linked wheels from source. A silent CPU box would build a different image
# and prove nothing.
set -euo pipefail

GPU_TYPE="${1:?usage: bootstrap_quickstart.sh <nvidia> [git_ref]}"
JARVIS_ROOT="${JARVIS_ROOT:-/opt/jarvis}"

log() { echo "[bootstrap-qs] $*"; }

# ── 1. Wait out cloud-init / apt locks (fresh VMs race their own provisioning) ──
if command -v cloud-init >/dev/null 2>&1; then
  log "waiting for cloud-init..."
  cloud-init status --wait >/dev/null 2>&1 || true
fi
for _ in $(seq 1 30); do
  if ! fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; then break; fi
  sleep 5
done

# ── 2. GPU visibility — same fail-fast contract as the GPU lane (exit 42) ──
case "$GPU_TYPE" in
  nvidia)
    if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L | grep -q GPU; then
      log "FATAL: no NVIDIA GPU visible in guest (nvidia-smi missing or empty)"
      log "PROVISIONING failure — driver/passthrough problem on this host."
      exit 42
    fi
    nvidia-smi -L
    ;;
  *)
    log "FATAL: quickstart lane is nvidia-only (got '$GPU_TYPE')"; exit 2 ;;
esac

# ── 3. Docker ──
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

# ── 4. NVIDIA Container Toolkit ──
# `./jarvis` overlays docker-compose.gpu.yaml when it detects nvidia-smi, so the
# GPU services request device reservations. Without the toolkit those containers
# fail to START — which would look like a jarvis bug rather than a missing host
# package, so install it here and prove it works before handing over.
if ! docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia; then
  log "installing nvidia-container-toolkit..."
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -qq
  apt-get install -y -qq nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker || service docker restart
fi
log "verifying GPU is visible INSIDE a container..."
if ! docker run --rm --gpus all docker.io/vastai/kvm:cuda-12.4.1-auto nvidia-smi -L 2>/dev/null \
   && ! docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L; then
  log "FATAL: GPU not visible inside containers — toolkit/runtime broken."
  exit 42
fi

# ── 5. Build/runtime prerequisites the ./jarvis CLI itself shells out to ──
# python3-venv: _run_migrations builds a per-service .venv on the HOST.
# openssl: _generate_tokens. jq/git: workflow + clone-repos.sh.
log "installing host prerequisites..."
apt-get update -qq
apt-get install -y -qq git curl jq openssl python3 python3-venv python3-pip build-essential

# ./jarvis init builds a HOST venv per service to run alembic, and six services
# declare requires-python >=3.11 (config-service, auth, logs, command-center,
# tts, whisper-api). The cuda-12.4.1-auto template ships Ubuntu 22.04 whose
# python3 is 3.10.12, so every one of those venvs failed:
#   ERROR: Package 'jarvis-auth' requires a different Python: 3.10.12 not in '<4.0,>=3.11'
# -> "Migrations: 3 OK, 7 failed" and a stack that cannot come up.
#
# Install 3.11 and put it FIRST on PATH via /usr/local/bin rather than
# repointing /usr/bin/python3, which would break apt's own tooling.
PY_MAJOR_MINOR=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
log "system python3 is ${PY_MAJOR_MINOR}"
if [ "$(printf '%s\n3.11\n' "$PY_MAJOR_MINOR" | sort -V | head -1)" != "3.11" ]; then
  log "installing python3.11 (services require >=3.11)"
  apt-get install -y -qq software-properties-common
  add-apt-repository -y ppa:deadsnakes/ppa >/dev/null 2>&1
  apt-get update -qq
  apt-get install -y -qq python3.11 python3.11-venv python3.11-dev
  ln -sf /usr/bin/python3.11 /usr/local/bin/python3
  hash -r
  log "python3 is now $(/usr/local/bin/python3 -V 2>&1)"
fi

# ── 6. Disk headroom check ──
# Source-building ~15 images (CUDA llama.cpp + whisper.cpp wheels) is far heavier
# than pulling them. Fail here with a clear message rather than 40 minutes into a
# build with a confusing ENOSPC.
AVAIL_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
log "root filesystem free: ${AVAIL_GB}G"
if [ "${AVAIL_GB:-0}" -lt 150 ]; then
  log "FATAL: <150G free — the full source build needs ~150G+ (observed 92G used
        on a 97G disk before whisper-api hit ENOSPC). Raise the lane's disk_gb."
  exit 42
fi

mkdir -p "$JARVIS_ROOT"
log "READY gpu=$GPU_TYPE jarvis_root=$JARVIS_ROOT free=${AVAIL_GB}G"
