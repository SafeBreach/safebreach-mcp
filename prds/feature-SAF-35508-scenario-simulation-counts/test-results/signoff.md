# Sign-off — Scenario Statistics MCP Tools (SAF-35508)

> Plan: ../test-plan.md | Recorded: 2026-09-23T15:50Z | Console: apricot-jellyfish.dev.sbops.com

## Verdict

**ALL 46 TESTS EXECUTED AND GREEN — no test gaps, no waivers.** The plan is not yet flipped to `Signed off` only
because its validator gate (`validating-test-plan`) has not been re-run against the 46-id plan; that is a plan-level
check, not a test.

| Tier | State |
|---|---|
| Unit (38 ids) | **All 38 executed with per-id evidence** — 168 passed, including T-29 against a live recording. |
| Real console, automatic (T-31 … T-35, T-44) | **All executed live** — 18 passed; T-33 observed on both sides of the cap. |
| Real console, manual (T-36, T-37) | **Both executed and passed.** T-37 found a defect, since fixed. |

The 2026-09-16 scoped sign-off (at `5373c1a`) is **superseded**. It rested on the owner waiving the whole
real-console tier; that tier has now run in full, so no waiver is needed or recorded.

## What is verified

- **Unit tier**: `168 passed` across the three feature files; `1847 passed` repo-wide (`-m "not e2e"`). Every id
  T-1 … T-30, T-38 … T-46 resolves to a non-empty passing subset via `-k "T_<n>_"`.
- **T-29** — both tools replayed against `plan/statistics` responses recorded verbatim from apricot-jellyfish
  (`tests/fixtures/`, with provenance). Every expectation is computed from the recording's own field names; the tool
  must still send the recorded request; renaming any field the tools read changes their answer, and a simulated
  orchestrator rename turns T-29 red.
- **Real-console tier** on apricot-jellyfish — `18 passed`. It closed every risk the previous record left open:
  - *Shape mismatch* — every field the tools read was observed in a live response, and is now pinned by T-29.
  - *Three-state model* — 34 offline simulators reported as excluded, not blocked (T-34, T-44).
  - *`getAllConstraints=true` unmeasured* — measured: ~155–162 KB / 7–8 s for the capped fixture; the broadest step
    this fleet allows measured 493,771 bytes / 10.8 s, 2.2× the `false` payload, inside the 120 s timeout.
  - *The listing cap* — T-33 observed live on a 22-simulator fleet (two mockulator sims added, then removed) and on
    the restored 20: breakdown dropped only past 20, the count kept, both routes back named, named ids answered in
    both roles on both sides.
- **T-36** — `run_scenario` and `quick_run` at `evaluate=True` byte-identical to `main`; nothing queued.
- **T-37** — the full score → why → adjust → re-score walk worked; the re-score moved exactly as predicted (336 → 84).

Details and per-id accounting: `phase-Final.md`.

## What is NOT verified

- No test. The only open box is the plan's validator re-run (below).

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

1. Re-run `validating-test-plan` and record `RESULT: clean`.
2. When every box in the plan's Sign-off section is checked, flip the plan's Status to `Signed off`.

## Artifacts

- Plan: `../test-plan.md` · Run accounting: `phase-Final.md`
- Commits: `6108673` (e2e fixes after the first live run), `d9ffe6d` (T-35 live fixture), `6bbdf1c` (verdict fix,
  Phase 8), `aaf725c` (PRD SHA), `cf0037e` (first live-run record), `00275c0` (T-29), and the T-33 commit that
  follows it
- Recorded fixtures: `safebreach_mcp_studio/tests/fixtures/plan_statistics_{counts,blocked}.json`
