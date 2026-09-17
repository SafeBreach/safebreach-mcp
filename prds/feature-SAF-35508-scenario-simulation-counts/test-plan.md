# Test Plan — Scenario Statistics MCP Tools (SAF-35508)

> PRD: ./prd.md  |  Branch: feature/SAF-35508-scenario-simulation-counts  |  Status: Draft  |  Updated: 2026-09-17

## Status & Review

| Field | Value |
|-------|-------|
| Status | Draft (In Sync with PRD 2026-09-17) — reset from Reviewed: Phase 6 added T-38 … T-44, a material change the 2026-09-16 scoped sign-off does not cover |
| Offering / surface | Validate + repo-harness |

## Requirements Traceability

Sources: JIRA acceptance criteria ∪ PRD §7 Definition of Done (user-confirmed at the authoring gate).
An uncovered requirement is a hard GAP — add a test or justify out-of-scope; never silent.

| Req | Requirement (from SAF-35508 ∪ PRD §7) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1 | Both tools accept an ad-hoc plan body with no saved scenario, and a saved numeric plan id passed through as `{id}` | T-3, T-31 | Covered |
| R2 | Exactly one of `scenario`/`scenario_id`/`test_id`; blank counts as absent; none-or-two errors naming all three | T-1 | Covered |
| R3 | A non-numeric `scenario_id` (OOB UUID) is refused, routing the caller to `get_scenario_details` | T-13, T-32 | Covered |
| R4 | A step-less scenario surfaces a typed error, not an unhandled 400 | T-2 | Covered |
| R5 | Counts tool surfaces per-step `simulationCount` and per-simulator attacker/target counts | T-6, T-14, T-31 | Covered |
| R6 | Counts are runnable; the expected figure is documented as underivable | T-9 | Covered |
| R7 | `isLimitReached` explicit; `null` never rendered as `0`; a short reply is reported as early termination | T-7 | Covered |
| R8 | 20-simulator listing cap keyed on the role-map union; past it count + narrow-filter ask; `simulator_ids` answered either way | T-14, T-15, T-16, T-33 | Covered |
| R9 | Blocked tool reports `moves[id]==0` attacks and `simulators[id]==0` simulators with their constraints | T-18, T-23, T-34 | Covered |
| R10 | Simulators absent from scoring are a distinct *excluded* state, never blocked | T-18, T-34 | Covered |
| R11 | Ran outranks blocked at the per-attack disposition, independent of step order | T-20 | Covered |
| R12 | Reporting blocks mutates nothing and never prevents saving | T-22 | Covered |
| R13 | No constraint meaning authored here; `constraintCatalog` relayed verbatim; absence disclosed | T-21, T-34 | Covered |
| R14 | Four-state verdict decided by whether counts were computed, never by list emptiness | T-19 | Covered |
| R15 | At the 50-attack cap: no partial list; a per-code tally covering every blocked attack | T-24, T-35 | Covered |
| R16 | The catalog at the cap covers every cited code, collected pre-cap | T-26, T-43 | Covered |
| R17 | A named `attack_id` carries its blockers in both cap states | T-27 | Covered |
| R18 | Tally rows carry no validator detail | T-25 | Covered |
| R19 | Both tools registered `readOnlyHint=True` and documented in the `CLAUDE.md` catalog | T-11 | Covered |
| R20 | The rate-limiting gate table is not extended | T-11 | Covered |
| R21 | No MCP-side caching, so no stale impact number can be served | T-12 | Covered |
| R22 | Exactly one HTTP request per call for every input form; zero playbook requests | T-8, T-13 | Covered |
| R23 | Fixed per-tool query parameters (counts `getConstraints=false`; blocked both `true`) | T-4, T-17 | Covered |
| R24 | Booleans sent in their JSON spelling, not the Python `"True"` string | T-5 | Covered |
| R25 | RBAC enforced via `check_rbac_response`; an HTTP failure becomes a typed error carrying status and body | T-10 | Covered |
| R26 | `simulator_ids` scopes the blocked-attack list to attacks blocked on the named simulators, each rendered with only the codes cited on that simulator | T-38, T-44 | Covered |
| R27 | The scoped list discloses its omission as an `n of m` ratio; the verdict, every total and both simulator-side sections stay scenario-wide and exact | T-39 | Covered |
| R28 | A named simulator **excluded** from scoring renders no scoped attack list and is reported as excluded | T-40, T-44 | Covered |
| R29 | A named simulator that ran, or is absent from the scenario, is answered explicitly; silence never stands in for an answer | T-41 | Covered |
| R30 | The 50-attack cap applies to the **scoped** list, and `simulator_ids` composes with `attack_ids` | T-42 | Covered |

## Change Coverage

Every file changed by the PRD (union of the §8 Changes tables) maps to >=1 unit test, or carries an
explicit justification. A file with neither is a validator violation — never silent.

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| `safebreach_mcp_studio/studio_functions.py` | T-1 … T-8, T-10, T-12 … T-27, T-29, T-30, T-38 … T-43 | — |
| `safebreach_mcp_studio/studio_server.py` | T-9, T-11, T-14, T-24, T-28, T-39 | — |
| `safebreach_mcp_studio/tests/test_scenario_simulation_counts.py` | T-1 … T-16 | Test file — it *is* the coverage it would otherwise need |
| `safebreach_mcp_studio/tests/test_scenario_blocked_entities.py` | T-17 … T-27, T-38 … T-43 | Test file — it *is* the coverage it would otherwise need |
| `CLAUDE.md` | — | Docs-only, no runtime surface. The catalog entry's existence is asserted indirectly by T-11 |
| `CHANGELOG.md` | — | Docs-only, no runtime surface |

## Risk Landscape

- Known risk areas:
  - `constraintCatalog` absent on the deployed console — orchestrator `e2c69b25f` (SAF-35568) is on `develop`, not
    necessarily the deployed build, so the catalog must be optional end to end (PRD §9).
  - `getAllConstraints=true` payload size on a large estate — one ordinary step measured 38,531 conflicts / 11.8 MB at
    `getAllConstraints=false`, and `true` is strictly larger. **Never yet measured at `true` against a real console**
    (PRD §9). Read-only tools get no rate-limit cover, so the caps are the only cost control.
  - The shared `_fetch_scenario_statistics` now serves two tools — a default drift would silently change the counts tool's
    question (PRD §9).
  - Reason codes are a moving vocabulary (97 today, ~102 before `e2c69b25f`) — nothing may be keyed on it (PRD §9).
  - Phase 5's tally is only as informative as the code variety — a step whose blocked attacks all cite one code renders
    one row (PRD §9).
  - **Phase 6: scoping to an excluded simulator would list every attack in the step as blocked on it** (PRD §9, High).
    Offline, disabled and unapproved nodes are seeded into `simulatorConstraints` carrying `simulator_is_offline` on
    *every* move, so the naïve scope is a maximal false positive — the exact confusion the three-state vocabulary
    exists to prevent. T-40 is the test that pins the short-circuit.
  - **Phase 6: an empty scoped list read as "the scenario is clean"** (PRD §9, Medium). The per-simulator answer and the
    unchanged scenario-wide verdict are what prevent it; T-39 and T-41 pin both halves.
  - **No CI in this repo executes pytest** (reviewer input, confirmed at the gate): only `release.yml` and
    `security-scan.yml` exist. Nothing mechanically prevents a regression from merging.
  - **`ruff` is not installed** (reviewer input): `uv run ruff` fails to spawn and ruff is absent from `uv.lock`, so the
    PRD's `ruff check --select F` gate is manual and non-reproducible as written.
  - ~~The 88 existing tests carry no `T-<n>:` title prefix~~ — **CLOSED 2026-09-16**: every test method now carries its
    plan id. **Selector convention: `pytest -k "T_<n>_"` with the trailing underscore** — a bare `-k "T_1"` also
    substring-matches T-10 … T-19 and silently over-selects, which is the one trap in this scheme.
