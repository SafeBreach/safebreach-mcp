# Test Results — Phase 3 (SAF-35508)
> Plan: ../test-plan.md | Run: 2026-08-27 | Mode: run

Phase 3 — Refactor the summariser onto the core.

## Preflight (Step 0)

| Check | Result |
|-------|--------|
| Dispatch mode | source-repo **uv-pytest** — plan says `repo-harness` for T-13…T-17, wrong again (see Smell #1) |
| `uv` toolchain | ✓ `uv 0.9.25`; `--python 3.12` pin mandatory |
| Environment reachability | ✓ n/a — all five tests mock the transport |
| Baseline | ✓ 534 passed (studio + rate-limiting + core statistics) before any edit |
| **Golden capture** | ✓ **completed before the first edit** — see Evidence |

## Accounting

| T-\<n\> | Level | Execution | Env (plan) | Runner (actual) | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|-------------------|---------|-------------------|
| T-1, T-3, T-38, T-39 | unit | Automatic | none | uv-pytest | executed | cumulative re-run, all green |
| T-6 … T-12 | integration | Automatic | repo-harness | uv-pytest | executed | cumulative re-run, all green (36 cases) |
| T-13 | integration | Automatic | repo-harness | uv-pytest | executed | 5/5 PASSED — `TestScenarioStatisticsContractUnchanged` |
| T-14 | integration | Automatic | repo-harness | uv-pytest | executed | 5/5 PASSED — `TestStatisticsRequestParameters` |
| T-15 | integration | Automatic | repo-harness | uv-pytest | executed | 8/8 PASSED — `TestLimitReachedNoLongerCrashesTheHelper` (6 helper + 2 caller) |
| T-16 | integration | Automatic | repo-harness | uv-pytest | executed | 2/2 PASSED — `TestSingleStatisticsCallSite` |
| T-17 | integration | Automatic | repo-harness | uv-pytest | executed | 2/2 PASSED — `TestCallerPreviewsUnchangedByRefactor` |

Ledgered = 16. Selected = 16. No test dropped.

## Cumulative readiness

- Selected (Passes after ≤ 3, Active): T-1, T-3, T-38, T-39, T-6…T-12, T-13…T-17
- Green: all 16 · BLOCKED: none · Unwritten-planned: none · Delegated: none
- Phase verdict: **PASS**

## Evidence

Full repo suite: **1626 passed, 137 deselected, 0 failed**.

**The refactor evidence is the ordering, not just the final green.** T-13/T-14/T-17 are guards, not
red-first tests — PRD §8 says the intended visible delta is none, so their goldens were captured from the
shipped implementation *before any edit*:

```
uv run --python 3.12 pytest ... -k "ContractUnchanged or StatisticsRequestParameters or CallerPreviews"
→ 12 passed          ← BEFORE the refactor
→ 12 passed          ← AFTER the refactor
```

Four branches were captured (no-constraints; zero-sim per-attack; partial-coverage aggregated;
partial-coverage verbose), plus the `sb_run_scenario` evaluate preview. Full dict equality, so key order,
`reasons` ordering and the exact conditions under which the four optional keys appear are all locked.

- **T-13**: executed — all four golden branches match byte-for-byte, and the no-constraints result's key
  set is exactly the seven mandatory keys with nothing optional leaking in.
- **T-14**: executed — the request still carries `includeDisabled=true` and `limit=500000`.
  `getConstraints`/`getAllConstraints` follow `include_constraints`, and `useCache` sits at the server
  default. Asserted on the parsed query dict rather than the raw string: pre-refactor the URL *omitted*
  the three parameters whose swagger defaults it wanted, where the core now states them — a different
  string, an identical request. See Smell #2.
- **T-15**: executed, **genuinely red first**. Against the shipped code, both modes raised
  `TypeError: '>' not supported between instances of 'NoneType' and 'int'`. Now neither raises;
  `matched*` report `None` (not `0`) when nothing was computed, totals still report map cardinality,
  the `resolved_attacks` sort tolerates nulls, and `simulationCount` stays `None`.
- **T-16**: executed, **red first with the right message** — "reached from 2 files", naming
  `studio_functions.py:2413` as the second call site. Now exactly one, in the fetch core. **AC-6 satisfied.**
- **T-17**: executed — the `sb_run_scenario` evaluate preview matches its pre-refactor fixture in full
  (`predicted_simulations`, `predicted_per_step`, per-step breakdown, `empty_steps`, `step_count`), and
  `sb_quick_run`'s preview is unchanged on the same statistics response.

**Three crash sites, not two.** The PRD names `sum(1 for v in ... if v > 0)` and
`sorted(key=lambda x: -x[1])`. A third, `sum(counts)` in the closing log line, would have kept T-15 red
after both named fixes were applied.

## Hand-off (delegated / BLOCKED)

None.

## To author (unwritten-planned)

None.

## Manual substitutions (not the planned test)

None.

## Smell observations

1. **`Environment needs: repo-harness` is wrong for T-13…T-17**, as it was for T-6…T-12. All five mock
   the transport entirely. Third phase running with this misclassification.
2. **T-14's "matching the pre-refactor request exactly" is unsatisfiable read literally.** The core always
   emits all five parameters; the old URL omitted three and relied on their swagger defaults
   (`getConstraints=false`, `getAllConstraints=false`, `useCache=true`). The strings differ; the requests
   do not. Implemented as semantic equality on the parsed query and recorded here.
3. **Nine seam-bound tests needed migration, not the five the phase plan predicted.** Four more live in
   `TestRunScenarioWithStatistics`, which patches only the studio-side resolvers. Root cause worth
   recording: `requests` is a single module object, so patching `studio_functions.requests.post` still
   intercepts the call after it moves into the core — but `get_api_base_url` / `get_api_account_id` /
   `get_auth_headers_for_console` are imported per-module and are not. Phase 3's Changes table lists only
   `studio_functions.py`; the test-file delta is real and was not anticipated.
4. **The crash was not fixed by the helper fix alone — the callers had to be fixed too.** Routing the
   helper through the core stopped *it* raising, which moved the crash one frame up to
   `sum(step_counts)` in both `sb_run_scenario` and `sb_quick_run`. T-15's `Verify` stops at the helper
   boundary and T-17's goldens are fully computed, so no phase test covered it; verified by running the
   real caller, not by reading. Fixed under an approved scope extension with two caller-level cases added.
   **No `T-<n>` covers this** — the plan's own T-15 Description ("breaks `quick_run` and `run_scenario`
   previews today") implies it, but its Verify does not reach it.
5. **`predicted_simulations` reports `0` on a truncated response** where the honest answer is "not
   computed". `predicted_per_step` keeps the distinction as `None`. Left for **Phase 4**, which owns the
   truncation explanation and the suppression rule.
6. **`_is_computed_count` is imported across a package boundary** despite its leading underscore. The PRD
   sanctions the reuse; a reviewer may prefer promoting it to a public name in `plan_statistics.py`.

## Verdict

- **PASS** — every cumulative test for Phase 3 green. The refactor's correctness rests on 12 guards that
  passed identically before and after the edit, and the two genuinely red tests both went green.
