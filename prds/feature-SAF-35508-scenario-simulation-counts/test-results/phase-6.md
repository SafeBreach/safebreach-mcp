# Test Results — Phase 6 (SAF-35508)

> Plan: ../test-plan.md | Run: 2026-09-17 | Mode: run

## Preflight (Step 0)

```
repo-root: .../.claude/worktrees/SAF-35508-scenario-simulation-counts — cwd matches ✓
toolchain: uv present ✓ (0.9.25) · uv sync ✓ (49 resolved / 46 audited) ·
           standalone-Python repo (pyproject.toml + uv.lock, no package.json) → uv-pytest mode ✓
environment.md: absent ✗ — no Validate console provisioned
```

**Real-env auto-provisioning deliberately NOT performed.** Step 0's gate would auto-provision, since all six
unsatisfied real-env tests are `Execution: Automatic`. It was withheld: standing up a Validate console is ongoing
cloud spend that the owner has already explicitly waived for this tier (`signoff.md`, 2026-09-16), and it is not an
action to take unattended on the runner's own initiative. The provisioning command is in the hand-off below.

## Selected set (cumulative, `Status: Active` and `Passes after ≤ 6`)

40 tests — T-1 … T-28, T-31 … T-35, T-38 … T-44.
`Final` tests T-29, T-30, T-36, T-37 are **not** selected: `Final` is a terminal stage strictly after every
numbered phase.

## Accounting

| T-\<n\> | Level | Execution | Env | Runner (intended) | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|-------------------|---------|-------------------|
| T-1 … T-28 (28 tests) | unit | Automatic | none | source-repo uv-pytest | executed | `uv run --python 3.12 pytest safebreach_mcp_studio/tests -m "not e2e"` → `615 passed, 52 deselected in 1.33s`; every id verified present in the `-v` output |
| T-38 | unit | Automatic | none | source-repo uv-pytest | executed | same run; `TestSimulatorScoping` (3 cases) |
| T-39 | unit | Automatic | none | source-repo uv-pytest | executed | same run; `TestScopingChangesOnlyTheListing` (3 cases) |
| T-40 | unit | Automatic | none | source-repo uv-pytest | executed | same run; `TestExcludedSimulatorShortCircuit` (6 cases) |
| T-41 | unit | Automatic | none | source-repo uv-pytest | executed | same run; `TestNamedSimulatorAnswers` (3 cases) |
| T-42 | unit | Automatic | none | source-repo uv-pytest | executed | same run; `TestScopedCapAndComposition` (3 cases) |
| T-43 | unit | Automatic | none | source-repo uv-pytest | executed | same run; `TestScopedCatalog` (3 cases) |
| T-31 | e2e | Automatic | Validate console | run-validate-attack | BLOCKED | no reachable console and no `environment.md`; never executed since authoring |
| T-32 | e2e | Automatic | Validate console | run-validate-attack | BLOCKED | as T-31 |
| T-33 | e2e | Automatic | Validate console | run-validate-attack | BLOCKED | as T-31 |
| T-34 | e2e | Automatic | Validate console | run-validate-attack | BLOCKED | as T-31 |
| T-35 | e2e | Automatic | Validate console | run-validate-attack | BLOCKED | as T-31 |
| T-44 | e2e | Automatic | Validate console | run-validate-attack | BLOCKED | as T-31; authored this phase, never executed |

Ledger rows: 40 selected / 40 accounted — no test dropped.

**Per-selected-id inclusion check.** Every selected unit id was confirmed present in the run's `-v` output, not
inferred from the pass count. The first extraction reported T-5 missing; that was a defect in the *extraction*
(`T-4` and `T-5` share one function, `test_T_4_T_5_parameters_are_fixed_and_booleans_are_json_spelled`, and the
regex captured only the leading id), not in the suite. Re-extracting every embedded `T_<n>_` occurrence confirmed
all 34 selected unit ids ran.

## Cumulative readiness

