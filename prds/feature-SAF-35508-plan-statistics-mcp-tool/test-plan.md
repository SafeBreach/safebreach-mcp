# Test Plan — MCP support for Core plan statistics API (`get_plan_statistics`) (SAF-35508)

> PRD: ./prd.md  |  Branch: feature/SAF-35508-plan-statistics-mcp-tool  |  Status: Draft  |  Updated: 2026-09-02 00:00

## Status & Review

| Field | Value |
|-------|-------|
| Status | Draft (In Sync with PRD v7) |
| Offering / surface | Helm AI Agent (JIRA `Offering`) over the **Validate** product surface — scenarios/plans, simulators, plan statistics — via the safebreach-mcp Studio server |

## Requirements Traceability

Sources: JIRA acceptance criteria (AC-1…AC-12, reworded 2026-08-26) ∪ PRD §7 Definition of Done
(user-confirmed at the authoring gate).

| Req | Requirement (from SAF-35508 ∪ PRD §7) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1 | Ad-hoc plan body evaluated with no saved scenario; `scenario_id` passed to the orchestrator as `{id}`; a plan with no steps surfaces a typed error, not a raw 400 | T-6, T-7, T-8, T-11, T-26, T-28, T-29, T-31 | Covered |
| R2 | Surface per-step `simulationCount`, `moves`, `simulators`/`attackerSimulators`/`targetSimulators`, `isLimitReached`, structured constraints; pass through all five query params with documented defaults | T-6, T-9, T-11, T-28 | Covered |
| R3 | Runnable counts by default (`includeDisabled=false`); expected available; both-mode issues two labelled calls; documents that expected is not derivable from runnable | T-9, T-27, T-30 | Covered |
| R4 | Numbers match the console per view and per parameter set (Checkout `includeDisabled=true, getConstraints=true`; run gating `includeDisabled=false`) | T-30, T-35 | Covered |
| R5 | `isLimitReached` reported explicitly; `null` (not computed) vs `0` (runs nowhere) preserved; truncated step list surfaced; no zero-impact reporting on that path | T-10, T-15, T-22 | Covered |
| R6 | Exactly one `plan/statistics` call site; `_get_scenario_statistics` and its two callers routed through it, not a parallel implementation | T-13, T-14, T-16 | Covered |
| R7 | `CONSTRAINT_REASON_DESCRIPTIONS` deleted; **no** constraint vocabulary vendored — no table and no lever map; `constraint_catalog` filled by relaying the response's own `constraintCatalog`, with code keys and `description` text passed through verbatim | T-1, T-19, T-38, T-40 | Covered |
| R8 | Every conflict is surfaced rather than dropped, never with a bare code as its explanation; a code the API did not describe reports an explicit `description: null`; conflicts are normalized against a catalog; `severity` is computed from the counts alone | T-3, T-18, T-23, T-36, T-32, T-39 | Covered |
| R9 | Zero-impact attack (`moves[id] === 0`) **reported** as inapplicable with an explanation; reporting does not block save; `null` never reported as zero-impact | T-20, T-22, T-36 | Covered |
| R10 | Zero-impact simulator (`simulators[id] === 0`) reported the same way, read from the **union** map not a role map | T-21, T-22 | Covered |
| R11 | No MCP-side caching, so any change to an earlier decision produces a fresh call | T-12 | Covered |
| R12 | **Re-scoped for PRD v7** — three read-only tools registered (`get_scenario_simulation_counts`, `get_scenario_blocked_entities`, `get_scenario_attack_blockers`), `get_plan_statistics` unregistered; all three documented in the CLAUDE.md tool catalog; rate-limiting gate table not extended | T-24, T-25, T-34, T-32 | Covered |
| R13 | `sb_quick_run` and `sb_run_scenario` verified behaviourally unchanged | T-13, T-14, T-15, T-17, T-33 | Covered |
| R14 | Three tools, one question each, projecting the shipped report; `sb_get_plan_statistics` unchanged as the repo's single `plan/statistics` call site; no second fetch path and no duplicated zero-impact, severity, cap or null-safety logic | T-41, T-46, T-47, T-48 | Covered |
| R15 | Full parameter pass-through on all three tools; only defaults differ, and only where the question differs — `get_scenario_simulation_counts` defaults `get_constraints=False` | T-26, T-27, T-46 | Covered |
| R16 | Blocked-entities verdict distinguishes blocked / clean / **not-evaluated**; attack dispositions emitted only for ids the caller named; filtering precedes the zero-impact cap; fully-blocked (integer-`0`) scope only, with reducing conflicts stated as out of scope | T-42, T-43, T-44, T-45, T-48 | Covered |
| R17 | Caller-facing vocabulary is `scenario` — tool names, parameters, descriptions and the CLAUDE.md catalog; shipped internals keep `plan`, which is the API's own name for the endpoint | T-24, T-26, T-34 | Covered |

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| `safebreach_mcp_core/plan_statistics.py` | T-6, T-7, T-8, T-9, T-10, T-11, T-12, T-16 | — |
| `safebreach_mcp_studio/studio_functions.py` | T-1, T-3, T-13, T-14, T-15, T-17, T-18, T-19, T-20, T-21, T-22, T-23, T-26, T-36, T-38, T-39, T-41, T-42, T-43, T-44, T-45, T-46 | — |
| `safebreach_mcp_studio/studio_types.py` | T-20, T-21, T-23, T-36 | — |
| `safebreach_mcp_studio/studio_server.py` | T-24, T-25, T-47 | — |
| `CLAUDE.md` | T-34 | — |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | T-24, T-25, T-26, T-41, T-42, T-43, T-44, T-45, T-46, T-47 | Test file — its own coverage is the cases it carries; listed in PRD §8 Phases 7 and 8 because both phases add to it. |
| `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py` | T-48 | Test file — its own coverage is the e2e cases it carries (T-28…T-31, T-40, T-48). |

## Risk Landscape

