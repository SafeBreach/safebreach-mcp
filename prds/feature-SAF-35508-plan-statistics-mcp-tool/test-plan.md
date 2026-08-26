# Test Plan — MCP support for Core plan statistics API (`get_plan_statistics`) (SAF-35508)

> PRD: ./prd.md  |  Branch: feature/SAF-35508-plan-statistics-mcp-tool  |  Status: Draft  |  Updated: 2026-08-26 12:04

## Status & Review

| Field | Value |
|-------|-------|
| Status | Draft (In Sync with PRD v4) |
| Offering / surface | Helm AI Agent (JIRA `Offering`) over the **Validate** product surface — scenarios/plans, simulators, plan statistics — via the safebreach-mcp Studio server |

## Requirements Traceability

Sources: JIRA acceptance criteria (AC-1…AC-12, reworded 2026-08-26) ∪ PRD §7 Definition of Done
(user-confirmed at the authoring gate).

| Req | Requirement (from SAF-35508 ∪ PRD §7) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1 | Ad-hoc plan body evaluated with no saved scenario; `scenario_id` passed to Core as `{id}`; a plan with no steps surfaces a typed error, not a raw 400 | T-6, T-7, T-8, T-11, T-26, T-28, T-29, T-31 | Covered |
| R2 | Surface per-step `simulationCount`, `moves`, `simulators`/`attackerSimulators`/`targetSimulators`, `isLimitReached`, structured constraints; pass through all five query params with documented defaults | T-6, T-9, T-11, T-28 | Covered |
| R3 | Runnable counts by default (`includeDisabled=false`); expected available; both-mode issues two labelled calls; documents that expected is not derivable from runnable | T-9, T-27, T-30 | Covered |
| R4 | Numbers match the console per view and per parameter set (Checkout `includeDisabled=true, getConstraints=true`; run gating `includeDisabled=false`) | T-30, T-35 | Covered |
| R5 | `isLimitReached` reported explicitly; `null` (not computed) vs `0` (runs nowhere) preserved; truncated step list surfaced; no zero-impact reporting on that path | T-10, T-15, T-22 | Covered |
| R6 | Exactly one `plan/statistics` call site; `_get_scenario_statistics` and its two callers routed through it, not a parallel implementation | T-13, T-14, T-16 | Covered |
| R7 | `CONSTRAINT_REASON_DESCRIPTIONS` deleted; all 88 emitted codes carry a `fix_lever` keyed on emitted values; no meaning is vendored; a test fails if a code lacks a lever | T-1, T-2, T-5, T-19 | Covered |
| R8 | Every conflict is surfaced with an explicit `description: null` rather than a bare code; conflicts are normalized against a catalog; `severity` is computed from the counts alone | T-3, T-18, T-23, T-36, T-32 | Covered |
| R9 | Zero-impact attack (`moves[id] === 0`) **reported** as inapplicable with an explanation; reporting does not block save; `null` never reported as zero-impact | T-20, T-22, T-36 | Covered |
| R10 | Zero-impact simulator (`simulators[id] === 0`) reported the same way, read from the **union** map not a role map | T-21, T-22 | Covered |
| R11 | No MCP-side caching, so any change to an earlier decision produces a fresh call | T-12 | Covered |
| R12 | Registered as `get_plan_statistics` with `readOnlyHint=True`; documented in the CLAUDE.md tool catalog; rate-limiting gate table not extended | T-24, T-25, T-34, T-32 | Covered |
| R13 | `sb_quick_run` and `sb_run_scenario` verified behaviourally unchanged | T-13, T-14, T-15, T-17, T-33 | Covered |

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| `safebreach_mcp_studio/studio_functions.py` | T-1, T-2, T-3, T-5, T-18, T-19, T-20, T-21, T-22, T-23, T-26, T-36 | — |
| `safebreach_mcp_studio/studio_types.py` | T-20, T-21, T-23, T-36 | — |
| `safebreach_mcp_studio/studio_server.py` | T-24, T-25 | — |
| `CLAUDE.md` | T-34 | — |

## Risk Landscape

- **Known risk areas** (PRD §9; reviewer added nothing further at the gate):
  - **R1 (High)** — misreading a limit-reached response. `simulationCount: null`, every `moves[id] = null`, and
    an early return that makes the step list shorter than the plan's. Treating falsy as zero, or assuming
    positional alignment, would report the user's whole selection as inapplicable.
  - **R2 (High)** — regressing the two existing callers. `_get_scenario_statistics` has 58 test references
    (~20 `@patch` decorators with hardcoded return dicts) plus `sb_quick_run` and `sb_run_scenario`.
  - **R3 (Low)** — vendored-meaning drift, largely designed out: the table is deleted, so MCP vendors no
    meaning that could go stale. `ui-react`'s measured rot (3 dead entries, 31 of 88 missing after years) is
    the evidence for deleting rather than a risk this plan still carries. Only the lever map remains vendored.
  - **R4 (Med)** — "matches the console" is not one number; Checkout and run-gating use opposite
    `includeDisabled` values.
  - **R5 (Med)** — cost of correctness; `getAllConstraints=true` disables the validator short-circuit.
  - **R6 (Med)** — vendoring by source key rather than emitted value ships two impossible codes, misses two
    real ones, and would still pass a naive coverage test.
  - **R7 (Med)** — levers assigned from code names rather than emit sites. No descriptions are authored now,
    but the same trap applies to the lever: `*_is_ignored` reads like a user-changeable setting when nothing
    the caller controls affects it. A wrong lever costs a wasted attempt.
  - **R8 (Med)** — asserting `severity` per code instead of computing it from the attack's count would label
    every `reducing` conflict a blocker, pulling SAF-35484's partial-impact scope in by accident.
  - **R9 (Med-High)** — meanings are absent until SAF-35568 lands, including the 14 that two shipped tools
    display today. Accepted deliberately; `description: null` is emitted explicitly so a caller can say "a
    conflict was reported" rather than guess from a misleading code name.
  - **R10 (Med)** — SAF-35568 is now on Stage 1's critical path, and its description half carries an open
    localization question. Its lever half can ship alone if that stalls.
