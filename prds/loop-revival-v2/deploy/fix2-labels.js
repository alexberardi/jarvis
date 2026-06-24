export const meta = {
  name: 'loop-v2-fix2-labels',
  description: 'Fix label ops to use issue_write read-modify-write (github-mcp-server 1.0.4 has no discrete label tools)',
  phases: [{ title: 'Fix' }, { title: 'Verify' }],
}

const D = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/openclaw'
const ROOT = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2'
const SPEC = ROOT + '/SHARED-SPEC.md'
const VF = ROOT + '/deploy/VERIFIED-FACTS.md'

const CONV = `LABEL/CLOSE OPS — github-mcp-server 1.0.4 reality (VERIFIED live on the Pi 2026-06-23):
There are NO discrete \`add_labels_to_issue\` / \`remove_label_from_issue\` tools. ALL label changes AND issue close/state go through \`mcp__github-rw__issue_write\` (method \`update\`). Its \`labels\` array is a FULL-SET REPLACE — whatever you pass becomes the issue's COMPLETE label set; any label you omit is DROPPED. Read current labels via \`mcp__github-rw__issue_read\` (method \`get_labels\`).

Mandatory read-modify-write pattern for ANY label change:
1. READ current labels: mcp__github-rw__issue_read (method "get_labels", owner="alexberardi", repo="jarvis-roadmap", issue_number=<N>).
2. COMPUTE the new full set = current labels + label(s) to ADD − label(s) to REMOVE (preserve EVERY other existing label).
3. WRITE: mcp__github-rw__issue_write (method "update", owner, repo, issue_number, labels=<the COMPLETE new set>).
NEVER pass a partial labels list — omitting a label removes it. Always read-then-write the full set.

To CLOSE an issue without touching labels: mcp__github-rw__issue_write (method "update", state="closed", state_reason="not_planned") and OMIT the labels param (omitted ⇒ labels unchanged). To close AND change labels in one call, include both state/state_reason and the full computed labels set.`

const items = [
  {
    id: 'triage', file: `${D}/triage-prompt.md`,
    work: `Rewrite ALL label/close operations in ${D}/triage-prompt.md to the github-mcp-server 1.0.4 reality. This contract is currently BROKEN: it tells engineering to call mcp__github-rw__add_labels_to_issue / mcp__github-rw__remove_label_from_issue, which DO NOT EXIST on the live server.

DO THIS:
1. Insert a clearly-headed convention block titled "## Label & close operations (read this — github-mcp-server 1.0.4)" near the START of the label-relevant material (just before or at the top of Step 6/Step 7, wherever the first label op appears; pick the most logical single home and reference it from later steps). The block content MUST be exactly the convention below.
2. Replace EVERY occurrence of mcp__github-rw__add_labels_to_issue and mcp__github-rw__remove_label_from_issue throughout the file. Each former call becomes an instruction to apply the read-modify-write pattern from the convention. E.g. "set status:ready-for-code via mcp__github-rw__add_labels_to_issue" → "set status:ready-for-code (per §Label & close operations: read get_labels → add status:ready-for-code to the full set → issue_write update labels=<full set>)". For REMOVE (e.g. remove needs:engineering / needs:alex), say "remove <label> (read get_labels → drop <label> → issue_write update labels=<remaining full set>)".
3. The Step 0.3.e interrupt remove-label (needs:engineering) MUST use the read-modify-write pattern (this is the exact op that was failing and re-firing interrupts).
4. Closing impossible issues (Step 8) MUST use mcp__github-rw__issue_write (method update, state=closed, state_reason=not_planned) — keep/fix that. (Engineering already used issue_write for close; ensure it's method=update with state/state_reason and that it doesn't accidentally wipe labels — omit labels unless also relabeling.)
5. Update the "## Tool whitelist" section: list mcp__github-rw__issue_read (methods: get_comments AND get_labels), mcp__github-rw__issue_write (labels via full-set-replace + close/state — the ONLY label/close tool), mcp__github-rw__list_issues, mcp__github-rw__add_issue_comment, mcp__github-rw__create_issue (unrelated-split only), Read, mcp__openclaw__message. REMOVE add_labels_to_issue/remove_label_from_issue entirely (they don't exist).
6. Anywhere the prose says "engineering owns labels via add_labels_to_issue/remove_label_from_issue", change to "via issue_write (read-modify-write full set) + issue_read get_labels".

THE CONVENTION BLOCK (use verbatim as the inserted section's body):
${CONV}

Preserve all other logic/steps/templates. Output the complete corrected file.`,
  },
  {
    id: 'eng-context', file: `${D}/workspaces/engineering/CONTEXT.md`,
    work: `Update ${D}/workspaces/engineering/CONTEXT.md for the github-mcp-server 1.0.4 label reality. Wherever it references add_labels_to_issue / remove_label_from_issue (e.g. the tool table, the "you OWN all labels" note, the line near :315 about the staged contracts saying issue_write with method add_labels), correct it: engineering owns labels via mcp__github-rw__issue_write (method update, labels = FULL-SET REPLACE) + reads current labels via mcp__github-rw__issue_read (method get_labels); there are NO discrete label tools in github-mcp-server 1.0.4. Add a short note pointing to the read-modify-write convention (read get_labels → modify → write full set; never partial). Keep everything else. Output the complete file.`,
  },
  {
    id: 'facts-spec', file: `${VF} + ${SPEC}`,
    work: `Correct the stale tool facts in TWO files.
(1) ${VF}: in the github-rw tool list, REPLACE the add_labels_to_issue / remove_label_from_issue lines with the truth: "github-mcp-server 1.0.4 has NO discrete label tools. Labels + close go through mcp__github-rw__issue_write (method update; labels = FULL-SET REPLACE — read-modify-write required). Read labels via mcp__github-rw__issue_read (method get_labels)." Add a dated note: "CORRECTION 2026-06-23: the live server is github-mcp-server v1.0.4 (consolidated). The historical transcripts showed add_labels_to_issue/remove_label_from_issue from an OLDER binary; those tools no longer exist. Verified via tools/list on the live server." Also update the per-agent tools section note so it's clear engineering uses issue_write for labels and qa/coding-agent/qa-executor are barred by denying issue_write (the deny of the nonexistent label tools is harmless/no-op).
(2) ${SPEC} §13 (Toolset reality) and the "Tool-name note": update engineering's tool list to issue_write (labels full-set-replace + close) + issue_read (get_comments, get_labels); remove any add_labels/remove_label discrete-tool claims; note labels are read-modify-write via issue_write in 1.0.4.
Output BOTH complete corrected files (Edit each in place).`,
  },
  {
    id: 'deny-refs', file: `${D}/qa-prompt.md + coding-prompt.md + coding-agent/CONTEXT.md + qa-executor-prompt.md + qa-executor/CONTEXT.md`,
    work: `Fix DENY-CONTEXT label-tool references (accuracy only — these personas correctly have NO label power; just name the real tool). In each of: ${D}/qa-prompt.md, ${D}/coding-prompt.md, ${D}/workspaces/coding-agent/CONTEXT.md, ${D}/qa-executor-prompt.md, ${D}/workspaces/qa-executor/CONTEXT.md — wherever the text says the persona lacks/deny "add_labels_to_issue" / "remove_label_from_issue", update it to reference mcp__github-rw__issue_write (the consolidated label+close tool, which they do NOT have — engineering owns it). Keep these personas comment-only on the tracker. Do NOT add any label capability. Where a "do NOT call" list enumerates the nonexistent label tools, replace with "mcp__github-rw__issue_write (no label/close power — engineering owns labels)". Preserve everything else. Output each complete corrected file.`,
  },
]

