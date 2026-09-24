# Sign-off — Scenario Statistics MCP Tools (SAF-35508)

> Plan: ../test-plan.md | Recorded: 2026-09-24 | Code: `9e06c1b` (Phase 10) | Console: pentest01.safebreach.com

## Verdict

**SIGNED OFF — 2026-09-24, at Phase 10.** All 47 active tests (T-2 removed) executed and green with evidence, no
waivers, and `validating-test-plan` returned `RESULT: clean` against the 48-id plan. This supersedes the earlier
2026-09-24 two-console sign-off, which covered the ad-hoc `scenario` input that Phase 10 removed.

| Tier | State |
|---|---|
| Unit (39 ids) | **All executed with per-id evidence** — 176 passed in the feature files, including T-29 re-recorded with the id form and T-48 (no ad-hoc input anywhere the model looks). |
| Real console, automatic (T-31 … T-35, T-44) | **Executed live on pentest01 against temporary saved plans** — 15 passed; T-33's per-row case skipped because every step offers 21 simulators (the row case is pinned by T-29's under-cap recording). |
| Real console, manual (T-36, T-37) | **Both executed and passed on pentest01.** T-36 identical to `main`; T-37's saved-plan walk (save, score, why, `PUT` edit, re-score, delete) completed. |

## What is verified

- **The input contract** — both tools take exactly one of `scenario_id` (numeric) or `test_id`; an OOB UUID is refused
  locally with a route that exists; a `scenario` argument is rejected by the function layer and the registered tool
  before any request; neither schema nor description offers it (T-1, T-13, T-32, T-48).
- **T-29** — both tools replayed against `plan/statistics` responses recorded verbatim on pentest01 from a temporary
  saved plan (request `{name, id}`), under the listing cap and with 2 disconnected simulators in the constraints, so the
  breakdown rows and the excluded state are both in the recording.
- **Real-console tier** — the module saves an OOB scenario's steps as a temporary plan and scores it by id; T-35 builds
  its over-cap step as a saved plan (57 attacks, 170,464 bytes / 1.7 s with every constraint requested). No test plan
  was left on the console.
- **T-36** — `run_scenario` / `quick_run` at `evaluate=True` identical to `main` (`6f60db8`) run back to back; nothing
  queued. A first pair differed only because the fleet changed between runs, shown by `main` differing from itself.
- **T-37** — an agent holding only a saved plan's id can score it, learn why three machines contribute nothing, edit
  the plan and re-score it by the same id; hints route between the two tools and never to an ad-hoc body.
- Unit repo context: 1,725 passed across the CLAUDE.md suites (`-m "not e2e"`).

Details and per-id accounting: `phase-Final.md`.

## What is NOT verified

- **One console at Phase 10.** apricot-jellyfish evidence predates the removal and covered the body form; the id form
  ran only on pentest01. Older consoles (e.g. without `constraintCatalog`) are covered by unit tests only.
- **T-33 under the cap was not observed live at Phase 10** — pentest01 offers 21. It is pinned by T-29's recording
  (5 offered) and was observed live on apricot-jellyfish before Phase 10.
- **Early termination is no longer detectable** by design (owner-accepted deviation from JIRA AC 5, R7); an unscored
  step still reads *not computed*.
- **No test crossed the MCP transport.** e2e calls the functions and T-48 the in-process tool manager.
- **4 pre-existing failures in `tests/test_auth_concurrency.py`** when run after another suite (a leaked auth context);
  reproduced with a suite this branch does not touch, and outside this change.

## Accepted gaps (carried forward from the 2026-09-16 owner approval)

- No CI in this repo executes pytest; every tier's evidence is an executor-run command and its output.
- No `Automation-Pen-Testing-*` suite covers this surface.
- `ruff` is not installed, so the PRD's stated lint gate did not run.

## Owner-accepted deviations (2026-09-24)

- R1 / JIRA AC 1 — the ad-hoc plan body is removed; OOB scenarios must be saved as a custom plan or run first.
- R7 / JIRA AC 5 — a reply shorter than the plan is no longer reported.

## Also outstanding, outside this test record

- PRD §12 code review is `⏳` for every phase. Test sign-off does not cover it.
- Console-side, for the config team: a plans `PUT` carrying `createdAt` / `updatedAt` returns an empty 400, and a
  rejected `PUT` (sbcode 709) left a plan with no steps.

## Artifacts

- Plan: `../test-plan.md` · Run accounting: `phase-Final.md`
- Commits: `c5dcaed` (Phase 10 PRD + plan), `9e06c1b` (Phase 10 code, tests, fixtures, docs); earlier: `6bbdf1c`
  (Phase 8), `e5edacb` (Phase 9)
- Recorded fixtures: `safebreach_mcp_studio/tests/fixtures/plan_statistics_{counts,blocked}.json`
