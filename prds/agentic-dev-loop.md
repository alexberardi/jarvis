# PRD: The Agentic Dev Loop (autonomous ticket→code→QA pipeline)

**Status**: Draft — findings captured 2026-06-20. The loop is **PAUSED** (three core agents removed 2026-05-19). This document is the canonical record so the architecture can be revived without re-research.

> Companion doc: the testing foundation this loop depends on is specced separately in [`prds/testing-infrastructure.md`](testing-infrastructure.md). That PRD owns CI honesty, the cross-service harness, the behavior lane, and the automerge/regression tail. **This PRD owns the loop mechanics** (agents, sentinels, webhooks, scheduling, the unit-of-work fix). Cross-references, not duplication.

---

## Overview / TL;DR

A multi-persona autonomous coding pipeline ran on a Raspberry Pi 5 (`openclaw.local`) from mid-May 2026, driving GitHub Issues in the private `alexberardi/jarvis-roadmap` repo through a fixed sentinel-comment protocol:

```
product → engineering breakdown → qa test-plan → coding-agent draft PR → integration-runner → qa-executor report
```

Models route through the local `claude` CLI (`agentRuntime: claude-cli`) so they bill against the **Claude Max subscription baseline (~$0 marginal)**, not API credits. Agents run as hourly **systemd `--user` timers**; GitHub events also drive them in real time via a Cloudflare-tunnelled webhook receiver.

On **2026-05-19** the three core dev-loop agents — `coding-agent`, `engineering`, `qa` — were removed (prompts, workspaces, and systemd units). Survivors (`product`, `qa-executor`, `doc-expert`, `install-expert`, `marketing`) still run. The loop is paused; reviving it is gated on the testing foundation and on a fix to the **atomic unit of work**.

