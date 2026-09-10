# Test Results — Phase 2 (SAF-35508)
> Plan: ../test-plan.md | Run: 2026-08-27 | Mode: run

Phase 2 — Raw fetch core (`safebreach_mcp_core/plan_statistics.py`).

## Preflight (Step 0)

| Check | Result |
|-------|--------|
| Dispatch mode | source-repo **uv-pytest** — see Smell observations #1, the plan says `repo-harness` |
| `uv` toolchain | ✓ present — `uv 0.9.25` |
| Interpreter pin | ✓ `--python 3.12` mandatory |
| Bootstrap | ✓ `uv sync` satisfied from `uv.lock` |
| Environment reachability | ✓ n/a in practice — every Verify mocks the transport; no console, AWS/SSM or VPN touched |
| Sub-runners | n/a — none dispatched (see #1) |
| Unwritten tests | ✗ **stale marker** — T-6…T-12 are `Automation lives in: planned:` but were authored this session (`39f1fd1`) |

## Accounting

| T-\<n\> | Level | Execution | Env (plan) | Runner (actual) | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|-------------------|---------|-------------------|
| T-1 | unit | Automatic | none | source-repo uv-pytest | executed | cumulative re-run — 4/4 PASSED, no regression |
| T-3 | unit | Automatic | none | source-repo uv-pytest | executed | cumulative re-run — 5/5 PASSED |
| T-38 | unit | Automatic | none | source-repo uv-pytest | executed | cumulative re-run — 6/6 PASSED |
| T-39 | unit | Automatic | none | source-repo uv-pytest | executed | cumulative re-run — 5/5 PASSED (hint case removed, see phase-1.md) |
| T-6 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 8/8 PASSED — `TestAdHocPlanBodyIsScoredUnreduced` |
| T-7 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 4/4 PASSED — `TestScenarioIdIsPassedForNativeResolution` |
| T-8 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 3/3 PASSED — `TestStepLessPlanRejectedBeforeAnyCall` |
| T-9 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 4/4 PASSED — `TestAllFiveQueryParametersArePassedThrough` |
| T-10 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 8/8 PASSED — `TestLimitReachedResponseKeepsNullDistinctFromZero` |
| T-11 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 5/5 PASSED — `TestApiFailureSurfacesTheFullResponseBody` |
| T-12 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 2/2 PASSED — `TestNoMcpSideCaching` |

Ledgered = 11. Selected = 11. No test dropped.

## Cumulative readiness

- Selected (Passes after ≤ 2, Active): T-1, T-3, T-38, T-39, T-6, T-7, T-8, T-9, T-10, T-11, T-12
- Green: all 11 · BLOCKED: none · Unwritten-planned: none · Delegated: none
- Phase verdict: **PASS**

## Evidence

```
uv run --python 3.12 pytest safebreach_mcp_core/tests/test_plan_statistics.py -v
→ 36 passed in 0.11s
```

Full repo suite, same state: **1604 passed, 137 deselected, 0 failed** across
`safebreach_mcp_config` + `_data` + `_utilities` + `_playbook` + `_studio` + `_core`, `-m "not e2e"`.

- **T-6**: executed — posted body carries the supplied steps and no `id`; `name` defaults to `""` when
  absent and is used as-is when given; all seven response fields per step returned unmodified; the union
  `simulators` map and the sparse `simulatorConstraints` survive intact; two steps returned in response
  order. Plus the two `constraint_catalog` cases (see Smell #2).
- **T-7**: executed — body carries `id` + `name`; `planId` asserted absent; `requests.get`
  `assert_not_called()` with `post.call_count == 1` proving no client-side lookup; the `scenario_id` path
  is not subject to the step-less guard and reports `plan_step_count: None`.
- **T-8**: executed — both a missing `steps` key and an empty `steps` list raise before any request, each
  with `mock_post.assert_not_called()` as the zero-call evidence; the message names `steps` and explains
  the expected `400 NOT_ALLOWED`.
- **T-9**: executed — the default call sends `limit=500000`, `includeDisabled=false`,
  `getConstraints=true`, `getAllConstraints=true`, `useCache=true`, parsed out of the real request URL;
  every parameter honours an override; no parameter drops when only one is overridden; `params_used`
  reports the effective set.
- **T-10**: executed — a limit-reached response does not raise; `simulationCount: null` is not defaulted
  to `0` and is asserted `!= 0`; `counts_computed` is `False` for null and **`True` for an integer `0`**
  (the null-vs-zero distinction, from both directions); every null `moves` value stays null; plan step
  count 3 / returned 1 / `truncated: True`; an untruncated response is not flagged.
- **T-11**: executed — the raised error carries both the status code and the identifiable body string,
  and is a `ValueError` whose message contains `"Statistics API error"` (the text studio's shipped e2e
  asserts on at `test_e2e_run_scenario.py:344`, which Phase 3 inherits).
- **T-12**: executed — two identical calls produce `mock_post.call_count == 2`; a module-global scan
  finds no cache object.

## Hand-off (delegated / BLOCKED)

None.

## To author (unwritten-planned)

None. T-6…T-12 authored in `39f1fd1`, despite the plan still marking them `planned:`.

## Manual substitutions (not the planned test)

None.

## Smell observations

1. **`Environment needs: repo-harness` is wrong for all seven of T-6…T-12.** Every one of their `Verify`
   steps says "with the API mocked"; every `Expected` is an assertion over a mocked `requests.post`
   (posted body, query string, call count, raised error). None touches Postgres, Vault, Elasticsearch, a
   console, or docker-compose — and this repo has no `test-integ` suite at all. Dispatching them per the
   plan would provision a disposable EC2 host to run 36 in-process mock tests. Run as source-repo
   uv-pytest instead; correct value is `Environment needs: none`. **Second-order runner gap:** the
   `running-phase-tests` uv-pytest dispatch row is scoped to `unit`/`component` and does not list
   `integration`, so even a corrected plan needs that row widened. `integration` is the honest level here —
   these exercise the module's full request/response path — so re-levelling to `unit` is not the fix.
2. **No `T-<n>` covers `constraint_catalog` surviving the fetch core.** Phase 1's relay is only reachable
   through this layer once Phase 3 routes through it, and PRD §8 Phase 2's Outputs list omits the catalog
   while T-6's title says the response is returned "unreduced". Two cases were written
   (`test_response_root_constraint_catalog_is_relayed_verbatim`,
   `test_absent_catalog_is_none_and_empty_catalog_is_empty_dict`) because an untested passthrough here
   would silently regress Phase 1 at Phase 3. They answer to no plan item — back-fill via
   `authoring-test-plan`.
3. **Two `Raises` paths had no plan coverage** — mutual exclusion of `plan`/`scenario_id`, and the
   403 → `PermissionError` passthrough that the deliberately narrow `except HTTPError` exists to protect.
   Both written as implementing cases; neither has a `T-<n>`.
4. **AC-6 is intentionally unsatisfied until Phase 3.** Two `plan/statistics` call sites exist between
   Phase 2 and Phase 3 — the new core and the untouched `_get_scenario_statistics`. T-16 is correctly
   `Passes after: Phase 3`; it must not be written early and reported as a false failure. Note the old
   helper still carries the live `TypeError` (`sum(1 for v in ... if v > 0)` on a limit-reached
   response's `None` values) that this module was written to fix — it stays live until Phase 3 lands.

## Verdict

- **PASS** — every cumulative test for Phase 2 green with the pytest output its `Evidence required`
  demands. No BLOCKED, no unwritten-planned, no manual substitution.
