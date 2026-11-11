# Jarvis server → Go: rewrite plan (`jarvis-server`)

Status: **decisions settled, ready for Phase 0** (updated 2026-10-06). Nothing is implemented yet.

Supporting work:

- Appendix A: route audit
- Appendix B: prompt providers
- Appendix C: voice spike (`spikes/voice-onnx/RESULTS.md`)

## 1. Goal

Replace every Python/FastAPI server service with a **single Go binary, `jarvisd`**, built from a new monorepo, `jarvis-server`.

**Why:** the easiest possible install. Today a casual user gets:

- 15+ containers
- 11 Postgres databases
- Redis, SeaweedFS, Mosquitto, Loki and Grafana
- service discovery, app-to-app keys and tiered startup
- multi-GB Python and torch images

Target: **download one file and run it.** Raw speed is *not* the reason. Voice latency is dominated by inference that is already native code.

What "single binary" means concretely:

- `jarvisd` is one self-contained executable (about 45–60 MB) with no separate database, broker, queue or object store.
- On first run it downloads **model weights** and, where the hardware needs them, **GPU inference engines** (`llama-server`, whisper). These come in GPU-specific flavours and are hundreds of MB to GB, so they can't be in the binary.
- They live under `~/.jarvis/` and are fully managed by `jarvisd`.

**Non-goals.** These stay as they are:

| Component | Why |
|---|---|
| `jarvis-node-setup` (Pi node) | A Python client. |
| `jarvis-command-sdk` and community packages | The Python plugin contract for nodes. |
| Mobile apps, `jarvis-web` | Clients. |
| `jarvis-pantry` | A separate cloud service on Fly. |
| `jarvis-host-agent` | Runs on users' desktops. |
| `jarvis-phone-gateway` | External. It calls `/internal/phone/*`. |

**Hard constraint:** every live client contract keeps working unchanged:

- HTTP paths and JSON shapes, and auth headers
- MQTT topics and payloads
- the `/services` discovery format
- the LLM stream frames and voice PCM streams

The route audit (Appendix A) found **about 180 live command-center routes**. Those are the contract, and unused routes are not ported.

## 2. Scope by service

| Python service | Disposition |
|---|---|
| config-service | **Port.** Discovery becomes trivial: one host, legacy ports. |
| auth | **Port**, including the unmerged `feat/rs256-minting` work (RS256 minting plus `/auth/public-key`). It keeps verifying HS256 during the window. |
| logs | **Port.** Logs live in the DB with retention, plus the SSE tail. A Loki push sink is optional. |
| notifications | **Port.** Fix the retry worker that is never started. |
| recipes-server + worker | **Port**, together with OCR. |
| ocr-service + worker | **Port the orchestration.** Engines: LLM vision, `tesseract` as an optional engine, and the macOS Vision helper. Fix the broken `POST /v1/ocr` job path. |
| llm-proxy (API, model service, worker) | **Port the orchestration**, which is about 60% of the code. Inference runs in `llama-server` subprocesses, as prod already does. The REST backend is ported (OpenAI, Anthropic, Ollama, LM Studio). |
| whisper-api | **Rebuild, greenfield.** STT on whisper.cpp as an engine (see D7). Speaker ID is in-binary via sherpa-onnx. |
| tts | **Rebuild, greenfield.** Kokoro is in-binary via sherpa-onnx (`bm_george`; validated by ear on jarvis-dev). |
| command-center | **Port** the roughly 180 live routes and the voice loop. Cut lists are in §7. |
| settings-server | **Drop.** Nothing calls it. |
| mcp | **Drop.** It's a deprecated dev tool. |
| admin backend (Fastify) | **Phase 6.** Its compose and installer machinery mostly disappears. What's left either stays a thin Fastify app or moves into `jarvisd`. |

Python libraries:

- **log-client and config-client** stay because nodes use them. Their endpoints are frozen contracts.
- **auth-client and settings-client** retire.

