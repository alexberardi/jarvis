# PRD: CI/CD — Build, Release, and Deploy

**Status**: Draft — findings captured 2026-06-20.

---

## Overview / TL;DR

Jarvis today has a working **build/publish** layer (every service has a GitHub-hosted Docker build workflow that pushes to `ghcr.io`), a working **release/tagging** layer (a manual `tag-release.sh` that pushes `v*` tags + a per-service release surface, plus a client-pinning script), and an **operator-driven prod deploy** (the `jarvis-admin` updater: regenerate compose → `docker compose pull` → restart → liveness-verify, human-clicked against the host-mounted `~/.jarvis/compose`).

What does **not** exist: any deploy *automation* (no SSH/cron/`workflow_run` deploy job), any **pre-prod regression gate** (nothing boots the full stack on freshly-built images and runs the CASE suite before anything is promoted/deployed), any **rollback** (the post-deploy step is liveness-only, no auto-revert), and any **self-hosted runner** (every workflow is GitHub-hosted, so there is zero GPU real-model regression and zero hardware-in-the-loop testing in CI). Prod rides **floating tags** (`:dev` / `:latest`, never digest-pinned) against a **hand-editable** `~/.jarvis/compose`, which makes a given prod state non-reproducible.

This PRD is the canonical record of how build/release/deploy works today, plus a phased plan to add a post-merge full-regression gate, a digest-pinned release manifest, and a gated auto-deploy with rollback. Promotion is explicitly tied to the testing foundation in [`prds/testing-infrastructure.md`](./testing-infrastructure.md).

> The hollow-CI details (3-of-185 in command-center, llm-proxy ignoring its own contract tests, mocked boundaries) are **owned by `prds/testing-infrastructure.md`** — this PRD cross-links them rather than re-litigating.

---

## Current state (verified)

### 1. Build / publish — `docker-build-push.yml` per service

Most services have `.github/workflows/docker-build-push.yml`. The **common** pattern (auth, config-service, command-center, logs, mcp, ocr-service, settings-server, tts, whisper-api, recipes-server):

- Triggers on `push` to `main` **and** `tags: ['v*.*.*']` (`jarvis-command-center/.github/workflows/docker-build-push.yml:3-8`).
- Registry is `ghcr.io`, image is `${{ github.repository }}` (`:11-12`).
- `docker/metadata-action` tag rules: **push to `main` → `:dev`** (`type=raw,value=dev,enable={{is_default_branch}}`), **`v*` tag → `:{version}` + `:{major}.{minor}` + `:latest`** (`jarvis-command-center/.github/workflows/docker-build-push.yml:66-74`; identical block in auth/config-service/logs/mcp/ocr/settings-server `:49-55`).

**But the "main → `:dev`" pattern is NOT universal** — three deviations were verified:

- **`jarvis-notifications`** pushes `:latest` + `:{sha}` on *every* push to main (no `:dev`, no metadata-action) — `jarvis-notifications/.github/workflows/docker-build-push.yml:36-40`.
- **`jarvis-relay`** pushes `:latest` + `:{sha}` on every push to main — `jarvis-relay/.github/workflows/docker-build-push.yml:33-37`.
- **`jarvis-web`** uses `:latest` on the default branch (`type=raw,value=latest,enable={{is_default_branch}}`) — `jarvis-web/.github/workflows/docker-build-push.yml:79`.
- **`jarvis-node-setup`** uses `:edge` on main (not `:dev`) and `:latest` + `:{version}` on tag/dispatch-release — `jarvis-node-setup/.github/workflows/release.yml:241-247`.

**jarvis-llm-proxy-api builds 4 GPU variants** via a matrix (`cuda`/`vulkan`/`rocm`/`cpu`, one Dockerfile each), tagging `dev-{suffix}` on main and `{version}-{suffix}` + `latest-{suffix}` on tag — `jarvis-llm-proxy-api/.github/workflows/docker-build-push.yml:21-37,78-84`. **whisper-api** builds 3 variants (cpu/cuda/rocm) with `flavor: suffix=…,onlatest=true` — `jarvis-whisper-api/.github/workflows/docker-build-push.yml:18-31,79-90`.

GPU/multi-variant builds run a "Free up disk space" step (deletes dotnet/android/CodeQL/boost + `docker system prune`) because stock `ubuntu-latest` OOMs on disk — `jarvis-llm-proxy-api/.github/workflows/docker-build-push.yml:42-57`; whisper additionally uses `jlumbroso/free-disk-space` for the ROCm variant (`:41-43` comment).