- **Known risk areas** (PRD §9; reviewer added nothing further at the gate):
  - **R1 (High)** — misreading a limit-reached response. `simulationCount: null`, every `moves[id] = null`, and
    an early return that makes the step list shorter than the plan's. Treating falsy as zero, or assuming
    positional alignment, would report the user's whole selection as inapplicable.
  - **R2 (High)** — regressing the two existing callers. `_get_scenario_statistics` has 58 test references
    (~20 `@patch` decorators with hardcoded return dicts) plus `sb_quick_run` and `sb_run_scenario`.
  - **R12 (Medium, PRD v7)** — retiring a shipped tool is a breaking change for whoever already calls it.
    `get_plan_statistics` is registered, documented as CLAUDE.md entry 25, and has been exercised live. An MCP
    client naming it gets "unknown tool", not a redirect.
  - **R13 (Medium, PRD v7)** — three tools introduce a *selection* problem the single tool did not have. A
    model asked for a count can plausibly reach the blocked-entities tool, get a verdict and no number, and
    either answer wrongly or burn a second call. Guarded by T-47 rather than by prose review.
  - **R14 (Medium, PRD v7)** — the three Manual tests still owed (T-32, T-33, T-35) were written against a
    tool that will not exist. They are re-scoped rather than dropped, and **AC-4 stays unchecked**: a refactor
    must not be allowed to look like verification.
  - **R3 (Closed)** — vendored-meaning drift, designed out entirely: nothing is vendored — no table and no
    lever map — so there is no local vocabulary that can go stale. `ui-react`'s measured rot (3 dead entries,
    31 codes missing after years) is the evidence for relaying rather than a risk this plan still carries.
  - **R4 (Med)** — "matches the console" is not one number; Checkout and run-gating use opposite
    `includeDisabled` values.
  - **R5 (Med)** — cost of correctness; `getAllConstraints=true` disables the validator short-circuit.
  - **R6 (Closed)** — vendoring by source key rather than emitted value would ship two impossible codes and
    miss two real ones. Resolved twice over: SAF-35568 renamed both mismatched keys at source (97 codes, keys
    1:1 with emitted values) and MCP now enumerates nothing to key wrongly.
  - **R7 (Low)** — a remedy inferred from a code's name rather than its emit site: `*_is_ignored` reads like a
    user-changeable setting when nothing the caller controls affects it. No longer MCP's exposure — `fixLever`
    was dropped upstream as redundant and none is vendored here, so MCP asserts no remedy at all and cannot
    assert a wrong one.
  - **R8 (Med)** — asserting `severity` per code instead of computing it from the attack's count would label
    every `reducing` conflict a blocker, pulling SAF-35484's partial-impact scope in by accident.
  - **R9 (Low)** — meanings are not MCP's to supply, so their availability is someone else's deployment.
    Resolved by SAF-35568 shipping: every referenced code now arrives with an authoritative description — 83
    codes more than MCP ever vendored — and the 14 change wording rather than losing it.
  - **R10 (Closed)** — SAF-35568 was on Stage 1's critical path; it has delivered. It shipped *without* the
    `fixLever` half (removed as redundant), which is why no lever map is planned here, and its localization
    question was deferred rather than answered — which does not block MCP, since the relay is agnostic to
    which string the orchestrator serves.
  - **R11 (Med)** — console-version straddle. A console whose orchestrator predates SAF-35568 returns no
    `constraintCatalog`, so every conflict reports `description: null` — including the 14 that carried vendored
    prose before this ticket. Degrades rather than failing (same contract as an unrecognised code), with a
    `hint_to_agent` naming the cause. Covered by T-39 and exercised at the boundary by T-40.
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
| Automatic | 21 | 14 | 0 | 6 | 41 |
| Manual | 0 | 0 | 0 | 3 | 3 |
| **Total** | **21** | **14** | **0** | **9** | **44** |

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
- **Regression tests in this plan**: T-10, T-13, T-14, T-15, T-16, T-17 (Automatic) and **T-33**
  (the mandatory Manual regression). This is the complete set carrying `Aspect: regression` — T-2 and T-5 were
  tombstoned in the v5 update, so they no longer appear here.
- **PRD v7 note**: phases 7–9 retire a registered tool but change no shipped behaviour beneath it —
  `sb_get_plan_statistics`, the fetch core and both run tools are untouched. That property is exactly what
  T-13, T-14, T-16, T-17 and T-33 already assert, so the regression set is unchanged by the decomposition;
  T-46 additionally proves no new fetch path was introduced.

## Tests

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|--------------|------|
| T-1 | No constraint vocabulary is vendored anywhere in the repo | API-contract | Phase 1 | safebreach_mcp_studio |
| T-3 | An unrecognised code is still surfaced, without a fabricated explanation | — | Phase 1 | safebreach_mcp_studio |
| T-18 | A sparse constraint map is never iterated as though dense | — | Phase 4 | safebreach_mcp_studio |
| T-19 | Every reason in a multi-reason constraint leaf surfaces, not just the first | API-contract | Phase 4 | safebreach_mcp_studio |
| T-20 | Only a genuine integer zero marks an attack inapplicable — never a null | — | Phase 4 | safebreach_mcp_studio |
| T-21 | Zero-impact simulators come from the union map, so one-sided nodes are not falsely reported | — | Phase 4 | safebreach_mcp_studio |
| T-22 | A limit-reached response suppresses zero-impact reporting entirely | — | Phase 4 | safebreach_mcp_studio |
| T-23 | Conflicts are normalized against a catalog, with nothing static repeated per conflict | API-contract | Phase 4 | safebreach_mcp_studio |
| T-24 | The three tools are registered under their agreed wire names, declared read-only, and the retired one is gone | API-contract | Phase 8 | safebreach_mcp_studio |
| T-25 | None of the three read-only tools takes a rate-limiting gate | — | Phase 8 | safebreach_mcp_studio |
| T-26 | Ambiguous input (more or fewer than one of scenario/scenario_id/test_id) is rejected with a clear error, on all three tools | — | Phase 7 | safebreach_mcp_studio |
| T-34 | The tool catalog documents all three tools, records the retirement, and the gate table is left alone | — | Phase 9 | safebreach_mcp_studio |
| T-41 | Each projection renders only the slice its question needs | API-contract | Phase 7 | safebreach_mcp_studio |
| T-42 | The blocked-entities verdict is decided by whether counts were computed, never by list emptiness | — | Phase 7 | safebreach_mcp_studio |
| T-43 | A named attack id resolves to exactly one of four dispositions | API-contract | Phase 7 | safebreach_mcp_studio |
| T-44 | Filtering to named ids precedes truncation, so a named attack past the cap is still explained | — | Phase 7 | safebreach_mcp_studio |
| T-45 | The blocked-entities catalog carries only the codes its own reported blockers cite | API-contract | Phase 7 | safebreach_mcp_studio |
| T-47 | Each tool's narration carries only its own sections and routes to its siblings | API-contract | Phase 8 | safebreach_mcp_studio |
| T-36 | The same code resolves blocking or reducing depending on the attack's count | — | Phase 4 | safebreach_mcp_studio |
| T-38 | A relayed description reaches the caller byte-for-byte, never re-worded | API-contract | Phase 1 | safebreach_mcp_studio |
| T-39 | A response with no catalog degrades to null descriptions, never an error | API-contract | Phase 1 | safebreach_mcp_studio |

**Integration** — all Automatic

