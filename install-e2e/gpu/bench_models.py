"""Model manifest for the voice-command tool-routing benchmark.

Single source of truth for which (weights x prompt-provider) pairs the benchmark
sweeps. Each entry couples:

  * the GGUF the llm-proxy model service loads into the `live` slot
    (``gguf_path`` is relative to ``.models`` on the inference host), plus its
    llama.cpp ``chat_format`` / ``stop_tokens`` / ``context_window``; and
  * the command-center prompt provider (``cc_provider`` == the ``llm.interface``
    setting value) that shapes the system prompt + parses the model's tool-call
    output.

The benchmark is fundamentally a matrix of (weights x provider): CC always asks
llm-proxy for ``model="live"``, so the physical model is chosen on the llm-proxy
side (``model.live.name``) while the prompt/parse strategy is chosen on the CC
side (``llm.interface``). Pairing each model with its family-appropriate provider
measures the tool-routing accuracy + latency the product actually delivers for
that model — not a raw native-tool-calling path (which local GGUFs do poorly).

Ordering note: benchmark cheapest/smallest first so a partial run still yields a
useful slice, and so the biggest VRAM consumers run last.

Gemma-2-9B was dropped from the sweep (2026-08-23). llama-cpp-python on the dev
box cannot load gemma-2 at all -- it fails in llama_load_model_from_file,
independently of VRAM. The publish guard added in da53038 requires EVERY
BENCH_MODELS entry to produce a result, so one permanently unloadable model
stops the nightly from ever publishing its table. Re-add it only once the
loader can load gemma-2; the custom "gemma2" chat format it needs still lives
in jarvis-llm-proxy-api/backends/chat_formats.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchModel:
    """One (weights x prompt-provider) benchmark subject."""

    key: str  # short stable id used in CLI filters + result JSON
    display: str  # human-readable label for tables
    family: str  # qwen / llama / mistral / hermes
    gguf_path: str  # relative to .models on the inference host
    chat_format: str  # llama-cpp-python chat_format (base template, not FC)
    stop_tokens: str  # comma-joined stop-token string for model.live.stop_tokens
    cc_provider: str  # command-center llm.interface value (prompt provider name)
    context_window: int = 8192  # uniform; corpus prompts are short, keeps VRAM/KV small
    backend: str = "GGUF"
    # Approx. download URL for the CI lane's bootstrap (host already has these
    # locally; the GPU CI VM fetches them). Kept here so lanes.py / bootstrap can
    # derive the fetch list from the same manifest.
    url: str = ""


BENCH_MODELS: list[BenchModel] = [
    BenchModel(
        key="qwen3-4b",
        display="Qwen3-4B (Q4_K_M)",
        family="qwen",
        gguf_path=".models/qwen3-4b-gguf/Qwen3-4B-Q4_K_M.gguf",
        chat_format="chatml",
        stop_tokens="<|im_end|>",
        cc_provider="Qwen3_8B_Compressed",
        url="https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf",
    ),
    BenchModel(
        key="mistral-7b",
        display="Mistral-7B-Instruct-v0.3 (Q4_K_M)",
        family="mistral",
        gguf_path=".models/mistral-7b-gguf/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        # chatml, NOT mistral-instruct: the tools ride in the SYSTEM prompt and
        # mistral-instruct drops system messages (per the Mistral provider).
        chat_format="chatml",
        stop_tokens="</s>",
        cc_provider="Mistral7bMediumUntrained",
        url="https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
    ),
    BenchModel(
        key="llama31-8b",
        display="Llama-3.1-8B-Instruct (Q4_K_M)",
        family="llama",
        gguf_path=".models/llama31-8b-gguf/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        chat_format="llama-3",
        stop_tokens="<|eot_id|>",
        cc_provider="Llama31MediumUntrained",
        url="https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    ),
    BenchModel(
        key="hermes3-8b",
        display="Hermes-3-Llama-3.1-8B (Q4_K_M)",
        family="hermes",
        gguf_path=".models/hermes3-8b-gguf/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf",
        chat_format="chatml",
        stop_tokens="<|im_end|>",
        cc_provider="HermesMediumUntrained",
        url="https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF/resolve/main/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf",
    ),
    BenchModel(
        key="qwen3-8b",
        display="Qwen3-8B (Q4_K_M)",
        family="qwen",
        gguf_path=".models/qwen8b-q4/Qwen3-8B-Q4_K_M.gguf",
        chat_format="chatml",
        stop_tokens="<|im_end|>",
        cc_provider="Qwen3_8B_Compressed",
        url="https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf",
    ),
]


def by_key(key: str) -> BenchModel | None:
    for m in BENCH_MODELS:
        if m.key == key:
            return m
    return None


if __name__ == "__main__":
    # `python bench_models.py --downloads` emits "relpath<TAB>url" per model with
    # a URL — the CI bootstrap fetches these onto the VM (relpath is under the
    # .models/ mount, i.e. gguf_path with the leading ".models/" stripped).
    import sys

    if "--downloads" in sys.argv:
        for _m in BENCH_MODELS:
            if _m.url:
                sys.stdout.write(f"{_m.gguf_path.split('.models/', 1)[-1]}\t{_m.url}\n")