- Existing coverage (investigated): input exclusivity, plan-body construction, the fixed query-parameter sets, the
  null-is-not-zero arbiter, moves-dropping, the paired simulator breakdown, both caps, named-id dispositions, the three
  simulator states, the verdict, attack dispositions, and catalog handling → `safebreach_mcp_studio/tests/`
  `test_scenario_simulation_counts.py` and `test_scenario_blocked_entities.py`. As of 2026-09-16 the gaps this plan
  targeted are closed in code: the MCP wrapper layer (T-28), the RBAC/`PermissionError` path (T-10, T-28), the
  runnable disclosure (T-9), no-MCP-caching (T-12), report-mutates-nothing (T-22) and transport failures (T-30) are all
  authored, alongside a new e2e suite (T-31 … T-35). The full studio suite is 594 passed / 50 skipped in 1.80s.
  Two gaps remain open: no recorded real-console payload (T-29) and no real-environment evidence for any e2e test.
- What we protect: the three-state simulator model (blocked vs excluded vs ran) and `null` never reading as `0` — the
  two claims whose silent breakage would make every answer confidently wrong; the fixed per-tool query parameters, which
  are what make each tool's cost predictable; and the one-request / zero-playbook-request cost contract.
- Intentionally out of scope:
  - **Verdict-level precedence for "ran outranks blocked"** — confirmed at the gate as *intended* behaviour: the verdict
    is a per-step union, and R11 scopes to the per-attack disposition only. An attack scoring 0 in one step and 240 in
    another is reported `ran` in `asked_about` while the verdict still counts the zero. T-20 pins the per-attack rule;
    nothing pins verdict-level precedence, by decision. The PRD's §3 Component C wording ("the answer never depends on
    step order") is broader than the delivered behaviour and should be narrowed — carried to the PRD, not tested here.
  - **Migrating `_get_scenario_statistics`** and its two callers onto the new path (ticket AC 6) — explicitly deferred by
    the PRD; the legacy path is untouched, so T-36 regresses it rather than testing a migration that does not exist.
  - **Name enrichment** for attacks and simulators — entities are reported as ids by design (zero playbook requests), so
    there is no name-resolution behaviour to test.
  - **Reductions / fail-rate conflicts** (SAF-35484) — an attack running on fewer simulators than offered is a reduction,
    not a block, and is deliberately not listed.

## Coverage Summary (generated)

| Execution | unit | integration | system | e2e | Total |
|-----------|------|-------------|--------|-----|-------|
| Automatic | 36   | 0           | 0      | 6   | 42    |
| Manual    | 0    | 0           | 0      | 2   | 2     |

## Environment Requirements (aggregated)

The environment CLASSES the plan needs (union of per-test `Environment needs`) PLUS the capability checklist —
the primary input to `design-test-environment`.

- Environment classes: `none` (unit); **Validate console environment** (e2e)

Capability checklist — answer EVERY line (Yes/No + one-line why; `N/A` only when the plan has no real-env test):

- [x] Simulators required? — **Yes**; the e2e tests score a scenario against a live fleet, and a count of zero would
  prove nothing about whether scoring works.
- [x] Running simulations / attacks required? — **No**; both tools only score a plan, so a static fleet plus a saved plan
  is sufficient and no queued test ever has to finish.
- [x] Mockulators sufficient? — **Yes**; mockulators carry `osType`/`isConnected`, so per-role numbers and
  `incompatible_os` arise normally, and bulk-create makes both the 20-simulator and 50-attack caps cheap to cross.
- [x] Console-specific configuration required? — **Yes**; at least one saved custom plan with a numeric id, one completed
  test for the `test_id` form, one offline/disabled simulator so *excluded* is observable, and a Windows+Linux mix so
  `incompatible_os` actually fires.
- [x] Lateral-movement topology required? — **No**; the feature touches no lateral-movement finding family, no AD
  behaviour and no `parentFindingIds` chain.
- Required additions (beyond class defaults): a console API token resolved non-interactively from the secret-provider
  chain. Minting that token may itself need one-time console admin access — a setup step before the run, never an
  interactive login inside a test.
- Artifacts under test: the `safebreach-mcp` Studio server run from this feature branch. No console image swap and no
  orchestrator build requirement, except that `constraintCatalog` assertions degrade to the absent-catalog path on a
  console older than orchestrator `e2c69b25f`.

## Regression

- CI that must pass: the repo's **Security Scan** GitHub Actions workflow, which runs on every pull request to `main`
  and `develop` and is the only CI gate this branch has. **No `Automation-Pen-Testing-*` suite applies** — the
  automation repo has zero MCP coverage and reaches this endpoint only by bypassing MCP entirely, so naming one would
  claim regression cover that does not exist. **No CI suite executes this repo's Python tests** (the only other
  workflow, `Release`, runs on version-bump tags), so the test-suite half of the regression gate is the executor
  running `SKIP_E2E_TESTS=true uv run --python 3.12 pytest safebreach_mcp_studio/tests` and recording the pass line.
  Both absences are carried as accepted gaps at Sign-off.
- Regression tests in this plan: T-36 (the mandatory Manual regression), plus Automatic T-12, T-17, T-19, T-29, T-30,
  and T-39 (Phase 6 — the scenario-wide totals must not move when the listing is scoped).

## Tests

