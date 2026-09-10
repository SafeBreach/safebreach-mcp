# Test Results — Phase 6 (SAF-35508)
> Plan: ../test-plan.md | Run: 2026-08-27 | Mode: run

Phase 6 — Documentation.

## Preflight (Step 0)

| Check | Result |
|-------|--------|
| Dispatch mode | source-repo **uv-pytest** |
| Environment reachability | ✓ n/a — T-34 reads a file in the repo |
| **`Validate console environment`** | ✗ still absent — T-28…T-31, T-40 remain BLOCKED |
| Unwritten tests | none |

## Accounting

| T-\<n\> | Level | Execution | Env | Runner | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|--------|---------|-------------------|
| T-1…T-23, T-36, T-24…T-27 | — | Automatic | none | uv-pytest | executed | cumulative re-run, all green |
| T-34 | unit | Automatic | none | uv-pytest | executed | 5/5 PASSED — `TestToolCatalogDocumentsThePlanStatisticsTool` |
| T-28, T-29, T-30, T-31, T-40 | e2e | Automatic | Validate console | — | **BLOCKED** | no console provisioned; authored and collecting |

Ledgered = 33. Selected = 33. No test dropped.

## Cumulative readiness

- Green: 28 of 33 · **BLOCKED: T-28, T-29, T-30, T-31, T-40** · Unwritten-planned: none
- Phase verdict: **INCOMPLETE** — Phase 6's own test is green; the five inherited blocks remain

## Evidence

```
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_studio_functions.py -q \
  -k "ToolCatalogDocuments"
→ 5 passed
```

Full repo suite: **1710 passed, 145 deselected, 0 failed**.

- **T-34**: executed. Split red/green exactly as a documentation guard should be — the three catalog
  assertions were RED before the edit (`assert '`get_plan_statistics`' in ...` failed on the unmodified
  file), while the two gate-table assertions were GREEN before *and* after, since "the gate table is left
  alone" is a property to preserve, not to create. The entry names the runnable default, the
  `include_disabled` inversion and the read-only posture; the gate table still holds exactly its original
  seven rows and no row for the new tool.

New catalog lines verified within the project's 140-character markdown limit (the file's pre-existing
over-length lines at 123–344 are untouched).

## Hand-off (delegated / BLOCKED)

**T-28, T-29, T-30, T-31, T-40 — unchanged from phase-5.md.** Authored in
`safebreach_mcp_studio/tests/test_e2e_plan_statistics.py`, collecting cleanly, blocked on a Validate
console environment that has never been provisioned for SAF-35508.

```
export E2E_CONSOLE=<console> && source .vscode/set_env.sh
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_e2e_plan_statistics.py -m "e2e" -v
```

**T-35 (Manual, `Passes after: Final`) is not in this phase's set but is the other environment-blocked
item** — it checks the tool's Checkout-parameter numbers against what the console itself displays, and is
the only test that verifies the numbers are *right* rather than merely self-consistent.

## To author (unwritten-planned)

None.

## Manual substitutions (not the planned test)

None.

## Smell observations

1. **The documentation is now ahead of the verification.** CLAUDE.md states as fact that descriptions are
   "relayed verbatim from the orchestrator" — which no executed test has confirmed against a real console. T-40 is
   what would confirm it, and it has never run.
2. **`Automation lives in: planned:` is stale for T-34 too** — twelfth item on the plan backlog.
3. Phase 6's Changes table named only `CLAUDE.md`; the test file was also edited, as in every prior
   phase. The Changes tables consistently omit test files.

## Verdict

- **INCOMPLETE** — Phase 6's own deliverable is complete and T-34 is green. The phase set is not fully
  green because it inherits five environment-blocked e2e tests. Nothing was skipped silently.
