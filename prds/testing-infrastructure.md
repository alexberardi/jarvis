# PRD: Testing Infrastructure for the Agentic Dev Loop

**Status**: Draft — architecture locked 2026-06-20. Ready to implement Phase 1. Supersedes the ad-hoc notes in `openclaw.local:~/we-are-in-the-lucky-brook.md` (the original QA-execution-layer plan) and folds them into a single source of truth.

---

## TL;DR

We are building the testing infrastructure that makes a green CI check a *trustworthy* signal — across repo seams, for real feature behavior — so that bulk-merging to `main` and (eventually) an unattended ticket→code→QA→merge loop become safe. Testing is the deliberate **first** investment: it pays off whether or not the autonomous loop is ever re-enabled.

The verified good news: the "full stack in a GitHub runner" **already exists** (`jarvis-node-setup/docker-compose.ci.yaml`). The work is making CI honest, adding a real *behavior* lane (a cheap cloud model deciding tool routing), and extending the harness across the ecosystem — then migrating it into a dedicated `jarvis-integration-tests` repo.

---

## Why now — the postmortem

An agentic dev loop was built mid-May 2026 on `openclaw.local` (a Pi 5 running the OpenClaw framework, models routed through the local `claude` CLI on the Claude Max subscription = ~$0 marginal). It drove GitHub issues in the private `alexberardi/jarvis-roadmap` repo via sentinel comments: `product → engineering breakdown → qa test plan → coding-agent draft PR → qa-executor`. On **2026-05-19 the three core dev-loop agents (engineering, qa, coding-agent) were removed** and the loop paused.

It was paused for two reasons that share **one root cause**:

1. **"PRs were isolated to a single repo; things got out of sync."**
2. **"Churning tokens without accomplishing much — looping on designs, then 'split this into a separate task,' until 2–3 issues became 30."**

Root cause: **the atomic unit of work was a single-repo PR, but real Jarvis features are cross-repo.** The coding-agent was hard-coded to *abort* on cross-repo work and triage had a "split into N child tickets" path, so a coherent feature mechanically fragmented into ordering-dependent per-repo tickets (the drift) and recursive splitting (the explosion). The integration-runner's `linked_prs` map (`{repo: branch}`) was reaching toward coordinated cross-repo PRs but the coding-agent never used it.

And underneath *that*: **the tests couldn't be trusted enough to merge on.** The original plan's own words: "nothing actually executes the QA plan's cross-service cases against the branch," so a PR goes green on per-service CI while the feature is unverified. You can't automate on top of validation you don't trust. **Pausing was correct.** This PRD fixes the foundation first.

---

## Current state (verified 2026-06-20)

### CI today is hollow — a green check means almost nothing

- **command-center runs 3 of its 185 test files in CI**, and the 2 substantive ones are wrapped in `|| echo "may fail without full deps"` so they *cannot fail the build*. The brain service's PR gate is effectively a settings smoke check.
- **llm-proxy's CI ignores its own `test_chat_completions.py` and `test_embedding_routes.py`** — the OpenAI-compatible contracts command-center depends on for every voice command and memory search are never asserted on a PR.
- **Every hot-path service mocks its single most consequential boundary**: CC mocks the LLM and the tool classifier; whisper mocks the transcription Model; TTS mocks Piper with *silent audio*. Tests prove the wiring is shaped right, never that the model/engine produces correct output.
- **All 11 `jarvis-device-*` and all 16 `jarvis-cmd-*` repos have zero CI.** `cmd-email` has 20 tests that never run anywhere. 4 device repos have neither tests nor CI.
- **`jarvis-command-sdk` has no CI at all** — the foundation every package imports — and there is *no test* for the `Alert.to_dict/is_expired` bug that already shipped to prod.
- Even the `./jarvis` CLI's own `jarvis test jarvis-command-center` runs a curated ~22-file subset, so the partial-test pattern is baked into the tooling, not just CI.

### What genuinely works (the backbone)

- **auth and config-service** enforce real `--cov-fail-under=80` gates, full suites, no per-file ignores.
- The **integration-runner's CASE tests are real**: live `jarvis-auth` + `config-service` + Postgres + Mosquitto, real app/node credential round-trips (CASE-201/202 — the actual fix for the node-403 class), real CC tool-call parsing against a wire-faithful fake LLM, and real MQTT publishes for high-blast-radius paths (settings, factory reset, package install — CASE-212/214/215). It's a legitimate cross-service harness; it's just only wired for 3 services and the LLM/STT/TTS are faked.

