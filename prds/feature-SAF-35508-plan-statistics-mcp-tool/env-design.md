# Environment Design — SAF-35508

**Owning ticket:** SAF-35508   **Env name (planned):** saf-35508
**Environment class:** product / console env
**Offering:** Validate (BAS) — _JIRA `Offering` (`customfield_13419`) = **"Helm AI Agent"**, which names the
consumer rather than a build topology, so it does not resolve a builder on its own. The test plan resolves it
explicitly: "Helm AI Agent over the **Validate** product surface — scenarios/plans, simulators, plan statistics".
Deciding tests: T-28…T-31, T-40, T-48 all read scenarios, simulators and the playbook from a Validate console and
score them through `plan/statistics`. Nothing in the plan touches lateral movement, AD, or patient-zero/victim
topology, so Propagate is not merely unnecessary here — it could not exercise these tests at all._
**Builder:** create-validate-environment
**Runnability verdict:** env buildable: **yes** · feature exercisable E2E: **yes for the six automatic e2e tests**
(they need only a console with a mixed-OS fleet) · **partially for T-35**, the Manual test that actually closes
AC-4 — see *Gaps*.
**Source artifacts:** prd.md, test-plan.md, context.md, test-results/ticket-compliance.md
**Status:** Draft (awaiting review) — rewritten 2026-09-03, superseding the earlier draft whose console choice
was left open

## Summary

A minimal Validate console whose only job is to answer one question the 1 927 passing unit tests cannot:
**do the three scenario-statistics tools report the numbers the product reports?** That is TI-4 / AC-4, the sole
accepted gap on this ticket and the only criterion that tests correctness rather than self-consistency.

The binding constraint is not scale — it is **OS diversity**. T-48 constructs a guaranteed block by aiming an
OS-constrained attack at simulators of a different OS; on a single-OS fleet it can only skip. Two simulators of
different OS families is therefore the floor, and also the ceiling for the automatic tests.

## Artifacts under test — DEPLOY MAP (developer: confirm this before approving)

> **Read this row-by-row: there is deliberately nothing to deploy.**

| Repo (mission-scoped) | Image / service on mgmt | Build job | Branch tag to deploy | Deploy mechanism | Built? |
|---|---|---|---|---|---|
| safebreach-mcp | **none — not deployed** | n/a | n/a | n/a | n/a |

**Why no deployment, against the usual rule.** The provisioning guidance says a `safebreach-mcp` change normally
makes the in-console MCP server an artifact under test, deployed by rebuilding `mcp-proxy` with the branch
pip-baked in. **That does not apply to the tests this env exists to run.** Every automatic e2e test in
`test_e2e_plan_statistics.py` imports `sb_get_scenario_simulation_counts` / `..._blocked_entities` /
`..._attack_blockers` **directly from the local worktree** and calls them with `console=E2E_CONSOLE`; the MCP
functions execute locally and speak to the console's REST API. No request passes through a deployed `mcp-proxy`.
Deploying one would cost a build and verify nothing these tests assert.

- **Console services:** all stock `develop`. Intended, and stated so the developer can confirm it.
- **Code under test:** the local worktree at `feature/SAF-35508-plan-statistics-mcp-tool` (HEAD `35e62a9`),
  exercised in-process by pytest.
- **The one exception, out of scope here:** T-32 (Manual progression, `Passes after: Final`) drives an *MCP client
  connected to the console* and would need `deploy-mcp-server-under-test`. It is not part of closing TI-4, and it
  is not attempted by this env. Flagged so its absence is a decision, not an oversight.

## Hosts (endpoints)

| # | Role | OS (version) | EDR sensor | Software | Notes |
|---|---|---|---|---|---|
| 1 | EP simulator | `windows2022` | — | — | Connected + approved. The **target-OS side** of T-48's constructed mismatch |
| 2 | EP simulator | `ubuntu22` | — | — | Connected + approved. The **other-OS side**. Two OS families is what makes T-48 assertable rather than skippable |
| 3 | EP simulator | `ubuntu22` | — | — | **Left unapproved** — see *Decisions needed*. `node.isEnabled = isConnected && approved`, so an unapproved node is "disabled" for `includeDisabled` without being switched off. Exercises T-30's conditional half |