Per-PR `test.yml` runs unit tests on `ubuntu-latest` (push to main + PR) — e.g. `jarvis-llm-proxy-api/.github/workflows/test.yml:3-11`. **The CI is hollow** (cross-linked, not re-litigated): llm-proxy's `test.yml` `--ignore`s its own `tests/test_chat_completions.py` and `tests/test_embedding_routes.py` (`:44,50`); command-center runs 3 files with 2 wrapped in `|| echo "may fail without full deps"` (`jarvis-command-center/.github/workflows/test.yml:44,48`). Full detail and remediation live in `prds/testing-infrastructure.md` ("CI today is hollow").

### 2. Image architecture (verified via `platforms:` lines)

| Image | Platforms | Evidence |
|---|---|---|
| auth | `linux/amd64,linux/arm64` | `jarvis-auth/.github/workflows/docker-build-push.yml:61` |
| config-service | `amd64 + arm64` | `jarvis-config-service/.github/workflows/docker-build-push.yml:61` |
| command-center | `amd64 + arm64` (uses QEMU) | `jarvis-command-center/.github/workflows/docker-build-push.yml:44-45,80` |
| logs / mcp / ocr / settings-server / tts | `amd64 + arm64` | respective `:61` / `:80` |
| notifications | `amd64 + arm64` | `jarvis-notifications/.github/workflows/docker-build-push.yml:35` |
| recipes-server (active) | `amd64 + arm64` | `jarvis-recipes-server/.github/workflows/docker-build-push.yml:80` |
| **llm-proxy-api** | **`linux/amd64` ONLY** (CUDA/GPU bases) | `jarvis-llm-proxy-api/.github/workflows/docker-build-push.yml:91` |
| whisper-api | cpu = `amd64+arm64`; cuda/rocm = `amd64` only | `jarvis-whisper-api/.github/workflows/docker-build-push.yml:22,26,30` |
| **relay** | **`amd64` only** (no `platforms:` line → buildx default) | `jarvis-relay/.github/workflows/docker-build-push.yml:28-37` |
| web / node-setup images | per-arch native runners merged into multi-arch manifest | `jarvis-web/.github/workflows/docker-build-push.yml:18-24`; `jarvis-node-setup/.github/workflows/release.yml:155-158` |

- **`jarvis-recipes-server` has a `docker-build-push-amd64-only.yml.disabled`** variant kept as an alternative (faster/less disk) — `jarvis-recipes-server/.github/workflows/docker-build-push-amd64-only.yml.disabled:1-6,78`.
- **`jarvis-notifications-relay` has no `.github/workflows/` directory** — it is not built in CI (verified: directory absent).

### 3. Release / tagging

- **`scripts/tag-release.sh`** — operator runs `./scripts/tag-release.sh v0.1.0 <repo|--all> [--retag]`. For each repo it warns on uncommitted changes, (optionally) deletes the old remote/local tag + GitHub release, then `git tag` + `git push origin <tag>` to fire each repo's tag-triggered build/release (`scripts/tag-release.sh:69-122`). Special-cases `jarvis-admin`: rewrites `platformVersion` in `server/src/data/service-registry.json`, commits, and pushes before tagging (`:102-115`). The hard-coded `ALL_REPOS` list is **16 repos** (`:19-36`) — notably **excludes** llm-proxy, ocr-service, relay, recipes-server, and all `device-*`/`cmd-*`.
  - **[unverified — likely latent bug]** `tag-release.sh` uses `local semver=…` / `local reg_file=…` at top scope (`:104,107`) inside a `for` loop, not a function. Under `set -e` (`:10`), `local` outside a function is a bash error; the jarvis-admin platformVersion bump branch may abort. Not runtime-confirmed here.
