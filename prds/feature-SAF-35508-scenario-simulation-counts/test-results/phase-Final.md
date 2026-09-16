# Test Results — Phase Final (SAF-35508)

> Plan: ../test-plan.md | Run: 2026-09-16T14:05Z | Mode: run

## Preflight

```
toolchain: uv present ✓ (0.9.25) · uv sync ✓ (46 packages audited, --python 3.12)
repo-root  /Users/bariber/projects/core/safebreach-mcp/.claude/worktrees/SAF-35508-scenario-simulation-counts — cwd matches ✓
dispatch   standalone-Python (pyproject.toml + uv.lock, no package.json) → uv-pytest mode ✓
sub-runners  run-validate-attack installed ✓ · sb-ui:manual-ui-testing installed ✓ (1.1.17)
authored files  test_scenario_simulation_counts.py ✓ · test_scenario_blocked_entities.py ✓
planned files   test_scenario_statistics_contract.py ✗ absent · test_e2e_scenario_statistics.py ✗ absent
environment     prds/.../environment.md ✗ absent
reachability    network control (github) 200 ✓ · console pentest01.sbops.com 000 ✗ (no route / VPN) ·
                console API token in env ✗ (0 found) · SafeBreach MCP servers ✗ (all 4 failed to connect)
per-id check    pytest -k "T_<n>" → 88 deselected for every probed id (T-1, T-7, T-15, T-19, T-24) ✗
```

**Environment note:** a real Validate console was NOT provisioned. `provision-feature-environment` builds live AWS
infrastructure at cost; with 7 of the 7 real-env tests unwritten, provisioning could not have moved the verdict, so
it was left to an explicit human decision rather than spent unilaterally.

## Suite-level evidence (the real signal)

The two authored suites are **green**:

```
$ SKIP_E2E_TESTS=true uv run --python 3.12 pytest \
    safebreach_mcp_studio/tests/test_scenario_simulation_counts.py \
    safebreach_mcp_studio/tests/test_scenario_blocked_entities.py -q
88 passed in 0.20s
```

This is genuine evidence that the delivered behaviour is covered and passing. It is **not** per-`T-<n>` evidence —
see the accounting gap below, which is why no individual test is marked `executed`.

## Accounting

| T-\<n\> | Level | Execution | Env | Runner (intended) | Outcome | Evidence / Reason |
|------|-------|-----------|-----|-------------------|---------|-------------------|
| T-1 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green (88/88); `-k "T_1"` → 88 deselected — id not addressable |
| T-2 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-3 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-4 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-5 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-6 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-7 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; `-k "T_7"` → 88 deselected |
| T-8 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-9 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-10 | unit | Automatic | none | uv-pytest | BLOCKED | Id not addressable; **and** the RBAC/`PermissionError` case is a known coverage gap — `check_rbac_response` is patched to a no-op in every existing test |
| T-11 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-12 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-13 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-14 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-15 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; `-k "T_15"` → 88 deselected |
| T-16 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-17 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-18 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-19 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; `-k "T_19"` → 88 deselected |
| T-20 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-21 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-22 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-23 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-24 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; `-k "T_24"` → 88 deselected |
| T-25 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-26 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-27 | unit | Automatic | none | uv-pytest | BLOCKED | Suite green; id not addressable |
| T-28 | unit | Automatic | none | uv-pytest | BLOCKED | Id not addressable; **and** the MCP wrapper layer is a known coverage gap — both suites call `sb_get_*` directly |
| T-29 | unit | Automatic | none | uv-pytest | unwritten-planned | `planned: .../test_scenario_statistics_contract.py` absent in a resolvable repo |
| T-30 | unit | Automatic | none | uv-pytest | unwritten-planned | same file absent |
| T-31 | e2e | Automatic | Validate console | run-validate-attack | unwritten-planned | `planned: .../test_e2e_scenario_statistics.py` absent in a resolvable repo |
| T-32 | e2e | Automatic | Validate console | run-validate-attack | unwritten-planned | same file absent |
| T-33 | e2e | Automatic | Validate console | run-validate-attack | unwritten-planned | same file absent |
| T-34 | e2e | Automatic | Validate console | run-validate-attack | unwritten-planned | same file absent |
| T-35 | e2e | Automatic | Validate console | run-validate-attack | unwritten-planned | same file absent |
| T-36 | e2e | Manual | Validate console | sb-ui:manual-ui-testing | BLOCKED | No environment.md; console unreachable (000); no API token; MCP servers down |
| T-37 | e2e | Manual | Validate console | sb-ui:manual-ui-testing | BLOCKED | Same — no live console to walk the feature through |