- **Existing coverage (investigated)**:
  - `_get_scenario_statistics` happy path + error paths → `safebreach_mcp_studio/tests/test_studio_functions.py`
    (`TestGetScenarioStatistics`, :6212-:6293)
  - Statistics-API error-body propagation against a live console →
    `safebreach_mcp_studio/tests/test_e2e_run_scenario.py` (`TestErrorPropagationE2E`, :344)
  - Baseline verified during authoring: **455 studio unit tests green**
  - **Not covered today**: `isLimitReached`, the union `simulators` map, constraint-table completeness, and
    `includeDisabled=false` — this plan targets exactly those gaps.
- **What we protect**: the observable contract of `_get_scenario_statistics` (its key set and values), and the
  `evaluate=True` preview output of `sb_quick_run` / `sb_run_scenario`.
- **Intentionally out of scope**:
  - **Acting on the zero-impact report** — mutating a plan body to remove inapplicable attacks/simulators is
    explicitly out of scope on the ticket (a statistics call reports; the caller holds the configuration).
  - **The in-console MCP deploy path** — verifying the tool through a built `mcp-proxy` image deployed to a
    console is not tested here. This repo's e2e tests call the console API directly with the same functions,
    which falsifies every acceptance criterion at a fraction of the cost; the image path adds deployment
    coverage, not tool coverage.
  - **Deterministic runnable-vs-expected delta** — asserted opportunistically (see T-30): the gate chose the
    existing console over provisioning a dedicated one with a guaranteed disabled simulator.

## Coverage Summary (generated)

| Execution | unit | integration | system | e2e | Total |
|-----------|------|-------------|--------|-----|-------|
| Automatic | 15 | 13 | 0 | 4 | 32 |
| Manual | 0 | 0 | 0 | 3 | 3 |
| **Total** | **15** | **13** | **0** | **7** | **35** |

## Environment Requirements (aggregated)

- Environment classes: **none** (unit); **repo-harness** (integration — this repo's pytest with the
  orchestrator API mocked); **Validate console environment** (e2e).

Capability checklist — answered from the plan's e2e (real-env) tests only:

- [ ] **Simulators required?** — **Yes.** Plan statistics are computed from the console's configuration nodes, so
  a console with a simulator fleet is required for any non-trivial count.
- [ ] **Running simulations / attacks required?** — **No.** `plan/statistics` is a pre-execution prediction; a
  static console with existing scenarios/plans is sufficient and no test queues a test.
- [ ] **Mockulators sufficient?** — **Yes.** The endpoint reads simulator configuration and capabilities rather
  than executing attacks, so mockulator fidelity suffices provided connected/approved state is observable.
- [ ] **Console-specific configuration required?** — **Yes.** At least one saved scenario or custom plan (for the
  `scenario_id` path). A disabled or unapproved simulator is desirable but not required — T-30 asserts the
  runnable-vs-expected delta opportunistically and skips with a stated reason when none exists.
- [ ] **Lateral-movement topology required?** — **N/A.** Not a Propagate feature.
- Required additions (beyond class defaults): none.
- Artifacts under test: none — e2e tests import the branch's functions directly and call the console API; no
  feature-branch image is built or deployed.

## Regression

- **CI that must pass**: the repo's GitHub Actions **Security Scan** workflow — the only CI this repo has.
  **Known gap:** `safebreach-mcp` has **no CI test gate** (`.github/workflows/` contains only
  `security-scan.yml` and `release.yml`; `pytest` appears nowhere in CI), and no `Automation-Pen-Testing-*`
  suite maps to this surface. Regression therefore rests on the executor running the **full studio suite**
  (`safebreach_mcp_studio/tests/`, 455 unit tests at baseline, plus the e2e suite) and recording the result in
  `test-results/`. Note the runner needs `uv run --python 3.12 pytest` — a fresh worktree otherwise selects
  Python 3.14, where `pydantic-core` has no wheel and the build fails.
- **Regression tests in this plan**: T-2, T-5, T-10, T-13, T-14, T-15, T-16, T-17 (Automatic) and **T-33**
  (the mandatory Manual regression). This is the complete set carrying `Aspect: regression`.

## Tests

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|--------------|------|
| T-1 | The translation table is gone and every emitted code has a valid fix lever | API-contract | Phase 1 | safebreach_mcp_studio |
| T-2 | The two codes whose emitted value differs from their source key are keyed by the emitted value | regression | Phase 1 | safebreach_mcp_studio |
| T-3 | An unrecognised code is still surfaced, without a fabricated explanation | — | Phase 1 | safebreach_mcp_studio |
| T-5 | The vendored table has not drifted from the orchestrator source of truth | regression | Phase 1 | safebreach_mcp_studio |
| T-18 | A sparse constraint map is never iterated as though dense | — | Phase 4 | safebreach_mcp_studio |
| T-19 | Every reason in a multi-reason constraint leaf surfaces, not just the first | API-contract | Phase 4 | safebreach_mcp_studio |
| T-20 | Only a genuine integer zero marks an attack inapplicable — never a null | — | Phase 4 | safebreach_mcp_studio |
| T-21 | Zero-impact simulators come from the union map, so one-sided nodes are not falsely reported | — | Phase 4 | safebreach_mcp_studio |
| T-22 | A limit-reached response suppresses zero-impact reporting entirely | — | Phase 4 | safebreach_mcp_studio |
| T-23 | Conflicts are normalized against a catalog, with nothing static repeated per conflict | API-contract | Phase 4 | safebreach_mcp_studio |
| T-24 | The tool is registered under the agreed wire name and declared read-only | API-contract | Phase 5 | safebreach_mcp_studio |
| T-25 | A read-only tool takes no rate-limiting gates | — | Phase 5 | safebreach_mcp_studio |
| T-26 | Ambiguous input (both or neither of plan/scenario_id) is rejected with a clear error | — | Phase 5 | safebreach_mcp_studio |
| T-34 | The tool catalog documents the new tool and the gate table is left alone | — | Phase 6 | safebreach_mcp_studio |
| T-36 | The same code resolves blocking or reducing depending on the attack's count | — | Phase 4 | safebreach_mcp_studio |

