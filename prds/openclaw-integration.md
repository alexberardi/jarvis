# PRD: OpenClaw Integration

**Status**: Draft. Blocked on Phase −1 Gateway protocol spike before implementation begins.

## Overview

Integrate Jarvis with [OpenClaw](https://github.com/openclaw/openclaw) — a self-hosted personal AI agent framework — so that skills installed in a user's running OpenClaw instance become first-class Jarvis voice/mobile commands. OpenClaw owns skill discovery, installation, runtime, sandboxing, and credentialing; Jarvis becomes a thin consumer that surfaces and dispatches.

## Scope

**In scope**
- Discover tools/skills available on a user's running OpenClaw Gateway
- Expose them to the Jarvis voice LLM as commands the LLM can pick
- Dispatch invocations from the node to the user's OpenClaw Gateway
- Surface external commands in the mobile app with provenance badging

**Out of scope**
- Publishing Jarvis as a ClawHub skill (separate direction, not pursued now)
- Running our own MCP host / skill catalog inside Jarvis
- Sandboxing or vetting skills (OpenClaw's responsibility)
- Skill install / config UX inside the mobile app (use OpenClaw's own UI)

## Background

### OpenClaw

Self-hosted personal AI agent framework, Node.js/TypeScript. Key pieces:

- **Gateway** — local control plane (WebSocket on `127.0.0.1:18789` by default). Owns sessions, channel routing, tool/event dispatch.
- **Agent runtime** — multi-agent routing, model failover across providers (OpenAI, Anthropic, local).
- **Multi-channel inbox** — adapters for WhatsApp, Telegram, Slack, Discord, Signal, iMessage, and 15+ others.
- **Companion apps** — macOS menu-bar, iOS/Android apps that pair to the local Gateway.
- **Workspace layout** — `~/.openclaw/workspace/skills/<slug>/`, plus injected prompt files (`AGENTS.md`, `SOUL.md`, `TOOLS.md`).

### ClawHub

Public skill registry for OpenClaw. ~3,500+ entries, Convex backend, vector search. CLI install via `openclaw skills install <slug>`. **Every published skill is an MCP server** (Anthropic's Model Context Protocol). Skill manifest is a `SKILL.md` file with YAML frontmatter declaring `name`, `description`, `version`, and `metadata.openclaw` (env vars, required binaries, install steps).

### Why this approach (vs. running our own MCP host)

We considered embedding our own MCP host (`jarvis-mcp` rename + catalog abstraction) that would install/run skills directly. Rejected in favor of consuming the user's OpenClaw because:

- OpenClaw already owns skill discovery, install, sandbox, secrets, runtime.
- Skill catalogs (ClawHub specifically) can come and go without breaking us — we depend on OpenClaw, not on any one registry.
- We don't duplicate ~3,500 skills' worth of trust surface.
- Integration is plug-in shaped — install or don't install, like Music Assistant or Z-Wave.

References:
- https://github.com/openclaw/openclaw
- https://github.com/openclaw/clawhub
- https://docs.openclaw.ai/clawhub
- https://docs.openclaw.ai/clawhub/skill-format

## Architecture

### End-to-end voice flow

```
User: "post 'standup in 5' to the eng slack channel"
  │
  ▼
[Pi Zero node]
  ├── Whisper STT → text + speaker_id
  └── command-center request built
  │
  ▼
[command-center]
  ├── tool list assembled from node's command registry (MQTT)
  │   includes both native commands AND external (openclaw) commands
  └── LLM picks tool → command-center dispatches to node
  │
  ▼
[Pi Zero node]
  ├── command resolves to OpenClaw dispatch via shared client
  └── outbound call to OpenClaw Gateway URL (per node owner)
  │
  ▼
[User's OpenClaw Gateway @ laptop/desktop]
  ├── invokes underlying Slack skill MCP server
  └── returns result
  │
  ▼
[Pi Zero node] → TTS → audio response
```

### Component overview

**New: `jarvis-openclaw-integration` Pantry package** (lives on the node)

- 1 agent (`openclaw_discovery`) — polls the user's OpenClaw Gateway every 5 min, lists available skills/tools, emits one `IJarvisCommand` per tool.
- Shared code (`openclaw_shared/gateway_client.py`) — WebSocket/HTTP client + dispatch helper.
- Secrets:

| Key | Scope | Sensitive | Purpose |
|-----|-------|-----------|---------|
| `OPENCLAW_GATEWAY_URL` | user | no | e.g. `ws://127.0.0.1:18789` or LAN URL of owner's machine |
| `OPENCLAW_AUTH_TOKEN` | user | yes | Pairing/auth token issued by OpenClaw |
| `OPENCLAW_HOST_ALIAS` | user | no | Display label (e.g. "Alex's laptop") |

**SDK extensions (`jarvis-command-sdk`)**

- Add `IJarvisAgent.get_dynamic_commands() -> list[IJarvisCommand]`. Default returns `[]`. Existing agents unaffected.

**Node extensions (`jarvis-node-setup`)**

- `CommandDiscoveryService`:
  - `register_dynamic_commands(source: str, commands: list[IJarvisCommand])` — source-keyed dynamic registration. Replaces the prior set contributed by `source` atomically.
  - `get_command_source_info(name) -> tuple[source_type, source]` — parallel lookup table; `get_all_commands()` signature unchanged for backward compat.
  - `_rebuild_cache()` merges static + dynamic. Static wins on collision; the dynamic command gets namespaced as `{source}__{name}` and a warning is logged.
- `AgentSchedulerService`:
  - Before `agent.run()`, set `jarvis_command_sdk.context.set_current_user_id(node_owner_id)` so user-scoped secrets resolve to the node's owner.
  - After `agent.run()`, call `agent.get_dynamic_commands()` and push to discovery via `register_dynamic_commands(agent.name, …)`.
- Snapshot serializer + MQTT tool payload include `source_type` and `source` per command.

### Source typing

| `source_type` | `source` | Meaning |
|---|---|---|
| `builtin` | `None` | Shipped with jarvis-node-setup |
| `pantry` | `<package_name>` | Installed from Pantry / community |
| `external` | `<integration_name>` (e.g. `openclaw`) | Contributed at runtime by an installed agent's `get_dynamic_commands()` |

### Per-user identity

Configured per-node-owner. The user's OpenClaw URL and auth token are `scope="user"` secrets, resolved against `node.owner_user_id`. The agent scheduler sets the owner as the user context before invoking each agent run.

Multi-OpenClaw households: each household member with an OpenClaw install owns their own node(s). One OpenClaw per owner per node — no multiplexing in v1.

### Mobile UX

External commands appear in the settings snapshot grouped under their `source`, read-only (no per-command secret config — secrets are owned by the integration package as a whole). A "via OpenClaw" badge marks them in list views. Configuration is deep-linked back to OpenClaw's own UI at `127.0.0.1:18789` (or the configured gateway URL).

## Dependencies

### Node owner concept

This integration requires a `nodes.owner_user_id` field plumbed through `jarvis-auth`, provisioning, and node settings. The owner concept is useful for other features (per-user OAuth integrations, etc.) and warrants its own PRD. Planned to spec alongside this one.

## Phased plan

### Phase −1: Gateway protocol spike (blocking)

Before committing to Phase 0/1/2/3/4, prove the OpenClaw Gateway protocol supports:

1. A third-party local client can connect + authenticate (without being a companion app).
2. It can enumerate installed skills with their MCP tool schemas.
3. It can invoke one tool round-trip.

Throwaway Python script against a real local OpenClaw install. ~1 day of work. If any of the three fail, this PRD goes back to the drawing board (possible fallbacks: shell out to the `openclaw` CLI, or revert to running our own MCP host).

### Phase 0: Node owner

See separate PRD `prds/node-owner.md` (TBD). Can run in parallel with Phase 1.

### Phase 1: Core hooks

**jarvis-command-sdk**
- `IJarvisAgent.get_dynamic_commands()` → `list[IJarvisCommand]`, default `[]`

**jarvis-node-setup**
- `CommandDiscoveryService` source-keyed dynamic registration + parallel source-info lookup
- `AgentSchedulerService` owner context + dynamic command emission after each agent run
- Snapshot serializer + MQTT payload surfaces `source_type` / `source`

### Phase 2: Integration package

**jarvis-openclaw-integration** (new repo)
- Manifest, 3 secrets, 1 agent, gateway client in `openclaw_shared/`
- Discovery agent: poll Gateway, list tools, build `IJarvisCommand` instances with shared dispatcher
- Tests against a real local OpenClaw or recorded fixtures

### Phase 3: Mobile surfacing

- Group external commands under their `source` in node settings
- "via OpenClaw" badge in tool lists / settings
- Deep-link to gateway URL for management

### Phase 4: E2E + docs

- Voice round-trip happy path (post-to-Slack via OpenClaw, end-to-end)
- Mobile dashboard: connected gateway + tool count
- README in integration repo + jarvis-docs entry

## Design decisions

**1. Consume, not publish or host.** Three directions were considered: publish Jarvis as a ClawHub skill, consume ClawHub skills inside Jarvis, or become an OpenClaw "channel" (voice front-end). Consume chosen — highest user value (~3,500 tools unlocked for voice), lowest risk to our architecture.

**2. Generic via OpenClaw, not via our own MCP host.** A generic `jarvis-mcp` host with pluggable catalogs (ClawHub, npm, git, etc.) was considered. Rejected — OpenClaw already does hosting/sandboxing/install, and we get equivalent generality through their catalog without rebuilding it. If ClawHub disappears, OpenClaw's catalog story changes, our integration is unchanged.

**3. Plug-in, not infrastructure.** Built as a Pantry package, not a new service. Same shape as `jarvis-home-assistant-integration`, `jarvis-cmd-music-assistant`, `jarvis-cmd-zwave`. If OpenClaw goes away, you uninstall the package and the rest of Jarvis is unchanged.

**4. Agent emits `IJarvisCommand` instances (no separate `IDynamicToolProvider`).** Reuses existing discovery / snapshot / MQTT pipelines. Single new method on `IJarvisAgent` with safe default.

**5. Source metadata in discovery service, not on the interface.** `IJarvisCommand` stays clean of provenance concerns. The discovery service is canonical for "where did this come from" — it already distinguishes built-in / `custom_commands/` / `test_commands/` at scan time.

**6. No per-command enable/disable for external sources.** Punt — disable the integration as a whole, or remove the skill from OpenClaw. Per-command control would require extra plumbing for marginal value.

**7. Owner-of-node, not per-speaker dispatch.** Each node has a single owner whose OpenClaw config is used. Simpler than per-speaker switching, matches how personal devices work, and the owner concept is independently useful.

**8. Outbound dispatch from the node, not from command-center.** The agent and the dispatch path both live on the node. The user's Gateway is reachable from the node's LAN; routing through CC would add an extra hop with no benefit.

**9. Version compatibility via Pantry package versioning, not Gateway version pinning.** Runtime detection of "is this Gateway version compatible" is brittle. Instead, the integration package itself is versioned. If OpenClaw ships a breaking Gateway-protocol change, we ship `jarvis-openclaw-integration` v2.0 (or a parallel `jarvis-openclaw-integration-v2` if the change is invasive enough to need both available simultaneously). Users coordinate which version to install with which Gateway version, the same way they coordinate any other Pantry package upgrade.

## Known limitations / trade-offs

- **No LoRA training examples for external tools.** External commands ship with descriptions + JSON schemas, not voice examples. They go through the standard prompt path only; per-node LoRA fine-tuning doesn't benefit them. Accuracy will be measurably worse than native commands.
- **Voice latency.** Adds a network hop (node → owner's OpenClaw Gateway → skill). Need tight timeouts (~1.5s), connection pooling, graceful degrade when Gateway is offline.
- **Prompt bloat.** A user with 30+ installed skills could surface 100+ tools. Compressed prompt providers benchmark cleanly to ~80; beyond that, accuracy drops. Plan for category-based filtering or favorites surface in mobile as a follow-up.
- **Schema fidelity.** MCP tools use JSON Schema (nested objects, `oneOf`, arrays of objects). `JarvisParameter` is flat (string / int / bool / enum). Complex schemas flatten to JSON-string params and decode at dispatch — voice extraction for nested args will be shakier than for native commands.
- **OpenClaw must be installed + reachable.** A user without OpenClaw gets no external commands. Acceptable for an opt-in integration; not a default-on feature.

## Open questions

- **Gateway protocol details + auth model for a third-party local client** — both resolved by Phase −1 spike.

## Punted

- **Prompt-bloat mitigation** (category-filtering / favorites in mobile). Deferred. Users who run OpenClaw are likely also running a cloud LLM provider for Jarvis, where the prompt-size ceiling is high enough that a flat tool list of 100+ entries is acceptable. Revisit if real users hit accuracy regressions on local-model setups.
