# VERIFIED FACTS — loop v2 deploy (ground truth from live Pi inspection 2026-06-23)

These supersede any conflicting detail in the staged contracts or the PRDs.
Everything here was verified by direct read-only inspection of `pi@openclaw.local`
and the session transcripts (40k+ real tool calls), the live `openclaw.json`, and
the `/home/pi/code/jarvis/` mirror. **If a staged contract disagrees with this file, this file wins.**

## OpenClaw MCP tool names (EXACT — these are what actually work)

**`github-rw`** (roadmap PAT, scoped to `alexberardi/jarvis-roadmap`):
- `mcp__github-rw__list_issues` — list/filter by labels/state
- `mcp__github-rw__issue_read` (method `get`) — read an issue (replaces the removed `get_issue`)
- `mcp__github-rw__issue_read` (method `get_comments`) — read a comment thread (replaces the removed `list_issue_comments` / `get_issue_comments` — those discrete tools DO NOT exist on 1.0.4)
- `mcp__github-rw__issue_read` (method `get_labels`) — **READ an issue's current labels** (required before any label edit — see below)
- `mcp__github-rw__add_issue_comment` — post a comment
- `mcp__github-rw__issue_write` (method `create`) — **create an issue** (engineering only; human-gated unrelated-split path). 1.0.4 has NO discrete `create_issue` tool — creation is `issue_write` method `create` (pass `title`, `body`, `labels:[...]`).
- `mcp__github-rw__issue_write` (method `update`) — **the ONLY label/state writer.** github-mcp-server 1.0.4 has NO discrete label tools. Labels + close go through `mcp__github-rw__issue_write` (method `update`; **labels = FULL-SET REPLACE — read-modify-write required**). Read labels via `mcp__github-rw__issue_read` (method `get_labels`). Also closes/sets state (`state=closed`, `state_reason=not_planned`) in the same `update` call.
- `mcp__github-rw__search_issues` — targeted search

> **CORRECTION 2026-06-23:** the live server is github-mcp-server v1.0.4 (consolidated). The historical transcripts showed `add_labels_to_issue`/`remove_label_from_issue` from an OLDER binary; those tools no longer exist. Verified via `tools/list` on the live server.

**`github-code`** (coding PAT, scoped to public `alexberardi/jarvis-*` code repos; CANNOT see private roadmap):
- `mcp__github-code__create_pull_request` — open a PR (supports `draft: true`)
- `mcp__github-code__list_pull_requests` — list (idempotency guard before create)
- `mcp__github-code__pull_request_read` — the consolidated PR reader (replaces the removed `get_pull_request*` discrete tools). **`method ∈ [get, get_diff, get_status, get_files, get_review_comments, get_reviews, get_comments, get_check_runs]`** — `get` = PR object; `get_diff` = unified diff; `get_files` = changed-file list; `get_status`/`get_check_runs` = CI/mergeability; `get_reviews`/`get_review_comments`/`get_comments` = review + comment threads.
- `mcp__github-code__issue_read` (method `get_comments`) — read PR comments (PRs share comment storage)
- `mcp__github-code__add_issue_comment` — comment on a PR
- `mcp__github-code__search_issues`, `mcp__github-code__list_issues`
- EXISTS but coding-agent MUST NOT use: `merge_pull_request`, `update_pull_request`, `push_files`, `create_or_update_file`, `delete_file` (use git CLI; deny these in tools)

**`github-code-ro`** (read-only service code): `mcp__github-code-ro__get_file_contents` etc. (qa-author/install-expert read service code via this or the local mirror)

**builtin**: `read`, `write`, `edit`, `exec` (all lowercase). `apply_patch` is NOT confirmed present — prefer `edit`/`write`; mention `apply_patch` only as optional.
**messaging**: `mcp__openclaw__message` (channel + `text`) — every persona ends a reportable run with this.

## github-mcp-server 1.0.4 migration map (AUTHORITATIVE — verified via `tools/list` on the live Pi 2026-06-23)