**Integration** — all Automatic

| Test | Description | Aspect | Passes after | Repo | Environment |
|------|-------------|--------|--------------|------|-------------|
| T-6 | An ad-hoc plan body is scored and the response returned unreduced | API-contract | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-7 | A scenario_id is passed to Core for native resolution, never via planId | API-contract | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-8 | A step-less plan is rejected before any network call is made | — | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-9 | All five query parameters are sent, with the documented defaults and honoured overrides | API-contract | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-10 | A limit-reached response is survived, and null is kept distinct from zero | regression | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-11 | An API failure surfaces the full response body, not just a status code | — | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-12 | Repeated identical calls each hit the API, proving no MCP-side cache | — | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-13 | The refactored helper's observable contract is byte-for-byte unchanged | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-14 | The helper still asks for expected counts explicitly, preserving today's numbers | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-15 | The helper no longer crashes on a limit-reached response | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-16 | The statistics endpoint is reached from exactly one place in the repo | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-17 | Both existing callers' evaluate previews are unchanged by the refactor | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-27 | Counts mode selects one call or two, and labels what it returns | API-contract | Phase 5 | safebreach_mcp_studio | repo-harness |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-28 | The tool scores an ad-hoc plan against a real console and returns usable numbers | Automatic | API-contract | Phase 5 | safebreach_mcp_studio | Validate console environment |
| T-29 | Scoring by scenario_id agrees with scoring the same scenario's body ad hoc | Automatic | API-contract | Phase 5 | safebreach_mcp_studio | Validate console environment |
| T-30 | Runnable never exceeds expected, and the offline reason explains the gap | Automatic | API-contract | Phase 5 | safebreach_mcp_studio | Validate console environment |
| T-31 | A step-less plan against a real console yields the typed error, not a raw 400 | Automatic | — | Phase 5 | safebreach_mcp_studio | Validate console environment |
| T-32 | An agent can answer "what will run and what won't, and why" through the real product | Manual | progression | Final | — | Validate console environment |
| T-33 | The two shipped run tools still preview correctly against a real console | Manual | regression | Final | — | Validate console environment |
| T-35 | The tool's Checkout-parameter numbers match what the console itself displays | Manual | API-contract | Final | — | Validate console environment |

### T-1 — The translation table is gone and every emitted code has a valid fix lever

- Description: Proves MCP vendors no constraint meanings at all, and that every code the API can emit still has an actionable remedy path.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Leaving any vendored description behind recreates the third copy this design deletes, and re-opens the possibility of MCP asserting a meaning it is not the source of. A missing lever leaves a conflict with no remedy path.
- Risk source: PRD §9 (R3)
- Verify: Assert the module exposes no `CONSTRAINT_REASON_DESCRIPTIONS` symbol. Enumerate the lever map: assert 88 entries, each a `null` or a member of the closed lever enum, and assert no entry carries a `description`, `suggested_fix` or `kind` field.
- Expected: `CONSTRAINT_REASON_DESCRIPTIONS` does not exist. The lever map has exactly 88 entries with valid-or-null levers, and carries no meaning-bearing field of any kind. The variant de-duplication family (`*_is_ignored`, `ignoring_*_variant`) resolves to `null`, since nothing the caller controls affects it.
- Evidence required: pytest run output naming the test, with the asserted entry count visible.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-2 — The two codes whose emitted value differs from their source key are keyed by the emitted value

- Description: Guards the one vendoring mistake that would pass a naive completeness check while shipping two codes that can never occur and missing the two that do.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Keying by source key ships `some_cloned_advanced_actions_are_disabled` and `move_does_not_require_location_simulator_location_is_ignored`, neither of which the API ever emits, while `some_duplicate_advanced_actions_are_disabled` and `move_does_not_require_url_simulator_url_is_ignored` go untranslated — and a count-based test still reports 88/88.
- Risk source: PRD §9 (R6)
- Verify: Assert the table contains `some_duplicate_advanced_actions_are_disabled` and `move_does_not_require_url_simulator_url_is_ignored`. Assert it does NOT contain `some_cloned_advanced_actions_are_disabled`, and does not contain the web-application group's source-key spelling as a distinct entry from the Azure code of the same name.
- Expected: Both emitted values present and translated; the two source-key-only spellings absent.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-3 — An unrecognised code is still surfaced, without a fabricated explanation

- Description: Proves an upstream addition after this ticket is still reported as a conflict rather than silently dropped, and that no explanation is invented for it.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: The current lookup returns the code itself on a miss. Silently dropping an unknown code would hide a genuine blocker — exactly what the console does, filtering to `CONSTRAINTS[reason]` at `helpers.tsx:820` and discarding the 31 codes its table lacks. Drift is measured, not hypothetical.
- Risk source: PRD §9 (R3)
- Verify: Resolve a code absent from the catalog (e.g. `a_future_upstream_reason`). Inspect the resolved entry's fields.
- Expected: `fix_lever` is `null` and `description` is explicitly `null` — not the code, not invented prose — and the conflict is still present in the output, surfaced rather than dropped.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-4 — The 14 pre-existing descriptions survive the table replacement verbatim

- Description: Would have protected the 14 descriptions two shipped tools display, across a table replacement.
- Status: Removed
- Reason for removal: **The design changed from replacing the table to deleting it.** `CONSTRAINT_REASON_DESCRIPTIONS`
  and all 14 of its entries are removed outright (PRD §3 Component A), so there is no wording to preserve —
  losing those 14 descriptions is now the accepted, recorded consequence (PRD §9 **R9**), not a regression to
  guard against. The replacement assertion — that no vendored meaning survives anywhere — is covered by the
  rescoped **T-1**.
- Passes after: Phase 1
- Level: unit
- Execution: Automatic

