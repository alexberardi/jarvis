export const meta = {
  name: 'loop-v2-fix',
  description: 'Apply the 4 cross-artifact consistency findings to the loop-v2 deploy artifacts',
  phases: [{ title: 'Fix' }, { title: 'Verify' }],
}

const D = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/deploy/openclaw'
const SPEC = '/Users/alexanderberardi/jarvis/prds/loop-revival-v2/SHARED-SPEC.md'

const F1 = `FINDING 1 (BLOCKER — silent-green hazard) ownership of case_ids / gating_cases. The staged design left these unowned: triage wrote [] and disclaimed ownership, coding-agent carried [] forward, qa-executor assumed they were already populated — so gating_cases stayed [] and qa-executor's "GREEN iff every gating case passes" was vacuously true on an empty set (a feature could report GREEN with zero cases verified).
THE DECISION TO ENCODE:
- ENGINEERING owns AND populates case_ids and gating_cases.
- On the INITIAL feature-state write (breakdown done, no qa-test-plan yet) they stay [] (feature not ready).
- At the READY-GATE write (when engineering sets status:ready-for-code) engineering MUST set case_ids = the qa-test-plan's validated integration_cases (the composition set it already validated against the catalog) AND gating_cases = the SAME list. gating_cases == case_ids: EVERY integration case must pass — do NOT gate on a subset (a subset is what allowed vacuous green). NEVER include CASE-402.
- coding-agent carries case_ids/gating_cases forward VERBATIM (it only runs on status:ready-for-code, so they're already populated).
- qa-executor annotates pass/fail on this populated set and MUST FAIL CLOSED: if gating_cases is empty/absent while a coding-agent-feature-ready sentinel exists, do NOT report GREEN — report a problem and flag @engineering ("gating_cases empty — cannot verify; engineering must populate at ready-gate"). An empty gating set is NEVER green.`

const F3 = `FINDING 3 (coverage-gap resolver attribution): replace any phrase saying the feature parks "until a human/coding-agent adds the CASE" with "until qa-author adds the CASE to the harness (and Alex re-arms via retry-please)". coding-agent is FORBIDDEN from touching the integration-tests harness; qa-author is the sole CASE author.`

const items = [
  {
    id: 'triage', files: [`${D}/triage-prompt.md`],
    work: `Apply to ${D}/triage-prompt.md:
${F1}
  In this file specifically: (a) at the "**The fields YOU (engineering) own and set here:**" list (~line 248-255) ADD bullets for \`case_ids\` and \`gating_cases\` describing the populate-at-ready-gate rule above (initial []; at ready-gate set both = qa plan's validated integration_cases; gating_cases==case_ids; never CASE-402; qa-executor later annotates pass/fail). (b) REPLACE the "**You do NOT own** \`case_ids\`/\`gating_cases\` (qa-executor + the CI mirror fill these...)" sentence (~line 259) — engineering DOES own them now; keep the composition-set derivation explanation but reframe it as what engineering writes, and keep "qa-executor later annotates pass/fail". (c) In Step 7 (~line 280, "ONLY when condition 0 holds ... set status:ready-for-code ... AND set human_locked: true in a fresh feature-state:v1 comment"), ADD that this same fresh feature-state comment MUST set case_ids = gating_cases = the validated integration_cases from condition 2. Keep the Step-6 INITIAL schema example (lines 239-240) as [] but add a short inline note that they are populated at the ready-gate write.
${F3}
  In this file: the sentence at ~line 284 ("...until a human/coding-agent adds the CASE to the harness and re-arms via...").
Do not change anything else.`,
  },
  {
    id: 'engineering-context', files: [`${D}/workspaces/engineering/CONTEXT.md`],
    work: `Apply to ${D}/workspaces/engineering/CONTEXT.md:
${F1}
  This file's §(c) already SHOWS case_ids/gating_cases populated in the schema example (good) but the surrounding ownership prose says coding-agent/qa-executor fill them. FIX the ownership prose: engineering owns + populates case_ids/gating_cases (populate-at-ready-gate = qa plan's validated integration_cases; gating_cases==case_ids; never CASE-402); coding-agent carries forward verbatim; qa-executor annotates pass/fail and fail-closes on empty. Keep the example values. Update any line implying qa-executor/CI "fill" the list to "annotate pass/fail".
Do not change anything else.`,
  },
  {
    id: 'qa-executor', files: [`${D}/qa-executor-prompt.md`, `${D}/workspaces/qa-executor/CONTEXT.md`],
    work: `Apply to ${D}/qa-executor-prompt.md AND ${D}/workspaces/qa-executor/CONTEXT.md:
${F1}
  Add the FAIL-CLOSED guard to the GREEN decision: in qa-executor-prompt.md the "**Decide GREEN.**" rule (~line 75) currently says GREEN iff every CASE in feature-state.gating_cases shows pass. ADD: an EMPTY or absent gating_cases is NEVER green — if gating_cases is empty/[] while a coding-agent-feature-ready:v1 sentinel exists, do NOT report GREEN; instead post the report noting "gating_cases empty — cannot verify" and end with an @engineering line asking engineering to populate case_ids/gating_cases at the ready-gate (it is engineering's owned field). Reflect the same fail-closed note + the "engineering populates, you only annotate pass/fail" ownership in qa-executor/CONTEXT.md.
Do not change anything else.`,
  },
  {
    id: 'qa-prompt', files: [`${D}/qa-prompt.md`],
    work: `Apply to ${D}/qa-prompt.md:
FINDING 2 (cadence): line ~41 "You are running your hourly QA pass" → "You are running your daily QA pass". (The canonical schedule is DAILY 05:30, not hourly.)
FINDING 4 (yaml schema): in the "## Machine-readable plan" fenced yaml block (~line 217) REMOVE the \`feature_key: "<feature_key — cross-repo-lane repos only>"\` line entirely. SHARED-SPEC §8 defines the qa-test-plan yaml as {unit_cases, integration_cases, proposed_cases} only, and the ready-gate ignores feature_key from qa (engineering owns it in feature-state). The prose "**feature_key**:" header line elsewhere in the plan stays — only the line inside the \`\`\`yaml\`\`\` block is removed.
Do not change anything else.`,
  },
  {
    id: 'coding', files: [`${D}/coding-prompt.md`, `${D}/workspaces/coding-agent/CONTEXT.md`],
    work: `Apply to ${D}/coding-prompt.md AND ${D}/workspaces/coding-agent/CONTEXT.md:
FINDING 2 (cadence): in coding-prompt.md line ~42 "You are running your hourly coding-agent pass" → "You are running your daily coding-agent pass".
${F3}
  Locations: coding-prompt.md ~line 132 ("The feature must PARK until a human/coding-agent adds the CASE to the harness and Alex re-arms via retry-please"); coding-agent/CONTEXT.md ~line 215 ("The feature parks until a human/coding-agent adds the CASE and ...").
Also (consistency with FINDING 1): confirm both files say coding-agent carries case_ids/gating_cases forward VERBATIM (does NOT blank or recompute them) — if any wording suggests coding-agent fills/owns these, fix it to "carry forward verbatim". Do not change anything else.`,
  },
  {
    id: 'shared-spec', files: [SPEC],
    work: `Apply to ${SPEC}:
${F1}
  In §3 "Field ownership (toolset-constrained...)": engineering's bullet currently lists the fields it writes but OMITS case_ids/gating_cases (they are assigned to no writer — the root of the bug). ADD case_ids and gating_cases to ENGINEERING's owned fields, with the populate-at-ready-gate rule (initial []; at ready-gate both = qa plan's validated integration_cases; gating_cases==case_ids; never CASE-402). Update qa-executor's bullet to "annotates gating_cases pass/fail (fail-closed: empty gating set is never green)" rather than implying it populates them. Keep everything else in §3 intact.
Do not change anything else.`,
  },
]