### The paused loop (context, not built here)

The OpenClaw agent org, sentinel protocol, `jarvis-webhook-receiver` (Cloudflare Tunnel → `openclaw.jarvisautomation.dev/webhook`), and the `jarvis-roadmap` issue database still exist. Reviving the loop is **out of scope for this PRD** — but every testing decision here is made so the loop *can* be safely re-enabled later on a feature-grained, integration-validated unit of work.

---

## Goals & non-goals

**Goals**
- A green CI check means the unit suite actually passed (no swallowing, no 3-of-185).
- Cross-service *feature* validation, not just per-repo unit wiring.
- A **behavior** signal: catch the wrong-tool / "answers the literal question" class automatically.
- Reproducible, ephemeral, cheap (free fast lane; pennies for the behavior lane).
- A bulk-testable `main` on mobile.

**Non-goals (for this PRD)**
- Re-enabling the autonomous coding loop (separate effort, gated on this one).
- A self-hosted GPU runner / real *local*-model quality regression (deferred; the cloud model covers behavior).
- Replacing GitHub Issues as the ticket store.

---

## Committed architecture

### Runner: GitHub-hosted `ubuntu-latest`

The trimmed stack is ~1.5–3 GB RAM, far inside ubuntu-latest's ~16 GB / ~14 GB disk. The only reason full-stack-in-a-runner was ever hard is the GPU services (llm-proxy/whisper/tts) — and we remove that blocker (below). **The Pi 5 is a documented fallback only**, not built: it's ARM (llm-proxy is CUDA/amd64-only, though faked), 8 GB shared with the OpenClaw gateway, and persistent-runner state leaks; ephemeral ubuntu-latest avoids all of it. All hot-path service `:dev` images except llm-proxy are already multi-arch (amd64+arm64), so the Pi remains viable if a concrete need ever arises.

### The stack: the existing `docker-compose.ci.yaml` (5 containers + 3 fakes)

The minimal voice round-trip (node → CC → LLM → tool → TTS):

- **Containers (5):** one Postgres (pgvector pg15, hosting `jarvis_command_center` + `jarvis_auth` + `jarvis_config` via `compose/postgres-init.sh`), one Mosquitto, `jarvis-auth`, `jarvis-config-service`, `jarvis-command-center`.
- **Host-process fakes (3):** `fake_llm:7705`, `fake_whisper:7706`, `fake_tts:7707`, reached via `host.docker.internal`.
- **The node is the pytest client** — it drives CC's HTTP API with seeded `X-API-Key` node creds. node-setup is encrypted SQLite (sqlcipher), needs no container.
- **Not on the voice path:** Redis (async enqueue only), MinIO, Loki/Grafana, ocr, recipes, pantry, web, notifications. Added only when a test specifically needs them.

Data layer confirmed: CC / auth / config / whisper / tts / notifications = Postgres; node-setup = SQLite.

### Two lanes — the key move

| Lane | Trigger | LLM/STT/TTS | What it proves | Cost |
|---|---|---|---|---|
| **Fast** | every PR (hot-path repos) | host fakes (canned) | wiring + contracts: auth round-trips, service discovery, MQTT, CC tool-call parsing | free, ~3–4 min |
| **Behavior** | nightly + on-demand | **llm-proxy `REST` backend → cheap cloud model (gpt-4.1-nano class)** + the `ChatGPTOpenAI` prompt provider; whisper/tts stay faked | *does the feature actually work* — a voice-command corpus asserts utterances route to the correct tools | pennies / run |

The fast lane gates PRs. The behavior lane is the capability that never existed: a genuinely capable model making the tool-routing decision, run for cents, catching behavior (not just wiring) regressions without a human listening to a device. **No GPU runner required** — that's why pointing llm-proxy's `REST` backend at a cloud model is sharper than self-hosting a model.

### The `./jarvis` CLI's role

The 3,287-line CLI already encodes the service/DB registry, `init` (tokens → `~/.jarvis/tokens.env` + `.env` + app-cred auto-register to config-service + migrations), and dependency-ordered `start --all`. Its role here:

