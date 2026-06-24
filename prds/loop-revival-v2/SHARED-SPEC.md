# Loop v2 — Shared Spec (single source of truth for the 3 agent contracts)

**Status:** DRAFT for review (2026-06-22, **rev 2** — corrected after adversarial review of the drafted contracts). Deploys to `openclaw.local:~/.openclaw/` alongside the rewritten `<persona>-prompt.md` files. Decisions locked by Alex 2026-06-22 — see `prds/agentic-dev-loop.md` → Phase R2 redesign. The rewritten contracts (`{triage,qa,coding}-prompt.v2.md`) MUST conform to this spec verbatim; if a contract and this spec disagree, this spec wins.

---

## 0. The unit of work
A **FEATURE** = one **umbrella tracker issue** in `alexberardi/jarvis-roadmap` = one **coordinated branch set** (one branch per affected repo, all named `coding-agent/feat-<N>-<slug>` where `N` = the umbrella issue number). **No child tickets.** The umbrella issue is the durable home of all feature state. This replaces the old single-repo-PR unit of work that caused drift + the recursive-split explosion.

## 1. `feature_key` — set identity (already canonical; do NOT reinvent)
`feature_key = '+'.join(sorted(<slugs of participating repos whose lane == "cross-repo">))` — i.e. **only the six-vocabulary repos (§2)**. **Fast-lane-only participants are EXCLUDED** (they carry no `Linked-PR:` marker and `resolve_cross_repo.py` hard-errors on any non-six slug), so this matches EXACTLY what `cross-repo-trigger.yml` (~line 68) computes from the markers. If a feature has zero cross-repo participants it never enters the cross-repo lane (no `feature_key`; validated solely by per-repo fast lanes). Computed **solely** in `cross-repo-trigger.yml`; the resolver consumes the union but does not recompute the key (the earlier "resolver computes it identically" claim was false). Persist this exact key into the feature-state object (§3) as the join between the durable tracker and the transient CI runs. Proven green: integration-tests run `27967408363`.

## 2. The six-repo cross-repo vocabulary (HARD limit)
The cross-repo CI lane can build + validate-as-one-unit ONLY these six (each has a `*-from-source.yaml` overlay; `resolve_cross_repo.py` hard-errors on any other slug):

`jarvis-auth · jarvis-config-service · jarvis-command-center · jarvis-llm-proxy-api · jarvis-whisper-api · jarvis-tts`

A feature touching ANY other repo (`jarvis-command-sdk`, `jarvis-node-setup`, `jarvis-cmd-*`, `jarvis-device-*`, …) → those participants are marked `lane: "fast-lane-only"` in `feature-state.repos[slug]` and validated only by each repo's own fast lane (no cross-repo CASE gates them, and they get NO `Linked-PR:` marker — §8/coding §). **coding-agent FAIL-FASTS** if a from-source/cross-repo CASE would be required for an uncovered repo (mirror the resolver's `::error::`). This overlay gap is the single biggest real-world limiter; expanding the vocabulary is a separate testing-infra task, not loop work.

## 3. Durable ticket-state object — `<!-- feature-state:v1 -->`
A **latest-wins JSON sentinel comment** on the umbrella tracker (the latest comment whose FIRST LINE is exactly `<!-- feature-state:v1 -->` is current truth; supersede like the `:v1/:v2` breakdowns). Readable by all 3 agents via `issue_read(get_comments)`. Schema:

```json
{
  "feature_key": "jarvis-command-center+jarvis-llm-proxy-api",
  "iteration": 1,
  "repos": {
    "jarvis-command-center": {"branch": "coding-agent/feat-12-streaming", "pr": 211, "head_sha": "abc123", "state": "open", "lane": "cross-repo"},
    "jarvis-llm-proxy-api":   {"branch": "coding-agent/feat-12-streaming", "pr": 47,  "head_sha": "def456", "state": "open", "lane": "cross-repo"}
  },
  "case_ids": ["CASE-301", "CASE-302", "CASE-303", "CASE-304", "CASE-401"],
  "gating_cases": ["CASE-301", "CASE-302", "CASE-303", "CASE-304", "CASE-401"],
  "ambiguities_open": 0,
  "human_locked": true,
  "blocked_on": null,
  "terminal": "open"
}
```
`case_ids`/`gating_cases` hold the **composition-mode** integration set only (§6). `CASE-402` is the routing-mode probe the lane derives automatically when an OpenAI key is present — it is **never** listed here (co-listing 302 + 402 is a mode error, §6).