Index by level (generated — Active tests only, sorted by Execution then T-id).

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|--------------|------|
| T-1 | The exactly-one-input rule is enforced before a request is spent | — | Phase 1 | safebreach-mcp |
| T-2 | A step-less scenario is refused locally rather than by a remote 400 | — | Phase 1 | safebreach-mcp |
| T-3 | Each input form builds the plan body the endpoint expects | API-contract | Phase 1 | safebreach-mcp |
| T-4 | The counts tool's question is pinned by its fixed query parameters | API-contract | Phase 1 | safebreach-mcp |
| T-5 | Boolean flags reach the endpoint as JSON, not as Python strings | API-contract | Phase 1 | safebreach-mcp |
| T-6 | Per-step and total simulation counts are preserved exactly | — | Phase 1 | safebreach-mcp |
| T-7 | An unmeasured count is never presented as a measured zero | — | Phase 1 | safebreach-mcp |
| T-8 | The tool costs exactly one request and never touches the playbook | perf | Phase 1 | safebreach-mcp |
| T-9 | The answer discloses that it is runnable, not expected | API-contract | Phase 1 | safebreach-mcp |
| T-10 | An API or RBAC failure surfaces as a typed error carrying the cause | security | Phase 1 | safebreach-mcp |
| T-11 | Both tools declare themselves read-only and stay outside the rate limiter | API-contract, security | Phase 4 | safebreach-mcp |
| T-12 | Repeated calls re-measure rather than serving a stale number | regression | Phase 1 | safebreach-mcp |
| T-13 | A scenario UUID is refused with the route to its own steps | API-contract | Phase 2 | safebreach-mcp |
| T-14 | One row per simulator carries both of its role numbers | — | Phase 3 | safebreach-mcp |
| T-15 | Past the listing cap the breakdown is dropped whole, never sampled | perf | Phase 3 | safebreach-mcp |
| T-16 | Named simulators are answered in both roles regardless of the cap | — | Phase 3 | safebreach-mcp |
| T-17 | The blocked tool asks for every constraint without moving its sibling | API-contract, regression | Phase 4 | safebreach-mcp |
| T-18 | A switched-off simulator is reported as excluded, not as incompatible | — | Phase 4 | safebreach-mcp |
| T-19 | The verdict follows whether counts were computed, not list emptiness | regression | Phase 4 | safebreach-mcp |
| T-20 | An attack that ran anywhere is reported as having run | — | Phase 4 | safebreach-mcp |
| T-21 | Constraint meanings come from the console or are absent, never invented | API-contract | Phase 4 | safebreach-mcp |
| T-22 | Asking what is blocked changes nothing about the scenario | — | Phase 4 | safebreach-mcp |
| T-23 | Blocked simulators are grouped by reason with their own detail | — | Phase 4 | safebreach-mcp |
| T-24 | At the attack cap every blocked attack is still accounted for | — | Phase 5 | safebreach-mcp |
| T-25 | A tally row never speaks for attacks it does not represent | — | Phase 5 | safebreach-mcp |
| T-26 | The catalog stays complete exactly when the list is dropped | — | Phase 5 | safebreach-mcp |
| T-27 | Naming an attack is the way back to its exact reasons | — | Phase 5 | safebreach-mcp |
| T-28 | What an agent actually receives on failure is a message, not a traceback | API-contract | Phase 4 | safebreach-mcp |
| T-29 | A renamed orchestrator field breaks a test rather than the answer | API-contract, regression | Final | safebreach-mcp |
| T-30 | A dead or slow console fails loudly instead of answering zero | regression | Final | safebreach-mcp |
| T-38 | Scoping by simulator lists only what is blocked on that machine | — | Phase 6 | safebreach-mcp |
| T-39 | Narrowing the listing never moves a total or the verdict | regression | Phase 6 | safebreach-mcp |
| T-40 | A switched-off simulator is never blamed for every attack in the step | — | Phase 6 | safebreach-mcp |
| T-41 | A named simulator that is fine says so rather than going quiet | — | Phase 6 | safebreach-mcp |
| T-42 | The cap follows the scoped list, and the two filters compose | perf | Phase 6 | safebreach-mcp |
| T-43 | Under scoping the catalog still explains exactly what is shown | API-contract | Phase 6 | safebreach-mcp |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-31 | The counts tool scores a real scenario against a real fleet | Automatic | — | Phase 1 | safebreach-mcp | Validate console environment |
| T-32 | All three input forms work against a live console | Automatic | API-contract | Phase 2 | safebreach-mcp | Validate console environment |
| T-33 | Real role numbers and the cap behave as measured, not as assumed | Automatic | — | Phase 3 | safebreach-mcp | Validate console environment |
| T-34 | The three-state model matches a live orchestrator | Automatic | — | Phase 4 | safebreach-mcp | Validate console environment |
| T-35 | The cap tally holds on a fleet large enough to trigger it | Automatic | perf | Phase 5 | safebreach-mcp | Validate console environment |
| T-44 | Simulator scoping holds against a real fleet, including a switched-off node | Automatic | — | Phase 6 | safebreach-mcp | Validate console environment |
| T-36 | The neighbouring tools that share the fetch helper still behave | Manual | regression | Final | — | Validate console environment |
| T-37 | An agent can actually assemble a scenario with these two answers | Manual | progression | Final | — | Validate console environment |

### T-1 — Exactly one of the three inputs, with blank treated as absent

- Description: Proves a caller cannot ask an ambiguous question, so every answer is traceable to one named input.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: If blank were treated as a choice, an empty form field would silently select an input the caller never named,
  and the answer would describe a different scenario than the one they held.
- Risk source: reviewer input
- Verify: Call each tool naming zero inputs; naming two; and naming one input whose value is empty or whitespace-only
  while a second is populated.
- Expected: Zero inputs and two inputs both raise an error whose message names all three of `scenario`, `scenario_id`
  and `test_id`. A blank value is treated as absent, so a blank plus one populated input is accepted as that one input,
  and a blank alone is refused as naming nothing.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-2 — A step-less scenario is refused before a request is spent

- Description: Proves the tool recognises an unanswerable question itself instead of paying a round trip to be told.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: The endpoint answers a step-less plan `400 NOT_ALLOWED`; surfacing that raw would read as a service fault
  rather than as the caller's own empty scenario, and would spend a request to learn it.
- Risk source: reviewer input
- Verify: Call with a `scenario` body whose `steps` is empty, and with one where `steps` is missing entirely.
- Expected: A typed error naming the missing steps is raised, and no HTTP request is issued at all.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-3 — Each input form builds the body the endpoint expects

- Description: Proves an unsaved configuration and a saved plan are both scoreable, which is the capability the feature exists to add.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: If an ad-hoc body were not relayed verbatim, a configuration still being assembled could not be scored at all —
  the one thing neither `run_scenario` nor `quick_run` offers.
- Risk source: reviewer input
- Verify: Call with an ad-hoc `scenario` body; with a numeric `scenario_id`; and with a `test_id`. Inspect the POST body
  sent in each case.
- Expected: The ad-hoc body is relayed as `{"name": ..., "steps": [...]}` with the submitted steps unaltered; a numeric
  id becomes `{"name": ..., "id": <int>}` with the id as an integer; a `test_id` becomes
  `{"name": ..., "testId": "<planRunId>"}`. No form carries more than one of the three keys.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-4 — The counts tool's fixed query parameters

- Description: Proves the counts tool always asks the cheap question, which is what makes its cost predictable.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A drifted default would either make the tool pay for constraints it discards, or change `includeDisabled` and
  silently turn a runnable count into an expected one without the answer saying so.
- Risk source: PRD §9
- Verify: Call the counts tool through each input form and capture the query parameters sent.
- Expected: Exactly `limit=500000`, `includeDisabled=false`, `getConstraints=false`, `getAllConstraints=false`,
  `useCache=true` — identical for every input form, with no parameter exposed as a tool argument.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-5 — Booleans are sent in their JSON spelling

- Description: Proves the flags mean to the endpoint what they mean in the code, rather than becoming a different question.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: `requests` serialises a Python `True` as the string `"True"`, which the endpoint reads as a different value —
  so a tool could silently request constraints it believed it had switched off.
- Risk source: PRD §9
- Verify: Capture the serialised query string actually sent for both tools.
- Expected: Boolean parameters appear as lowercase `true`/`false`, never as `True`/`False`.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-6 — Per-step and total counts are preserved exactly

- Description: Proves the number a caller acts on is the number the console measured, with no rounding, capping or re-derivation.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: A total derived by summing is wrong the moment any step is unmeasured; asserting zero for "summed nothing"
  would report a scenario that was never scored as one that produces nothing.
- Risk source: reviewer input
- Verify: Score a multi-step response whose steps carry distinct known counts, including a step at exactly zero, and
  one response where every step is unmeasured.
- Expected: Each step reports its own `simulationCount` verbatim; the total equals the sum of the measured steps; and
  when no step was measured the total is reported as not computed rather than as `0`.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-7 — An unmeasured count is never rendered as zero

- Description: Proves the answer distinguishes "measured, produces nothing" from "never measured" — the difference between a fact and a silence.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: On the circuit-breaker path the endpoint null-fills counts and returns a short step list. Rendering those nulls
  as zeros would tell a caller their scenario produces nothing when in truth it was never scored.
- Risk source: reviewer input
- Verify: Score a response with `isLimitReached` set; one whose `steps` is shorter than the submitted plan; one with a
  genuine measured `0`; and one whose count is the boolean `True`.
