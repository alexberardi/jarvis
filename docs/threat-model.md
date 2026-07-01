# Jarvis — Threat Model & Privacy Boundaries

> **Status: beta.** This page describes how Jarvis is designed to run today, where the
> trust boundaries are, and the sharp edges we know about. It is written for people who
> will read the code — so it names the limitations instead of hiding them. If you find a
> boundary we got wrong, please open a security advisory (see `SECURITY.md`).

Jarvis is designed to run **self-hosted on a private LAN**, behind the operator's own
reverse proxy which terminates TLS at the edge. The threat model assumes the LAN is a
trusted network segment and the operator controls what is exposed to the internet.

---

## 1. What runs locally vs. in a cloud

| Capability | Where it runs | Data that leaves your network |
|---|---|---|
| Wake word, speech-to-text (whisper.cpp) | **Local** | None |
| Text-to-speech (Piper / Kokoro) | **Local** | None |
| Orchestration, memory, tool routing | **Local** | None |
| LLM inference — **local model** (GPU / Ollama / llama.cpp) | **Local** | None |
| LLM inference — **cloud model** (optional, the no-GPU default) | Your chosen provider | **Transcripts + tool context go to that provider** |
| Pantry store (browse/install packages) | *Our* hosted service | Package queries |
| AI Forge (generate a package from a sentence) | *Our* hosted service, **your** LLM key (BYOK) | Your prompt + your provider key |
| Push notifications | *Our* relay → Apple/Google push | Notification title/body + device token |

**The honest caveat:** the easiest onboarding path (no local GPU) routes your voice
transcripts to a third-party LLM. That is a real privacy trade-off. The fully-local path
(a local GPU or a machine running Ollama) keeps *everything* on your network. Pick the
posture you want — both are first-class.

**To run with zero external dependencies:** use a local LLM, and leave the Pantry, Forge,
and push-relay features disabled (they are optional conveniences, not required for the
voice hot path). Outbound updates are **fail-closed** by default (`JARVIS_ALLOW_UPDATES=false`) —
Jarvis does not phone home unless you opt in.

---

## 2. Trust boundaries — what a compromise can reach

- **A stolen user JWT** → acts as that user until the token expires. See §3 on revocation
  latency. Refresh tokens are rotated on use, with reuse detection (see §3).
- **A compromised Pi node** (`X-API-Key: node_id:node_key`) → is **scoped per-service** in
  jarvis-auth; a node cannot act as an arbitrary user or reach services it wasn't granted.
  It can, however, see traffic on the LAN segment it sits on (see §4).
- **A malicious Pantry package** → the AI Forge / Pantry pipeline builds and tests
  submitted code in a **locked-down sandbox**: `--network=none --read-only --memory=128m`,
  and a two-job CI split so untrusted submissions never touch the package-signing key.
  Installed packages then run on your node with the node's privileges — **review what you
  install**, exactly as you would a Home Assistant custom component.

---

## 3. Authentication — known, deliberate limitations

These are honest beta limitations. They are documented here so you can decide if they fit
your threat model, not buried in code:

- **JWT validation is local (no per-request round-trip to auth).** This makes revocation
  **eventually consistent — up to ~30 minutes.** A deactivated or deleted user's *access*
  token keeps working downstream until it expires. If you need instant lockout, shorten the
  access-token lifetime.
- **Refresh-token reuse detection defaults to "reject the request," not "revoke the whole
  family."** Full family-revocation-on-reuse is opt-in (`REFRESH_TOKEN_REVOKE_FAMILY_ON_REUSE`)
  because the grace cache is currently in-process and an over-eager revoke would nuke live
  mobile sessions on a restart. Enable it if you want strict theft response and can run auth
  single-worker / Redis-backed.
- **Local username/password only.** No OAuth/OIDC, no password reset, and the logout
  endpoint is not yet wired (mobile clears tokens client-side). These are on the roadmap.

---

## 4. Network posture

- **Inter-service traffic is plaintext HTTP inside the LAN.** This is by design for the
  self-hosted, single-segment trust model — TLS is terminated at the operator's edge proxy,
  not between services on the trusted network. Do **not** expose individual service ports to
  the internet; put the reverse proxy in front.
- **Data-plane infra (Postgres, Redis, MinIO) binds to `127.0.0.1` by default** in the
  generated Compose (`JARVIS_INFRA_BIND_HOST` opts you into wider exposure).
- **MQTT (Mosquitto) is the node control plane.** On a trusted LAN this is fine; if you
  port-forward it, put it behind the authenticated tunnel path, not a raw public listener.
- Auth modes are documented in the top-level `CLAUDE.md` (User JWT / App-to-app / Node
  API-key / Admin token). App-to-app and node keys are validated against jarvis-auth.

---

## 5. Hardening checklist for a public-facing deploy

1. Terminate TLS at a reverse proxy; expose **only** the proxy, never individual service ports.
2. Use a **local LLM** if you want zero transcript egress.
3. Set strong, random secrets (services refuse to boot on placeholder/short values).
4. Keep `JARVIS_ALLOW_UPDATES=false` unless you want auto-updates.
5. Leave Pantry / Forge / push disabled if you don't need them.
6. Keep MQTT and the admin surface on the LAN / behind the tunnel — never on a public bind.
7. Only install Pantry packages you've reviewed.

---

*This document reflects the current beta. Corrections and security reports:
see [`SECURITY.md`](../SECURITY.md).*