- OS ids are the canonical no-hyphen Validate tokens from `hosts.md` "Buildable OS ids" (`windows2022`,
  `ubuntu22`) — verified against the **Validate** row, not the hyphenated Propagate scheme.
- No EDR sensors, no connectors, no email inboxes, no cloud nodes: `plan/statistics` is a **pre-execution
  prediction** over configuration. Nothing in the plan runs a simulation or asserts a detection, so detection
  tooling would add cost and cover nothing.
- Cloud/network simulator: default cloud attacker only, as it ships.
- Domain Controller: **no** — Validate, no AD in scope.

## Console configuration

- **Scenarios:** the OOB scenarios that ship with the console are sufficient — T-28/T-29/T-30/T-40 discover one
  with steps at runtime and hardcode nothing. A custom plan is optional; T-29's integer-id case skips without one.
- **Playbook:** ships with the console. T-48 queries it for an OS-constrained attack via
  `target_platform_filter`.
- **Simulator approval:** hosts 1 and 2 approved; host 3 deliberately left unapproved (pending the decision below).
- **Impersonated users / roles / assets / connectors / toggles / RBAC / API keys:** none required.
- **API key:** one console API token is required for the tests to authenticate — sourced, not created here.

## Credential sources (no secrets here)

- Console API token → AWS SSM under the console's configured parameter, per `environments_metadata.py`
  (`secret_config.provider = aws_ssm`, parameter `<console>-apitoken`), read with `--profile dev`.
- EC2 key → `~/.ssh/us-east-1.pem`.
- The token is written only to `.vscode/set_env.sh`, which is gitignored and must never be committed.

## Decisions needed

1. **Host 3 — build it, or accept T-30's skip?** T-30's conditional half (a positive runnable-vs-expected delta
   *explained* by `simulator_is_offline`) needs a simulator that is disabled/unapproved **and fully blocks
   something**. Its unconditional half (runnable ≤ expected) runs either way, and the test carries an explicit
   skip with a stated reason. Building host 3 costs one small instance; skipping it leaves that assertion
   unexercised. **Recommendation: build it** — "runnable excludes offline simulators and says why" is the
   feature's most user-visible correction, and a skip here would leave it verified only against mocks.
2. **T-35's browser access.** AC-4 as written compares the tools' numbers against the **Add Simulators Checkout
   view** in the console UI. See *Gaps* — this needs a decision before the env is judged sufficient.

## Gaps

- 🔴 **T-35 cannot be fully executed as written.** It requires reading a rendered console view, and both browser
  MCP servers (`sb-ui:playwright`, `sb-ui:chrome-devtools`) failed to connect this session. The env is buildable
  and the *numbers* half is reachable another way: the Checkout view calls this same endpoint with
  `includeDisabled=true, getConstraints=true` (`ui-react/src/actions/execution.tsx:615`), so the tools' output can
  be compared against a direct call using the console's own parameter set. That verifies the real risk — **that
  our parameter mapping diverges from the console's** — and is far stronger than any mocked assertion. It does not
  verify the rendered figure. Recommend running that comparison and recording the rendered-view half as still
  owed, rather than marking T-35 passed.
- **No dispatch row fits these e2e tests.** `running-phase-tests` routes "e2e, Validate/BAS (console)" to
  `run-validate-attack`, which *runs attacks*; these tests run no attack and live in the source repo, not
  `automation`. They execute as `uv run pytest -m e2e` with `E2E_CONSOLE` set — a source-repo uv-pytest run that
  happens to need a live console. Recorded so the runner's accounting reflects what actually ran.
- **T-32 is not covered by this env** (needs a deployed MCP server; see the DEPLOY MAP).