**Field ownership (toolset-constrained — only engineering has `issue_write`):**
- **engineering** writes: `feature_key`, `iteration`, the initial `repos` plan (branch names from the breakdown's `## Branch set`), `lane` per repo, `ambiguities_open`, `human_locked`, `blocked_on`, `terminal`, **`case_ids`, `gating_cases`** — **and all `status:*` LABELS.** **`case_ids`/`gating_cases` populate-at-ready-gate rule:** on the INITIAL feature-state write (breakdown done, no qa-test-plan yet) both stay `[]` (feature not ready). At the READY-GATE write (when engineering sets `status:ready-for-code`) engineering MUST set `case_ids` = the qa-test-plan's validated `integration_cases` (the composition set it already validated against the catalog) AND `gating_cases` = the SAME list — **`gating_cases == case_ids`: EVERY integration case must pass; do NOT gate on a subset** (a subset is what allowed vacuous green). NEVER include `CASE-402`.
- **coding-agent** appends a NEW `feature-state:v1` comment after pushing branches, carrying engineering's fields forward verbatim (including `case_ids`/`gating_cases` — it only runs on `status:ready-for-code`, so these are already populated) and filling `repos[slug].pr / head_sha / state` (latest-wins). It has `add_issue_comment` on the roadmap but NOT `issue_write` — it never sets labels.
- **qa-executor** mirrors the CI `cross-repo-test-results` outcome onto the tracker (it already does PR-result → roadmap mirroring) and annotates `gating_cases` pass/fail (**fail-closed: an empty gating set is NEVER green** — if `gating_cases` is empty/absent while a `coding-agent-feature-ready` sentinel exists, do NOT report GREEN; report a problem and flag `@engineering` "gating_cases empty — cannot verify; engineering must populate at ready-gate"). It does not populate `gating_cases`; engineering owns that at the ready-gate.

`terminal ∈ {open, merged, abandoned}` · `state ∈ {open, merged, closed}` · `lane ∈ {cross-repo, fast-lane-only}`.

## 4. Label vocabulary
**Lifecycle (engineering-set, EXCEPT `status:locked`):**
`status:proposed` → `status:accepted` → **`status:locked` (ALEX sets — the human "go")** → `status:ready-for-code` (engineering sets once the §5 predicate holds AND `status:locked` present) → `status:in-progress` → `status:blocked` (park) → `status:done` / `status:merged` / `status:abandoned` (terminal). `status:ready-for-group-merge` marks a feature whose PR set is open + linked, awaiting Alex's group-merge (§12).

**Other:** `needs:engineering|qa|coding-agent|qa-executor|product|alex`; `type:feature|bug|risk|refactor|question`; `priority:p0..p3`; `service:<svc>`; `feature:<id>`; `filed-by:engineering|product`; `spun-out` (recursion guard); `integration:fast-lane-only` (set on the umbrella when any participant is outside the six).

## 5. The ready-gate predicate (machine-checkable — kills the no-op-plan + co-presence bugs)
A feature is **READY-FOR-CODE** iff ALL of:
0. the latest qa-test-plan yaml block's `proposed_cases` is empty (a non-empty `proposed_cases` is the coverage-gap BLOCK signal, §7 — it OVERRIDES everything below; check it FIRST), AND
1. latest breakdown's `ambiguities_open == 0`, AND
2. the qa-test-plan's fenced ```yaml``` block exists with `len(unit_cases) + len(integration_cases) > 0` AND every `integration_cases` id ∈ the CASE catalog (§6) AND (if ≥1 repo has `lane:cross-repo`) `len(integration_cases) > 0`, AND
3. `feature-state.repos` is non-empty (the branch set is declared), AND
4. **`status:locked` is present** (Alex's explicit go).

Engineering computes this; ONLY THEN does it set `status:ready-for-code` + `human_locked=true`. The coverage-gap check (condition 0) must be evaluated BEFORE the `status:ready-for-code` write is even considered — if `proposed_cases` is non-empty, set `status:blocked` instead and never reach the ready write. coding-agent gates on the `status:ready-for-code` LABEL and re-asserts content before any clone. **Sentinel *presence* is never sufficient** — content is asserted.

## 6. CASE catalog + the two lane modes (the reconciliation join)
A CI step in `jarvis-integration-tests` greps `@pytest.mark.qa_case("CASE-…")` across the test files + the resolver's `KNOWN` map and writes a committed `tests/CASE_CATALOG.json` (id → `intent / lane / mode / repo / gating / test`). **The generator is now MERGED and live** (`tools/gen_case_catalog.py` + the committed `tests/CASE_CATALOG.json` + the PR-gated `unit.yml` drift check — PR #8 + regen PR #9; 38 cases, drift-check CLEAN). The committed catalog is the primary source; the fail-closed grep path (below) remains as a secondary safety fallback only if the catalog mirror is ever absent. QA READS it from the local mirror to (a) validate every `integration_cases` id it names exists, and (b) know which cases the resolver derives for a participant union — so QA's plan and the lane's `plan_cases` agree by construction. QA never edits the harness; it references existing CASES only.

**Two mutually-exclusive lane modes — do NOT co-list their cases.** The cross-repo lane auto-detects mode per dispatch:
- **Composition mode** (default; no OpenAI key, or no cc+llm pair): `plan_cases` = per-repo `always_cases` (**301·303·304** llm-proxy · **311** tts · **321** whisper) + `composition_cases` (**302** llm-proxy) + **CASE-401** when union ≥ 2.
- **Routing mode** (OpenAI key present AND cc+llm both build): `plan_cases_routing` = the `always_cases` + **CASE-402**; it DROPS 302 AND 401 (both are MOCK-backend composition probes — 401 skips wholesale in routing).

**QA's `integration_cases` = the COMPOSITION-mode set ONLY** (always + 302 + 401-when-≥2). **QA never lists CASE-402** — it is the routing-mode probe the lane derives automatically when a key is present (listing 402 in a composition plan → `not-implemented` → red). Worked examples (illustrative snapshots — always DERIVE from the live resolver `KNOWN` map / committed catalog, which may add cases over time): cc+llm union → `[CASE-301, CASE-302, CASE-303, CASE-304, CASE-401]`; whisper+tts union → `[CASE-311, CASE-321, CASE-401]`; single llm-proxy → `[CASE-301, CASE-302, CASE-303, CASE-304]`.

**Fail-closed when the catalog is absent (secondary safety path):** if the committed `tests/CASE_CATALOG.json` mirror is ever missing or stale, agents fall back to grepping `@pytest.mark.qa_case` across `jarvis-integration-tests/tests/*.py` to enumerate valid ids; if even that is unavailable, FAIL CLOSED — engineering sets `status:blocked` + `blocked_on:"case-catalog-missing"`, coding-agent aborts rather than opening a set. Never improvise validation.

## 7. Coverage-gap policy — **DECIDED: BLOCK**
When the generic `CASE-401` (composition) / `CASE-402` (routing) probes do NOT exercise the feature's actual behavior and no feature-specific CASE exists: QA MUST NOT bless it ready. QA emits a **park plan**: the yaml block sets `integration_cases: []` + a non-empty `proposed_cases: [...]` describing the missing assertion, and **omits `unit_cases` for the offending cross-repo repo** (so the BLOCK is unforgeable — a `proposed_cases`-bearing plan is ALWAYS a park, never a ready plan, regardless of `unit_cases` content). engineering reads non-empty `proposed_cases` → sets `status:blocked` + `needs:alex` (condition 0 of §5). The feature PARKS until qa-author adds the CASE to the harness and re-arms via `retry-please` (qa-author is the sole CASE author; coding-agent is forbidden from touching the harness). (Stronger "green means it works" over loop velocity — Alex's call.)

## 8. Sentinel grammar (first-line-of-comment markers; latest-wins per sentinel)
| Sentinel (first line) | Author | On | Contents |
|---|---|---|---|
| `<!-- engineering-triage-breakdown:v1 -->` | engineering | umbrella | feasibility + **repo-qualified** Files to change + **`## Branch set`** (`<repo> → <branch>`/repo) + Open ambiguities + (original template otherwise) |
| `<!-- feature-state:v1 -->` | all 3 (latest-wins) | umbrella | §3 JSON |
| `<!-- clarify:v1 -->` | engineering | umbrella | JSON `[{qid, question, answer:null}]`; engineering sets `status:blocked` while any unanswered |
| `<!-- answer:v1 -->` | Slack→GitHub relay (optional) | umbrella | `{qid, text}` — qid-keyed. **The loop does NOT depend on the relay.** If absent, Alex answers with a plain comment on the issue (reachable from GitHub mobile via the Slack link engineering posts at every `needs:alex`) and engineering maps it heuristically to the open `clarify` qids; the iteration cap + park still hold. The relay is a convenience that lets Alex answer from a Slack thread instead of opening the issue. |
| `<!-- qa-test-plan:v1 -->` | qa | umbrella | prose per-repo cases + fenced ```yaml``` `{unit_cases: {<repo>: [test_names]}, integration_cases: [CASE-…], proposed_cases: [...]}` |
| `<!-- coding-agent-feature-ready:v1 -->` | coding-agent | umbrella | terminal sentinel: all PR URLs + branches + `feature_key`; coding-agent also requests `status:ready-for-group-merge` (engineering applies the label) |
| `<!-- cross-repo-test-results:v1 -->` | CI | originating CODE PR | `N pass\|fail\|skip\|not-impl` table; mirrored to the umbrella by qa-executor |
| `<!-- retry-please:v1 -->` | Alex/orchestrator | umbrella | re-arm the whole feature |

## 9. Bounded clarify loop + park
engineering increments `feature-state.iteration` on each breakdown that carries non-empty Open ambiguities. **Init rule:** `iteration` starts at 1 on the FIRST breakdown (fresh or amended) that ships with non-empty ambiguities; it is 0/absent only while `ambiguities_open == 0`. At `iteration == 3` → set `status:blocked` + `needs:alex`, post the `clarify:v1` questions, and STOP auto-amending. Park = engineering early-exits on any tracker with `status:blocked` + unanswered `clarify` until an `answer` transition clears it. On unlock, clear `status:blocked`/`needs:alex`/`blocked_on`, **re-derive `human_locked` from the current presence of `status:locked` (§5/§ engineering)** before resuming. (No busy-wait, no quota churn.)

## 10. Per-ticket terminal-state / idempotency
First action of EVERY persona run — **including the needs:* interrupt path** — is to check the umbrella's terminal label/state; if `status:done|merged|abandoned`, do NOT amend/relabel/rewrite state (at most acknowledge an interrupt with a comment, remove the `needs:*` label, and move on). Transitions are one-way and label-based (idempotent — re-writing the label set via `issue_write(update)` with a label already in the set is a no-op). This is the #42/#40 fix scaled to the N-PR fan-out: N PRs' CI events all map to ONE feature terminal-state, so the loop converges once.

## 11. Anti-split (DECIDED defaults)
- engineering child-ticket creation budget = **0/run** by default. Cross-repo = DECOMPOSE into the `## Branch set`, NEVER N tickets.
- The ONLY path that creates a new tracker = an Alex-approved **UNRELATED-split** (two genuinely independent features), human-gated via `needs:alex`, cap 1/run, NEVER on an issue already labeled `filed-by:engineering`/`spun-out`.
- repos-per-feature soft cap = **3**; > 3 from-source repos → abort + `needs:alex`.
- Bright line: ONE feature = "shares a single user-visible acceptance outcome AND the branches are mutually dependent (the cross-repo CASE is red with any branch missing)". Genuinely-unrelated ⇒ separate tracker (human-gated).

## 12. Merge — **R2 = HUMAN-ONLY**
coding-agent NEVER merges (`merge_*` denied). For R2: coding-agent posts `coding-agent-feature-ready:v1` + requests `status:ready-for-group-merge` (engineering applies it); **Alex merges the set** after the cross-repo lane is green. The automerge gate (an integration-tests job merging the persisted `repos[]` set on an all-green feature-keyed `cross-repo-test-results`, needing a NEW merge-scoped PAT) is DESIGNED but DEFERRED to R3 — re-enabling autonomous merge is the R3 trust fork.

## 13. Toolset reality (per persona — verified against the live github-mcp-server 1.0.4 surface)
- **engineering**: `list_issues`, `issue_read` (methods `get` — read an issue —, `get_comments` — CAN read threads — and `get_labels` — read current labels before any label edit), `add_issue_comment`, `issue_write` (methods `create` and `update`: **create + labels (full-set REPLACE) + close** — **only persona that can**), `Read` (local mirror `/home/pi/code/jarvis/`), `message`. **github-mcp-server 1.0.4 has NO discrete `create_issue` / `add_labels_to_issue` / `remove_label_from_issue` tools** — create, labels, and close ALL route through the single consolidated `issue_write`: **create** = `issue_write(method create; title, body, labels:[...])` (now only the human-gated unrelated-split path); **labels** = read-modify-write — read the current set with `issue_read(method get_labels)`, compute the merged set, then write it WHOLE with `issue_write(method update; labels=<full set>)` (a partial `labels` array DROPS any omitted label); **close** = `issue_write(method update; state="closed", state_reason="not_planned"; OMIT labels to leave them unchanged)`.
- **qa**: `list_issues`, `issue_read` (method `get_comments`), `add_issue_comment`, `Read`, `message`. READ-ONLY on tracker metadata (no labels, no create — barred by denying `issue_write`). No write/exec on the harness.
- **coding-agent**: read/write/edit/apply_patch + exec (the only persona with these), `github-rw` `{list_issues, issue_read(get_comments), add_issue_comment}` on roadmap (no `issue_write` → no labels), `github-code` `{create_pull_request, list_pull_requests}` on code repos, `message`. DENIED: `issue_write`, `merge_*`, `update_pull_request`, `delete_*`, `push_files`, github-code against the private roadmap.

**Tool-name note:** all three read comment threads via `mcp__github-rw__issue_read` (method `get_comments`). **VERIFIED 2026-06-22** (read-only Pi inspection): the live, working `product` / `qa-executor` / `marketing` prompts all read comments via `issue_read` method `get_comments` (on both `github-rw` and `github-code` — PRs and issues share comment storage, so `issue_read` works on PRs too). The server uses the consolidated `issue_read` tool, not a discrete `list_issue_comments` (the only `list_issue_comments` reference lives in the *removed* qa agent's archived `qa.removed-2026-05-19/CONTEXT.md`, a pre-consolidation artifact). **CORRECTION 2026-06-23:** the live server is **github-mcp-server v1.0.4 (consolidated)** — it has **NO discrete `create_issue` / label tools.** Any `create_issue` / `add_labels_to_issue` / `remove_label_from_issue` claim (from older transcripts/an older binary) is stale: engineering does ALL issue creation, labels, and close via the single `issue_write` tool — **create** via `issue_write(method create)`, **labels** via `issue_write(method update, full-set REPLACE — read-modify-write` via `issue_read(method get_labels)` first`)`, **close** via `issue_write(method update, state="closed")`; and qa/coding-agent/qa-executor are barred from create/labels/close purely by denying `issue_write`. PR reads use the consolidated `pull_request_read` (methods `get`/`get_diff`/`get_status`/`get_files`/`get_review_comments`/`get_reviews`/`get_comments`/`get_check_runs`), NOT the removed `get_pull_request*` discrete tools. The full removed→use-instead migration map + the DEFERRED-TOOL/`ToolSearch` note are in `deploy/VERIFIED-FACTS.md` (the authoritative tool-surface source). Verified via `tools/list` on the live server.

Consequence: all label/state-LABEL writes are centralized in **engineering**; qa & coding-agent only READ tracker metadata + append `feature-state:v1` comments. Keep it that way (bounds the blast radius of a mislabel).

## 14. Slack channels (single-sourced)
| Persona | Channel | ID |
|---|---|---|
| engineering | #engineering-bot | `C0B4C4XJ9L1` |
| qa | #qa-bot | `C0B3WKBPSJ3` |
| coding-agent | #coding-bot | `C0B4C0W5WHY` |

Reference by ID; do not transcribe ad-hoc (a transposed id posts to the wrong channel silently).

## 15. Deployment prerequisites (before the contracts go live on the Pi)
1. **Merge the CASE catalog generator** — DONE (merged: `tools/gen_case_catalog.py` + the committed `tests/CASE_CATALOG.json` + a PR-gated `unit.yml` that runs the resolver+generator unit tests and drift-checks the catalog; PR #8 `feat/case-catalog-generator` + regen PR #9; 38 cases, drift-check CLEAN, 28 unit tests pass). It greps `@pytest.mark.qa_case` + the resolver `KNOWN` map → committed `tests/CASE_CATALOG.json`, and cross-checks the markers against `KNOWN` (a referenced case with no marker, or a CASE-3xx/4xx marker the resolver doesn't know, is a hard error). Now merged, so the committed catalog is the primary source; the §6 fail-closed grep remains only as a secondary safety path if the catalog mirror is ever absent. The two file paths engineering's `Read`-only fallback enumerates (`tests/test_from_source_services.py` → CASE-301/302/303/304/311/321; `tests/test_cross_repo_services.py` → CASE-401/402) are CONFIRMED correct against the harness (all 28 unit tests pass; catalog builds clean).
2. **Verify the github-rw MCP comment-read method name** (§13) — DONE 2026-06-22: verified against the live Pi that the working agents read comments via `issue_read` method `get_comments`; the contracts already match, no change needed.
3. **(Optional, DEFERRED 2026-06-22) Slack→GitHub answer relay.** NOT built for R2. Engineering already posts a Slack ping (issue link + plain-language question summary) at every `needs:alex` surfacing, and Alex answers by replying ON the issue (works from GitHub mobile); the clarify-unpark accepts his plain human comment (heuristic qid mapping — §"Bounded clarify loop + park" path (b)). The qid-keyed Slack-thread relay (so Alex can answer without leaving Slack) is a later convenience — when built it emits `<!-- answer:v1 -->`; until then nothing is blocked.
4. **R0/R2 mechanics:** re-rename the `.removed-2026-05-19` prompts/workspaces, re-add `agents.list`, re-install the `{coding-agent,engineering,qa}-runner.{timer,service}` units, refresh PATs.
