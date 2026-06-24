export const meta = {
  name: 'loop-v2-author',
  description: 'Author + adversarially review the 11 loop-v2 agent artifacts for openclaw.local',
  phases: [
    { title: 'Author' },
    { title: 'Review' },
    { title: 'Fix' },
    { title: 'Consistency' },
  ],
}

const ROOT = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2'
const DEPLOY = ROOT + '/deploy/openclaw'
const VF = ROOT + '/deploy/VERIFIED-FACTS.md'
const SPEC = ROOT + '/SHARED-SPEC.md'

const PREAMBLE = `You are authoring ONE deployable artifact for the Jarvis autonomous dev loop ("loop v2") that runs on pi@openclaw.local (an OpenClaw multi-persona Pi). These are real agent contracts that will drive an autonomous ticket->code->QA pipeline; precision matters.

BEFORE writing, Read these two files IN FULL — they are ground truth and OVERRIDE the staged contracts wherever they conflict:
- ${VF}    (exact live OpenClaw tool names, Slack channel IDs, kill switches, mirror/catalog paths, per-agent tools profile, the v2 topology)
- ${SPEC}  (the loop-v2 SHARED-SPEC the contracts MUST conform to)

NON-NEGOTIABLE TOOL-NAME CORRECTION (the staged contracts get this WRONG — fix it everywhere):
- ADD a roadmap label    -> mcp__github-rw__add_labels_to_issue        (NOT issue_write)
- REMOVE a roadmap label -> mcp__github-rw__remove_label_from_issue    (NOT issue_write)
- CLOSE / set state       -> mcp__github-rw__issue_write (state=closed, state_reason=not_planned)  [issue_write is ONLY for close/state, NEVER labels]
- read a comment thread   -> mcp__github-rw__issue_read (method get_comments)   [github-code__issue_read for PR comments]
- post a comment          -> mcp__github-rw__add_issue_comment
- Slack                   -> mcp__openclaw__message  (channel id + text)
The staged contracts also sometimes hedge ("if the tool name is unclear, ToolSearch..."). REMOVE all such hedging and use the confirmed names above.

OUTPUT RULE: Write the FINAL, COMPLETE file to the exact absolute path given. Never output a diff, summary, or placeholder. For artifacts based on a staged contract, reproduce it in full and apply only the listed corrections — do NOT drop, summarize, or reorder sections.`