OpenClaw runs **github-mcp-server v1.0.4 (consolidated)**. It exposes ONLY the consolidated, methods-bearing tools below. The older discrete tools **DO NOT EXIST** — confirmed: a direct call / `ToolSearch` for them returns *"No matching deferred tools found"*. Every contract reference MUST use the right-hand column.

| REMOVED (pre-1.0.4 discrete tool) | USE INSTEAD (1.0.4 consolidated) |
|---|---|
| `create_issue` | `mcp__github-rw__issue_write` (method `create`; pass `title`, `body`, `labels:[...]`) |
| `add_labels_to_issue` / `remove_label_from_issue` / `remove_label` | `mcp__github-rw__issue_write` (method `update`, `labels` = **FULL REPLACEMENT set**). FIRST read current labels via `mcp__github-rw__issue_read` (method `get_labels`); compute current ± the change; write the COMPLETE merged set. **NEVER a partial `labels` list** — any label omitted is DROPPED. |
| `update_issue` / `close` | `mcp__github-rw__issue_write` (method `update`; `state="closed"`, `state_reason="not_planned"`; **OMIT `labels`** to leave them unchanged) |
| `get_issue` | `mcp__github-rw__issue_read` (method `get`) |
| `list_issue_comments` / `get_issue_comments` | `mcp__github-rw__issue_read` (method `get_comments`)  — use `mcp__github-code__issue_read` (method `get_comments`) for PR comment threads (PRs share comment storage) |
| `get_pull_request` | `mcp__github-code__pull_request_read` (method `get`) |
| `get_pull_request_diff` | `mcp__github-code__pull_request_read` (method `get_diff`) |
| `list_pull_request_files` | `mcp__github-code__pull_request_read` (method `get_files`) |
| `get_pull_request_comments` | `mcp__github-code__pull_request_read` (method `get_comments`) |
| `get_pull_request_reviews` / `get_pull_request_status` | `mcp__github-code__pull_request_read` (method `get_reviews` / `get_status`) |

**UNCHANGED (still exist on 1.0.4 — keep verbatim):** `list_issues`, `search_issues`, `add_issue_comment`, `issue_read` (methods `get`/`get_comments`/`get_labels`), `issue_write` (methods `create`/`update`), `pull_request_read` (methods `get`/`get_diff`/`get_status`/`get_files`/`get_review_comments`/`get_reviews`/`get_comments`/`get_check_runs`), `create_pull_request`, `list_pull_requests`, `merge_pull_request`, `update_pull_request`, `get_file_contents`, `list_commits`, `create_or_update_file`, `push_files`, `search_code`.

**DEFERRED-TOOL NOTE.** OpenClaw keeps less-common tools **"deferred"** — their schemas aren't loaded, so a direct call to a deferred tool fails with `InputValidationError`. The common ones (`list_issues`, `issue_read`, `add_issue_comment`, `issue_write`, `pull_request_read`, `create_pull_request`, `list_pull_requests`) are **ACTIVE** and immediately callable. If a contract references any other tool and it is not immediately callable, load its schema first with **`ToolSearch` (`select:<exact tool name>`)** before calling it. Never reference a removed discrete tool from the left column above — it cannot be loaded (`No matching deferred tools found`).

## Slack channel IDs (single source)

| Persona | Channel | ID |
|---|---|---|
| engineering | #engineering-bot | `C0B4C4XJ9L1` |
| qa | #qa-bot | `C0B3WKBPSJ3` |
| coding-agent | #coding-bot | `C0B4C0W5WHY` |
| qa-author | #qa-author-bot | `C0BC7FK5GAH` |
| qa-executor | #qa-executor-bot | `C0B4DQL8SF4` |
| product | #product-bot | `C0B4C3YBTC1` |
| install-expert | #install-bot | `C0B5QHC4G4B` |
| marketing | #marketing-bot | `C0B53CS62RE` |
| doc-expert | #docs-bot | `C0B60GS5HHS` |

## Kill switches (per persona)

Each runnable persona checks for a disable file FIRST and exits if present:
`~/.openclaw/<persona>.disabled` → output `<persona> disabled by kill switch.` and STOP.
Personas: `engineering.disabled`, `qa.disabled`, `coding-agent.disabled`, `qa-author.disabled`, `install-expert.disabled`, `qa-executor.disabled`.