### T-5 — The vendored table has not drifted from the orchestrator source of truth

- Description: Detects upstream vocabulary drift, which is the one failure mode a self-contained table cannot see on its own.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: The vocabulary lives in a different repo on a different release cadence; a code added upstream is invisible to this repo until a user hits it.
- Risk source: PRD §9 (R3)
- Verify: When an `orchestrator` checkout is resolvable, parse the emitted values of every exported group in its constraints module and compare that set against the vendored table's keys. When the checkout is absent, skip with an explicit reason naming the missing path.
- Expected: The two sets are equal, or the test skips with a stated reason. A skip is never reported as a pass.
- Evidence required: pytest run output showing either the equality assertion or the explicit skip reason.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-6 — An ad-hoc plan body is scored and the response returned unreduced

- Description: Proves the core capability the parent story needs — scoring a configuration that was never saved — and that nothing is dropped on the way back.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Aspect: API-contract
- Risk: The existing helper reduces the response to aggregates and never extracts the union `simulators` map or `isLimitReached`, so the data the reporting rules need is discarded before any caller sees it.
- Risk source: PRD §9 (R2)
- Verify: With the orchestrator API mocked, call the fetch core with a plan body carrying two steps and no `id`. Inspect the posted body and the returned per-step structures.
- Expected: The posted body carries the supplied steps and a `name` (defaulted to empty string when absent) and no `id`. Each returned step exposes `simulationCount`, `moves`, `simulators`, `attackerSimulators`, `targetSimulators`, `simulatorConstraints` and `isLimitReached` with the mocked values unmodified.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-7 — A scenario_id is passed to Core for native resolution, never via planId

- Description: Proves the saved-scenario path is a passthrough rather than a client-side fetch, and avoids the schema field the controller silently ignores.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Aspect: API-contract
- Risk: `planId` is present in the request schema but is not honoured by the controller; using it would produce a body that looks correct and is scored as an empty ad-hoc plan.
- Risk source: PRD §9 (assumptions — by-id resolution)
- Verify: With the API mocked, call the fetch core with a `scenario_id` and no plan body. Inspect the posted body and assert no scenario-fetch call was made.
- Expected: The posted body carries `id` set to the supplied value plus a `name`; `planId` is absent; no additional scenario or plan lookup is issued.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-8 — A step-less plan is rejected before any network call is made

- Description: Proves a normal mid-construction state produces an explanatory error instead of an opaque upstream rejection, and does so without spending a request.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Risk: Core answers a step-less plan with an HTTP 400; surfaced raw it reads as a tool failure rather than "add a step", which Helm will hit constantly while building.
- Risk source: PRD §9 (edge cases)
- Verify: With the API mocked, call the fetch core with a plan body whose `steps` is missing, then again with `steps` empty. Assert the mocked transport was never invoked.
- Expected: Both calls raise a typed error whose message names the missing steps; the HTTP mock records zero calls.
- Evidence required: pytest run output naming the test, showing the zero-call assertion.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-9 — All five query parameters are sent, with the documented defaults and honoured overrides

- Description: Proves the parameters that carry the tool's meaning are genuinely pass-through, and pins the defaults the documentation promises.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Aspect: API-contract
- Risk: The current helper hardcodes two parameters, ties two more to a single boolean, and never sends the fifth — so callers cannot select which question is being asked.
- Risk source: PRD §9 (R4, R5)
- Verify: With the API mocked, call the fetch core with no parameter overrides and parse the request URL's query string. Repeat with each parameter explicitly overridden to a non-default value.
- Expected: The default call sends `includeDisabled=false`, `getConstraints=true`, `getAllConstraints=true`, `limit=500000`, `useCache=true`. Each override appears in the URL in place of its default, and no parameter is omitted in either case.
- Evidence required: pytest run output naming the test, with the asserted query strings visible.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-10 — A limit-reached response is survived, and null is kept distinct from zero

- Description: Falsifies the plan's highest-severity risk at the layer where the distinction is established, so no downstream consumer can confuse "not computed" with "runs nowhere".
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Aspect: regression
- Risk: The existing helper raises `TypeError` on this response. Worse, defaulting the absent count to zero would tell a user their whole selection is inapplicable, and the returned step list is shorter than the plan's so positional attribution is wrong too.
- Risk source: PRD §9 (R1)
- Verify: Mock a limit-reached response for a three-step plan: a single returned step with `isLimitReached` true, a null `simulationCount`, and every `moves` value null. Call the fetch core.
- Expected: No exception. The step's count is reported as not-computed, distinct from zero, and every null `moves` value stays null rather than becoming `0`. The result reports the plan's step count as 3, the returned count as 1, and the truncation flag as set.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-11 — An API failure surfaces the full response body, not just a status code

- Description: Proves a failed scoring call is diagnosable, since the response body is where Core explains what it rejected.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Risk: A bare status code gives a caller nothing to act on, and Core signals distinguishable conditions (step-less plan, unsupported filter operator) through the body.
- Risk source: PRD §9 (R4)
- Verify: Mock the API returning a non-2xx status with a JSON body carrying an identifiable error string. Call the fetch core and capture the raised error.
- Expected: The raised error's message contains both the status code and the identifiable string from the body.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-12 — Repeated identical calls each hit the API, proving no MCP-side cache

- Description: Proves the freshness guarantee the conversational flow depends on — a re-check after a changed decision must not be answered from a stale local cache.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Risk: This repo's other servers cache aggressively by convention; adding a TTL cache here would serve impact numbers for a configuration the user has already edited.
- Risk source: PRD §9 (R5)
- Verify: With the API mocked, call the fetch core twice with identical arguments. Count transport invocations.
- Expected: Exactly two invocations. No module-level cache object is consulted for statistics results.
- Evidence required: pytest run output naming the test, showing the call count.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-13 — The refactored helper's observable contract is byte-for-byte unchanged

