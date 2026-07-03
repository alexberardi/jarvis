"""Phase G — the GPU actually did the work.

Everything before this phase proves the install pattern *deployed* (containers
running, healthchecks green, migrations at head). None of it can distinguish
"inference runs on the GPU" from "inference silently fell back to CPU" — the
exact failure mode that shipped the RDNA4 breakage class. This phase can:

  1. Real inference through each service's public endpoint (chat completion on
     the local GGUF; tts /speak → whisper /transcribe round trip).
  2. Backend-init log markers: llama.cpp/whisper.cpp print which device ggml
     initialized (CUDA/ROCm/Vulkan) and how many layers were offloaded. A
     0-layers offload or a missing device line fails, green /health or not.

Env contract (set by the workflow):
    JARVIS_E2E_LANE             cuda | vulkan | rocm  (required)
    JARVIS_E2E_WHISPER_BACKEND  cpu | cuda | vulkan | rocm (default: lane's)
    JARVIS_E2E_GEN_FILE         generated compose to parse app creds from
                                (default: install-e2e/docker-compose.gen.yaml)
    JARVIS_E2E_EXPECT_AUTH      "0" on the admin SYNC stack, whose placeholder
                                app creds aren't registered in jarvis-auth —
                                HTTP inference tests skip, log markers still run.
    DOCKER_HOST                 ssh://… — docker log reads go to the rented VM.

Run after test_deployment.py (which blocks until /health is green — and the
model service only starts serving after weights load, so markers exist by now).
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import wave
from functools import lru_cache

import pytest
import requests
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lanes import LANES, OFFLOAD_PATTERN  # noqa: E402

LANE_KEY = os.environ.get("JARVIS_E2E_LANE", "")
LANE = LANES.get(LANE_KEY)
WHISPER_BACKEND = os.environ.get(
    "JARVIS_E2E_WHISPER_BACKEND", LANE.whisper_backend if LANE else "cpu"
)
GEN_FILE = os.environ.get(
    "JARVIS_E2E_GEN_FILE", os.path.join("install-e2e", "docker-compose.gen.yaml")
)
EXPECT_AUTH = os.environ.get("JARVIS_E2E_EXPECT_AUTH", "1") != "0"

LLM_URL = "http://localhost:7704"
WHISPER_URL = "http://localhost:7706"
TTS_URL = "http://localhost:7707"

pytestmark = pytest.mark.skipif(
    LANE is None, reason="JARVIS_E2E_LANE not set to a known lane (cuda|vulkan|rocm)"
)

needs_auth = pytest.mark.skipif(
    not EXPECT_AUTH,
    reason="SYNC stack: placeholder app creds aren't registered in jarvis-auth "
    "(known gap, see install-e2e.yml sync-live) — log markers still assert GPU use",
)


@lru_cache(maxsize=1)
def app_headers() -> dict[str, str]:
    """App-auth creds, parsed from the generated compose (export mode inlines
    them and seeds matching AppClient rows in jarvis-auth)."""
    with open(GEN_FILE) as f:
        compose = yaml.safe_load(f)
    env = compose["services"]["jarvis-llm-proxy-api"]["environment"]
    return {"X-Jarvis-App-Id": env["JARVIS_APP_ID"], "X-Jarvis-App-Key": env["JARVIS_APP_KEY"]}


def container_logs(name: str) -> str:
    """docker logs — honors DOCKER_HOST, so this reads the rented VM's daemon."""
    proc = subprocess.run(
        ["docker", "logs", name], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, f"docker logs {name} failed: {proc.stderr[-500:]}"
    return proc.stdout + proc.stderr


# ── LLM: real completion through the local GGUF on the GPU ──────────────────


@needs_auth
def test_chat_completion_real_local_model():
    r = requests.post(
        f"{LLM_URL}/v1/chat/completions",
        headers=app_headers(),
        json={
            "model": "live",
            "messages": [{"role": "user", "content": "Reply with one short sentence: what is 2+2?"}],
            "max_tokens": 40,
            "temperature": 0,
        },
        timeout=300,  # first call may include warmup on a cold backend
    )
    assert r.status_code == 200, f"chat completion failed: {r.status_code} {r.text[:500]}"
    content = r.json()["choices"][0]["message"]["content"]
    assert content and content.strip(), f"empty completion: {r.json()}"


def test_llm_backend_initialized_gpu_device():
    logs = container_logs("jarvis-llm-proxy-api")
    assert any(m in logs for m in LANE.device_markers), (
        f"lane '{LANE.key}': none of {LANE.device_markers} in llm-proxy logs — "
        "the backend did not initialize the GPU (silent CPU fallback?)"
    )


def test_llm_layers_offloaded_to_gpu():
    logs = container_logs("jarvis-llm-proxy-api")
    matches = [int(m.group(1)) for m in re.finditer(OFFLOAD_PATTERN, logs)]
    assert matches, "no 'offloaded N/M layers to GPU' line in llm-proxy logs"
    assert max(matches) > 0, (
        f"model loaded with 0 GPU layers (offload counts: {matches}) — "
        "inference is running on CPU despite the GPU image"
    )


# ── TTS → STT round trip: functional proof for both, one utterance ───────────


@needs_auth
def test_tts_speaks_and_whisper_transcribes_roundtrip():
    spoken = requests.post(
        f"{TTS_URL}/speak",
        headers=app_headers(),
        json={"text": "Hello Jarvis, this is a test."},
        timeout=180,
    )
    assert spoken.status_code == 200, f"/speak failed: {spoken.status_code} {spoken.text[:300]}"
    assert spoken.headers.get("content-type", "").startswith("audio/"), spoken.headers
    audio = spoken.content
    assert len(audio) > 1000, f"suspiciously small wav ({len(audio)} bytes)"
    # Sanity: it's a real, non-empty wav.
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getnframes() > 0

    heard = requests.post(
        f"{WHISPER_URL}/transcribe",
        headers=app_headers(),
        params={"speaker_recognition": "false"},
        files={"file": ("roundtrip.wav", audio, "audio/wav")},
        timeout=300,
    )
    assert heard.status_code == 200, f"/transcribe failed: {heard.status_code} {heard.text[:300]}"
    text = (heard.json().get("text") or "").lower()
    assert any(word in text for word in ("jarvis", "hello", "test")), (
        f"transcript doesn't resemble the utterance: {text!r}"
    )


def test_whisper_backend_initialized_gpu_device():
    if WHISPER_BACKEND == "cpu":
        pytest.skip("lane deploys the CPU whisper image (no GPU variant selected)")
    logs = container_logs("jarvis-whisper-api")
    # whisper.cpp shares ggml with llama.cpp, so the same device-init markers
    # apply. The model loads at service startup, so markers exist pre-request.
    assert any(m in logs for m in LANE.device_markers), (
        f"whisper backend '{WHISPER_BACKEND}': none of {LANE.device_markers} "
        "in whisper logs — GPU not initialized (silent CPU fallback?)"
    )
