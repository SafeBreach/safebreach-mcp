# Test Results — Phase Final (SAF-35508)

> Plan: ../test-plan.md | Runs: pass 3 2026-09-23T15:05Z on apricot-jellyfish.dev.sbops.com (account 3475543660);
> pass 4 2026-09-24T11:46Z on pentest01.safebreach.com (account 3471166703) | Mode: run

## Run history

| Pass | Result |
|---|---|
| 1 (2026-09-16 14:05Z) | INCOMPLETE — 30 BLOCKED, 7 unwritten-planned, **0 green by id**. No test carried a `T-<n>:` title prefix. |
| 2 (2026-09-16 14:50Z) | INCOMPLETE — 29 executed with per-id evidence, 7 BLOCKED (no console), 1 unwritten-planned. Recorded a scoped sign-off; see git history of this file at `5373c1a`. |
| 4 (2026-09-24 11:46Z → 12:42Z, pentest01) | **COMPLETE — 47 of 47 executed with evidence** on a second console at `448c25e` plus the Phase 9 fix. See "Second console — pentest01" below. T-37 found an unbounded blocked-entities answer; Phase 9 (T-47) fixed it. |
| 3 (2026-09-23 15:05Z → 15:45Z) | **COMPLETE — 46 of 46 executed with evidence** (38 unit, 6 e2e automatic, 2 manual). Real-console tier run for the first time; T-29 authored from a live recording at 15:15Z; T-33 observed on both sides of the cap by growing the fleet to 22 with two mockulator simulators (15:32Z) and restoring it to 20 (15:41Z). |

Between passes 2 and 3: Phases 6–8 landed (T-38 … T-46 added), the first live run surfaced three defective e2e tests
(fixed in `6108673`), T-35's fixture became buildable (`d9ffe6d`), and T-37 surfaced a product defect in the verdict
sentence (fixed in `6bbdf1c`, Phase 8, T-46).

## Preflight

```
toolchain    uv present ✓ · uv run --python 3.12 ✓
repo-root    …/worktrees/SAF-35508-scenario-simulation-counts — cwd matches ✓
dispatch     standalone-Python (pyproject.toml + uv.lock) → uv-pytest mode ✓
environment  prds/.../environment.md ✗ absent — console supplied by the owner (apricot-jellyfish.dev.sbops.com)
reachability control (google) 200 ✓ · console 302 ✓ · API token ✓ (created via sb-support:apitoken-creator, kept out of repo)
             SafeBreach MCP servers ✗ (failed to connect) — not needed: tests call the functions and tool manager directly
per-id check every id T-1 … T-46 resolves to a non-empty set via -k "T_<n>_", except T-36 / T-37 (manual)
```

**Selector convention.** Use `-k "T_<n>_"` with the trailing underscore; a bare `-k "T_1"` over-selects T-10 … T-19.

## Evidence

Unit tier, one batch covering every unit id:

```
$ SKIP_E2E_TESTS=true uv run --python 3.12 pytest \
    safebreach_mcp_studio/tests/test_scenario_simulation_counts.py \
    safebreach_mcp_studio/tests/test_scenario_blocked_entities.py \
    safebreach_mcp_studio/tests/test_scenario_statistics_contract.py -v
168 passed in 0.39s
```

That is 152 at `aaf725c` plus T-29's 16 cases, authored this pass. Whole repo, for regression context:
`1847 passed, 171 deselected` (`-m "not e2e"`, all six server packages).

Real-console tier, run 15:05Z → 15:08Z:

```
$ E2E_CONSOLE=apricot-jellyfish SKIP_E2E_TESTS=false \
    uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_e2e_scenario_statistics.py -m e2e -v
18 passed in 177.46s
```

T-33 across the cap — the same command on two fleet sizes. The console's own fleet offers exactly 20, so the over-cap
side was reached by bringing up the on-box mockulator (`sb-dev-base:mockulator-connect`, image `mockulator:latest`
v2.452.0) and adding two connected sims (`saf35508-t33-mock-win`, `saf35508-t33-mock-linux`); both were deleted and the
container removed afterwards, leaving the console as found.