- Description: Locks the contract that two shipped tools and ~20 hardcoded test fixtures depend on, so the refactor cannot alter what existing callers receive.
- Status: Active
- Passes after: Phase 3
- Level: integration
- Execution: Automatic
- Aspect: regression
- Risk: The helper is referenced 58 times in the studio test file, mostly as patched return values in its present shape. A renamed or dropped key breaks both callers and a large number of tests at once.
- Risk source: PRD §9 (R2)
- Verify: For a fixed mocked statistics response, call the helper and compare the returned structure against the pre-refactor expected value captured as a fixture — full equality, keys and values.
- Expected: Exact equality. The key set is precisely `simulationCount`, `matchedTargetSimulators`, `matchedAttackerSimulators`, `matchedAttacks`, `totalTargetSimulators`, `totalAttackerSimulators`, `totalAttacks`, plus the constraint and resolved-attack keys under their existing conditions.
- Evidence required: pytest run output naming the test.
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py` (extends `TestGetScenarioStatistics`)
- Environment needs: repo-harness

### T-14 — The helper still asks for expected counts explicitly, preserving today's numbers

- Description: Proves the new runnable default did not silently change the numbers two shipped tools already report.
- Status: Active
- Passes after: Phase 3
- Level: integration
- Execution: Automatic
- Aspect: regression
- Risk: The new tool defaults `includeDisabled` to false. If the helper inherits that default instead of passing true explicitly, both existing previews change their reported figures with no code visibly saying so.
- Risk source: PRD §9 (R2)
- Verify: With the API mocked, call the helper and parse the resulting request URL.
- Expected: The URL carries `includeDisabled=true` and `limit=500000`, matching the pre-refactor request exactly.
- Evidence required: pytest run output naming the test, with the asserted query string visible.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-15 — The helper no longer crashes on a limit-reached response

- Description: Confirms the latent crash in the shipped code path is fixed as a by-product of the refactor, not merely avoided in the new tool.
- Status: Active
- Passes after: Phase 3
- Level: integration
- Execution: Automatic
- Aspect: regression
- Risk: The helper's counting and sorting expressions both raise `TypeError` on null counts, so a large scenario breaks `quick_run` and `run_scenario` previews today.
- Risk source: PRD §9 (R1, R2)
- Verify: Call the helper with a mocked limit-reached response containing null counts, in both the constraints-enabled and constraints-disabled modes.
- Expected: No exception in either mode. A defined result is returned, and the aggregate counts do not claim zero matches where the underlying values were never computed.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-16 — The statistics endpoint is reached from exactly one place in the repo

- Description: Enforces the single-source-of-truth requirement structurally, so a future contributor cannot reintroduce a second estimation path.
- Status: Active
- Passes after: Phase 3
- Level: integration
- Execution: Automatic
- Aspect: regression
- Risk: A parallel path is what the parent requirement forbids, and it would let the translation table and parameter defaults diverge between callers.
- Risk source: PRD §9 (R2)
- Verify: Scan the repository's Python sources for occurrences of the `plan/statistics` endpoint path, excluding tests.
- Expected: Exactly one occurrence, inside the fetch core.
- Evidence required: pytest run output naming the test, with the matched location listed.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-17 — Both existing callers' evaluate previews are unchanged by the refactor

- Description: Verifies the regression surface at the level users actually see — the preview payloads of the two shipped tools — rather than only at the helper boundary.
- Status: Active
- Passes after: Phase 3
- Level: integration
- Execution: Automatic
- Aspect: regression
- Risk: The helper's output is reshaped by both callers before display; an unchanged helper contract does not by itself prove unchanged previews.
- Risk source: PRD §9 (R2)
- Verify: For a fixed mocked statistics response, invoke the scenario-run and quick-run entry points in evaluate mode and compare each returned preview payload against a pre-refactor fixture.
- Expected: Both payloads equal their fixtures, including the predicted totals, per-step breakdown and empty-step list.
- Evidence required: pytest run output naming both assertions.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-18 — A sparse constraint map is never iterated as though dense

- Description: Proves absence is read as "no conflicts" rather than as missing data, which is what the upstream pruning actually means.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: Core prunes empty constraint leaves and then any simulator with no constraints at all. Treating the map as dense would fabricate entries for simulators that are simply fine.
- Risk source: PRD §9 (edge cases)
- Verify: Shape a response where three simulators are in scope but only one appears in the constraint map. Run the reporting layer.
- Expected: Conflicts are reported for the one present simulator only. The two absent simulators produce no conflict entries and are not described as unevaluated or unknown.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-19 — Every reason in a multi-reason constraint leaf surfaces, not just the first

- Description: Proves the completeness that the chosen parameter set pays for — with all constraints requested, a simulator accumulates every reason it failed, and all of them must reach the caller.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: The constraint leaf is an array and usually holds several reasons under the chosen settings. Reading only the first element discards most of the explanation the extra cost bought.
- Risk source: PRD §9 (R5, edge cases)
- Verify: Shape a constraint leaf holding three distinct reasons for one simulator/attack pair, on both the attacker and target sides. Run the reporting layer.
- Expected: All three reasons appear, each classified, with the side(s) that produced them recorded. Reasons from both sides are merged rather than one side overwriting the other.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-20 — Only a genuine integer zero marks an attack inapplicable — never a null

- Description: Falsifies the highest-severity risk at the reporting layer: telling a user an attack runs nowhere when the number was simply never computed.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: A falsy test treats null and zero alike. On a limit-reached response every count is null, so a falsy test reports the user's entire attack list as inapplicable and presents it as a normal result.
- Risk source: PRD §9 (R1)
- Verify: Shape one step whose `moves` map mixes a positive count, an integer zero, and a null. Run the reporting layer.
- Expected: Exactly one attack — the integer zero — is reported as zero-impact, with its translated reasons. The null-valued attack appears in no zero-impact list, and the positive one does not either.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-21 — Zero-impact simulators come from the union map, so one-sided nodes are not falsely reported

- Description: Proves the requirement's specific map choice is honoured, since reading a role map instead produces confidently wrong answers for any single-role simulator.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: A node present on only one side is absent from the other role map, not zero in it. Reading role maps would either miss real zero-impact simulators or invent them. The current helper never extracts the union map at all.
- Risk source: PRD §9 (R1, edge cases)
- Verify: Shape a step where the union map holds a simulator at zero and another at a positive count, while the attacker and target role maps each omit one of those simulators entirely. Run the reporting layer.
- Expected: Only the union-map zero is reported as a zero-impact simulator. No simulator is reported on the basis of being absent from a role map.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-22 — A limit-reached response suppresses zero-impact reporting entirely

- Description: Proves the plan's central safety property: when Core did not compute the numbers, the tool says so instead of drawing conclusions from them.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: This is the single path where every count is null and the step list is truncated. Any reporting at all here risks presenting a fabricated verdict on the user's whole configuration.
- Risk source: PRD §9 (R1)
- Verify: Run the reporting layer over a limit-reached step whose counts are not computed.
- Expected: No zero-impact attack list and no zero-impact simulator list are emitted for that step. A truncation explanation is present, and the response makes clear the returned step list is shorter than the plan's.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-23 — Conflicts are normalized against a catalog, with nothing static repeated per conflict

- Description: Proves the response is a catalog plus references rather than repeated blobs — the property that keeps payloads usable on a real console and makes an API-served catalog a drop-in later.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Inlining static fields per conflict repeats them across every attack that hit the code, bloating the response and letting two code paths format the same code differently. It would also have to be restructured when the catalog moves to the API.
- Risk source: PRD §9 (R3)
- Verify: Run the reporting layer over a response where three distinct attacks share one reason code and one attack carries an unknown code. Inspect the top-level catalog and each conflict entry.
- Expected: The catalog holds exactly one entry per distinct code present, and only codes present in this response, each carrying `fix_lever` and an explicit `description: null`. Each conflict carries `code`, `severity`, `attack_id`, `side`, `simulator_count` and `values` — and no `fix_lever` or `description`, which live only in the catalog. No field anywhere in the payload presents a bare reason code as its explanation.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-36 — The same code resolves blocking or reducing depending on the attack's count

- Description: Proves severity is computed from context rather than asserted per code — the distinction that keeps this ticket's hard-failure scope separate from SAF-35484's partial-impact scope.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: A reason lives at (simulator, attack) and eliminates one node variant; an attack with surviving candidates still runs. Treating any elimination as a blocker would mislabel every partial-coverage conflict — including the whole variant-de-duplication family — over-report zero-impact attacks, and drag Story 2's scope in by accident.
- Risk source: PRD §9 (R8)
- Verify: Shape one step where the same reason code appears for two attacks — one whose count is an integer `0`, one whose count is positive. Run the reporting layer and inspect both conflicts' severities.
- Expected: The code resolves `blocking` for the zero-count attack and `reducing` for the positive-count attack within the same step, with no contradiction. Only the `blocking` entry appears in that attack's `blockers`. No catalog field is consulted to reach either verdict.
- Evidence required: pytest run output naming the test, showing both severities for the shared code.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-37 — The sixteen informational codes are classified as such and never block

- Description: Would have proved the false-alarm class was closed by classifying 16 codes as benign notes.
- Status: Removed
- Reason for removal: **The premise was false.** Verified at the emit sites that every one of the 88 codes sets
  `valid = false`, after which the node is never pushed to `filteredNodes` (`aws_validation.js:96-101`,
  `gcp_validation.js:77-81`). The `*_is_ignored` / `ignoring_*_variant` families are variant-level
  de-duplication, not informational notes, so there is no `informational` class to assert and the `kind` field
  this test asserted through no longer exists. The effect it reached for — a variant de-duplication must not
  read as a blocker — is covered by **T-36**, which derives severity from the attack's count alone.
- Passes after: Phase 1
- Level: unit
- Execution: Automatic

### T-24 — The tool is registered under the agreed wire name and declared read-only

- Description: Proves the tool is discoverable under the name every sibling subtask and the agent prompt depend on, and that it advertises itself as safe to call repeatedly.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A wrong name breaks every dependent contract; a missing read-only hint invites a calling model to treat re-checks as risky and avoid them.
- Risk source: PRD §9 (assumptions)
- Verify: Introspect the studio server's registered tools.
- Expected: A tool named exactly `get_plan_statistics` exists, with the read-only hint true and the destructive hint false. The previously registered tools are all still present.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-25 — A read-only tool takes no rate-limiting gates

- Description: Proves the project's rate-limiting contract is respected — gates belong to mutating tools, and gating a read-only impact check would throttle exactly the re-checks the feature exists to enable.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: Copying an existing studio tool as a template would bring its rate-limiting gates along, silently capping how often a configuration can be re-scored.
- Risk source: PRD §9 (R5)
- Verify: With rate limiting enabled and the API mocked, invoke the new tool more times than the configured per-tool limit while observing the limiter.
- Expected: Every invocation succeeds. Neither the pre-check nor the record-action entry point is called for this tool.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_rate_limiting.py`
- Environment needs: none

