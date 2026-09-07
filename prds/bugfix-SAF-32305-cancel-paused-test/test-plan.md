# Test Plan — Cancel a PAUSED Test Directly (SAF-32305)

> PRD: ./prd.md  |  Branch: bugfix/SAF-32305-cancel-paused-test  |  Status: Draft  |  Updated: 2026-09-07 12:20

## Status & Review

| Field | Value |
|-------|-------|
| Status | Draft (In Sync with PRD v1) |
| Offering / surface | console (Validate) — plus `none` for the bulk of the work |

## Requirements Traceability

| Req | Requirement (from SAF-32305 ∪ PRD §7) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1 | Cancel on `PAUSED` succeeds directly — no resume planned, attempted or mentioned | T-1, T-6, T-15, T-16 | Covered |
| R2 | Guard removed outright, not replaced by an internal resume-then-cancel | T-1, T-3 | Covered |
| R3 | Inverted unit test asserts the DELETE proceeds from `PAUSED` | T-1 | Covered |
| R4 | Cancel works on a multi-step plan whose steps are partially paused | T-2, T-7 | Covered |
| R5 | Orchestrator 500 propagates honestly — not retried, not re-described as a pause restriction | T-3 | Covered |
| R6 | Dead resume-then-cancel fallbacks removed from the e2e fixtures | T-6, T-7 | Covered (behavioural — see Change Coverage) |
| R7 | Tool description + `CLAUDE.md` state `PAUSED`→cancel is legal and document all four actions incl. `delete` | T-5 | Covered |
| R8 | Verified end-to-end against a live paused test | T-6, T-7, T-16 | Covered |
| R9 | `delete` documented: terminal-only, irreversible, `dry_run` preview, `reason` mandatory | T-9 | Covered |
| R10 | Synonyms stop routing "remove from queue"/"kill" to `cancel`; title drops "(pause / resume / cancel)" | T-10 | Covered |
| R11 | Skill stops pre-refusing `pause` on `PAUSED` / `resume` on `RUNNING`; reports `was_already` | T-11, T-16 | Covered |
| R12 | `reason` documented as an argument to pass; rate-limited responses handled | T-12 | Covered |
| R13 | Legality table, global-pause gate and `N/A` note each exist in exactly one place | T-13 | Covered |
| R14 | The two skills are **not** merged; the ticket records why | T-14 | Covered |

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| `safebreach_mcp_studio/studio_functions.py` | T-1, T-2, T-3, T-4 | — |
| `safebreach_mcp_studio/studio_server.py` | T-5 | — |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | — | test file; it *is* T-1..T-4 |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | — | test file; it *is* T-6, T-7 |
| `conftest.py` | T-6, T-7 | fixture-only. The epilogue's single-call cancel is exercised implicitly: after the fix, a `PAUSED` leftover must be cleaned without the deleted fallback, so a green e2e run *is* the assertion. |
| `tests/test_rate_limiting_e2e.py` | T-4 | fixture edit; the limiter behaviour it depended on is asserted directly by T-4 |
| `CLAUDE.md` | — | docs-only, no runtime surface (T-5 covers the tool description that agents actually read) |
| `breach-genie content/skills/safebreach-managing-tests/SKILL.md` | T-9..T-14 | — |
| `breach-genie content/skills/safebreach-managing-tests/references/valid-transitions.md` | T-10, T-13 | — |
| `breach-genie content/skills/safebreach-managing-tests/references/examples.md` | T-11 | — |
| `automation tests/.../helm_long_session_lib/test_cases/scenario_lifecycle_test_cases.py` | T-15 | — |

## Risk Landscape

