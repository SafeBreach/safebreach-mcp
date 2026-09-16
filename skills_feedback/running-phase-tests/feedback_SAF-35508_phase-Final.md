# SAF-35508 · phase Final · 2026-09-16

Subject: test-runner skills/KBs for SAF-35508 phase Final (running-phase-tests + authoring-test-plan contract + uv-pytest dispatch)
Evidence: prds/feature-SAF-35508-scenario-simulation-counts/test-results/phase-Final.md,
prds/feature-SAF-35508-scenario-simulation-counts/test-plan.md, ambient run context
Plugin: sb-dev-base@2.3.156

## What worked well

- **Step 0 preflight earned its place.** Every blocker in this run was surfaced before a single test was
  dispatched: uv toolchain, both absent `planned:` files, the missing `environment.md`, console unreachability,
  and the per-id addressability failure. Nothing was discovered lazily mid-pass.
- **uv-pytest dispatch detection was correct and frictionless.** `pyproject.toml` + `uv.lock` with no
  `package.json` → uv-pytest, exactly as the SAF-33511 note describes. The Node-centric default did not leak into
  a Python repo.
- **The `planned:`-marker filesystem rule resolved cleanly.** Both planned paths were absent in a resolvable repo,
  giving an unambiguous `unwritten-planned` for 7 tests — no guessing, no stale-marker ambiguity.
- **The evidence-provenance guardrails did the single most valuable thing in this run: they prevented a false
  green.** The natural shortcut here is to record `88 passed` as 30 passing tests. The per-selected-id inclusion
  check forbade it, and the resulting verdict is honest.
- **The three-skill chain held end to end.** `authoring-test-plan` predicted the title-prefix gap as accepted gap
  #2, `validating-test-plan` passed the plan as internally consistent, and `running-phase-tests` then demonstrated
  the predicted gap concretely. The prediction and the observation agreed.

## What could improve

**1. The automation title contract is unsatisfiable for a retrospectively-authored plan, and nothing bridges it.**
(Rating: moderate)

`authoring-test-plan` explicitly supports authoring a plan over an already-implemented feature, and the template's
automation title contract requires every automated test's own title to begin with `T-<n>: `. Those two facts are in
direct tension: when the tests were written months before the plan, their titles cannot carry ids that did not exist
yet, so the author can only record an accepted gap. `running-phase-tests` Step 4 then converts that accepted gap into
28 BLOCKED rows.

*Impact:* the entire unit tier — 28 of 37 tests — was unaccountable on the first execution, and the phase verdict is
INCOMPLETE for a reason unrelated to the feature's correctness. As the contract stands, a retrospective test plan can
never reach PASS on its first run, no matter how good the code or the plan. The cost in this run was a full pass that
produced zero per-id evidence despite a green suite.

*Fix (surgical, no capability loss):* when `authoring-test-plan` maps a `T-<n>` onto an **existing** test case, let
`Automation lives in:` name the concrete case (`<file>::<Class>::<method>`) rather than only the file. The runner can
then select by pytest node-id, which is mechanical and needs no title rewrite. Keep the `T-<n>:` prefix contract for
newly-authored tests, where it costs nothing.

**2. The ledger has no outcome for "suite green, id unattributed."** (Rating: moderate)

The outcome vocabulary — `executed` / `remediated-then-executed` / `BLOCKED` / `unwritten-planned` /
`manual-substitution` / `local-pending-ci` / `delegated` — has no slot for a test whose behaviour demonstrably passes
but whose per-id attribution is absent. I recorded `BLOCKED`, which the skill defines as an infra/runner gap meaning
"fix infra". That is the closest available fit, but it misdescribes the state.

*Impact:* the results file required explicit prose in three places to stop a reader concluding the feature is broken.
A reviewer scanning the Outcome column sees 30 BLOCKED against a feature whose 88 tests pass in 0.2s — the artifact
actively misleads at a glance, which is the opposite of what a sign-off document should do.

*Fix:* add an `unattributed-green` outcome (the suite ran green; per-id evidence is missing), ranked below `executed`
and above `BLOCKED`, and let it carry the suite-level evidence ref. It keeps the guardrail (still not a PASS) while
describing reality.

**3. `--phase Final` is a documented concept but an undocumented input.** (Rating: minor)

Step 2 defines `Final` semantics precisely, but the Inputs section describes `--phase <N>` as "the PRD phase to run",
implying a number. I passed `--phase Final` on inference from Step 2 rather than from the input contract.

## Blockers & gaps

None. The run proceeded to a complete, fully-accounted verdict without any manual workaround. Every item above is
friction or vocabulary, not a hard stop.

## Prioritized improvements

1. **(moderate)** `authoring-test-plan` — allow `Automation lives in:` to name an existing test case by node-id, so a
   retrospective plan has a mechanical selection path instead of an unsatisfiable title contract.
2. **(moderate)** `running-phase-tests` Step 4 — add an `unattributed-green` outcome so a green-but-unattributed test
   is not reported with the same token as a broken environment.
3. **(minor)** `running-phase-tests` Inputs — document that `--phase` accepts `Final` / `last`.

## Out-of-band observations (effectiveness-orthogonal)

- **Documentation-vs-reality drift in the repo under test:** `ruff` is named as the quality gate by both the PRD and
  `CLAUDE.md`, but it is not installed (`uv run ruff` fails to spawn; absent from `uv.lock`). This did not impede the
  run — the runner does not invoke lint — but any reader trusting those documents would believe a gate ran that
  cannot.
- **The plan names evidence that structurally cannot exist:** the e2e tier's `Evidence required` cites a CI build,
  while the repo has no pipeline that runs pytest at all. Already recorded as a Smell in the phase results; noted here
  because it is a plan-authoring pattern worth catching at authoring time rather than at execution time.
- No secrets were encountered, written, or transited. No console credentials were present in the environment.

## Materiality

`max_rating = moderate` (two moderate items). No `--channel` was supplied, so the Slack post is skipped by argument,
not by materiality. The durable record is the artifact.