| Test | Description | Aspect | Passes after | Repo | Environment |
|------|-------------|--------|--------------|------|-------------|
| T-6 | An ad-hoc plan body is scored and the response returned unreduced | API-contract | Phase 2 | safebreach_mcp_core | repo-harness |
| T-7 | A scenario_id is passed to the orchestrator for native resolution, never via planId | API-contract | Phase 2 | safebreach_mcp_core | repo-harness |
| T-8 | A step-less plan is rejected before any network call is made | — | Phase 2 | safebreach_mcp_core | repo-harness |
| T-9 | All five query parameters are sent, with the documented defaults and honoured overrides | API-contract | Phase 2 | safebreach_mcp_core | repo-harness |
| T-10 | A limit-reached response is survived, and null is kept distinct from zero | regression | Phase 2 | safebreach_mcp_core | repo-harness |
| T-11 | An API failure surfaces the full response body, not just a status code | — | Phase 2 | safebreach_mcp_core | repo-harness |
| T-12 | Repeated identical calls each hit the API, proving no MCP-side cache | — | Phase 2 | safebreach_mcp_core | repo-harness |
| T-13 | The refactored helper's observable contract is byte-for-byte unchanged | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-14 | The helper still asks for expected counts explicitly, preserving today's numbers | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-15 | The helper no longer crashes on a limit-reached response | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-16 | The statistics endpoint is reached from exactly one place in the repo | regression | Phase 3 | safebreach_mcp_core | repo-harness |
| T-17 | Both existing callers' evaluate previews are unchanged by the refactor | regression | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-27 | Counts mode selects one call or two, and labels what it returns | API-contract | Phase 7 | safebreach_mcp_studio | repo-harness |
| T-46 | Each public function makes exactly one statistics call and passes every parameter through | API-contract | Phase 7 | safebreach_mcp_studio | repo-harness |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-28 | The three tools score an ad-hoc scenario against a real console and return usable numbers | Automatic | API-contract | Phase 8 | safebreach_mcp_studio | Validate console environment |
| T-29 | Scoring by scenario_id agrees with scoring the same scenario's body ad hoc | Automatic | API-contract | Phase 8 | safebreach_mcp_studio | Validate console environment |
| T-30 | Runnable never exceeds expected, and the offline reason explains the gap | Automatic | API-contract | Phase 8 | safebreach_mcp_studio | Validate console environment |
| T-31 | A step-less scenario against a real console yields the typed error on all three tools, not a raw 400 | Automatic | — | Phase 8 | safebreach_mcp_studio | Validate console environment |
| T-40 | A real console supplies the descriptions the relay depends on | Automatic | API-contract | Phase 8 | safebreach_mcp_studio | Validate console environment |
| T-48 | The three tools agree with each other against a real console on a scenario built to block | Automatic | API-contract | Phase 8 | safebreach_mcp_studio | Validate console environment |
| T-32 | An agent answers all three questions through the real product, one tool per question | Manual | progression | Final | — | Validate console environment |
| T-33 | The two shipped run tools still preview correctly against a real console | Manual | regression | Final | — | Validate console environment |
| T-35 | The counts tool's Checkout-parameter numbers match what the console itself displays | Manual | API-contract | Final | — | Validate console environment |

### T-1 — No constraint vocabulary is vendored anywhere in the repo

- Description: Proves MCP owns no constraint vocabulary at all — no meanings and no levers — so the third copy this design deletes cannot reappear.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Leaving any vendored artifact behind recreates the third copy this design deletes and re-opens the possibility of MCP asserting a meaning, or a remedy, it is not the source of. A partial table is the most likely form: "just the misleading ones", kept as a stopgap, which is exactly how `ui-react`'s copy became permanent.
- Risk source: PRD §9 (R3)
- Verify: Assert the module exposes no `CONSTRAINT_REASON_DESCRIPTIONS` and no `CONSTRAINT_FIX_LEVERS` symbol. Then assert no module-level constant maps reason codes to explanatory or remedial text at all: scan the module's own constants for any dict whose keys look like reason codes (`snake_case`, present in a sample response) and whose values carry prose or a lever-like enum.
- Expected: Neither symbol exists, and no substitute mapping is found. The only source of a code's meaning is the response being processed.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-2 — The two codes whose emitted value differs from their source key are keyed by the emitted value

- Description: Would have guarded the one vendoring mistake that passes a naive completeness check while shipping two codes that can never occur and missing the two that do.
- Status: Removed
- Reason for removal: **There is no vendored map to key, and the upstream mismatch no longer exists.** MCP now
  builds `constraint_catalog` from the response it is processing (PRD §3 Component A), so it keys off whatever
  the API actually emitted and cannot enumerate a wrong spelling. Independently, SAF-35568 renamed both
  mismatched keys at source and deleted 5 dead ones, leaving 97 codes whose declared keys are 1:1 with their
  emitted values — so the defect this test policed is fixed in the only repo that could have it. The
  no-vendoring assertion that replaces it lives in the rescoped **T-1**.
- Passes after: Phase 1
- Level: unit
- Execution: Automatic

### T-3 — An unrecognised code is still surfaced, without a fabricated explanation

- Description: Proves an upstream addition after this ticket is still reported as a conflict rather than silently dropped, and that no explanation is invented for it.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: The current lookup returns the code itself on a miss. Silently dropping an unknown code would hide a genuine blocker — exactly what the console does, filtering to `CONSTRAINTS[reason]` at `helpers.tsx:820` and discarding the 31 codes its table lacks. Drift is measured, not hypothetical.
- Risk source: PRD §9 (R3)
- Verify: Process a response carrying a conflict whose code the response's own `constraintCatalog` does not describe — both forms the orchestrator can produce: the code absent from the catalog entirely, and present with an empty entry (`{}`), which is how the orchestrator represents a code it does not itself recognise. Inspect the resolved catalog entry and the conflict list.
- Expected: `description` is explicitly `null` for both forms — not the code, not invented prose — and the conflict is still present in the output, surfaced rather than dropped.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-38 — A relayed description reaches the caller byte-for-byte, never re-worded

- Description: Proves MCP is a conduit and not an author — the property that makes "no vendored vocabulary" true in practice rather than only in the absence of a constant.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A relay that "improves" the text it passes through is a vendored table with extra steps — one that drifts silently, because no coverage test can see a re-worded string as a gap. Trimming, sentence-casing, appending a lever hint, or substituting a nicer phrase for an awkward one all reintroduce MCP as a source of meaning.
- Risk source: PRD §9 (R3)
- Verify: Process a response whose `constraintCatalog` carries deliberately awkward description text — leading and trailing whitespace, an internal double space, a trailing period on one entry and none on another, a non-ASCII character, and a code whose description contradicts what its name suggests. Compare each emitted `constraint_catalog` entry's `description` against the input string with an exact equality assertion.
- Expected: Every description is byte-for-byte identical to the input, including whitespace, punctuation and casing. The contradicting description is relayed as-is, not "corrected" toward the code name. Catalog keys are the API's code strings, unchanged.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-39 — A response with no catalog degrades to null descriptions, never an error