## 3. Architecture

### 3.1 One process, legacy ports

`jarvisd` runs one in-process **module** per former service.

For compatibility it **listens on every legacy port**: 7700, 7701, 7702, 7703, 7704, 7706, 7707, 7712, 7030 and 7031. Each listener mounts only that module's routes. The services' paths collide if merged onto one port:

- `/health`, `/ping`, `/info`
- `/settings/*`
- `/api/v0/me/data`, served by both command-center and notifications
- `/api/v0/admin/*`

Multi-listen gives zero client changes. `/services` returns the same host for every name, on different ports. A unified single port is a later, optional step.

Inside the process:

- Modules talk through **Go interfaces**, not HTTP.
- App-to-app keys remain only for external callers: node-setup, phone-gateway, and a remote GPU satellite.
- An **mDNS advertiser** for `_jarvis-config._tcp` is added. Mobile already browses for it, but nothing advertises it today.

### 3.2 Storage and infrastructure, all embedded

| Today | In `jarvisd` |
|---|---|
| 11 Postgres DBs | **One SQLite file** (`~/.jarvis/jarvis.db`) in WAL mode, with one writer connection and a read pool. Tables are **prefixed per module** (`auth_users`, `cc_routines`, …) because every service has its own `settings` table. |
| Alembic ×11 | **goose** migrations, embedded and run at startup. `jarvisd migrate status` replaces "alembic current == heads". |
| Queries | **sqlc** (supports SQLite). JSON stays in TEXT columns, which matches the current convention. |
| pgvector (CC memory) | **Brute-force cosine in Go** over the household's memories. That's thousands of 384-d vectors, well under a millisecond. sqlite-vec is the fallback if it ever matters. |
| Redis + RQ | **SQLite-backed durable job queue**: a jobs table with leases, retries, priorities and dedup keys, plus an in-process worker pool. **Concurrency is capped per job type**, e.g. one background LLM job at a time, so slow hardware keeps the live path responsive. Today's `llmproxy:dedupe` and enqueue/callback semantics are preserved. Job completions become function calls. |
| SeaweedFS | A blob interface: **local filesystem** (`~/.jarvis/blobs`), with S3 optional. |
| Mosquitto | **Embedded broker** (mochi-mqtt) on 1884 and WebSocket 9883, with the same topics. It authenticates against the credentials CC issues via `/node/mqtt-credentials`. |
| Loki + Grafana | A log table with retention, plus the SSE tail. |
| phone-gateway's Redis dial queue | Optional `REDIS_URL` LPUSH compatibility shim, or move phone-gateway to HTTP. Decide in Phase 5. |
| go2rtc, ffmpeg | Optional external binaries (cameras/HLS), supervised when enabled. |

SQLite driver: `modernc.org/sqlite` (pure Go; keeps the build cgo-free, see §3.4).

### 3.3 Inference

| Capability | How | Where |
|---|---|---|
| LLM | `llama-server`, one per slot (live and background), with `--jinja`, `--mmproj` and grammar/JSON-schema. This mirrors prod today. Remote providers go through the Go REST backend. | Engine subprocess, downloaded per GPU flavour |
| Embeddings (memory) | `llama-server --embedding` with a MiniLM GGUF, or sherpa-onnx. Existing memories are re-embedded by the existing sweep worker. | Engine or in-binary |
| STT | whisper.cpp `whisper-server` on GPU. The alternative is sherpa-onnx ASR on CPU (D7). | Engine |
| Speaker ID | **sherpa-onnx**: 3D-Speaker ERes2Net or NeMo TitaNet-small. Pick and calibrate thresholds on a real enrollment set. | **In-binary** |
| TTS | **sherpa-onnx Kokoro** v1.0, `bm_george`, speed 1.25, CPU, fp32 (RTF 0.17). It streams per sentence. | **In-binary** |
| Intent classifier (fastText) | Pure-Go inference over the supervised `.bin`, verified against Python on the full corpus. Training stays an offline Python script. | In-binary |
| OCR | LLM vision via `llama-server` (`--mmproj`), `tesseract` (optional), and a macOS Swift Vision helper. | Engine |

