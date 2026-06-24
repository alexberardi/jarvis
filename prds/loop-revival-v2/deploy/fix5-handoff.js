export const meta = {
  name: 'loop-v2-fix5-handoff',
  description: 'Auto hand-off engineering→qa: engineering sets needs:qa on spec-complete; qa plans on needs:qa',
  phases: [{ title: 'Edit' }, { title: 'Verify' }],
}

const D = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/openclaw'
const WEBHOOK = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/webhook/main.py'
const VF = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/VERIFIED-FACTS.md'

const DESIGN = `THE AUTO-HANDOFF STATE MACHINE (engineering→qa, no human step between):
- engineering, after writing a COMPLETE Doable/Doable-with-caveats breakdown (ambiguities_open==0) + the feature-state object, AND when there is NO current qa-test-plan (none exists, OR the latest qa-test-plan is OLDER than the latest breakdown): SET the \`needs:qa\` label (the hand-off signal) together with \`status:accepted\`. This hands the feature to qa immediately — it does NOT wait for Alex's \`status:locked\`.
- qa runs on \`needs:qa\` (its scan now includes it) and writes/refreshes the \`<!-- qa-test-plan:v1 -->\` via its normal plan-writing flow (breakdown present + plan missing/stale → write the plan; or PARK with proposed_cases on a coverage gap). qa has NO label power, so it does NOT clear needs:qa.
- engineering, on a later run, once a CURRENT qa-test-plan exists (newer than the breakdown): REMOVE \`needs:qa\` (qa's job is done). THEN run the ready-gate — if \`status:locked\` is present + plan-ready + ambiguities==0 + branch set → \`status:ready-for-code\`; if the plan carries non-empty proposed_cases → \`status:blocked\` + \`needs:alex\` (coverage-gap park) and remove needs:qa.
- Net flow: eng spec done → needs:qa → qa plans → eng removes needs:qa → [Alex reviews breakdown+plan, sets status:locked] → eng ready-gate → status:ready-for-code → coding-agent. The human lock gates CODING, not PLANNING.
LABEL OPS reminder (github-mcp-server 1.0.4): set/remove labels via mcp__github-rw__issue_write (method "update", FULL-SET REPLACE — read current via issue_read method "get_labels" first, then write the merged set). Never partial.`

const items = [
  {
    id: 'engineering', files: 'triage-prompt.md + workspaces/engineering/CONTEXT.md + sysprompt/engineering.txt',
    work: `Add the engineering side of the auto-handoff to ${D}/triage-prompt.md, ${D}/workspaces/engineering/CONTEXT.md, and ${D}/sysprompt/engineering.txt.
In triage-prompt.md, in Step 7 (the ready-gate / status section) and Step 6 (feature-state) as appropriate:
- When a Doable breakdown is complete (ambiguities_open==0) + feature-state written + NO current qa-test-plan (missing or older than the latest breakdown): SET \`needs:qa\` (via the §Label & close operations read-modify-write) alongside \`status:accepted\`. This is the auto hand-off — do NOT wait for status:locked.
- When a CURRENT qa-test-plan exists (newer than the latest breakdown): REMOVE \`needs:qa\` (qa done), THEN proceed with the existing ready-gate logic (status:ready-for-code if locked+plan-ready; status:blocked+needs:alex if proposed_cases non-empty — also remove needs:qa in the park case).
- Do NOT set needs:qa if a current plan already exists, and do NOT set it on Needs-design/Impossible verdicts.
Keep the existing Step-0 needs:engineering interrupt handling + everything else intact. Reflect the hand-off briefly in engineering/CONTEXT.md (the label vocabulary / flow section) and in sysprompt/engineering.txt (one line under the loop-v2 unit-of-work or guardrails: "When a spec is complete and unplanned, hand off to qa by setting needs:qa; clear it once qa's plan exists.").
${DESIGN}`,
  },
  {
    id: 'qa', files: 'qa-prompt.md + workspaces/qa/CONTEXT.md + sysprompt/qa.txt',
    work: `Add the qa side of the auto-handoff to ${D}/qa-prompt.md, ${D}/workspaces/qa/CONTEXT.md, and ${D}/sysprompt/qa.txt.
In qa-prompt.md Step 1 (the candidate scan): ADD \`needs:qa\` as a primary trigger label, alongside the existing status:locked / status:ready-for-code / status:in-progress (which stay for the post-lock refresh path). A feature labeled \`needs:qa\` with a complete breakdown is the engineering→qa hand-off — process it through the NORMAL plan-writing flow (the same eligibility checks: breakdown present, no current/owed plan, repos non-empty, ambiguities resolved) and write/refresh the \`<!-- qa-test-plan:v1 -->\`. qa is no longer gated on status:locked — it plans as soon as engineering hands off.
- Clarify that qa does NOT (cannot) clear needs:qa — engineering removes it once the plan is current. So qa simply writes the plan; if its plan is already current vs the breakdown, it skips (no re-plan), and a lingering needs:qa is harmless (engineering clears it next pass).
- If a needs:qa feature has NO breakdown yet (edge case), qa skips it (nothing to plan) rather than treating it as a Step-0 interrupt to acknowledge.
- The existing Step 0 needs:qa interrupt path: keep it, but note that the COMMON needs:qa case is the engineering hand-off → plan-writing (Step 1+), not a bare acknowledgement. (If both the breakdown-present plan path and the interrupt path could apply, prefer writing the plan.)
Reflect the change in qa/CONTEXT.md (trigger section) and sysprompt/qa.txt (one line: "You run on needs:qa — the engineering→qa hand-off — and write the per-feature test plan; you don't wait for status:locked.").
${DESIGN}`,
  },
  {
    id: 'webhook', files: 'webhook/main.py',
    work: `Refine ${WEBHOOK} so the needs:qa webhook hand-off drives PLAN-WRITING. The webhook already has a Route firing the matching persona on needs:* labels (Route 3, interrupts). For the needs:qa case specifically, the invocation message should instruct qa to run its NORMAL test-plan flow on that umbrella (write/refresh the qa-test-plan), not merely acknowledge an interrupt — because needs:qa is now the engineering→qa hand-off. Adjust the needs:qa branch's message text accordingly (keep needs:engineering / needs:coding-agent / needs:qa-executor as interrupt acknowledgements). Keep Route 1 (status:locked→qa, for the post-lock refresh) and Route 2 (coding-agent-feature-ready→qa-executor) intact. Keep HMAC + repo-gate + fire-and-forget. Valid Python 3, no new deps. (Read ${VF} for the persona/contract facts if needed.)`,
  },
]

