"""Lane definitions for the GPU install-e2e — the single source of truth.

A *lane* is one GPU flavor of the install pattern, tested end-to-end on a
rented Vast.ai VM: which installer --gpu / --whisper-backend values it uses,
which marketplace offers qualify to host it, and which backend-init log
markers prove the GPU was actually used (vs. a silent CPU fallback, which
/health can never see).

Consumed by provision_vast.py (offer query), spike_availability.py,
test_gpu_inference.py (log markers), and the workflow (via `python -m` /
direct import).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lane:
    key: str
    # Installer/admin generator inputs (--gpu / --whisper-backend).
    gpu_type: str
    whisper_backend: str
    # Vast.ai offer filters. gpu_names use Vast's underscore naming.
    gpu_names: tuple[str, ...]
    max_dph: float  # hard $/hr cap — cost guardrail, not a preference
    disk_gb: int
    # ggml backend-init lines (llama.cpp + whisper.cpp share ggml, so the same
    # markers prove the device for both). ANY match passes.
    device_markers: tuple[str, ...]
    # Vast KVM VM template image — MUST be a fully-qualified docker.io/vastai/kvm
    # tag (real tags: hub.docker.com/r/vastai/kvm/tags). The cuda-*-auto images
    # ship the NVIDIA driver; AMD lanes get the plain CLI image.
    vm_image: str
    # How the LLM proxy serves the model on this lane:
    #   "in-process"           — proxy loads the GGUF itself (default; every lane
    #                            below except the sidecar one).
    #   "llama-server-sidecar" — proxy runs a REST backend against a separate
    #                            llama.cpp `llama-server` container (the
    #                            Qwen3.5-9B hybrid-SSM rollout). CUDA-only.
    serving: str = "in-process"
    # Which container's logs carry the ggml backend-init + `offloaded N/M layers`
    # markers Phase G greps. In-process: the proxy loads the model, so the proxy.
    # Sidecar: the proxy is REST and does NO GGUF load — the markers live ONLY in
    # the llama-server container, so reading the proxy's logs would falsely fail.
    marker_container: str = "jarvis-llm-proxy-api"


# Offload proof, common to all lanes: llama.cpp logs "offloaded N/M layers to
# GPU". N must be > 0 — N=0 with a green /health is exactly the silent-CPU
# failure mode this suite exists to catch.
OFFLOAD_PATTERN = r"offloaded (\d+)/\d+ layers to GPU"

LANES: dict[str, Lane] = {
    "cuda": Lane(
        key="cuda",
        gpu_type="nvidia",
        whisper_backend="cuda",
        gpu_names=("RTX_4090", "RTX_3090"),
        max_dph=0.60,
        disk_gb=100,
        device_markers=("ggml_cuda_init: found", "CUDA devices"),
        # Must be a cuda-* template: ubuntu_cli guests ship NO nvidia driver
        # (proven live — bootstrap exit 42). Boot stalls seen earlier with this
        # tag were the broken cheap hosts, which the fail-fast offer strategy
        # now skips past.
        vm_image="docker.io/vastai/kvm:cuda-12.4.1-auto",
    ),
    # Same rented hardware + CUDA markers as `cuda`, but the proxy serves the
    # model through a llama.cpp `llama-server` REST sidecar instead of loading it
    # in-process (the Qwen3.5-9B hybrid-SSM rollout — see
    # jarvis-installer/docs/llama-server-sidecar-rollout.md). CUDA-only: the
    # sidecar image (ghcr.io/ggml-org/llama.cpp, digest-pinned) needs the NVIDIA
    # runtime. Opt-in only — NOT in the nightly default (`cuda`); dispatch
    # `lanes: cuda-sidecar` to run it. DORMANT until the installer/admin
    # generators support the `--serving llama-server-sidecar` enablement flag
    # (rollout §4c) — without it, compose generation errors on an unknown flag.
    "cuda-sidecar": Lane(
        key="cuda-sidecar",
        gpu_type="nvidia",
        whisper_backend="cuda",
        gpu_names=("RTX_4090", "RTX_3090"),
        max_dph=0.60,
        disk_gb=100,
        device_markers=("ggml_cuda_init: found", "CUDA devices"),
        vm_image="docker.io/vastai/kvm:cuda-12.4.1-auto",
        serving="llama-server-sidecar",
        marker_container="llama-server-9b",
    ),
    "vulkan": Lane(
        key="vulkan",
        gpu_type="amd",
        whisper_backend="vulkan",
        # gfx1100/gfx1101 — RDNA3, present in both the rocm image's GPU_TARGETS
        # and the vulkan runtime's Mesa support. Datacenter AMD (MI300X=gfx942)
        # is NOT in our build targets; consumer RDNA is what users run anyway.
        gpu_names=("RX_7900_XTX", "RX_7900_XT"),
        max_dph=0.45,
        disk_gb=100,
        device_markers=("ggml_vulkan: Found", "Vulkan devices"),
        vm_image="docker.io/vastai/kvm:ubuntu_cli",
    ),
    "rocm": Lane(
        key="rocm",
        gpu_type="amd-rocm",
        whisper_backend="rocm",
        gpu_names=("RX_7900_XTX", "RX_7900_XT"),
        max_dph=0.45,
        disk_gb=100,
        # HIP builds log through the CUDA codepath: "found N ROCm devices".
        device_markers=("ROCm devices",),
        vm_image="docker.io/vastai/kvm:ubuntu_cli",
    ),
}

# Small ungated chatml model for the real-inference proof. ~490MB, loads in
# seconds, matches the generated JARVIS_MODEL_CHAT_FORMAT=chatml.
TEST_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    "/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
TEST_MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