### T-26 — Ambiguous input (both or neither of plan/scenario_id) is rejected with a clear error

- Description: Proves the two input modes are genuinely exclusive, so a caller never gets a silently-ignored argument and a number that answers a different question.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: Silently preferring one input over the other would score a different configuration than the caller asked about, and the result would look entirely plausible.
- Risk source: PRD §9 (assumptions)
- Verify: Invoke the public function with both a plan body and a scenario id, then with neither. Also invoke with a plan argument that is not valid JSON.
- Expected: All three raise errors whose messages state which inputs are expected and that exactly one must be supplied. No API call is attempted.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-27 — Counts mode selects one call or two, and labels what it returns

- Description: Proves the expected-versus-runnable contract, including that the cheaper single-call default is what a caller gets unless they ask for both.
- Status: Active
- Passes after: Phase 5
- Level: integration
- Execution: Automatic
- Aspect: API-contract
- Risk: The two figures cannot come from one call and cannot be derived from each other. An unlabelled or wrongly-defaulted result is indistinguishable from a correct one at a glance.
- Risk source: PRD §9 (R4, R5)
- Verify: With the API mocked and call-counting enabled, invoke the tool three ways: default, expected-only, and both. Inspect the request count, each request's `includeDisabled` value, and the returned labels.
- Expected: Default issues one call with `includeDisabled=false` and labels the result runnable. Expected-only issues one call with `includeDisabled=true` and labels it expected. Both issues exactly two calls, one of each, and returns both results labelled, together with the note that expected cannot be derived from runnable.
- Evidence required: pytest run output naming the test, with the per-mode call counts visible.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-28 — The tool scores an ad-hoc plan against a real console and returns usable numbers

