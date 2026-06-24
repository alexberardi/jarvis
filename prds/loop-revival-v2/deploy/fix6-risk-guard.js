export const meta = {
  name: 'loop-v2-fix6-risk-guard',
  description: 'Stop engineering bypassing the ready-gate via the interrupt path; never code type:risk trackers',
  phases: [{ title: 'Edit' }, { title: 'Verify' }],
}

const D = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/openclaw'

const RULES = `THREE RULES TO ENCODE (a real bug: engineering set status:ready-for-code + needs:coding-agent on a type:risk install-drift tracker #44 via its interrupt path, bypassing the ready-gate — coding-agent correctly skipped, but the state was wrong):

RULE 1 — The interrupt path (Step 0) must NOT advance lifecycle. When handling a needs:* interrupt, engineering may: assess + post a comment, raise needs:alex IF it needs Alex's decision, and remove the ONE triggering needs:* label. It must NOT set or flip any status:* label (especially status:ready-for-code/status:accepted) and must NOT set needs:qa / needs:coding-agent (no routing into the pipeline) from the interrupt path. Lifecycle advancement happens ONLY through the normal triage flow (Step 4/5) + the ready-gate (Step 7). Specifically: DELETE/replace the "flip a label" wording in Step 0's "Request for action within your scope → do it (… update the feature-state object; flip a label)" — flipping status labels in the interrupt handler is the exact bug.

RULE 2 — status:ready-for-code is reachable ONLY via the Step 7b ready-gate (all conditions: empty proposed_cases + ambiguities==0 + a current qa-test-plan + a non-empty branch set + status:locked). Never from "the ambiguity is now resolved", never from the interrupt path, never as a shortcut. Reinforce this explicitly.

RULE 3 — type:risk and type:question trackers are NOT codeable feature umbrellas; neither are service:install-pattern drift trackers (install-expert files these as RISK FLAGS, not build orders). engineering NEVER sets status:accepted / status:locked / status:ready-for-code / needs:qa / needs:coding-agent on a type:risk / type:question / service:install-pattern issue. On a needs:engineering interrupt for one, engineering may assess + comment its recommendation, optionally raise needs:alex for a human decision, and clear needs:engineering — then STOP (it stays a flag for Alex to triage; if Alex wants it fixed, HE converts it into a proper type:feature status:proposed umbrella). The coding pipeline is for type:feature / type:bug / type:refactor only.`

const items = [
  {
    id: 'engineering', files: 'triage-prompt.md + workspaces/engineering/CONTEXT.md + sysprompt/engineering.txt',
    work: `Apply all three rules to ${D}/triage-prompt.md, ${D}/workspaces/engineering/CONTEXT.md, and ${D}/sysprompt/engineering.txt.
- triage-prompt.md: In Step 0 (interrupt handling), fix the "Request for action within your scope → do it" bullet — remove "flip a label" and replace with explicit allowed actions (assess + comment; raise needs:alex if a human decision is needed; remove ONLY the triggering needs:* label) and an explicit prohibition (NEVER set/flip status:* or set needs:qa/needs:coding-agent from the interrupt path; lifecycle advances only via Step 4/5 + Step 7). In Step 7b, add a one-line reinforcement that status:ready-for-code is reachable ONLY here. Add a guard (near Step 2/Step 3 classification and in the Hard rules) that type:risk / type:question / service:install-pattern trackers are NOT codeable: engineering never sets status:accepted/locked/ready-for-code/needs:qa/needs:coding-agent on them; on a needs:engineering interrupt it assesses + comments + (optionally needs:alex) + clears needs:engineering, then stops.
- engineering CONTEXT.md + sysprompt/engineering.txt: add the same guardrails concisely (interrupt path never flips status; ready-for-code only via the gate; type:risk/question/install-pattern are flags, never coded).
Preserve everything else (the 1.0.4 issue_write label ops via §Label & close, the needs:qa auto-handoff, kill switch, channel). All label ops still use the read-modify-write full-set-replace pattern.

${RULES}`,
  },
  {
    id: 'coding-agent', files: 'coding-prompt.md + workspaces/coding-agent/CONTEXT.md',
    work: `Add a DEFENSIVE guard to coding-agent (belt-and-suspenders for RULE 3) in ${D}/coding-prompt.md and ${D}/workspaces/coding-agent/CONTEXT.md.
In coding-prompt.md Step 2 (per-feature terminal-state / idempotency guard) or Step 5 (content pre-flight): add a check that SKIPS/aborts any umbrella whose type is type:risk or type:question (these are risk flags / questions, never buildable features) — even if it somehow carries status:ready-for-code. coding-agent already skips on missing breakdown/branch-set/qa-plan; this is an explicit additional guard so a mislabeled risk tracker can never be built. Note it in coding-agent/CONTEXT.md hard rules too. Preserve all other logic.

${RULES}`,
  },
]

const EDIT_SCHEMA = { type: 'object', additionalProperties: false, required: ['id', 'summary'],
  properties: { id: { type: 'string' }, summary: { type: 'string' }, changes: { type: 'array', items: { type: 'string' } } } }

phase('Edit')
const edits = await parallel(items.map((it) => () =>
  agent(`Apply a precise loop-v2 contract fix (the type:risk / ready-gate-bypass guard). Read the target file(s), make surgical Edits, preserve all other logic. This is an ADDITION of guardrails + the removal of the "flip a label" interrupt-path hole.

${it.work}`,
    { label: `edit:${it.id}`, phase: 'Edit', schema: EDIT_SCHEMA })))

phase('Verify')
const verify = await agent(
`Verify the risk-guard fix across ${D}/triage-prompt.md, ${D}/workspaces/engineering/CONTEXT.md, ${D}/sysprompt/engineering.txt, ${D}/coding-prompt.md, ${D}/workspaces/coding-agent/CONTEXT.md. Check:
1. Step 0 (engineering interrupt) NO LONGER permits flipping status:* labels — "flip a label" is gone/replaced; the interrupt path may only assess+comment, raise needs:alex, and remove the triggering needs:* label.
2. status:ready-for-code is stated to be reachable ONLY via the Step 7b ready-gate (all conditions).
3. engineering NEVER sets status:accepted/locked/ready-for-code/needs:qa/needs:coding-agent on type:risk / type:question / service:install-pattern trackers; it assesses + comments + clears needs:engineering on the interrupt and stops.
4. coding-agent has a defensive guard that skips type:risk / type:question umbrellas.
5. Nothing else broke: the needs:qa auto-handoff still works, the 1.0.4 issue_write read-modify-write label pattern is intact, kill switches/channels unchanged.
Report PASS/FAIL per check with file:line evidence; flag any contradiction (e.g., a place that still lets the interrupt path set status).`,
  { label: 'verify-risk-guard', phase: 'Verify', schema: {
    type: 'object', additionalProperties: false, required: ['all_pass', 'checks'],
    properties: { all_pass: { type: 'boolean' }, checks: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['check', 'pass', 'evidence'], properties: { check: { type: 'string' }, pass: { type: 'boolean' }, evidence: { type: 'string' } } } } } } })

return { edits: edits.filter(Boolean).map((e) => e && e.id), verify }
