# Jarvis workspace

Jarvis Automation is a private, self-hosted assistant. The current server and Go
agent live in **`jarvis-server/`**: `jarvisd` and `jarvis-agent`.

This is the **umbrella repository**, containing project docs, shared reference
material and legacy tooling. The `jarvis-*/` directories are independent Git
repositories, ignored by this repo; they are not submodules. A fresh clone of
the umbrella will not contain them.

## Start here

1. Identify the repository or worktree that owns the change. Check its
   `git status --short`, branch and `git rev-parse --show-toplevel` before editing.
   Run Git commands and checks there; the umbrella's status does not show changes
   inside ignored child repos.
2. Read that checkout's `AGENTS.md` and/or `CLAUDE.md`, plus any guidance beneath
   the directory you will edit. Many repos currently have only `CLAUDE.md`;
   read it regardless of which coding agent you are using.
3. For server or Go-agent work, start with `jarvis-server/docs/STATUS.md`, then
   the relevant plan and decisions. Read `internal/agent/CLAUDE.md` for agent work
   and `web/admin/CLAUDE.md` for the web UI, relative to that server checkout.
4. Follow [RULES.md](RULES.md) for shared development practices. Use the owning
   repo's source, manifests, scripts and CI to verify commands and behavior.
   Historical plans and the graph snapshot are context, not proof of current state.

Local `wt-*`, `.wt-*` and `.claude/worktrees/` directories may be separate
worktrees with ongoing work. Preserve unrelated changes and use the intended
checkout; do not switch, reset or clean another task's worktree.

## Current architecture

- **Server:** `jarvis-server/cmd/jarvisd`, with application modules in
  `internal/modules/` and shared infrastructure in `internal/platform/`.
  Auth, config, conversation/tool routing, logs, notifications, recipes, OCR,
  LLM, STT, TTS and admin are modules in that program. Use their existing
  Go interfaces for in-process calls.
- **Storage and transport:** SQLite, a durable database-backed job queue,
  filesystem blobs and an embedded MQTT broker. A normal jarvisd install does
  not require separate PostgreSQL, Redis, MinIO or Mosquitto services.
- **API and UI:** fresh installs use port 7700 for the API gateway, 7710 for the
  embedded web UI and 1884 for MQTT. Legacy per-module listeners are optional
  compatibility settings. Use the server's discovered URLs and configuration;
  an old port number does not imply a separate process.
- **Inference:** jarvisd manages local engines and models. Some inference runs
  in-process; engines such as llama-server and whisper-server run as supervised
  subprocesses. Remote providers are optional. Preserve local operation and
  explicit opt-in for cloud integrations.
- **Go agent:** `jarvis-server/cmd/jarvis-agent` and `internal/agent/` own desktop
  voice, computer/browser control and the Go Pi implementation. Python packages
  run through its sidecar. Check the server's Pi parity/status docs before treating
  the Go Pi implementation as a replacement for `jarvis-node-setup`.
- **Clients and extensions:** mobile remains Expo/React Native. The Python node,
  command SDK and Pantry packages remain separate projects. The server rewrite
  does not make all Python code obsolete.

## Where work belongs

Paths below are relative to this workspace when those repos are checked out.

| Work | Repository / path |
| --- | --- |
| Server behavior, APIs, storage, inference, auth, recipes, inbox | `jarvis-server/internal/modules/`, `jarvis-server/internal/platform/` |
| Web admin and browser chat | `jarvis-server/web/admin/` |
| Desktop/Go Pi agent and browser extension | `jarvis-server/internal/agent/` |
| Mobile app | `jarvis-node-mobile/` |
| Python Pi node and its package runtime | `jarvis-node-setup/` |
| Python extension interfaces and packages | `jarvis-command-sdk/`, `jarvis-cmd-*/`, `jarvis-device-*/` |
| Pantry store, web app and runner | `jarvis-pantry/`, `jarvis-pantry-web/`, `jarvis-pantry-runner/` |
| External mobile push delivery | `jarvis-notifications-relay/`; server inbox/queue lives in jarvisd |
| User documentation and installer website | `jarvis-docs/`, `jarvis-installer/` |
| Agent development pipeline | `jarvis-loop/` (private; its own workflow applies) |
| Umbrella docs, graph snapshot and legacy install tooling | This repository |

Repo names are not lifecycle guarantees: the old `jarvis-admin`,
`jarvis-command-center` and `jarvis-host-agent*` checkouts are not the current
web UI, server brain or Go desktop agent.

## Graphify code navigation

When a question spans unfamiliar files or repos, use the existing Graphify graph
to find entry points and relationships, then read the current source. Use `rg`
for exact symbols/text and to verify the graph's leads.

When `graphify` is installed and `graphify-out/graph.json` exists, run from the
umbrella root:

