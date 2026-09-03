# Environment — SAF-35508

**Env name:** saf-35508   **Mgmt URL:** https://saf-35508.dev.sbops.com
**Owning ticket:** SAF-35508   **Created:** 2026-09-03   **sb_ticket tag:** SAF-35508
**Credentials:** console API token minted at build time and stored only in the gitignored
`.vscode/set_env.sh` (never in this file, a log, or any PRD artifact). EC2 key `~/.ssh/us-east-1.pem`.
**Built by:** `create-custom-environment` build **#55302** (SUCCESS, 624 s) —
https://butler.sbops.com/job/create-custom-environment/55302/

## Infrastructure

| Resource | Instance ID | Role / OS | sb_ticket | Verify |
|---|---|---|---|---|
| management | i-065cb508e02430d32 | management (t3.xlarge) | ✅ | up — console reachable, API answering |
| cloud-sim | i-0c1e6bd85093747c3 | cloud simulator (LINUX 26.04) | ✅ | connected |
| saf-35508-windows2022 | i-0430f9d81097b85c3 | EP / windows2022 (WINDOWS 2022Server) | ✅ | connected |
| saf-35508-ubuntu22 (a) | i-035a18a31859aa6c7 | EP / ubuntu22 (LINUX 22.04) | ✅ | connected |
| saf-35508-ubuntu22 (b) | i-0eb4608fa8ecaf47a | EP / ubuntu22 (LINUX 22.04) | ✅ | connected |

**Fleet as the tools see it:** 4 simulators, all connected — `{LINUX: 3, WINDOWS: 1}`. The mixed-OS
property is the one T-48 depends on; verified live, not assumed.

**Lifecycle tags — verified on every instance** (all five, no exceptions):

| Tag | Value |
|---|---|
| `sb_ticket` | `SAF-35508` |
| `stop_at` | `2026-09-10 13:26:13` |
| `terminate_at` | `2026-09-12 13:26:13` |
| `TF` | `eod-off` |

`stop_at` is strictly before `terminate_at`, both are future. Retention honoured the requested 168 h
(the build's own `Terminated at` line reads `2026-09-10 10:14:43`; the explicit tags above supersede it
with the 48 h grace the lifecycle procedure requires).

## Console configuration applied

- **API key:** one administrator key minted via `create_apikey(..., role_id="administrator")`
  (account `3475543660`). Required because a fresh console has no token.
- **Everything else: none, by design.** No cloud integrations, EDR/SIEM connectors, email inboxes,
  impersonated users, roles/assets, feature toggles or RBAC. `plan/statistics` is a pre-execution
  prediction over configuration — nothing in this feature's tests runs a simulation or asserts a
  detection, so detection tooling would cost money and cover nothing.
- **Not applied — a deviation from the approved design, stated plainly:** the design called for the
  third `ubuntu22` to be left **unapproved**, so T-30's offline-reason assertion would run instead of
  skip. The `automation` client exposes no node-approval verb, and hand-rolling the console API call was
  not attempted. Consequence: T-30's conditional half still skips (its unconditional half passes). See
  *Known gaps*.

## Artifacts under test (verified running tags)

| Repo | Service/image | Expected | Running | OK |
|---|---|---|---|---|
| safebreach-mcp | **not deployed** — runs locally | n/a | n/a | n/a |

Deliberate, and confirmed at the review gate. Every automatic e2e test imports the three tools from the
local worktree and calls the console's REST API directly; no request passes through a deployed
`mcp-proxy`. Console services are stock `develop`. The code exercised is the worktree at
`feature/SAF-35508-plan-statistics-mcp-tool`.

## Test evidence — the reason this env exists

**e2e suite: 11 passed, 2 skipped** (`test_e2e_plan_statistics.py -m e2e`, 113 s).

**AC-4 / TI-4 — the numbers match the console.** The Add Simulators Checkout view calls this same
endpoint with `includeDisabled=true, getConstraints=true`
(`ui-react/src/actions/execution.tsx:615`). Driving the endpoint with the console's own parameter set
and the counts tool with the equivalent question, on the 4-step OOB scenario **KongTuke**:

| Parameter set | Console's own call | `get_scenario_simulation_counts` | Match |
|---|---|---|---|
| Checkout (`includeDisabled=true`) | `[54, 1, 0, 0]` | `[54, 1, 0, 0]` | ✅ |
| Run gating (`includeDisabled=false`) | `[54, 1, 0, 0]` | `[54, 1, 0, 0]` | ✅ |

Mode labels correct (`expected` / `runnable`); runnable ≤ expected holds. This verifies the real risk —
**that our parameter mapping diverges from the console's** — on live data with non-trivial numbers.
It does **not** read the rendered figure out of the browser; see *Known gaps*.

## Known gaps

1. **T-35's rendered-view half is still owed.** AC-4 as written compares against the *displayed* count in
   the Checkout view. Both browser MCP servers (`sb-ui:playwright`, `sb-ui:chrome-devtools`) failed to
   connect. The parameter-set comparison above is materially stronger than any mocked assertion and
   covers the divergence risk, but it is not the rendered number. **T-35 is not marked passed.**
2. **T-30's conditional half skips** — no simulator is unapproved (see above), so nothing is *fully*
   blocked by `simulator_is_offline`. Its unconditional half (runnable ≤ expected) passes.
3. **T-29's custom-plan case skips** — a fresh console ships no custom plans. Benign; the test is
   designed to skip.
4. 🔴 **A real finding from this run: `absent` is a misleading answer when the orchestrator generates no
   move for an attack.** Aiming a LINUX-constrained attack at WINDOWS-only targets returns
   `simulation_count: 0` with an **empty** `attacks` map — the attack never became a candidate move, so
   there is no `moves[id] = 0`. `get_scenario_attack_blockers` then reports **`absent`** — "not present
   in this scenario" — for an attack the caller had just named in the scenario's own filter. Both tools
   are spec-correct (AC-9 governs `moves[id] === 0`, which never occurs here), but the pair reads
   wrongly, and "the attack was filtered out entirely" is probably the *most common* real reason a user
   asks why an attack did not run. This is the same class of misleading-but-plausible answer the feature
   exists to prevent, one level out. Worth its own disposition and a follow-up ticket. Discovered only
   because the test ran against a real console — every mocked fixture had put the attack in the map at 0.

## Status

**built** — infrastructure provisioned and verified, console reachable, API key minted, e2e evidence
captured. Not torn down; terminates 2026-09-12.