`internal/engines` handles, for each engine:

- download and version-pin it
- set GPU environment (port of `gpu_select.py`)
- spawn it, health-check it, and restart it with backoff
- unload and reload it for GPU hand-off

### 3.4 Build and distribution: **no cgo, every OS**

Platforms: linux/amd64, linux/arm64, darwin/arm64 and **windows/amd64**, all native.

- **Windows forces the approach.** sherpa-onnx's Windows static libraries are MSVC-built, and cgo's MinGW toolchain can't link them. Only DLLs are usable.
- **So `jarvisd` uses no cgo on any platform.** It embeds the sherpa-onnx and onnxruntime shared libraries for its OS (`.so`, `.dylib` or `.dll`, about 31 MB) via `go:embed`. On first run it extracts them to `~/.jarvis/lib/<version-hash>/` and loads them at runtime with **purego** (`ebitengine/purego`), which provides dlopen/LoadLibrary and C calls from pure Go.
- **SQLite uses a pure-Go driver** (`modernc.org/sqlite`).
- **Result:**
  - all four targets cross-compile from one CI runner with `CGO_ENABLED=0`
  - each ships as a single file
  - one code path everywhere
- **One-time cost:** mirror the sherpa C-API config structs in Go, exactly matching their layout. This is guarded by a test that round-trips every config struct, and it is **Phase 0 task #1**.
- **Fallback if purego proves fragile on a platform:** static cgo on linux/darwin (already proven: a 41 MB binary) and DLLs-beside-exe on Windows.
- **Release outputs:**
  - `jarvisd-<os>-<arch>` binaries
  - a minimal container image
  - install scripts: `install.sh` for systemd/launchd, `install.ps1` for a Windows service or scheduled task
- **Windows notes:**
  - extracted DLLs may need code-signing to avoid antivirus friction; plan an Authenticode step in Phase 6
  - GPU engines (`llama-server`, whisper) have official Windows CUDA and Vulkan builds

### 3.5 Repository layout (`jarvis-server`)

```
cmd/jarvisd/            serve | migrate | import-legacy | doctor | engines
internal/platform/      httpx (router, errors, SSE, chunked), authn (JWT HS256+RS256, node, app, admin),
                        settings (definitions, cascade, cache, /settings router), db (sqlite, sqlc, goose),
                        queue, blob, mqtt (broker + req/resp), logging (slog → logs module), mdns, engines
internal/voice/         sherpa-onnx wrappers: kokoro, speaker
internal/modules/       config auth logs notifications recipes ocr llm stt tts
                        cc/{voice,toolloop,prompts,memory,smarthome,nodes,routines,errands,signals,phone,mobile,...}
third_party/sherpa/     pinned static libs per platform (fetched by script, not committed)
contract/               black-box pytest suite + fakes (§4)
fixtures/golden/        JSON fixtures exported from the Python implementation
```

## 4. Verification