const items = [
  {
    id: 'triage-prompt',
    path: `${DEPLOY}/triage-prompt.md`,
    label: 'engineering prompt',
    persona: 'engineering',
    prompt: `Produce the deployable ENGINEERING (triage) cron prompt at ${DEPLOY}/triage-prompt.md.
Base = the staged contract at ${ROOT}/triage-prompt.v2.md. Read it and reproduce it COMPLETELY and VERBATIM, applying ONLY these corrections:
1. Apply the label-tool correction everywhere (add_labels_to_issue / remove_label_from_issue / issue_write-for-close-only).
2. Insert a KILL-SWITCH block as the very FIRST content in the file (above "## Step 0"): "## Kill switch — check FIRST" — if the file \`~/.openclaw/engineering.disabled\` exists, output exactly \`engineering disabled by kill switch.\` and STOP (do nothing else).
3. In Step 0.3.e the staged text hedges about the remove-label tool ("likely ... or via issue_write ... ToolSearch"). Replace with the confirmed call: \`mcp__github-rw__remove_label_from_issue\` (label \`needs:engineering\`). No hedging.
4. Verify Slack channel is C0B4C4XJ9L1 (#engineering-bot), the CASE catalog path is /home/pi/code/jarvis/jarvis-integration-tests/tests/CASE_CATALOG.json, and the mirror is /home/pi/code/jarvis/<repo>.
5. The "## Tool whitelist" section must list ONLY confirmed tools: list_issues, issue_read (get_comments), add_issue_comment, add_labels_to_issue, remove_label_from_issue, issue_write (close/state ONLY), create_issue, Read, mcp__openclaw__message. Remove any "issue_write (labels)" phrasing.
Change NOTHING else — keep all logic, steps, templates, hard rules verbatim.`,
  },
  {
    id: 'engineering-context',
    path: `${DEPLOY}/workspaces/engineering/CONTEXT.md`,
    label: 'engineering CONTEXT',
    persona: 'engineering',
    prompt: `Author the durable ENGINEERING CONTEXT.md (read at session start) at ${DEPLOY}/workspaces/engineering/CONTEXT.md.
Read the current live one for the accurate infra content: run \`ssh pi@openclaw.local 'cat ~/.openclaw/workspaces/engineering/CONTEXT.md'\`. KEEP its accurate sections (product-in-one-breath; where code lives = /home/pi/code/jarvis; top-level layout cheat-sheet; conventions; how-you-talk-to-Alex).
UPDATE / ADD for loop v2 (concise — this is a brief, NOT step-by-step; the cron prompt has the steps):
 (a) Unit of work = ONE umbrella tracker = a coordinated branch set; NO child tickets.
 (b) The six-repo cross-repo vocabulary (list it).
 (c) The feature-state:v1 JSON schema + that engineering owns its plan fields AND all status:* labels (only persona with label power).
 (d) The machine-checkable ready-gate predicate, with coverage-gap (condition 0: non-empty proposed_cases => BLOCK) evaluated FIRST.
 (e) CASE catalog location (read-only reference) + the resolver.
 (f) Label vocabulary; status:locked is ALEX's alone.
 (g) Anti-split: child-ticket budget 0/run; cross-repo => decompose into the branch set.
 (h) Bounded clarify loop + park (iteration cap 3).
 (i) Per-ticket terminal-state idempotency (the #42/#40 fix scaled to N PRs).
 (j) Corrected tool whitelist.
 (k) Kill switch ~/.openclaw/engineering.disabled.
FIX stale claims in the current CONTEXT: it says "QA coming"/"engineering persona doesn't exist yet" (both exist now: qa, qa-author, coding-agent), and "mirror not auto-refreshed, clone date 2026-05-16" — the mirror is now \`git pull --ff-only\`'d daily at 05:00 by a jarvis-mirror-refresh timer, so treat it as current-as-of-this-morning (still flag suspected drift on hot files). Match the tone/structure of the existing CONTEXT files.`,
  },
  {
    id: 'qa-prompt',
    path: `${DEPLOY}/qa-prompt.md`,
    label: 'qa prompt',
    persona: 'qa',
    prompt: `Produce the deployable QA (per-feature test-plan author) cron prompt at ${DEPLOY}/qa-prompt.md.
Base = the staged contract at ${ROOT}/qa-prompt.v2.md. Reproduce it COMPLETELY and VERBATIM, applying ONLY these corrections:
1. QA is READ-ONLY on tracker metadata: it must use ONLY list_issues, issue_read (get_comments), add_issue_comment, Read, mcp__openclaw__message. It NEVER calls any label/create/close tool. Ensure the tool whitelist + body reflect the confirmed names and that NO issue_write / add_labels / create_issue appears as a QA action.
2. Insert a KILL-SWITCH block as the very FIRST content (above "## Step 0"): if \`~/.openclaw/qa.disabled\` exists, output \`qa disabled by kill switch.\` and STOP.
3. Verify Slack channel C0B3WKBPSJ3 (#qa-bot), the CASE catalog path /home/pi/code/jarvis/jarvis-integration-tests/tests/CASE_CATALOG.json, and the resolver path /home/pi/code/jarvis/jarvis-integration-tests/tools/resolve_cross_repo.py.
4. It reads CONTEXT at ~/.openclaw/workspaces/qa/CONTEXT.md (add a one-line "read it this session if you haven't" near the top if not present).
Change NOTHING else — keep the composition-vs-routing rules, CASE-402-never-listed rule, coverage-gap BLOCK, fail-closed catalog handling, the qa-test-plan template, hard rules verbatim.`,
  },
  {
    id: 'qa-context',
    path: `${DEPLOY}/workspaces/qa/CONTEXT.md`,
    label: 'qa CONTEXT',
    persona: 'qa',
    prompt: `Author a NEW durable QA CONTEXT.md (read at session start) at ${DEPLOY}/workspaces/qa/CONTEXT.md. There is no prior version. Model the structure/tone on the other CONTEXT files (run \`ssh pi@openclaw.local 'cat ~/.openclaw/workspaces/qa-executor/CONTEXT.md'\` to see the house style).
Content (a durable brief, NOT step-by-step — the cron prompt ~/.openclaw/qa-prompt.md has the steps):
 - Who you are: the per-FEATURE test-PLAN author. You read the engineering breakdown + feature-state on an umbrella tracker and post ONE \`<!-- qa-test-plan:v1 -->\` comment covering every participating repo. You are READ-ONLY on tracker metadata (no labels, no create, no close, no harness writes). Distinguish yourself from qa-author (a SEPARATE agent that writes the real CASE test CODE into jarvis-integration-tests) and qa-executor (mirrors CI results) — a small ascii pipeline helps.
 - The unit of work: umbrella tracker = coordinated branch set; one plan per umbrella.
 - The six-repo cross-repo vocabulary; fast-lane-only repos get unit_cases only, no integration_cases.
 - The CASE catalog at /home/pi/code/jarvis/jarvis-integration-tests/tests/CASE_CATALOG.json (structure {_meta, cases:{id:{intent,lane,mode,repo,gating,test}}}) + the resolver KNOWN map (llm-proxy always 301/303/304 + composition 302; whisper 321; tts 311; +401 when union>=2; routing=>402 lane-derived). You REFERENCE existing CASE ids, never author them.
 - Two lane modes: composition (you list always+composition+401) vs routing (CASE-402, lane-derived — you NEVER list 402).
 - Coverage-gap = BLOCK: when generic 401/402 don't exercise the feature and no specific CASE exists, emit an unforgeable PARK (integration_cases:[] + non-empty proposed_cases + OMIT unit_cases for the offending cross-repo repo) and flag @engineering. Fail-closed if the catalog is unreadable.
 - "Read each participating repo's test conventions first" discipline (mirror /home/pi/code/jarvis/<repo>/tests).
 - The corrected tool whitelist (read-only set).
 - Kill switch ~/.openclaw/qa.disabled. Slack #qa-bot C0B3WKBPSJ3.
 - How you talk to Alex (cron worker, no chitchat; surface Alex-questions via the @engineering line, NOT a direct label — you can't label).`,
  },
  {
    id: 'coding-prompt',
    path: `${DEPLOY}/coding-prompt.md`,
    label: 'coding-agent prompt',
    persona: 'coding-agent',
    prompt: `Produce the deployable CODING-AGENT cron prompt at ${DEPLOY}/coding-prompt.md.
Base = the staged contract at ${ROOT}/coding-prompt.v2.md. Reproduce it COMPLETELY and VERBATIM, applying ONLY these corrections:
1. Tool names: github-rw is READ+COMMENT only for coding-agent — list_issues, issue_read (get_comments), add_issue_comment (NO labels, NO create_issue, NO issue_write). github-code = create_pull_request, list_pull_requests, pull_request_read ONLY (DENIED: merge_pull_request, update_pull_request, push_files, create_or_update_file, delete_file). Builtin file ops are read/write/edit (apply_patch only "if available" — prefer edit/write); exec/bash for git. Fix the tool whitelist + the "Do NOT call" list to these confirmed names.
2. Insert a KILL-SWITCH block as the very FIRST content (above "## Step 0"): if \`~/.openclaw/coding-agent.disabled\` exists, output \`coding-agent disabled by kill switch.\` and STOP.
3. Verify Slack channel C0B4C0W5WHY (#coding-bot), CONTEXT path ~/.openclaw/workspaces/coding-agent/CONTEXT.md, CASE catalog path /home/pi/code/jarvis/jarvis-integration-tests/tests/CASE_CATALOG.json, scratch /tmp/coding-agent/feat-<N>/<repo>, and that clone/push use https://x-access-token:\${CODING_GITHUB_PAT}@github.com/alexberardi/<repo>.git.
4. The systemd unit kills the run at ~35 min; keep the internal 30-min wall-clock cap note.
Change NOTHING else — keep the two-phase push, symmetric Linked-PR markers (cross-repo lanes only), per-repo 1200-line cap, repos-per-feature cap 3, forbidden paths, content+vocabulary pre-flight (incl coverage-gap=BLOCK and CASE-catalog fail-closed), two-commit TDD, idempotency guards, all templates verbatim.`,
  },
  {
    id: 'coding-context',
    path: `${DEPLOY}/workspaces/coding-agent/CONTEXT.md`,
    label: 'coding-agent CONTEXT',
    persona: 'coding-agent',
    prompt: `Author the durable CODING-AGENT CONTEXT.md (read at session start) at ${DEPLOY}/workspaces/coding-agent/CONTEXT.md.
Read the ARCHIVED prior one for accurate infra/conventions: \`ssh pi@openclaw.local 'cat ~/.openclaw/workspaces/coding-agent.removed-2026-05-19/CONTEXT.md'\`. Keep its still-accurate infra (local git identity, /home/pi/code/jarvis mirror, forbidden paths, conventions, how-you-talk-to-Alex), but REWRITE the unit-of-work for loop v2:
 - You are the ONLY write+exec persona on code repos. Unit of work = a FEATURE = umbrella tracker = a coordinated branch set (one branch per affected repo, all coding-agent/feat-<N>-<slug>). NO child tickets, NEVER "spans multiple repos, please split" — cross-repo IS the expected case.
 - Two MCP servers: github-rw (roadmap, read+comment only — no labels/create) vs github-code (code-repo PRs: create_pull_request/list_pull_requests/pull_request_read only; merge/update/push_files DENIED). git via exec with CODING_GITHUB_PAT.
 - The six-repo cross-repo vocabulary + fast-lane-only handling (PR but no Linked-PR marker).
 - feature_key (read+carry-forward, never recompute) + the feature-state:v1 object (you fill repos[].pr/head_sha/state).
 - Two-phase: push ALL branches, THEN open N draft PRs with symmetric Linked-PR markers (cross-repo lanes only, BRANCH refs not SHAs).
 - Two-commit TDD per repo (test commit then impl commit, never squashed).
 - Caps: 1200 lines/repo, <=3 cross-repo repos, ~30min wall-clock (unit kills at 35). Forbidden paths.
 - Content+vocabulary pre-flight before any clone; coverage-gap=BLOCK; CASE-catalog fail-closed; CASE-402 never in a plan.
 - Idempotency: terminal-state guard, list_pull_requests duplicate guard, pre-existing-branch reuse, retry-please re-arm. Scratch /tmp/coding-agent/feat-<N>/.
 - Kill switch ~/.openclaw/coding-agent.disabled. Slack #coding-bot C0B4C0W5WHY.
 Concise durable brief; the cron prompt has the step-by-step. Match house style.`,
  },
  {
    id: 'qa-executor-prompt',
    path: `${DEPLOY}/qa-executor-prompt.md`,
    label: 'qa-executor prompt',
    persona: 'qa-executor',
    prompt: `REWRITE the qa-executor cron prompt for loop v2 at ${DEPLOY}/qa-executor-prompt.md.
Read the CURRENT one (the OLD single-PR model): \`ssh pi@openclaw.local 'cat ~/.openclaw/qa-executor-prompt.md'\`. Keep its house style, the EARLY-EXIT token discipline, cap-5, and the Slack/stdout patterns. But change the MODEL to loop v2 per SHARED-SPEC §3/§8/§12:
 - The unit is now an UMBRELLA tracker carrying a feature-state:v1 object + a coding-agent-feature-ready:v1 sentinel (the PR set). The OLD triggers (status:accepted, "🤖 Pushed", single-PR <!-- integration-test-results:v1 -->) are GONE.
 - EARLY-EXIT: first calls = list_issues for needs:qa-executor, then for umbrellas in status:in-progress / status:ready-for-code that carry a coding-agent-feature-ready:v1 sentinel. If none, exit silent.
 - For each eligible umbrella: read the latest feature-state:v1 to get repos{} (each repo's pr number + lane) and feature_key. For the cross-repo participants, find the CI's \`<!-- cross-repo-test-results:v1 -->\` comment on the ORIGINATING code PR (check the repos[].pr PRs via github-code issue_read/pull_request_read; the cross-repo lane posts it on the originating PR). Also note each repo's own fast-lane status where relevant.
 - Skip-already-reported: compare your latest qa-execution-report created_at vs the latest cross-repo-test-results created_at (one report per CI run).
 - OUTPUTS (comments only — you have NO label power):
   1. a \`<!-- qa-execution-report:v1 -->\` comment on the UMBRELLA summarizing the cross-repo lane result (per-CASE pass/fail/skip/not-impl table + summary + CI run link + source-comment link).
   2. a fresh \`<!-- feature-state:v1 -->\` comment that carries engineering's fields forward VERBATIM and updates gating_cases pass/fail status (this is the §3 qa-executor responsibility). Do NOT change labels, terminal, or human_locked.
   3. When the cross-repo lane is GREEN, end the report with an @engineering line: "all gating cases green — please flip status:ready-for-group-merge" (engineering owns the label; coding-agent already requested it).
 - Confirmed tool names: github-rw {list_issues, issue_read[get_comments], add_issue_comment, search_issues}; github-code {issue_read[get_comments], pull_request_read, list_pull_requests, search_issues}; mcp__openclaw__message. NO write/edit/exec, NO labels/create/close.
 - KILL SWITCH as first content: if \`~/.openclaw/qa-executor.disabled\` exists, output \`qa-executor disabled by kill switch.\` and STOP. Slack #qa-executor-bot C0B4DQL8SF4.
Author the full prompt.`,
  },
  {
    id: 'qa-executor-context',
    path: `${DEPLOY}/workspaces/qa-executor/CONTEXT.md`,
    label: 'qa-executor CONTEXT',
    persona: 'qa-executor',
    prompt: `REWRITE the qa-executor CONTEXT.md for loop v2 at ${DEPLOY}/workspaces/qa-executor/CONTEXT.md.
Read the current one: \`ssh pi@openclaw.local 'cat ~/.openclaw/workspaces/qa-executor/CONTEXT.md'\`. Keep house style + the "you are the bridge from CI back to the planning issue" framing, but update the pipeline to v2:
 - You sit downstream of coding-agent + the cross-repo CI lane. Trigger = an umbrella with a coding-agent-feature-ready:v1 sentinel; data source = the \`<!-- cross-repo-test-results:v1 -->\` comment on the originating code PR; outputs = a qa-execution-report:v1 on the umbrella AND a fresh feature-state:v1 comment updating gating_cases.
 - You read the umbrella's feature-state to find the PR set (repos[].pr) and feature_key. You comment only — engineering owns labels; coding-agent requested status:ready-for-group-merge; you signal green via an @engineering line.
 - Distinguish from qa (writes the plan) and qa-author (writes the real CASE code).
 - The qa-execution-report:v1 + feature-state:v1 formats; the corrected tool whitelist (read both github-rw and github-code; no writes beyond comments). Kill switch ~/.openclaw/qa-executor.disabled. Slack C0B4DQL8SF4.`,
  },
  {
    id: 'install-expert-prompt',
    path: `${DEPLOY}/install-expert-prompt.md`,
    label: 'install-expert prompt',
    persona: 'install-expert',
    prompt: `REWRITE the install-expert cron prompt with the v2 LABEL-BASED IDEMPOTENCY redesign at ${DEPLOY}/install-expert-prompt.md.
Read the current one: \`ssh pi@openclaw.local 'cat ~/.openclaw/install-expert-prompt.md'\`. Read the v2 guard spec in ${ROOT}/../agentic-dev-loop.md (search "install-expert idempotency redesign (v2)") — implement it faithfully:
 1. Dedup key = machine-stable token, NOT prose. Tracker title \`[install-pattern] owner/repo#NNN — <service>\`; labels \`service:install-pattern\` + \`pr:owner-repo-NNN\` set ONCE at create. (Body is omitted by list_issues; rely on title+labels, and pin search_issues when a body read is unavoidable.)
 2. FLAGGED via per-PR TARGETED search (not a bulk 30-item page): for each candidate owner/repo#N, \`mcp__github-code__search_issues\` style query against jarvis-roadmap "is:issue label:pr:owner-repo-N" (all states). Match FULLY-QUALIFIED owner/repo#N only (bare PR numbers collide across 50+ repos).
 3. Idempotency keyed on (PR + head SHA + surface): tracker body records tracked-pr-sha + surfaces-checked; a tracked PR re-enters scope ONLY if its head SHA changed; a not-yet-tracked PR is always in scope.
 4. Fail closed + hard caps: targeted-search error => do NOT create (skip+log). <=1 tracker/run, on top of the existing <=5 PRs/run scan cap.
 5. Close the loop with LABELS not comments: apply \`needs-triage\` once at create (engineering/Alex's fix-queue). A label-only RESOLUTION SWEEP (separate from the UNCHECKED scan, NEVER comments) flips \`needs-triage\`->\`install-expert:resolved\` once when the mirror merge is detected, sending ONE Slack ping gated on the absent->present transition. \`label:install-expert:resolved is:open\` = safe-to-bulk-close queue.
 6. Re-comment ban: add_issue_comment on an existing tracker is FORBIDDEN; status/resolution is expressed only via idempotent labels (add_labels_to_issue is a no-op if present).
 Use confirmed tool names: github-rw {list_issues, search_issues, create_issue, add_issue_comment (NEW trackers only), add_labels_to_issue}; github-code read tools for PR diffs (get_pull_request_diff/list_pull_request_files/get_file_contents/list_pull_requests/search_issues). KILL SWITCH first: if \`~/.openclaw/install-expert.disabled\` exists, output \`install-expert disabled by kill switch.\` and STOP. Slack #install-bot C0B5QHC4G4B. Keep the EARLY-EXIT discipline + cap 5.`,
  },
  {
    id: 'install-expert-context',
    path: `${DEPLOY}/workspaces/install-expert/CONTEXT.md`,
    label: 'install-expert CONTEXT',
    persona: 'install-expert',
    prompt: `UPDATE the install-expert CONTEXT.md for the v2 idempotency redesign at ${DEPLOY}/workspaces/install-expert/CONTEXT.md.
Read the current one: \`ssh pi@openclaw.local 'cat ~/.openclaw/workspaces/install-expert/CONTEXT.md'\`. Keep the accurate "drift patterns" list + scope + house style. REPLACE the idempotency section with the v2 design (label-based, per-(PR+SHA+surface) keying, machine-stable title token + pr:owner-repo-NNN label, targeted per-PR search not bulk page, RESOLUTION SWEEP with labels only, re-comment ban, fail-closed, <=1 tracker/run). Reference the agentic-dev-loop.md v2 guard spec. Confirmed tool names. Kill switch ~/.openclaw/install-expert.disabled.`,
  },
  {
    id: 'webhook',
    path: `${ROOT}/deploy/webhook/main.py`,
    label: 'webhook receiver',
    persona: 'webhook',
    prompt: `REWRITE the GitHub webhook receiver for loop v2 at ${ROOT}/deploy/webhook/main.py.
Read the current one: \`ssh pi@openclaw.local 'cat ~/jarvis-webhook-receiver/main.py'\`. KEEP verbatim: the FastAPI app, HMAC verification (compare_digest on X-Hub-Signature-256), the jarvis-roadmap repo gate, the fire-and-forget invoke_persona() via asyncio.create_subprocess_exec to /usr/bin/openclaw agent (stdout/stderr DEVNULL), the health endpoints. UPDATE the dispatch() routes to loop v2 (the current routes are broken: Route 1 invokes a "qa" agent + ~/.openclaw/qa-prompt.md that match the NEW qa, good, but it triggers on status:accepted — change to status:locked; Route 2 keys on "🤖 Pushed" which no longer exists):
 - Route 1: event=issues, action=labeled, label.name == "status:locked" (Alex's GO), repo jarvis-roadmap -> invoke persona "qa" (message: run the QA pass on this umbrella now; contract at ~/.openclaw/qa-prompt.md + ~/.openclaw/workspaces/qa/CONTEXT.md).
 - Route 2: event=issue_comment, action=created, comment body whose FIRST line is exactly "<!-- coding-agent-feature-ready:v1 -->", repo jarvis-roadmap -> invoke persona "qa-executor" (message: coding-agent just opened the coordinated PR set; begin polling each PR for <!-- cross-repo-test-results:v1 --> and mirror onto the umbrella per your contract).
 - Route 3 (interrupts): event=issues, action=labeled, label.name in {needs:engineering, needs:qa, needs:coding-agent, needs:qa-executor}, repo jarvis-roadmap -> invoke the matching persona (strip the "needs:" prefix) with an interrupt message (handle the needs:* interrupt on this issue per your Step 0).
 Update the module docstring + the /health "phase" to 2 and the header comment to reflect three routes. Keep it valid, runnable Python 3 (FastAPI). Do not add new dependencies.`,
  },
]