## Local code mirror (read-only, on the Pi)

- Root: `/home/pi/code/jarvis/<repo>` — all 50 `jarvis-*` repos cloned. Read with `read`.
- CASE catalog: `/home/pi/code/jarvis/jarvis-integration-tests/tests/CASE_CATALOG.json`
  - Structure: `{"_meta": {...}, "cases": {"CASE-001": {"intent","lane","mode","repo","gating","test"}, ...}}` (35 cases as of deploy).
  - `mode ∈ {fast, always, composition, routing}`. QA lists `always` + `composition` integration_cases; NEVER `routing` (CASE-402 — lane-derived).
- Resolver: `/home/pi/code/jarvis/jarvis-integration-tests/tools/resolve_cross_repo.py` — `KNOWN` map confirms:
  - `jarvis-llm-proxy-api`: always=[CASE-301,303,304], composition=[CASE-302]
  - `jarvis-whisper-api`: always=[CASE-321]
  - `jarvis-tts`: always=[CASE-311]
  - `jarvis-auth`/`jarvis-config-service`/`jarvis-command-center`: no standalone always-case
  - union ≥2 of the six → add `CASE-401` (composition); routing mode → always + `CASE-402`, drops 302/401.
- **Mirror refresh:** a `jarvis-mirror-refresh` timer (added in this deploy) `git pull --ff-only`s the mirror at 05:00 daily, just before the pipeline. Agents can assume the mirror is current as of that morning.

## The six-repo cross-repo vocabulary (HARD limit)

`jarvis-auth · jarvis-config-service · jarvis-command-center · jarvis-llm-proxy-api · jarvis-whisper-api · jarvis-tts`
Any other repo (sdk, node-setup, cmd-*, device-*, …) → `lane: "fast-lane-only"` (no cross-repo CASE, no `Linked-PR:` marker).

## Secrets / env available in runner services

Runner units load `EnvironmentFile=~/.openclaw/secrets/github.env` (`GITHUB_PERSONAL_ACCESS_TOKEN` = roadmap PAT) + `coding.env` (`CODING_GITHUB_PAT` = code PAT).
- `github-rw`/`github-ro` MCP inherit `GITHUB_PERSONAL_ACCESS_TOKEN` (roadmap).
- `github-code`/`github-code-ro` MCP are configured with `GITHUB_PERSONAL_ACCESS_TOKEN=${CODING_GITHUB_PAT}`.
- coding-agent's `git clone`/`push` use `https://x-access-token:${CODING_GITHUB_PAT}@github.com/alexberardi/<repo>.git` (the coding PAT is in the exec env).

## Runtime

