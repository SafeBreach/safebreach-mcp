# Test Results — Phase 7 (SAF-35508)

> Plan: ../test-plan.md | Run: 2026-09-03T09:46 | Mode: run

Phase 7 adds three pure projections and their public functions. Nothing is registered, so the MCP
surface is unchanged at phase end — which is why the 23 tests from phases 1–4 are expected to pass
**untouched**, and did.

## Accounting

| T-<n> | Level | Execution | Env | Runner (intended) | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|-------------------|---------|-------------------|
| T-1 | unit | Automatic | none | source-repo uv-pytest | executed | 4 cases green — `TestNoVendoredConstraintVocabulary` |
| T-3 | unit | Automatic | none | source-repo uv-pytest | executed | 5 cases green — `TestUnrecognisedConstraintCode` |
| T-38 | unit | Automatic | none | source-repo uv-pytest | executed | 6 cases green — `TestConstraintDescriptionsRelayedVerbatim` |
| T-39 | unit | Automatic | none | source-repo uv-pytest | executed | 5 cases green — `TestAbsentConstraintCatalog` |
| T-6 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 8 cases green — `TestAdHocPlanBodyIsScoredUnreduced` |
| T-7 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 4 cases green — `TestScenarioIdIsPassedForNativeResolution` |
| T-8 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 3 cases green — `TestStepLessPlanRejectedBeforeAnyCall` |
| T-9 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 4 cases green — `TestAllFiveQueryParametersArePassedThrough` |
| T-10 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 8 cases green — `TestLimitReachedResponseKeepsNullDistinctFromZero` |
| T-11 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 5 cases green — `TestApiFailureSurfacesTheFullResponseBody` |
| T-12 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 2 cases green — `TestNoMcpSideCaching` |
| T-13 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 5 cases green — `TestScenarioStatisticsContractUnchanged` |
| T-14 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 5 cases green — `TestStatisticsRequestParameters` |
| T-15 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 8 cases green — `TestLimitReachedNoLongerCrashesTheHelper` |
| T-16 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 2 cases green — `TestSingleStatisticsCallSite` |
| T-17 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 2 cases green — `TestCallerPreviewsUnchangedByRefactor` |
| T-18 | unit | Automatic | none | source-repo uv-pytest | executed | 4 cases green — `TestSparseConstraintMapIsNotDense` |
| T-19 | unit | Automatic | none | source-repo uv-pytest | executed | 4 cases green — `TestEveryReasonInAConstraintLeafSurfaces` |
| T-20 | unit | Automatic | none | source-repo uv-pytest | executed | 5 cases green — `TestZeroImpactAttacksRequireIntegerZero` |
| T-21 | unit | Automatic | none | source-repo uv-pytest | executed | 5 cases green — `TestZeroImpactSimulatorsComeFromTheUnionMap` |
| T-22 | unit | Automatic | none | source-repo uv-pytest | executed | 6 cases green — `TestLimitReachedSuppressesZeroImpactReporting` |
| T-23 | unit | Automatic | none | source-repo uv-pytest | executed | 6 cases green — `TestConflictsAreNormalizedAgainstTheCatalog` |
| T-36 | unit | Automatic | none | source-repo uv-pytest | executed | 6 cases green — `TestSeverityIsComputedFromTheAttackCount` |
| T-26 | unit | Automatic | none | source-repo uv-pytest | executed | 27 cases green — `TestPlanInputIsExclusiveAndParsed`, `TestScenarioInputIsExclusiveOnAllThreeTools` |
| T-27 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 14 cases green — `TestCountsModeSelectsOneCallOrTwo`, `TestScenarioCountsModeSelectsOneCallOrTwo` |
| T-41 | unit | Automatic | none | source-repo uv-pytest | executed | 6 cases green — `TestEachProjectionRendersOnlyItsSlice` |
| T-42 | unit | Automatic | none | source-repo uv-pytest | executed | 10 cases green — `TestBlockedEntitiesVerdictComesFromCountsComputed` |
| T-43 | unit | Automatic | none | source-repo uv-pytest | executed | 11 cases green — `TestNamedAttackResolvesToOneDisposition` |
| T-44 | unit | Automatic | none | source-repo uv-pytest | executed | 16 cases green — `TestFilteringPrecedesCapping` |
| T-45 | unit | Automatic | none | source-repo uv-pytest | executed | 5 cases green — `TestBlockedEntitiesCatalogIsNarrowed` |
| T-46 | integration | Automatic | repo-harness | source-repo uv-pytest | executed | 15 cases green — `TestEachToolMakesExactlyOneStatisticsCall` |
| T-49 | unit | Automatic | none | source-repo uv-pytest | executed | 3 cases green — `TestMultiStepDispositionPrecedence` |
| T-50 | unit | Automatic | none | source-repo uv-pytest | executed | 5 cases green — `TestInvalidAttackIdIsRejectedBeforeAnyCall` |
| T-51 | unit | Automatic | none | source-repo uv-pytest | executed | 5 cases green — `TestBlockerDetailTruncatedIsNotNoConstraintReported` |
| T-52 | unit | Automatic | none | source-repo uv-pytest | executed | 3 cases green — `TestAttackBlockersCatalogIsNarrowed` |
| T-53 | unit | Automatic | none | source-repo uv-pytest | executed | 10 cases green — `TestBlockedEntitiesVerdictComesFromCountsComputed` |
| T-54 | unit | Automatic | none | source-repo uv-pytest | executed | 16 cases green — `TestFilteringPrecedesCapping` |