const AUTHOR_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'wrote', 'summary'],
  properties: {
    id: { type: 'string' },
    wrote: { type: 'boolean', description: 'true if the file was written to the exact path' },
    summary: { type: 'string', description: 'one-paragraph summary of what was produced + key decisions' },
    corrections_applied: { type: 'array', items: { type: 'string' } },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'verdict', 'findings'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['pass', 'needs-fix'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'issue', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          issue: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
  },
}

const FIX_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'applied', 'notes'],
  properties: {
    id: { type: 'string' },
    applied: { type: 'boolean' },
    notes: { type: 'string' },
    residual_risks: { type: 'array', items: { type: 'string' } },
  },
}

const results = await pipeline(
  items,
  // Stage 1 — author
  (item) => agent(`${PREAMBLE}\n\n=== YOUR ARTIFACT: ${item.label} (${item.persona}) ===\n${item.prompt}`,
    { label: `author:${item.id}`, phase: 'Author', schema: AUTHOR_SCHEMA }),
  // Stage 2 — adversarial review
  (authored, item) => agent(
`Adversarially REVIEW the loop-v2 artifact just written at ${item.path} (persona: ${item.persona}, ${item.label}).
Read: the file at ${item.path}; ${VF}; ${SPEC}. ${item.id.startsWith('triage') || item.id === 'qa-prompt' || item.id === 'coding-prompt' ? `Also Read the staged source ${ROOT}/${item.id === 'triage-prompt' ? 'triage' : item.id === 'qa-prompt' ? 'qa' : 'coding'}-prompt.v2.md to confirm NO section was dropped/altered beyond the listed corrections.` : ''}
Check, and report each problem as a finding with an EXACT fix:
1. TOOL NAMES: every roadmap label op uses add_labels_to_issue / remove_label_from_issue (NEVER issue_write for labels); issue_write only for close/state; no hedging/ToolSearch-fallback language about tool names; only confirmed tools in the whitelist; the persona's tool set matches VERIFIED-FACTS (e.g. qa & qa-executor have NO label power; coding-agent has no labels/create and no merge/update/push_files).
2. CHANNEL: the Slack channel id is correct for ${item.persona} (engineering C0B4C4XJ9L1, qa C0B3WKBPSJ3, coding-agent C0B4C0W5WHY, qa-executor C0B4DQL8SF4, install-expert C0B5QHC4G4B).
3. KILL SWITCH present + correct filename (~/.openclaw/${item.persona === 'webhook' ? 'N/A — webhook has no kill switch' : item.persona + '.disabled'}).
4. SPEC CONFORMANCE: feature-state schema, ready-gate ordering (coverage-gap condition 0 FIRST), CASE-402 never listed by qa, six-repo vocabulary, terminal-state guard on the interrupt path too, latest-wins sentinels, sentinel first-line rule. (Where applicable to this artifact.)
5. NO references to nonexistent files/agents/paths; CASE catalog path = /home/pi/code/jarvis/jarvis-integration-tests/tests/CASE_CATALOG.json; mirror = /home/pi/code/jarvis/<repo>.
6. For webhook main.py: valid Python, HMAC + repo-gate + fire-and-forget preserved, the three v2 routes correct (status:locked->qa, coding-agent-feature-ready first-line->qa-executor, needs:* ->persona), no new deps.
7. Internal consistency + completeness; no placeholders/TODOs; no stale "QA coming"/"persona doesn't exist" claims.
Be strict: a wrong tool name or a dropped section is a blocker. Return verdict needs-fix if ANY blocker/major exists.`,
    { label: `review:${item.id}`, phase: 'Review', schema: REVIEW_SCHEMA }),
  // Stage 3 — apply fixes
  (review, item) => {
    if (!review || review.verdict === 'pass') {
      return { id: item.id, applied: false, notes: 'review passed — no fix needed', residual_risks: [] }
    }
    return agent(
`Apply these review findings to the loop-v2 artifact at ${item.path}. Read the file + ${VF} + ${SPEC}, make ONLY the fixes listed (and any directly-implied corrections), and re-Write the COMPLETE corrected file to ${item.path}. Do not introduce new issues; preserve everything that was correct.

FINDINGS:
${JSON.stringify(review.findings, null, 2)}

Confirm the non-negotiable tool-name rule holds after your edits (add_labels_to_issue / remove_label_from_issue for labels; issue_write close-only). Return what you changed + any residual risks.`,
      { label: `fix:${item.id}`, phase: 'Fix', schema: FIX_SCHEMA })
  },
)

