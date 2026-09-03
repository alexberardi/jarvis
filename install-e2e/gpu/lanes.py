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
        # Widened 2026-09-02. Restricting to two consumer cards left the KVM
        # pool essentially empty: the spike found ONE qualifying VM offer
        # marketplace-wide, and that host hung in 'loading' for 600s without
        # ever pulling the VM image. vms_enabled is the filter that hurts (32
        # offers without it, 1 with it) and cannot be dropped — the harness
        # needs a real VM to run Docker — so widen the GPU set instead.
        #
        # Everything here is >=16GB VRAM, which comfortably fits the workload
        # (source builds + an 8B Q4 GGUF + whisper + TTS). All are NVIDIA, so
        # the CUDA device_markers below still apply.
        gpu_names=(
            "RTX_4090", "RTX_3090", "RTX_3090_Ti", "RTX_5090",
            "RTX_4080", "RTX_4080_SUPER",
            "RTX_A5000", "RTX_A4500", "RTX_A6000",
            "L4", "A10",
        ),
        # TEMPORARY raise from 0.60. Both GPU lanes failed to provision on
        # 2026-09-02 with "0 qualifying offer(s)" — the marketplace had nothing
        # at <=$0.60/hr meeting vms_enabled + disk_space>=100. VM (KVM) offers
        # are far scarcer than container offers, so the VM filter plus the disk
        # floor is what prices us out, not the GPU choice.
        #
        # A quickstart run is ~1-2h of source builds, so at this cap a run costs
        # roughly $1.50-3.00. Lower it once the spike shows where offers
        # actually clear.
        max_dph=1.50,
        disk_gb=100,
        device_markers=("ggml_cuda_init: found", "CUDA devices"),
        # Must be a cuda-* template: ubuntu_cli guests ship NO nvidia driver
        # (proven live — bootstrap exit 42). Boot stalls seen earlier with this
        # tag were the broken cheap hosts, which the fail-fast offer strategy
        # now skips past.
        vm_image="docker.io/vastai/kvm:cuda-12.4.1-auto",
    ),
    # Same hardware and markers as `cuda`, but sized for SOURCE BUILDS rather
    # than image pulls. install-e2e-quickstart runs ./jarvis start --all, which
    # BUILDS ~15 images: llm-proxy (llama.cpp CUDA), whisper-api (torch 2.6.0 +
    # torchaudio cu124 + a pywhispercpp source build), tts and ocr each pulling
    # their own torch stack, plus the buildkit cache for all of it.
    #
    # 100 GB is ample for install-e2e-gpu, which only PULLS prebuilt images, but
    # the quickstart filled it: 92G of 97G used, and whisper-api died with
    #   ERROR: Could not install packages due to an OSError:
    #          [Errno 28] No space left on device
    # taking settings-server, admin, notifications, recipes, ocr and web with it.
    #
    # Kept as its own lane so raising this cannot make install-e2e-gpu pickier
    # about offers than it needs to be — KVM inventory is thin enough already.
    "cuda-quickstart": Lane(
        key="cuda-quickstart",
        gpu_type="nvidia",
        whisper_backend="cuda",
        gpu_names=(
            "RTX_4090", "RTX_3090", "RTX_3090_Ti", "RTX_5090",
            "RTX_4080", "RTX_4080_SUPER",
            "RTX_A5000", "RTX_A4500", "RTX_A6000",
            "L4", "A10",
        ),
        max_dph=1.50,
        disk_gb=250,
        device_markers=("ggml_cuda_init: found", "CUDA devices"),
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