- Host: `pi@openclaw.local` (Pi 5, aarch64). OpenClaw 2026.5.12. `claude` CLI 2.1.187 at `/home/pi/.local/bin/claude` (on the systemd PATH). Gateway active.
- Models route via `agentRuntime: {id: claude-cli}` → bills the Claude Max baseline (~$0 marginal). engineering/qa/coding-agent/qa-author pin `anthropic/claude-opus-4-7`; survivors pin `anthropic/claude-sonnet-4-6`.
- Schedule (daily, staggered — "daily NOT hourly", the #42 runaway lesson): mirror-refresh 05:00 → engineering 05:10 → qa 05:30 → coding-agent 05:50. qa-executor hourly :05. qa-author temp-hourly :55 (WIP=1 gated).
- Agent registration in `~/.openclaw/openclaw.json`: each agent in `agents.list` has `{id, name, workspace, agentDir, model, systemPromptOverride, tools}`. `agentDir` = `/home/pi/.openclaw/agents/<id>/agent`. `workspace` = `/home/pi/.openclaw/workspaces/<id>`. Slack route in `bindings`.
- Runner service ExecStart pattern (fresh session per run):
  `/usr/bin/openclaw agent --agent <id> --session-id "cron-$(date +%Y%m%d-%H%M%S)" --message "$(cat ~/.openclaw/<persona>-prompt.md)" --timeout <sec>`

## Tools profile per agent (openclaw.json `tools`)

> **Label-tool note (github-mcp-server 1.0.4):** there are NO discrete `add_labels_to_issue`/`remove_label_from_issue`/`remove_label` tools. Engineering does ALL label work (and close) via `github-rw__issue_write` (method `update`, full-set REPLACE — read current labels with `issue_read` method `get_labels` first, then write the merged set). qa / coding-agent / qa-executor are barred from label/state writes by denying **`github-rw__issue_write`** — the deny of the now-nonexistent `add_labels_to_issue`/`remove_label_from_issue`/`remove_label` tools below is harmless/no-op (kept only for belt-and-suspenders against an older binary).

- **engineering** (read-only code; OWNS all roadmap labels via `issue_write` full-set REPLACE): `{profile:"full", deny:["group:runtime","write","edit","apply_patch","github-ro__*","github-code__*","github-code-ro__*"]}` → keeps `read` + full `github-rw` (incl. `issue_write` for labels+close) + `message`.
- **qa** (read-only on tracker metadata; NO labels/create/close): `{profile:"full", deny:["group:runtime","write","edit","apply_patch","github-ro__*","github-code__*","github-code-ro__*","github-rw__create_issue","github-rw__issue_write","github-rw__add_labels_to_issue","github-rw__remove_label_from_issue","github-rw__remove_label"]}` → `read` + github-rw `{list_issues,issue_read(get/get_comments/get_labels),add_issue_comment,search_issues}` + `message` (comment threads via `issue_read` method `get_comments` — the removed `list_issue_comments` is NOT callable on 1.0.4). (The `issue_write` deny is what bars labels/close; the discrete-label denies are no-ops on 1.0.4.)
- **coding-agent** (only write+exec persona on code repos): `{profile:"full", deny:["github-ro__*","github-code-ro__*","github-rw__create_issue","github-rw__issue_write","github-rw__add_labels_to_issue","github-rw__remove_label_from_issue","github-rw__remove_label","github-code__merge_pull_request","github-code__update_pull_request","github-code__push_files","github-code__create_or_update_file","github-code__delete_file"]}` → read/write/edit/exec (git) + github-rw `{list_issues,issue_read,add_issue_comment}` + github-code `{create_pull_request,list_pull_requests,pull_request_read}` + `message`. (The `issue_write` deny is what bars labels/close; the discrete-label denies are no-ops on 1.0.4.)
- **qa-executor** (mirror CI→roadmap; comments only, NO labels): `{profile:"full", deny:["group:runtime","write","edit","apply_patch","github-ro__*","github-rw__create_issue","github-rw__issue_write","github-rw__add_labels_to_issue","github-rw__remove_label_from_issue","github-rw__remove_label"]}` → `read` + github-rw `{list_issues,issue_read,add_issue_comment,search_issues}` + github-code read `{issue_read,pull_request_read,list_pull_requests,search_issues}` + `message`. (The `issue_write` deny is what bars labels/close; the discrete-label denies are no-ops on 1.0.4.)
- **qa-author** (unchanged — Alex's design): `{profile:"full", deny:["github-rw__*","github-ro__*"]}`.
- **install-expert** (unchanged toolset; v2 prompt redesign only): `{profile:"full", deny:["group:runtime","write","edit","apply_patch","github-ro__*"]}`.

## v2 loop topology (DECIDED by Alex 2026-06-23)

product (files `status:proposed`) → engineering (triage: breakdown + `## Branch set` + `feature-state:v1` + ready-gate; OWNS labels) → **qa** (per-feature `qa-test-plan:v1` comment; references catalog CASES; coverage-gap=BLOCK) + **qa-author** (continuously authors the real CASES into the harness — resolves coverage-gap parks) → Alex sets `status:locked` → engineering sets `status:ready-for-code` → coding-agent (TDD per-repo; N linked draft PRs with `Linked-PR:` markers) → cross-repo CI lane → qa-executor (mirrors `cross-repo-test-results:v1` onto the umbrella) → Alex group-merges. Merge stays HUMAN-ONLY (R2).
