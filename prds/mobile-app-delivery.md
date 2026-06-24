# PRD: Mobile App Delivery — dev-mode tracking `main` for bulk testing

**Status**: Draft — delivery findings 2026-06-20; **UI/e2e testing strategy designed + decisions locked 2026-06-22** (see Phase 2).

---

## Overview / TL;DR

`jarvis-node-mobile` (the Expo/React Native admin + provisioning app) ships every change to the App Store / Play Store via a **full native build per merge**. There is **no over-the-air (OTA) update path** — `expo-updates` is not installed, and there is no `updates`/`runtimeVersion`/`channel` configuration anywhere. So a one-character JS change costs a complete iOS local build + TestFlight submit (and an Android build + Play internal-track submit) before any tester can exercise it.

**Key correction to the working mental model:** `jarvis-node-mobile` **already builds from `main`** — its production build job is gated on `refs/heads/main` (`.github/workflows/ci.yml:58`). The *tag-based* release model (`tag v*` → production, `main` → preview) belongs to a **different app**, `jarvis-recipes-mobile` (`.github/workflows/build-and-deploy.yml:68-71`). So the real blocker is **not** "switch tags → main." It is: **there is no fast, JS-only path to bulk-test `main` without a full native TestFlight/Play build per change.**

The `EXPO_PUBLIC_DEV_MODE` flag exists but only toggles a manual node-IP entry field in the provisioning screen (`src/config/env.ts:1`, `src/screens/Provisioning/ScanForNodesScreen.tsx:25-26`). It has **nothing** to do with which code/version loads, so "dev mode tracks main" has no existing hook to attach to.

**Decision (LOCKED 2026-06-20): hosted EAS Update on a `main` channel.** Add `expo-updates`, pin `runtimeVersion`, channel-map the eas.json build profiles, and have CI publish a JS-only `eas update --branch main --channel main` on every push to `main`. Dev/internal builds bound to the `main` channel then auto-pull the latest `main` JS bundle on launch — that is "dev mode tracks main," in seconds rather than a 20-minute native build. Native-dependency changes (the `jarvis-crypto` module, app.json plugins, `ios/`/`android/`) still require a full rebuild + `runtimeVersion` bump; OTA ships JS/assets only. Estimated effort: ~half a day. (This PRD is the canonical record for the `PT-Mobile` parallel quick-win line item in `prds/testing-infrastructure.md:150-152`.)

---

## Current state (verified)

### Stack

`jarvis-node-mobile`:
- **Expo SDK 54** (`expo: ~54.0.33`, `package.json`), **React Native 0.81.5**, **React 19.1.0**.
- **EAS** build/submit via the Expo GitHub Action (`.github/workflows/ci.yml`).
- **EAS projectId** `db3e1a49-edf0-463d-bd7d-0b40d13caf83` (`app.json:94`).
- `newArchEnabled: true` (`app.json`).
- **Custom native module `modules/jarvis-crypto`** — an Expo native module implementing AES-256-GCM + Argon2id (iOS CryptoKit + a public-domain Argon2id C impl; Android `javax.crypto` `AES/GCM/NoPadding` + `org.signal:argon2`). It backs the **K2 crypto / key service** (`docs/jarvis-node-mobile-sync.md:74-99`; `modules/jarvis-crypto/expo-module.config.json`, `modules/jarvis-crypto/ios/JarvisCryptoModule.swift:9`, `modules/jarvis-crypto/index.ts:7-31`). Because of this custom native module, the app **cannot run in Expo Go** — it requires an **Expo dev client** (`expo-dev-client: ~6.0.20` in `package.json`; the `start` script is `expo start --dev-client`).

### Update path today: NO OTA

Verified absences:
- **`expo-updates` is not installed.** `node_modules/expo-updates` does not exist; only `expo-updates-interface` (a transitive peer-dep stub) appears in `package-lock.json:5826,6022-6024`. The real OTA package is absent.
- **No `updates` block, no `runtimeVersion`, no `channel`** anywhere in `app.json` or `eas.json` (grep for `updates|runtimeVersion|channel` returns nothing in either file).

Because there is no OTA layer, **every** change — including pure-JS changes — reaches testers only through a full native store build.

### CI today (`.github/workflows/ci.yml`)