- **Source of truth for the service/DB registry** and the seeding semantics.
- **Local reproduction tool** — a developer reproduces a CI failure with `jarvis init && jarvis start ...` (on Linux it's all-Docker; the macOS-only override that runs llm-proxy/ocr locally doesn't apply).

**`compose.ci` stays canonical for CI** (deterministic, wizard-free, ephemeral, already proven). We keep the two consistent (same service list, same `seed.sh` path). Making the CLI itself the literal CI driver is possible but fights its interactive/mixed-mode grain for no gain — *open to revisit if preferred*.

### The ChatGPT prompt provider (enables the behavior lane)

CC's prompt providers are `IJarvisPromptProvider` subclasses, discovered by `PromptProviderFactory` (pkgutil-walks `app/core/prompt_providers/` + `prompt_providers_custom/`, matched on `.name`), selected **solely** by the DB setting `llm.interface` (default `Qwen25MediumUntrained`, `requires_reload=True`). There is **no provider↔model coupling**: CC always sends `model='live'` (`llm_proxy_client.py:57`); which model runs is entirely llm-proxy-side.

**Plan:** add a built-in `ChatGPTOpenAI` provider at `app/core/prompt_providers/large/untrained/chatgpt_openai.py`:
- `name -> 'ChatGPTOpenAI'`
- `build_system_prompt(node_context, timezone, tools, available_commands)` — concise OpenAI-style prompt; reuse `build_context_header`.
- `supports_native_tools -> True` (the natural fit for a real OpenAI-compatible model: tools via the `tools` param + `tool_choice='auto'`, structured `tool_calls`).
- `build_tools(...)` returning clean OpenAI function defs.

Activate by setting `llm.interface='ChatGPTOpenAI'` and pointing llm-proxy's `live` backend at the cloud model. Tests force it via `PromptProviderFactory.create_provider('ChatGPTOpenAI')` (unit) or `ModelService(model_name='ChatGPTOpenAI')` / the DB setting (end-to-end).

> **KEY RISK — native tool-calling path is untested.** Every existing provider is `supports_native_tools=False` (they parse text `<tool_call>` tags). CC's native path (`tool_choice='auto'`, structured `tool_calls`, different warmup at `conversation_handler.py:382-397`, `max_iters=10`) has **never been exercised end-to-end**. The ChatGPT provider is the first to do so — treat it as a small sub-project (shake out native `tool_calls` handling + warmup against the cloud endpoint), not a drop-in. Also: llm-proxy must actually route the `live` alias to the OpenAI `REST` backend; coordinate the `llm.interface` flip with llm-proxy's live-model config (and the `requires_reload` restart).

### Seeding

`compose/seed.sh` already performs the two-phase bring-up that mints the CC app-key **and** the node-key (both an auth row *and* a CC-local `nodes` row are required for `X-API-Key` node auth). Extend it to also set `llm.interface='ChatGPTOpenAI'` and point llm-proxy's live backend at REST→cloud for the behavior lane.

---

## Locked decisions