| Layer | What | Notes |
|---|---|---|
| 1. Contract suite (`contract/`, pytest, black-box HTTP) | Route tests ported from in-process TestClient to real HTTP. Includes a fake LLM (OpenAI-compatible, scripted), a fake relay and a fake MQTT node. | **Each test must pass against today's Python stack first.** Then it is the oracle for Go. |
| 2. Golden fixtures | Python dumps input→output JSON. Covers: the date-key matcher (4,987 examples), date detection and resolution, the tool-call parser and malformed-JSON extractor, JSON repair, think-strip, transcript filter, param validation, recipe quantity parsing and extractors, SSRF guards, queue envelopes, SDK wire formats, and fastText predictions. | **Prompts are byte-exact:** every kept Qwen provider (Appendix B) × representative contexts. |
| 3. Existing black-box suites | install-e2e Phase 2 (behaviour corpus, using the kept ChatGPTOpenAI provider), Phase 3 (real node and MQTT K2 provisioning), the HTTP parts of Phases 1 and 1.7, and the node-setup integration suite. The GPU lane does a real chat and a TTS→STT round trip. | Docker/alembic/RQ checks get `jarvisd` equivalents. |
| 4. Shadow replay (CC voice path) | Record dev traffic and CC's LLM calls against Python CC. Replay against Go CC with the LLM fake returning the recorded completions. Diff, ignoring volatile fields. | |
| 5. Real hardware | jarvis-dev (`pi@jarvis-dev.local`) re-provisioned against `jarvisd`, with soak time per phase. | |

Go code follows TDD per RULES.md, plus `go test -race`. Coverage target: 80%.

## 5. Migration approach: strangler

- Each module runs **either** in `jarvisd` **or** as the legacy Python container. The set is chosen with `--modules=…`.
- An enabled module serves its legacy port.
- A disabled module is reached through an HTTP-client implementation of the same Go interface, pointed at the Python service.
- Each phase ships to dev, soaks, then moves on. There is no big-bang cutover.

**Strangler caveat:** while modules are split between Go (SQLite) and Python (Postgres), each side owns its own data. Modules move with their data.

**Legacy data import (wanted, not required):** `jarvisd import-legacy --from postgres://…` reads each legacy DB at alembic head and writes the module's SQLite tables.

- **Covered:** users, households, nodes and keys, app clients, settings, routines, memories (re-embedded), recipes, inbox, rooms and devices.
- **Blob files** are copied from S3/SeaweedFS.
- **Voice profiles are not imported.** Voice is greenfield, so users re-enroll.
- It has a dry-run mode, and is tested against a prod snapshot in dev.

## 6. Phases

**Done when** (applies to every phase):

- its contract tests and golden fixtures pass
- install-e2e is green with the module enabled in `jarvisd`
- it has soaked on dev

### Phase 0: groundwork

1. Create the `jarvis-server` repo. **First, prove the purego sherpa loader on linux, darwin and windows** (§3.4). Then build `platform/`, the multi-listener runner and the module interface, and set up the CI cross-compile matrix for all 4 targets.
2. Build the `contract/` harness and its fakes. Make it runnable against the Python stack in CI.
3. Write the golden-fixture exporters, which live beside the Python code.
4. Freeze the wire contracts as tests:
   - `/services` and `/info`
   - the log batch endpoints
   - `/internal/app-ping` and `/internal/validate-node`
   - LLM stream frames
   - voice PCM stream headers
   - the MQTT topic catalogue
   - the public plugin endpoints (`/node/inbox-item`, `/node/push-notification`, `/node/llm/chat`, `/callbacks`, `/signals`)
5. Write the schema baseline: translate each service's schema at alembic head into a goose SQLite migration per module.

### Phase 1: control plane

config, auth (with RS256), logs, notifications.

### Phase 2: recipes and OCR together

Both move to the embedded queue, which removes the RQ pickle coupling. Files move to the blob store.

### Phase 3: LLM

- Engine supervisor and the `llama-server` driver.
- REST backend.
- Slot state machine.
- Stream proxy with the custom frames, and cancel.
- JSON repair, the date-key extension, no-think prefill and reasoning budget.
- Embeddings.
- Queue jobs.
- Model downloads from Hugging Face.

### Phase 4: voice, greenfield

- Kokoro and speaker ID in-binary.
- STT engine (D7).
- Enrollment and verification flows behind the existing node and mobile routes.
- Threshold calibration on real enrollments from jarvis-dev.
- Affect features ported to pure Go, if still wanted.

### Phase 5: command-center

