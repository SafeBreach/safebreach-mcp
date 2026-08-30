# Test Results — Phase 5 (SAF-35508)
> Plan: ../test-plan.md | Run: 2026-08-27 | Mode: run

Phase 5 — Public function + tool registration.

## Preflight (Step 0)

| Check | Result |
|-------|--------|
| Dispatch mode | source-repo **uv-pytest** for T-24…T-27; e2e for T-28…T-31, T-40 |
| `uv` toolchain | ✓ `uv 0.9.25`; `--python 3.12` pin mandatory |
| **`Validate console environment`** | ✗ **absent** — no environment provisioned for SAF-35508. Five tests blocked. |
| `E2E_CONSOLE` | not set; no `.vscode/set_env.sh` sourced |
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
| T-28 | e2e | Automatic | Validate console | — | **BLOCKED** | no console provisioned; test authored and collected |
| T-29 | e2e | Automatic | Validate console | — | **BLOCKED** | as above (2 cases) |
| T-30 | e2e | Automatic | Validate console | — | **BLOCKED** | as above (2 cases) |
| T-31 | e2e | Automatic | Validate console | — | **BLOCKED** | as above |
| T-40 | e2e | Automatic | Validate console | — | **BLOCKED** | as above (2 cases) |

¹ wrong again — T-27 mocks the transport. Fifth consecutive phase.

Ledgered = 32. Selected = 32. No test dropped.

## Cumulative readiness

- Green: T-1, T-3, T-38, T-39, T-6…T-12, T-13…T-17, T-18…T-23, T-36, T-24, T-25, T-26, T-27 (27 of 32)
- **BLOCKED: T-28, T-29, T-30, T-31, T-40** — environment, not code
- Unwritten-planned: none · Delegated: none
- Phase verdict: **INCOMPLETE** — five tests cannot run until a console exists

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

**T-28, T-29, T-30, T-31, T-40 — BLOCKED on infrastructure, not on code.**

All five are authored in `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py` and collect cleanly
(`--collect-only` → 8 tests). They need a **Validate console environment**, which does not exist for
SAF-35508. To run them:

```
# provision, then:
export E2E_CONSOLE=<console>          # defaults to pentest01
source .vscode/set_env.sh
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_e2e_plan_statistics.py -m "e2e" -v
```

Nothing is hardcoded — every scenario and plan id is discovered at runtime via `_fetch_all_scenarios` /
`_fetch_all_plans`, so they adapt to whatever the console holds.

**T-40 matters most of the five.** It is the only test in the entire plan that can falsify the relay
design: every Phase 1 test asserts MCP's behaviour *given* a catalog. Until it runs against a real
console, "Core supplies the descriptions we relay" remains an assumption.

Two carry deliberate skip paths (T-30's disabled-simulator precondition, T-40's SAF-35568 precondition).
Each asserts its unconditional half **before** the skip, so a skipped precondition can never be reported
as a pass — the specific failure both tests warn about.

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
5. **Uncapped raw maps.** `attacks`, `simulators`, `attacker_simulators` and `target_simulators` are
   relayed whole, and with `both_counts=True` twice. On a real console a step can carry thousands of
   attack ids. §4 specifies full maps and T-20/T-21 assert on them, so capping is a PRD decision, not a
   code fix.
6. **`simulator_names` is dead on every production path.** `_fetch_and_shape` never passes it, so
   `zero_impact_simulators` always emits bare UUIDs. Kept as the documented extension point for a future
   `get_console_simulators` lookup; noted so it does not evaporate.
7. **Phase 6 (T-34) is the CLAUDE.md tool-catalog entry** — correctly still pending; the tool is not yet
   in the catalog list.

## Verdict

- **INCOMPLETE** — 27 of 32 cumulative tests green with evidence. Five are BLOCKED on a Validate console
  environment that has never been provisioned for this ticket. No test was skipped silently, none is
  unwritten, and no manual substitution stands in for a planned test.