const FIX_SCHEMA = { type: 'object', additionalProperties: false, required: ['id', 'summary'],
  properties: { id: { type: 'string' }, summary: { type: 'string' }, occurrences_replaced: { type: 'number' } } }

phase('Fix')
const fixes = await parallel(items.map((it) => () =>
  agent(`You are fixing loop-v2 agent contracts to match the LIVE github-mcp-server 1.0.4 tool surface. Read the target file(s), apply the changes with Edit/Write, preserve everything else. Be thorough — miss no occurrence.

${it.work}`,
    { label: `fix:${it.id}`, phase: 'Fix', schema: FIX_SCHEMA })))

phase('Verify')
const verify = await agent(
`Verify the label-tool fix is COMPLETE and correct across the loop-v2 artifacts. Read ${VF} and ${SPEC}, then:
1. grep the deploy dir ${D} for "add_labels_to_issue" and "remove_label_from_issue" — there should be ZERO remaining references (they don't exist on the server). Report any file:line that still has them.
2. Confirm ${D}/triage-prompt.md now contains the read-modify-write convention (read get_labels → modify → issue_write update full set), and that every former label op references it. Confirm close uses issue_write(method update, state=closed, state_reason=not_planned).
3. Confirm engineering CONTEXT + SHARED-SPEC §13 + VERIFIED-FACTS describe issue_write (full-set-replace) + issue_read get_labels, with no discrete-label-tool claims.
4. Confirm qa/coding-agent/qa-executor still have NO label power (their references now name issue_write as denied, and they remain comment-only).
Report PASS/FAIL per check with evidence (file:line). If any add_labels_to_issue/remove_label_from_issue remains, that's a FAIL.`,
  { label: 'verify-label-fix', phase: 'Verify', schema: {
    type: 'object', additionalProperties: false, required: ['all_pass', 'checks'],
    properties: { all_pass: { type: 'boolean' }, checks: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['check', 'pass', 'evidence'], properties: { check: { type: 'string' }, pass: { type: 'boolean' }, evidence: { type: 'string' } } } } } } })

return { fixes: fixes.filter(Boolean).map((f) => f && f.id), verify }