- Expected: `isLimitReached` is reported explicitly; an unmeasured count reads as not computed and never as `0`; a
  measured `0` reads as a measured zero; a reply shorter than the submitted plan is reported as early termination, and
  that claim is only made when the submitted step count is knowable. A boolean is not accepted as a count.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-8 — One request per call, zero playbook requests

- Description: Proves the tool's cost contract holds for every input form, which is what makes it safe to call while iterating.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: perf
- Risk: Resolving even one attack name costs the entire playbook (`?details=true`) since no per-id endpoint exists, so a
  single name lookup would turn a cheap scoring call into the most expensive call in the server.
- Risk source: PRD §9
- Verify: Call through each of the three input forms and count outbound HTTP calls; assert the attack map is discarded
  on arrival rather than carried into the shaped result.
- Expected: Exactly one POST per call for every input form; no playbook fetch and no scenario/plan listing call is made;
  the `moves` map is absent from everything the tool returns.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-9 — The answer discloses that it is runnable, not expected

- Description: Proves a caller cannot mistake a runnable count for the expected one, given the answer cannot supply the latter.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: `includeDisabled=false` both excludes disabled simulators and suppresses the offline reason, so the expected
  figure is not derivable from this response. A caller who assumed otherwise would under-read their own coverage.
- Risk source: reviewer input
- Verify: Read the registered tool's description and the rendered answer.
- Expected: Both state that counts are runnable — offline, disabled and unapproved simulators excluded — and that the
  expected figure is neither offered nor derivable from this response.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-10 — An API or RBAC failure surfaces as a typed error carrying the cause

- Description: Proves a refusal is distinguishable from an empty result, so a caller never reads "denied" as "nothing found".
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: security
- Risk: RBAC is enforced per call, and a permission failure rendered as an empty answer would tell a restricted caller
  their scenario produces nothing — a wrong answer that looks like a valid one. This path is currently unasserted:
  `check_rbac_response` is patched to a no-op in every existing test.
- Risk source: reviewer input
- Verify: Drive both tools with a non-2xx HTTP response, and separately with a `check_rbac_response` that refuses.
- Expected: A non-2xx response raises a typed error whose message carries both the status code and the response body.
  An RBAC refusal propagates as a permission error, distinct from any empty-result path, and never as zeros.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-11 — Both tools declare themselves read-only and stay outside the rate limiter

- Description: Proves the two tools are safe to call freely, which is the property that makes iterative scoring possible at all.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract, security
- Risk: A write-hinted registration would make an agent treat scoring as a destructive act and avoid it — reintroducing
  exactly the problem the feature was built to remove. Conversely a rate-limit gate on a read-only tool would throttle
  the iteration loop.
- Risk source: reviewer input
- Verify: Inspect both tools' registered annotations, and assert neither tool name appears in the rate-limiting gate
  table or calls the limiter's check/record functions.
- Expected: Both register with `readOnlyHint=True`; neither calls `check_limit` or `record_action`; the gate table is
  unchanged. Both appear in the `CLAUDE.md` tool catalog.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-12 — Repeated calls re-measure rather than serving a stale number

- Description: Proves a re-score after adjusting filters reflects the change, which is what makes the iterate-and-rescore loop trustworthy.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: If an MCP-side cache were introduced, a caller adjusting a scenario's filters would be shown the previous
  answer and would conclude their change had no effect.
- Risk source: reviewer input
- Verify: Call the same tool twice with identical input against a stub returning different payloads, and assert no
  Studio cache is read or written on either path.
- Expected: Each call issues its own POST and returns the payload it actually received; the second call reflects the
  changed payload.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-13 — A scenario UUID is refused with the route to its own steps

- Description: Proves the tool holds its one-request contract instead of quietly listing the console to resolve an id.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Resolving a UUID would require fetching every scenario or plan, which is the only path that ever issued a second
  request — turning a fixed-cost call into one that scales with the console.
- Risk source: reviewer input
- Verify: Call with an OOB scenario UUID, with a non-numeric string, and with a digits-only string; assert across all
  three input forms that no scenario-listing or plan-listing fetch occurs.
- Expected: A digits-only value is accepted as a plan id. Any non-numeric value — UUID included — is refused with a
  message naming `get_scenario_details` as the way to fetch the steps and pass them as `scenario`. No input form lists
  the console.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-14 — One row per simulator carrying both role numbers

- Description: Proves a role choice can be made from a single row, which is the decision the breakdown exists to support.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: Two separate per-role lists force a caller to join them mentally and hide the fact that a simulator offered in
  only one role is a target-only or attacker-only candidate. A simulator measured at zero that is hidden rather than
  listed withholds the most actionable statement the answer can make about a machine.
- Risk source: reviewer input
- Verify: Shape a response whose attacker and target maps overlap partially, include a simulator present in only one
  map and one present in both at a measured zero.
- Expected: Rows are built from the union of both maps, one row per simulator carrying its attacker number and its
  target number, ranked by total contribution. A simulator absent from one role says so in that role rather than
  reading as zero. A simulator measured at zero in both roles is listed, not hidden.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-15 — Past the listing cap the breakdown is dropped whole

- Description: Proves a large fleet yields a short honest answer rather than a long misleading one.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: perf
- Risk: A sample answers nobody — a caller reading "20 of 498" cannot tell whether their machine is among the 478
  unshown. Keying the cap on one role map rather than the union would also mis-trigger, since the union is the
  breakdown's actual length.
- Risk source: reviewer input
- Verify: Shape responses just under, exactly at, and over the cap, where the union exceeds the cap but neither role map
  does on its own. Measure the rendered output size for a 500-simulator fleet.
- Expected: Under the cap the full breakdown is present. At or over it the breakdown key is absent rather than empty,
  the step's simulation count is untouched, and the answer asks the caller to narrow the step's simulators filter —
  without instructing them to name `simulator_ids`. The 500-simulator rendering stays under 1,000 characters.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-16 — Named simulators are answered in both roles regardless of the cap

- Description: Proves naming a machine is a reliable way to get its number even when the breakdown is gone.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: If the named-id filter were dropped past the cap, the only per-simulator number available on a large fleet
  would disappear exactly when it is most needed.
- Risk source: reviewer input
- Verify: Name simulators that produce in both roles, in one role only, at a measured zero, and one absent from the
  scenario entirely — below the cap and again past it. Include duplicate and blank names.
- Expected: Each named simulator is answered in both roles with one of the four dispositions, identically below and
  past the cap. Duplicates collapse to one answer; an all-blank filter is refused before any request.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_simulation_counts.py
- Environment needs: none

### T-17 — The blocked tool asks for every constraint without moving its sibling

- Description: Proves each tool keeps its own cost profile, which is the whole reason the feature is two tools rather than one flag.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract, regression
- Risk: The two tools share one fetch helper. If the blocked tool's flags leaked into the shared defaults, the counts
  tool would start paying for an 11.8 MB constraint payload it discards — the exact coupling the split was meant to
  prevent.
- Risk source: PRD §9
- Verify: Capture the query parameters for the blocked tool, then for the counts tool in the same test session.
- Expected: The blocked tool sends `getConstraints=true` and `getAllConstraints=true`, sharing `limit=500000`,
  `includeDisabled=false` and `useCache=true`. The counts tool's parameters are unchanged, still with both constraint
  flags `false`.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-18 — A switched-off simulator is excluded, not incompatible

- Description: Proves the answer separates "cannot run this" from "is switched off" — a distinction that changes what a caller should do next.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: Offline nodes carry `simulator_is_offline` in the constraint structure while never being seeded into the count
  map. Folding the two states together would report every switched-off machine as incompatible, sending a caller to fix
  an OS mismatch that does not exist.