const FIX_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['id', 'edits_made', 'summary'],
  properties: {
    id: { type: 'string' },
    edits_made: { type: 'number' },
    summary: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } },
  },
}

phase('Fix')
const fixes = await parallel(items.map((it) => () =>
  agent(
`You are applying SURGICAL consistency fixes to loop-v2 agent contract files. Read the target file(s), make ONLY the changes described (use Edit for surgical replacements), preserve everything else verbatim. These are precise edits — do not rewrite sections, do not introduce new issues.

${it.work}

After editing, re-read the changed region(s) to confirm the edits are correct and self-consistent. Return what you changed.`,
    { label: `fix:${it.id}`, phase: 'Fix', schema: FIX_SCHEMA })
))

phase('Verify')
const verify = await agent(
`Verify the 4 consistency findings are RESOLVED across the loop-v2 deploy artifacts. Read these files and check:
1. case_ids/gating_cases now have a clear OWNER+POPULATOR (engineering, at the ready-gate write = qa plan's validated integration_cases; gating_cases==case_ids; never CASE-402); coding-agent carries forward verbatim; qa-executor fail-closes on empty gating (empty is never green). Check: ${D}/triage-prompt.md, ${D}/workspaces/engineering/CONTEXT.md, ${D}/qa-executor-prompt.md, ${D}/workspaces/qa-executor/CONTEXT.md, ${SPEC} (§3).
2. No remaining "hourly QA pass" / "hourly coding-agent pass" (should be "daily"): ${D}/qa-prompt.md, ${D}/coding-prompt.md.
3. No remaining "human/coding-agent adds the CASE" (should be "qa-author adds the CASE"): ${D}/triage-prompt.md, ${D}/coding-prompt.md, ${D}/workspaces/coding-agent/CONTEXT.md.
4. The qa-test-plan yaml block in ${D}/qa-prompt.md no longer has a feature_key: line.
Use grep/Read. Report each finding as resolved/unresolved with evidence (file:line). If anything is unresolved or a fix introduced an inconsistency, say exactly what.`,
  { label: 'verify-fixes', phase: 'Verify', schema: {
    type: 'object', additionalProperties: false, required: ['all_resolved', 'findings'],
    properties: {
      all_resolved: { type: 'boolean' },
      findings: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['finding', 'resolved', 'evidence'], properties: { finding: { type: 'string' }, resolved: { type: 'boolean' }, evidence: { type: 'string' } } } },
    },
  } })

return { fixes: fixes.filter(Boolean).map((f) => f && f.id), verify }