Ledgered rows: 37 · Selected: 37 ✓ (no test dropped)

## Cumulative readiness

- Selected (Active, Passes after ≤ Final): T-1 … T-37 (all 37)
- Green (per-id evidence): **none**
- BLOCKED: T-1 … T-28 (per-id accounting gap; underlying suite green), T-36, T-37 (no live console) — 30 total
- Unwritten-planned: T-29 … T-35 — 7 total
- Local-pending-ci: none · Delegated: none · Manual substitutions: none
- **Phase verdict: INCOMPLETE**

## Evidence

- Suite-level: `88 passed in 0.20s` — both authored studio suites, uv-pytest, py3.12. Real and reproducible, but
  not attributable to individual `T-<n>` ids.
- T-1 … T-28: no per-id evidence — see Hand-off.
- T-29 … T-35: no evidence — not authored.
- T-36, T-37: no evidence — no environment.

## Hand-off (delegated / BLOCKED)

- **T-1 … T-28 — BLOCKED (accounting, not correctness).** The 88 authored tests pass, but none carries the
  `T-<n>:` title prefix the automation title contract requires, so `pytest -k "T_<n>"` deselects all 88 for every
  id. Step 4's per-selected-id inclusion check forbids accepting a batch pass as per-id evidence. **Fix:** prefix
  each test's name with its plan id (`def test_T_7_null_is_never_zero…`), then re-run. This is the plan's own
  accepted gap #2, now demonstrated rather than predicted. No code defect is implied — the behaviour is green.
- **T-36, T-37 — BLOCKED (infra).** Both need a live Validate console. There is no `environment.md`,
  `pentest01.sbops.com` returns `000` (no route — VPN required), no console API token is present, and all four
  SafeBreach MCP servers failed to connect this session. **Fix:** provision via
  `provision-feature-environment SAF-35508` (needs one offline/disabled simulator and a Windows+Linux mix), from a
  VPN-connected machine, then re-run.

## To author (unwritten-planned)

- **T-29, T-30** — `planned: safebreach_mcp_studio/tests/test_scenario_statistics_contract.py`. Author the recorded
  real-console payload contract test and the transport-failure/timeout test.
- **T-31 … T-35** — `planned: safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py`. Author the five e2e
  cases following the existing `test_e2e_run_scenario.py` pattern (module-level `SKIP_E2E_TESTS` + `@pytest.mark.e2e`,
  `E2E_CONSOLE` default `pentest01`, discover-don't-create fixtures). These also need the environment above.

## Manual substitutions (not the planned test)

- None. No improvised probe was recorded in place of any planned test.

## Smell observations

- **The plan's `Evidence required` for T-31 … T-35 names evidence that cannot exist.** The e2e tier normally owes a
  butler job + build #, but this repo has no CI that runs pytest at all, so those tests can never upgrade past a
  local run. The plan already flags this as an accepted gap; it should be revised via `authoring-test-plan` to name
  evidence that actually exists (console name + timestamped output), rather than leaving a permanently-owed build.
- **The authored suites and the plan were written independently**, so the T-id ↔ test-case mapping exists only in
  prose. Until the title prefixes land, every future run repeats this same accounting gap.
- **`ruff` is not installed** (`uv run ruff` fails to spawn; absent from `uv.lock`), so the lint gate the PRD names
  as its quality bar did not run and cannot run as written.
- The PRD's §3 Component C still claims the blocked answer "never depends on step order", which is broader than the
  delivered per-step-union verdict confirmed as intended at the authoring gate.

## Verdict

- **INCOMPLETE** — 30 BLOCKED, 7 unwritten-planned, 0 with per-id evidence. **The feature cannot be signed off.**
  Note for the reader: this is a *sign-off evidence* verdict, not a statement that the code is broken — the 88
  authored tests pass. What is missing is per-id attribution, seven unwritten tests, and any real-environment run.