- Risk source: reviewer input
- Verify: Shape a response containing a simulator present in the count map at `0`, one absent from the count map but
  present in the constraint structure, one producing a positive count, and one whose count is unmeasured.
- Expected: Present-and-zero is reported as blocked with its constraints; absent-from-scoring is reported under a
  distinct excluded category citing why it was not scored; a positive count is neither; an unmeasured count is neither
  blocked nor excluded.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-19 — The verdict follows whether counts were computed

- Description: Proves a report that was never scored is never mistaken for a scenario with nothing wrong.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: A verdict read off list emptiness is the single most dangerous bug available here: an early-terminated report
  empties both lists by construction, so emptiness would render as `clean` — telling a caller their scenario is fine
  when in fact nobody measured it.
- Risk source: reviewer input
- Verify: Drive the verdict with a fully-scored report containing blocked entities; a fully-scored report with none; a
  report whose counts are entirely unmeasured; and one partially measured. Then mutate the implementation to derive the
  verdict from list emptiness and re-run.
- Expected: The four states follow from whether counts were computed — `blocked`, `clean`, `partially_evaluated`,
  `not_evaluated` — with `not_evaluated` stated as explicitly not a clean result. Counts are over distinct entities
  scenario-wide. The emptiness mutation is caught by at least two assertions.
- Evidence required: the exact pytest command scoped to this id plus its pass line, and the mutation run's failure output.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-20 — An attack that ran anywhere is reported as having run

- Description: Proves a per-attack answer reflects the whole scenario rather than whichever step happened to be examined first.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: An attack scored `0` in one step and positive in another has run. Reporting it as blocked would send a caller
  to fix a constraint that is not stopping anything.
- Risk source: reviewer input
- Verify: Ask about an attack scoring `0` in the first step and positive in a later one, then reverse the step order and
  ask again.
- Expected: The attack's disposition is `ran` with its positive count in both step orders. An attack scoring zero in
  every step is `blocked`; one never scored is `not computed`; one absent from the scenario says so. (Scope note: this
  is the per-attack disposition. Verdict-level precedence is intended to be a per-step union and is deliberately not
  asserted — see Intentionally out of scope.)
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-21 — Constraint meanings come from the console or are absent

- Description: Proves this repo never authors a meaning, so a vocabulary change on the console cannot make the answer wrong.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A vendored meaning table rots in both directions — `ui-react` carried an "interim" copy for years. A stale local
  description attached to a live code would confidently explain a constraint incorrectly.
- Risk source: PRD §9
- Verify: Shape a response with a catalog describing some cited codes; one whose catalog is absent entirely; one whose
  catalog omits a code that is cited; and one citing codes the catalog does not know.
- Expected: Descriptions are relayed verbatim from the response's own catalog and narrowed to the codes this answer
  cites. A code the console did not describe is reported bare and stays undescribed. An absent catalog is disclosed as
  such rather than failing or substituting a local meaning.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-22 — Asking what is blocked changes nothing

- Description: Proves the tool is a report, so a caller can ask freely while assembling without risking their configuration.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: If reporting removed blocked entities or gated saving, the tool would make decisions that belong to whoever
  holds the configuration.
- Risk source: reviewer input
- Verify: Score an ad-hoc scenario body, then compare the caller's body against its pre-call state; assert only the
  statistics endpoint is called.
- Expected: The submitted scenario is byte-identical after the call, nothing is removed from it, no save or update
  endpoint is contacted, and the tool issues no request other than the single statistics POST.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-23 — Blocked simulators are grouped by reason with their own detail

- Description: Proves the simulator half of the answer stays specific, since there a row is one machine rather than many.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: The sparse constraint structure prunes empty leaves, so an absent simulator means "evaluated, nothing recorded"
  rather than "not evaluated"; conflating them would invent a blocker. Only `reason` is guaranteed on a leaf, so
  assuming the optional detail fields exist would break on real payloads.
- Risk source: reviewer input
- Verify: Shape blocked simulators citing several codes, some leaves carrying `required`/`actual` detail and some
  carrying only `reason`; include a blocked simulator with no recorded constraint at all; exceed the simulator cap.
- Expected: Blocked simulators are grouped per constraint code carrying their own per-simulator detail where the leaf
  supplied it, and omitting it where it did not — never fabricated. A blocked simulator with nothing recorded is still
  reported, as unexplained. Past the node cap a bounded number of ids is named per code followed by a count, and no
  count map is capped, so totals stay exact.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-24 — At the attack cap every blocked attack is still accounted for

- Description: Proves a large blocked set is summarised rather than sampled, so no attack silently disappears from the answer.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: The superseded behaviour returned the first fifty of sixty blocked attacks, leaving ten unaccounted for while
  costing ~8,500 characters and burying the fact a tally makes obvious — on the measured fixture one offline machine was
  implicated in all sixty.
- Risk source: reviewer input
- Verify: Shape a step with more blocked attacks than the cap allows, citing a mix of constraint codes, and one step
  just below the cap.
- Expected: Below the cap the per-attack list is present. Past it the list key is absent rather than empty, and is
  replaced by a per-code tally whose blocked-attack counts sum to the exact number of blocked attacks in that step.
  Tally rows are ordered by attack count descending then by code. The simulator and excluded sections are unaffected,
  and a hint routes the caller to `attack_ids` for exact per-attack reasons.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-25 — A tally row never speaks for attacks it does not represent

- Description: Proves a summarised row stays honest by omitting detail that belongs to only one of the attacks behind it.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: Validator detail on a leaf belongs to whichever leaf was recorded first. Thirty attacks failing `incompatible_os`
  need not share one `required`/`actual` pair, so showing one pair would misrepresent the other twenty-nine.
- Risk source: PRD §9
- Verify: Trigger the cap with blocked attacks whose leaves carry differing `required`/`actual` values under the same
  code, and inspect the tally rows and, separately, the simulator rows.
- Expected: Tally rows carry the code, the blocked-attack count and the sides it was recorded against, and no
  validator detail fields. Simulator rows still carry their detail, since there a row represents one simulator.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-26 — The catalog stays complete exactly when the list is dropped

- Description: Proves the meanings survive the cap, which is when a reader has least other context to work from.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: Collecting cited codes from the rendered rows would shrink the catalog as the list is dropped — removing
  descriptions at exactly the moment they are doing the most work.
- Risk source: reviewer input
- Verify: Trigger the attack cap with blocked attacks citing codes that appear only in the dropped per-attack list, and
  compare the catalog against the codes cited anywhere in the report.
- Expected: The catalog covers every code cited by any blocked entity, including codes that appear only in dropped
  rows, and remains narrowed to cited codes rather than relaying the whole vocabulary.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-27 — Naming an attack is the way back to its exact reasons

- Description: Proves the documented escape hatch from the cap actually works, since the answer tells callers to use it.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: The cap's hint routes callers to `attack_ids`. If a named attack's answer omitted its blockers past the cap,
  that instruction would lead nowhere and exact per-attack reasons would be unreachable on a large scenario.
- Risk source: PRD §9
- Verify: Name a blocked attack below the cap and again past it; also name an attack that ran, one never scored, and one
  absent from the scenario.
- Expected: A named blocked attack carries its blocking constraints in both cap states. An attack that ran is reported
  `ran` with its count and carries no blockers; one never scored reads not computed; one absent says it is not in this
  scenario.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-28 — What an agent receives on failure is a message, not a traceback

- Description: Proves the registered tool boundary behaves as an agent experiences it, which no current test exercises.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Every existing error assertion targets the inner function via `pytest.raises`, so nothing pins what the
  registered wrapper actually returns. A wrapper that leaked an exception, or that swallowed the cause into a bare
  string, would degrade every error path without failing a test.
