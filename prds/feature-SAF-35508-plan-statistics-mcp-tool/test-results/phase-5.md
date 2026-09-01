# Test Results — Phase 5 (SAF-35508)
> Plan: ../test-plan.md | Run: 2026-08-27 | Mode: run

Phase 5 — Public function + tool registration.

## Preflight (Step 0)

| Check | Result |
|-------|--------|
| Dispatch mode | source-repo **uv-pytest** for T-24…T-27; e2e for T-28…T-31, T-40 |
| `uv` toolchain | ✓ `uv 0.9.25`; `--python 3.12` pin mandatory |
| **`Validate console environment`** | ✓ `zircon-piculet.dev.sbops.com` — reused, not built (see `../env-design.md`) |
| `E2E_CONSOLE` | set to `zircon-piculet.dev.sbops.com`; token from `~/.claude/safebreach.json` |
| `-m "not e2e"` | ✓ **required, not automatic** — `pyproject.toml` registers the `e2e` marker but sets no `addopts`, so the marker alone deselects nothing |
| Unwritten tests | ✓ none — all nine authored, including the five that cannot run |

## Accounting

| T-\<n\> | Level | Execution | Env | Runner | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|--------|---------|-------------------|
| T-1…T-3, T-38, T-39, T-6…T-23, T-36 | — | Automatic | none | uv-pytest | executed | cumulative re-run, all green |
| T-24 | unit | Automatic | none | uv-pytest | executed | 7/7 PASSED — `TestPlanStatisticsToolRegistration` |
| T-25 | unit | Automatic | none | uv-pytest | executed | 2/2 PASSED — `TestPlanStatisticsTakesNoRateLimitingGates` |
| T-26 | unit | Automatic | none | uv-pytest | executed | 7/7 PASSED — `TestPlanInputIsExclusiveAndParsed` |
| T-27 | integration | Automatic | repo-harness¹ | uv-pytest | executed | 9/9 PASSED — `TestCountsModeSelectsOneCallOrTwo` |
| T-28 | e2e | Automatic | Validate console | pytest -m e2e | executed | PASSED — see Addendum |
| T-29 | e2e | Automatic | Validate console | pytest -m e2e | executed | 2/2 PASSED |
| T-30 | e2e | Automatic | Validate console | pytest -m e2e | executed | 2/2 PASSED, neither skipped |
| T-31 | e2e | Automatic | Validate console | pytest -m e2e | executed | PASSED |
| T-40 | e2e | Automatic | Validate console | pytest -m e2e | executed | 2/2 PASSED, neither skipped |

¹ wrong again — T-27 mocks the transport. Fifth consecutive phase.

Ledgered = 32. Selected = 32. No test dropped.

## Cumulative readiness

- Green: **all 32** — the 27 offline plus T-28, T-29, T-30, T-31, T-40, executed against
  `zircon-piculet.dev.sbops.com` on 2026-08-27 (see Addendum)
- BLOCKED: none · Unwritten-planned: none · Delegated: none
- Phase verdict: **PASS**

## Evidence

```
uv run --python 3.12 pytest safebreach_mcp_studio/tests/ -q -m "not e2e" \
  -k "PlanStatisticsToolRegistration or PlanInputIsExclusive or CountsModeSelects or
      TruncatedResponsesRender"
→ 27 passed
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_rate_limiting.py -q \
  -k "PlanStatisticsTakesNoRateLimiting"
→ 2 passed
```

Full repo suite: **1705 passed, 145 deselected, 0 failed**.

- **T-24**: executed — `get_plan_statistics` is registered under exactly that wire name (no `sb_`
  prefix), with `readOnlyHint=True` and `destructiveHint=False`, via `mcp.list_tools()` on a server
  constructed in-process. All 12 pre-existing studio tools remain, and the count is asserted at 13 so a
  future accidental removal fails. The three counter-intuitive statements §8 requires are each asserted
  on a stable substring.
- **T-25**: executed both ways — with `rate_limiter` mocked, neither `check_limit` nor `record_action`
  is called across 12 invocations (past both the 10 total and 5 per-tool limits); and with
  `_rate_limit_enabled` genuinely patched True, the store is left empty. **The registration contains
  zero references to the limiter**, so the property holds by construction.
- **T-26**: executed — both/neither/malformed-JSON/non-object all raise with a message naming both
  inputs and the exclusivity, and no API call is attempted in any case. Plus the two blank-string cases
  found in review.