**Root cause of the pause (Alex's words, 2026-06-20):** the atomic unit of work was a *single-repo PR*, but real Jarvis features are *cross-repo*. The coding-agent hard-**aborts** on cross-repo work, and triage **splits** oversized/cross-repo tickets into N children — so a coherent feature mechanically fragmented (drift) and recursively split (2–3 issues became 30). The revival design makes the unit of work a **feature spanning N repos** (a coordinated branch set merged as a group), validated by cross-service integration tests.

---

## Current state (verified)

### Host

| Property | Value | Source |
|---|---|---|
| Host | `openclaw.local` = `pi@openclaw.local` = `10.0.0.245` | given; SSH confirmed |
| Hardware | Raspberry Pi 5, 8 GB RAM (`7.9Gi` total, `6.3Gi` available), ~100 GB free (`/dev/mmcblk0p2 117G ... 100G avail`), `aarch64` | `uname -m`, `free -h`, `df -h ~` |
| Node | v24.15.0 | `node --version` |
| OpenClaw | 2026.5.12 (`f066dd2`), gateway `active` | `openclaw --version`, `systemctl --user is-active openclaw-gateway` |
| Gateway service | `openclaw-gateway.service` (systemd `--user`) | `systemctl --user list-units` |

> **Note:** `claude` is on `$PATH` for interactive shells but not for non-login SSH (`bash: claude: command not found` over `ssh ... 'claude --version'`). The systemd runner units set an explicit `PATH=/usr/bin:/home/pi/.local/bin:/usr/local/bin:/bin`, so the cron path differs from a bare SSH command. [The setup doc claims CLI 2.1.143; runtime version unconfirmable headless — [unverified].]

### Claude Max billing path (the ~$0 marginal trick)

Full how-to lives on the Pi at `~/openclaw-claude-max-setup.md`. The core mechanism, verified in `~/.openclaw/openclaw.json`:

- `agents.defaults.model.primary` = `anthropic/claude-opus-4-7`.
- `agents.defaults.models.<model>.agentRuntime = {"id": "claude-cli"}` for every Anthropic model (opus-4-7/4-6/4-5, sonnet-4-6/4-5, haiku-4-5).
- The five surviving agents pin `model: anthropic/claude-sonnet-4-6` (cheaper than opus default).

**Why this matters (per the setup doc):** Anthropic bills Max two ways. First-party `claude` CLI traffic consumes the **Max subscription baseline** (the weekly quota you pay $20/$100/$200/mo for). Third-party tools using an OAuth-minted token consume the separate pay-as-you-go **"extra usage" pool** most Max users don't fund. OpenClaw's onboarding "Claude CLI" auth option mints an OAuth token and calls `api.anthropic.com` directly — the *wrong* path (bills extra-usage). The *right* path is the model-scoped `agentRuntime: {id: "claude-cli"}` config, which invokes the local `claude` binary as a subprocess per turn → bills the Max baseline. Verify with `journalctl --user -u openclaw-gateway | grep cli-backend` showing `provider=claude-cli`.

Documented footguns from the setup doc (revival-relevant):
- Do **not** put `agentRuntime` at `agents.defaults.agentRuntime` (legacy, silently ignored) or use runtime IDs `acp`/`acpx` (throw "harness not registered").
- Do **not** set `plugins.allow` to silence the doctor warning — it's an *exclusive* whitelist and will drop ~65 plugins to 2, breaking `claude-cli` (a bundled plugin).
- First message after a fresh agent/workspace is slow (15–30 s warmup on this hardware).

### Inbound triggers

**(1) Slack** — one channel per persona, routed via `bindings` in `openclaw.json` (`type: route`, `agentId`, channel id). Verified channel ids:

| Persona | Bot channel | Notes |
|---|---|---|
| product | `C0B4C3YBTC1` (#product-bot) | |
| qa-executor | `C0B4DQL8SF4` (#qa-executor-bot) | qa-executor *posts* to this id |
| marketing | `C0B53CS62RE` (#marketing-bot) | |
| doc-expert | `C0B60GS5HHS` (#docs-bot) | |
| install-expert | `C0B5QHC4G4B` (#install-bot) | |
| qa (removed) | posts to `C0B3WKBPSJ3` | from `qa-prompt.md` |
| engineering (removed) | `C0B4C4XJ9L1` (#engineering-bot) | from `triage-prompt.md` |
| coding-agent (removed) | `C0B4C0W5WHY` (#coding-bot) | from `coding-prompt.md` |

`commands.ownerAllowFrom = ["slack:U0B45958CCW"]` (Alex's Slack user; ad-hoc agent invocation gate).

**(2) GitHub webhooks** — Cloudflare Tunnel `https://openclaw.jarvisautomation.dev/webhook` → `~/jarvis-webhook-receiver/main.py` (FastAPI on `127.0.0.1:8088`, systemd `jarvis-webhook-receiver.service`, `active`). HMAC-verified against `WEBHOOK_SECRET` (loaded from `~/.openclaw/secrets/webhook.env`) using `hmac.compare_digest` on `X-Hub-Signature-256` (`main.py:67-72`). Two dispatch routes (`main.py:dispatch`):

| Route | Match | Persona invoked |
|---|---|---|
| 1 | `event=issues`, `action=labeled`, `label.name == status:accepted`, repo `alexberardi/jarvis-roadmap` (`main.py:108-117`) | `qa` |
| 2 | `event=issue_comment`, `action=created`, body `lstrip().startswith("🤖 Pushed")`, repo `jarvis-roadmap` (`main.py:139-152`) | `qa-executor` |

`invoke_persona()` (`main.py:181-211`) fire-and-forgets `openclaw agent --agent <p> --session-id wh-<ts>-<delivery8> --message <...> --timeout 900` via `asyncio.create_subprocess_exec` with stdout/stderr to `DEVNULL`. GitHub gets an immediate 200; the agent runs detached.

> The webhook receiver header comment still says "Phase 1 wires only one route," but Route 2 (qa-executor) is in fact present and live (`main.py:139-152`).

### Scheduling — systemd `--user` timers (NOT cron)

There is **no crontab** (`crontab -l` → "no crontab for pi"). Each persona is a `<persona>-runner.timer` → `<persona>-runner.service` pair in `~/.config/systemd/user/`. Verified `systemctl --user list-timers`: **5 active timers** — `product`, `install-expert`, `marketing`, `qa-executor`, `doc-expert`. Staggered minutes (e.g. qa-executor `OnCalendar=*-*-* *:05:00`, `RandomizedDelaySec=30`, `Persistent=true`).

Service shape (from `qa-executor-runner.service`):
```ini
[Service]
Type=oneshot
Environment=HOME=/home/pi
Environment=PATH=/usr/bin:/home/pi/.local/bin:/usr/local/bin:/bin
EnvironmentFile=/home/pi/.openclaw/secrets/github.env
EnvironmentFile=/home/pi/.openclaw/secrets/coding.env
TimeoutStartSec=900
ExecStart=/bin/bash -c '/usr/bin/openclaw agent --agent qa-executor \
  --session-id "cron-$(date +%Y%m%d-%H%M%S)" \
  --message "$(cat /home/pi/.openclaw/qa-executor-prompt.md)" --timeout 600'
```

Each run is a **fresh session** (`--session-id cron-<timestamp>`); the prompt is read from `~/.openclaw/<persona>-prompt.md` at invoke time. The runner timers for the three removed agents (`coding-agent`, `engineering`, `qa`) **no longer exist** in `~/.config/systemd/user/` — removal extended to systemd units, not just prompt files.

### Removed agents (the pause) — verified

| Artifact | State | Evidence |
|---|---|---|
| Prompts | `coding-prompt.md` / `qa-prompt.md` / `triage-prompt.md` all `.removed-2026-05-19`, mode `600` | `ls ~/.openclaw/*prompt*` |
| Workspaces | `coding-agent` / `engineering` / `qa` dirs all `.removed-2026-05-19` | `ls ~/.openclaw/workspaces` |
| Systemd units | no `coding-agent`/`engineering`/`qa` runner timer/service files remain | `ls ~/.config/systemd/user/` |
| Config backup | `~/.openclaw/openclaw.json.bak-pre-3agent-removal` (45 KB vs current 28 KB) | `ls ~/.openclaw/` |
| `agents.list` | only `main`, `marketing`, `product`, `qa-executor`, `doc-expert`, `install-expert` (6) | `openclaw.json` |

> **Subtlety:** the `~/.openclaw/agents/` directory still contains *subdirectories* named `coding-agent/`, `engineering/`, `qa/` (not renamed). Only the prompts, workspaces, systemd units, and `agents.list` entries were removed. Restoring the agents means un-renaming prompts + workspaces, re-adding `agents.list` entries, re-installing the timer units, and refreshing PATs.

### Survivors (still live)

- **product** — `needs:product` interrupts ONLY. EARLY-EXIT token saver: first tool call is `list_issues labels=["needs:product"]`; empty → print `No needs:product interrupts.` and stop. No periodic/proactive work. (`product-prompt.md`)
- **qa-executor** — hourly; reads `<!-- integration-test-results:v1 -->` from the code PR, posts `<!-- qa-execution-report:v1 -->` on the roadmap issue. EARLY-EXIT (checks `needs:qa-executor` then `status:accepted`; both empty → stop). **Currently starved** — its only input is a `🤖 Pushed` PR from coding-agent, which no longer runs. (`qa-executor-prompt.md`)
- **doc-expert**, **install-expert**, **marketing** — peripheral; not part of the core build loop.
- **install-expert** — hourly; scans recently-updated `alexberardi/jarvis-*` PRs for "install drift" (config/env added to a service but not mirrored in `jarvis-admin`/`jarvis-installer`); files `type:risk service:install-pattern` roadmap issues. (`install-expert-prompt.md`)

### Ticket DB — `alexberardi/jarvis-roadmap`

Pure **GitHub-Issues database**. File tree is empty — no README, no issue templates. Bot actors: GitHub accounts `jarvis-automation-agent` (the personas) and `alexberardi` (the human). Verified via `gh issue list ... --state all` (issues #18–#47 present) and `gh label list`.

**Label taxonomy (verified `gh label list`):**
- Lifecycle: `status:proposed` (filed, not triaged) → `status:accepted` (Alex agreed) → `status:in-progress` → `status:blocked`.
- Interrupts: `needs:engineering`, `needs:qa`, `needs:coding-agent`, `needs:product`, `needs:qa-executor` (per-persona "look at this NOW"); `needs:alex` (surfaces in a `jarvis-status` view so Alex sees his queue from one place).
- Type/priority: `type:feature|bug|risk|refactor|question`, `priority:p0..p3`.
- `filed-by:engineering|product`, `service:<svc>` (command-center/llm-proxy/whisper/admin/auth/tts/...), `feature:<name>` (e.g. `feature:apt-install`).

Observed split fragmentation in the live data (the explosion the loop produced): issue titles like *"part 1 of 2"*, *"part 2a of 7"*, *"part 2b of 7 ... runner slice of #12"*, *"(SDK slice of #1)"* / *"(node slice of #1)"* — concrete evidence of recursive single-repo splitting (#19→#21/#22; #12→#25/#26; #1→#36/#37).

### Agent org (verified `ls ~/.openclaw/agents`)

`main`, `coding-agent`, `engineering`, `qa`, `product`, `qa-executor`, `doc-expert`, `install-expert`, `marketing`. Each persona's full operating contract is split between `~/.openclaw/<persona>-prompt.md` (the cron message body, read at invoke time) and `~/.openclaw/workspaces/<persona>/CONTEXT.md` (durable brief read at session start). CONTEXT.md line counts verified: product 108, qa-executor 112, doc-expert 61, install-expert 83, marketing 104, and the removed coding-agent 145 / engineering 127 / qa 130.

**Per-role contract (from the prompt files):**

- **product** — interrupt-only, EARLY-EXIT (above). Files new tickets on `needs:product` requests with `status:proposed` + `filed-by:product`.
- **engineering = triage** (`triage-prompt.md`, removed) — hourly. Three cases: **CASE A** fresh triage of `status:proposed` with no existing breakdown → posts `<!-- engineering-triage-breakdown:v1 -->` (feasibility verdict S/M/L, "What I read" file:line citations, Files to change, Step-by-step, New deps/config, Test surface hints, Migration concerns, Verification, **Out of scope**, **Open ambiguities**, Open questions for Alex). **CASE B** amendment — re-files a superseding `:v1`-sentinel breakdown after Alex answers ambiguities (QA/coding-agent always use the *latest* sentinel comment). **CASE B2** split — files N (2–4) child tickets, posts `<!-- engineering-split:v1 -->` linking them, closes parent `not_planned`. Also handles `needs:engineering` interrupts (Step 0, cap 3). Cap 5 issues/run.
- **qa** (`qa-prompt.md`, removed) — hourly on `status:accepted`. Requires the latest `<!-- engineering-triage-breakdown:v1 -->` with **empty Open ambiguities**; **skips if** breakdown missing, ambiguities open, its own test-plan already current, or coding-agent already ran on the current spec. Reads the target repo's existing tests for conventions, then posts `<!-- qa-test-plan:v1 -->` with **CASE-NNN** ids (prose + signatures, arrange/act/assert, `manual:true|false`, test file location + framework). One issue/run.
- **coding-agent** (`coding-prompt.md` + CONTEXT.md, removed) — hourly. Requires **BOTH** sentinels (breakdown + test-plan), with the test-plan **not older** than the breakdown (coherence check). Clones to `/tmp/coding-agent/issue-<N>/<repo>` using `CODING_GITHUB_PAT`, branches `coding-agent/issue-<N>-<slug>`, **TDD two-commit shape** (`test(...)` commit then `feat/fix/...` commit), opens a **draft PR** via `github-code`, posts `🤖 Pushed` on the roadmap issue. Guardrails: **~1200-line diff cap** (abort + ask to split), 30-min wall-clock, never push to default branch, never merge, forbidden paths (`.git/`, `*secret*`, `.env*`, `.github/workflows/` except `jarvis-pantry-runner`). **ABORTS** on cross-repo ("Files to change spans more than one repo → request split"). One issue/run. Statuses: `🤖 Pushed` / `🤖 Coding-agent run aborted` / `🤖 Awaiting clarification`.
- **qa-executor** (survivor) — translates the PR's integration-test-results into a roadmap report (above).
- **doc-expert / install-expert / marketing** — peripheral.

### MCP servers + credentials (names only — values not read)

MCP servers in `openclaw.json` (`mcp.*`), all the `github-mcp-server` binary with different toolsets:

| Server | Toolsets | Scope / PAT |
|---|---|---|
| `github-rw` | `issues,pull_requests,repos,users` | roadmap PAT — `jarvis-roadmap` writes |
| `github-ro` | `issues` (`--read-only`) | read-only |
| `github-code` | `repos,issues,pull_requests,users` | env `GITHUB_PERSONAL_ACCESS_TOKEN` → coding PAT (public `jarvis-*` code repos; **cannot see private `jarvis-roadmap`**) |
| `github-code-ro` | `repos,pull_requests` (`--read-only`) | coding PAT, read-only |

Secrets on the Pi (var **names** only; values never read):
- `~/.openclaw/secrets/github.env` → `GITHUB_PERSONAL_ACCESS_TOKEN` (roadmap PAT; used by `github-rw`). Mode `600`.
- `~/.openclaw/secrets/coding.env` → `CODING_GITHUB_PAT` (code-repo clone/push PAT). Mode `600`.
- `~/.openclaw/secrets/webhook.env` → `WEBHOOK_SECRET`. Mode `600`.
- `.bak-pre-bot-migration` copies of `coding.env`/`github.env` exist alongside.

> **⚠️ SECURITY FINDING (new, unprompted):** `~/github.env` is mode **`-rw-r--r--` (world-readable)** and its contents are **bare PAT token strings, one per line, with NO `KEY=` prefix** (it is not a dotenv file). It holds one classic `ghp_…` token and four `github_pat_…` fine-grained tokens. This file should be `chmod 600`'d (or deleted if superseded by `~/.openclaw/secrets/*`) as part of revival. Values were observed incidentally during name-enumeration and are **not reproduced here**. **Verified 2026-06-22:** it IS superseded — all 8 systemd units load `~/.openclaw/secrets/github.env` (mode 600), and nothing references the bare `~/github.env`. It's a confirmed orphan → safe to remove after rotation (see the R0 status block in the revival plan for exact commands).

GitHub-Actions-side secrets (referenced by the testing-infra PRD; not re-verified here):
- `INTEGRATION_DISPATCH_TOKEN` — in `jarvis-command-center`, `repository_dispatch:write` on `jarvis-node-setup` (`integration-trigger.yml:10-11`).
- `INTEGRATION_COMMENT_TOKEN` — in `jarvis-node-setup`, `pull-requests:write` + commit-statuses:write (posts integration-test-results on the PR). [Scope description per given findings — [unverified] against the runner workflow yaml here.]

**PATs are likely EXPIRED since May** — refreshing them is a revival prerequisite. [Expiry not directly tested — [unverified]; inferred from the May timestamps and the multi-week pause.]

### #42 runaway (idempotency failure) — corrected

The given finding pointed at "issue #42, ~28 comments hourly for days." **Verified and corrected:**
- The runaway is the **`install-expert`** persona (actor `jarvis-automation-agent`) re-posting near-identical "both gaps merged / can likely be closed" comments without ever closing.
- **#42** ("pgvector migration requires `vector` extension...", `priority:p1`) has **41 comments** (not ~28); last comment 2026-06-10. Comment first-lines confirm the repetition: *"both gaps described above have been shipped"*, *"both gaps now have merged fixes — this issue can likely be closed"*, *"Both Required Actions 1 and 2 ... have been merged"* — same actor, repeating.
- **#40** ("PANTRY_CALLBACK_SIGNING_KEY ... no installer automation", `priority:p1`) has **22 comments** — same pattern.
- Root cause in the prompt: `install-expert` idempotency is **per-PR** ("a PR you've already flagged has a tracker issue"), not **per-tracker-issue terminal-state**. So once the tracker issue exists, every hourly run re-evaluates and re-comments "this can be closed" without a guard that says *"I already said this; stop."* No terminal/blocked-on-human state. (`install-expert-prompt.md` EARLY-EXIT + "One roadmap issue per detected gap" — the dedup protects against *duplicate issues*, not *duplicate comments on an existing issue*.)

### The cross-repo plumbing that was built but never used

`linked_prs` is a JSON map `{repo_name: branch_or_sha}` threaded through the integration-runner for coordinated cross-service PR deps. Verified:
- `jarvis-command-center/.github/workflows/integration-trigger.yml:49` fires `repository_dispatch` to `jarvis-node-setup` with `client_payload[linked_prs]={}` **hardcoded empty**.
- `jarvis-node-setup/.github/workflows/integration-runner.yml:44,81,89,121` accept `linked_prs` from both `client_payload` and manual `inputs`.
- `jarvis-node-setup/docs/integration-tests.md:510` — *"JSON map of `{repo_name: branch_or_sha}` for cross-service PR deps. Empty `{}` default; **not consumed yet**."* And `:827` — *"`linked_prs` plumbed through but not consumed. When v2.5+ lands..."*

This is the smoking gun: the cross-repo coordination map exists in the wire protocol but **the coding-agent never populated it and the runner never consumed it.** It is exactly the seam the revival design must light up.

---

## How it works (the protocol)

### Sentinel protocol

A machine-readable comment counts **only when the sentinel is the literal first line of the comment body** (a mid-body mention is a reference, not a marker). Agents always act on the **most recent** comment per sentinel (so `:v2`/`:v3` supersede `:v1`).

| Sentinel (first line) | Posted by | Posted on | Contents |
|---|---|---|---|
| `<!-- engineering-triage-breakdown:v1 -->` | engineering | roadmap issue | feasibility (S/M/L), "What I read" file:line citations, Files to change, Step-by-step, deps/config, Test-surface hints, Migration, Verification, **Out of scope**, **Open ambiguities**, Open questions for Alex |
| `<!-- qa-test-plan:v1 -->` | qa | roadmap issue | CASE-NNN ids, arrange/act/assert, `manual:true|false`, test file location + framework |
| `🤖 Pushed` / `🤖 Coding-agent run aborted` / `🤖 Awaiting clarification` | coding-agent | roadmap issue | status; `🤖 Pushed` carries the draft-PR URL |
| `<!-- integration-test-results:v1 -->` | integration-runner | **code PR** | `\| Case \| Status \| Notes \|` table + summary + CI run URL |
| `<!-- qa-execution-report:v1 -->` | qa-executor | roadmap issue | per-CASE pass/fail/skipped/not-implemented/manual-required + summary + CI/source links |
| `<!-- retry-please:v1 -->` | Alex/orchestrator | roadmap issue | tells coding-agent to retry after an external blocker resolved (no spec change) |
| `<!-- engineering-split:v1 -->` | engineering | roadmap issue | lists child tickets; parent closed `not_planned` |

Engineering "Open ambiguities" + "Open questions for Alex" double-surface to Slack as a top-level threaded message and apply `needs:alex` (so it shows in `jarvis-status`). Alex answers in plain English; the next engineering run amends the breakdown (`:v2`) and removes `needs:alex`.

### Intended end-to-end flow

```
 Slack request
   │
   ▼
 product  ──files──▶  roadmap issue (status:proposed, filed-by:product)
   │
   ▼
 engineering (hourly triage)
   ├─ CASE A → <!-- engineering-triage-breakdown:v1 --> (Open ambiguities listed)
   │
   ▼  ITERATE-TO-READY  ◀────────────────────────────────────────┐
   │   Alex answers design questions in plain comments            │
   │   engineering CASE B re-files amended :v2/:v3 until "Locked" │
   │   cross-repo work → CASE B2 engineering-split (child tickets)│ ← FRAGMENTATION SOURCE
   └──────────────────────────────────────────────────────────────┘
   │
   ▼   Alex / product sets  status:accepted
   │     (webhook Route 1 → qa fires immediately; also hourly)
   ▼
 qa  ──▶  <!-- qa-test-plan:v1 -->  (CASE-NNN)
   │
   ▼
 coding-agent (hourly; needs BOTH sentinels + coherence)
   ├─ TDD two commits → draft PR on a single jarvis-* code repo
   ├─ 🤖 Pushed (PR URL)  ── webhook Route 2 → qa-executor fires immediately
   └─ ABORTS if "Files to change" spans >1 repo  ← CROSS-REPO BREAK
   │
   ▼
 integration-trigger.yml (on the code PR)  ──repository_dispatch──▶  jarvis-node-setup
   │
   ▼
 integration-runner.yml  ──runs CASE suite──▶  <!-- integration-test-results:v1 --> on the PR
   │
   ▼
 qa-executor  ──▶  <!-- qa-execution-report:v1 -->  on the roadmap issue
   │
   ▼
 ┌─────────────────────  BREAK (not built)  ─────────────────────┐
 │  no automerge gate · no full-regression-on-main · no deploy    │
 └────────────────────────────────────────────────────────────────┘
   │
   ▼
 Alex manually reviews + merges + tests
```

---

## Postmortem / root cause

**Two failure modes, one root cause** (Alex's framing, 2026-06-20):

1. **"PRs were isolated to a single repo; things got out of sync."** (drift)
2. **"Churning tokens looping on designs, then 'split this into a separate task,' until 2–3 issues became 30."** (explosion)

**Root cause:** the **atomic unit of work was a single-repo PR**, but real Jarvis features are inherently **cross-repo** (e.g. SDK + node + command-center for one capability). Two mechanisms in the agent contracts then guaranteed fragmentation:

- coding-agent **hard-aborts** on cross-repo ("Files to change spans more than one repo → request split"), and
- engineering triage has a **CASE B2 split** path that decomposes oversized/cross-repo tickets into N child tickets and closes the parent.

So any coherent cross-repo feature was mechanically chopped into ordering-dependent per-repo tickets (**drift** — repos merge at different times, half a feature lands), and the split path recursed (**explosion** — the live `jarvis-roadmap` data shows "part 2b of 7", "SDK slice of #1 / node slice of #1", etc.).

Underneath that: the **tests couldn't be trusted enough to merge on** (the subject of `prds/testing-infrastructure.md`). And the cross-repo coordination primitive that *would* have fixed the unit-of-work problem — the `linked_prs` map — was built into the integration-runner wire protocol but **never populated by the coding-agent or consumed by the runner** (`integration-tests.md:510,827`; `integration-trigger.yml:49` hardcodes `{}`).

---

## Plan / recommendations (the revival design)

> Sequencing: the testing foundation (`prds/testing-infrastructure.md`) is the deliberate **first** investment and gates everything below. Do not re-enable autonomous merging until the fast lane gates PRs honestly and the behavior lane + cross-service CASE suite exist.

### Design pillars (the unit-of-work fix)

1. **Unit of work = a FEATURE spanning N repos**, not a single-repo PR. A feature becomes a **coordinated branch set** — one branch per affected repo, named by a shared feature id — opened together and validated together. Light up `linked_prs` (`{repo: branch}`): the coding-agent **populates** it; the integration-runner **consumes** it to check out all branches into one stack before running the CASE suite (`integration-runner.yml:44,81,89`; the consumption path the docs say lands "in v2.5+").
2. **Merge as a group.** The automerge gate (in the testing PRD's "Later" section) merges the whole coordinated set on all-green, or none of it — eliminating the half-a-feature drift.
3. **Hard anti-split bias + ticket-creation cap.** Invert the coding-agent's cross-repo *abort* and engineering's *split*: cross-repo is the **expected** case, not a reason to fragment. Cap the number of child tickets a single triage run may create (e.g. ≤1, with a human gate to exceed it) to stop the recursive explosion.
4. **Bounded, cheap design/clarify loop.** Cap ITERATE-TO-READY iterations (e.g. ≤3 amendment rounds) before forcing a `needs:alex` human decision; never loop indefinitely re-breaking-down the same ticket.
5. **A machine-checkable "ready" gate.** Today readiness is the *emergent co-presence* of two sentinels plus human judgement — fragile (see Known gaps). Replace with an explicit, queryable "ready" predicate (e.g. a `status:ready-for-code` label set only when breakdown has empty ambiguities AND a non-empty CASE list AND a human "Locked" ack).
6. **A structured clarifying-questions primitive + a `status:blocked` (blocked-on-human) state.** A first-class Q&A object (question id → answer), not free-text comments parsed heuristically; the loop *parks* on it instead of busy-waiting.
7. **Idempotency / terminal-state guards on every persona.** Per-tracker-issue terminal state (not just per-PR), so an agent that has already said "this can be closed" stops (the #42/#40 fix). A durable, queryable ticket-state object: which PR(s) implement it, which CASE-IDs gate it, current loop iteration #.

### Phased revival

**Phase R0 — Stop the bleeding + prerequisites (do now, before any re-enable)**
- Kill the `install-expert` #42/#40 runaway: add a per-tracker-issue terminal-state guard so it stops re-commenting "can be closed"; or temporarily disable the `install-expert-runner.timer`. Optionally close #42/#40 by hand.
- Refresh both PATs (roadmap + coding) and re-write `~/.openclaw/secrets/{github,coding}.env`. **Also `chmod 600` (or delete) `~/github.env`** (world-readable bare tokens — security finding above).
- Verify the Claude Max path post-refresh (`journalctl | grep cli-backend` shows `provider=claude-cli`).

#### R0 execution status & install-expert redesign (verified 2026-06-22, live Pi inspection + adversarial guard review)

**Verified on the live Pi (read-only SSH):**
- `install-expert-runner.timer` is **still enabled and firing hourly** (last run 12:37 EDT scanned 5 PRs → 0 gaps; next 13:35). The #42/#40 **re-comment symptom is dormant since 2026-06-10** — the *current* prompt is already tighter than this doc's original description: its early-exit computes `UNCHECKED = CANDIDATES − FLAGGED`, so once a tracker exists for a source PR it's excluded. Residual: an uncapped `create_issue`/`add_issue_comment` path when the FLAGGED match misses, and no terminal close-the-loop state. Each hourly run still burns one `claude` session (~11s CPU) doing nothing useful while the loop is paused.
- **Secrets:** every systemd unit loads `~/.openclaw/secrets/github.env` (mode 600). The bare `~/github.env` (`-rw-r--r--`, 5 bare tokens) is a **confirmed orphan** — referenced by no unit/config. Fix: `chmod 600` now → archive → rotate the 5 PATs → delete. (`~/.openclaw/secrets/*` already 600.)
- **No real agent-set discrepancy:** 5 active timers = product, install-expert, marketing, qa-executor, doc-expert (the documented survivors). A `qa-author-runner.service` file lingers but has **no active timer** (consistent with the 2026-05-19 removal — leftover unit file, not a live agent).

**R0 decision:** since the loop is paused and install-expert is mid-redesign, R0 **disables the timer** (`systemctl --user disable --now install-expert-runner.timer`) + secures the secrets, rather than patching the prompt piecemeal. The redesign below lands in Phase R2 when install-expert is revived. **DONE + verified 2026-06-22:** the timer is disabled/inactive (off the active list) and `~/github.env` is now `-rw-------`. **Update 2026-06-22:** Alex has revoked + recycled the PATs (DONE — the PRD had lagged this). Only loose end: deleting the orphan `~/github.env` file (its tokens are now dead, already mode 600 → pure tidiness).

**install-expert idempotency redesign (v2) — the verified guard spec.** A proposed "append-only terminal-state guard" was adversarially reviewed from 4 lenses (duplicate-runaway, false-negative-regression, toolset-feasibility, closeability-loop) and found **insufficient on all 4**. Root structural fact: install-expert has **no local state and no comment-thread-read tool** (its whitelist is `list_issues`/`search_issues`/`create_issue`/`add_issue_comment`/`add_labels_to_issue` + read-only source tools), so *every* idempotency decision must ride on **queryable GitHub labels + a machine-stable title token** — never parsed body prose or a bounded list page. The correct guard:

1. **Dedup key = machine-stable token, not prose.** Tracker title `[install-pattern] owner/repo#NNN — <service>`; labels `service:install-pattern` + `pr:owner-repo-NNN` (set once at create). Title + labels are returned by both `list_issues` and `search_issues`; **the body is not — `list_issues` omits it** (so pin `search_issues` wherever a body read is unavoidable).
2. **FLAGGED via per-PR targeted search, not a bulk page.** For each candidate `owner/repo#N`: `search_issues "repo:…/jarvis-roadmap is:issue label:pr:owner-repo-N"` (all states). Immune to the limit-30 page cap (the append-only tracker population *outgrows one page* — the dominant steady-state failure) and to body-format drift. Match **fully-qualified `owner/repo#N` only** — bare PR numbers collide across the 50+ `jarvis-*` repos.
3. **Idempotency keyed on (PR + head SHA + surface), NOT PR-number-forever.** Tracker body records `tracked-pr-sha` + `surfaces-checked`. A tracked PR re-enters scope only if its head SHA changed (new commits ⇒ possible new gap); a not-yet-tracked PR number is **always** in scope (no semantic-similarity skipping). This restores the coverage the naive "permanently out of scope" rule throws away: second gaps from later commits, drift reappearing after a wont-fix close, cross-repo number collisions, partially-scanned PRs.
4. **Fail closed + hard caps.** Targeted search errors → do NOT create (skip + log). ≤1 tracker created per run (on top of the existing ≤5 PRs/run scan cap).
5. **Close the loop with labels, not comments.** The runaway was repeated *free-text comments*; `add_labels_to_issue` is **idempotent** (no-op if present) → labels are the safe primitive. Apply `needs-triage` **once at create** = engineering/Alex's fix-and-close queue (`label:service:install-pattern label:needs-triage is:open`). A **label-only RESOLUTION SWEEP** (separate from UNCHECKED, **never comments**) flips `needs-triage`→`install-expert:resolved` once when the mirror merge is detected, and sends ONE Slack ping gated on the absent→present label transition. `label:install-expert:resolved is:open` = the safe-to-bulk-close queue. This is the close-the-loop mechanism the per-tracker-terminal-state pillar (#7) was reaching for — labels, not a "can be closed" comment.
6. **Re-comment ban (kept).** `add_issue_comment` on an existing tracker is forbidden; status/resolution is expressed only via idempotent labels.

This supersedes the sentinel-comment sketch in design pillar #7 (a sentinel-in-prior-comments check is **not executable** — there is no tool to read an issue's comment thread).

**Phase R1 — Testing foundation (separate PRD, blocking)**
- Execute `prds/testing-infrastructure.md` Phases 1–2 (honest CI, the `jarvis-integration-tests` repo, the behavior lane, from-source overlays for llm-proxy/whisper/tts, and **T10: coordinated cross-repo branch sets via `linked_prs`**). T10 is where the testing fix and the unit-of-work fix converge — **DONE** (merged as jarvis-integration-tests #6, validated green run 27967408363).

**Phase R2 — Restore the three agents on the new unit of work**
- Un-rename `coding-prompt.md` / `qa-prompt.md` / `triage-prompt.md` and the three `.removed-2026-05-19` workspaces; re-add `agents.list` entries (cross-check against `openclaw.json.bak-pre-3agent-removal`); re-install the `{coding-agent,engineering,qa}-runner.{timer,service}` units in `~/.config/systemd/user/` and `systemctl --user enable --now` them.
- Rewrite the contracts per the design pillars: coding-agent populates `linked_prs` and operates on a branch *set*; engineering's split path is replaced by a feature-decomposition-without-fragmentation path (one tracker issue → coordinated branches, not N tickets); add the ready-gate label and the structured Q&A primitive.

#### Phase R2 redesign — grounded design decisions (2026-06-22, 4-agent analysis over the REAL archived contracts; full output cached at the workflow task file)

Grounded in the *actual* archived contracts (`triage/qa/coding-prompt.md.removed-2026-05-19` + workspace CONTEXTs), not the PRD summaries. **Settled engineering-call decisions (no Alex input needed):**

**Engineering (triage):**
- DELETE the CASE-B2 child-ticket SPLIT path (the explosion engine). Cross-repo features are DECOMPOSED into a `## Branch set` (`<repo> → <branch>`/repo) inside the SAME breakdown — one tracker stays the unit, zero child tickets.
- Child-ticket creation budget = **0/run** by default; recursion guard: never split an issue already labeled `filed-by:engineering`/`spun-out`.
- Bound the clarify loop: `loop_iteration` in the state object; at 3 unresolved-ambiguity rounds → `status:blocked` + `needs:alex`, stop auto-amending.
- Engineering owns ALL label/state writes — it's the ONLY persona with `issue_write` (qa + coding-agent are read-only on tracker metadata; keep it that way to bound blast radius).

**QA (test-plan):**
- Reconcile the two namespaces by **reference, not authorship**: `<!-- qa-test-plan:v1 -->` gains a fenced yaml block — `unit_cases:` (per-repo pytest names for coding-agent) + `integration_cases: [CASE-…]` chosen from a **generated CASE catalog** (a CI step in jarvis-integration-tests greps `@pytest.mark.qa_case` + the resolver's KNOWN map). QA never edits the harness.
- Empty-plan fix: the ready-gate parses the block; ≥1 case required, every `CASE-…` must exist in the catalog. Reuse the existing `not_implemented>0 → fail` net as backstop.

**Coding-agent:**
- DELETE the cross-repo hard-abort (the root cause + the exact signal CASE-B2 fed on — removing it de-fuses the explosion at the source). Operate on the repo SET from one breakdown: N clones, N branches all `coding-agent/feat-<N>-<slug>`, **two-phase**: push ALL branches, THEN open N draft PRs each carrying symmetric `Linked-PR: <sibling>@<branch>` markers (BRANCH refs not SHAs — they resolve at clone time + avoid the denied `update_pull_request`). Keep the per-repo two-commit TDD shape + the **per-repo** 1200-line cap.
- Input guard (kills the no-op-plan bug): before any clone, require ambiguities==None AND ≥1 parseable test case AND every implied repo ∈ the six from-source overlays (else fail-fast).
- Feature-level idempotency: terminal `<!-- coding-agent-feature-ready:v1 -->` sentinel keyed on the feature id; re-arm via the existing `retry-please` sentinel.

**Cross-cutting (the spine):**
- **Durable ticket-state object** = a latest-wins `<!-- feature-state:v1 -->` JSON comment on the tracker: `{feature_key, iteration, repos:{slug:{branch,pr,head_sha,state}}, case_ids, gating_cases, ambiguities_open, human_locked, blocked_on, terminal}`. Readable by all 3 (`get_comments`); engineering owns lock/terminal/label fields, coding-agent appends its branch/PR, qa-executor mirrors the CI result.
- **`feature_key` already exists** (computed identically in `cross-repo-trigger.yml` + `resolve_cross_repo.py`) → persist that same sorted-union key into the state object; it's the join between durable Issues state and the transient CI runs. Nothing new to invent for set-identity (proven green: run 27967408363).
- **Ready predicate** = `ambiguities_open==0 AND len(case_ids)>0 AND len(repos)>=1 AND human_locked==true`, mirrored to a `status:ready-for-code` label.
- **Per-ticket terminal-state** via a `status:done|merged|abandoned` label (idempotent) + the `terminal` field — every persona early-exits on a terminal tracker (the #42/#40 fix scaled to the N-PR fan-out).

**HARD constraint the whole design must respect:** the cross-repo CI lane only covers the **six from-source overlay repos** (auth, config-service, command-center, llm-proxy-api, whisper-api, tts; `resolve_cross_repo.py` hard-errors on others). A feature touching SDK / node-setup / a `jarvis-cmd-*` / `jarvis-device-*` can be branch-set + PR'd but is NOT validatable as one unit until an overlay is authored → coding-agent fail-fasts, and such participants are marked `integration:fast-lane-only` so the future automerge gate doesn't wait on a CASE that can't run. **This overlay gap is the single biggest real-world limiter** (the postmortem's canonical SDK+node example is OUTSIDE the covered set).

**3 forks — DECIDED by Alex 2026-06-22:** (1) feature data model = **umbrella-ticket-per-feature** (one tracker = the coordinated branch set + a `feature-state:v1` JSON comment); (2) human "go" = **a `status:locked` label Alex sets** → engineering flips `status:ready-for-code`; (3) coverage-gap = **BLOCK** (QA parks the feature blocked-on-human + requests a new harness CASE when the generic 401/402 probes don't exercise the feature). The full shared spec is staged at `prds/loop-revival-v2/SHARED-SPEC.md`; the rewritten contracts at `prds/loop-revival-v2/{triage,qa,coding}-prompt.v2.md`. **Deferred to R3:** autonomous group-merge — the gate is designed (an integration-tests job merging the persisted PR set on an all-green feature-keyed `cross-repo-test-results`, needing a new merge-scoped PAT) but stays HUMAN-ONLY for R2; re-enabling auto-merge is the R3 trust fork. **Adopted defaults (Alex can override):** all ticket-splits human-gated; repos-per-feature cap ≤3 (needs:alex to exceed); forbidden-paths unchanged; markers go in PR bodies (no workflow-file edits).

**Build status (2026-06-22):** all 3 contracts drafted against the spec, 4-lens adversarially reviewed, and fixed (2 review rounds + a surgical pass, final verification PASS) — staged at `prds/loop-revival-v2/{triage,qa,coding}-prompt.v2.md` against `SHARED-SPEC.md` (rev 2). `qa` deployable (2 optional-hardening lows deferred); `triage` + `coding` deployable after the applied fixes (engineering's non-clarify-park un-park exit + `Read`-only catalog fallback; coding's terminal-ack idempotency). The review caught real bugs the spec/drafts had — coverage-gap ordering, a terminal-guard bypass on the interrupt path, feature_key mixed-lane divergence, the CASE-402 dual-mode conflation — all corrected. **Deployment gate — spec §15 prereq #1 is now DONE; #2–#4 remain (all Alex-gated):** prereq #1, the `CASE_CATALOG.json` generator, is **MERGED 2026-06-22** to jarvis-integration-tests `main` (PR #8 `feat/case-catalog-generator`: `tools/gen_case_catalog.py` + the committed `tests/CASE_CATALOG.json` + the repo's first PR-gated `unit.yml` drift lane; regen PR #9 `chore/catalog-add-216-220`). Catalog now **38 cases** (post the #7/#10/#11 negative-auth CASEs), drift-check CLEAN (`python tools/gen_case_catalog.py --check` exit 0), 28 unit tests pass. Remaining: (#2) verify the github-rw MCP comment-read method name; (#3) optional Slack→GitHub relay qid-keyed answers; (#4) the Pi mechanics (un-rename `.removed-2026-05-19` prompts/workspaces, re-add `agents.list`, re-install `{coding-agent,engineering,qa}-runner.{timer,service}`, refresh PATs) — Alex's to run.

**Phase R3 — Wire the missing tail (depends on testing PRD)**
- Automerge gate on an all-green `qa-execution-report` for the *whole coordinated set*.
- Full-regression-on-`main` job after merge.
- Gated auto-deploy with post-deploy smoke + rollback.
(These are the testing PRD's "Later (post-testing, separate efforts)" items.)

---

## Open questions

- **What is the right ready-gate predicate?** Co-presence of two sentinels demonstrably fools a naive check (see #6 in Known gaps). Candidates: an explicit `status:ready-for-code` label, or a structured "readiness object" the agents write/read. Needs design.
- **Where does the durable ticket-state object live?** GitHub labels can't express "which PRs implement this / which CASE-IDs gate it / iteration #." Options: a JSON block in a pinned sentinel comment, a sidecar file in `jarvis-roadmap`, or an external store. The testing PRD already commits to *keeping* GitHub Issues as the ticket store — so the state object likely rides inside it.
- **Where does the QA CASE catalog live?** Today CASE ids in `qa-test-plan` are generated per-issue and the executed CASE suite lives in the integration-runner repo — two disconnected namespaces. Reconciling them is a prerequisite for the ready-gate to mean anything.
- **Does the engineering "split" path survive at all?** Under the feature-grained model, splitting is the disease. But genuinely independent tickets do exist. Define the bright line (and the human gate) between "decompose into coordinated branches of one feature" vs "two unrelated tickets."
- **PRD-to-ticket linkage** is manual and unlinked today. Should a PRD auto-seed a tracker issue (and how is that lineage recorded)?
- **Claude Max quota under load** — with three core agents back on hourly timers (plus webhook bursts), does the Max baseline hold, or does it throttle? (The runaway already burned quota for days.)

---

## Risks / limitations

- **No machine-checkable "ready" gate exists today.** Readiness is the emergent co-presence of two sentinels + human judgement. A no-op `qa-test-plan` (an empty CASE list) would satisfy a naive "both sentinels present" check and let coding-agent run against nothing — this actually happened (a no-op test plan on a real issue). Any re-enable without a real gate is unsafe.
- **No structured Q&A / no blocked-on-human state.** Clarifications are free-text comments parsed heuristically by the next cron; there is no first-class "question→answer" object and no `status:blocked` park state, so the loop busy-waits or guesses.
- **No durable, queryable ticket state beyond labels** — which PR implements a ticket, which CASE-IDs gate it, and the loop iteration # are not recorded anywhere queryable.
- **QA CASE catalog lives outside the repo** (in the integration-runner), disconnected from the per-issue CASE ids in `qa-test-plan`.
- **No idempotency / terminal-state guards** — the live #42 (41 comments) and #40 (22 comments) `install-expert` runaways prove agents re-act on already-handled state indefinitely. Burns Max quota; never converges.
- **PRD→ticket is manual + unlinked.**
- **Cross-repo was a hard abort, not a capability** — the central architectural flaw; `linked_prs` was plumbed but never consumed.
- **Tests can't yet be trusted to merge on** — the whole reason the testing PRD comes first.
- **Pi is single-tenant for the gateway + the loop + the dashboard + webhook** — 8 GB shared; the testing PRD explicitly rejects the Pi as the CI runner for this reason (ARM, shared RAM, persistent-runner state leaks).
- **Secrets hygiene** — world-readable `~/github.env` with bare tokens (above).

---

## Appendix — key file references

**On the Pi (`pi@openclaw.local`, read-only):**
- `~/openclaw-claude-max-setup.md` — the Claude Max `claude-cli` runtime how-to (the ~$0-marginal billing config + footguns).
- `~/jarvis-webhook-receiver/main.py` — FastAPI webhook receiver. HMAC verify `:60-73`; Route 1 (issues.labeled status:accepted → qa) `:108-117`; Route 2 (issue_comment `🤖 Pushed` → qa-executor) `:139-152`; `invoke_persona()` fire-and-forget `:181-211`.
- `~/.openclaw/openclaw.json` — gateway config. `agents.defaults.model.primary = anthropic/claude-opus-4-7`; `agents.defaults.models.*.agentRuntime = {id: claude-cli}`; `agents.list` (6 survivors, each `model: anthropic/claude-sonnet-4-6`); `bindings` (Slack channel→agent routes); `mcp.*` (github-rw/ro/code/code-ro); `commands.ownerAllowFrom`.
- `~/.openclaw/openclaw.json.bak-pre-3agent-removal` — config snapshot before the 2026-05-19 removal (use to restore `agents.list` entries).
- `~/.openclaw/triage-prompt.md.removed-2026-05-19` — engineering contract (CASE A/B/B2; breakdown template; split template; needs:alex Slack surfacing).
- `~/.openclaw/qa-prompt.md.removed-2026-05-19` — qa contract (skip rules; CASE-NNN test-plan; `C0B3WKBPSJ3` slack).
- `~/.openclaw/coding-prompt.md.removed-2026-05-19` + `~/.openclaw/workspaces/coding-agent.removed-2026-05-19/CONTEXT.md` — coding-agent contract (two-commit TDD; 1200-line cap; cross-repo abort; forbidden paths; PR body template; `/tmp/coding-agent/issue-<N>`; `CODING_GITHUB_PAT`; `C0B4C0W5WHY` slack).
- `~/.openclaw/product-prompt.md` — product (EARLY-EXIT, needs:product only; `C0B4C3YBTC1`).
- `~/.openclaw/qa-executor-prompt.md` — qa-executor (EARLY-EXIT; reads `integration-test-results` from PR via `github-code`; posts `qa-execution-report`; `C0B4DQL8SF4`).
- `~/.openclaw/install-expert-prompt.md` — install-expert (per-PR idempotency; the #42/#40 runaway root cause).
- `~/.config/systemd/user/<persona>-runner.{timer,service}` — scheduling. `Type=oneshot`; `ExecStart=openclaw agent --agent <p> --session-id cron-<ts> --message "$(cat ~/.openclaw/<p>-prompt.md)" --timeout 600`; `EnvironmentFile=~/.openclaw/secrets/{github,coding}.env`. 5 survivors; removed-agent units gone.
- `~/.openclaw/secrets/{github.env,coding.env,webhook.env}` — `GITHUB_PERSONAL_ACCESS_TOKEN` / `CODING_GITHUB_PAT` / `WEBHOOK_SECRET` (mode 600).
- `~/github.env` — **world-readable, bare token strings** (security finding; chmod 600 or delete).

**In the jarvis ecosystem (`/Users/alexanderberardi/jarvis`):**
- `jarvis-command-center/.github/workflows/integration-trigger.yml` — fires `repository_dispatch` to jarvis-node-setup on PR events; `linked_prs={}` hardcoded `:49`; token note `:10-11`.
- `jarvis-node-setup/.github/workflows/integration-runner.yml` — consumes the dispatch; `linked_prs` input `:44`, `:81`, `:89`, `:121`.
- `jarvis-node-setup/docs/integration-tests.md` — `linked_prs` is `{repo: branch_or_sha}`, "not consumed yet" `:510`, `:827`; payload shape `:245`; manual inputs `:259`.
- `prds/testing-infrastructure.md` — the foundation this loop is gated on (committed architecture: two CI lanes, `jarvis-integration-tests` repo, `ChatGPTOpenAI` behavior lane, T10 coordinated cross-repo branch sets).

**GitHub (`alexberardi/jarvis-roadmap`, private):**
- Issues #18–#47 (the live ticket DB). Fragmentation evidence: "part 2a/2b of 7" (#25/#26), "SDK slice of #1 / node slice of #1" (#36/#37). Runaways: #42 (41 comments), #40 (22 comments). Verify: `gh issue list --repo alexberardi/jarvis-roadmap --state all --limit 30`, `gh label list --repo alexberardi/jarvis-roadmap`, `gh issue view 42 --repo alexberardi/jarvis-roadmap --json comments`.