```bash
graphify query "desktop agent tools" --budget 1500
graphify explain "<node label or ID>"
graphify path "<source node>" "<target node>"
```

From another checkout, pass `--graph /absolute/path/to/graphify-out/graph.json`.
For ambiguous or noisy results, use a specific node ID/file path (`--seed` for
queries). Narrow truncated results rather than loading the whole graph.

The graph is a snapshot: [graph/repos.txt](graph/repos.txt) records its source
commits. Verify paths and behavior in the checkout you are changing, and treat
inferred edges as leads. If the CLI or graph is unavailable, continue with source
search. Querying an existing graph does not require a rebuild; restoration and
deliberate refreshes follow [graph/README.md](graph/README.md). Keep generation
and refreshes separate from routine code navigation.

## Development entry points

Run commands from the owning checkout after reading its setup instructions.

| Working directory | Entry point |
| --- | --- |
| `jarvis-server/` | `scripts/check` for the local change gate; `scripts/check --all` includes the full Go race suite |
| `jarvis-server/` | `scripts/sandbox up --name <task> --llm scripted --ui` for an isolated instance with the web UI and a scripted model |
| `jarvis-server/` | `scripts/e2e web` for web regression tests; see `docs/dev/e2e.md` for other lanes |
| `jarvis-server/` | `scripts/screenshots --sandbox <task>` for web UI captures |
| `jarvis-node-mobile/` | `npm test -- --ci` and `npx tsc --noEmit`; runtime checks follow its own guide |
| Python node, SDK or package repo | Its own virtualenv, dependency setup and focused pytest suite |

For Go, use the toolchain declared by the owning repo. Server builds use
`CGO_ENABLED=0`; race tests use `CGO_ENABLED=1`. Native voice assets and test
models have setup scripts documented in `jarvis-server/CLAUDE.md`.

There is no workspace-wide build or test command. Use the relevant repo's
required checks and harness; do not start the legacy stack to test jarvisd.

## Temporary files and cleanup

Cleanup is part of finishing a task, including failed or interrupted runs.

- Reuse the normal disk-backed compiler and package caches. Do not create a
  separate multi-gigabyte cache in `/tmp` for each task or worktree. For Go,
  inspect `go env GOCACHE GOTMPDIR GOMODCACHE`; the server guide has the setup.
- Put disposable files in a uniquely named directory created with `mktemp -d`.
  Track the exact paths and processes you create. Use an exit trap or the
  harness's cleanup command, and check for leftovers after an interruption.
  Large builds should use a short, disk-backed `TMPDIR`; moving scratch to
  `~/.cache` does not exempt it from cleanup.
- Before handing back, stop your task's processes and remove its temporary
  build directories, binaries, downloads and redundant logs/reports. Keep only
  evidence needed for review or debugging; report its path and why it remains.
- Remove your finished worktrees with `git worktree remove` from another
  checkout once commits are pushed and no work or review depends on them.
  Inspect untracked **and ignored** files first; never force-remove a worktree
  containing work or credentials that need preserving.
- On a space/quota error, inspect usage (`df -h`, `df -i`, and `du` on the
  relevant directories) before retrying. Free only artifacts you can establish
  belong to your finished task. Never sweep `/tmp`, prune shared caches, or
  remove another task's files merely because they look old. If ownership is
  uncertain, report the candidates instead.

## Legacy maintenance

The Python microservice server stack is retired for new installs. Root
`./jarvis`, `deploy/`, `apply_all_migrations.sh`, most root `scripts/` helpers
and `install-e2e/` describe or operate that stack. They are not jarvisd's setup
or development workflow.

Some artifacts still serve current development: for example,
`install-e2e/gpu/bench_corpus.cc.yaml` can be read by jarvis-server's
`scripts/toolbench`. Check callers before removing legacy files.

For legacy maintenance, read the specific service's instructions and the Git
history of this guide. Do not carry its FastAPI, service-discovery, shared JWT
secret or `jarvis-log-client` assumptions into new Go code.

## Operational boundaries

- Production is read-only unless the user explicitly authorizes a write.
  Use the repo's isolated harness for development and verification.
- Keep credentials, private host details and real user data out of commits,
  logs and PRs. Host values belong in the gitignored `HOSTS.local.md`;
  environment files and harness credentials remain local.
- Use task-specific sandbox names and disposable test devices. Do not stop the
  installed assistant, take over the user's desktop/emulator or interfere with
  another task's processes to make a test pass.
- Follow the owning repo's merge and release policy, including its review holds.
  Permission to merge in one repo does not transfer to another; mobile merges,
  for example, can ship builds to testers.

Keep shared architecture and routing guidance here. `CLAUDE.md` and the root
Cursor rule point to this file; keep detailed implementation rules in their
owning repo so the copies cannot drift.