- Description: Proves the whole path works against the real Core service, which is the only way to know the request shape and response parsing are actually right.
- Status: Active
- Passes after: Phase 5
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: Every mocked test encodes an assumption about the real endpoint. The maps are untyped at the source, so only a live call confirms the shape.
- Risk source: PRD §9 (assumptions)
- Verify: Against the configured e2e console, build a plan body from a step of an existing scenario read through the product's own scenario API, then call the tool with default parameters.
- Expected: A per-step result is returned. `simulationCount` is an integer, `moves` and the three simulator maps are populated with integer values, and where conflicts exist each carries a translated description and suggested fix. No field contains a bare reason code.
- Evidence required: pytest e2e run output naming the test, plus the console name and the returned counts.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-29 — Scoring by scenario_id agrees with scoring the same scenario's body ad hoc

- Description: Proves the two input modes are two routes to one answer, which is what makes the saved-scenario passthrough trustworthy.
- Status: Active
- Passes after: Phase 5
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: The by-id path is resolved server-side from a code path this repo does not control. If it diverged from the ad-hoc path, callers would silently get different numbers for the same scenario.
- Risk source: PRD §9 (assumptions)
- Verify: Against the e2e console, pick an existing scenario or custom plan through the product's own listing APIs. Call the tool once with its id, and once with its steps as an ad-hoc body, using identical parameters.
- Expected: Both calls return the same number of steps and the same per-step `simulationCount`. If the target is a custom plan, the integer-as-string id is accepted as readily as a scenario UUID.
- Evidence required: pytest e2e run output naming the test, with both count sequences shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-30 — Runnable never exceeds expected, and the offline reason explains the gap

- Description: Proves the feature's most user-visible correction against the live service — that a disconnected simulator is no longer counted as if it would run, and that the tool can say why.
- Status: Active
- Passes after: Phase 5
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: The parameter's behaviour is the inverse of its intuitive reading, and it was read from source rather than observed. If that reading is wrong, the default asks for the wrong number.
- Risk source: PRD §9 (R4)
- Verify: Against the e2e console, score the same scenario twice — runnable then expected — and compare. Then inspect the runnable response's conflicts for the offline reason. When the console has no disabled or unapproved simulator, skip the delta and offline-reason assertions with an explicit reason naming that precondition, and still assert the ordering relation.
- Expected: Runnable `simulationCount` is less than or equal to expected for every step. When a disabled simulator exists, the runnable response reports the offline reason for it and the expected response does not, and the delta is strictly positive for at least one step. A skipped assertion is reported as a skip with its reason, never as a pass.
- Evidence required: pytest e2e run output naming the test, with both count sequences, the disabled-simulator precondition status, and any skip reason.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-31 — A step-less plan against a real console yields the typed error, not a raw 400

- Description: Confirms against the live service that the most common mid-construction state reads as guidance rather than as a tool failure.
- Status: Active
- Passes after: Phase 5
- Level: e2e
- Execution: Automatic
- Risk: The pre-flight rejection is asserted against a mock in T-8. Only a live call confirms the real endpoint still behaves as the pre-flight assumes, and that no other path reaches it.
- Risk source: PRD §9 (edge cases)
- Verify: Against the e2e console, call the tool with a plan body carrying no steps.
- Expected: A typed error naming the missing steps, matching T-8's message. No unhandled HTTP error and no raw upstream error code surface to the caller.
- Evidence required: pytest e2e run output naming the test, with the error message shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-32 — An agent can answer "what will run and what won't, and why" through the real product

- Description: The progression walkthrough — proves the tool delivers its actual purpose as a conversational capability, which no assertion on a payload can establish.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: Every criterion can pass while the tool remains unusable in conversation — for instance if the response is too large to reason over, or its wording does not let an agent explain a conflict to a user.
- Risk source: PRD §9 (R3, assumptions)
- Verify: Through an MCP client connected to the e2e console, take an existing scenario, call `get_plan_statistics`, and have the agent state in plain language how many simulations will run, which attacks or simulators will not contribute, and why. Then change one step's filter and call again to confirm the answer changes accordingly. Preconditions come from existing console scenarios read through the product's own APIs — no seeding.
- Expected: The agent produces a correct, plain-language answer with per-conflict explanations and suggested fixes. No raw reason code appears in anything shown to the user. The second call reflects the changed filter, demonstrating freshness. If the tool cannot be reached or the response cannot be interpreted, the test reports BLOCKED.
- Evidence required: transcript of the agent session, the tool invocations and responses, and observed-versus-expected for each claim.
- Manual because: the assertion is a judgment about whether the response is interpretable and explainable in conversation — not a deterministic value.
- Environment needs: Validate console environment

### T-33 — The two shipped run tools still preview correctly against a real console

- Description: The mandatory regression walkthrough — proves the refactor did not degrade the shipped capability that most users touch, exercised through the real product rather than through fixtures.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: regression
- Risk: The refactor rewires the code path behind both run tools. Fixture-level equality is necessary but does not prove the tools still behave against the live service.
- Risk source: PRD §9 (R2)
- Verify: Against the e2e console, run the scenario-run tool in evaluate mode on an existing scenario and the quick-run tool in evaluate mode on a small set of playbook attack ids, using scenarios and attacks read through the product's own APIs. Compare each preview against the same invocation recorded before the change. Confirm neither queues a test.
- Expected: Both previews return the same predicted totals and per-step breakdown as before the change, and neither queues a test. Any numeric difference is explained by console state changing between runs, not by the refactor.
- Evidence required: transcript with both tool invocations and responses, the before/after comparison, and confirmation that no test was queued.
- Manual because: it asserts unchanged end-to-end behaviour of two shipped tools against live console state, where the baseline is a prior observed run rather than a value that can be computed deterministically.
- Environment needs: Validate console environment