- **Selected** (Active, `Passes after ≤ 6`): T-1 … T-28, T-31 … T-35, T-38 … T-44 (40)
- **Green**: T-1 … T-28, T-38 … T-43 (34)
- **BLOCKED**: T-31, T-32, T-33, T-34, T-35, T-44 (6) — no Validate console
- **Unwritten-planned**: none in this phase's set (T-29 is unwritten but is `Final`, so not selected)
- **Local-pending-ci**: none — this repo has no CI that executes pytest, so no test's `Evidence required` names a
  build that could arrive. The local run is the only evidence that exists (see Smell).
- **Plan-drift**: none
- **Phase verdict**: **INCOMPLETE** — the unit tier is green with per-id evidence; the six real-env tests are open
  BLOCKED.

## Evidence

- T-1 … T-28, T-38 … T-43: executed — `uv run --python 3.12 pytest safebreach_mcp_studio/tests -m "not e2e"` →
  `615 passed, 52 deselected in 1.33s`; per-id presence verified against the `-v` output.
- Mutation evidence for the Phase 6 tests (beyond the green run): disabling the excluded short-circuit flips T-40
  red (`KeyError: 'blocked_attacks_withheld'`); disabling the per-simulator blocker filter flips T-38 red
  (`['incompatible_os', 'port_in_use'] != ['incompatible_os']`); disabling the tally filter flips T-43 red
  (`'port_in_use' not in {...}`). The T-43 check initially did **not** move — its fixture was tightened until it
  did, and the mutation re-applied to confirm.

## Hand-off (delegated / BLOCKED)

- T-31 … T-35, T-44: BLOCKED — no Validate console environment. To unblock, provision deliberately:
  `Skill("sb-dev-base:provision-feature-environment", "SAF-35508")`, then re-run
  `--prd-folder prds/feature-SAF-35508-scenario-simulation-counts --phase 6`.
  T-44 additionally needs the console to hold **at least one offline/disabled simulator**, or its second case
  skips naming that missing precondition rather than passing vacuously.

## To author (unwritten-planned)

- none in this phase's set. (T-29 remains unwritten but is `Passes after: Final`.)

## Manual substitutions (not the planned test)

- none. No improvised probe was recorded in place of a planned test.

## Plan drift (spec ≠ code — plan owner reconciles)

- none.

## Smell observations

- **The e2e suite had five assertions that never matched the emitted shape** and could not have passed on first
  real run: `blocked_attack_count`, `blocked_attacks_by_reason`, `catalog_available`, `group['reason']` and
  `group['simulator_id']`. A sixth, `sample_blocked_attack_id`, does not exist at all and — read via
  `.get(...) or ''` — made its assertion **unfailable**. All were repaired this phase; the last became an explicit
  skip, because a capped step exposes no attack id by design. These belong to T-34/T-35 (frozen Phases 4-5), so
  the repair is a deliberate, owner-approved scope expansion, recorded here rather than absorbed silently.
- **No CI executes this repo's tests.** Only `release.yml` and `security-scan.yml` exist. No test's
  `Evidence required` can ever be satisfied by a build number, so `local-pending-ci` is structurally unreachable
  here and the local run is the only evidence that will ever exist. Per the guardrail this is surfaced rather than
  held as a pending build: the plan's `Evidence required` wording should be revised via `authoring-test-plan` to
  name evidence that actually exists.
- **The real-env tier has now been carried as BLOCKED across three consecutive sign-offs.** Six Automatic e2e
  tests have never run against anything. T-44 in particular is the only test that can confirm the offline-node
  seeding claim every T-40 fixture merely encodes — so the highest-risk behaviour in Phase 6 rests on an
  unverified premise about orchestrator behaviour.

## Verdict

- **INCOMPLETE** — 34 of 40 green with full per-id evidence and mutation-verified discrimination; 6 real-env tests
  open BLOCKED for want of a console. No manual substitutions, no plan drift, nothing silently skipped.