- Risk source: reviewer input
- Verify: Invoke both registered tools — not the inner functions — with a refused input, a non-2xx API response, and an
  RBAC refusal.
- Expected: Each returns a text answer naming the tool and carrying the underlying cause; no exception escapes the
  registered boundary; a refusal remains distinguishable from an empty or zero result.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-29 — A renamed orchestrator field breaks a test, not the answer

- Description: Proves the tools are pinned against a real response shape rather than against fixtures that encode our own assumptions.
- Status: Active
- Passes after: Final
- Level: unit
- Execution: Automatic
- Aspect: API-contract, regression
- Risk: Every existing fixture is a hand-built minimal dict, so a rename of `attackerSimulators`, `simulatorConstraints`
  or `constraintCatalog` on the orchestrator would pass all 88 tests while making every answer silently empty. The
  vocabulary is known to move — 97 codes today, ~102 before `e2c69b25f`.
- Risk source: PRD §9
- Verify: Capture one real `plan/statistics` response from a live console (constraints requested and not requested),
  commit it as a recorded fixture, and drive both tools' shaping layers from it.
- Expected: Both tools produce a non-empty, correctly-shaped answer from the recorded payload; the assertions reference
  the payload's real field names, so a rename fails this test rather than emptying the answer. The recorded fixture
  notes the console and date it came from.