### T-34 — The tool catalog documents the new tool and the gate table is left alone

- Description: Proves the documentation requirement is met in the precise way the project's own conventions demand, including the deliberate omission.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: The project treats its tool catalog as the tool contract. An undocumented tool is invisible to future contributors, and wrongly adding it to the rate-limiting table would contradict the stated gate rule.
- Risk source: PRD §9 (assumptions)
- Verify: Read the project instruction file. Assert the Studio Server tool catalog contains an entry for the new tool, and that the rate-limiting gate table's row set is unchanged.
- Expected: The catalog entry is present and names the runnable default and the read-only posture. The gate table contains no row for the new tool.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-35 — The tool's Checkout-parameter numbers match what the console itself displays

- Description: The independent cross-layer check — proves the tool agrees with what a user actually sees in the product, which is the requirement's own wording and cannot be shown by comparing the tool to itself.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: API-contract
- Risk: Every other parity test compares the tool against the same API it calls. Only reading the rendered console view falsifies the claim that the numbers match the product, and the two views legitimately differ by parameter set.
- Risk source: PRD §9 (R4)
- Verify: For one scenario on the e2e console, open the Add Simulators Checkout view and record the displayed simulation count. Call the tool for the same scenario with the Checkout parameter set (expected counts, constraints requested) and compare. Repeat the comparison against the run-gating view using the runnable parameter set.
- Expected: The tool's count equals the Checkout view's displayed count for the Checkout parameter set, and equals the run-gating view's for the runnable parameter set. Where a view greys out Run because a step yields nothing, the tool reports that step's count as zero.
- Evidence required: screenshots of both console views, the tool responses for both parameter sets, and an observed-versus-expected comparison per view.
- Manual because: the comparison target is a rendered console view and this repo has no browser automation of any kind (Python only); the automation repo's Playwright suites are the org's only browser infra, and standing up a cross-repo suite for a single parity check is disproportionate to the risk.
- Environment needs: Validate console environment

## Tests by Phase (readiness view — generated)

Cumulative: at the end of phase N, EVERY test with "Passes after" <= N must be green.

| After phase | Newly green | Cumulative green |
|-------------|-------------|------------------|
| Phase 1 | T-1, T-2, T-3, T-5 | 4 |
| Phase 2 | T-6, T-7, T-8, T-9, T-10, T-11, T-12 | 11 |
| Phase 3 | T-13, T-14, T-15, T-16, T-17 | 16 |
| Phase 4 | T-18, T-19, T-20, T-21, T-22, T-23, T-36 | 23 |
| Phase 5 | T-24, T-25, T-26, T-27, T-28, T-29, T-30, T-31 | 31 |
| Phase 6 | T-34 | 32 |
| Final | T-32, T-33, T-35 | all (35) |

## Sign-off

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [ ] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — >=1 Manual regression test (T-33) + post-ship CI named (with the no-test-CI gap recorded)
- [ ] Progression evidence — >=1 Manual progression test walking the new feature (T-32)
- [ ] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Final) — evidence: test-results/<phase-or-date>.md
- [ ] Accepted gaps listed and approved: none

## Change Log

| Date | Change |
|------|--------|
| 2026-08-26 12:04 | Test plan created from PRD v1 |
| 2026-08-26 16:35 | Fixed the Regression section's test list: dropped tombstoned T-4 and added T-2 and T-10, which carry `Aspect: regression` but were never listed. The list is now the complete regression set. |
| 2026-08-26 16:20 | Corrected for PRD v4 — the vendored translation table is **deleted**, not extended. **T-4 tombstoned** (Status: Removed, ID retained): its premise was preserving the 14 existing descriptions, which are now deliberately removed (PRD R9). T-1 rescoped to assert `CONSTRAINT_REASON_DESCRIPTIONS` no longer exists and that all 88 codes carry a valid-or-null lever with no meaning-bearing field; T-3 and T-23 assert an explicit `description: null` rather than a fabricated or bare-code explanation. R7 narrowed from descriptions to levers; R3 dropped to Low; R9/R10 added for the accepted regression and the SAF-35568 dependency. Regenerated views: 35 Active (15 unit / 13 integration / 7 e2e), phases 4/11/16/23/31/32/35. In Sync with PRD v4. |
| 2026-08-26 15:40 | Corrected for PRD v3 and aligned to SAF-35568. Verified at the emit sites that all 88 codes eliminate the node — the `informational` class does not exist, so **T-37 is tombstoned** (Status: Removed, ID retained) and `kind` is gone from T-1/T-3/T-36. T-1 now asserts a description plus a valid fix lever for all 88; T-3 asserts an unknown code is surfaced rather than dropped; T-4 covers all 14 legacy descriptions. R7 rewritten to "descriptions from names, not emit sites". Fixed the non-existent `safebreach-mcp/` path prefix on all automation locations. Regenerated views: 36 Active (16 unit / 13 integration / 7 e2e), phases 5/12/17/24/32/33/36. In Sync with PRD v3. |
| 2026-08-26 13:20 | Updated for the PRD v2 design revision (MCP is structured, Helm narrates). Rescoped T-1 (classification on two closed enums, no `suggested_fix`), T-3 (fail-safe to `elimination`, not a generic description), T-4 (retained-vs-dropped descriptions), T-23 (catalog normalization rather than per-conflict translation). Added T-36 (computed severity — same code blocking and reducing in one step) and T-37 (the 16 informational codes never block). Regenerated the unit index, Coverage Summary (17/13/0/7 = 37) and Tests by Phase; extended R7/R8/R9 traceability and Change Coverage. Status stays Draft — material change. In Sync with PRD v2. |
