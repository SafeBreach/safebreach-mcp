# Test Results — Phase Final (SAF-35508)

> Plan: ../test-plan.md | Run: 2026-09-16T14:50Z | Mode: run (second pass, after remediation)

## Run history

| Pass | Result |
|---|---|
| 1 (14:05Z) | INCOMPLETE — 30 BLOCKED, 7 unwritten-planned, **0 green by id**. No test carried a `T-<n>:` title prefix, so no plan id was addressable. |
| 2 (14:50Z, this pass) | INCOMPLETE — **29 executed with per-id evidence**, 7 BLOCKED (no console), 1 unwritten-planned. |

Between passes: every test method was prefixed with its plan id, and the cases that had none were authored
(T-9, T-12, T-22, T-28, the RBAC half of T-10, T-30, and T-31 … T-35).

## Preflight

```
toolchain: uv present ✓ (0.9.25) · uv sync ✓ (46 packages audited, --python 3.12)
repo-root  …/worktrees/SAF-35508-scenario-simulation-counts — cwd matches ✓
dispatch   standalone-Python (pyproject.toml + uv.lock, no package.json) → uv-pytest mode ✓
sub-runners  run-validate-attack installed ✓ · sb-ui:manual-ui-testing installed ✓ (1.1.17)
test files   counts ✓ · blocked ✓ · statistics_contract ✓ (new) · e2e_scenario_statistics ✓ (new)
environment  prds/.../environment.md ✗ absent
reachability network control (github) 200 ✓ · console pentest01.sbops.com 000 ✗ (no route / VPN) ·
             console API token ✗ · SafeBreach MCP servers ✗ (all 4 failed to connect)
per-id check pytest -k "T_<n>_" resolves every id T-1 … T-35 to a non-empty set ✓ (T-29 = 0, by design)
```

**Selector convention.** Use `-k "T_<n>_"` **with the trailing underscore**. A bare `-k "T_1"` substring-matches
T-10 … T-19 and selects 43 tests instead of 7 — the one trap in this scheme, confirmed by probe.

## Evidence

Primary evidence command (all three unit suites, one batch covering every unit id):

```
$ SKIP_E2E_TESTS=true uv run --python 3.12 pytest \
    safebreach_mcp_studio/tests/test_scenario_simulation_counts.py \
    safebreach_mcp_studio/tests/test_scenario_blocked_entities.py \
    safebreach_mcp_studio/tests/test_scenario_statistics_contract.py -q
116 passed in 0.27s
```

Whole studio package, for regression context: `594 passed, 50 skipped in 1.80s`
(independently reproduced by `validating-test-plan`).

Per-id inclusion was verified by resolving each `T-<n>_` selector against the collected set before the batch
ran; every unit id resolves to a non-empty subset of the 116 passing tests, so each id's pass is attributable.

## Accounting

| T-\<n\> | Level | Execution | Env | Runner | Outcome | Evidence / Reason |
|------|-------|-----------|-----|--------|---------|-------------------|
| T-1 | unit | Automatic | none | uv-pytest | executed | `-k "T_1_"` → 7 passed |
| T-2 | unit | Automatic | none | uv-pytest | executed | `-k "T_2_"` → 2 passed |
| T-3 | unit | Automatic | none | uv-pytest | executed | `-k "T_3_"` → 4 passed |
| T-4 | unit | Automatic | none | uv-pytest | executed | `-k "T_4_"` → 2 passed |
| T-5 | unit | Automatic | none | uv-pytest | executed | `-k "T_5_"` → 1 passed |
| T-6 | unit | Automatic | none | uv-pytest | executed | `-k "T_6_"` → 2 passed |
| T-7 | unit | Automatic | none | uv-pytest | executed | `-k "T_7_"` → 6 passed |
| T-8 | unit | Automatic | none | uv-pytest | executed | `-k "T_8_"` → 5 passed |
| T-9 | unit | Automatic | none | uv-pytest | executed | `-k "T_9_"` → 3 passed (**authored this pass**) |
| T-10 | unit | Automatic | none | uv-pytest | executed | `-k "T_10_"` → 2 passed; RBAC case added via T-28 boundary tests |
| T-11 | unit | Automatic | none | uv-pytest | executed | `-k "T_11_"` → 3 passed |
| T-12 | unit | Automatic | none | uv-pytest | executed | `-k "T_12_"` → 3 passed (**authored this pass**) |
| T-13 | unit | Automatic | none | uv-pytest | executed | `-k "T_13_"` → 3 passed |
| T-14 | unit | Automatic | none | uv-pytest | executed | `-k "T_14_"` → 5 passed |
| T-15 | unit | Automatic | none | uv-pytest | executed | `-k "T_15_"` → 7 passed |
| T-16 | unit | Automatic | none | uv-pytest | executed | `-k "T_16_"` → 7 passed |
| T-17 | unit | Automatic | none | uv-pytest | executed | `-k "T_17_"` → 2 passed |
| T-18 | unit | Automatic | none | uv-pytest | executed | `-k "T_18_"` → 4 passed |
| T-19 | unit | Automatic | none | uv-pytest | executed | `-k "T_19_"` → 6 passed |
| T-20 | unit | Automatic | none | uv-pytest | executed | `-k "T_20_"` → 2 passed |
| T-21 | unit | Automatic | none | uv-pytest | executed | `-k "T_21_"` → 4 passed |
| T-22 | unit | Automatic | none | uv-pytest | executed | `-k "T_22_"` → 3 passed (**authored this pass**) |
| T-23 | unit | Automatic | none | uv-pytest | executed | `-k "T_23_"` → 7 passed |
| T-24 | unit | Automatic | none | uv-pytest | executed | `-k "T_24_"` → 2 passed |
| T-25 | unit | Automatic | none | uv-pytest | executed | `-k "T_25_"` → 1 passed |
| T-26 | unit | Automatic | none | uv-pytest | executed | `-k "T_26_"` → 1 passed |
| T-27 | unit | Automatic | none | uv-pytest | executed | `-k "T_27_"` → 4 passed |
| T-28 | unit | Automatic | none | uv-pytest | executed | `-k "T_28_"` → 6 passed (**authored this pass**) |
| T-29 | unit | Automatic | none | uv-pytest | unwritten-planned | File exists; this case is 0-match. Needs a payload captured from a live console — a hand-built stand-in would re-assert the shapes it exists to check |
| T-30 | unit | Automatic | none | uv-pytest | executed | `-k "T_30_"` → 13 passed (**authored this pass**) |
| T-31 | e2e | Automatic | Validate console | uv-pytest (e2e) | BLOCKED | Authored (2 cases, collect clean); skipped — no console |
| T-32 | e2e | Automatic | Validate console | uv-pytest (e2e) | BLOCKED | Authored (3 cases); skipped — no console |
| T-33 | e2e | Automatic | Validate console | uv-pytest (e2e) | BLOCKED | Authored (3 cases); skipped — no console |
| T-34 | e2e | Automatic | Validate console | uv-pytest (e2e) | BLOCKED | Authored (3 cases); skipped — no console |
| T-35 | e2e | Automatic | Validate console | uv-pytest (e2e) | BLOCKED | Authored (2 cases); skipped — no console |
| T-36 | e2e | Manual | Validate console | sb-ui:manual-ui-testing | BLOCKED | No environment.md; console unreachable; no API token |
| T-37 | e2e | Manual | Validate console | sb-ui:manual-ui-testing | BLOCKED | Same — no live console to walk the feature through |