- Evidence required: the exact pytest command scoped to this id plus its pass line, and the recorded fixture's provenance note.
- Automation lives in: planned: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_statistics_contract.py
  (the file exists and carries the rest of the contract suite; this case alone is still unwritten, because it
  needs a payload captured from a live console — a hand-built stand-in would re-assert the shapes this test
  exists to check. The file's docstring records that.)
- Environment needs: none
  - Requires a one-off capture from a reachable console before it can be authored.

### T-30 — A dead or slow console fails loudly instead of answering zero

- Description: Proves an infrastructure failure is never dressed up as a measured result.
- Status: Active
- Passes after: Final
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Transport failures are currently unasserted. A connection error or malformed body that degraded into an empty
  shaped result would be indistinguishable from a scenario that genuinely produces nothing.
- Risk source: reviewer input
- Verify: Drive both tools with a connection error, a timeout, a 200 carrying a non-JSON body, and a 200 whose `data`
  key is missing or null. Separately assert the configured request timeout is passed to the HTTP call.
- Expected: Each failure raises a typed error naming what went wrong; none produces zeros, an empty answer, or a
  `clean` verdict. The statistics request carries the module's configured timeout rather than defaulting to none.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_statistics_contract.py
- Environment needs: none

### T-31 — The counts tool scores a real scenario against a real fleet

- Description: Proves the feature's core promise end to end — an unsaved configuration is scored against the live estate without running anything.
- Status: Active
- Passes after: Phase 1
- Level: e2e
- Execution: Automatic
- Risk: Every existing result comes from canned payloads and from reading the orchestrator source; nothing has been
  compared against a live console. A shape mismatch, an auth-header gap or an account-id error would surface only here.
- Risk source: reviewer input
- Verify: Against a mockulator-backed Validate console, discover an existing scenario's steps and submit them as an
  ad-hoc `scenario` body. Assert no test is queued as a side effect by checking the console's test list is unchanged.
- Expected: A single POST returns within the configured timeout; the answer reports a per-step `simulationCount` and a
  total consistent with those steps; at least one step produces a positive count on a connected fleet; no test appears
  in the console's execution history as a result of the call.
- Evidence required: the exact pytest command, the console name, the returned totals, and the run timestamp. No CI job
  exists to run this — recorded as an accepted gap.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py
- Environment needs: Validate console environment

### T-32 — All three input forms work against a live console

- Description: Proves the saved-plan and test-run entry points resolve against real ids, which fixtures cannot demonstrate.
- Status: Active
- Passes after: Phase 2
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: The numeric-id and `test_id` forms depend on the endpoint accepting `{id}` and `{testId}` bodies as the
  orchestrator source suggests. If either were rejected in practice, two of the three documented entry points would be
  unusable while every unit test still passed.
- Risk source: reviewer input
- Verify: On the same console, score the same underlying configuration three ways — as an ad-hoc body, by the saved
  custom plan's numeric id, and by a completed test's planRunId. Then pass an OOB scenario UUID.
- Expected: All three forms return a scored answer, each costing exactly one request. The UUID is refused locally with
  the message routing to `get_scenario_details`, without contacting the console.
- Evidence required: the exact pytest command, the console name, the plan id and planRunId used, and the run timestamp.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py
- Environment needs: Validate console environment

### T-33 — Real role numbers and the cap behave as measured

- Description: Proves the paired breakdown and its cap hold against a real fleet, where role membership is not something we chose.
- Status: Active
- Passes after: Phase 3
- Level: e2e
- Execution: Automatic
- Risk: The union-keyed cap and the attacker/target pairing are derived from how the orchestrator populates its three
  simulator maps. If a live response populates them differently from the fixtures, the breakdown could mis-rank, or the
  cap could trigger on the wrong size.
- Risk source: reviewer input
- Verify: Score a scenario on a fleet below the listing cap and assert the breakdown; then bulk-create mockulators to
  push the offered union past the cap and re-score. Name specific simulator ids in both runs.
- Expected: Below the cap every offered simulator appears once with both role numbers, ranked by total contribution,
  with one-role simulators saying so in the other role. Past the cap the breakdown is absent while the step's count is
  unchanged and the narrow-your-filter ask appears. Named ids are answered in both roles in both runs.
- Evidence required: the exact pytest command, the console name, the fleet sizes used either side of the cap, and the run timestamp.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py
- Environment needs: Validate console environment
  - Requires a fleet that can be grown past the listing cap and shrunk back within the run.

### T-34 — The three-state model matches a live orchestrator

- Description: Proves the feature's sharpest claim — blocked versus excluded versus ran — against a console that genuinely has a switched-off machine.
- Status: Active
- Passes after: Phase 4
- Level: e2e
- Execution: Automatic
- Risk: This is the claim a fixture cannot honestly test, because a fixture only re-asserts the shape we assumed. If a
  live orchestrator seeds offline nodes differently, every switched-off machine would be reported as incompatible and
  callers would chase constraints that do not exist.
- Risk source: reviewer input
- Verify: On a console carrying at least one offline or disabled simulator and a Windows+Linux mix, score a scenario
  whose steps constrain OS, requesting constraints.
- Expected: The offline or disabled simulator appears under the excluded category citing its not-scored reason, and does
  not appear as blocked. An OS-mismatched but connected simulator appears as blocked citing an OS constraint. The
  verdict reflects computed counts. If the console predates the catalog commit, descriptions are reported absent rather
  than invented — and the test asserts that disclosure instead of failing.
- Evidence required: the exact pytest command, the console name, the offline simulator's id, the cited constraint codes,
  and the run timestamp.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py
- Environment needs: Validate console environment
  - Requires at least one offline or disabled simulator and simulators of two OS families.

### T-35 — The cap tally holds on a fleet large enough to trigger it

- Description: Proves the summarise-don't-sample rule survives contact with a real constraint payload, which is the expensive path never yet measured live.
- Status: Active
- Passes after: Phase 5
- Level: e2e
- Execution: Automatic
- Aspect: perf
- Risk: `getAllConstraints=true` has never been measured against a real console. One ordinary step measured 38,531
  conflicts / 11.8 MB at `false`, and `true` is strictly larger — with no rate-limit cover, an unbounded real payload
  is the feature's main operational risk.
- Risk source: PRD §9
- Verify: Build a scenario and fleet that put more blocked attacks in a step than the cap allows, score it with
  constraints requested, and record the wall-clock duration and response size.
- Expected: The per-attack list is absent and the per-code tally's counts sum to the step's exact blocked-attack total.
  The catalog still covers every cited code. Naming one of the capped attacks returns its exact blockers. The call
  completes within the configured timeout, and the observed payload size is recorded so the PRD's unmeasured risk
  becomes a measured one.
- Evidence required: the exact pytest command, the console name, the blocked-attack count, the measured response size
  and duration, and the run timestamp.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py
- Environment needs: Validate console environment
  - Requires a fleet and scenario able to produce more blocked attacks in one step than the attack cap.

### T-36 — The neighbouring tools that share the fetch helper still behave

- Description: Proves the refactor that introduced two new callers did not change what the existing pre-flight tools tell an agent.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: regression
- Risk: `_fetch_scenario_statistics` gained two keyword flags and now serves two additional tools. `run_scenario` and
  `quick_run` with `evaluate=True` consume constraint summaries shaped differently from the new tools. A defaults drift
  would change their narrated pre-flight without failing any assertion, since their output is prose an agent reads.
- Risk source: PRD §9
- Verify: On the same console, exercise the real product surface as an agent would: call `run_scenario` with
  `evaluate=True` on a scenario, and `quick_run` with `evaluate=True` on explicit attack ids. Read the returned
  pre-flight narratives and compare them against the same two calls made from `main` for the same inputs. Confirm
  neither call queued a test by checking the console's execution history.
- Expected: Both tools still return a per-step simulation preview with their constraint summaries, semantically
  unchanged from the `main` baseline — same steps, same counts, same constraint framing — and neither queues a test at
  `evaluate=True`. Any difference is reported as a regression rather than judged acceptable.
- Evidence required: transcript of both calls on each branch, the console name, the two narratives side by side, and the
  observed-versus-expected judgement.
- Manual because: the assertion is semantic equivalence of two rendered prose narratives that no stored baseline pins;
  judging whether a wording difference is cosmetic or a behavioural change is exactly the judgment call that cannot be
  reduced to a deterministic comparison.
- Environment needs: Validate console environment

### T-37 — An agent can assemble a scenario from these two answers

- Description: Walks the feature's whole reason for existing through the real product — score, spot a zero, ask why, adjust, re-score — and judges whether the answers are actually actionable.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: Every individual behaviour can be correct while the combined answer is still unusable — ids without names, a
  cap that fires too early, a hint that loops back on itself. The feature's value is that an agent can act on the
  answer, and only a walkthrough tests that.
- Risk source: reviewer input
- Verify: Follow the PRD §5 primary flow against a live console. Hold an unsaved scenario body; call
  `get_scenario_simulation_counts`; identify a simulator measured at zero in both roles and one offered in a single
  role; call `get_scenario_blocked_entities` on the same body to learn why the zero produces nothing; adjust the
  scenario's filters accordingly; re-score and confirm the numbers moved.
- Expected: The counts answer supports a concrete attacker/target selection without a follow-up call. The blocked answer
  explains the zero with a cited code and, where the console supplies a catalog, a description. The hints route between
  the two tools rather than in a circle. The re-score reflects the adjusted filters. No test is queued at any point.
- Evidence required: the full transcript of the call sequence, the console name, the simulator and attack ids reasoned
  about, the before and after counts, and an explicit judgement on whether the answers were sufficient to act on.
- Manual because: the question is whether the rendered answers are coherent and actionable for an agent assembling a
  configuration — a judgment about usefulness that no assertion captures.
- Environment needs: Validate console environment

### T-38 — Scoping by simulator lists only what is blocked on that machine

- Description: Proves the filter answers the per-machine question it was added for, rather than re-printing the scenario-wide list.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: A filter that narrows the heading but not the rows would read as a per-machine answer while still showing every
  blocked attack — the caller would act on attacks that have nothing to do with the simulator they named.
- Risk source: PRD §7
- Verify: Shape a step whose blocked attacks are blocked by constraints recorded against different simulators, with at
  least one attack cited against several simulators and at least one cited against none of the named ones. Name a
  single simulator, then name two.
- Expected: The scoped list contains exactly the blocked attacks whose recorded constraints cite a named simulator, and
  no others. Each listed attack shows only the codes cited against that simulator — a code recorded only against a
  different simulator does not appear on the line. Naming two simulators returns the union.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-39 — Narrowing the listing never moves a total or the verdict

- Description: Proves the tool's central invariant survives the new filter — naming ids changes what is shown, never what is claimed.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: If scoping narrowed the counted set rather than the listed set, a caller could narrow their way into a clean
  verdict on a blocked scenario. This is the same invariant `attack_ids` already relies on, so breaking it here breaks
  the tool's whole contract, not just the new parameter.
- Risk source: PRD §7
- Verify: Score one step-set twice — once with no `simulator_ids`, once naming a simulator implicated in only some of
  the blocked attacks — and compare the verdict, every total, and both simulator-side sections between the two runs.
- Expected: The verdict, `blocked_attacks_total`, `blocked_simulators_total`, `excluded_simulators_total` and both
  simulator-side sections are identical in both runs. The scoped run additionally discloses its own omission as an
  `n of m` ratio, where `m` is the unscoped blocked-attack total for that step and `n` the number listed.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-40 — A switched-off simulator is never blamed for every attack in the step

- Description: Proves the highest-risk edge of this feature — that naming an offline machine cannot turn every attack in the step into a false positive.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: Offline, disabled and unapproved nodes are seeded into the constraint map carrying `simulator_is_offline`
  against *every* move, so a naïve scope returns the entire step as "blocked on this simulator". That is the maximal
  false positive this tool can emit, and it contradicts the three-state model that keeps *excluded* distinct from
  *blocked*.
- Risk source: PRD §9
- Verify: Shape a step containing a simulator present in the constraint map but absent from the count map — carrying
  `simulator_is_offline` against every move — and name it in `simulator_ids`. Separately, name a simulator that is
  genuinely blocked, to confirm the short-circuit is keyed on exclusion and not on the code.
- Expected: The excluded simulator's answer is *excluded*, never *blocked*, and no scoped attack list is rendered for
  it — the absence is stated with its reason rather than left as an empty list. The scenario-wide verdict and every
  total are unchanged. The genuinely blocked simulator still produces its scoped list, so the short-circuit did not
  swallow the ordinary case.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-41 — A named simulator that is fine says so rather than going quiet

- Description: Proves an empty scoped list can be read correctly, because the simulator itself is always given an explicit state.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: Silence is ambiguous — a caller who names a healthy simulator and sees nothing cannot distinguish "nothing is
  blocked on it", "it is not in this scenario" and "it was never scored", and the most likely misreading is that the
  whole scenario is clean.
- Risk source: PRD §7
- Verify: Name, in one call, a simulator that contributed simulations, one absent from the scenario entirely, one in a
  step whose counts were never computed, and one that is blocked.
- Expected: Each named simulator is answered with exactly one state — ran (carrying its contribution), not in this
  scenario, not computed, blocked or excluded — and none is omitted from the answer. A count that was never measured is
  reported as not computed, never as a zero.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-42 — The cap follows the scoped list, and the two filters compose

- Description: Proves scoping is a real remedy for the cap rather than a second thing the cap ignores, and that the two filters are independent axes.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Aspect: perf
- Risk: If the cap were judged on the unscoped list, a caller who narrowed to one machine would still be handed a tally
  instead of the handful of attacks they asked for — scoping would fail exactly where it is most useful. If the two
  filters interfered, naming both would silently drop one of the answers.
- Risk source: PRD §7
- Verify: Shape a step whose unscoped blocked set exceeds the attack cap but whose scoped set falls under it, and the
  reverse. Then call with `simulator_ids` and `attack_ids` together.
- Expected: The cap decision follows the scoped list — under the cap the per-attack list is present even though the
  unscoped set exceeds it, and over the cap the list key is absent and replaced by the per-code tally. Naming both
  filters returns both answers: the named attacks keep their scenario-wide dispositions and the scoped list is still
  scoped by simulator; neither narrows the other.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-43 — Under scoping the catalog still explains exactly what is shown

- Description: Proves the meanings track the narrowed answer, so a scoped report is neither missing descriptions nor padded with irrelevant ones.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A catalog computed before scoping would describe codes the scoped answer never shows; one computed from the
  rendered rows alone would lose the codes dropped at the cap — the same shrinkage Phase 5 fixed, reintroduced through
  the new filter.
- Risk source: PRD §7
- Verify: Score a scoped report whose named simulator cites a subset of the step's codes, once below the attack cap and
  once above it, with a catalog supplied and again with none.
- Expected: The catalog covers every code cited anywhere in the rendered answer, including codes appearing only in
  dropped rows, and is narrowed to those codes rather than relaying the whole vocabulary. Because the blocked- and
  excluded-simulator sections stay scenario-wide by design, "the rendered answer" is the **union** of the scoped
  attack codes and those sections' codes — not the scoped attack codes alone; a code cited only by an out-of-scope
  *attack* and by no rendered simulator is what must be absent. With no catalog supplied, codes are rendered bare and
  the absence is disclosed rather than filled with a local meaning.
- Evidence required: the exact pytest command scoped to this id plus its pass line.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_scenario_blocked_entities.py
- Environment needs: none

### T-44 — Simulator scoping holds against a real fleet, including a switched-off node

- Description: Proves the filter works against constraints a live orchestrator actually emits, which is the only place the offline-seeding behaviour can be observed for real.
- Status: Active
- Passes after: Phase 6
- Level: e2e
- Execution: Automatic
- Risk: The offline short-circuit is built on a documented claim about how the orchestrator seeds excluded nodes into
  `simulatorConstraints`. Every unit test asserts that claim against a fixture that encodes it, so only a live console
  can confirm the claim itself — if it is wrong, T-40 passes while the real answer is a maximal false positive.
- Risk source: PRD §9
- Verify: Against a live console holding a saved plan and a fleet that includes at least one offline or disabled
  simulator, call `get_scenario_blocked_entities` unscoped, then scoped to a simulator that contributes, then scoped to
  the offline one.
- Expected: The scoped runs list strictly fewer blocked attacks than the unscoped run, and every listed attack's codes
  are ones the unscoped run also recorded for that simulator. The offline simulator is reported as excluded with no
  scoped list. The verdict and all totals are identical across all three runs. No test is queued at any point.
- Evidence required: the exact pytest command scoped to this id plus its pass line, the console name, the simulator ids
  used, and the three answers' totals side by side.
- Automation lives in: safebreach-mcp/safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py
- Environment needs: Validate console environment

## Tests by Phase (readiness view — generated)

Cumulative: at the end of phase N, EVERY test with "Passes after" <= N must be green.

| After phase | Newly green | Cumulative green |
|-------------|-------------|------------------|
| Phase 1 | T-1 … T-10, T-12, T-31 | 12 tests |
| Phase 2 | T-13, T-32 | 14 tests |
| Phase 3 | T-14, T-15, T-16, T-33 | 18 tests |
| Phase 4 | T-11, T-17 … T-23, T-28, T-34 | 28 tests |
| Phase 5 | T-24, T-25, T-26, T-27, T-35 | 33 tests |
| Phase 6 | T-38 … T-44 | 40 tests |
| Final | T-29, T-30, T-36, T-37 | all 44 |

## Sign-off

**Scope note (2026-09-16).** A **scoped** sign-off was recorded: the unit tier is signed off on per-id evidence;
the real-environment tier is **unverified and explicitly waived by the owner**. The three unchecked boxes below are
waived, not satisfied. The record is `test-results/signoff.md`. This plan's Status stays `Reviewed` rather than
`Signed off`, because a full sign-off requires every box.

**Superseded (2026-09-17).** That sign-off predates Phase 6. T-38 … T-44 are authored but unwritten and unrun, so the
boxes it covered no longer cover the current test set; Status is reset to `Draft` and the affected boxes are unchecked
below. The 2026-09-16 record stands as history for T-1 … T-37, not as evidence for this plan.

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope (30 R-rows; re-run the validator)
- [x] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — **WAIVED**: T-36 is authored but has never run; no console. CI suite named.
- [ ] Progression evidence — **WAIVED**: T-37 is authored but has never run; no console.
- [ ] validating-test-plan: RESULT: clean — must be re-run against the Phase 6 test set
- [ ] All tests green (cumulative through Final) — **WAIVED for the real-environment tier**. Unit tier green with
      per-id evidence for T-1 … T-30: 29 of 29 executed (`test-results/phase-Final.md`). Open: T-29 unwritten,
      T-31 … T-37 BLOCKED, and T-38 … T-44 not yet written (Phase 6 is pending implementation).
- [x] Accepted gaps listed and approved:
  - **No CI runs these tests.** The repo's only PR gate is the Security Scan workflow (secret scanning); nothing
    executes pytest. The e2e tier's normal butler-build evidence is therefore unavailable, and every tier's evidence is
    an executor-run command plus its output.
  - **No `Automation-Pen-Testing-*` suite covers this surface**, because the automation repo has no MCP coverage at all.
  - ~~The 88 existing tests carry no `T-<n>:` title prefix~~ — **CLOSED 2026-09-16**; select with
    `pytest -k "T_<n>_"` (trailing underscore required, or T-1 over-selects T-10 … T-19).
  - **T-29 is still unwritten** — it needs a response captured from a live console, and a hand-built stand-in would
    re-assert the very shapes it exists to check.
  - **Verdict-level "ran outranks blocked" is deliberately untested** — confirmed at the gate as intended per-step-union
    behaviour; the PRD's §3 Component C wording should be narrowed to match.
  - **`getAllConstraints=true` has never been measured against a real console**; T-35 is the test that converts this
    from an unmeasured risk into a measured one.

## Change Log

| Date | Change |
|------|--------|
| 2026-09-16 13:40 | Test plan created from PRD 2026-09-16 12:52 (retrospective — all 5 phases already delivered) |
| 2026-09-17 | Reconciled with PRD Phase 6 (`simulator_ids` scopes the blocked-attack list). Added R26 … R30 and T-38 … T-44 — six unit tests at Phase 6 plus one Phase 6 e2e, following the plan's per-slice e2e pattern. Extended R16 with T-43. Nothing reverted, so no tombstones and no existing T-id touched. Regenerated the index tables, Coverage Summary (42 Automatic / 2 Manual) and Tests by Phase. Status reset to Draft and the 2026-09-16 scoped sign-off marked superseded — a material change it does not cover. |
| 2026-09-16 14:45 | Phase Final execution follow-up. Every existing test method prefixed with its plan id (selector: `pytest -k "T_<n>_"`). Authored the cases that had none — T-9, T-12, T-22, T-28 and the RBAC half of T-10 — plus T-30 in a new contract suite and T-31 … T-35 in a new e2e suite; their `planned:` markers are now real paths. T-29 stays unwritten (needs a live-console capture). Suite: 594 passed / 50 skipped. Status stays Draft — the test set changed materially. |
