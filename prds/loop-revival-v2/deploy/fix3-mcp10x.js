export const meta = {
  name: 'loop-v2-fix3-mcp10x',
  description: 'Migrate all contracts to the github-mcp-server 1.0.4 consolidated tool surface (issue_write / issue_read / pull_request_read)',
  phases: [{ title: 'Migrate' }, { title: 'Verify' }],
}

const D = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/openclaw'
const ROOT = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2'
const SPEC = ROOT + '/SHARED-SPEC.md'
const VF = ROOT + '/deploy/VERIFIED-FACTS.md'

const MIG = `### github-mcp-server 1.0.4 TOOL SURFACE — VERIFIED via tools/list on the live Pi 2026-06-23
OpenClaw exposes ONLY these CONSOLIDATED tools. The older discrete tools DO NOT EXIST (confirmed: a call/ToolSearch for them returns "No matching deferred tools found"). Migrate EVERY reference:

REMOVED  →  USE INSTEAD
- create_issue                       → mcp__github-rw__issue_write (method "create"; pass title, body, labels:[...])
- add_labels_to_issue / remove_label_from_issue / remove_label → mcp__github-rw__issue_write (method "update", labels = FULL REPLACEMENT set). FIRST read current labels via mcp__github-rw__issue_read (method "get_labels"); compute current ± change; write the COMPLETE merged set. NEVER a partial labels list (omitted = dropped).
- update_issue / close               → mcp__github-rw__issue_write (method "update"; state="closed", state_reason="not_planned"; OMIT labels to leave them unchanged)
- get_issue                          → mcp__github-rw__issue_read (method "get")
- list_issue_comments / get_issue_comments → mcp__github-rw__issue_read (method "get_comments")  [github-code__issue_read for PRs]
- get_pull_request                   → mcp__github-code__pull_request_read (method "get")
- get_pull_request_diff              → mcp__github-code__pull_request_read (method "get_diff")
- list_pull_request_files            → mcp__github-code__pull_request_read (method "get_files")
- get_pull_request_comments          → mcp__github-code__pull_request_read (method "get_comments")
- get_pull_request_reviews / _status → mcp__github-code__pull_request_read (method "get_reviews" / "get_status")

UNCHANGED (still exist — keep): list_issues, search_issues, add_issue_comment, issue_read (get/get_comments/get_labels), issue_write, pull_request_read, create_pull_request, list_pull_requests, merge_pull_request, update_pull_request, get_file_contents, list_commits, create_or_update_file, push_files, search_code.

DEFERRED-TOOL NOTE: OpenClaw keeps less-common tools "deferred". The common ones (list_issues, issue_read, add_issue_comment, issue_write, pull_request_read, create_pull_request, list_pull_requests) are ACTIVE. If you reference any other tool and it is not immediately callable, load it first with ToolSearch (select:<exact tool name>).`