- **Known risk areas** (PRD §9): R1 the publisher retry race (`slot.js:319`) still fires independently of pause; R2 merged multi-step status vs slot-level `isPaused`; R3 global pause must not gate cancel; R4 `resume` has a documented orchestrator crash (SAF-32835); R5 the data-API fallback can report a stale `PAUSED` (SAF-31138); R6 Phase 2 changes HELM behaviour beyond the reported bug.
- **Existing coverage (investigated)**: the cancel/pause/resume/delete transition matrix is already unit-tested in `test_studio_functions.py` class `TestManageTest:7580` — cancel×RUNNING `:8111`, ×CANCELED `:8132`, ×COMPLETED `:8152`, ×PAUSED `:8169` (asserts the raise — T-1 **inverts** it, does not duplicate it); pause matrix `:8186-8248`; resume matrix `:8255-8317`; delete matrix `:8407-8442`. Rate-limit gating in `test_rate_limiting.py` class `TestManageTestRateLimitingGate:24`. This plan targets only the gaps.
- **The gap that let the bug ship**: no e2e anywhere covers pause→cancel. `test_e2e_manage_test.py` has cancel `:107`, pause `:151`, pause+resume `:187`, cancel-already-canceled `:235`, delete `:283` — not this cell. The `automation` HELM suite stops at `tc13_cancel_single_test`, which cancels a **RUNNING** test only. T-6 and T-15 close both.
- **A third, silent confirmation**: `test_e2e_manage_test.py:57-73` `_cancel_test()` bypasses `sb_manage_test` and issues `requests.delete` at the queue URL directly — so every e2e run has been cancelling paused leftovers successfully while the tool refused to make the same call. The suite routed around its own subject.
- **What we protect**: the untouched lifecycle actions (pause / resume / delete) and their idempotent quick-returns; the rate limiter's accounting; RBAC on the DELETE.
- **Intentionally out of scope**: (a) root-causing the `no plan was stopped` retry race — the orchestrator's bug, its own ticket; T-3 only asserts we surface it honestly. (b) The `mcp-proxy` image bake + `dpull` needed to prove HELM's behaviour in-console — T-16 covers the same requirement from an existing console at no provisioning cost. (c) No markdown link-integrity test is added for the skill tree; breach-genie has none today and this ticket is not the place to introduce one.

## Coverage Summary (generated)

| Execution | unit | integration | system | e2e | Total |
|-----------|------|-------------|--------|-----|-------|
| Automatic | 11   | 0           | 1      | 2   | 14    |
| Manual    | 0    | 0           | 1      | 1   | 2     |

## Environment Requirements (aggregated)

- Environment classes: `none` (T-1..T-5, T-9..T-14); **console environment (Validate)** (T-6, T-7, T-8, T-15, T-16)

Capability checklist — answered from the system/e2e tests only:

- [x] **Simulators required?** — Yes, minimally one, and it need not be real. Not to execute an attack, but because `sb_run_scenario` only accepts a scenario `compute_scenario_readiness()` deems ready (`studio_functions.py:1916-1936`), and those filters resolve against simulator nodes.
- [x] **Running simulations / attacks required?** — No. Pause and cancel are queue-side operations on the `planRun`; nothing asserts an attack result, detection or finding. A purely static pre-seeded console is nonetheless insufficient — a `PAUSED` planRun is live queue state, not seedable data.
- [x] **Mockulators sufficient?** — Yes. No assertion depends on real attack execution or EDR/SIEM detection. A mockulator's only advantage over no simulator is keeping the run non-terminal long enough to pause, which prevents flakes.
- [x] **Console-specific configuration required?** — Yes, three cheap items: an API token whose role permits test management (`check_rbac_response` still wraps the DELETE, so a viewer token turns T-6 into a false negative); at least one ready OOB scenario; one multi-step scenario for T-7.
- [x] **Lateral-movement topology required?** — No. No patient-zero→victim producer is involved; a Propagate lab adds cost and zero coverage.
- Required additions (beyond class defaults): none — an existing shared console (`E2E_CONSOLE` default `pentest01`, or `staging`) satisfies every line. Decided at the authoring gate: no new provisioning.
- Artifacts under test: none for T-6/T-7/T-15 (the fixed `safebreach-mcp` runs locally against a real orchestrator). T-16 uses the console's already-deployed HELM.

## Regression

- **CI that must pass**: safebreach-mcp repo CI (the full pytest suite, `-m "not e2e"`); breach-genie CI (vitest, `npm test`) for the Phase 2 skill edits; **`Automation-Helm-Tests`** for the HELM surface. Note: the `Automation-Pen-Testing-*` family does **not** cover this surface — `automation/pytest.ini:62` states the `helm` marker runs only in `Automation-Helm-Tests` and is excluded from `Automation-PenTest-UI`.
- **Regression tests in this plan**: T-4, T-8 (the mandatory Manual one).