```
15:32Z → 15:40Z  fleet 22  → 17 passed, 1 skipped   T-33 observed: step 0–3 offer 22 — over the cap
                                                    (skip: the per-row case, which has no rows past the cap)
15:41Z → 15:45Z  fleet 20  → 18 passed              T-33 observed: step 0–3 offer 20 — up to the cap
```

## Accounting

| T-\<n\> | Level | Execution | Env | Runner | Outcome | Evidence / Reason |
|------|-------|-----------|-----|--------|---------|-------------------|
| T-1 | unit | Automatic | none | uv-pytest | executed | `-k "T_1_"` → 7 passed |
| T-2 | unit | Automatic | none | uv-pytest | executed | 2 passed |
| T-3 | unit | Automatic | none | uv-pytest | executed | 4 passed |
| T-4 | unit | Automatic | none | uv-pytest | executed | 2 passed |
| T-5 | unit | Automatic | none | uv-pytest | executed | 1 passed |
| T-6 | unit | Automatic | none | uv-pytest | executed | 2 passed |
| T-7 | unit | Automatic | none | uv-pytest | executed | 6 passed |
| T-8 | unit | Automatic | none | uv-pytest | executed | 5 passed |
| T-9 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-10 | unit | Automatic | none | uv-pytest | executed | 2 passed |
| T-11 | unit | Automatic | none | uv-pytest | executed | 5 passed (adds no-duplicate-payload and object-schema cases, `9e15ed0`) |
| T-12 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-13 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-14 | unit | Automatic | none | uv-pytest | executed | 7 passed (adds per-role note cases, `9e15ed0`) |
| T-15 | unit | Automatic | none | uv-pytest | executed | 7 passed; plan Expected aligned to the two-route cap message this pass |
| T-16 | unit | Automatic | none | uv-pytest | executed | 7 passed |
| T-17 | unit | Automatic | none | uv-pytest | executed | 2 passed |
| T-18 | unit | Automatic | none | uv-pytest | executed | 4 passed |
| T-19 | unit | Automatic | none | uv-pytest | executed | 6 passed |
| T-20 | unit | Automatic | none | uv-pytest | executed | 2 passed |
| T-21 | unit | Automatic | none | uv-pytest | executed | 4 passed |
| T-22 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-23 | unit | Automatic | none | uv-pytest | executed | 7 passed |
| T-24 | unit | Automatic | none | uv-pytest | executed | 2 passed |
| T-25 | unit | Automatic | none | uv-pytest | executed | 1 passed |
| T-26 | unit | Automatic | none | uv-pytest | executed | 1 passed |
| T-27 | unit | Automatic | none | uv-pytest | executed | 4 passed |
| T-28 | unit | Automatic | none | uv-pytest | executed | 6 passed |
| T-29 | unit | Automatic | none | uv-pytest | executed | `-k "T_29_"` → 16 passed (**authored this pass**, from responses recorded verbatim on apricot-jellyfish 2026-09-23T15:15Z; a simulated rename of `attackerSimulators`, `simulationCount`, `moves` or `simulatorConstraints` turns it red) |
| T-30 | unit | Automatic | none | uv-pytest | executed | 13 passed |
| T-31 | e2e | Automatic | Validate console | uv-pytest (e2e) | executed | 2 passed live |
| T-32 | e2e | Automatic | Validate console | uv-pytest (e2e) | executed | 3 passed live |
| T-33 | e2e | Automatic | Validate console | uv-pytest (e2e) | executed | **Both sides of the cap, live.** 22 simulators (fleet + 2 mockulator sims, 15:32Z): every step over the cap — breakdown dropped, count kept, both routes named, named ids answered in both roles; the per-row case skips by design. 20 simulators (mocks removed, 15:41Z): every step up to the cap — breakdown present, every row carries both roles, named ids answered. 3 passed in the second run |
| T-34 | e2e | Automatic | Validate console | uv-pytest (e2e) | executed | 3 passed live (offline simulators present: 34 excluded) |
| T-35 | e2e | Automatic | Validate console | uv-pytest (e2e) | executed | 5 passed live, from both an unsaved body and a saved `scenario_id` (built fixture: 78 exfiltration attacks, one zero-target simulator; plan created and deleted). Payload 154,744 bytes / 7.0 s |
| T-36 | e2e | Manual | Validate console | manual (executor) | executed | See Manual evidence — byte-identical to `main` |
| T-37 | e2e | Manual | Validate console | manual (executor) | executed | See Manual evidence — criteria met; one defect found and fixed |
| T-38 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-39 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-40 | unit | Automatic | none | uv-pytest | executed | 6 passed |
| T-41 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-42 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-43 | unit | Automatic | none | uv-pytest | executed | 3 passed |
| T-44 | e2e | Automatic | Validate console | uv-pytest (e2e) | executed | 2 passed live (scoped to `1edc7d68`; lists attacks 10458 and 10459, which ran elsewhere) |
| T-45 | unit | Automatic | none | uv-pytest | executed | 5 passed |
| T-46 | unit | Automatic | none | uv-pytest | executed | 6 passed (authored this pass, Phase 8) |
| T-47 | unit | Automatic | none | uv-pytest | executed | 6 passed (authored in pass 4, Phase 9); live 24-step answer 1,294,873 → 88,715 characters |

