---
name: jarvis-dev-env
description: Switch the Jarvis stack between local and remote (Mac) control planes, and wire an Android emulator up to a source stack. Use when asked to point services at a different host, switch env profiles, run the mobile app against the local stack, set up or recover the Android emulator, or when the app cannot reach the backend / discovery is failing.
---

# Jarvis local dev environment

Two helpers in `scripts/`, plus the gotchas that make them necessary. Both are
idempotent and safe to re-run.

## Switching control planes — `./scripts/jarvis-profile`

A box can run the GPU services locally (for CUDA) while Postgres, Redis and
config-service live on another host. Three services can point either way:
`jarvis-llm-proxy-api`, `jarvis-tts`, `jarvis-whisper-api`.

```bash
./scripts/jarvis-profile status    # which profile each service is on
./scripts/jarvis-profile local     # this machine's own stack
./scripts/jarvis-profile mac       # the remote stack
```

**After switching you MUST recreate the containers**, not restart them —
`docker compose restart` does not re-read `env_file`:

```bash
./jarvis restart jarvis-llm-proxy-api jarvis-tts jarvis-whisper-api
```

Notes:
- `status` reports `modified` when a service's `.env` matches neither profile
  (someone hand-edited it). Save it first — `cp <svc>/.env <svc>/.env.<profile>`
  — or the switch refuses. `FORCE=true` overrides.
- `.env.mac` / `.env.local` contain real tokens and DB passwords. They are
  gitignored in all three service repos; never commit them or paste their
  contents.
- After `./jarvis init`, re-sync the profile snapshots if init re-stamped
  values: `cp <svc>/.env <svc>/.env.local`.

## Android emulator — `./scripts/android-reverse`

```bash
$ANDROID_HOME/emulator/emulator -avd <avd> -gpu host &   # boot the emulator
./scripts/android-reverse                                 # then map the ports
```

```bash
./scripts/android-reverse --list     # show current tunnels
./scripts/android-reverse --clear    # remove them
./scripts/android-reverse <serial>   # target a specific device
```

**Re-run it after every emulator or adb restart** — `adb reverse` tunnels do not
survive either. If the app suddenly cannot reach the backend, check this first.

### Why reverse tunnels rather than `10.0.2.2`

`jarvis-config-service` returns *absolute* URLs for every other service, and for
an off-docker client those come back as `localhost:<port>`. Inside the emulator
that is the emulator's own loopback. `adb reverse` makes the emulator's
`localhost:<port>` reach this host, so every discovered URL resolves correctly
without rewriting anything the config service returns.

### Emulator limitations to expect

- **mDNS discovery does not work.** The emulator is NAT'd, so
  `react-native-zeroconf` cannot see `_jarvis-config._tcp`. Set
  `EXPO_PUBLIC_MANUAL_CONFIG_URL` in `jarvis-node-mobile/.env` — the documented
  escape hatch in `src/config/env.ts` — rather than relying on discovery.
- **Node QR provisioning needs a physical device** (camera + a real Pi in AP mode).
- **Android push tokens will not mint** — there is no `googleServicesFile` in
  `app.json`. Local/scheduled notifications still work.
- Use a `google_apis` system image so Play services is present.

### Running the app

```bash
cd jarvis-node-mobile
npx expo start --dev-client          # Metro; survives emulator restarts
```

The app needs a **dev build**, not Expo Go — it has a local native module
(`modules/jarvis-crypto`) and `react-native-zeroconf`. Build with
`npx expo run:android` (CNG prebuild; there is no committed `android/`).
Node is pinned to 22 via `mise.toml`; newer Node breaks Metro on SDK 54.

## Quick triage

| symptom | check |
|---|---|
| app can't reach backend after emulator restart | re-run `./scripts/android-reverse` |
| service talking to the wrong host | `./scripts/jarvis-profile status` |
| profile switched but behaviour unchanged | containers not recreated — `./jarvis restart <svc>` |
| `status` says `modified` | `.env` hand-edited; save it to a profile first |