- **`scripts/pin-clients.sh`** — pins the 4 client libs (`jarvis-config-client`, `jarvis-log-client`, `jarvis-settings-client`, `jarvis-auth-client`) to their latest short commit hash in every repo's `requirements*.txt` / `pyproject.toml` (both PEP 508 `git+…@hash` and Poetry `rev=` forms), so a client update busts Docker layer cache. `--dry-run` / `--commit` modes (`scripts/pin-clients.sh:40-176`). This is a **source-pin** of *client libraries* — orthogonal to *image* tagging.
- **`scripts/pull-all.sh`** — `git pull --ff-only` across all `jarvis-*` repos, skipping dirty/diverged (`scripts/pull-all.sh:17-42`). Dev convenience, not deploy.
- **`scripts/deploy-configs.sh` / `refresh-configs.sh`** — these copy **editor/tmux dotfiles** (`configs/tmuxinator-jarvis.yml`, `configs/nvim/`) to/from `~/.config`. **They are NOT service deploy scripts** despite the name (`scripts/deploy-configs.sh:11-43`).
- **Release workflows** (tag-triggered, beyond the plain image build):
  - **`jarvis-admin/.github/workflows/release.yml`** — on `v*.*.*`: builds standalone `bun`-compiled binaries for darwin-arm64 / linux-x64 / linux-arm64 / windows-x64 (`:18-35`), publishes an npm package (`:251-314`), builds a multi-arch Docker image (`:343-354`), and creates a GitHub Release with checksums (`:210-248`). The admin GitHub Release is what the in-prod updater polls (see below).
  - **`jarvis-node-setup/.github/workflows/release.yml`** — on push to main, `v*`, or `workflow_dispatch`: builds an arm64 install tarball (`:24-68`), and builds `jarvis-node`(headless) + `jarvis-node-audio` images per-arch on native runners, pushed **by digest**, then merged into one multi-arch tag (main → `:edge`; tag/dispatch-release → `:latest` + `:{version}`) — `:150-277`.
  - **`jarvis-installer/.github/workflows/deploy.yml`** — **deploys to GitHub Pages** (a static install landing site: `npm ci && npm test && npm run build` → `actions/deploy-pages`). This is **not** a service deploy (`jarvis-installer/.github/workflows/deploy.yml:1-41`).

### 4. Prod deploy — manual / operator-driven (the key finding)

Prod deploys are **human-clicked through the `jarvis-admin` updater**, never automated. The flow:

1. **Check for update** — `update-checker.ts` polls `https://api.github.com/repos/alexberardi/jarvis-admin/releases/latest`, compares semver against the running `VERSION`, caches 30 min (`jarvis-admin/server/src/services/update-checker.ts:3-4,28-71`). The **`jarvis-admin` GitHub Release tag is the platform version proxy** — there is no per-service version manifest.
2. **Apply** — `POST /update/apply` (superuser-only, SSE) calls `runUpgrade()` (`jarvis-admin/server/src/routes/update.ts:52-83`). In Docker mode it runs `runDockerUpgrade()` (`jarvis-admin/server/src/services/upgrade/orchestrator.ts:33-72`):
   - **regenerate compose** — `upgradeCompose()` backs up `docker-compose.yml`/`.env`/`init-db.sh`, reconstructs `WizardState` from the existing `.env`, regenerates compose from the bundled registry, merges env, regenerates `init-db.sh` (`jarvis-admin/server/src/services/upgrade/compose-upgrader.ts:49-114`).
   - **`docker compose pull`** — `pullImages()` shells `docker compose -f … pull` against the host-mounted compose dir (`jarvis-admin/server/src/services/upgrade/service-updater.ts:28-49`).
   - **restart** — `restartServices()` runs `docker compose up -d --force-recreate <services>`, **skipping tier-0/1 (config-service, auth) and jarvis-admin itself** (restarting admin would SIGKILL the in-flight sweep) — `:51-86`. Admin must be updated separately via `docker compose pull jarvis-admin && … --force-recreate jarvis-admin` (`orchestrator.ts:71`).
   - **verify** — `verifyHealth()` calls `pollServiceHealth()` and **only counts healthy/unhealthy + emits a message** — `:88-105`. **It does not fail the upgrade and does not roll back.**
3. A **dev/stable track switch** exists: `WizardState.releaseTrack: 'stable' | 'dev'` (`jarvis-admin/server/src/types/wizard.ts:48`). `env-generator` maps it to the floating image tag — **`stable → :latest`, `dev → :dev`** (`jarvis-admin/server/src/services/generators/env-generator.ts:127`). Switching tracks via the install/reconcile route triggers an explicit `docker compose pull` + `--force-recreate` (`jarvis-admin/server/src/routes/install.ts:869-912`).