## Tests

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|--------------|------|
| T-1 | Cancelling a paused test reaches the orchestrator instead of raising | regression | Phase 1a | safebreach-mcp |
| T-2 | A partially-paused multi-step plan is still cancellable | regression | Phase 1a | safebreach-mcp |
| T-3 | A backend 500 stays a backend 500 and never re-acquires a pause story | regression | Phase 1a | safebreach-mcp |
| T-4 | The paused→cancel path consumes a rate-limit slot like any real mutation | regression | Phase 1a | safebreach-mcp |
| T-5 | The tool description tells an agent the truth about all four actions | API-contract | Phase 1b | safebreach-mcp |
| T-9 | The skill documents `delete` as irreversible and dry-run-first | API-contract | Phase 2 | breach-genie |
| T-10 | "remove"/"kill" no longer steer a delete request into a cancel | API-contract | Phase 2 | breach-genie |
| T-11 | The skill defers no-op legality to the tool instead of pre-refusing | API-contract | Phase 2 | breach-genie |
| T-12 | `reason` and rate-limiting are documented as agent-facing concerns | API-contract | Phase 2 | breach-genie |
| T-13 | Each transition rule exists in exactly one place | regression | Phase 2 | breach-genie |
| T-14 | Both skills survive as separate, registered skills | regression | Phase 2 | breach-genie |

**System**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-15 | HELM cancels a paused test in the suite that should have caught this | Automatic | regression | Phase 2 | automation | console environment |
| T-8 | The three untouched lifecycle actions still behave as before | Manual | regression | Phase 1c | — | console environment |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-6 | A real paused test on a real console cancels in one call | Automatic | progression | Phase 1c | safebreach-mcp | console environment |
| T-7 | A real partially-paused multi-step plan cancels in one call | Automatic | regression | Phase 1c | safebreach-mcp | console environment |
| T-16 | The ticket's own repro no longer reproduces | Manual | progression | Phase 2 | — | console environment |

### T-1 — Cancel on PAUSED proceeds to the DELETE