- Description: Proves the tool still works against a console whose orchestrator predates SAF-35568 — the one deployment state where meanings are genuinely unavailable.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Treating the catalog as required — a `KeyError`, or an exception on a missing key — breaks the tool outright on every console that has not taken the orchestrator change, turning a cosmetic gap into an outage. The opposite failure is quieter and worse: dropping the conflicts because they cannot be explained, which hides real blockers.
- Risk source: PRD §9 (R11)
- Verify: Process two responses carrying conflicts but no catalog: one with `constraintCatalog` absent entirely (a pre-SAF-35568 console) and one with it present but empty. Inspect the catalog, every conflict, and `hint_to_agent`.
- Expected: Neither call raises. Every referenced code appears in `constraint_catalog` with `description: null` — the key is present, not omitted — and every conflict is still surfaced with its `severity`, `attack_id`, `side` and `simulator_count` intact. `hint_to_agent` states that no catalog was supplied, so the caller can distinguish "this console is older" from "these conflicts have no meaning". No conflict presents its bare code as an explanation.
- Evidence required: pytest run output naming the test, with the emitted hint text visible.
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

- Description: Would have detected upstream vocabulary drift, the one failure mode a self-contained table cannot see on its own.
- Status: Removed
- Reason for removal: **Nothing is vendored, so nothing can drift.** The catalog is built per response from the
  payload it explains (PRD §3 Component A), which makes it structurally impossible for MCP's vocabulary to be a
  different vintage from the codes it describes — the property this test approximated by reaching into another
  repo's checkout. A code added upstream tomorrow arrives already described, so the failure mode is gone rather
  than merely policed. The cross-repo checkout dependency (and its skip-when-absent hole) goes with it.
- Passes after: Phase 1
- Level: unit
- Execution: Automatic

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
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
- Environment needs: repo-harness

### T-7 — A scenario_id is passed to the orchestrator for native resolution, never via planId

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
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
- Environment needs: repo-harness

### T-8 — A step-less plan is rejected before any network call is made

- Description: Proves a normal mid-construction state produces an explanatory error instead of an opaque upstream rejection, and does so without spending a request.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Risk: the orchestrator answers a step-less plan with an HTTP 400; surfaced raw it reads as a tool failure rather than "add a step", which Helm will hit constantly while building.
- Risk source: PRD §9 (edge cases)
- Verify: With the API mocked, call the fetch core with a plan body whose `steps` is missing, then again with `steps` empty. Assert the mocked transport was never invoked.
- Expected: Both calls raise a typed error whose message names the missing steps; the HTTP mock records zero calls.
- Evidence required: pytest run output naming the test, showing the zero-call assertion.
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
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
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
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
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
- Environment needs: repo-harness

### T-11 — An API failure surfaces the full response body, not just a status code

- Description: Proves a failed scoring call is diagnosable, since the response body is where the orchestrator explains what it rejected.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Risk: A bare status code gives a caller nothing to act on, and the orchestrator signals distinguishable conditions (step-less plan, unsupported filter operator) through the body.
- Risk source: PRD §9 (R4)
- Verify: Mock the API returning a non-2xx status with a JSON body carrying an identifiable error string. Call the fetch core and capture the raised error.
- Expected: The raised error's message contains both the status code and the identifiable string from the body.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
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
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
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
- Automation lives in: planned: `safebreach_mcp_core/tests/test_plan_statistics.py`
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
- Risk: the orchestrator prunes empty constraint leaves and then any simulator with no constraints at all. Treating the map as dense would fabricate entries for simulators that are simply fine.
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

- Description: Proves the plan's central safety property: when the orchestrator did not compute the numbers, the tool says so instead of drawing conclusions from them.
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
- Expected: The catalog holds exactly one entry per distinct code present, and only codes present in this response, each carrying the `description` relayed from the API (or an explicit `null` for the unknown code). Each conflict carries `code`, `severity`, `attack_id`, `side`, `simulator_count` and `values` — and no `description`, which lives only in the catalog. No field anywhere in the payload presents a bare reason code as its explanation.
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

### T-24 — The three tools are registered under their agreed wire names, declared read-only, and the retired one is gone

- Description: Proves the three tools are discoverable under the names every sibling subtask and the agent prompt depend on, that each advertises itself as safe to call repeatedly, and that the tool they replace no longer answers.
- Status: Active
- Passes after: Phase 8
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A wrong name breaks every dependent contract; a missing read-only hint invites a calling model to treat re-checks as risky and avoid them.
- Risk source: PRD §9 (assumptions)
- Verify: Introspect the studio server's registered tools.
- Expected: Tools named exactly `get_scenario_simulation_counts`, `get_scenario_blocked_entities` and `get_scenario_attack_blockers` exist, each with the read-only hint true and the destructive hint false. No tool named `get_plan_statistics` remains. Every other previously registered tool is still present, and the server's total tool count reflects three added and one removed. Each tool's parameter set names the ad-hoc scenario body `scenario`, not `plan`.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-25 — None of the three read-only tools takes a rate-limiting gate