**Image references in generated compose are floating env-var tags, never digests:**
- Admin-generated services: `${baseImage}:${JARVIS_IMAGE_TAG:-latest}${gpuSuffix}` — `jarvis-admin/server/src/services/generators/compose-generator.ts:243-264` (GPU suffix from `state.hardware.gpuType`: nvidia→`-cuda`, amd→`-vulkan`, amd-rocm→`-rocm`, none→`-cpu`, `:253-261`).
- The standalone GPU box compose at **`deploy/llm-proxy/docker-compose.yaml`** uses `ghcr.io/alexberardi/jarvis-llm-proxy-api:${LLM_PROXY_VERSION:-dev}` (default **`:dev`**) for api/model/worker/migrate (`:15,42`), updated by hand via `docker compose pull && docker compose up -d` (`:5-7`).

**Consequences (verified):**
- **No deploy automation** — no SSH/scp/rsync/cron/`workflow_run` deploy job anywhere (`grep` over all `.github/workflows/` for `ssh|scp|rsync|ssh-action` → zero hits; `workflow_run` → zero hits).
- **No pre-prod regression gate** — nothing boots the full stack on the new images and runs the CASE suite before pull/restart.
- **No rollback** — `verifyHealth` is liveness-only (`service-updater.ts:88-105`).
- **Non-reproducible prod** — floating `:dev`/`:latest` tags + a hand-editable `~/.jarvis/compose`. Per the prod rule in `jarvis/CLAUDE.md`: "NEVER write directly to prod (`~/.jarvis/compose`) without explicit user instructions."
- The **`jarvis` CLI** (`/Users/alexanderberardi/jarvis/jarvis`, 127 KB) is a **local dev orchestrator only** — it has no deploy/ssh/prod path (grep for `ssh|scp|prod|compose pull` finds only a local `~/.jarvis/admin.json` stamp at `:669-679`).
- **`PUSH-PLAN.md`** is a one-time **pre-release security/history-cleanup plan** (secret rotation, `git filter-repo` purges, org hygiene), not a deploy pipeline (`PUSH-PLAN.md:1-162`).

### 5. Runners — all GitHub-hosted; zero self-hosted

`grep 'runs-on:'` across **every** `.github/workflows/` file resolves to GitHub-hosted runners only: `ubuntu-latest` (60×), `ubuntu-24.04-arm` (free native arm64 for public repos), `macos-14` / `macos-15`, `windows-latest`, and matrix expansions (`matrix.os` / `matrix.runner`) that all enumerate those same hosted labels (`jarvis-admin/.github/workflows/release.yml:22-33`; `jarvis-node-setup/.github/workflows/release.yml:155-158`; `jarvis-web/.github/workflows/docker-build-push.yml:18-23`; `jarvis-node-mobile/.github/workflows/ci.yml:59`). **No `self-hosted` label exists anywhere.**

**Consequence:** zero GPU **real-model** regression (llm-proxy/whisper run only against MOCK/fakes in CI) and zero **hardware-in-the-loop** (Pi) testing. The GPU box (`10.0.0.122`, Ubuntu — runs LLM/Whisper per `HOSTS.local.md:10`) is a candidate self-hosted CUDA runner, and the mac (`10.0.0.103`, `HOSTS.local.md:11`) a candidate MLX runner — **both currently unused for CI**.

### 6. The one cross-repo CI mechanism (per-PR, not post-merge)

The only cross-service automation is the integration-runner, and it fires **per-PR**, not post-merge:

- **`jarvis-command-center/.github/workflows/integration-trigger.yml`** fires a `repository_dispatch` (`event_type=pr-integration`) at `jarvis-node-setup` on CC PR open/sync/reopen (`:13-49`). **This trigger exists only in command-center** (verified: no other repo has `integration-trigger.yml`).
- **`jarvis-node-setup/.github/workflows/integration-runner.yml`** receives it on `ubuntu-latest`, boots the trimmed stack, runs the CASE suite, comments back (`:20-72`). For the rest of the stack it pulls `ghcr.io :dev` images (`:55-63` comment; `linked_prs` default `{}` → `:dev`). Full harness detail is owned by `prds/testing-infrastructure.md`.

There is **no full-regression-on-main job**: a merge to main only builds the new `:dev` image; nothing boots the full stack on those `:dev` images and runs the CASE suite to gate a `dev → candidate` promotion.

---

## How it works (end-to-end, today)

