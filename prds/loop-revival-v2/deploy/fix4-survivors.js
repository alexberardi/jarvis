export const meta = {
  name: 'loop-v2-fix4-survivors',
  description: 'Migrate product/marketing/doc-expert to github-mcp-server 1.0.4 tool names (preserve role/logic)',
  phases: [{ title: 'Migrate' }, { title: 'Verify' }],
}

const D = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/openclaw'
const VF = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/VERIFIED-FACTS.md'

const MIG = `### github-mcp-server 1.0.4 TOOL SURFACE — VERIFIED live (2026-06-23). The OLD discrete tools DO NOT EXIST; migrate every reference:
- create_issue                       → issue_write (method "create"; title, body, labels:[...])
- add_labels_to_issue / remove_label_from_issue / remove_label → issue_write (method "update", labels = FULL REPLACEMENT set; FIRST read current labels via issue_read method "get_labels", merge, write the complete set; never partial)
- update_issue / close               → issue_write (method "update"; state="closed", state_reason="not_planned"; omit labels to leave them)
- get_issue                          → issue_read (method "get")
- list_issue_comments/get_issue_comments → issue_read (method "get_comments")
- get_pull_request                   → pull_request_read (method "get")
- get_pull_request_diff              → pull_request_read (method "get_diff")
- list_pull_request_files            → pull_request_read (method "get_files")
- get_pull_request_comments/reviews/status → pull_request_read (method "get_comments"/"get_reviews"/"get_status")
UNCHANGED (keep): list_issues, search_issues, add_issue_comment, issue_read, issue_write, pull_request_read, create_pull_request, list_pull_requests, get_file_contents, search_code, list_commits, create_or_update_file, push_files.
These apply on whichever server the agent uses (mcp__github-rw__*, mcp__github-ro__*, mcp__github-code__*, mcp__github-code-ro__*) — keep the same server prefix, only change the tool name + add the method.
DEFERRED note: OpenClaw keeps less-common tools deferred — if a referenced tool isn't immediately callable, load it via ToolSearch (select:<exact name>). The common ones are active.`

const personas = [
  { id: 'product', server: 'github-rw (write)', note: 'product FILES tickets (create_issue→issue_write create) and reads (get_issue→issue_read get); keep its interrupt-only/EARLY-EXIT logic + the Slack-thread-relay + "Filing tickets" guidance verbatim except tool names. It suggests labels in the body text — that stays (it does not call label tools). Fix any "engineering persona doesn\'t exist yet / for now flag and stop" lines — engineering, qa, coding-agent NOW EXIST (it can hand off to them).' },
  { id: 'marketing', server: 'github-ro / github-code-ro (read-only)', note: 'marketing is READ-ONLY (no writes). Migrate get_issue→issue_read(get) on github-ro, and get_pull_request/get_pull_request_diff→pull_request_read(get/get_diff) on github-code-ro. Keep its scope/voice. Fix any "those personas (product/engineering/QA) don\'t exist yet" lines — they exist now.' },
  { id: 'doc-expert', server: 'github-code (write PRs) + github-rw (file tickets)', note: 'doc-expert opens DRAFT PRs to jarvis-docs (create_pull_request stays), reads PR diffs (get_pull_request_diff→pull_request_read get_diff, list_pull_request_files→pull_request_read get_files), and files type:risk roadmap tickets (create_issue→issue_write create) sometimes with labels (add_labels_to_issue→issue_write update read-modify-write). Keep its draft-PR-only/never-push-main guardrails + scope verbatim except tool names.' },
]

const MIGRATE_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['id', 'replaced', 'summary'],
  properties: {
    id: { type: 'string' },
    replaced: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
}
const VERIFY_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['all_pass', 'issues'],
  properties: {
    all_pass: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'string' } },
  },
}

phase('Migrate')
const out = await parallel(personas.map((p) => () =>
  agent(
`You are migrating the SURVIVOR persona "${p.id}" to the live github-mcp-server 1.0.4 tool surface. This is a TOOL-NAME migration ONLY — preserve the agent's role, scope, behavior, voice, and structure EXACTLY; change ONLY tool names + call shapes (and fix obviously-false "persona doesn't exist yet" team-status claims). Do NOT alter what the agent does or how it talks.

Read first: ${VF} (authoritative tool surface).

Read the persona's THREE current surfaces from the live Pi:
1. Cron prompt:    ssh pi@openclaw.local 'cat ~/.openclaw/${p.id}-prompt.md'
2. CONTEXT:        ssh pi@openclaw.local 'cat ~/.openclaw/workspaces/${p.id}/CONTEXT.md'
3. systemPromptOverride: ssh pi@openclaw.local "python3 -c \\"import json;print([a['systemPromptOverride'] for a in json.load(open('/home/pi/.openclaw/openclaw.json'))['agents']['list'] if a.get('id')=='${p.id}'][0])\\""

Persona-specific notes: ${p.note}

Apply the migration map to all three. Then WRITE the migrated files to:
- ${D}/${p.id}-prompt.md
- ${D}/workspaces/${p.id}/CONTEXT.md
- ${D}/sysprompt/${p.id}.txt   (the migrated systemPromptOverride, plain text)

${MIG}

Output each file COMPLETE (full content, not a diff). Report which old tool names you replaced and where.`,
    { label: `migrate:${p.id}`, phase: 'Migrate', schema: MIGRATE_SCHEMA })))

phase('Verify')
const verify = await agent(
`Verify the survivor migration. For each of product, marketing, doc-expert, read the 3 written files (${D}/<id>-prompt.md, ${D}/workspaces/<id>/CONTEXT.md, ${D}/sysprompt/<id>.txt). Check:
1. ZERO LIVE-USE of pre-1.0.4 tool names (create_issue, add_labels_to_issue, remove_label_from_issue, get_issue, list_issue_comments, get_pull_request_diff, list_pull_request_files, get_pull_request, update_issue) — they must be migrated to issue_write/issue_read/pull_request_read with methods. (Negations/deny-context OK.)
2. The correct SERVER PREFIX is preserved (marketing stays github-ro/github-code-ro read-only; product/doc-expert keep their write servers).
3. The agent's role/scope/behavior is UNCHANGED (only tool names differ) — flag if any behavior/scope was altered.
4. No remaining "persona doesn't exist yet" falsehoods about engineering/qa/coding-agent.
Report PASS/FAIL with file:line evidence for any remaining live-use stale name or behavior change.`,
  { label: 'verify-survivors', phase: 'Verify', schema: VERIFY_SCHEMA })

return { migrated: out.filter(Boolean).map((x) => x && x.id), verify }