| Sub-phase | Scope |
|---|---|
| 5a | Data plane and node management. Embedded MQTT broker and request/response, replacing the temp-file result correlation. |
| 5b | Voice pipeline and tool loop: conversation handler, tool engine, parser, kept prompt providers (byte-exact), the 17 server tools, fastText, dates, media proxy, PCM streaming. |
| 5c | Background workers and subsystems: memory, signals and proposals, errands and workflows, schedules, phone, deep research and quick search, cameras. |
| 5d | Mobile surface, including SSE chat. |

### Phase 6: packaging and install

- Release binaries and image, plus the install script.
- `import-legacy`.
- Re-provision jarvis-dev and then the prod nodes.
- Shrink or absorb jarvis-admin. Update the `./jarvis` CLI and jarvis-installer.
- Remote-GPU-satellite mode: a `jarvisd` instance with only `llm,stt` enabled.

### Phase 7: retire

Archive the Python service repos. Rewrite CLAUDE.md files and jarvis-docs.

## 7. Cut lists (not ported)

- **LoRA and adapters, everywhere:**
  - CC's adapter pipeline and its 9 routes
  - llm-proxy adapter cache, storage and training
  - the node-setup `train_node_adapter` script
  - node-mobile's three adapter screens (a client change)
- **About 27 CC routes with no caller** (Appendix A), plus the 4 job callbacks, which become in-process.
- **Prompt providers:** everything except the Qwen 3.x set and the test-only ChatGPTOpenAI (Appendix B). Community provider install (`exec()` of cloned Python) is dropped; the mechanism gets redesigned after the rewrite.
- **llm-proxy:** the TRANSFORMERS, vLLM and MLX in-process backends (vLLM and MLX remain reachable as OpenAI-compatible remote endpoints), unused `swap_*`, legacy `cache/`, and the WIP pipeline routes. Training and conversion scripts stay as offline Python tooling, outside the server.
- **OCR:** EasyOCR, PaddleOCR, rapidocr (revisit if LLM vision plus tesseract recall falls short), and the dead async-validation modules.
- **TTS:** `/generate-wake-response` (deprecated) and Piper. sherpa can run Piper/VITS models later if a low-end voice is needed.
- **Whisper:** resemblyzer, the ECAPA/torch stack and librosa.
- **Services:** settings-server, jarvis-mcp.

## 8. Risks

1. **CC size and undocumented behaviour.** Mitigations: sub-phases, byte-exact prompts, shadow replay and the behaviour corpus.
2. **FastAPI/Pydantic implicit semantics:** null vs missing, coercion, the 422 shape. These are captured by the contract suite and matched deliberately in `httpx`.
3. **SQLite under concurrent load.** The design uses one writer and the queue in the same DB. Mitigation: a load test in Phase 0 with voice traffic plus background jobs on Pi-class and mini-PC hardware.
4. **purego native loading.** C struct layouts must match the C headers exactly on every OS; this is proven first in Phase 0. The fallback is static cgo plus Windows DLLs.
5. **Engine parity:** `llama-server` tool calls and JSON schema versus llama-cpp-python. This is low risk because prod already runs `llama-server` via the REST backend.
6. **Single-process blast radius.** Mitigations: recover() per request and per job, engines out of process, and a watchdog restart via systemd/launchd.
7. **Legacy import correctness.** Mitigations: dry run, a prod-snapshot rehearsal, and Postgres left untouched until the user confirms.

## 9. Decisions

**Settled (2026-10-06):**

- **Language:** Go.
- **Distribution:** a single binary on linux, macOS **and Windows**, with no cgo (purego plus embedded native libraries).
- **Repo:** `jarvis-server`, public, AGPL-3.0 like the rest of Jarvis.
- **Database:** SQLite, with legacy import wanted but not required.
- **Queue:** embedded durable queue; Redis not required.
- **Voice:** greenfield. sherpa-onnx statically linked, Kokoro `bm_george`, ERes2Net or TitaNet for speaker ID.
- **Cuts:** LoRA cut; the prompt-provider keep list; settings-server and mcp dropped; Pantry out of scope.