- Description: Proves the transition SAF-32305 reported as blocked is now performed, by the same call path already used for a running test.
- Status: Active
- Passes after: Phase 1a
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: The guard is removed but replaced by a silent internal resume-then-cancel, which would satisfy "cancel works" while reintroducing the resume call that R4 shows is dangerous.
- Risk source: PRD §9 R4
- Verify: Mock `_get_test_state` → `"PAUSED"`; call `sb_manage_test(action="cancel")`. Assert `requests.delete` was called exactly once with the queue URL, `requests.put` was **not** called at all, and no `ValueError` is raised.
- Expected: `status == "success"`, `action == "cancel"`. No response field contains the substring `resume`.
- Evidence required: CI run (safebreach-mcp pytest job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py` — invert the existing `test_cancel_on_paused_raises_error:8169` into `test_cancel_on_paused_proceeds`, keeping it in the `# --- Phase 9: State transition matrix — Cancel ---` section.
- Environment needs: none

### T-2 — Cancel on a partially-paused multi-step plan

- Description: Guards the gap between how the MCP reads pause state and how the orchestrator applies it, so a plan that is paused at one step but not another is still cancellable.
- Status: Active
- Passes after: Phase 1a
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: `_get_test_state` reads slot-level `isPaused` (`queue_state.py:53-54`) while `deletePlan` iterates per-step `pausedDate`. A merged-status mismatch could reintroduce a refusal for multi-step plans only — invisible to a single-step test.
- Risk source: PRD §9 R2
- Verify: Mock the orchestrator queue payload so the plan reports `PAUSED` via the slot while carrying multiple steps with mixed `pausedDate` values; call cancel.
- Expected: The DELETE is issued once; `status == "success"`. No branch distinguishes step count.
- Evidence required: CI run (safebreach-mcp pytest job + build #).
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_studio_functions.py` (class `TestManageTest`, Phase 9 section)
- Environment needs: none

### T-3 — An orchestrator 500 propagates untouched

- Description: Ensures the flaky backend error that caused the original misdiagnosis surfaces as itself, so it can never again be mistaken for a state rule.
- Status: Active
- Passes after: Phase 1a
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: A well-meaning retry or a friendly "try resuming first" hint is added around the DELETE, hiding the publisher race a second way and recreating SAF-31111's error.
- Risk source: PRD §9 R1
- Verify: Mock `requests.delete` to return 500 with body `no plan was stopped`; state `PAUSED`; call cancel.
- Expected: The error propagates to the caller. `requests.delete` is called **exactly once** (no retry). The raised message contains neither `resume` nor any claim that a paused test cannot be cancelled.
- Evidence required: CI run (safebreach-mcp pytest job + build #).
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_studio_functions.py` (class `TestManageTest`, Phase 9 section)
- Environment needs: none

### T-4 — Paused→cancel consumes a rate-limit slot

- Description: Confirms the newly-unblocked path is metered like every other mutation, closing a gap the existing quick-return test would otherwise mask.
- Status: Active
- Passes after: Phase 1a
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: `test_rate_limiting.py:169` proves idempotent quick-returns bypass the limiter. If paused→cancel were implemented as a quick-return rather than a real DELETE, it would silently escape metering — and no existing test would notice.
- Risk source: reviewer input (Branch 1b coverage sweep)
- Verify: State `PAUSED`; call cancel; record call order.
- Expected: Order is `check_limit` → DELETE → `record_action`, with `check_limit("<caller>", "manage_test")`. Mirrors the assertion style of `test_check_limit_called_before_api_call:42`.
- Evidence required: CI run (safebreach-mcp pytest job + build #).
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_rate_limiting.py` (class `TestManageTestRateLimitingGate`)
- Environment needs: none

### T-5 — The tool description documents all four actions and the paused→cancel rule

- Description: The description string is the only contract an LLM caller ever reads, so it is the surface where a stale rule does real damage — this asserts it matches the tool.
- Status: Active
- Passes after: Phase 1b
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: `delete` shipped in SAF-29972 and never reached the description (`studio_server.py:1553-1591`) or `CLAUDE.md:471-478`. The same silence is what let the paused rule stay wrong and unnoticed.
- Risk source: PRD §9 (contract drift), reviewer input
- Verify: Read the registered `manage_test` tool description.
- Expected: It names all four actions including `delete`; it states a paused test can be cancelled directly; it contains no instruction to resume before cancelling.
- Evidence required: CI run (safebreach-mcp pytest job + build #).
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-6 — Cancel a real paused test on a live console

- Description: The missing e2e cell — its absence is why this bug shipped, and its presence is what stops the guard being re-added.
- Status: Active
- Passes after: Phase 1c
- Level: e2e
- Execution: Automatic
- Aspect: progression
- Risk: Unit tests mock the orchestrator, so every unit assertion here would pass equally against a broken real endpoint. Only a live call proves the transition.
- Risk source: PRD §9, reviewer input
- Verify: Follow the established in-repo recipe (`test_e2e_manage_test.py:187-233`): `_fetch_all_scenarios` → first scenario where `compute_scenario_readiness` is true → `sb_run_scenario` → `sb_manage_test(action="pause")` → assert PAUSED → `sb_manage_test(action="cancel")`. Register the id via `register_e2e_test` for epilogue cleanup.
- Expected: The cancel returns `status == "success"` from a single call. Re-reading state yields `CANCELED`. No `resume` call is made at any point.
- Evidence required: CI run or local `uv run pytest -m "e2e"` transcript naming the console and `planRunId`, plus the observed state transition.
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_e2e_manage_test.py` — `test_e2e_cancel_paused_test` in class `TestManageTestE2E:104`, sibling of `test_e2e_pause_and_resume_test`.
- Environment needs: console environment

### T-7 — Cancel a real partially-paused multi-step plan

- Description: Carries T-2's multi-step concern onto real infrastructure, where the merged-status semantics actually live.
- Status: Active
- Passes after: Phase 1c
- Level: e2e
- Execution: Automatic
- Aspect: regression
- Risk: The mocked queue payload in T-2 encodes an assumption about merged status. Only a real multi-step plan proves that assumption.
- Risk source: PRD §9 R2
- Verify: Same recipe as T-6, selecting a ready scenario with more than one step; pause mid-run; cancel.
- Expected: Single-call cancel succeeds; state reads `CANCELED`.
- Evidence required: Test transcript naming the console, `planRunId` and the step count.
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_e2e_manage_test.py` (class `TestManageTestE2E`)
- Environment needs: console environment — requires one ready OOB scenario with ≥2 steps

### T-8 — The untouched lifecycle actions still behave as before

- Description: The mandatory regression walkthrough — proves the change did not disturb pause, resume or delete, exercised through HELM, their real consumer.
- Status: Active
- Passes after: Phase 1c
- Level: system
- Execution: Manual
- Aspect: regression
- Risk: The edit sits inside the shared `if action == …` chain in `sb_manage_test`; a careless removal could alter a neighbouring branch's quick-return or hint text without failing a unit test that asserts only its own cell.
- Risk source: PRD §9 R6, reviewer input
- Verify: On a live console, drive HELM through: pause a running test; resume it; pause it again; delete a terminal test (dry-run then confirm). Observe each response.
- Expected: Every action behaves as it did before the change — including the idempotent replies for pause-on-paused and resume-on-running, and delete's dry-run-first flow.
- Evidence required: Transcript of the HELM session plus observed-vs-expected for each of the four actions. If any step cannot be completed, report BLOCKED — never an improvised pass.
- Manual because: The assertion is the quality and correctness of an LLM's natural-language responses across a multi-turn session, which is a judgment call, not a deterministic signal.
- Environment needs: console environment

### T-9 — The skill documents `delete` as irreversible and dry-run-first

- Description: `delete` has been live and undocumented since SAF-29972; this asserts the agent's guidance finally covers the one action that cannot be undone.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: An agent reaching for `delete` with no dry-run discipline destroys test data irreversibly. Cancel is recoverable; delete is not.
- Risk source: reviewer input (Sebastian Altheim, SAF-32305 comment), Branch 1b
- Verify: Read `content/skills/safebreach-managing-tests/**` and assert the documented `delete` semantics.
- Expected: The skill states `delete` is terminal-states-only, irreversible, defaults to a `dry_run` preview, and requires `reason`.
- Evidence required: CI run (breach-genie vitest job + build #).
- Automation lives in: `planned: breach-genie tests/unit/skill-managing-tests-content.test.ts`
- Environment needs: none

### T-10 — "remove"/"kill" no longer steer a delete request into a cancel

- Description: Fixes the specific line that routes the words most likely to precede a delete request toward the wrong, non-equivalent action.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: `references/valid-transitions.md:63` currently maps "remove from queue" and "kill" to `cancel`. A user asking to delete gets a cancel, or the agent improvises.
- Risk source: reviewer input, Branch 1b
- Verify: Read the synonyms table and the skill title.
- Expected: The synonym mapping distinguishes cancel from delete for those phrases; the `SKILL.md` title no longer claims the skill covers only "(pause / resume / cancel)".
- Evidence required: CI run (breach-genie vitest job + build #).
- Automation lives in: `planned: breach-genie tests/unit/skill-managing-tests-content.test.ts`
- Environment needs: none

### T-11 — The skill defers no-op legality to the tool

- Description: Removes the skill's duplicate rulebook — the mechanism that produced this bug in one direction and the `delete` gap in the other.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: The skill instructs a pre-refusal the tool handles gracefully, based on a read that is already stale on a multi-writer console.
- Risk source: PRD §9 R6
- Verify: Read `SKILL.md` and `references/examples.md`.
- Expected: The skill no longer instructs refusing `pause` on `PAUSED` or `resume` on `RUNNING` without calling; it instructs calling the tool and reporting the `was_already` response. Transition legality is attributed to the tool.
- Evidence required: CI run (breach-genie vitest job + build #).
- Automation lives in: `planned: breach-genie tests/unit/skill-managing-tests-content.test.ts`
- Environment needs: none

### T-12 — `reason` and rate-limiting are documented as agent-facing concerns

- Description: Both exist in the tool and are invisible in the guidance, so the agent neither passes an audit reason nor knows what to do when metered.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Lifecycle mutations land with no audit note; a rate-limited response is mishandled or retried blindly.
- Risk source: Branch 1b, reviewer input
- Verify: Read the skill tree.
- Expected: `reason` is described as an argument to pass (not only a field read back); rate-limited responses have stated handling.
- Evidence required: CI run (breach-genie vitest job + build #).
- Automation lives in: `planned: breach-genie tests/unit/skill-managing-tests-content.test.ts`
- Environment needs: none

### T-13 — Each transition rule exists in exactly one place

- Description: Two copies of a table is how a wrong row survives in one of them — this asserts the de-duplication that makes the class of bug harder to repeat.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: The action-legality table exists at `SKILL.md:77-84` and `references/valid-transitions.md:43-50`; the global-pause gate and the `N/A` note are likewise duplicated. Drift between copies is invisible.
- Risk source: reviewer input, Branch 1b
- Verify: Scan the `safebreach-managing-tests` tree (and `safebreach-test-states/SKILL.md` for the `N/A` note) for each of the three rules.
- Expected: Each appears exactly once; the other location references it rather than restating it.
- Evidence required: CI run (breach-genie vitest job + build #).
- Automation lives in: `planned: breach-genie tests/unit/skill-managing-tests-content.test.ts`
- Environment needs: none

### T-14 — Both skills survive as separate, registered skills

- Description: Pins the explicit decision not to merge, so a future tidy-up cannot quietly collapse a split that other skills depend on.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Merging would drag the write-side transition matrix into every read-side turn and break the split `ctem-validation-run-lifecycle` and `safebreach-mitre-coverage` rely on.
- Risk source: PRD §9 R6, reviewer input
- Verify: Extends the existing CI guard at `tests/unit/SkillRegistry.test.ts:215-238`.
- Expected: `safebreach-managing-tests` and `safebreach-test-states` both parse, both validate, and both remain registered on `helm.agent.js` and `ctem-validation.agent.js`.
- Evidence required: CI run (breach-genie vitest job + build #).
- Automation lives in: `breach-genie tests/unit/SkillRegistry.test.ts` (existing) + `tests/unit/ctem-subagents.skills.test.ts` (existing)
- Environment needs: none

### T-15 — HELM cancels a paused test in the automation HELM suite

- Description: Closes the same missing cell in the suite that owns this surface — the one that would have caught the bug had it existed.
- Status: Active
- Passes after: Phase 2
- Level: system
- Execution: Automatic
- Aspect: regression
- Risk: `tc13_cancel_single_test` cancels a RUNNING test only. Without a paused case, the HELM suite stays blind to exactly this regression.
- Risk source: Branch 1b (automation-repo coverage sweep)
- Verify: New test case alongside `tc09`–`tc14`, using the suite's existing backend seed — `_make_pausable_test` / `seed_running_tests` (`helm_custom_moves.py:84-129`) then `orch_actions.v4.pause_test(run_id)` — then drive HELM via `helm_utils/helpers.py:188` `manage_test(..., action="cancel")`.
- Expected: HELM cancels the paused test in one action; the run reaches `CANCELED`; no resume is issued and none is narrated.
- Evidence required: `Automation-Helm-Tests` build # and the test-case log.
- Automation lives in: `planned: automation tests/automation_team/pen_test/ui/ai/helm/helm_long_session_lib/test_cases/scenario_lifecycle_test_cases.py`
- Environment needs: console environment

### T-16 — The ticket's own repro no longer reproduces

- Description: Replays the exact steps QA filed, as the closing sign-off evidence that the reported behaviour is gone end to end.
- Status: Active
- Passes after: Phase 2
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: The tool can be fixed while HELM still narrates a resume step from stale skill guidance — the user-visible symptom would persist even with every automated test green.
- Risk source: PRD §9 R6, the ticket's Steps to Reproduce
- Verify: On a live console, put a test into `PAUSED` (via the UI or a queued run), open HELM, and issue the ticket's literal prompt: "cancel it please".
- Expected: HELM cancels it directly. Its response contains no claim that the test must be resumed first, and no resume action appears in the tool-call trail. The Running page clears the test.
- Evidence required: Session transcript, the tool-call trail showing a single `manage_test(action="cancel")`, and a screenshot of the cleared Running page. BLOCKED if HELM cannot be reached — never an improvised pass.
- Manual because: The assertion includes what the agent *says*, not only what it calls — narration quality is a judgment call with no deterministic signal.
- Environment needs: console environment

## Tests by Phase (readiness view — generated)

| After phase | Newly green | Cumulative green |
|-------------|-------------|------------------|
| Phase 1a | T-1, T-2, T-3, T-4 | T-1..T-4 |
| Phase 1b | T-5 | T-1..T-5 |
| Phase 1c | T-6, T-7, T-8 | T-1..T-8 |
| Phase 2 | T-9, T-10, T-11, T-12, T-13, T-14, T-15, T-16 | all |

## Sign-off

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [ ] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — ≥1 Manual regression test (T-8) + post-ship CI builds named
- [ ] Progression evidence — ≥1 Manual progression test walking the new feature (T-16)
- [ ] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Final) — evidence: test-results/<phase-or-date>.md
- [ ] Accepted gaps listed and approved: none

## Change Log

| Date | Change |
|------|--------|
| 2026-09-07 12:20 | Test plan created from PRD v1 |