Triggers: `push` to `main`, `pull_request` to `main`, and `workflow_dispatch` (`ci.yml:3-8`).

| Job | Runs on | What it does |
|---|---|---|
| `lint-and-typecheck` | `ubuntu-latest` | **Type-check only** — `npx tsc --noEmit`. Despite the job name, **no ESLint is configured/run** (no `lint` script in `package.json`, no eslint invocation in the workflow). |
| `test` | `ubuntu-latest` | `npm test -- --ci --coverage --forceExit` → Jest (`jest-expo` preset) over the **55 `*.test.ts(x)` files under `__tests__/`**. Uploads a coverage artifact. |
| `build-and-submit` (iOS) | `macos-15` | **Gated on `github.ref == 'refs/heads/main'`** (push or dispatch) (`ci.yml:58`). Runs `eas build --platform ios --profile production --local …` (a **local** EAS build on the runner) then `eas submit --platform ios --profile production …` to **TestFlight** (`ci.yml:97,104`). The submit App Store Connect app id is `ascAppId: 6760924901` (`eas.json:51`). |
| `build-and-submit-android` | `ubuntu-latest` | Same `refs/heads/main` gate (`ci.yml:113`). `eas build --platform android --profile production --local …` then `eas submit … --profile production` to the **Play Store `internal` track** (`ci.yml:144,147`; `eas.json:55`). |

**KEY CORRECTION:** `node-mobile` **already builds from `main`** (the production store builds are gated on `refs/heads/main`, not on tags). The tag-based model is `jarvis-recipes-mobile`, a *different* app: in `jarvis-recipes-mobile/.github/workflows/build-and-deploy.yml`, `refs/tags/v*` → `production` and otherwise (e.g. `main`) → `preview` (`build-and-deploy.yml:68-71`; environment selection at `:32`). (Recipes-mobile also has no OTA: it uses cloud `eas build`/`eas submit` with no `expo-updates`/`channel` either.)

### eas.json profiles (`eas.json`)

- `cli.appVersionSource: "remote"` (`eas.json` top).
- `development` — `developmentClient: true`, `distribution: "internal"`, iOS `simulator: true` (`eas.json:7-15`, `:9`).
- `development-device` — `developmentClient: true`, `distribution: "internal"`, real-device (no `simulator`) (`eas.json:16-24`, `:20`).
- `preview` — `distribution: "internal"` (`eas.json:26-32`, `:29`).
- `production` — store distribution, `autoIncrement: true`, iOS `resourceClass: m-medium`, Android `buildType: app-bundle` (`eas.json:34-49`).
- **No `channel` key on any profile** — confirming there is nothing for OTA branches to bind to today.

### DEV_MODE flag — unrelated to delivery

`DEV_MODE = process.env.EXPO_PUBLIC_DEV_MODE === 'true'` (`src/config/env.ts:1`). Its **only** consumer is `ScanForNodesScreen` (`src/screens/Provisioning/ScanForNodesScreen.tsx:11,25`). It seeds `showDevMode`, which reveals a "Developer Options" panel for manual node IP/port entry — "Connect to provisioning simulator running on another machine" (`ScanForNodesScreen.tsx:193-243`, label at `:207`, `handleConnectDevMode` at `:58`). It does **not** influence which JS/binary/version loads. So there is no existing "dev tracks main" hook.

### Testing gap

- **No Detox / Maestro / Appium / WDIO e2e** anywhere (grep + `.detoxrc`/`.maestro` file search both empty). All testing is Jest unit tests with **mocked native modules**.
- High-risk native flows — **BLE/WiFi node provisioning, onboarding/registration, and deep-link handling** — are only unit-tested with mocks (`__tests__/screens/ScanForNodesScreen.test.tsx`, `RegisterScreen.test.tsx`, `SelectNetworkScreen.test.tsx`, `ProvisioningProgressScreen.test.tsx`, `__tests__/navigation/deepLinks.test.ts`), yet ship straight to both app stores. Deep links are wired to a real associated domain (`app.json:20-21`, `applinks:docs.jarvisautomation.dev`), so the un-e2e'd path is production-facing.

---

## How it works (today's delivery flow)