- Description: Proves the project's rate-limiting contract is respected across all three — gates belong to mutating tools, and gating a read-only impact check would throttle exactly the re-checks the feature exists to enable. Three tools mean three chances to get this wrong.
- Status: Active
- Passes after: Phase 8
- Level: unit
- Execution: Automatic
- Risk: Copying an existing studio tool as a template would bring its rate-limiting gates along, silently capping how often a configuration can be re-scored.
- Risk source: PRD §9 (R5)
- Verify: With rate limiting enabled and the API mocked, invoke each of the three tools more times than the configured per-tool limit, and more times in total than the configured per-caller limit, while observing the limiter.
- Expected: Every invocation of every tool succeeds. Neither the pre-check nor the record-action entry point is called for any of the three, individually or in aggregate.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_rate_limiting.py`
- Environment needs: none

### T-26 — Ambiguous input (more or fewer than one of scenario/scenario_id/test_id) is rejected with a clear error, on all three tools

- Description: Proves the three input modes are genuinely exclusive on every tool, so a caller never gets a silently-ignored argument and a number that answers a different question.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Risk: Silently preferring one input over the other would score a different configuration than the caller asked about, and the result would look entirely plausible.
- Risk source: PRD §9 (assumptions)
- Verify: For each of the three public functions in turn, invoke it with both a scenario body and a scenario id, then with neither, then with a scenario argument that is not valid JSON, then with a blank string in place of an unused optional.
- Expected: Every case raises an error whose message states which inputs are expected and that exactly one must be supplied. A blank string counts as absent rather than as a supplied value, so it neither satisfies the exclusivity check nor reaches the API. No API call is attempted in any case, on any of the three.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-27 — Counts mode selects one call or two, and labels what it returns

- Description: Proves the expected-versus-runnable contract on the tool that reports the numbers, including that the cheaper single-call default is what a caller gets unless they ask for both.
- Status: Active
- Passes after: Phase 7
- Level: integration
- Execution: Automatic
- Aspect: API-contract
- Risk: The two figures cannot come from one call and cannot be derived from each other. An unlabelled or wrongly-defaulted result is indistinguishable from a correct one at a glance.
- Risk source: PRD §9 (R4, R5)
- Verify: With the API mocked and call-counting enabled, invoke `get_scenario_simulation_counts` three ways: default, expected-only, and both. Inspect the request count, each request's `includeDisabled` value, and the returned labels.
- Expected: Default issues one call with `includeDisabled=false` and labels the result runnable. Expected-only issues one call with `includeDisabled=true` and labels it expected. Both issues exactly two calls, one of each, and returns both results labelled, together with the note that expected cannot be derived from runnable.
- Evidence required: pytest run output naming the test, with the per-mode call counts visible.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-28 — The three tools score an ad-hoc scenario against a real console and return usable numbers

- Description: Proves the whole path works against the real the orchestrator service, which is the only way to know the request shape and response parsing are actually right — now across all three tools, since each renders a different part of that parse.
- Status: Active
- Passes after: Phase 8
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: Every mocked test encodes an assumption about the real endpoint. The maps are untyped at the source, so only a live call confirms the shape.
- Risk source: PRD §9 (assumptions)
- Verify: Against the configured e2e console, build a scenario body from a step of an existing scenario read through the product's own scenario API, then call each of the three tools with default parameters.
- Expected: The counts tool returns a per-step simulation count that is an integer and a total consistent with it. The blocked-entities tool returns a verdict in one of its three states plus, where applicable, entries carrying blockers that reference a catalog entry. The blockers tool, asked about an id present in the scenario, returns exactly one disposition for it. No tool's output contains a bare reason code as its explanation.
- Evidence required: pytest e2e run output naming the test, plus the console name and the returned counts.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-29 — Scoring by scenario_id agrees with scoring the same scenario's body ad hoc

- Description: Proves the two input modes are two routes to one answer, which is what makes the saved-scenario passthrough trustworthy.
- Status: Active
- Passes after: Phase 8
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: The by-id path is resolved server-side from a code path this repo does not control. If it diverged from the ad-hoc path, callers would silently get different numbers for the same scenario.
- Risk source: PRD §9 (assumptions)
- Verify: Against the e2e console, pick an existing scenario or custom plan through the product's own listing APIs. Call `get_scenario_simulation_counts` once with its id, and once with its steps as an ad-hoc `scenario` body, using identical parameters.
- Expected: Both calls return the same number of steps and the same per-step `simulationCount`. If the target is a custom plan, the integer-as-string id is accepted as readily as a scenario UUID.
- Evidence required: pytest e2e run output naming the test, with both count sequences shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-30 — Runnable never exceeds expected, and the offline reason explains the gap

- Description: Proves the feature's most user-visible correction against the live service — that a disconnected simulator is no longer counted as if it would run, and that the tools can say why.
- Status: Active
- Passes after: Phase 8
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: The parameter's behaviour is the inverse of its intuitive reading, and it was read from source rather than observed. If that reading is wrong, the default asks for the wrong number.
- Risk source: PRD §9 (R4)
- Verify: Against the e2e console, score the same scenario twice through `get_scenario_simulation_counts` — runnable then expected — and compare. Then inspect `get_scenario_blocked_entities`' runnable output for the offline reason. When the console has no disabled or unapproved simulator, skip the delta and offline-reason assertions with an explicit reason naming that precondition, and still assert the ordering relation.
- Expected: Runnable `simulationCount` is less than or equal to expected for every step. When a disabled simulator exists, the runnable response reports the offline reason for it and the expected response does not, and the delta is strictly positive for at least one step. A skipped assertion is reported as a skip with its reason, never as a pass.
- Evidence required: pytest e2e run output naming the test, with both count sequences, the disabled-simulator precondition status, and any skip reason.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-31 — A step-less scenario against a real console yields the typed error on all three tools, not a raw 400

- Description: Confirms against the live service that the most common mid-construction state reads as guidance rather than as a tool failure — from whichever of the three tools the caller happened to reach for.
- Status: Active
- Passes after: Phase 8
- Level: e2e
- Execution: Automatic
- Risk: The pre-flight rejection is asserted against a mock in T-8. Only a live call confirms the real endpoint still behaves as the pre-flight assumes, and that no other path reaches it.
- Risk source: PRD §9 (edge cases)
- Verify: Against the e2e console, call each of the three tools with a `scenario` body carrying no steps.
- Expected: Each returns a typed error naming the missing steps, matching T-8's message — the rejection lives in the shared plumbing, so all three messages are identical. No unhandled HTTP error and no raw upstream error code surface to the caller from any of them.
- Evidence required: pytest e2e run output naming the test, with the error message shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-40 — A real console supplies the descriptions the relay depends on

- Description: Proves the relay works against the live API rather than against a mock of it — the one assumption every unit test in Phase 1 encodes and none can falsify. Re-aimed at the blocked-entities tool, which is now the only one that renders a catalog.
- Status: Active
- Passes after: Phase 8
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: Every Phase 1 test asserts MCP's behaviour given a catalog. Whether a catalog actually arrives — under this tool's own parameter set, at the response root rather than per step, keyed the way MCP looks codes up — is an assumption about another team's deployed service. If it is wrong, the whole design silently reports `description: null` for everything while every unit test stays green.
- Risk source: PRD §9 (R9, R11)
- Verify: Against the configured e2e console, call `get_scenario_blocked_entities` with default parameters on a scenario whose steps are known to produce conflicts, and read the returned constraint catalog. First establish whether that console carries SAF-35568 — a catalog present with at least one non-null description. If it does not, skip with an explicit reason naming the console and the absent field, and assert the R11 degradation instead (conflicts surfaced, descriptions null, hint present).
- Expected: On a SAF-35568 console: every code referenced by a reported blocker has a catalog entry, each `description` a non-empty string, and no entry is the code name echoed back. The catalog contains only codes this tool's own reported blockers cite — not the full vocabulary, and not codes reachable only through the conflicts this tool drops (T-45 asserts that narrowing against a fixture; this asserts it against live data). On an older console: the test skips with a stated reason, and the degradation assertion passes. A skip is never reported as a pass.
- Evidence required: pytest e2e run output naming the test, the console name, and the returned catalog with its descriptions — or the explicit skip reason and the degradation assertion's output.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment

### T-32 — An agent answers all three questions through the real product, one tool per question

- Description: The progression walkthrough — proves the decomposition delivers its actual purpose as a conversational capability, which no assertion on a payload can establish: that each question is answered by one call to one tool, and that the agent picks the right one unprompted.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: Every criterion can pass while the tools remain unusable in conversation — if a response is too large to reason over, if its wording does not let an agent explain a conflict to a user, or if the agent cannot tell which of three similar tools answers the question it was asked. The last of those is a failure the single tool could not have had.
- Risk source: PRD §9 (R3, R13, assumptions)
- Verify: Through an MCP client connected to the e2e console, take an existing scenario and ask the agent, in three separate turns and without naming any tool: how many simulations this would produce; whether anything here will not run at all; and why one specific attack did not run. Record which tool it reaches for each time. Then change one step's filter and repeat the count question to confirm the answer changes. Preconditions come from existing console scenarios read through the product's own APIs — no seeding.
- Expected: Each question is answered from one call to the tool that owns it — counts, blocked-entities, blockers respectively — with no wrong-tool detour and no second call to recover a missing figure. Each answer is correct and in plain language. No raw reason code appears in anything shown to the user. The repeated count question reflects the changed filter, demonstrating freshness. If a tool cannot be reached or a response cannot be interpreted, the test reports BLOCKED.
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

### T-34 — The tool catalog documents all three tools, records the retirement, and the gate table is left alone

- Description: Proves the documentation requirement is met in the precise way the project's own conventions demand, including the deliberate omission — and that a reader looking for the retired tool is redirected rather than left to wonder.
- Status: Active
- Passes after: Phase 9
- Level: unit
- Execution: Automatic
- Risk: The project treats its tool catalog as the tool contract. An undocumented tool is invisible to future contributors, and wrongly adding it to the rate-limiting table would contradict the stated gate rule.
- Risk source: PRD §9 (assumptions)
- Verify: Read the project instruction file. Assert the Studio Server tool catalog contains an entry for each of the three tools, that it records `get_plan_statistics` as retired and names its three replacements, and that the rate-limiting gate table's row set is unchanged.
- Expected: Three catalog entries are present, each naming the question its tool answers, the runnable default and the read-only posture, and the counts entry naming its `get_constraints=False` default. The catalog states the retirement and the replacements, so the redirect is in the document rather than only in the change log. Every entry uses `scenario` rather than `plan` for the caller-facing vocabulary. The gate table contains no row for any of the three.
- Evidence required: pytest run output naming the test.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-35 — The counts tool's Checkout-parameter numbers match what the console itself displays

- Description: The independent cross-layer check — proves the tool agrees with what a user actually sees in the product, which is the requirement's own wording and cannot be shown by comparing the tool to itself. Re-aimed at `get_scenario_simulation_counts`, which is now the tool that reports the numbers being compared; **AC-4 remains unchecked until this runs** — the decomposition does not discharge it.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: API-contract
- Risk: Every other parity test compares the tool against the same API it calls. Only reading the rendered console view falsifies the claim that the numbers match the product, and the two views legitimately differ by parameter set.
- Risk source: PRD §9 (R4)
- Verify: For one scenario on the e2e console, open the Add Simulators Checkout view and record the displayed simulation count. Call `get_scenario_simulation_counts` for the same scenario with the Checkout parameter set (expected counts, constraints requested) and compare. Repeat the comparison against the run-gating view using the runnable parameter set.
- Expected: The tool's count equals the Checkout view's displayed count for the Checkout parameter set, and equals the run-gating view's for the runnable parameter set. Where a view greys out Run because a step yields nothing, the tool reports that step's count as zero.
- Evidence required: screenshots of both console views, the tool responses for both parameter sets, and an observed-versus-expected comparison per view.
- Manual because: the comparison target is a rendered console view and this repo has no browser automation of any kind (Python only); the automation repo's Playwright suites are the org's only browser infra, and standing up a cross-repo suite for a single parity check is disproportionate to the risk.
- Environment needs: Validate console environment

### T-41 — Each projection renders only the slice its question needs

- Description: Proves the decomposition is real rather than cosmetic — each tool's answer is genuinely narrowed, so a caller asking one question does not pay for the other two.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Three tools that each return the whole report would satisfy every naming and registration assertion while delivering none of the benefit the split exists for, and nothing else in the plan would catch it.
- Risk source: PRD §9 (R13)
- Verify: Apply each of the three projections to one report carrying per-step counts, both zero-impact lists, a conflicts list and a constraint catalog. Inspect what each returns.
- Expected: The counts projection carries the mode, the step counts, the coverage denominators and the truncation facts, and carries no conflicts, no zero-impact list and no catalog. The blocked-entities projection carries both zero-impact lists and a catalog, and carries no conflicts list. The attack-blockers projection carries entries only for attacks it was asked about. None of the three mutates the report it was given.
- Evidence required: pytest run output naming the test, with each projection's returned key set shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-42 — The blocked-entities verdict is decided by whether counts were computed, never by list emptiness

- Description: Proves the feature's most dangerous confusion is impossible on the one tool whose entire subject is emptiness — a scenario nobody scored must never read as a scenario with nothing wrong.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Risk: A limit-reached report and a clean report both carry two empty zero-impact lists. A verdict derived from those lists would report "nothing is blocked" over a plan the orchestrator never evaluated, which is the exact inversion PRD §9 R1 exists to prevent, now on a tool whose whole output is that sentence.
- Risk source: PRD §9 (R1)
- Verify: Project three reports — one carrying a zero-impact attack, one where every count is a positive integer and both lists are empty, one limit-reached where counts were not computed and both lists are empty by construction. Then take the second report and flip only its counts-computed flag.
- Expected: Three textually distinct verdicts. The first names what contributes nothing. The second states every attack and simulator contributes at least one simulation. The third states that scoring stopped early and that nothing in the result indicates anything is inapplicable. Flipping only the counts-computed flag changes the second verdict into the third, proving the verdict is derived from that flag and not from the empty lists.
- Evidence required: pytest run output naming the test, with all three verdict strings shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-43 — A named attack id resolves to exactly one of four dispositions

- Description: Proves the tool never answers "why didn't this run" with silence, which a caller cannot distinguish from any of the three non-constraint reasons an attack produced nothing.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Reporting only blocked attacks makes an id that ran, an id nobody scored, and an id that is not in the scenario all appear identically — as absence. Two of those three are not constraint problems at all, so the caller would go looking for a conflict that does not exist.
- Risk source: PRD §9 (R13)
- Verify: Project a report whose attack counts hold an integer zero, a positive integer and a null, then ask about those three ids plus one appearing in no step. Then project the same report asking about nothing at all.
- Expected: The zero id is reported blocked and carries its blockers. The positive id is reported as having run, with its count. The null id is reported as not computed. The absent id is reported as not present in this scenario. Each id receives exactly one disposition and the four are textually distinct. Asked about nothing, the projection reports every fully-blocked attack and emits no disposition entries at all.
- Evidence required: pytest run output naming the test, with the four dispositions shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-44 — Filtering to named ids precedes truncation, so a named attack past the cap is still explained

- Description: Proves the tool cannot fail at exactly the moment it is needed — on a large scenario, where the attack the caller asked about is the one most likely to fall off a capped list.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Risk: The zero-impact list is capped without regard to which attack the caller cared about. Reading dispositions from that capped list would report a genuinely blocked attack as not present in the scenario — a confident wrong answer, and the opposite of the truth.
- Risk source: PRD §9 (R13)
- Verify: Project a report whose zero-impact list was capped, holding more blocked attacks than the cap admits, and ask specifically about one whose integer-zero count is present in the counts map but whose zero-impact entry falls beyond the cap. Then repeat with an id the counts map itself was capped past.
- Expected: The first named attack is reported blocked, not absent. The second is reported as having been truncated away rather than as not present in the scenario — the two answers stay distinct and neither collapses into the other.
- Evidence required: pytest run output naming the test, with the cap size and both dispositions shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-45 — The blocked-entities catalog carries only the codes its own reported blockers cite

- Description: Proves the narrowed tool narrows its catalog too, so the answer to a short question does not carry a vocabulary list explaining conflicts it deliberately did not report.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Relaying the whole report's catalog would describe codes reachable only through the reducing conflicts this projection drops, inviting a caller to present a meaning for something the tool never showed them.
- Risk source: PRD §9 (R13)
- Verify: Project a report whose catalog describes more codes than the reported blockers reference, including one cited only by a reducing conflict the projection drops.
- Expected: Every code in the returned catalog is cited by at least one reported blocker, and every code a reported blocker cites has an entry. The code reachable only through a dropped conflict does not appear. Each description is byte-for-byte what the report carried, and a code the report described as null is still emitted with an explicit null.
- Evidence required: pytest run output naming the test, with both code sets shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-46 — Each public function makes exactly one statistics call and passes every parameter through

- Description: Proves the three tools are three views of one scoring, not three scorings — which is what makes their answers comparable and what keeps the single-call-site guarantee true.
- Status: Active
- Passes after: Phase 7
- Level: integration
- Execution: Automatic
- Aspect: API-contract
- Risk: A projection that re-fetched to fill a gap would triple the cost of a three-question conversation, break the one-call-site requirement this PRD already satisfies, and could return three answers computed from three different console states.
- Risk source: PRD §9 (R2, R5)
- Verify: With the statistics call mocked and counted, invoke each of the three public functions with every parameter explicitly set to a non-default value, then invoke each again with defaults.
- Expected: Each invocation produces exactly one statistics call. Every explicitly-set parameter reaches it unchanged. On defaults, the counts function requests no constraints while the other two do, and all three request runnable counts. No function issues a second fetch under any input.
- Evidence required: pytest run output naming the test, with the per-function call counts and the sent parameter sets shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-47 — Each tool's narration carries only its own sections and routes to its siblings

- Description: Proves the split solved a problem rather than trading it for a worse one — three tools are only an improvement if a reading model can tell which to call.
- Status: Active
- Passes after: Phase 8
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Decomposition replaces a mining problem with a selection problem. A model asked for a count that reaches the blocked-entities tool gets a verdict and no number, then either answers wrongly or burns a second call — and nothing in a payload assertion would reveal it.
- Risk source: PRD §9 (R13)
- Verify: Render each tool's output from one report and read its section headings and its hint text. Read each tool's registered description.
- Expected: The counts output carries no conflict, zero-impact or catalog section. The blocked-entities output carries no per-step simulation-count listing beyond its coverage denominators, and no conflicts section. The attack-blockers output names only the attacks asked about. Each output's hint names the sibling that answers the question it does not — the counts output points at blocked-entities for why a step produces nothing, and the attack-blockers output states that attacks which ran on fewer simulators than offered are outside its scope. Each registered description opens by naming the single question its tool answers.
- Evidence required: pytest run output naming the test, with each rendered output and each description's opening shown.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: none

### T-48 — The three tools agree with each other against a real console on a scenario built to block

- Description: Proves the decomposition preserves one truth — three tools reading one scoring must not disagree — on input engineered to make a block certain rather than found by luck.
- Status: Active
- Passes after: Phase 8
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: Each tool is asserted against mocks in isolation. Nothing yet proves that against a live console the counts tool's totals, the blocked-entities tool's denominators and the blockers tool's dispositions describe the same scoring — three plausible answers that quietly contradict each other is the failure mode a split invites and a single tool could not have.
- Risk source: PRD §9 (R13, assumptions)
- Verify: Against the e2e console, read the simulator fleet and the playbook through the product's own APIs and construct an ad-hoc scenario body pairing an OS-constrained attack with target simulators of a different OS, so at least one attack is blocked by construction rather than by chance. Score that body through all three tools with identical parameters. Then ask the blockers tool specifically about the attack expected to be blocked and about one expected to run. If the fleet carries a single OS throughout, fall back to a role mismatch (an attack requiring an infiltration-capable attacker against a filter that admits none); only if neither mismatch is constructible does the test skip, stating the fleet composition.
- Expected: The counts tool's per-step totals are consistent with the blocked-entities tool's coverage denominators for the same steps. The blocked-entities tool reports at least one attack contributing nothing and names it. The blockers tool reports that same attack as blocked, with at least one constraint carrying a non-null description, and reports the other attack as having run with its count. No tool presents a bare reason code as an explanation. A skip is reported as a skip with the fleet composition, never as a pass.
- Evidence required: pytest e2e run output naming the test, the console name, the constructed scenario body, all three tool responses, and the cross-tool comparison — or the explicit skip reason with the fleet composition.
- Automation lives in: planned: `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`
- Environment needs: Validate console environment


## Tests by Phase (readiness view — generated)

Cumulative: at the end of phase N, EVERY test with "Passes after" <= N must be green.

| After phase | Newly green | Cumulative green |
|-------------|-------------|------------------|
| Phase 1 | T-1, T-3, T-38, T-39 | 4 |
| Phase 2 | T-6, T-7, T-8, T-9, T-10, T-11, T-12 | 11 |
| Phase 3 | T-13, T-14, T-15, T-16, T-17 | 16 |
| Phase 4 | T-18, T-19, T-20, T-21, T-22, T-23, T-36 | 23 |
| Phase 5 | — (T-24, T-25, T-26, T-27, T-28, T-29, T-30, T-31 and T-40 re-scoped by PRD v7 and re-phased to 7/8) | 23 |
| Phase 6 | — (T-34 re-scoped by PRD v7 and re-phased to 9) | 23 |
| Phase 7 | T-26, T-27, T-41, T-42, T-43, T-44, T-45, T-46 | 31 |
| Phase 8 | T-24, T-25, T-28, T-29, T-30, T-31, T-40, T-47, T-48 | 40 |
| Phase 9 | T-34 | 41 |
| Final | T-32, T-33, T-35 | all (44) |

## Sign-off

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [ ] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — >=1 Manual regression test (T-33) + post-ship CI named (with the no-test-CI gap recorded)
- [ ] Progression evidence — >=1 Manual progression test walking the new feature (T-32, re-scoped to the three-question walkthrough)
- [ ] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Final) — evidence: test-results/<phase-or-date>.md
- [ ] Accepted gaps listed and approved: none

## Change Log

| Date | Change |
|------|--------|
| 2026-09-02 | Updated for **PRD v7** — the single `get_plan_statistics` tool is decomposed into three question-shaped tools (`get_scenario_simulation_counts`, `get_scenario_blocked_entities`, `get_scenario_attack_blockers`) and its registration retired, appended as PRD phases 7-9. **Eight tests added**: T-41 (each projection renders only its own slice), T-42 (the blocked-entities verdict is decided by the counts-computed flag, never by list emptiness — R1 on the one tool whose whole subject is emptiness), T-43 (a named id resolves to exactly one of four dispositions, and asking about nothing emits none), T-44 (filtering precedes the zero-impact cap, so a named attack past #50 is still explained rather than reported absent), T-45 (the narrowed tool narrows its catalog too), T-46 (each public function makes exactly one statistics call with every parameter passed through — the single-call-site guarantee, now across three tools), T-47 (each narration carries only its own sections and routes to its siblings — the guard on the *selection* problem a split introduces), T-48 (e2e: the three tools agree against a real console on a scenario **built to block**, per the authoring gate — an OS mismatch constructed from the live fleet, with a role mismatch as fallback, so the assertion is not left to luck). **Twelve tests re-scoped, none tombstoned**: T-24/T-25/T-26 to the three tools and the `scenario` vocabulary, T-27/T-29/T-30/T-35 to the counts tool, T-28/T-31 across all three, T-40 to the blocked-entities tool (now the only one rendering a catalog), T-32 to the three-question walkthrough — which is why **no new Manual progression test was added**, and T-34 to three catalog entries plus the retirement redirect. **Nine tests re-phased out of completed phases 5 and 6** into 7-9, because their assertions changed rather than their subject: the plan now shows those phases adding nothing new, which is honest rather than a regression. **T-33 is untouched** — the shipped run tools and `sb_get_plan_statistics` are genuinely unchanged, which is exactly what it asserts, so the regression set needs nothing added. R12 re-scoped; R14-R17 added for the projection contract, the pass-through surface, the disposition/verdict rules and the scenario vocabulary. PRD §9's new R12/R13/R14 folded into the Risk Landscape. Regenerated views: 44 Active (21 unit / 14 integration / 9 e2e), phases 4/11/16/23/23/23/31/40/41/44. Status stays Draft — material change. In Sync with PRD v7. |
| 2026-08-27 15:40 | Fetch core relocated to `safebreach_mcp_core` per user decision — `plan/statistics` is a general orchestrator API with further clients expected, so it ships as a shared primitive (`safebreach_mcp_core/plan_statistics.py`, public `fetch_plan_statistics`) rather than a studio-private helper, mirroring `core/queue_state.py`. Retargeted the eight tests that exercise the fetch core itself — T-6, T-7, T-8, T-9, T-10, T-11, T-12 and T-16 (the single-call-site scan) — to `safebreach_mcp_core/tests/test_plan_statistics.py`, and updated their Repo column. T-13/T-14/T-15/T-17 stay in the studio suite: they assert the summariser's own contract. Added a Change Coverage row for the new core module. No test was added, removed or re-phased and no assertion changed — placement only. |
| 2026-08-27 14:57 | Corrected for PRD v5 — MCP vendors **no** constraint vocabulary and relays the orchestrator's `constraintCatalog` instead, after [SAF-35568](https://bitbucket.org/safebreach/orchestrator/pull-requests/2299) shipped `{ description }` only (its `fixLever` was implemented then removed as redundant) over 97 codes with keys 1:1 with emitted values. **T-2 tombstoned** (Status: Removed, ID retained) — there is no vendored map to key, and the upstream key/value mismatch it policed was fixed at source. **T-5 tombstoned** — nothing is vendored, so nothing can drift; the cross-repo checkout dependency goes with it. T-1 rescoped from "every code has a valid fix lever" to "no constraint vocabulary is vendored anywhere", including a scan for substitute mappings; T-3 rescoped to both forms of an undescribed code (absent entry and empty `{}`); T-23's catalog assertion moved from `fix_lever` to a relayed `description`. **Added T-38** (descriptions relayed byte-for-byte, never re-worded), **T-39** (absent/empty catalog degrades to `description: null` with conflicts intact and a hint, per new R11) and **T-40** (e2e — a real console actually supplies the descriptions the relay depends on, skipping with a stated reason on a pre-SAF-35568 console). Also fixed stale v1 wording in T-28's Expected, which still demanded a "suggested fix" dropped back in v2. R7 restated to the relay contract, R8 to conditional-null; R3/R6/R10 closed, R7/R9 dropped to Low, R11 added. Regenerated views: 36 Active (15 unit / 13 integration / 8 e2e), phases 4/11/16/23/32/33/36. Status stays Draft — material change. In Sync with PRD v5. |
| 2026-08-26 12:04 | Test plan created from PRD v1 |
| 2026-08-26 16:35 | Fixed the Regression section's test list: dropped tombstoned T-4 and added T-2 and T-10, which carry `Aspect: regression` but were never listed. The list is now the complete regression set. |
| 2026-08-26 16:20 | Corrected for PRD v4 — the vendored translation table is **deleted**, not extended. **T-4 tombstoned** (Status: Removed, ID retained): its premise was preserving the 14 existing descriptions, which are now deliberately removed (PRD R9). T-1 rescoped to assert `CONSTRAINT_REASON_DESCRIPTIONS` no longer exists and that all 88 codes carry a valid-or-null lever with no meaning-bearing field; T-3 and T-23 assert an explicit `description: null` rather than a fabricated or bare-code explanation. R7 narrowed from descriptions to levers; R3 dropped to Low; R9/R10 added for the accepted regression and the SAF-35568 dependency. Regenerated views: 35 Active (15 unit / 13 integration / 7 e2e), phases 4/11/16/23/31/32/35. In Sync with PRD v4. |
| 2026-08-26 15:40 | Corrected for PRD v3 and aligned to SAF-35568. Verified at the emit sites that all 88 codes eliminate the node — the `informational` class does not exist, so **T-37 is tombstoned** (Status: Removed, ID retained) and `kind` is gone from T-1/T-3/T-36. T-1 now asserts a description plus a valid fix lever for all 88; T-3 asserts an unknown code is surfaced rather than dropped; T-4 covers all 14 legacy descriptions. R7 rewritten to "descriptions from names, not emit sites". Fixed the non-existent `safebreach-mcp/` path prefix on all automation locations. Regenerated views: 36 Active (16 unit / 13 integration / 7 e2e), phases 5/12/17/24/32/33/36. In Sync with PRD v3. |
| 2026-08-26 13:20 | Updated for the PRD v2 design revision (MCP is structured, Helm narrates). Rescoped T-1 (classification on two closed enums, no `suggested_fix`), T-3 (fail-safe to `elimination`, not a generic description), T-4 (retained-vs-dropped descriptions), T-23 (catalog normalization rather than per-conflict translation). Added T-36 (computed severity — same code blocking and reducing in one step) and T-37 (the 16 informational codes never block). Regenerated the unit index, Coverage Summary (17/13/0/7 = 37) and Tests by Phase; extended R7/R8/R9 traceability and Change Coverage. Status stays Draft — material change. In Sync with PRD v2. |
