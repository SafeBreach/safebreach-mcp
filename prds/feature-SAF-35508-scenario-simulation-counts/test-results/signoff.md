# Scoped Sign-off — Scenario Statistics MCP Tools (SAF-35508)

> Plan: ../test-plan.md | Recorded: 2026-09-16T15:05Z | Terminal stage (Phase Final)

## Verdict

**SCOPED SIGN-OFF — not a full sign-off.**

| Tier | State |
|---|---|
| Unit tier (T-1 … T-28, T-30) | **SIGNED OFF** — 29 of 29 executed with per-id evidence |
| Real-environment tier (T-29, T-31 … T-37) | **NOT VERIFIED — waived by the owner** |

Read this document before treating SAF-35508 as verified. The feature's behaviour is well covered by tests that
run entirely against fixtures we wrote. **No part of it has ever been exercised against a live SafeBreach
console.** That is the precise boundary of what is signed off here.

## What is signed off

The unit tier, on per-id evidence, at commit `5373c1a`:

```
$ SKIP_E2E_TESTS=true uv run --python 3.12 pytest \
    safebreach_mcp_studio/tests/test_scenario_simulation_counts.py \
    safebreach_mcp_studio/tests/test_scenario_blocked_entities.py \
    safebreach_mcp_studio/tests/test_scenario_statistics_contract.py -q
116 passed in 0.27s
```

Whole studio package: `594 passed, 50 skipped in 1.80s` (independently reproduced by `validating-test-plan`).

Every plan id from T-1 to T-28 and T-30 resolves to a non-empty subset of those passing tests via
`pytest -k "T_<n>_"`. The per-test breakdown is in `phase-Final.md`.

All 25 requirements (R1 … R25) are covered by at least one test, and `validating-test-plan` returns
`RESULT: clean`.

## What is NOT verified

Eight items, all tracing to one cause — **no reachable Validate console**:

| Item | State | Why it matters |
|---|---|---|
| T-29 | unwritten | Needs a payload captured from a live console. A hand-built stand-in would re-assert the shapes it exists to catch, so it was deliberately not faked. |
| T-31 … T-35 | authored, never run | 13 e2e cases. They collect cleanly and skip. **Their assertions have never seen a real payload** — field names come from the plan and the implementation, not from observation. |
| T-36 | authored, never run | The mandatory Manual regression — that `run_scenario` / `quick_run` still behave after the shared fetch helper gained two callers. |
| T-37 | authored, never run | The Manual progression walkthrough — whether an agent can actually assemble a scenario from these two answers. |

### The specific risks this leaves open

1. **Shape mismatch.** Every fixture encodes our reading of the orchestrator source. If the live response names a
   field differently (`attackerSimulators`, `simulatorConstraints`, `constraintCatalog`), all 594 tests still pass
   while the answer goes silently empty. T-29 exists precisely to close this and is the one still unwritten.
2. **The three-state model is unconfirmed against a real orchestrator.** Blocked vs *excluded* vs ran is the
   feature's sharpest claim. A fixture can only re-assert what we already assumed; only a console with a genuinely
   offline simulator can confirm it. That is T-34.
3. **`getAllConstraints=true` has never been measured live.** One ordinary step measured 38,531 conflicts /
   11.8 MB at `false`, and `true` is strictly larger. These tools are read-only and therefore get no rate-limit
   cover, so the caps are the only cost control — and the cap behaviour on a real payload is untested (T-35).
4. **The 13 new e2e tests are themselves unproven code.** Treat their first real run as a debugging run.

## Waiver

The owner (Bari) was presented with the three options — obtain a console and complete a full sign-off, record this
scoped sign-off, or leave the plan unsigned — and chose to record the scoped sign-off, explicitly accepting the
real-environment tier as unverified.

Accepted gaps, as listed in the plan's Sign-off section:

- No CI in this repo executes pytest; the only PR gate is the Security Scan workflow.
- No `Automation-Pen-Testing-*` suite covers this surface (the automation repo has zero MCP coverage).
- Verdict-level "ran outranks blocked" is intentionally untested — confirmed as intended per-step-union behaviour.
- `getAllConstraints=true` unmeasured against a real console.
- `ruff` is not installed, so the PRD's stated lint gate did not run.

## What would convert this to a full sign-off

1. Provision a mockulator-backed Validate console — `provision-feature-environment SAF-35508` from a
   VPN-connected machine. It needs **one offline or disabled simulator** and a **Windows + Linux mix**, or T-34
   and T-35 will skip naming their missing precondition.
2. `source .vscode/set_env.sh && uv run pytest -m e2e -k "T_3"` for T-31 … T-35. Expect to debug them.
3. Capture one `plan/statistics` response (constraints on and off), commit it with a provenance note, and author
   T-29 against it.
4. Run T-36 and T-37 through `sb-ui:manual-ui-testing`.
5. Re-run `running-phase-tests --phase Final`; when every box checks, flip the plan's Status to `Signed off`.

## Artifacts

- Plan: `../test-plan.md` (Status: Reviewed — deliberately **not** `Signed off`, since a full sign-off requires
  every box and three are waived rather than satisfied)
- Run accounting: `phase-Final.md`
- Retrospection: `../../../skills_feedback/running-phase-tests/feedback_SAF-35508_phase-Final.md`
- Commits: `bc990ef` (plan), `7a06b92` (first run), `5373c1a` (remediation)