```
developer merges PR → main
   │
   ▼
GitHub Actions (ci.yml, on push to main)
   ├── lint-and-typecheck  (tsc --noEmit only)   ubuntu-latest
   ├── test                (jest, 55 files)        ubuntu-latest
   │
   └── (both green) ──┬── build-and-submit (iOS)        macos-15
                      │     eas build --profile production --local
                      │     eas submit  --profile production  → TestFlight (ascAppId 6760924901)
                      │
                      └── build-and-submit-android        ubuntu-latest
                            eas build --profile production --local
                            eas submit  --profile production  → Play Store internal track

Every change — even one line of JS — pays the full native-build cost on BOTH platforms.
There is no OTA layer; testers only ever see store builds.
```

The app itself is the **admin / orchestration control plane** for Jarvis (provisioning headless Pi Zero nodes, managing node config/secrets, monitoring) — it is *not* a voice node (`docs/jarvis-node-mobile-design.md:11,19-25`). Provisioning involves the phone joining the Pi's AP-mode WiFi and talking directly to it (`docs/jarvis-node-mobile-design.md:60-69`), which is exactly the native-heavy path that is mock-only in tests.

---

## Plan / recommendations

**Decision LOCKED 2026-06-20: hosted EAS Update, `main` channel.** Roughly half a day of work.

### Phase 1 — Add the OTA layer (the locked decision)

1. **Install OTA.** `npx expo install expo-updates`. This is the package that is currently absent.
2. **Pin `runtimeVersion` explicitly** in `app.json` (a `runtimeVersion` policy such as `appVersion`, or `fingerprint`). Pin it deliberately so an OTA JS bundle can **never** load against an incompatible native binary — the runtimeVersion is the compatibility key between a JS update and the installed native app.
3. **Channel-map the eas.json profiles.** Add a `channel` to each build profile:
   - `development` / `development-device` / `preview` → channel **`main`**
   - `production` → channel **`production`**
   (No profile has a `channel` today — `eas.json` confirms.)
4. **CI publishes JS-only updates on push to `main`.** Add a CI step (on push to `main`) that runs `eas update --branch main --channel main`. This is a **JS/asset-only** publish that completes in seconds. Dev/internal builds bound to the `main` channel then **auto-pull the latest `main`** on launch = "dev mode tracks main." The heavy native store builds move to the **`production`** channel on a slower cadence.
5. **Gate native rebuilds on native-dependency changes only.** Detect changes to native-affecting paths — `modules/jarvis-crypto/**`, `app.json` `plugins`, and `ios/`/`android/` dirs — and **only then** trigger a full `eas build` **plus a `runtimeVersion` bump**. Pure-JS merges stay instant (OTA only). This keeps the expensive TestFlight/Play production build for changes that genuinely need a new binary.

**Document the limitation prominently:** native changes still require a rebuild; OTA ships **JS and assets only**, never native code. The `jarvis-crypto` module is the canonical example — any change to it is a native change and bypasses the OTA fast path.

### Phase 2 — Real UI/e2e testing: a 3-layer pyramid (designed 2026-06-22; the larger correctness investment)

