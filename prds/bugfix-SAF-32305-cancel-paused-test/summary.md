# Ticket Summary: SAF-32305

## Overview

**Mode**: Improving existing
**Project**: SAF · Bug · Medium · In Progress
**Repositories**: `safebreach-mcp` (fix, Phase 1) · `breach-genie` (HELM skills, Phase 2)
**Evidence-only**: `orchestrator`, `ui-react`

---

## Current State

**Summary**: HELM | Manage Test - Agent enforces an unnecessary "Resume" state sequence when attempting to cancel a paused test

**Issues identified with the ticket as filed**:

- No acceptance criteria.
- Attributes the behaviour to HELM. The restriction is in the MCP `manage_test` tool, which
  hard-raises; HELM only relays the message. The HELM skills already document `PAUSED` → cancel
  as legal.
- No root cause. The guard was added deliberately by SAF-31111 on a misdiagnosis — the ticket
  needs to record that, or it will be re-added.
- The reviewer comment adds real scope (skill/tool contract alignment) that is not reflected
  anywhere in the ticket body.

---

## Investigation Summary

### orchestrator (backend authority)

- `src/server/services/slot.js:296-322` — `deletePlan()` has an **explicit branch for cancelling
  a paused plan**, finalising `step.pauseDuration` from `step.pausedDate`. Cancel-on-paused is
  a supported path, not an edge case.
- `src/server/services/slot.js:319` — `no plan was stopped` throws only after
  `clearAndDeleteStep()` returns `null` twice. A retry-exhaustion race, unrelated to pause state.

### ui-react (reference behaviour cited in the ticket)

- `src/actions/execution.tsx:280-311` — "Remove test" issues `DELETE orch/v4 queue/{planRunId}`
  unconditionally, no pause check.
- `src/containers/HomePage/MatrixSummaryRunningList.tsx:88` — the X button on any active row,
  paused included.
- Same endpoint the MCP `cancel` path uses.

### Live verification (staging, 2026-09-06)

`DELETE /api/orch/v4/accounts/3477291461/queue/1788688888175.2` on a paused test → **HTTP 200**.
Response shows `pausedDate 10:05:04.263` + `pauseDuration 10871ms` ≈ `endTime 10:05:15.212`,
i.e. the orchestrator's paused-cancel branch ran. No 500.

### safebreach-mcp (defect)

- `safebreach_mcp_studio/studio_functions.py:3484-3488` — the `ValueError`. Sole source of the
  reported behaviour.
- Test/fixture surface: `safebreach_mcp_studio/tests/test_studio_functions.py:8169-8179`,
  `conftest.py:147-159`, `tests/test_rate_limiting_e2e.py:45-56`.
- Docs: `safebreach_mcp_studio/studio_server.py:1553-1591`, `CLAUDE.md:471-478`.

### breach-genie (HELM skills)

- `PAUSED` → cancel is already **correct** in both skills. No behaviour change needed there.
- **`delete` is entirely undocumented** — zero hits for `delete` / `dry_run` / rate-limit across
  both skills, though the tool has had `action="delete"` since SAF-29972. And
  `references/valid-transitions.md:63` routes *"remove from queue"* / *"kill"* → `cancel`.
- The tool's idempotent `already_paused` / `already_running` returns contradict
  `safebreach-managing-tests/SKILL.md:77-84`, which tells HELM to refuse without calling.
- `reason` and rate-limit handling are undocumented as agent-facing concerns.

---

## Problem Analysis

### Problem description

`sb_manage_test()` refuses `action="cancel"` on a `PAUSED` test and instructs the caller to
resume first. The orchestrator handles that transition explicitly, the UI performs it routinely
via the same endpoint, and a live staging DELETE against a paused test returns 200. The guard
denies a legal operation.

Underneath the single wrong row is a structural problem: transition legality is re-implemented
three times — orchestrator (authoritative), MCP tool (client-side copy, wrong about `PAUSED`),
HELM skills (third copy, wrong about `delete` and the quick-returns). Each drifts
independently. Removing one wrong row without moving ownership leaves the mechanism that
produced it.

### Impact assessment

- **Users**: any HELM cancel on a paused test is blocked; documented workaround is to abandon
  the agent and use the UI.
- **E2E cost**: both epilogues burn two extra rate-limited `manage_test` actions per paused
  leftover, against the SAF-29871 limiter.
- **Latent risk above the filed bug**: HELM holds an irreversible `delete` action with no
  guidance, while the synonym table steers the words most likely to precede a delete request
  toward `cancel`.

### Risks & edge cases

- **R1** — `no plan was stopped` can still fire as a genuine publisher retry race. With the
  guard gone it surfaces as a real API error. It must not be masked by a resurrected
  "resume first" hint, and must not be retried around.
- **R2** — a partially-paused multi-step plan must still cancel; `_get_test_state()` reads
  slot-level `isPaused` while the orchestrator iterates per-step `pausedDate`. Needs a
  regression test.
- **R3** — global pause gates individual pause/resume, not cancel. Do not add a cancel gate.
- **R4** — the reviewer's skill-merge ask is rejected on load and coupling grounds (see
  `context.md`); the alignment ask is accepted.

---

## Proposed Ticket Content

### Summary (Title)