const EDIT_SCHEMA = { type: 'object', additionalProperties: false, required: ['id', 'summary'],
  properties: { id: { type: 'string' }, summary: { type: 'string' }, files_changed: { type: 'array', items: { type: 'string' } } } }

phase('Edit')
const edits = await parallel(items.map((it) => () =>
  agent(`Implement a precise contract change (the engineering→qa auto-handoff). Read the target file(s), apply surgical Edits, preserve everything else (all existing logic, the 1.0.4 tool surface, kill switches, channels). This is an ADDITION (the needs:qa hand-off), not a rewrite.

${it.work}`,
    { label: `edit:${it.id}`, phase: 'Edit', schema: EDIT_SCHEMA })))

phase('Verify')
const verify = await agent(
`Verify the engineering→qa auto-handoff is coherent and complete across ${D}/triage-prompt.md, ${D}/workspaces/engineering/CONTEXT.md, ${D}/sysprompt/engineering.txt, ${D}/qa-prompt.md, ${D}/workspaces/qa/CONTEXT.md, ${D}/sysprompt/qa.txt, ${WEBHOOK}. Check:
1. engineering SETS needs:qa exactly when (Doable breakdown complete + ambiguities==0 + no current qa-test-plan), via issue_write read-modify-write; and REMOVES needs:qa once a current plan exists (and in the coverage-gap park case). It does NOT set needs:qa when a current plan already exists or on Needs-design/Impossible.
2. qa SCANS needs:qa and processes it through normal plan-writing (not just Step-0 acknowledge); qa is no longer gated on status:locked for initial planning; qa does not try to clear needs:qa (no label power).
3. No infinite loop: once qa's plan is current, engineering removes needs:qa and it is not re-set (engineering's set-condition requires "no current plan").
4. The lock still gates CODING (status:ready-for-code needs status:locked) — the handoff did NOT remove the human lock gate before coding.
5. webhook needs:qa branch tells qa to write the plan; Routes 1/2 intact; HMAC/repo-gate/fire-and-forget intact; valid Python.
Report PASS/FAIL per check with file:line evidence; flag any loop risk or contradiction.`,
  { label: 'verify-handoff', phase: 'Verify', schema: {
    type: 'object', additionalProperties: false, required: ['all_pass', 'checks'],
    properties: { all_pass: { type: 'boolean' }, checks: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['check', 'pass', 'evidence'], properties: { check: { type: 'string' }, pass: { type: 'boolean' }, evidence: { type: 'string' } } } } } } })

return { edits: edits.filter(Boolean).map((e) => e && e.id), verify }