Ledgered rows: 46 · Selected: 46 ✓ (no test dropped)

## Manual evidence

**T-36 — neighbouring tools unchanged.** Branch at `9e15ed0` against a clean `git archive main` export (`1b6f63f`),
same console, same inputs; each run printed the module path it imported to prove which tree ran.

| Call | Input | Branch | `main` |
|---|---|---|---|
| `run_scenario(evaluate=True)` | `c499f461-7766-4306-90b0-4e4a5e85c4a7` (5 steps, 74,437 predicted simulations, constraint summaries on 3 steps) | 10,486 chars | **byte-identical** |
| `quick_run(evaluate=True, all_connected=True)` | attacks 10458, 10459 → 336 predicted | 310 chars | **byte-identical** |
| `run_scenario(evaluate=True)` (first, weaker pick) | `00b979b5-…` (0 predicted) | 2,816 chars | byte-identical |

The first ten tests in execution history were identical before and after every call: nothing was queued. Later
commits (`6108673` … `aaf725c`) change no path these two tools execute. **Judgement: PASS.**

**T-37 — an agent can assemble a scenario from the two answers.** UNC1069 (4 steps) held as an unsaved body.

1. `get_scenario_simulation_counts` → 374 simulations. Step 0: seven machines produce in both roles (36 / 48), two
   only as attacker (`82fc6580`, `8e7e9433`: 42 / 0), eleven at zero. Each role column summed to its step total in all
   four steps.
2. `get_scenario_blocked_entities` → every zero explained by a cited code with validator detail (e.g. `incompatible_os`,
   actual LINUX, required WINDOWS); the console's catalog relayed verbatim for all 12 cited codes. The hints route
   between the two tools, not in a circle.
3. Adjusted step 0 to attack from the two attacker-only machines and target the seven → re-score: step 0 336 → **84**,
   exactly as step 1 predicted (2 × 42); total 374 → 122; steps 1–3 unchanged. Nothing was queued.

**Defect found:** the verdict read "20 simulator(s) contribute nothing in this scenario" while 15 of the 20 produce
simulations in another step. Fixed in `6bbdf1c` (Phase 8, T-46); the same scenario now reads "5 simulator(s)
contribute nothing anywhere in this scenario; 15 more contribute nothing in at least one step but run in another."
**Judgement: PASS** — the answers were sufficient to act on, and the one misleading sentence is fixed.

## Second console — pentest01 (pass 4)

Console `pentest01.safebreach.com` (account 3471166703), reached over VPN, configured through the repo's
`SAFEBREACH_ENVS_FILE` / `.env` convention (both git-ignored). Code at `448c25e`, then with the Phase 9 fix.