Ledgered rows: 37 · Selected: 37 ✓ (no test dropped)

## Cumulative readiness

- Selected (Active, Passes after ≤ Final): T-1 … T-37 (all 37)
- **Green with per-id evidence: T-1 … T-28, T-30 — 29 tests**
- BLOCKED: T-31 … T-37 — 7 (all on the same cause: no live Validate console)
- Unwritten-planned: T-29 — 1
- Local-pending-ci: none · Delegated: none · Manual substitutions: none
- **Phase verdict: INCOMPLETE**

## Hand-off (delegated / BLOCKED)

- **T-31 … T-35 — BLOCKED (infra only).** The tests are now written and collect cleanly; they skip because
  `SKIP_E2E_TESTS=true` and no console is reachable. They were authored but have **never executed against a real
  console**, so they are unproven code as well as unrun tests — expect to debug them on first real run.
  **Fix:** `provision-feature-environment SAF-35508` from a VPN-connected machine, then
  `source .vscode/set_env.sh && uv run pytest -m e2e -k "T_3"`. T-34 needs an offline/disabled simulator and a
  Windows+Linux mix; T-35 needs a step blocking more than 50 attacks. Both `pytest.skip` with a message naming
  the missing precondition rather than passing vacuously.
- **T-36, T-37 — BLOCKED (infra).** Manual walkthroughs needing the same console.

## To author (unwritten-planned)

- **T-29** — the recorded real-console payload contract test. `test_scenario_statistics_contract.py` exists and
  its docstring records why this one case is absent. Capture one `plan/statistics` response (constraints on and
  off), commit it with a provenance note, and drive both shaping layers from it.

## Manual substitutions (not the planned test)

- None. No improvised probe was recorded in place of any planned test.

## Smell observations

- **The 13 new e2e tests are unproven.** They are authored from the repo's existing e2e pattern and the tools'
  documented result shape, but no assertion in them has ever seen a real payload. Field names such as
  `simulators_offered`, `blocked_attacks_by_reason` and `sample_blocked_attack_id` are taken from the plan and
  the implementation; the first real run should be treated as a debugging run, not a verification run.
- **The plan's e2e `Evidence required` still names a CI build that cannot exist** — no pipeline in this repo runs
  pytest. Worth revising via `authoring-test-plan` to name evidence that is actually producible.
- **`ruff` is still not installed**, so the PRD's stated lint gate did not run this pass either.
- The PRD's §3 Component C still claims the blocked answer "never depends on step order", broader than the
  delivered per-step-union verdict confirmed as intended at the authoring gate.

## Verdict

- **INCOMPLETE** — 29 executed, 7 BLOCKED, 1 unwritten-planned. **The feature still cannot be signed off.**
  Every remaining item traces to one of two causes: no reachable Validate console (8 tests, 7 BLOCKED + T-29's
  capture). The entire unit tier is now green with attributable per-id evidence, which it was not on the first pass.