```
                         ┌─────────────────── BUILD/PUBLISH (GitHub-hosted) ───────────────────┐
  push to main  ───────▶ │ docker-build-push.yml → ghcr.io/<repo>:dev   (per service)          │
                         │   (llm-proxy: 4 GPU variants :dev-{cuda|vulkan|rocm|cpu}, amd64)     │
                         │   (notifications/relay/web: :latest on main; node-setup: :edge)      │
  per PR        ───────▶ │ test.yml (unit, often hollow) ; CC PRs also dispatch integration    │
                         └─────────────────────────────────────────────────────────────────────┘
                                                  │  (NO post-merge full-regression gate)
  operator runs  ──────▶ scripts/tag-release.sh v0.1.0 <repo|--all>
                              │  git tag v* + push  ─────────────▶ tag build → ghcr.io/<repo>:latest + :{version}
                              │  (admin: bumps platformVersion, builds binaries/npm + GH Release)
                                                  │
                         ┌─────────────────── PROD DEPLOY (human-clicked) ────────────────────┐
  superuser clicks ────▶ │ jarvis-admin /update/apply (SSE):                                   │
   "Update" in admin     │   1. check: poll alexberardi/jarvis-admin GH releases/latest        │
                         │   2. compose: upgradeCompose() regenerates ~/.jarvis/compose/*       │
                         │   3. pull:    docker compose pull   (floating :dev/:latest tags)     │
                         │   4. restart: docker compose up -d --force-recreate (skip auth/cfg/admin) │
                         │   5. verify:  liveness count only — NO gate, NO rollback             │
                         └─────────────────────────────────────────────────────────────────────┘
  GPU box (10.0.0.122):  deploy/llm-proxy/docker-compose.yaml  ←  docker compose pull (manual, :dev)
```

---

## Plan / recommendations (phased)

These are the "Later (post-testing, separate efforts)" items named in `prds/testing-infrastructure.md` ("full-regression-on-main job, gated auto-deploy with post-deploy smoke + rollback"), specified here. **All of it is gated on the testing foundation** (a green check must mean something first — Phase 1 of the testing PRD).

### Phase 1 — Full-regression-on-main (the promotion gate)

Add a **post-merge `full-regression-on-main`** workflow that, after a merge to main rebuilds `:dev`, boots the full stack on the new `:dev` images (reusing the existing integration-runner / `docker-compose.ci.yaml`) and runs the **CASE suite + behavior lane**. On green it promotes `:dev → :candidate` (a new floating tag *or* the digest manifest from Phase 2). This is the missing `dev → candidate` gate. Reuse the `jarvis-integration-tests` repo and runner from `prds/testing-infrastructure.md` (Phase 2 there).

### Phase 2 — Digest-pinned platform release manifest (kills floating-tag non-reproducibility)

Have `tag-release.sh` (or a new release job) emit a **release manifest** mapping each service → resolved `ghcr.io/...@sha256:<digest>` for the tagged build, and make:
- the **admin updater** (`compose-generator.ts:243-264`) consume the manifest instead of `${JARVIS_IMAGE_TAG:-latest}`, and
- `deploy/llm-proxy/docker-compose.yaml` (`:15,42`) consume the manifest instead of `${LLM_PROXY_VERSION:-dev}`.

This makes a given platform version a single immutable, reproducible set of digests. (Pairs naturally with the `service-registry.json` `platformVersion` bump already in `tag-release.sh:102-115`.)

### Phase 3 — Gated auto-deploy with rollback

Once Phase 1 is green and Phase 2 gives an immutable manifest: a **gated auto-deploy** on green regression that either (a) SSHes to prod (`10.0.0.107`) and runs `docker compose pull && up -d` against the manifest, or (b) drives the **existing `jarvis-admin` `/update/apply` API** (which already does compose-pull-restart). Add a real **post-deploy smoke** (a CASE subset against prod, not just liveness) and **auto-rollback** to the previous digest manifest on failure — closing the gap that `verifyHealth` (`service-updater.ts:88-105`) leaves open. **Respect the prod rule** — this is the central open question below.

### Phase 4 — Extend integration triggers to all hot-path repos

Today only command-center carries `integration-trigger.yml`. Add the trigger to the other hot-path repos (llm-proxy, whisper, tts, auth, config-service) so their PRs hit the cross-service stack, not just per-repo unit CI. (Mirrors `prds/testing-infrastructure.md` T9.)

