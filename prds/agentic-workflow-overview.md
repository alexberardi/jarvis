# PRD: Autonomous Dev Workflow — Master Overview

**Status**: Draft — research consolidated 2026-06-20; **build progress updated 2026-06-21** (see [Progress](#progress-updated-2026-06-21) below). This is the entry point. Read it first, then the detail PRD for whatever you're building.

---

## The vision

Move from "one human typing to one agent" to a pipeline where: a ticket is filed → an agent pulls it and asks clarifying questions → the human answers (iterate until *ready*) → an agent codes it → a QA agent validates the feature actually works → it auto-merges → a full regression runs → and the human only comes in to test manually at the end. Most of this was **already built** on a Raspberry Pi 5 (`openclaw.local`) in May 2026 and then deliberately **paused**, because the testing couldn't be trusted enough to merge on. This effort rebuilds the foundation — testing first — and re-enables the loop on a sounder design.

## The document set

This overview links five detail PRDs. Each is self-contained and citation-backed so the research phase never has to repeat.

| PRD | Covers | Status |
|---|---|---|
| **`testing-infrastructure.md`** | The foundation: honest CI, the cross-service integration harness, the two-lane (fakes / cloud-model behavior) test stack, the `ChatGPTOpenAI` provider, the runner decision. **Build this first.** | Architecture locked |
| **`agentic-dev-loop.md`** | The loop itself: the OpenClaw agent org, the sentinel protocol, the `jarvis-roadmap` ticket DB, the webhook receiver, the paused-state inventory, the unit-of-work root cause + revival design, and a revival checklist. | Findings captured |
| **`cicd-release-deploy.md`** | How Jarvis builds/releases/deploys today (manual admin updater, floating tags, no self-hosted runner, no rollback) and what regression-on-main + gated auto-deploy require. | Findings captured |
| **`mobile-app-delivery.md`** | The Expo/EAS mobile stack, the no-OTA reality, and the EAS `main`-channel plan so dev-mode bulk-tracks `main`. | Findings captured |
| **`agentic-workflow-overview.md`** | This file — the index + roadmap + cross-cutting decisions. | — |

## Current state at a glance

- **Host:** `openclaw.local` = `pi@openclaw.local` = 10.0.0.245 — a Pi 5 (8 GB / ~100 GB free) running the OpenClaw framework, with agents routed through the local `claude` CLI on the **Claude Max subscription (~$0 marginal)**. Scheduled by **systemd `--user` timers** (not cron). See `agentic-dev-loop.md`.
- **What runs today:** the survivor agents — `product`, `qa-executor`, `doc-expert`, `install-expert`, `marketing`.
- **What's paused:** the three core dev-loop agents — `coding-agent`, `engineering` (triage), `qa` (test-plan author) — removed 2026-05-19.
- **The ticket DB:** private repo `alexberardi/jarvis-roadmap` (a pure GitHub-Issues database, empty file tree), driven by sentinel comments.
- **The testing reality:** CI is hollow across most of the ecosystem (command-center runs 3 of 185 test files; the SDK and all 27 device/cmd repos have no CI). The one real cross-service harness (`docker-compose.ci.yaml` on `ubuntu-latest`) exists but is wired only for command-center and fakes the LLM/STT/TTS. See `testing-infrastructure.md`.

## The root insight

The loop was paused for two reasons that share **one root cause**: the atomic unit of work was a **single-repo PR**, but real Jarvis features are **cross-repo**. The coding-agent was hard-coded to abort on cross-repo work and triage split features into per-repo child tickets — so a coherent feature fragmented into ordering-dependent tickets ("things got out of sync") and recursive splitting ("2–3 issues became 30"). Underneath that, the tests couldn't validate cross-repo behavior, so nothing was trustworthy enough to merge. **Therefore: fix testing first; redesign the unit of work to be a feature spanning N repos (coordinated branch set, merged as a group); only then re-enable the loop.**

## The phased roadmap

```
Phase 0 — TESTING INFRASTRUCTURE   (testing-infrastructure.md)  ← build first; pays off regardless
   ├─ ✅ Make CI honest + pin known prod bugs (no stack needed)  [T1,T2,T3,T5 merged]
   ├─ ✅ Stand up jarvis-integration-tests repo (migrate the harness)  [T6a DONE — public repo, 22 tests collect standalone; fast-lane cutover DONE (wired into CI)]
   │   └─ ✅ Route the corpus through CC's real ChatGPTOpenAI provider + full stack  [T6b — DONE, MERGED; GREEN 30/30 in CI vs pinned gpt-4.1-nano; stability-confirmed 3×]
   ├─ ✅ Behavior lane: llm-proxy REST→cloud model + ChatGPTOpenAI provider + voice-command corpus  [T7,T8 merged; PROVEN 10/10 vs gpt-4.1-nano]
   ├─ ✅ Harden the corpus: 10→29 utterances, arg-shape assertions, pinned snapshot, externalized YAML  [PR #5 MERGED; PROVEN 30/30 x3 live]
   ├─ ✅ Wire the behavior corpus as a NIGHTLY + on-demand CI job  [PR #6 MERGED; secret SET; first CI run GREEN 30/30 — OpenAI now connected to CI]
   ├─ ✅ Broaden: from-source overlays for llm-proxy/whisper/tts  [T9 — DONE; all 3 lanes GREEN in CI; cutover wired + validated end-to-end on a real PR]
   └─ ✅ Coordinated cross-repo branch sets  [T10 — DONE; all 4 pieces MERGED (integration-tests #6, CC #15+#16, llm-proxy #9 merged 2026-06-22) + validated GREEN in CI (run 27967408363, CASE-301+402 2/2, CC+llm-proxy from source, routing→gpt-4.1-nano). Phase 0 COMPLETE → unblocks Phase 1]

Phase 1 — LOOP REVIVAL             (agentic-dev-loop.md)        ← UNBLOCKED; R0 in progress (2026-06-22)
   ├─ 🔄 R0: secure ~/github.env (verified orphan; chmod 600+rotate) + refresh PATs   [commands prepped; Alex runs]
   ├─ 🔄 R0: install-expert runaway DORMANT since 2026-06-10; timer still fires hourly → disable it; v2 guard spec'd (label-based, adversarially verified)
   ├─ Restore the 3 removed agents (prompts + workspaces + systemd timers)
   ├─ Redesign unit-of-work: feature spanning N repos, merge-as-group, anti-split bias
   └─ Add machine-checkable "ready" gate + structured clarify loop + idempotency guards (incl. the install-expert v2 guard)

Phase 2 — DEPLOY AUTOMATION        (cicd-release-deploy.md)     ← gated on Phase 0
   ├─ Full-regression-on-main job (reuse the integration-runner)
   ├─ Digest-pinned release manifest (kill floating-tag non-reproducibility)
   └─ Gated auto-deploy: green regression → apply → post-deploy smoke → auto-rollback

Parallel — MOBILE                  (mobile-app-delivery.md)     ← EXPANDED into a UI/e2e testing pyramid (in progress 2026-06-23)
   ├─ Hosted EAS Update 'main' channel (delivery) — designed, not yet built
   └─ 🔄 UI/e2e testing (the bigger correctness piece): **P0 + both L1 flows MERGED** (node-mobile #7/#8/#9 — real-hook provisioning wizard + auth bootstrap); **P2 fake-node overlay MERGED + locally validated** (integration-tests #16 — node-setup builds-from-source, serves the real /api/v1/* in sim mode); next = P3 (Maestro L2) + interactive EAS/simulator validation. Provisioning is fakeable end-to-end (HTTP, node-setup SimulatedWiFi + the app's DEV_MODE manual-IP); only the phone-side AP join stays manual.
```

## Locked decisions (2026-06-20)

1. **Tests live in a new `jarvis-integration-tests` repo** (migrate the harness out of node-setup).
2. **Behavior tests use a cheap cloud model via llm-proxy's `REST` backend** (gpt-4.1-nano class) — *not* a self-hosted GPU runner.
3. **Mobile dev-mode tracks `main` via hosted EAS Update (`main` channel).**
4. **CI runner = GitHub-hosted `ubuntu-latest`**; the Pi 5 is a documented fallback, not built.

## ⚠️ Security finding (surfaced during documentation)

`~/github.env` on the Pi is **world-readable (mode 644)** and contains **bare GitHub PAT strings** (one `ghp_` + four `github_pat_`, one per line). Any user/process on the host can read live GitHub credentials. **Action:** `chmod 600` (or move into `~/.openclaw/secrets/` and delete the plaintext copy), and rotate the tokens (they're likely expired anyway). Tracked in `agentic-dev-loop.md`'s revival checklist. Token *values* were deliberately never read or recorded. **Verified 2026-06-22:** confirmed an **orphan** — no systemd unit or config references it (all 8 units load `~/.openclaw/secrets/github.env`, mode 600), so it's safe to remove after rotation; exact commands in `agentic-dev-loop.md`'s R0 status block. **Update 2026-06-22:** Alex has revoked + recycled the PATs; the orphan's tokens are now dead, so deleting the file is pure tidiness.

## Progress (updated 2026-06-22)

**Phase 0 "make CI honest" is done and merged; the behavior lane exists and is proven.** All landed via one branch→PR→squash-merge per ticket.

| Ticket | What landed | Repo / PR |
|---|---|---|
| T3 ✅ | First-ever SDK CI + `Alert` regression pin; coverage 84→95% | `jarvis-command-sdk` #1 |
| T2 ✅ | Un-ignored llm-proxy's chat + embeddings OpenAI-contract tests (MOCK backend) | `jarvis-llm-proxy-api` #3 |
| T5 ✅ | 3 regression pins: JarvisLogger `propagate=False`, message-bypasses-LLM, node→logs-403 | `jarvis-log-client` #3, `jarvis-command-center` #12, `jarvis-auth` #6 |
| T1 ✅ | command-center runs its **full suite** vs a pgvector Postgres service, gated (was 3-of-69 with `\|\| echo` swallowing). Surfaced 21 hidden stale-test/fragility issues, **zero app bugs**. | `jarvis-command-center` #13 |
| T7 ✅ | `ChatGPTOpenAI` native-tool-calling prompt provider (first `supports_native_tools=True`) | `jarvis-command-center` #14 |
| **T8 ✅** | REST backend tool passthrough (it was silently dropping `tool_calls`) + **behavior lane**: real **gpt-4.1-nano routed a 10-utterance corpus 10/10** to the correct tool | `jarvis-llm-proxy-api` #4 |
| **T8.1 ✅** | **Hardened the corpus**: 10→29 utterances, **argument-shape assertions** (not just tool name), **pinned `gpt-4.1-nano-2025-04-14`**, externalized to provider-agnostic YAML (`tests/manual/behavior/{corpus,tools}.yaml`) for T6 reuse, + small-talk negatives. **PROVEN 30/30 across 3 consecutive live runs** (deterministic at temp=0). | `jarvis-llm-proxy-api` #5 (`c4c59a1`) |
| **T8.2 ✅** | **Nightly + on-demand CI job** for the behavior lane (`schedule` + `workflow_dispatch`, not PR — public-repo secret hygiene). Guard step keeps it green/idle until `OPENAI_API_KEY` is set, then runs for real. | `jarvis-llm-proxy-api` #6 (`dba9bdb`) |
| **T6b ✅** | **Behavior corpus through CC's REAL provider — MERGED; GREEN in CI (30/30 vs pinned `gpt-4.1-nano`, stability-confirmed 3×).** Discovered the externalized corpus does NOT "carry over unchanged" (llm-proxy's `tools.yaml` is a *fictional* stand-in; CC's real tools differ in name + arg shape) → **re-authored** `tools.cc.yaml` + `corpus.cc.yaml` from the real command sources. Added a real-llm-proxy compose overlay (`REST`→gpt-4.1-nano), CC `/voice/command` behavior test, `seed.sh` proxy-target param, and a nightly+dispatch workflow that flips `llm.interface=ChatGPTOpenAI`. Dry-run booted the `:dev-cpu` model service with the real key → **29/29 correct routing**. | `jarvis-integration-tests` #1 (`bae7169c2`) |
| **🐞 REST-loop fix ✅** | **Latent bug surfaced by the T6b dry-run + fixed; MERGED.** `rest_backend.py:generate_text_chat` reused the persistent `httpx.AsyncClient` across the throwaway `asyncio.run` loops the sync bridge spins from the model service's async endpoint → intermittent `RuntimeError: Event loop is closed` (flaky 500s on any REST-backed inference under load). Fixed by routing async-context calls onto one dedicated background loop. **217 passed + 2 regression tests; re-validated 29/29, 0 errors.** | `jarvis-llm-proxy-api` #7 (`e83ad2c82`) |
| **Corpus stability pass ✅** | **The CC-real-provider behavior-corpus red on integration-tests `main` was STALE, not a real failure.** The 4× `control_device` errors predate #2 (which dropped it — a multi-turn HA flow CI can't resolve) and the `get_current_time` misroute is the exact utterance #3 rephrased; no run had landed on main *after* both fixes. Re-validated current main with **3 consecutive independent full-stack runs, GREEN 30/30 each (90/90 routings)** → the lane is stable. All ecosystem repos' latest main CI is green. | `jarvis-integration-tests` (runs `27922094306`/`27922416513`/`27923430337`) |
| **T9 ✅** | **From-source overlays for llm-proxy / whisper / tts — DONE; all 3 lanes GREEN in CI.** Each lane builds the service-under-test from PR source into the real CC+auth+config stack, repoints CC at the real container, fakes only the other two. Gated CASEs (all passed live): **301** real proxy `/health`→model-service hop; **302** direct app-auth'd `/v1/chat/completions` on the **MOCK** backend (no key); **311** CC→real **Piper** TTS, real audio ≫ fake's 32 bytes; **321** CC→real **whisper** transcribe (whisper.cpp compiled from source), shape-asserted. Dedicated `from-source-services.yml`. Two findings: whisper/tts need **no settings DB** — `jarvis_settings_client.get()` swallows DB errors → env fallback (sqlite `DATABASE_URL` + baked `WHISPER_MODEL`/`TTS_PROVIDER=piper`); and MOCK can't satisfy CC's `response_format=json_object` path, so the llm-proxy lane validates the proxy's OWN contract directly (CC→real-model is the behavior lane's job). The first dispatch surfaced + fixed a `kill 0` teardown self-SIGTERM. **Cutover DONE + validated end-to-end (2026-06-22):** triggers added to all 3 service repos (`jarvis-llm-proxy-api` #8, `jarvis-whisper-api` #4, `jarvis-tts` #5), both secrets set, and a throwaway tts PR fired the full live chain — trigger→dispatch→build→CASE-311→results comment posted back. **T9 fully complete.** | `jarvis-integration-tests` #4 (`dbee25d`) + #5 (`181e5a5`); CI runs `27924404567`/`27924405026`/`27924405533` |

**T4 (27-repo reusable CI template) deprioritized** per Alex (breadth < behavior; coverage % is a floor not a target — see the testing PRD's "Direction" note).

**Two live-model findings worth keeping** (from the #5 live runs): gpt-4.1-nano fills *primary-subject* args reliably (location, topic, query, item) but *secondary optional* args inconsistently (`list_name`) → assert only reliable args or the lane goes flaky; and "what's the weather like **today**" mis-routes to `get_time` (latches on "today") → curate phrasings the pinned model handles, so green = a real regression baseline.

**Key facts to carry forward:**
- The behavior corpus now runs **nightly + on-demand in CI** (`.github/workflows/behavior-nightly.yml`) AND locally. It's still excluded from the PR fast suite (lives under `tests/manual/`, skips without a key). The OpenAI key lives at `~/.jarvis/secrets/openai.env` (chmod 600, `JARVIS_REST_AUTH_TOKEN`, **no `export` — source with `set -a`**). Run live: `set -a && source ~/.jarvis/secrets/openai.env && set +a && JARVIS_REST_PROVIDER=openai JARVIS_REST_AUTH_TYPE=bearer .venv/bin/python -m pytest tests/manual/test_behavior_tool_routing.py -v`.
- **DONE (2026-06-21):** Alex set the usage-capped `OPENAI_API_KEY` GH secret and ran the nightly on demand — **first CI run GREEN, 30/30** vs pinned `gpt-4.1-nano-2025-04-14` (run `27891359331`). OpenAI is now connected to CI; the behavior lane runs nightly + on-demand and a routing regression will turn it red.
- The reproduce-CI-faithfully trick (a recurring trap): hide the repo `.env` and run with a clean env — `load_dotenv()` + a locally-installed config-client otherwise mask the missing service-discovery / auth env that CI lacks (`JARVIS_AUTH_BASE_URL`, `JARVIS_AUTH_SECRET_KEY`, etc.).

## Resume here (next section)

In priority order:
1. ✅ **Expand + harden the corpus** — done (PR #5): 29 utterances, arg-shape assertions, pinned snapshot, externalized YAML. Proven 30/30 x3 live.
2. ✅ **Wire the behavior corpus as a nightly + on-demand CI job** — done (PR #6); secret set; **first CI run GREEN 30/30**. OpenAI connected to CI; signal is continuous.
3. ✅ **T6a — stood up `jarvis-integration-tests`** (PUBLIC, `1573b50`). Faithful harness lift out of node-setup; validated standalone (22 tests collect in a clean venv). node-setup's live runner untouched. **Cutover DONE** (secrets set, GHCR read confirmed, CC's `integration-trigger.yml` retargeted; the T6b/T9/T10 lanes all run here GREEN). Remaining loop-deployment gates are only SHARED-SPEC §15 prereqs #2-#4 (all Alex-gated).
4. ✅ **T6b — route the corpus through CC's real provider — DONE; LANE GREEN 30/30 in CI (2026-06-21).** `jarvis-integration-tests` #1 (`bae7169c2`) + REST fix `jarvis-llm-proxy-api` #7 (`e83ad2c82`) + corpus fixes #2 (`a7356cd99`, drop `control_device` — a multi-turn HA flow not testable without HA node-context) + #3 (`c518e9db2`, rephrase one borderline todo utterance). The FULL CC native-tool path is validated end-to-end against real gpt-4.1-nano (7 built-in tools, 29 utterances + load guard = 30/30). `OPENAI_API_KEY` secret set; nightly + on-demand signal live. **KEY RISK (CC's never-before-exercised native tool-calling branch) retired.**
5. ✅ **T9 — from-source overlays for llm-proxy/whisper/tts — DONE; all 3 lanes GREEN in CI** (`jarvis-integration-tests` #4 + #5; dispatch runs `27924404567`/`27924405026`/`27924405533`). Real services built from PR source + round-trips pass. **Cutover DONE + validated live (2026-06-22):** triggers merged (`jarvis-llm-proxy-api` #8, `jarvis-whisper-api` #4, `jarvis-tts` #5), both secrets set (`INTEGRATION_DISPATCH_TOKEN` on the 3 service repos, `INTEGRATION_COMMENT_TOKEN` on jarvis-integration-tests), GHCR read confirmed, and a throwaway tts PR proved the full chain (trigger→dispatch→build→CASE-311→comment posted back). **T9 fully complete.**
6. ✅ **T10 — coordinated cross-repo branch sets via `linked_prs` — DONE; all pieces MERGED + validated GREEN in CI (2026-06-22, run 27967408363: CASE-301+402 2/2, CC+llm-proxy built from source together, routing→gpt-4.1-nano). The symmetric llm-proxy trigger (PR #9) merged 2026-06-22 — Phase 0 (testing-infrastructure) is now COMPLETE and Phase 1 (loop revival) is unblocked.** A NEW sibling lane `cross-repo-services.yml` + a stdlib resolver `tools/resolve_cross_repo.py` build `{originating} ∪ keys(linked_prs)` from source TOGETHER; **CASE-401** (no key) proves CC + llm-proxy compose + the cross-service credential chain, **CASE-402** (key-gated) routes a real voice command through the from-source proxy to gpt-4.1-nano. `linked_prs` populated by a **symmetric `Linked-PR: <repo>@<ref>` PR-body marker** trigger on CC + llm-proxy. Also fixed a verified latent bug — `docker compose up` was PULLING `:dev` instead of building PR source (`image:`+`build:` coexist) — via `pull_policy: build` on the CC/auth/config overlays. Existing fast/T9/T6b lanes untouched. The LAST Phase-0 ticket — the convergence of the testing fix + the unit-of-work fix; merging it unblocks **Phase 1 (loop revival)**.

## Open decisions for Alex (carried across the detail PRDs)

- **Prod-deploy autonomy** — does the no-touch-prod rule permit an automated deploy agent, or must prod deploys stay human-approved? (`cicd-release-deploy.md`)
- **`jarvis` CLI as CI driver** vs `compose.ci` canonical — recommended `compose.ci`; open to revisit. (`testing-infrastructure.md`)
- **Self-hosted CUDA runner** on 10.0.0.122 for real *local*-model regression — deferred; the cloud model covers behavior for now. (`cicd-release-deploy.md`)
- **Ticket intake UX** — the system is GitHub-Issues-based but interaction happens in Slack; whether to keep Issues as the agents' DB or build a different front-door. (`agentic-dev-loop.md`)
</content>