**Still open, decided at the start of the relevant phase:**

- **D5 (Phase 1):** confirm Go auth ships RS256 minting from day one. Recommended: yes.
- **D7 (Phase 4):** STT engine. Options are whisper.cpp on GPU (today's quality, needs an engine download), or sherpa-onnx ASR on CPU in-binary (e.g. Parakeet or Whisper ONNX; simpler, needs a latency and accuracy check).
- **D8 (Phase 5):** phone-gateway dial queue. Options are a Redis shim, or switching phone-gateway to HTTP.
- **D9 (Phase 6):** whether jarvis-admin stays as a Fastify app or is absorbed into `jarvisd`.

## Appendix A: command-center route audit (2026-10-06)

**Method.**
- The route list comes from CC's OpenAPI schema plus one hidden route: 220 method+path pairs. The `/settings/*` mount is excluded because it is a shared contract.
- Every route was cross-referenced against non-test source in:
  - node-setup, node-mobile, recipes-mobile, web, admin, command-sdk, install-e2e and scripts;
  - every other service repo;
  - all 30 `jarvis-cmd-*` / `jarvis-device-*` package repos, the `jarvis-command-*` repos, phone-gateway, relay, osx-api, pantry-web/runner, home-assistant-integration, integration-tests, and the `jarvis-pp-*` prompt providers.
- Matching handles f-strings, template literals and `base()` helpers.
- Every route without a match, and every suspicious match, was checked by hand.

**Result: about 180 routes are live. About 40 can be cut.**

### Unused: no caller anywhere (27)
- **Admin cache:** `GET /admin/cache/stats`, `POST /admin/cache/clear`, `DELETE /admin/cache/{conversation_id}`
- **Smart home:** `GET /households/{hh}/rooms/tree`, `POST /households/{hh}/devices/assign-rooms`, `GET /node/devices/{entity_id}`
- **Attention:** `POST /attention/events`, `GET /attention/journal`
- **Characterizations:** `GET /characterizations`, `POST /characterizations/synthesize`
- **Prompt providers:** `GET /prompt-providers`, `DELETE /prompt-providers/{name}`. Install and poll are used by mobile.
- **Media voice profiles:** `GET /media/whisper/voice-profiles`, `DELETE /media/whisper/voice-profiles/{user_id}`
- **Node-plane memories:** `GET|POST /memories`, `GET|PUT|DELETE /memories/{id}`. Only `/memories/inject` and the `/mobile/memories*` routes are used.
- **Traces:** `GET /mobile/traces/{conversation_id}`
- **Chat and misc:** `POST /lightweight/chat`, `POST /test/command` (only jarvis-mcp, which is being dropped), `GET /api/v0/ping`
- **Errands:** `POST /errands`, `POST /routines/run-background`. Errands run through server tools, not these routes.
- **Factory reset:** `POST /admin/nodes/{id}/factory-reset`. Mobile's delete goes through `DELETE /admin/nodes/{id}`.

### LoRA/adapters: cut by decision (9)
- **Routes:** `GET /admin/adapter/{hh}`, `/history`, `POST …/rollback`, `POST /adapters/train`, `POST /adapters/jobs/callback`, `GET /adapters/proposals/{id}`, `POST …/apply`, `POST …/dismiss`, `POST /adapters/deployments/{hash}/revert`
- **Knock-on removals:**
  - node-mobile has three screens that use the proposal and deploy routes: `AdapterProposalScreen`, `AdapterProposalDetailScreen`, `AdapterDeployedScreen`.
  - node-setup has `train_node_adapter` and `scripts/train_node_adapter.py`.

### Callbacks that become in-process (4)
`/memory-extraction/callback`, `/deep-research/callback`, `/situation-matcher/callback` and `/characterization-synthesis/callback` exist only so llm-proxy's queue worker can call back into CC. Inside one process, a job completion is a function call, so these stop being routes.

### Live but with a single, narrow caller (keep, but worth knowing)
- `POST /tool-router/train`: only `scripts/train_tool_router.py` calls it (fastText training).
- `GET /oauth/callback`: browser redirect target for the OAuth bounce.
- `/internal/phone/*`: jarvis-phone-gateway only.
- `POST /api/v0/chat`: node `chat_text()` (jokes, what's up, routines).
- `POST /voice/command` and `POST /voice/command/continue` (non-stream): **core node contract**, not just install-e2e Phase 2. Every node follow-up turn uses blocking `/voice/command` (`follow_up_loop.py:342`), and `/continue` is the node's fallback and clarification path. Corrected 2026-10-06 by spec doc 01.
- `GET|POST /households/{hh}/rooms`: also called by jarvis-home-assistant-integration.
- `POST /node/inbox-item`, `/node/push-notification`, `/node/llm/chat`, `/callbacks`, `/signals`: also called directly by community packages (sports, entertainment-knowledge, news, messages) and the SDK. These are **public plugin API** and must stay stable.

## Appendix B: prompt providers (decided 2026-10-06)

Prod state, read on 2026-10-06 from `jarvis@10.0.0.107`:

- `llm.interface = Qwen3_14B_Compressed`.
- Both the live and the background slot run `Qwen3.8-27B-UD-Q4_K_M.gguf` through llm-proxy's **REST backend**, pointing at `llama-server` sidecars (`llama-server:8080` and `llama-server-bg:8080`).
- Prod therefore already uses the engine-subprocess pattern from §3.3.

Dev is set to `Qwen3_8B_Compressed`.

**Decision.** Port only the current Qwen 3.x providers, plus `shared/`, and drop the rest. The provider mechanism will be redesigned after the rewrite.

| Port | Drop |
|---|---|
| `large/untrained/qwen3_14b_compressed.py` (prod) | Gemma 2/3/4 providers |
| `medium/untrained/qwen3_8b_compressed.py` (dev) | Llama (3.1/3.3, small, generated variants) |
| `medium/untrained/qwen3_5_9b_compressed.py` | Mistral, Ministral |
| `shared/` (`core_rules`, `context_builders`, `tool_formatters`, `command_converters`) | Hermes |
| `ChatGPTOpenAI`, test-only (confirmed). Used by the install-e2e behaviour suite, which runs on gpt-4.1-nano. | Qwen 2.5 (3B, 7B, 14B, 32B, compressed and untrained) |
| | `qwen3_large_untrained` |

Community prompt-provider install (`/prompt-providers/install`, which `exec()`s Python cloned from GitHub; e.g. `jarvis-pp-hermes`, `jarvis-pp-mistral`) is **dropped** with the old mechanism.

## Appendix C: voice spike (2026-10-06)

Full write-up: `spikes/voice-onnx/RESULTS.md`.

- **Speaker ID** (LibriSpeech, 40 speakers, 3-clip enrollment). Equal error rate at 3 s and 1.5 s clips:

  | Model | 3 s EER | 1.5 s EER |
  |---|---|---|
  | ERes2Net from Go | 1.25% | 1.46% |
  | TitaNet-small from Go | 1.88% | 1.70% |
  | Today's SpeechBrain ECAPA | 1.45% | 1.66% |

  On jarvis-dev's mic, the user's clips scored 0.46–0.72 against each other and at most 0.27 against impostors.
- **Kokoro** (`bm_george`, speed 1.25):
  - Whisper transcripts match the Python output on 10 of 10 test sentences.
  - Voice similarity to the Python output is 0.89–0.95.
  - RTF is 0.17 on CPU.
  - The user listened on jarvis-dev and said it was "basically exactly the same".
- **Static build:** sherpa-onnx v1.13.8 static libraries link into a 41 MB Go binary that needs only libc and libstdc++. Results are identical.