### Phase 5 — Make unit suites blocking

Remove the `--ignore`s and `|| echo` swallowing so a red unit suite fails the build (llm-proxy `test.yml:44,50`; CC `test.yml:44,48`). This is **`prds/testing-infrastructure.md` Phase 1** (T1/T2) — listed here only because promotion in Phases 1–3 is meaningless until it lands.

---

## Open questions

- **Does the no-touch-prod rule permit an automated deploy agent, or must prod deploys stay human-approved?** `jarvis/CLAUDE.md` says never write `~/.jarvis/compose` without explicit instruction. Phase 3 either needs a standing exception (a vetted deploy identity) or must keep a human in the loop (auto-prepare + one-click apply via the admin updater).
- **Self-hosted CUDA runner on `10.0.0.122` vs a pull-based job the box runs itself?** A registered self-hosted runner gives real-model GPU regression in CI but adds a persistent, network-exposed runner (the testing PRD flagged "persistent-runner state leaks"). A box-pulls-itself job (cron/queue consumer on the GPU host) avoids inbound exposure but is harder to gate a PR on.
- **Auto-deploy over SSH vs via the `jarvis-admin` update API?** SSH is simplest but bypasses admin's compose-regeneration/env-merge logic (risking drift from the wizard's source of truth); the admin `/update/apply` API already encapsulates pull+restart+verify but is SSE/superuser-interactive and intentionally excludes self-update of admin (`orchestrator.ts:71`, `install.ts:898-907`).
- **What is the canonical platform version?** Today it's the `jarvis-admin` GitHub Release tag (`update-checker.ts:3`, `tag-release.sh:102-115`) — not a per-service manifest. Phase 2's digest manifest should become canonical; decide whether it supersedes or wraps the admin-tag scheme.

---

## Risks / limitations

- **Floating tags are mutable.** `:dev`/`:latest`/`:edge` can be overwritten by the next push; two prod hosts pulling "the same version" minutes apart can get different bits. Phase 2 is the fix; until then prod state is non-reproducible.
- **Liveness-only verify masks bad deploys.** A service that boots and answers its health endpoint but mis-routes tools (the "answers the literal question" class) passes `verifyHealth` and stays live with no rollback.
- **Tag-release coverage gaps.** `tag-release.sh:19-36` omits llm-proxy, ocr-service, relay, recipes-server, and all `device-*`/`cmd-*` — those ride floating `:dev`/`:latest`/`:sha` only and are never cut a versioned release by this script.
- **`tag-release.sh` `local`-outside-function** (`:104,107`) is a likely `set -e` abort on the jarvis-admin path — [unverified] but should be fixed before relying on the script for releases.
- **GPU/multi-variant builds are disk-bound on `ubuntu-latest`** — already mitigated with prune/free-disk steps (`jarvis-llm-proxy-api/docker-build-push.yml:42-57`), but adding more variants risks OOM.
- **Single cross-repo trigger.** Only command-center PRs exercise the integration stack; a breaking change merged in llm-proxy/whisper/tts/auth has no cross-service gate at all.
- **No real-model / no-hardware CI.** Without a self-hosted GPU runner, model-quality and Pi-runtime regressions can only be caught manually on `10.0.0.122` / a dev Pi.

---

## Appendix — key file references (file:line)

**Build / publish**
- `jarvis-command-center/.github/workflows/docker-build-push.yml:3-8` (triggers), `:44-45` (QEMU), `:66-74` (dev/latest tag rules), `:80` (amd64+arm64)
- `jarvis-llm-proxy-api/.github/workflows/docker-build-push.yml:21-37` (4 GPU variants), `:42-57` (free disk), `:78-84` (variant tags), `:91` (amd64-only)
- `jarvis-whisper-api/.github/workflows/docker-build-push.yml:18-31` (3 variants), `:79-90` (tags, `onlatest`), `:22,26,30` (per-variant platforms)
- `jarvis-auth/.github/workflows/docker-build-push.yml:49-55,61` ; `jarvis-config-service/.../docker-build-push.yml:49-55,61` (common pattern)
- `jarvis-notifications/.github/workflows/docker-build-push.yml:36-40` (`:latest`+`:sha`, amd64+arm64)
- `jarvis-relay/.github/workflows/docker-build-push.yml:28-37` (`:latest`+`:sha`, amd64-only, no `platforms:`)
- `jarvis-web/.github/workflows/docker-build-push.yml:18-24` (per-arch runners), `:79` (`:latest` on default branch)
- `jarvis-recipes-server/.github/workflows/docker-build-push-amd64-only.yml.disabled:1-6,78` (disabled variant) ; `…/docker-build-push.yml:80` (active, multi-arch)
- Per-PR unit (hollow — see testing PRD): `jarvis-llm-proxy-api/.github/workflows/test.yml:3-11,44,50` ; `jarvis-command-center/.github/workflows/test.yml:44,48`