## Cumulative readiness

- Selected (Passes after ≤ 7, Active): 37 — T-1, T-3, T-38, T-39, T-6, T-7, T-8, T-9, T-10, T-11, T-12, T-13, T-14, T-15, T-16, T-17, T-18, T-19, T-20, T-21, T-22, T-23, T-36, T-26, T-27, T-41, T-42, T-43, T-44, T-45, T-46, T-49, T-50, T-51, T-52, T-53, T-54
- Green: all 37 · BLOCKED: none · Unwritten-planned: none · Local-pending-ci: none · Delegated: none
- Total assertions executed across the phase set: **258** individual cases
- Whole-repo suite (`-m "not e2e"`): **1873 passed / 0 failed**; the 1771 that predate this phase are unchanged, which is the property Phase 7 had to preserve.
- **Phase verdict: PASS**

## Evidence

Every row ran as itself, selected by its own implementing class, not inferred from an aggregate
total. Runner: `uv run --python 3.12 pytest <file> -k <class>` per test.

- T-1: executed — `[32m[32m[1m4 passed[0m, [33m724 deselected[0m[32m in 0.11s[0m[0m` via `-k TestNoVendoredConstraintVocabulary`
- T-3: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.10s[0m[0m` via `-k TestUnrecognisedConstraintCode`
- T-38: executed — `[32m[32m[1m6 passed[0m, [33m722 deselected[0m[32m in 0.10s[0m[0m` via `-k TestConstraintDescriptionsRelayedVerbatim`
- T-39: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.11s[0m[0m` via `-k TestAbsentConstraintCatalog`
- T-6: executed — `[32m[32m[1m8 passed[0m, [33m46 deselected[0m[32m in 0.02s[0m[0m` via `-k TestAdHocPlanBodyIsScoredUnreduced`
- T-7: executed — `[32m[32m[1m4 passed[0m, [33m50 deselected[0m[32m in 0.02s[0m[0m` via `-k TestScenarioIdIsPassedForNativeResolution`
- T-8: executed — `[32m[32m[1m3 passed[0m, [33m51 deselected[0m[32m in 0.02s[0m[0m` via `-k TestStepLessPlanRejectedBeforeAnyCall`
- T-9: executed — `[32m[32m[1m4 passed[0m, [33m50 deselected[0m[32m in 0.02s[0m[0m` via `-k TestAllFiveQueryParametersArePassedThrough`
- T-10: executed — `[32m[32m[1m8 passed[0m, [33m46 deselected[0m[32m in 0.02s[0m[0m` via `-k TestLimitReachedResponseKeepsNullDistinctFromZero`
- T-11: executed — `[32m[32m[1m5 passed[0m, [33m49 deselected[0m[32m in 0.02s[0m[0m` via `-k TestApiFailureSurfacesTheFullResponseBody`
- T-12: executed — `[32m[32m[1m2 passed[0m, [33m52 deselected[0m[32m in 0.02s[0m[0m` via `-k TestNoMcpSideCaching`
- T-13: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.11s[0m[0m` via `-k TestScenarioStatisticsContractUnchanged`
- T-14: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.11s[0m[0m` via `-k TestStatisticsRequestParameters`
- T-15: executed — `[32m[32m[1m8 passed[0m, [33m720 deselected[0m[32m in 0.12s[0m[0m` via `-k TestLimitReachedNoLongerCrashesTheHelper`
- T-16: executed — `[32m[32m[1m2 passed[0m, [33m52 deselected[0m[32m in 0.74s[0m[0m` via `-k TestSingleStatisticsCallSite`
- T-17: executed — `[32m[32m[1m2 passed[0m, [33m726 deselected[0m[32m in 0.11s[0m[0m` via `-k TestCallerPreviewsUnchangedByRefactor`
- T-18: executed — `[32m[32m[1m4 passed[0m, [33m724 deselected[0m[32m in 0.10s[0m[0m` via `-k TestSparseConstraintMapIsNotDense`
- T-19: executed — `[32m[32m[1m4 passed[0m, [33m724 deselected[0m[32m in 0.10s[0m[0m` via `-k TestEveryReasonInAConstraintLeafSurfaces`
- T-20: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.10s[0m[0m` via `-k TestZeroImpactAttacksRequireIntegerZero`
- T-21: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.11s[0m[0m` via `-k TestZeroImpactSimulatorsComeFromTheUnionMap`
- T-22: executed — `[32m[32m[1m6 passed[0m, [33m722 deselected[0m[32m in 0.11s[0m[0m` via `-k TestLimitReachedSuppressesZeroImpactReporting`
- T-23: executed — `[32m[32m[1m6 passed[0m, [33m722 deselected[0m[32m in 0.11s[0m[0m` via `-k TestConflictsAreNormalizedAgainstTheCatalog`
- T-36: executed — `[32m[32m[1m6 passed[0m, [33m722 deselected[0m[32m in 0.11s[0m[0m` via `-k TestSeverityIsComputedFromTheAttackCount`
- T-26: executed — `[32m[32m[1m27 passed[0m, [33m701 deselected[0m[32m in 0.13s[0m[0m` via `-k TestPlanInputIsExclusiveAndParsed, TestScenarioInputIsExclusiveOnAllThreeTools`
- T-27: executed — `[32m[32m[1m14 passed[0m, [33m714 deselected[0m[32m in 0.12s[0m[0m` via `-k TestCountsModeSelectsOneCallOrTwo, TestScenarioCountsModeSelectsOneCallOrTwo`
- T-41: executed — `[32m[32m[1m6 passed[0m, [33m722 deselected[0m[32m in 0.10s[0m[0m` via `-k TestEachProjectionRendersOnlyItsSlice`
- T-42: executed — `[32m[32m[1m10 passed[0m, [33m718 deselected[0m[32m in 0.11s[0m[0m` via `-k TestBlockedEntitiesVerdictComesFromCountsComputed`
- T-43: executed — `[32m[32m[1m11 passed[0m, [33m717 deselected[0m[32m in 0.11s[0m[0m` via `-k TestNamedAttackResolvesToOneDisposition`
- T-44: executed — `[32m[32m[1m16 passed[0m, [33m712 deselected[0m[32m in 0.13s[0m[0m` via `-k TestFilteringPrecedesCapping`
- T-45: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.10s[0m[0m` via `-k TestBlockedEntitiesCatalogIsNarrowed`
- T-46: executed — `[32m[32m[1m15 passed[0m, [33m713 deselected[0m[32m in 0.12s[0m[0m` via `-k TestEachToolMakesExactlyOneStatisticsCall`
- T-49: executed — `[32m[32m[1m3 passed[0m, [33m725 deselected[0m[32m in 0.10s[0m[0m` via `-k TestMultiStepDispositionPrecedence`
- T-50: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.11s[0m[0m` via `-k TestInvalidAttackIdIsRejectedBeforeAnyCall`
- T-51: executed — `[32m[32m[1m5 passed[0m, [33m723 deselected[0m[32m in 0.11s[0m[0m` via `-k TestBlockerDetailTruncatedIsNotNoConstraintReported`
- T-52: executed — `[32m[32m[1m3 passed[0m, [33m725 deselected[0m[32m in 0.10s[0m[0m` via `-k TestAttackBlockersCatalogIsNarrowed`
- T-53: executed — `[32m[32m[1m10 passed[0m, [33m718 deselected[0m[32m in 0.11s[0m[0m` via `-k TestBlockedEntitiesVerdictComesFromCountsComputed`
- T-54: executed — `[32m[32m[1m16 passed[0m, [33m712 deselected[0m[32m in 0.12s[0m[0m` via `-k TestFilteringPrecedesCapping`

**Why these are `executed` and not `local-pending-ci`:** the provenance rule reserves
`local-pending-ci` for a test whose `Evidence required` names a CI build. Every test in this phase
set asks only for "pytest run output naming the test", which is exactly what is cited above. This
repo additionally has **no CI test gate** to owe a build number to (recorded in the plan's Regression
section: `.github/workflows/` carries only `security-scan.yml` and `release.yml`).

## Hand-off (delegated / BLOCKED)

- None.

## To author (unwritten-planned)

- None. **But see the first smell** — 36 of the 37 selected tests still carry a stale
  `Automation lives in: planned:` prefix in the plan, which by the runner's own rule would have
  classified them `unwritten-planned`. They are all written; the marker is wrong, not the test.

## Manual substitutions (not the planned test)

- None.

## Smell observations

- **Stale `planned:` markers (36 of 37).** Every selected test's `Automation lives in:` still reads
  `planned: <path>`, though all 36 paths exist and every class was found and run. Taken literally the
  dispatch rule would mark this entire phase `unwritten-planned` and run nothing — a green phase
  reported as unwritten. The plan's own change log has flagged this since Phase 1 and it is still
  open; it wants an `authoring-test-plan` pass to drop the prefixes.
- **T-53 and T-54 had no implementing class docstring** naming them when this run started — their
  cases were added inside T-42's and T-44's classes. Fixed during preflight by naming both ids in
  those docstrings, so plan→test traceability is click-through. Worth watching whenever a review adds
  cases to an existing class rather than a new one.
- **`Environment needs: repo-harness` is wrong for 14 of these tests.** They all mock the transport
  and need no backing service; the phase ran with no environment at all. The PRD's Phase 2 and Phase 3
  notes already record this mislabel twice. Correct value is `none`. Left as-is rather than silently
  edited — it belongs to `authoring-test-plan`.
- **`uv` panicked intermittently** mid-phase (`Tokio executor failed`, uv 0.9.25), three times in a
  row, then recovered on its own. `.venv/bin/python -m pytest` was unaffected throughout and gave
  identical results. Not a code signal, but a runner flake worth knowing if a future phase reports a
  spurious infrastructure failure.
- **Six review rounds were needed to reach this green**, and three of the nine defects fixed were
  regressions introduced by an earlier round's own fix. The common cause was three separate
  aggregations answering one question; they now share a single rule. Flagged for sign-off attention
  because the pattern — a fix that satisfies its test while breaking a sibling invariant — is not
  visible in a passing suite.

## Verdict

- **PASS** — every cumulative test green with its own evidence ref; no BLOCKED, no
  unwritten-planned, no manual substitution.