const items = [
  {
    id: 'eng-sysprompt', file: `${D}/sysprompt/engineering.txt`,
    work: `Fix ${D}/sysprompt/engineering.txt — this is the engineering persona's INJECTED system prompt (it's currently WRONG: it says "You OWN all status:* labels via mcp__github-rw__add_labels_to_issue / mcp__github-rw__remove_label_from_issue, and close via issue_write"). Replace that with the 1.0.4 reality: engineering owns all status:* labels + create + close via mcp__github-rw__issue_write — labels via method "update" with a FULL-SET-REPLACE labels array (read current labels first via mcp__github-rw__issue_read method "get_labels", then write the merged full set); create via method "create"; close via method "update" state="closed". There are NO discrete add_labels_to_issue/remove_label_from_issue/create_issue tools. Keep the rest of the sysprompt (identity, guardrails, delivery, slack relay) intact. Apply the migration map below to any other stale tool name. ${MIG}`,
  },
  {
    id: 'triage', file: `${D}/triage-prompt.md`,
    work: `Audit + finish the 1.0.4 migration in ${D}/triage-prompt.md. fix2 already converted LABEL ops to the issue_write read-modify-write convention (the "## Label & close operations" section) — KEEP that. NOW also: (a) migrate the unrelated-split CREATE path: any mcp__github-rw__create_issue → mcp__github-rw__issue_write (method "create", title/body/labels). (b) confirm CLOSE uses issue_write(method update, state=closed, state_reason=not_planned). (c) ensure the Tool whitelist lists ONLY 1.0.4 tools (issue_read [get_comments/get_labels], issue_write [create/update/labels/close], list_issues, search_issues, add_issue_comment, Read, message). (d) add the one-line deferred-tool note. Apply the full migration map to any other stale name. ${MIG}`,
  },
  {
    id: 'eng-context', file: `${D}/workspaces/engineering/CONTEXT.md`,
    work: `Finish the 1.0.4 migration in ${D}/workspaces/engineering/CONTEXT.md. fix2 converted labels to issue_write — keep. Also migrate create_issue → issue_write(method create) in the unrelated-split note + tool table; ensure the tool table lists only 1.0.4 tools; add the deferred-tool note. ${MIG}`,
  },
  {
    id: 'install-expert', file: `${D}/install-expert-prompt.md + ${D}/workspaces/install-expert/CONTEXT.md`,
    work: `FULL 1.0.4 migration of install-expert — both ${D}/install-expert-prompt.md AND ${D}/workspaces/install-expert/CONTEXT.md. install-expert is BROKEN on 1.0.4 (its whole label-resolution + tracker-creation + PR-diff workflow uses removed tools). Migrate:
- create_issue (tracker creation) → mcp__github-rw__issue_write (method "create", title, body, labels:[service:install-pattern, pr:owner-repo-NNN, needs-triage]).
- add_labels_to_issue / remove_label_from_issue (the RESOLUTION SWEEP: flip needs-triage→install-expert:resolved) → mcp__github-rw__issue_write (method "update", labels=FULL set). READ current labels first via mcp__github-rw__issue_read (method "get_labels"); compute the merged set; write it. NEVER partial. (This preserves the idempotency design — label add is a no-op if already in the read set.)
- PR diff/files reads (get_pull_request_diff, list_pull_request_files, get_pull_request) → mcp__github-code__pull_request_read (method "get_diff" / "get_files" / "get"). get_file_contents stays. search_issues stays. list_pull_requests stays.
- Update both tool whitelists to 1.0.4 names; add the deferred-tool note.
Preserve the v2 idempotency LOGIC exactly (per-PR targeted search, machine-stable title token, pr:owner-repo-NNN label, <=1 tracker/run, fail-closed, re-comment ban, RESOLUTION SWEEP via labels). Only the TOOL NAMES change. ${MIG}`,
  },
  {
    id: 'qa-and-rest', file: `${D}/workspaces/qa/CONTEXT.md + ${D}/qa-prompt.md + ${D}/coding-prompt.md + ${D}/workspaces/coding-agent/CONTEXT.md + ${D}/qa-executor-prompt.md + ${D}/workspaces/qa-executor/CONTEXT.md`,
    work: `Audit these 6 files for ANY pre-1.0.4 tool name and migrate per the map. Specific known issues: ${D}/workspaces/qa/CONTEXT.md lines ~252-256 present add_labels_to_issue/remove_label_from_issue as "confirmed live names" — replace that whole block: the ONLY label/create/close tool is mcp__github-rw__issue_write (engineering-only; qa has NONE of it). Then audit qa-prompt.md, coding-prompt.md, coding-agent/CONTEXT.md, qa-executor-prompt.md, qa-executor/CONTEXT.md for stale read-tool names (get_pull_request*, get_issue, list_issue_comments) and convert to pull_request_read(method ...) / issue_read(method ...). These personas are read/comment-only on the tracker — do NOT give them issue_write; where they note they "can't label", they should reference issue_write (engineering's tool) as the thing they lack. coding-agent + qa-executor already use pull_request_read/issue_read correctly — just verify + fix any straggler. Add the deferred-tool note where a tool whitelist exists. ${MIG}`,
  },
  {
    id: 'docs', file: `${VF} + ${SPEC}`,
    work: `Finalize the tool-surface truth in ${VF} and ${SPEC} §13. ${VF} was already partly corrected (it notes issue_write for labels). Make it COMPLETE + authoritative: add the full migration map (create_issue→issue_write create; get_pull_request*→pull_request_read methods; get_issue→issue_read get; list_issue_comments→issue_read get_comments), and the DEFERRED-TOOL/ToolSearch note. Update the github-code section's pull_request_read method enum: [get, get_diff, get_status, get_files, get_review_comments, get_reviews, get_comments, get_check_runs]. ${SPEC} §13: align engineering's toolset to issue_write (create/update/labels/close) + issue_read (get_comments/get_labels); note no discrete create/label tools in 1.0.4. ${MIG}`,
  },
]

const FIX_SCHEMA = { type: 'object', additionalProperties: false, required: ['id', 'summary'],
  properties: { id: { type: 'string' }, summary: { type: 'string' }, migrated_names: { type: 'array', items: { type: 'string' } } } }

phase('Migrate')
const fixes = await parallel(items.map((it) => () =>
  agent(`You are migrating loop-v2 agent contracts to the LIVE github-mcp-server 1.0.4 consolidated tool surface. Read the target file(s), apply the migration with Edit/Write, preserve ALL logic/structure — only tool NAMES + call shapes change. Be exhaustive; miss no occurrence.

${it.work}`,
    { label: `migrate:${it.id}`, phase: 'Migrate', schema: FIX_SCHEMA })))

phase('Verify')
const verify = await agent(
`Verify the github-mcp-server 1.0.4 migration is COMPLETE across the loop-v2 deploy artifacts. Read ${VF} (the authoritative tool surface), then grep the entire deploy dir ${D} (all .md + sysprompt/*.txt) for EVERY pre-1.0.4 tool name: add_labels_to_issue, remove_label_from_issue, remove_label, create_issue, update_issue, get_issue, list_issue_comments, get_issue_comments, get_pull_request_diff, list_pull_request_files, get_pull_request_comments, get_pull_request_reviews, get_pull_request (as a tool name, not the words "pull request").
For EACH remaining hit, classify it: (NEGATION) "this tool does NOT exist / removed" = OK; (DENY-LIST) an explicit deny entry = OK; (LIVE-USE) the text instructs the agent to CALL it as a real tool = FAIL (must be migrated). Report every LIVE-USE hit as file:line with the needed fix.
Also confirm: engineering's sysprompt (sysprompt/engineering.txt) now routes labels/create/close through issue_write (not the discrete tools); install-expert prompt+CONTEXT use issue_write for create+labels and pull_request_read for PR diffs; qa/CONTEXT no longer presents discrete label tools as live. Report PASS only if ZERO LIVE-USE hits remain.`,
  { label: 'verify-mcp10x', phase: 'Verify', schema: {
    type: 'object', additionalProperties: false, required: ['all_pass', 'live_use_hits', 'checks'],
    properties: {
      all_pass: { type: 'boolean' },
      live_use_hits: { type: 'array', items: { type: 'string' } },
      checks: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['check', 'pass'], properties: { check: { type: 'string' }, pass: { type: 'boolean' }, note: { type: 'string' } } } },
    } } })

return { migrated: fixes.filter(Boolean).map((f) => f && f.id), verify }
