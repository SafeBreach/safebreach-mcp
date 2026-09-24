# Sign-off — Scenario Statistics MCP Tools (SAF-35508)

> Plan: ../test-plan.md | Recorded: 2026-09-24 | Consoles: apricot-jellyfish.dev.sbops.com, pentest01.safebreach.com

## Verdict

**SIGNED OFF — 2026-09-24, on two consoles.** All 47 tests executed and green with evidence, no waivers, and
`validating-test-plan` returned `RESULT: clean` against the 47-id plan. This supersedes the 2026-09-23 sign-off, which
covered 46 tests on one console: running the real-console tier again on pentest01 found a defect apricot-jellyfish
never showed, fixed in Phase 9 with a new test (T-47).

| Tier | State |
|---|---|
| Unit (39 ids) | **All 39 executed with per-id evidence** — 174 passed in the feature files, including T-29 against a live recording and T-47's answer-size caps. |
| Real console, automatic (T-31 … T-35, T-44) | **All executed live on both consoles** — 18 passed on apricot-jellyfish; 17 passed + T-33's per-row case skipped by design on pentest01, whose fleet is over the cap. |
| Real console, manual (T-36, T-37) | **Both executed and passed on both consoles.** T-37 found a defect on each; both are fixed (Phase 8, Phase 9). |

The 2026-09-16 scoped sign-off (at `5373c1a`) is **superseded**. It rested on the owner waiving the whole
real-console tier; that tier has now run in full on two consoles, so no waiver is needed or recorded.

## What is verified

- **Unit tier**: 174 passed across the three feature files; 1,853 passed repo-wide (`-m "not e2e"`). Every id
  T-1 … T-30, T-38 … T-47 resolves to a non-empty passing subset via `-k "T_<n>_"`.
- **T-29** — both tools replayed against `plan/statistics` responses recorded verbatim from apricot-jellyfish
  (`tests/fixtures/`, with provenance). Every expectation is computed from the recording's own field names; the tool
  must still send the recorded request; renaming any field the tools read changes their answer, and a simulated
  orchestrator rename turns T-29 red.
- **Real-console tier on two consoles.** On apricot-jellyfish: 18 passed. On pentest01 at `448c25e`: 17 passed and the
  T-33 per-row case skipped because every step there offers 21 real simulators. Between them:
  - *Shape* — every field the tools read was observed in two live responses, and is pinned by T-29.
  - *Three-state model* — offline simulators reported as excluded, not blocked (T-34, T-44), on both.
  - *`getAllConstraints=true` cost* — apricot-jellyfish: ~155–162 KB / 7–8 s for the capped fixture, 493,771 bytes /
    10.8 s for its broadest step; pentest01: 159,391 bytes / 1.6 s for the fixture. All inside the 120 s timeout.
  - *The listing cap* — T-33 observed over the cap on pentest01's real 21-simulator fleet and on apricot-jellyfish's
    22 (with two mockulator sims), and up to the cap on apricot-jellyfish's real 20.
- **T-36** — `run_scenario` and `quick_run` at `evaluate=True` byte-identical to `main` on both consoles; nothing queued.
- **T-37** — the full score → why → adjust → re-score walk worked on both consoles, and the re-score matched the
  prediction exactly each time (apricot-jellyfish 336 → 84; pentest01 1,620 → 432, via the over-cap `simulator_ids`
  route). It found one defect on each console, both fixed:
  - Phase 8 (T-46): the verdict called machines useless that run in another step.
  - Phase 9 (T-47): the blocked-entities answer was unbounded — 1,294,873 characters for a 24-step scenario, one
    `schemaErrors` detail alone 1,076,267. Capped at 15 steps, 100 entries and 5 items per detail list, the same
    answer is 88,715 characters with its longest line 1,368.

Details and per-id accounting: `phase-Final.md`.

## What is NOT verified

Every planned test ran and passed. The evidence still has limits:

- **Two consoles, not every build.** Older consoles, e.g. without `constraintCatalog`, are covered by unit tests only.
- **Bounded, not small.** 88,715 characters is ~7% of the unbounded answer but still a large tool result; the caps
  (15 / 100 / 5) were chosen, not tuned against an agent's context budget.
- **After the Phase 9 fix only the blocked-entities answer was re-measured live**, not the full T-37 walk. The counts
  tool and every other step of the walk are untouched by the change.
- **pentest01 returned HTTP 500 intermittently** on `/plan/statistics` with every constraint requested — 3 tests at
  12:37–12:41Z, all passing on re-run at 12:42Z. Transient, but it is the constraint-heavy call, on a shared console.
- **No test crossed the MCP transport.** e2e calls the functions and the manual runs used the in-process tool
  manager; no MCP client talked to a running server.

## Accepted gaps (carried forward from the 2026-09-16 owner approval)

- No CI in this repo executes pytest; every tier's evidence is an executor-run command and its output.
- No `Automation-Pen-Testing-*` suite covers this surface.
- `ruff` is not installed, so the PRD's stated lint gate did not run.

Dropped from that list because they no longer hold: "`getAllConstraints=true` unmeasured" (measured above) and
"verdict-level precedence deliberately untested" (Phase 8 added a scenario-wide count beside the unchanged union,
pinned by T-46).

## Also outstanding, outside this test record

- PRD §12 code review is `⏳` for every phase. Test sign-off does not cover it.

## Artifacts

- Plan: `../test-plan.md` · Run accounting: `phase-Final.md`
- Commits: `6108673` (e2e fixes after the first live run), `d9ffe6d` (T-35 live fixture), `6bbdf1c` (verdict fix,
  Phase 8), `00275c0` (T-29), `7c1532c` (T-33), `2ba1b22` (first sign-off), `448c25e` (Yossi's `quick_run` e2e fix,
  the head run on pentest01), `e5edacb` (Phase 9)
- Recorded fixtures: `safebreach_mcp_studio/tests/fixtures/plan_statistics_{counts,blocked}.json`