**Build progress (2026-06-23):**
- **P0 ✅ MERGED** (`jarvis-node-mobile` #7) — L0 hardening: fixed the dead crypto mock (it mocked `chacha20poly1305*`; the module exports `aesGcm*`, so AEAD-path tests silently passed on `undefined`), replaced a vanity connection-failure test (it asserted the *happy* path) with real retry-exhaustion, added the load-bearing `provision()`-throws-still-success invariant + K2/token-guard/scan-failure tests, first `bluetoothApi` test.
- **P1 ✅ MERGED** — L1 flow-integration, crossing the seam no test crossed (the per-screen tests stub `useProvisioningContext`/`useAuth` → prove nothing): the full provisioning wizard against the **real** hook + real native-stack navigation, incl. the invariant proven end-to-end through the UI (`#8`); auth-bootstrap against the **real** `AuthContext` — login→token-persist→fetch-households→auto-select + a failure path (`#9`). Used `jest.mock`-the-leaves (MSW deferred per below). Native-stack renders fine in jest; the L1 harness pattern is established + reusable.
- **P2 🟡 overlay MERGED + locally validated** (`jarvis-integration-tests` #16) — `compose/ci-overlays/fake-node.yaml`. **Finding:** node-setup publishes no ghcr `:dev` image (it's the Pi runtime + the harness's pytest client) → the fake node **builds from source** (the from-source pattern; SDK wired as a buildx additional context). Smoke-validated locally: built from source → served the real `/api/v1/{info,scan-networks}` provisioning API in sim mode. **Remaining (P3 + interactive — needs the real stack/EAS/simulator):** the CI mobile-e2e lane (checkout node-setup+SDK → build → boot on the core stack → Maestro), the EAS dev-build URL injection (`EXPO_PUBLIC_DEV_MODE` + `SIMULATED_NODE_IP/PORT` + `MANUAL_CONFIG_URL` seed), the **host-LAN-IP networking** (the app's `command_center_url` must be reachable from both the simulator-on-host *and* the node container), the simulator run.
- **Pantry-browse L1: DEFERRED** (low-risk read-only browse; diminishing ROI vs P3).

---

**Reframe:** Phase 1 (OTA) makes shipping *fast*; it does nothing for *correctness*. The mobile app is the one hot-path surface with no behavior coverage, and its highest-risk flow (AP-mode node provisioning) ships to both stores validated only by mocked unit tests. This phase fixes that. It is **not** "add a Maestro tier" — it's a pyramid where the cheap layers carry the load and the device layer stays deliberately thin.

**Codebase findings that make it tractable (verified):**
1. **Provisioning is plain HTTP, no BLE.** `src/api/provisioningApi.ts` is axios over HTTP to the node's `/api/v1/{info,scan-networks,provision,provision/k2}`. The app's BLE (`src/api/bluetoothApi.ts`) is post-provisioning device management, not a provisioning transport.
2. **The app never joins the AP programmatically** — `openWiFiSettings()` deep-links the user to OS WiFi settings (iOS has no public join API). The only true native action in the flow is a *manual user step*.
3. **The fake node already exists.** `jarvis-node-setup/scripts/run_provisioning.py` + `JARVIS_SIMULATE_PROVISIONING=true` serves the byte-for-byte FastAPI app the Pi runs, backed by the in-codebase `SimulatedWiFi` driver (no hostapd/nmcli/root). Contract-pinned by `jarvis-node-setup/tests/test_provisioning/test_api.py`.
4. **Built-in test hook:** `DEV_MODE` "Simulator Mode" (`ScanForNodesScreen.tsx` `handleConnectDevMode`) collapses the two-network dance into one tap against any LAN host:port — driving the *exact same* provisioning code path, minus the WiFi switch.

**The 3 layers:**

| Layer | Proves | Tool | Runs / Gate |
|---|---|---|---|
| **L0 — unit** (exists; harden) | state machine, parsers, the `timeout==success` invariant. Fix the dead crypto mock (`jest.setup` mocks `chacha20poly1305*`; the module exports `aesGcm*`). | Jest + jest-expo + RNTL v13 (drop `react-test-renderer` — breaks on React 19) | Ubuntu, secs; every PR |
| **L1 — flow-integration** (NEW; biggest ROI) | the full wizard wired to the REAL `useProvisioning` hook, only HTTP intercepted (MSW). Crosses the screen↔hook↔api seam no current test crosses — today's screen tests mock a pass-through `ProvisioningContext` and prove nothing. | Jest + RNTL + `msw/native` | Ubuntu, secs; every PR |
| **L2 — device e2e** (NEW; thin) | real dev-client binary (real `jarvis-crypto`) driving the one-tap dev-IP provision against the dockerized fake node + the `docker-compose.ci` backend; assert node-online **via CC** (the app's Success screen reports success even on node error). Plus QR-import + config-push flows (the ONLY place real AEAD/KDF runs). | **Maestro CLI on the runner** | iOS sim (macos); nightly → gate later |

**Honest coverage ceiling (manual hardware only):** the phone joining the Pi's SoftAP, the node's real `nmcli`/`hostapd` WiFi-join with real creds, AP-drop timing, captive portal, real-radio scan. `SimulatedWiFi` stubs `connect()`/`start_ap_mode()` to always-success, so wrong-password/weak-signal/driver edge cases are invisible. A short pre-release checklist (1 Pi + 1 phone) covers these — explicitly including the **wrong-creds → node-ERROR → app-still-Success** failure case.

**Harness reuse:** extends `jarvis-integration-tests/docker-compose.ci.yaml` with ONE service — the existing `node-setup:dev` image run with `command: python scripts/run_provisioning.py` + sim env (its default CMD is `entrypoint.py`, so a command override is needed; the working dev container boots *pre-provisioned* and does NOT serve the `:8080` provisioning endpoints). Emulator/sim runs ON the host and reaches compose-published ports at `localhost:<port>` (iOS) / `10.0.2.2:<port>` (Android) — do NOT put the app on `jarvis-net`.

**Phased plan:** P0 harden L0 (~1d) → P1 L1 flow-integration in Jest/MSW (~2-3d) → P2 wire the provisioning server + URL injection into the harness (~2-3d) → P3 Maestro L2 happy-path nightly (~1-2wk incl. shakeout) → P4 promote to store-submit gate + add Android (~few d).

**Locked decisions (Alex, 2026-06-22):**
- Build **P0+P1 immediately**, P2-P3 fast-follow.
- L2 runs **self-hosted Maestro CLI on the CI runner** — NOT EAS-hosted Maestro (that runs in Expo's cloud, can't reach the docker backend, and is metered). **iOS-sim first**; add Android (works on GitHub-hosted ubuntu via KVM since Apr-2024) once stable.
- Gate: **advisory nightly → hard-gate only the provisioning happy-path** after 3 consecutive stable runs.
- **Assert node-online via CC** (not the app Success screen). **Add a small app↔node contract test** (the TS types and node Pydantic models are hand-mirrored → can drift silently; `test_api.py` only pins node-internal). Per-release **manual hardware checklist** owned by Alex.

### What does NOT change

- `node-mobile` already builds from `main` — no tag→main migration is needed (that was a recipes-mobile pattern).
- The two store-submit jobs remain the production delivery path; they just move to a slower cadence / the `production` channel while `main`-channel OTA carries the fast bulk-test loop.

---

## Open questions

Most are resolved by the locked decision; recorded here for the canonical record.

- **Hosted EAS vs self-hosted update server — DECIDED: hosted**, for the dev/test path. Note for the future: a **self-hosted EAS-protocol update server is possible** if cloud-free OTA ever becomes a hard requirement under Jarvis's "no cloud by default" core principle. The dev/test loop does not justify standing one up now, but it is the documented escape hatch.
- **Which builds track `main`** — only **dev/internal** builds (`development`, `development-device`, `preview` → `main` channel). The App Store **production** app must **not** auto-pull `main`; it stays on the `production` channel.
- **What testers must run** — testers' devices must run a **dev-client / internal build** bound to the `main` channel, **not** the TestFlight production app. The production TestFlight build is on the `production` channel and will not see `main` updates. This is a rollout/communications detail: bulk testers need an internal build installed.
- **`runtimeVersion` policy choice** — `appVersion` vs `fingerprint`. `fingerprint` auto-bumps when native deps change (tighter safety, more rebuilds); `appVersion` is simpler but relies on discipline to bump on native changes. [unverified — not yet decided in code; either is compatible with the plan above.]

---

## Risks / limitations

- **OTA ships JS/assets only — native changes still need a full rebuild + `runtimeVersion` bump.** The custom `jarvis-crypto` native module guarantees there will be native changes; those bypass the fast path. If `runtimeVersion` is not bumped on a native change, an OTA bundle could load against an incompatible binary — hence the explicit-pin requirement in Phase 1, step 2.
- **Channel/runtime misconfiguration is a footgun.** A wrong channel mapping could push `main` JS to production users, or pin a runtime that strands updates. The mapping (`development`/`preview`→`main`, `production`→`production`) and the explicit `runtimeVersion` are load-bearing.
- **The e2e gap is the larger correctness risk.** OTA makes shipping *faster*; it does nothing for *correctness*. Provisioning/onboarding/deep-link flows remain mock-only until the Maestro tier lands, and OTA could now ship a broken JS bundle to all `main`-channel testers in seconds. The e2e gate (Phase 2) is the mitigation.
- **CI `lint-and-typecheck` does not actually lint.** It only type-checks. A class of JS errors that ESLint would catch can reach an OTA bundle. Worth adding a real lint step alongside the OTA work. [unverified that this is in scope — flagged as an adjacent gap.]
- **Hosted EAS Update is a cloud dependency** for the dev/test loop, in mild tension with Jarvis's no-cloud-by-default principle. Accepted for dev/test; the self-hosted EAS-protocol server is the documented fallback (Open questions).
- **Effort estimate (~half a day)** covers Phase 1 wiring only; the Maestro e2e tier (Phase 2) is additional and unestimated here.

---

## Appendix — key file references (file:line)

**`jarvis-node-mobile` — stack:**
- `package.json` — `expo: ~54.0.33`, `react-native: 0.81.5`, `react: 19.1.0`, `expo-dev-client: ~6.0.20`, `"start": "expo start --dev-client"`, `jarvis-crypto: file:./modules/jarvis-crypto`; Jest config (`testMatch: **/__tests__/**/*.test.ts?(x)`).
- `app.json:5` (`version: 1.0.0`), `:17-18` (iOS `bundleIdentifier` / `buildNumber: 10`), `:20-21` (`associatedDomains` / `applinks`), `:54` (Android `package`), `:73-91` (`plugins`, incl. `./plugins/withJarvisAppIntents.js`, `@bacons/apple-targets`), `:94` (`projectId db3e1a49-edf0-463d-bd7d-0b40d13caf83`). **No `updates`/`runtimeVersion`/`channel` keys present.**
- `modules/jarvis-crypto/expo-module.config.json`, `modules/jarvis-crypto/index.ts:7-31` (`argon2id`/`aesGcmEncrypt`/`aesGcmDecrypt`), `modules/jarvis-crypto/ios/JarvisCryptoModule.swift:9`.
- `docs/jarvis-node-mobile-sync.md:74-99` (jarvis-crypto native module + K2 key service); `docs/jarvis-node-mobile-design.md:11,19-25,60-69` (admin/control-plane role + AP-mode provisioning).

**No-OTA evidence:**
- `node_modules/expo-updates` — **does not exist**.
- `package-lock.json:5826,6022-6024` — only `expo-updates-interface` (transitive stub), not `expo-updates`.

**CI (`.github/workflows/ci.yml`):**
- `:3-8` triggers (push/PR to `main`, `workflow_dispatch`).
- `lint-and-typecheck` job — `npx tsc --noEmit` only (no ESLint).
- `test` job — `npm test -- --ci --coverage --forceExit` (Jest, 55 `*.test.ts(x)` files under `__tests__/`).
- `:55-58` iOS `build-and-submit` job, **gated `refs/heads/main`** (`:58`); `:97` `eas build … --profile production --local`; `:104` `eas submit … --profile production` → TestFlight.
- `:110-113` Android job, gated `refs/heads/main` (`:113`); `:144` `eas build … android … --local`; `:147` `eas submit …` → Play Store.

**eas.json:**
- `cli.appVersionSource: "remote"`; `:7-15` `development` (simulator/internal), `:16-24` `development-device`, `:26-32` `preview` (`:29` `distribution: internal`), `:34-49` `production` (`autoIncrement`, store).
- `:51` `ascAppId: 6760924901`; `:55` Android `track: internal`. **No `channel` on any profile.**

**DEV_MODE (unrelated to delivery):**
- `src/config/env.ts:1` (`DEV_MODE = EXPO_PUBLIC_DEV_MODE === 'true'`).
- `src/screens/Provisioning/ScanForNodesScreen.tsx:11,25-26` (import + `showDevMode`/`devIp` state), `:58` (`handleConnectDevMode`), `:193-243` ("Developer Options" manual-IP panel, label `:207`).

**Testing gap:**
- No Detox/Maestro/Appium/WDIO config or e2e files exist.
- Mock-only native-flow tests: `__tests__/screens/ScanForNodesScreen.test.tsx`, `RegisterScreen.test.tsx`, `SelectNetworkScreen.test.tsx`, `ProvisioningProgressScreen.test.tsx`; `__tests__/navigation/deepLinks.test.ts`.

**Comparison app — `jarvis-recipes-mobile` (the tag-based one):**
- `.github/workflows/build-and-deploy.yml:32` (environment by ref), `:68-71` (`refs/tags/v*` → `production`, else → `preview`). Cloud `eas build`/`eas submit`; no `expo-updates`/`channel`.

**Cross-reference:**
- `prds/testing-infrastructure.md:127` (locked decision "Mobile dev-mode tracks `main` via hosted EAS Update (`main` channel)"), `:150-152` (the `PT-Mobile` parallel quick-win this PRD expands).
</content>
</invoke>
