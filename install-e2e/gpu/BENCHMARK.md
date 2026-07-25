# Voice-command model benchmark

Sweeps a set of local GGUF models through command-center's **real
`/voice/command` path** against a canned corpus of voice utterances, scoring
each model on two axes:

- **Accuracy** — does the model route each utterance to the correct built-in
  tool with sensible arguments, and does it correctly *decline* to fire a tool
  on small talk (false-positive rate on negatives).
- **Speed** — end-to-end `/voice/command` wall-clock latency (p50/p95), i.e. the
  latency the product actually delivers, plus per-model load time.

It is developed/run locally against the dev GPU box and is designed to ship into
the `install-e2e-gpu` lane (rented Vast GPU) as a nightly artifact.

## Why the CC path (not raw native tool-calling)

Local GGUF models do **not** reliably emit structured `tool_calls` under a plain
chat template — llama.cpp native function-calling is slow (15–30 s) and flaky.
That is exactly why command-center embeds the tools into the **system prompt**
per a family-specific **prompt provider** and parses the model's
`<tool_call>{…}</tool_call>` output back out. Benchmarking that path measures
the accuracy **and** latency the product actually delivers. Each model is paired
with its family-appropriate provider (the `cc_provider` field in the manifest).

The benchmark is a matrix of **(weights × provider)**: CC always asks llm-proxy
for `model="live"`, so the physical model is chosen on the llm-proxy side
(`model.live.name`) while the prompt/parse strategy is chosen on the CC side
(`llm.interface`).

## Files

| File | Role |
|---|---|
| `bench_models.py` | Manifest: the `(weights × provider)` pairs to sweep + per-model chat_format / stop_tokens / context_window. Single source of truth. |
| `benchmark_models.py` | Driver: swap → provider flip → warmup → timed corpus → score → emit → restore. |
| `bench_corpus.cc.yaml` | Expanded corpus, ~10 utterances/category (80 total). Superset of `../behavior/corpus.cc.yaml` (the 29-entry regression gate, left untouched). |
| `../behavior/tools.cc.yaml` | The real CC built-in tool schemas (shared with the behavior lane). |

## How a model swap works

Per model, the driver:

1. writes `model.live.{name,backend,chat_format,stop_tokens,context_window}` on
   llm-proxy (app-auth `PUT /settings/*`). `model.background.name` is blanked
   once at start so background **follows live** → a single shared load (critical
   on a 12 GB card — pinning background to a different model double-loads and
   OOMs).
2. restarts the `llm-proxy-model` container to reload the new weights (no
   internal token needed; mirrors what CI does).
3. polls `:7704/health` until `status == "healthy"` (the live slot is loaded).
4. flips CC `llm.interface` to the model's prompt provider (superuser JWT
   `PUT /settings/llm.interface` + `/settings/invalidate-cache`).

Originals (llm-proxy `model.live.*` / `model.background.name` and CC
`llm.interface`) are captured up front and restored at the end (also on Ctrl-C),
so the box is left as found.

## Auth

- **llm-proxy settings** — app-to-app creds, read once from the `llm-proxy-api`
  container env (never inlined).
- **CC `llm.interface`** — a superuser JWT. On a fresh stack (CI) `/auth/setup`
  mints the first superuser; on an existing stack the driver registers a bench
  user and promotes it via the auth admin token, then logs in.
- **`/voice/command`** — a fresh node registered via CC's admin key each run.

## Running it (dev)

```bash
cd install-e2e/gpu
python3 benchmark_models.py                      # all present models, full corpus
python3 benchmark_models.py --models qwen3-8b,llama31-8b
python3 benchmark_models.py --limit 6            # quick smoke (first 6 utterances)
python3 benchmark_models.py --corpus ../behavior/corpus.cc.yaml   # use the 29-entry gate
python3 benchmark_models.py --out results/bench.json
```

Env (all default to the dev box):

| Var | Default |
|---|---|
| `LLM_PROXY_URL` | `http://10.0.0.122:7704` |
| `LLM_PROXY_SSH` | `alex@10.0.0.122` |
| `MODEL_CONTAINER` / `API_CONTAINER` | `llm-proxy-model` / `llm-proxy-api` |
| `CC_URL` / `AUTH_URL` | `http://localhost:7703` / `:7701` |
| `ADMIN_API_KEY` / `AUTH_ADMIN_TOKEN` | read from the CC / auth containers if unset |
| `HEALTH_TIMEOUT_S` | `420` (a model that never loads — e.g. VRAM OOM — is skipped, not fatal) |

## Output

`results/*.json` per model: `tool_accuracy`, `arg_accuracy`, `exact_match`,
`false_positive_rate`, `negative_accuracy`, `overall_accuracy`, per-category
breakdown, `latency_ms` (p50/p95/mean/min/max), `load_time_s`, and the full
`per_utterance` detail. A markdown summary table is printed and appended to
`$GITHUB_STEP_SUMMARY` when set.

## Hardware notes (dev box: RTX 3080 Ti, 12 GB)

- Models run **sequentially** (one resident at a time); the swap unloads the
  previous via a model-service restart.
- Gemma-2-9B's KV cache is large; at 8192 ctx it OOMs `llama_context` once
  whisper/tts hold ~3.8 GB. It runs at 4096 ctx (corpus prompts are < 2 K
  tokens). The rented CI GPU (24 GB) has no such constraint.

## Shipping to CI (install-e2e-gpu)

The `install-e2e-gpu` lane rents a 24 GB Vast GPU (RTX 4090 / 3090) and runs the
benchmark **weekly** (the Sunday nightly, gated by day-of-week) or on a manual
`workflow_dispatch` with `run_benchmark=true` — cuda lane only. Steps (after
Phase G, before teardown): download the `BENCH_MODELS` GGUFs onto the VM
(`bench_models.py --downloads`), run this driver, upload `gpu-<lane>-benchmark.json`
as an artifact, and — on the weekly run — regenerate the README table
(`update_readme.py`) and commit it.

The same driver runs unchanged; only the environment differs (everything is on
the VM, reached via `DOCKER_HOST=ssh://gpu-vm` + SSH tunnels):

| Var | CI value | Why it differs from dev |
|---|---|---|
| `LLM_PROXY_URL` | `http://localhost:7704` | tunnelled to the VM |
| `LLM_PROXY_SSH` | `gpu-vm` | the rented VM's ssh alias |
| `MODEL_CONTAINER` / `API_CONTAINER` | `jarvis-llm-proxy-api` | one container supervises the model service (no separate `llm-proxy-model`) |
| `CC_CONTAINER` | `jarvis-command-center` | compose service name on the VM |
| `AUTH_CONTAINER` | `jarvis-auth` | compose service name on the VM |
| `CC_URL` / `AUTH_URL` | `http://localhost:7703` / `:7701` | tunnelled |

No `--free-vram` on the 24 GB GPU. **Dependency:** the CC image the lane installs
must already contain the `Mistral7bMediumUntrained` / `HermesMediumUntrained`
providers and the Gemma-2 parse fix — ship the command-center change first, then
validate with a manual `run_benchmark=true` dispatch before trusting the weekly
schedule.
