# PRD: Resilient package installs — a bad package must never brick a node

**Status**: Draft — written from the 2026-06-10 field incidents, pending review
**Date**: 2026-06-10
**Owner**: alex

## Problem

A Pantry install is currently a leap of faith. Three real incidents from one day of dogfooding
(email 1.0.1/1.0.2 on the dev Pi), all of which would strand a non-technical user:

1. **Version-floor violation, silent feature death.** Email 1.0.1 requires SDK 0.3.3
   (`JarvisInbox`); the node had an older SDK. Install "succeeded," then every discovery pass
   logged `cannot import name 'JarvisInbox'`, the command vanished, agents vanished, and the
   settings-snapshot flow degraded. Nothing checked any version floor: the manifest's
   `min_jarvis_version` is stored by Pantry and **never enforced anywhere**, and no
   `min_sdk_version` field exists at all. The only fix was SSH.
2. **In-process install corrupts the MQTT runtime.** The install handler re-registers the MQTT
   message handler without tearing down the old one. After install, every inbound message is
   processed N times; duplicate snapshot uploads 409; the node looks half-offline. Only a
   service restart clears it. (See memory: mqtt-duplicate-handler-after-install.)
3. **Silent disappearance instead of visible failure.** Agent discovery *hides* agents whose
   `validate_secrets()` fails — email_alerts was dead for ~2 months and nothing surfaced it.
   The user-visible difference between "not installed," "installed but broken," and
   "installed but unconfigured" is currently nothing.

Adjacent known debt that compounds the above: partial installs leave files
(CLAUDE.md failure mode), pip deps aren't refcounted on uninstall, store installs with
`git_tag: null` float on repo `main` (unpinned, unreproducible — how a "1.0.0" store entry
installed 1.0.1 code).

**Principle**: the worst legal outcome of any install is "package doesn't run, user is told
why, node keeps working, uninstall/rollback is one tap." SSH is never part of recovery.

## Design

**1. Enforce version floors at install time (cheapest, highest leverage).**
The node's install handler refuses — before touching disk — when:
- `min_jarvis_version` > node version (field already exists, already stored, just unenforced)
- `min_sdk_version` > installed `jarvis_command_sdk.__version__` (new manifest field; Pantry
  records the SDK version each submission was validated against, so Forge/validation can set
  it automatically rather than trusting authors)
Refusal is a clean, user-facing result on the mobile install flow: "Needs node update v0.1.114+
— update this node first." *Rejected*: auto-updating the node as part of package install — too
much magic in one tap; the message tells the user the one action to take.

**2. Pre-flight validation in a subprocess, then commit.**
`command_store.py validate` already exists (manifest, component paths, import-tests every
component). Make the install handler run it as a gate, in a **subprocess against the node's
real venv**, on the staged copy *before* scattering into the live directories:
download → stage → validate (imports run against the node's actual SDK — this alone would have
caught incident #1 even without floors) → only then scatter + pip install + register.
Validation failure = nothing changed on the node, full error back to mobile.

**3. Restart, don't reload.**
After a successful install (or uninstall), the node schedules a self-restart (systemd
`Restart=always` respawns it; the node already survives restarts as a design requirement).
This kills the entire class of in-process-reload corruption — incident #2's duplicate MQTT
handlers, stale module state, half-reloaded imports — for the price of ~15s of node downtime
the user just caused on purpose. The mobile install flow already shows progress; add a
"restarting node…" terminal state that resolves when the node reports back post-boot.
*Rejected*: fixing in-process reload to be perfectly clean — it's a permanent tax on every
future subsystem (each new long-lived handler must be reload-aware); restart makes correctness
structural. Keep in-process reload only for the dev `--local` path if speed matters there.

**4. Package health is a first-class, visible state.**
Discovery already catches per-component import errors; today it only logs them. Persist a
per-package health record at discovery time: `ok | failed_import(error) | unconfigured(missing
secrets)`. Surface it: (a) in the settings snapshot (same `_errors` plumbing the snapshot
already has), so the mobile package card shows a red "failed to load" / amber "needs setup"
badge instead of the component silently vanishing; (b) agents that fail `validate_secrets`
stay **listed** (disabled, with reason) rather than hidden — incident #3's two-month silence
becomes a visible amber badge. One inbox item on first transition to failed (not per-pass spam).

**5. Rollback = keep N-1.**
Before scattering a new version, move the currently-installed package files to
`~/.jarvis/packages/<name>/.previous/`. Post-install validation failure (or the post-restart
health check coming up `failed_import`) auto-restores `.previous` and reports. Mobile gets a
manual "Revert to 1.0.1" action on the package card for the cases automation can't judge.
This also finally bounds incident-class "partial install leaves files."

**6. Pin store installs.**
New Pantry submissions record the validated commit SHA + tag; the download endpoint stops
handing out `git_tag: null` (floating main). Existing 1.0.0-era rows are grandfathered until
resubmitted. (Pantry-side; small.)

## Phases

**Phase 1 — floors + pre-flight gate** (jarvis-node-setup install handler + SDK
`min_sdk_version` manifest field + Pantry records validated-SDK): kills the bricking class
observed in incident #1.
**Phase 2 — restart-after-install + install-flow terminal states** (node + CC + mobile
status): kills incident #2's class.
**Phase 3 — package health states + visible badges + list-don't-hide agents** (node snapshot +
mobile): kills incident #3's class.
**Phase 4 — staged install with `.previous` rollback + store pinning** (node + Pantry).

## Punts (explicit)

- Full sandboxing / signature verification of packages (Pantry validation + danger ratings
  remain the trust layer).
- pip dependency refcounting on uninstall (tracked separately: pip-uninstall-debt).
- Auto-update of the node as a dependency-resolution step (see decision 1).
- Multi-package transactional installs (one package at a time is fine).

## Open Questions

1. Restart-after-install on a node actively playing TTS/music: defer restart until idle, or
   restart immediately? (Lean: immediately — the user is holding the phone mid-install.)
2. Does the post-restart health check live in the node (self-report on boot) or CC (timeout
   watching for the node to report)? (Lean: node self-reports package health in its boot
   report; CC times out at 60s and marks "node didn't come back" for the install flow UI.)
3. `min_sdk_version` default for existing packages with no field: treat as 0 (always passes)
   or infer from the SDK symbols the validator saw? (Lean: 0 for back-compat; Forge/pipeline
   sets it going forward.)