// Final phase — holistic cross-artifact consistency check
phase('Consistency')
const fileList = items.map((i) => `- ${i.persona}: ${i.path}`).join('\n')
const consistency = await agent(
`Holistic CROSS-ARTIFACT consistency review of the loop-v2 deployment set. Read ${VF} and ${SPEC}, then read ALL of these files:
${fileList}

Verify they fit together as ONE coherent loop (not just individually correct):
1. Sentinel names match across personas: engineering-triage-breakdown:v1, feature-state:v1, qa-test-plan:v1, coding-agent-feature-ready:v1, cross-repo-test-results:v1, clarify:v1, retry-please:v1. Each producer/consumer agrees.
2. The handoffs line up: engineering ready-gate consumes qa's qa-test-plan yaml block (proposed_cases empty + integration_cases valid); coding-agent consumes engineering's breakdown branch-set + feature-state + qa plan; qa-executor consumes cross-repo-test-results and updates gating_cases.
3. The webhook routes match the contracts' triggers (status:locked -> qa is the go; coding-agent-feature-ready -> qa-executor; needs:* -> persona).
4. Label ownership: ONLY engineering writes status:* labels; qa/qa-executor/coding-agent are comment-only on the tracker.
5. Channel IDs consistent with VERIFIED-FACTS across every artifact.
6. The coverage-gap loop is closed: qa BLOCKs on a missing CASE -> qa-author is the agent that adds the CASE -> retry-please re-arms. Confirm the contracts reference this correctly (qa parks; qa-author independently enriches; nobody else invents CASES).
Report any cross-file mismatch as a finding with the file + exact fix. List the final set with a one-line status each.`,
  { label: 'cross-artifact-consistency', phase: 'Consistency', schema: {
    type: 'object', additionalProperties: false, required: ['coherent', 'findings', 'file_status'],
    properties: {
      coherent: { type: 'boolean' },
      findings: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['file', 'issue', 'fix'], properties: { file: { type: 'string' }, issue: { type: 'string' }, fix: { type: 'string' } } } },
      file_status: { type: 'array', items: { type: 'string' } },
    },
  } })

return {
  authored: results.map((r) => r && r.id).filter(Boolean),
  reviews: results.length,
  consistency,
}