`manage_test` falsely blocks cancelling a PAUSED test, and the HELM skills no longer match the tool contract

### Acceptance Criteria

**Phase 1 — safebreach-mcp**

- [ ] `manage_test(action="cancel")` on a `PAUSED` test issues `DELETE orch/v4 queue/{planRunId}` and succeeds; no resume step is planned, attempted, or mentioned.
- [ ] The `PAUSED` guard at `studio_functions.py:3484-3488` is removed, not replaced with a silent internal resume-then-cancel.
- [ ] `test_cancel_on_paused_raises_error` is inverted to assert the DELETE proceeds from `PAUSED`.
- [ ] A regression test covers cancel on a multi-step plan whose steps are partially paused.
- [ ] The resume-then-cancel fallbacks in `conftest.py:147-159` and `tests/test_rate_limiting_e2e.py:45-56` are removed; the epilogues stop spending extra rate-limited actions.
- [ ] An orchestrator 500 (`no plan was stopped`) propagates as an honest error — not retried, not re-described as a pause restriction.
- [ ] `studio_server.py` `manage_test` description and `CLAUDE.md` state that `PAUSED` → cancel is legal, and document all four actions including `delete`.
- [ ] Verified end to end against a live paused test on staging.

**Phase 2 — breach-genie (HELM skills)**

- [ ] `safebreach-managing-tests` documents `delete`: terminal-states-only, irreversible, `dry_run=True` default with a preview step, `reason` mandatory.
- [ ] The synonyms table stops routing *"remove from queue"* / *"kill"* to `cancel` where the user means `delete`, and the skill title drops "(pause / resume / cancel)".
- [ ] The skill stops pre-refusing `pause` on `PAUSED` and `resume` on `RUNNING`; it calls the tool and reports the `was_already` response. Transition legality is owned by the tool, not restated by the skill.
- [ ] `reason` is documented as an argument HELM should pass, and rate-limited responses have defined handling.
- [ ] The action-legality table, global-pause gate and `N/A`-means-no-permission note each exist in exactly one place.
- [ ] The two skills are **not** merged; the ticket records why.

### Suggested Labels/Components

- Labels: `CTEM-dev`, `HELM-AI-Agent` (unchanged)
- Team: Cloud

---

## Proposed Ticket Content (JIRA Markdown)

**Description:**

```markdown
### Background

HELM refuses to cancel a paused test and tells the user to resume it first. The UI's
"Remove test" cancels a paused test directly. The workaround is to leave HELM entirely.

### Root cause

Not HELM. `safebreach_mcp_studio/studio_functions.py:3484-3488` in `sb_manage_test()`
raises `ValueError("Cannot cancel a paused test...")` before any API call. HELM relays it.

The orchestrator supports the transition explicitly — `slot.js:296-322` `deletePlan()` has a
dedicated branch that finalises `step.pauseDuration` when a step is deleted while paused.
`ui-react` `stopRunningMatrix` (`actions/execution.tsx:280`) issues the same
`DELETE orch/v4 queue/{planRunId}` with no pause check.

Verified on staging 2026-09-06: `DELETE .../queue/1788688888175.2` against a paused test
returned **200**, with `pausedDate + pauseDuration ≈ endTime`, i.e. the orchestrator's
paused-cancel branch ran.

The guard came from SAF-31111, which observed a 500 `no plan was stopped` and attributed it
to the pause. That error (`slot.js:319`) fires only when `clearAndDeleteStep` returns null
twice — a matrix-publisher retry race, unrelated to pause state.

### Also in scope — tool/skill contract drift

Per the review comment, the HELM skills were checked against the real `manage_test` contract:

* `PAUSED` -> cancel is already **correct** in the skills. Only the tool is wrong.
* `delete` (added in SAF-29972) is **absent from both skills** — no mention of `delete`,
  `dry_run`, or rate limiting anywhere. `valid-transitions.md:63` routes "remove from
  queue" / "kill" to `cancel`. Cancel is recoverable; delete is not.
* The tool's idempotent `already_paused` / `already_running` returns contradict
  `safebreach-managing-tests/SKILL.md:77-84`, which tells HELM to refuse without calling.

The durable fix is that the skill stops owning transition legality — the tool is the
authority, the skill teaches verify-before-act and honest reporting. That closes this bug
class in both directions.

### On merging the two skills

Not recommended. `safebreach-test-states` is a read skill loaded on any turn describing a
test; `safebreach-managing-tests` is a write skill loaded only on a rare approval-gated
action. The split is already relied on by `ctem-validation-run-lifecycle` (reads vs writes)
and `safebreach-mitre-coverage` (polarity only). Merging loads the transition matrix and six
write dialogues into every "is my test done?" turn. The redundancy worth removing is inside
`safebreach-managing-tests`, where its SKILL.md duplicates its own references.

### Affected Areas

* safebreach-mcp: `studio_functions.py:3484`, `studio_server.py:1553-1591`,
  `tests/test_studio_functions.py:8169`, `conftest.py:147`,
  `tests/test_rate_limiting_e2e.py:45`, `CLAUDE.md:471`
* breach-genie: `content/skills/safebreach-managing-tests/**` (Phase 2)
* orchestrator, ui-react: evidence only, no change
```