- **T-27**: executed — default issues one call with `includeDisabled=false` labelled runnable;
  `include_disabled=True` issues one with `true` labelled expected; `both_counts=True` issues exactly
  two, one of each, returning two labelled reports each carrying its own derived `counts_mode`, and
  neither nested hint advises a call that was already made.

## Hand-off (delegated / BLOCKED)

None — the five e2e tests recorded BLOCKED in the original run have since executed and passed. See the
Addendum.

Nothing in them is hardcoded: every scenario and plan id is discovered at runtime via
`_fetch_all_scenarios` / `_fetch_all_plans`, so they adapt to whatever console they are pointed at.

## To author (unwritten-planned)

None.

## Manual substitutions (not the planned test)

None.

## Smell observations

1. **The limit-reached crash had a third frame, found only in review.** Phase 3 fixed
   `_get_scenario_statistics` and then both callers' `sum(step_counts)`, and phase-3.md claimed it
   "verified gone end-to-end". That verification ran `sb_run_scenario` directly, **not through the
   registered tool**, and the renderer's `f"{count:,}"` and `count > 0` still raised — swallowed by the
   wrapper's `except Exception` into an error string. Fixed here at four sites plus a `> 0` comparison,
   and verified through the tool this time. **Process lesson: a fix verified one layer below the user
   is not verified.**
2. **A truncated run told the user something false.** `sb_run_scenario` refused with "would produce 0
   simulations across all 1 steps. No matching simulators or attacks found." — a measured verdict on a
   path where nothing was measured, and reporting the *returned* step count as the plan's. Now refuses
   with "could not be scored … this is NOT a report that nothing runs".
3. **No `T-<n>` covers any renderer.** Four tests were written for the truncated preview because
   nothing else would have caught the above. This is the second renderer gap (Phase 1's
   `_render_constraint_reason` was the first).
4. **`_get_scenario_statistics` discards `truncated` / `counts_computed` / `isLimitReached`.** The
   fetch core supplies all three; the helper drops them, so callers must re-derive truncation from
   `simulationCount is None`. **This cannot be fixed without changing T-13**, whose goldens lock the
   step dict to exactly seven keys — a genuine tension between the contract-lock and the improvement.
   Needs an owner decision.
5. **Uncapped raw maps — since confirmed as a defect and fixed.** Recorded here as "a PRD decision, not
   a code fix". The first live call settled it: one default step returned 38,531 conflicts, 9,613 attacks
   and an **11.8 MB** result. Capped in `a4a0800` with true totals stated; a real scenario now scores in
   41.7 KB. **The judgement to defer it was wrong** — it was a defect, and only live data made that
   visible.
6. **`simulator_names` is dead on every production path.** `_fetch_and_shape` never passes it, so
   `zero_impact_simulators` always emits bare UUIDs. Kept as the documented extension point for a future
   `get_console_simulators` lookup; noted so it does not evaporate.
7. **Phase 6 (T-34) is the CLAUDE.md tool-catalog entry** — correctly still pending; the tool is not yet
   in the catalog list.

## Addendum — 2026-08-27, the e2e suite executed

The five e2e tests recorded BLOCKED above have now **run and passed**, against
`zircon-piculet.dev.sbops.com` (the console whose mcp-proxy was updated to this feature branch):

```
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_e2e_plan_statistics.py -m e2e -v -rs
→ 8 passed in 99.62s
```

**Zero skips**, which matters more than the pass count: T-30 and T-40 each carry a deliberate skip path
for a console that cannot demonstrate their precondition, and neither fired. So this console does have a
disabled/offline simulator (T-30's conditional half genuinely ran) and does carry SAF-35568 (T-40's relay
assertions genuinely ran).

Two things this run corrected:

1. **`test_custom_plan_integer_string_id_is_accepted` passed rather than skipping.** An earlier ad-hoc
   probe reported "no custom plans on this console" — it queried the wrong endpoint. `_fetch_all_plans`
   finds them. The test was more reliable than the probe.
2. **The suite could not have passed before today's fix.** Five of its eight cases pass an OOB scenario
   UUID, which returned `400 /id must be integer` until `900db94`. This run is the first execution of
   this file, and it is what a green e2e suite is for — the defect was found by probe, but the suite is
   what proves the fix.

## Verdict

- **PASS** — all 32 cumulative tests green with evidence. The five previously BLOCKED e2e tests executed
  against a real console with zero skips. Nothing is unwritten, nothing was skipped silently, and no
  manual substitution stands in for a planned test.

  Still outside this phase: **T-32, T-33, T-35** (Manual, `Passes after: Final`). T-35 remains the only
  check that the numbers are *right* rather than internally consistent.