| Check | Result |
|---|---|
| Unit suite at `448c25e` | 1,847 passed repo-wide; 168 in the feature files |
| e2e file at `448c25e` (11:54Z → 11:59Z) | **17 passed, 1 skipped**. The skip is T-33's per-row case: pentest01's real fleet offers 21 simulators, so every step is over the cap — T-33's over-cap side observed on real agents, not only the mockulator run. T-35 built from 57 exfiltration attacks (159,391 bytes / 1.6 s); its plan was created, scored by id and deleted, and none is left |
| T-36 | `run_scenario(evaluate=True)` on "Step 1 - Fortify your Network Perimeter" (5 steps, 10,924 predicted, constraint summaries on 3 steps) and `quick_run(evaluate=True)` on attacks 11034 + 10976 (exercising the zero-simulation warning) — **byte-identical** to a clean `main` export (`1b6f63f`), 10,173 and 541 characters; nothing queued. **PASS** |
| T-37 | "Network TTP Coverage - Perimeter to Impact", 24 steps, 21 simulators offered. The counts answer is over the cap and names both routes; following `simulator_ids` gave per-machine numbers in both roles; aiming step 0 at the two strongest attackers and every target-producing machine predicted **432** and re-scored **432** (from 1,620; total 215,751 → 214,563, other steps unchanged); nothing queued. **Defect:** the blocked-entities answer was **1,294,873 characters**, one `simulator_failed_schema_validation` group's `schemaErrors` (3,520 objects) alone 1,076,267. Fixed in Phase 9 (T-47); re-measured on the same scenario: **88,715 characters**, longest line 1,368. **PASS after the fix** |
| e2e file with the Phase 9 fix (12:37Z → 12:41Z) | 14 passed, 1 skipped, **3 failed — all HTTP 500 from pentest01's `/plan/statistics` with every constraint requested**. The fix changes rendering only and these three call the functions directly, so their request was byte-identical to the 11:54Z pass. Re-run at 12:42Z: **3 passed**. Recorded as a transient console error — but it is the constraint-heavy call, on a shared console |

## Cumulative readiness

- Selected (Active, Passes after ≤ Final): T-1 … T-47 (47)
- **Executed with evidence: 47** on two consoles — T-33 on both sides of the cap (apricot-jellyfish 22 and 20; pentest01
  21 real simulators)
- Unwritten-planned: none
- BLOCKED: none · Local-pending-ci: none · Delegated: none · Manual substitutions: none
- **Phase verdict: COMPLETE** — every selected test executed and green with evidence

## To author (unwritten-planned)

- None. **T-29** was authored this pass from two responses recorded verbatim on apricot-jellyfish
  (`tests/fixtures/plan_statistics_counts.json`, 4.6 KB of response; `plan_statistics_blocked.json`, 27 KB), each with
  its provenance. The recording itself showed one thing no hand-built fixture had: a live step omits `isLimitReached`
  when the limit is not reached. The tools read it with `.get()`, and T-29 now pins that.

## Smell observations

- **The e2e tests had never met a real payload, and three were wrong.** T-33 dropped the breakdown at `>= 20` where the
  spec says more than 20; T-33 read a `named_simulators` key that has never existed; T-44 asserted Phase 6's subset
  rule after Phase 7 superseded it. All three were test defects — the tool behaved to spec each time.
- **Two more tests silently depended on being under the cap.** The T-33 naming case and the T-35 fixture both took
  their simulator ids from the breakdown rows, which the tool drops past 20 offered — on the 22-simulator fleet the
  naming case had nothing to name and the T-35 fixture skipped with a misleading "no simulator is measured at zero".
  Both now take ids from the console's connected-simulator list, the source the tool's own hint names.
- **The plan encoded two of the same wrong assumptions.** T-44's Expected still stated the superseded subset rule, and
  T-35's claimed the tally rows sum to the blocked total (live: 78 blocked, rows summing to 721 — an attack cites every
  code recorded against it). Both corrected.
- **Design findings, not defects (unchanged):** past the attack cap the tally ranks by count, so codes recorded against
  bystander machines outrank the real cause, and nothing says the rows overlap; in a typical 20-simulator breakdown 61
  of 80 rows are zero in both roles; neither cap offers pagination.
- **`ruff` is still not installed**, so the PRD's lint gate did not run.

## Verdict

- **COMPLETE** — all 47 executed and green with evidence on two consoles: the whole unit tier including T-29's
  recorded-payload contract and T-47's answer-size caps, the real-console tier on apricot-jellyfish and pentest01 with
  T-33 on both sides of the cap, and both manual walkthroughs on both consoles. No waiver was needed for any test.