**Release / tagging**
- `scripts/tag-release.sh:19-36` (ALL_REPOS), `:69-122` (tag+push loop), `:102-115` (admin platformVersion bump — `local`-outside-function at `:104,107`)
- `scripts/pin-clients.sh:40` (client list), `:63-176` (PEP508 + Poetry pinning)
- `scripts/pull-all.sh:17-42` ; `scripts/deploy-configs.sh:11-43` / `scripts/refresh-configs.sh:11-30` (dotfiles, NOT service deploy)
- `jarvis-admin/.github/workflows/release.yml:18-35` (binaries), `:210-248` (GH Release), `:251-314` (npm), `:343-354` (docker)
- `jarvis-node-setup/.github/workflows/release.yml:24-68` (tarball), `:150-217` (per-arch by-digest), `:220-277` (manifest merge: main→`:edge`, tag→`:latest`+`:version`)
- `jarvis-installer/.github/workflows/deploy.yml:1-41` (GitHub Pages — not a service deploy)

**Prod deploy (admin updater)**
- `jarvis-admin/server/src/routes/update.ts:33-83` (`/check`, `/status`, `/apply` SSE, superuser)
- `jarvis-admin/server/src/services/update-checker.ts:3-4,28-71` (polls admin GH releases/latest; 30-min cache; semver compare)
- `jarvis-admin/server/src/services/upgrade/orchestrator.ts:33-72` (docker upgrade: compose→pull→restart→verify), `:71` (admin self-update excluded)
- `jarvis-admin/server/src/services/upgrade/service-updater.ts:28-49` (`docker compose pull`), `:51-86` (`up -d --force-recreate`, skip auth/config/admin), `:88-105` (**verify = liveness count only, no rollback**)
- `jarvis-admin/server/src/services/upgrade/compose-upgrader.ts:49-114` (regenerate compose+env+init-db, backup)
- `jarvis-admin/server/src/services/generators/compose-generator.ts:243-264` (image = `${JARVIS_IMAGE_TAG:-latest}${gpuSuffix}` — floating, no digest)
- `jarvis-admin/server/src/services/generators/env-generator.ts:127` (`JARVIS_IMAGE_TAG` = `dev` if track=dev else `latest`)
- `jarvis-admin/server/src/types/wizard.ts:48` (`releaseTrack: 'stable' | 'dev'`) ; `…/routes/install.ts:869-912` (track-change → pull + force-recreate)
- `deploy/llm-proxy/docker-compose.yaml:15,42` (`:${LLM_PROXY_VERSION:-dev}` floating tag) ; `:5-7` (manual `docker compose pull && up -d`)
- `PUSH-PLAN.md:1-162` (one-time pre-release security/history cleanup — NOT a deploy pipeline)

**Runners / cross-repo CI**
- `jarvis-command-center/.github/workflows/integration-trigger.yml:13-49` (per-PR `repository_dispatch` — only CC has this)
- `jarvis-node-setup/.github/workflows/integration-runner.yml:20-72` (receiver, `ubuntu-latest`, pulls `:dev` for rest of stack)
- All `runs-on:` resolve to GitHub-hosted (`ubuntu-latest`/`ubuntu-24.04-arm`/`macos-14`/`macos-15`/`windows-latest`); no `self-hosted` anywhere
- `HOSTS.local.md:10-11,20` (GPU box `10.0.0.122`, mac `10.0.0.103`, prod `10.0.0.107` — gitignored/local)

**Cross-references**
- `prds/testing-infrastructure.md` — hollow-CI detail, the CASE suite / integration-runner, the behavior lane, and Phase-1 "make CI honest" (prerequisite for every promotion gate here)
- `jarvis/CLAUDE.md` — prod rule: never write `~/.jarvis/compose` without explicit instruction