1. **Tests live in a new `jarvis-integration-tests` repo** — migrate the harness out of node-setup (it's the Pi runtime, an odd owner for ecosystem-wide tests).
2. **Behavior tests use a cheap cloud model via llm-proxy's `REST` backend** (gpt-4.1-nano class) — *not* a self-hosted GPU runner.
3. **Mobile dev-mode tracks `main` via hosted EAS Update (`main` channel).**
4. **Runner = GitHub-hosted `ubuntu-latest`**; Pi 5 fallback documented, not built.

---

## Phased plan

> **STATUS (2026-06-22):** Phase 1 done (T1/T2/T3/T5 merged; T4 deprioritized). Phase 2: T7+T8 merged; **behavior lane hardened + LIVE in CI** — corpus 10→29 utterances with **argument-shape assertions** + pinned `gpt-4.1-nano-2025-04-14`, externalized to provider-agnostic YAML (PR #5), and a **nightly + on-demand CI job** (PR #6). The `OPENAI_API_KEY` secret is set on BOTH llm-proxy AND jarvis-integration-tests; the CC-real-provider behavior corpus now runs green in CI. **T6a done (incl. fast-lane cutover)**, **T6b MERGED**. **Corpus stability pass (2026-06-21):** the visible red behavior-corpus runs on integration-tests `main` were **stale** (pre-#2 `control_device` errors + the pre-#3 `get_current_time` misroute, never re-run after those fixes merged); re-validated current main with **3 consecutive independent full-stack runs GREEN, 30/30 each (90/90 routings)** — the lane is stable. **T9 DONE + cutover validated end-to-end** (#4 + #5; all 3 from-source lanes GREEN in CI; triggers merged on the 3 service repos #8/#4/#5; both secrets set; a throwaway tts PR proved trigger→dispatch→build→CASE-311→comment-back live). **All T-tickets DONE (2026-06-22):** **T10** merged (integration-tests #6 `f18fa52`) + validated GREEN in CI (run `27967408363`); the **T6a fast-lane cutover** finished in the same session (CC `integration-trigger` retargeted node-setup→integration-tests, validated 22/22 with CC built from source; node-setup runner retirement = node-setup #36). The CASE-catalog generator is **MERGED** too (PR #8/#9; catalog now **38 cases**, drift-check clean), with new negative-auth CASEs landed (CC CASE-216..223 in #7/#11, llm-proxy CASE-303/304 in #10). **Phase 0 testing-infrastructure is COMPLETE.** The only remaining loop-deployment gate is now the SHARED-SPEC §15 prereqs **#2-#4** (verify github-rw MCP comment-read method name; optional Slack→GitHub relay; Pi mechanics) — all **Alex-gated**. Full scorecard in `agentic-workflow-overview.md` → Progress.

### Phase 1 — Make CI honest + pin known bugs (no stack required; do first)

- **T1 ✅ MERGED · command-center CI runs the full suite and gates** (`jarvis-command-center` PR #13). Replaced the 3-file allowlist + `|| echo` swallowing with the full suite vs a `pgvector/pgvector:pg15` service + `pip install -e ".[dev]"`. Surfaced **21 hidden problems, ALL stale-test/test-fragility, zero app bugs** (prompt redesign, auth admin-key→JWT migration, manager_name default, 4-col unique constraint, a pytest≥9.1 monkeypatch break). CI env needs `JARVIS_AUTH_BASE_URL` + `JARVIS_AUTH_SECRET_KEY` placeholders. Full suite: 1283 passed.
- **T2 ✅ MERGED · Un-ignore llm-proxy's chat + embeddings contract tests** (`jarvis-llm-proxy-api` PR #3). Added lightweight deps `numpy redis rq boto3` (the `from main import app` chain) + a placeholder `JARVIS_AUTH_BASE_URL` (module-level `get_auth_url()` in settings/pipeline routes). Full job 167 passed.
- **T3 ✅ MERGED · jarvis-command-sdk CI + Alert regression test** (`jarvis-command-sdk` PR #1). First-ever SDK CI; pinned `Alert.to_dict`/`is_expired`; coverage 84→95% (gate 90, treated as a floor).
- **T4 ☐ DEPRIORITIZED · Minimal CI across all 27 device/cmd repos.** Per Alex: breadth < behavior; revisit later. **Size: M (templated).**
- **T5 ✅ MERGED · Regression pins** — `JarvisLogger propagate=False` (`jarvis-log-client` #3), message-bearing command bypasses the LLM (`jarvis-command-center` #12, + a non-swallowing CI step since CC CI was hollow), node→jarvis-logs auth grant (`jarvis-auth` #6). Each is a true regression guard (would flip red if the fix reverted).

### Phase 2 — The real cross-service harness + behavior lane

- **T6a ✅ DONE · Stand up `jarvis-integration-tests`** — new PUBLIC repo `alexberardi/jarvis-integration-tests` ([initial commit `1573b50`](https://github.com/alexberardi/jarvis-integration-tests)). Faithfully migrated `docker-compose.ci.yaml`, `compose/` (overlays + `seed.sh` + `postgres-init.sh`), `tests/` (conftest + `test_loop_smoke` + `test_cc_real_smoke`), `tests/fakes/`, `tools/parse_junit.py`, and the runner out of node-setup. Added `requirements-ci.txt`, a minimal `pyproject.toml` (qa_case marker), README + cutover plan. **`tests/integration/` deliberately left behind** (node-client unit layer that imports the node app + SDK). Verified: all YAML/TOML parse, all Python compiles, suite **collects 22 tests standalone** in a clean venv. **node-setup untouched — live loop intact.**
  - **Cutover:** `INTEGRATION_COMMENT_TOKEN` secret + GHCR `:dev` read are now DONE (set for T9 and validated live). **DONE (2026-06-22):** CC's `integration-trigger.yml` dispatch path was retargeted node-setup → `/repos/alexberardi/jarvis-integration-tests/dispatches` (CC's `INTEGRATION_DISPATCH_TOKEN` re-scoped to integration-tests), and the fast lane (CASE-001..215) validated **22/22 with CC built from source**. node-setup runner retirement = node-setup #36. Separate from T9's from-source triggers, which were already live + validated.
- **T6b ✅ MERGED (2026-06-21; CI secret still pending)** · Behavior corpus through CC's REAL provider — adds a real llm-proxy (`REST`→gpt-4.1-nano) to the CI stack and routes the corpus through command-center's real `ChatGPTOpenAI` prompt + full stack. The convergence point of the testing fix and the unit-of-work fix. Merged as `jarvis-integration-tests` #1 (`bae7169c2`) + REST-backend fix `jarvis-llm-proxy-api` #7 (`e83ad2c82`).
  - **Key finding — the corpus is RE-AUTHORED, not lifted.** The doc claim that the externalized corpus "carries over unchanged" was **false**: llm-proxy's `tools.yaml` is an explicitly *fictional* stand-in toolset whose names AND arg shapes differ from CC's real tools (`set_alarm`→`reminder`, `get_time`→`get_current_time`, `add_to_list`→`shopping_list`/`todo_list`; `duration_minutes`→`duration_seconds`, `device`→`device_name`). T6b ships **CC-targeted fixtures** transcribed from the real command sources (via the SDK's `to_openai_tool_schema()`): `jarvis-integration-tests/tests/behavior/{tools.cc.yaml,corpus.cc.yaml}`.
  - **Scope decision (Alex):** the corpus targets node-setup **BUILT-IN** commands only — the optional `jarvis-cmd-*` packages (`get_weather`/open-weather, `get_news`/news, `music`/music-assistant) are **excluded** (a baseline node may not have them, so they aren't a reliable CI signal). Built-in `calculate` + `convert_measurement` stand in their place. `set_alarm` (no real tool) maps to `reminder`(action=set) — kept (validated). 8 built-in tools: `set_timer, reminder, get_current_time, control_device, shopping_list, todo_list, calculate, convert_measurement`.
  - **What landed (branch `feat/t6b-cc-real-provider-behavior-lane` in `jarvis-integration-tests`):** `tools.cc.yaml` (8 built-in tools), `corpus.cc.yaml` (29 utterances: 26 routing + 3 negatives), `tests/test_cc_behavior_corpus.py` (drives `/conversation/start` + blocking `/voice/command`, ports the 4 matchers, gated on `CC_URL`+node creds), `compose/ci-overlays/llm-proxy-behavior.yaml` (model service :7705 + API :7704, `:dev-cpu`, `JARVIS_LIVE_MODEL_BACKEND=REST`), a parameterized `seed.sh` (`LLM_PROXY_HOST/PORT` so config-discovery points at the real proxy), a `behavior` marker, and `.github/workflows/behavior-corpus.yml` (nightly + dispatch, guard-no-op without key, flips `llm.interface=ChatGPTOpenAI` via CC's settings API — it's DB-only, no env fallback).
  - **Local dry-run (the riskiest leg, validated with the real key):** booted the `:dev-cpu` model service container with the exact behavior-lane env → `live`=gpt-4.1-nano via REST. Routed the full `corpus.cc.yaml` through `/internal/model/chat`: **29/29 correct** to CC's real tool names + arg shapes (incl. every risky translation; 3 negatives declined).
  - **🐞 Bug found + fixed (separate PR, `jarvis-llm-proxy-api` branch `fix/rest-backend-event-loop-reuse`):** the first dry-run hit intermittent 500s — `RuntimeError: Event loop is closed` in `backends/rest_backend.py:generate_text_chat`. Root cause: the persistent `httpx.AsyncClient` (`self.client`, connection pool binds to the loop it's first used on) was reused across the throwaway `asyncio.run` loops the sync bridge spins when called from the model service's async endpoint. **Fix:** route all async-context calls onto one dedicated background event loop. Re-validated: **29/29, 0 event-loop errors**; full llm-proxy suite **217 passed** + 2 new regression tests. This is a real latent bug on any REST-backed inference path, surfaced by the dry-run — the canonical cross-repo unit of work.
  - **Remaining (Alex one-time):** set `OPENAI_API_KEY` secret on `jarvis-integration-tests`; confirm GHCR read access to `:dev`/`:dev-cpu` (no-op if public); run the workflow to validate the FULL CC native-tool path end-to-end in CI (the dry-run validated the model-routing leg, not CC's provider/prompt/native-branch). **Size: M–L.**
- **T7 ✅ MERGED · `ChatGPTOpenAI` prompt provider** in command-center (PR #14). First `supports_native_tools=True` provider (concise prompt; tools via native API param; `use_tool_classifier=False`). 12 unit tests incl. factory discovery. **The native-tool-path shakeout is partially done** (provider + REST passthrough proven live); the full CC engine native branch (`tool_execution_engine.py` `use_native_tools`) is exercised end-to-end only via the local behavior run, not yet a CI test.
- **T8 ✅ MERGED · Behavior lane** (`jarvis-llm-proxy-api` PR #4). Fixed the REST backend (it dropped `tool_calls`); `tests/manual/test_behavior_tool_routing.py` asserts a real gpt-4.1-nano routes a 10-utterance corpus to the correct tool. **PROVEN 10/10.**
  - **T8.1 ✅ MERGED · PR #5 (`c4c59a1`) · Corpus hardened.** 10→29 utterances, **argument-shape assertions** (matchers: equals/contains/in/any_of, not just tool name), **pinned `gpt-4.1-nano-2025-04-14`**, externalized to `tests/manual/behavior/{corpus,tools}.yaml` (provider-agnostic → T6 reuse), + small-talk negatives (over-eager-routing guard). **PROVEN 30/30 across 3 consecutive live runs**, deterministic at temp=0.
  - **T8.2 ✅ MERGED · PR #6 (`dba9bdb`) · Nightly + on-demand CI — LIVE.** `schedule` (08:17 UTC) + `workflow_dispatch`, deliberately not `pull_request` (public-repo secret hygiene). Guard no-ops until `OPENAI_API_KEY` lands. **Alex set the secret; first CI run GREEN 30/30** vs the pinned snapshot (run `27891359331`). OpenAI is now connected to CI.
  - Still open under T8: route the corpus through CC's *real* `ChatGPTOpenAI` provider (that's **T6**) and `llm.interface` seeding.
- **T9 ✅ DONE (all 3 lanes GREEN in CI) · From-source overlays for llm-proxy, whisper, tts** (`jarvis-integration-tests` #4 `dbee25d` + #5 `181e5a5`; dispatch runs `27924404567` llm-proxy 2/2, `27924405026` whisper, `27924405533` tts). Each lane builds the service-under-test from the PR's source into the real CC+auth+config stack, repoints CC at the real container, and fakes only the *other* two. New gated CASEs bind to real round-trips: **CASE-301** (real llm-proxy `/health` reaches the model service over the internal token) + **CASE-302** (CC → real proxy on the **MOCK** backend — no key, proves the OpenAI contract/wiring end-to-end); **CASE-311** (CC → real **Piper** TTS, asserts real audio ≫ the fake's 32 bytes); **CASE-321** (CC → real **whisper** transcribe, shape-asserted so non-flaky). Dedicated `from-source-services.yml` (dispatch + `repository_dispatch`).
  - **Key findings that shaped it:** (1) MOCK echoes plain text with `tool_calls=None`, so the llm-proxy lane proves *contract+wiring*, not routing (that's the behavior lane). (2) **No settings DB needed for whisper/tts** — `jarvis_settings_client.SettingsService.get()` wraps the DB query in `try/except` and falls through to env fallbacks (`service.py`), so a throwaway sqlite `DATABASE_URL` lets `whisper.model_path`→`WHISPER_MODEL` (baked) and `tts.provider`→`TTS_PROVIDER=piper` resolve cleanly — dropping alembic/Postgres complexity. (3) tts default provider is `kokoro` (~300MB download) → forced `TTS_PROVIDER=piper`. (4) whisper builds compile whisper.cpp from C++ source (pywhispercpp sdist) — accepted per Alex, buildx GHA cache mitigates warm runs.
  - **Validated in CI:** all 3 dispatch runs GREEN — the real services build from PR source and the round-trips pass (llm-proxy 2/2, whisper compiles whisper.cpp from source + transcribes, tts synthesizes real Piper audio). The first dispatch surfaced + fixed a `kill 0` teardown self-SIGTERM (each lane starts only 2 of 3 fakes, so the unset PID must not default to 0). **Cutover — triggers WIRED (2026-06-22):** each service repo now has `integration-trigger.yml` firing `repository_dispatch [from-source-integration]` at jarvis-integration-tests on PRs, guarded green-idle until its token is set (`jarvis-llm-proxy-api` #8, `jarvis-whisper-api` #4, `jarvis-tts` #5 — all merged). **Secrets SET (2026-06-22):** `INTEGRATION_DISPATCH_TOKEN` on all 3 service repos + `INTEGRATION_COMMENT_TOKEN` on jarvis-integration-tests. **Receiving path validated green:** a real `repository_dispatch [from-source-integration]` (tts) resolved the `client_payload`, built tts from source, and passed CASE-311 (run `27957245379`) — the one leg `workflow_dispatch` couldn't exercise. (A transient Docker Hub `eclipse-mosquitto` pull timeout flaked the first attempt — the base compose pulls mosquitto + pgvector from Docker Hub, a known intermittent GHA flake across all lanes; mirror to GHCR if it recurs.) **T9 cutover COMPLETE + validated end-to-end (2026-06-22)** — a throwaway tts PR fired the full chain live: `integration-trigger` dispatched with `INTEGRATION_DISPATCH_TOKEN` → from-source lane built real tts → CASE-311 passed → a `from-source-test-results` comment posted back on the PR via `INTEGRATION_COMMENT_TOKEN`. Both tokens confirmed working; throwaway PR closed. **Size: M.**
- **T10 ✅ DONE — all pieces MERGED + validated GREEN in CI (2026-06-22) · Coordinated cross-repo branch sets** via the `linked_prs` map — validate a multi-repo feature *as one unit* (the convergence of the testing fix + the unit-of-work fix). **NEW sibling lane** `cross-repo-services.yml` builds `{originating} ∪ keys(linked_prs)` from source TOGETHER, driven by a stdlib resolver `tools/resolve_cross_repo.py` (folds the originator in, validates names against the 6 from-source overlays, emits the composed overlay `-f` chain / checkout list / `seed.sh` discovery overrides / host-fake skip flags / two plan-case sets). Default demonstrator = **command-center + jarvis-llm-proxy-api** from source. Two mutually-exclusive modes: **CASE-401** (no key) — a direct app-auth'd plain `/v1/chat` to the from-source proxy on MOCK with CC's seeded creds, proving both builds boot + the cross-service credential chain + the API→model hop (gated on CROSS_REPO_CC AND CROSS_REPO_LLM); **CASE-402** (key-gated) — the from-source proxy runs `REST`→gpt-4.1-nano and CC routes a real voice command through its real ChatGPTOpenAI native-tool path. `linked_prs` populated by a **`Linked-PR: <repo>@<ref>` PR-body marker** via a new **symmetric** `cross-repo-trigger.yml` on CC + llm-proxy (both compute the same sorted `feature_key`; the receiver's concurrency group dedups to one run/feature). **Three verified findings applied:** (1) `docker compose up` PULLS `:dev` instead of building when `image:`+`build:` coexist → added `pull_policy: build` to the CC/auth/config overlays + the lane uses `--build` (this ALSO fixes a pre-existing latent bug in the fast lane's CC bring-up); (2) `linked_prs` must be sent as a JSON STRING via `-f` (gh keeps `-f` values as strings); (3) the llm-proxy from-source overlay made backend env-driven (MOCK default, REST when routing) — backward-compatible with the T9 lane. Existing fast/T9/T6b lanes untouched. Locally validated then proven in CI: resolver 7/7 unit tests, overlay merge via `docker compose config` (MOCK + REST). **Merged:** integration-tests #6 (`f18fa52`), command-center #15 + #16, llm-proxy #9 (the symmetric cross-repo trigger; merged 2026-06-22 — verified byte-identical to CC #15 bar one example slug). **T10 lane validated GREEN in CI** (run `27967408363`): CC+llm-proxy built from source together, auto ROUTING mode, **CASE-301 + CASE-402 2/2 pass** (a real voice command routed CC→from-source proxy→gpt-4.1-nano→`set_timer(300s)`). **T6a fast-lane cutover finished in the same session** (CC `integration-trigger` retargeted node-setup→integration-tests, token refreshed, validated 22/22 with CC built from source; node-setup runner-retirement = node-setup #36). **Phase 0 testing-infrastructure is COMPLETE — every piece has landed + been validated.** **Size: M.**

### Parallel quick win — mobile tracks `main`

- **PT-Mobile** (`jarvis-node-mobile`): `expo install expo-updates`, pin `runtimeVersion`, add `channel` to eas.json profiles (dev/preview → `main`, production → `production`), add an `eas update --branch main --channel main` CI step on push to main. Dev/internal builds bulk-track main in seconds; store builds stay stable. *(Note: `node-mobile` already builds from `main`; the tagged-release model is `recipes-mobile`. Native changes — `jarvis-crypto` — still need a rebuild + runtimeVersion bump.)* **Size: S (~half day).**

### Later (post-testing, separate efforts)

Cross-repo unit-of-work in the agents, automerge gate on all-green `qa-execution-report`, full-regression-on-main job, gated auto-deploy with post-deploy smoke + rollback. All gated on the testing foundation above.

---

## Open questions / risks

- **Native tool-calling path** in CC is untested (see KEY RISK above) — the largest unknown in Phase 2.
- **Behavior-corpus flakiness/cost** — a real model is non-deterministic; assert tool *selection* (and arg shape), not exact prose. Pin a model snapshot; cap corpus size.
- **Does the loop need node-setup's own code in-stack**, or is the pytest client with `X-API-Key` creds sufficient? CI uses the latter today (the node's SQLite layer / `voice_listener` never run in-stack).
- **#42 runaway**: a *live* OpenClaw agent (`install-expert`) has posted a near-identical "gaps resolved" comment on `jarvis-roadmap#42` hourly for days with no terminal-state guard. Kill it before it burns more Max quota; add idempotency when the loop is revived.
- **node-setup SQLite is sqlcipher-encrypted** — tests that load its `db.py` need the key (`db.key` / `JARVIS_MASTER_KEY`) provisioned, or one is silently generated.
- **Disk, not RAM, is the eventual ubuntu-latest constraint** if real GPU images are ever added to the stack (the GPU build workflows already include a "free up disk" step).

---

## Appendix — key file references

- **CC prompt providers**: `app/core/interfaces/ijarvis_prompt_provider.py` (ABC; `name` :72, `build_system_prompt` :82-103, `supports_native_tools` default False :199-210); `app/core/prompt_provider_factory.py` (roots :26-29, walk/match :100-115, `_resolve_provider_name` :178-203); `app/services/settings_definitions.py:13-20` (`llm.interface`, `requires_reload`); `app/core/llm_proxy_client.py:57` (`model='live'`); `app/core/tool_execution_engine.py` (native path :558-569, text path :570-578); `app/core/model_service.py:47,68-72`; `app/deps.py:166-185`; `tests/test_prompt_provider_factory.py:23,30,36,47,172`.
- **CI stack**: `jarvis-node-setup/docker-compose.ci.yaml` (services :17-198, fakes :6-9, pgvector :18-22, node register :164); `compose/seed.sh`, `compose/postgres-init.sh`; `tests/fakes/{fake_llm_backend,fake_whisper,fake_tts}.py`, `canned_responses.yaml`; `tools/parse_junit.py`; `docs/integration-tests.md` (seed :138-202, :286-307); `.github/workflows/integration-runner.yml` (runs-on :65, compose up :214-217/:242-245).
- **Triggers**: `jarvis-command-center/.github/workflows/integration-trigger.yml`.
- **jarvis CLI**: `jarvis` (`_find_compose_file` :251, init/tokens :420-459, `_auto_register` :2060-2225, CC test list :72).
- **Data layer**: `jarvis-node-setup` `db.py:31-46` (sqlcipher).
</content>
</invoke>
