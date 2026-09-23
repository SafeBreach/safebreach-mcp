# Sign-off — Scenario Statistics MCP Tools (SAF-35508)

> Plan: ../test-plan.md | Recorded: 2026-09-23T15:10Z | Commit: `aaf725c` | Console: apricot-jellyfish.dev.sbops.com

## Verdict

**NOT SIGNED OFF — two items open, each awaiting either the work or an owner waiver.**

| Tier | State |
|---|---|
| Unit (37 ids) | **36 of 37 executed with per-id evidence** — 152 passed. T-29 unwritten. |
| Real console, automatic (T-31 … T-35, T-44) | **All executed live** — 18 passed. T-33 only in part. |
| Real console, manual (T-36, T-37) | **Both executed and passed.** T-37 found a defect, since fixed. |

The 2026-09-16 scoped sign-off (at `5373c1a`) is **superseded**. It rested on the owner waiving the whole
real-console tier; that tier has now run, so the waiver no longer describes anything, and it never covered Phases 6–8.
It stays in git history as a record, not as evidence.

## What is verified

- **Unit tier** at `aaf725c`: `152 passed` across the three feature files; `1831 passed` repo-wide (`-m "not e2e"`).
  Every id T-1 … T-28, T-30, T-38 … T-46 resolves to a non-empty passing subset via `-k "T_<n>_"`.
- **Real-console tier** on apricot-jellyfish, 15:05Z → 15:08Z: `18 passed`. This closes three of the previous
  record's four open risks:
  - *Shape mismatch* — every field the tools read was observed in a live response.
  - *Three-state model* — 34 offline simulators reported as excluded, not blocked (T-34, T-44).
  - *`getAllConstraints=true` unmeasured* — now measured: 154,744 bytes / 7.0 s for the capped fixture; the broadest
    step this fleet allows (78 attacks × every connected simulator) measured 493,771 bytes / 10.8 s, 2.2× the
    `false` payload, inside the 120 s timeout.
- **T-36** — `run_scenario` and `quick_run` at `evaluate=True` byte-identical to `main`; nothing queued.
- **T-37** — the full score → why → adjust → re-score walk worked; the re-score moved exactly as predicted (336 → 84).

Details and per-id accounting: `phase-Final.md`.

## What is NOT verified — the two open items

| Item | State | To close it |
|---|---|---|
| **T-29** | unwritten | The real-payload contract test. Its old blocker (no console) is gone: capture one `plan/statistics` response from apricot-jellyfish, commit it with provenance, and drive both shaping layers from it. Work only — or waive. |
| **T-33, over-cap half** | unobserved | Every step on apricot-jellyfish offers exactly 20 simulators, so the path that drops the breakdown past 20 never ran live. The unit tier covers it (T-15). Needs a 21+ simulator fleet (the plan's mockulator step) — or waive. |

## Accepted gaps (carried forward from the 2026-09-16 owner approval)

- No CI in this repo executes pytest; every tier's evidence is an executor-run command and its output.
- No `Automation-Pen-Testing-*` suite covers this surface.
- `ruff` is not installed, so the PRD's stated lint gate did not run.

Dropped from that list because they no longer hold: "`getAllConstraints=true` unmeasured" (measured above) and
"verdict-level precedence deliberately untested" (Phase 8 added a scenario-wide count beside the unchanged union,
pinned by T-46).

## Also outstanding, outside this test record

- `validating-test-plan` has not been re-run against the 46-id plan.
- PRD §12 code review is `⏳` for every phase.

## What converts this to a full sign-off

1. Author T-29 against a captured apricot-jellyfish payload — or the owner waives it.
2. Observe T-33 on a 21+ simulator fleet — or the owner waives its over-cap half.
3. Re-run `validating-test-plan` and record `RESULT: clean`.
4. When every box in the plan's Sign-off section is checked, flip the plan's Status to `Signed off`.

## Artifacts

- Plan: `../test-plan.md` · Run accounting: `phase-Final.md`
- Commits: `6108673` (e2e fixes after the first live run), `d9ffe6d` (T-35 live fixture), `6bbdf1c` (verdict fix,
  Phase 8), `aaf725c` (PRD SHA)
