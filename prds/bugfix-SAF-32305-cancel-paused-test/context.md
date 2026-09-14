# Ticket Context: SAF-32305

## Status

Phase 6: Summary Created

## Mode

Improving

## Original Ticket

- **Summary**: HELM | Manage Test - Agent enforces an unnecessary "Resume" state sequence when attempting to cancel a paused test
- **Type**: Bug · **Priority**: Medium · **Status**: In Progress
- **Reporter**: Hadas Cohen · **Assignee**: Itamar Bar Hod
- **Labels**: `CTEM-dev`, `HELM-AI-Agent`
- **Found on**: pentest01.safebreach.com, mgmt + simulator 2026Q2.5
- **Description**: HELM blocks a cancel request on a `PAUSED` test and states it must be resumed first. The UI cancels a paused test directly via "Remove test" with no resume step.
- **Acceptance Criteria**: none on the ticket as filed.
- **Reviewer comment (Sebastian Altheim, 2026-08-31)**:
    1. Consolidate `safebreach-managing-tests` and `safebreach-test-status` into a single skill.
    2. Make sure the skill is aligned with the description of the manage test tool in the MCP, so they don't collide.

    (No skill named `safebreach-test-status` exists; the real name is `safebreach-test-states`. Treated as directional, not a spec.)

## Task Scope

Remove the false `PAUSED` → cancel restriction in the MCP `manage_test` tool, and close the
divergence between the MCP tool's real contract and the HELM skills that describe it.

## Repositories Under Investigation

- `~/Projects/safebreach-mcp` — owns the bug (this repo; PRD lives here)
- `~/Projects/orchestrator` — backend authority on transition legality (read-only, root-cause evidence)
- `~/Projects/ui-react` — reference implementation the ticket compares against (read-only)
- `~/Projects/breach-genie` — HELM agent skills (Phase 2 of implementation)

## Investigation Findings

### orchestrator (root-cause authority)

`src/server/services/slot.js:296-322` — `deletePlan()` contains an explicit branch for
deleting a plan **while paused**:

```js
if (this.isTestRunning()) {
  // If step was deleted while in paused state, we need to update the pause duration
  plan.steps.forEach((step) => {
    if (step.pausedDate) {
      step.pauseDuration += new Date() - Date.parse(step.pausedDate);
    }
  });
  ...
}
```

Cancelling a paused test is a **first-class, deliberately handled path**, not a tolerated
edge case.

`src/server/services/slot.js:319` — `throw new Error('no plan was stopped')` fires only when
`clearAndDeleteStep()` returns `null` **twice in a row**, i.e. the matrix publisher failed to
stop the step on both the first attempt and the retry. It is a retry-exhaustion race and has
no relationship to pause state. SAF-31111 attributed this flaky 500 to the paused status and
encoded it as a permanent rule.

### ui-react (reference implementation)

- `src/actions/execution.tsx:280-311` — `stopRunningMatrix()` issues
  `DELETE orch/v4 queue/{planRunId}`, unconditionally. No pause check, no resume step.
- `src/containers/HomePage/MatrixSummaryRunningList.tsx:88` — the "Remove test" X button
  dispatches exactly that action for any active row, paused included.
- The UI and the MCP `cancel` path hit the **same endpoint**. The MCP simply refuses to call it.

### Live verification (staging, 2026-09-06)

`DELETE https://staging.sbops.com/api/orch/v4/accounts/3477291461/queue/1788688888175.2`
against a paused test returned **HTTP 200** with the plan body, not a 500.

The response corroborates that the test was paused at the moment of the DELETE and that the
orchestrator's paused-cancel branch executed: step 0 carries
`pausedDate: 2026-09-06T10:05:04.263Z`, `pauseDuration: 10871`, `endTime: 2026-09-06T10:05:15.212Z`
— and `10:05:04.263 + 10.871s ≈ 10:05:15.13`, i.e. `pauseDuration` was finalised by the
`new Date() - Date.parse(step.pausedDate)` line above at cancel time.

**SAF-31111's premise is refuted.**

### safebreach-mcp (the defect)

`safebreach_mcp_studio/studio_functions.py:3484-3488`, inside `sb_manage_test()`:

```python
if current_state == "PAUSED":
    raise ValueError(
        "Cannot cancel a paused test. Use manage_test with "
        "action='resume' first, then cancel."
    )
```

This is the sole source of the reported behaviour. HELM is not inventing the restriction —
the tool hard-raises and HELM relays the message.

Introduced by SAF-31111 (`prds/SAF-31111-manage_test-failing-to-cancel-tests/prd.md:56`,
`:88`) on the strength of the misdiagnosed 500.

Blast radius in this repo:

| File | Line(s) | What |
|---|---|---|
| `safebreach_mcp_studio/studio_functions.py` | 3484-3488 | the raise — delete |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | 8169-8179 | `test_cancel_on_paused_raises_error` — invert to assert the DELETE proceeds |
| `conftest.py` | 147-159 | E2E epilogue resume-then-cancel fallback — dead, remove |
| `tests/test_rate_limiting_e2e.py` | 45-56 | same fallback, plus two extra `_rate_limit_store.clear()` calls — dead, remove |
| `safebreach_mcp_studio/studio_server.py` | 1553-1591 | `manage_test` tool description — silent on `PAUSED` → cancel |
| `CLAUDE.md` | 471-478 | tool docs say "pause, resume, cancel"; omit `delete` (added by SAF-29972) |

### breach-genie (HELM skills — divergence from the tool contract)

Two skills, both on `helm.agent.js:11-12` and `ctem-validation.agent.js:13`:

- `content/skills/safebreach-test-states/` — **read** discipline: two state axes, correlation
  phase derivation, result polarity, block-rate arithmetic. 8.8KB + 17KB refs.
- `content/skills/safebreach-managing-tests/` — **write** discipline: verify-before-act
  procedure, transition legality, synonyms. 5.8KB + 6KB refs.

Divergences from the actual `manage_test` contract:

1. **`delete` is entirely absent.** `grep -riE "delete|dry.?run|rate.?limit"` across both
   skills returns zero hits. The tool has taken `action="delete"` since SAF-29972 —
   irreversible, terminal-states-only, `dry_run=True` by default, `reason` mandatory.
   Worse, `references/valid-transitions.md:63` routes *"remove from queue"* and *"kill"* to
   `cancel`, actively steering away from the correct action.
2. **The idempotent quick-returns contradict the skills.** The tool returns success-shaped
   `already_paused` / `already_running` (`studio_functions.py:3495-3520`, `was_already: True`)
   where `safebreach-managing-tests/SKILL.md:77-84` marks the same actions ❌ and instructs
   HELM to refuse **without calling**. The tool's behaviour is the better one — it is
   race-safe against the shared/live console that `safebreach-test-states` itself opens with.
3. **`reason` is never described as an argument to pass** — both skills mention it only as a
   field read back off a cancelled test.
4. **Rate limiting (SAF-29871) is unmentioned**; no guidance for a rate-limited response.
5. **`PAUSED` → cancel**: the skills are already **correct**
   (`SKILL.md:81`, `references/valid-transitions.md:48` both say ✅). Only the tool is wrong.

Internal redundancy inside `safebreach-managing-tests` (drift hazard, and the mechanism by
which a wrong row could survive in one copy):

- action-legality table duplicated at `SKILL.md:77-84` and `references/valid-transitions.md:43-50`
- global-pause gate at `SKILL.md:91-93` and `references/valid-transitions.md:82`
- `N/A` = no-permission at `SKILL.md:94-95` and `safebreach-test-states/SKILL.md` §4.5

## Problem Analysis

### Problem scope

A single defensive check in `sb_manage_test()` denies a transition the backend supports and
the UI performs routinely. Users are told to take an action they should not need, and the
documented workaround is to leave HELM and use the UI.

The deeper issue is **ownership of transition legality**. The MCP tool re-implements the
orchestrator's state rules client-side, from the outside, and got one row wrong. The HELM
skills then re-implement the tool's rules a third time, and diverge again in the opposite
direction (they are right about `PAUSED`, wrong about `delete` and the quick-returns). Three
copies of one truth, each drifting independently. Fixing only the `PAUSED` row leaves the
mechanism intact.

### Impact assessment

- **User-facing**: any HELM user cancelling a paused test is blocked and redirected to the
  UI. Reported on pentest01 by QA; reproducible on any console.
- **Silent cost**: the E2E epilogues burn two extra rate-limited `manage_test` actions per
  paused leftover test, against a limiter built by SAF-29871.
- **Latent, higher severity than the filed bug**: HELM has an irreversible `delete` action
  with no guidance covering it, while the synonym table routes the words most likely to
  precede a delete request (*"remove"*, *"kill"*) to `cancel`. Cancel is recoverable; delete
  is not.

### Risks & edge cases

- **R1 — the 500 is real, just misattributed.** `no plan was stopped` can still fire on a
  publisher retry race, paused or not. Removing the guard exposes it as a genuine API error
  rather than a pre-emptive refusal. That is correct behaviour, but the error surfaced to the
  user must be honest rather than a resurrected "resume first" hint. Out of scope to fix in
  the orchestrator; in scope to not paper over.
- **R2 — merged multi-step status.** A test's status is the merged status of its steps
  (`valid-transitions.md:75-79`). `_get_test_state()` reads slot-level `isPaused`
  (`safebreach_mcp_core/queue_state.py:53-54`). A partially-paused multi-step plan must still
  cancel; the orchestrator loop iterates `plan.steps` and handles per-step `pausedDate`, so it
  does — but it deserves a regression test.
- **R3 — global pause.** Individual pause/resume is blocked while "All Running is Paused" is
  active. Cancel is not part of that gate in the UI. Do not add one.
- **R4 — scope creep on the skills.** Sebastian's ask (1) — merge the two skills — is
  **rejected**; see below. Ask (2) is accepted and is the bulk of Phase 2.

### Dependency: the skill-merge recommendation

Merging `safebreach-test-states` into `safebreach-managing-tests` is not recommended, and the
ticket should carry the reasoning:

- They have different trigger conditions and different consumers. `safebreach-test-states` is
  a **read** skill loaded on any turn that describes a test; `safebreach-managing-tests` is a
  **write** skill loaded only on a rare, approval-gated action.
- The split is already load-bearing for other skills: `ctem-validation-run-lifecycle/SKILL.md:74-75`
  deliberately routes reads to one and writes to the other, and `safebreach-mitre-coverage`
  (`SKILL.md:35`, `references/derivation.md:23`) pulls in test-states for result polarity with
  no interest in the write procedure.
- Merging forces every *"is my test done?"* turn to load the transition matrix, the synonyms
  table and six worked write dialogues, and produces a description that must cover both
  concerns — firing more often and matching less precisely.

The redundancy the comment is reacting to is real but sits **inside**
`safebreach-managing-tests` (SKILL.md duplicating its own `references/`), not between the two
skills. Deduping that is smaller than a merge and fixes the actual drift hazard.

## Proposed Improvements

See `summary.md`.
