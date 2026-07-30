# Environment Design — SAF-33511

**Owning ticket:** SAF-33511   **Env name (planned):** saf-33511
**Environment class:** product / console env
**Offering:** Validate (BAS) — _JIRA `Offering` field (`customfield_13419`) = "All"; the deciding feature is the
Validate test-execution queue (5 validate execution slots, quick-run BAS tests). No lateral-movement/pentest
findings are involved, so Validate is selected over Propagate (cheaper, and Helm data-query runs on Validate per
the run-helm-tests contract)._
**Builder:** create-validate-environment
**Runnability verdict:** env buildable: **yes** · feature exercisable E2E via Helm: **yes, only if** (a) the
`safebreach-mcp` feature branch is deployed into the console's `mcp-proxy` (DEPLOY MAP below), (b) AI features +
Bedrock + Helm flags are enabled, (c) ≥1 connected simulator exists so real Validate tests can saturate the 5
execution slots and leave one queued, and (d) Bedrock is reachable from the runner. If (a) is skipped, Helm runs
**stock** `get_tests` and the queued behavior is absent — the test would silently prove nothing.
**Source artifacts:** prd.md, test-plan.md, context.md
**Status:** Draft (awaiting review)

## Summary
A small Validate (BAS) console whose in-console MCP server (`mcp-proxy` / SIMP) runs the **SAF-33511 feature
branch** of `safebreach-mcp`, with the AI agent (Helm) enabled. The E2E verifies the feature through Helm chat: an
authored Helm **data-query** test saturates the console's 5 validate execution slots with tiny quick-run tests so
one waits in the orchestrator queue, then asks the AI agent to list tests and confirms the queued test surfaces
(status `queued`, with `queue_position`) — cross-checked against the backend. One connected simulator is enough to
produce the submissions; the queue is a console-level construct, so slot saturation does not need many simulators.

## Artifacts under test — DEPLOY MAP (developer: confirm this before approving)   — see references/artifacts.md, mcp-artifact-under-test.md

> The feature lives in `safebreach-mcp`. For Helm to exercise it, the console's `mcp-proxy` container must be built
> with our branch pip-baked in (there is no runtime file-swap for the MCP server). Everything else is stock.

**In-console MCP artifact** (SAF-31681 Phase 10 chain — `deploy-mcp-server-under-test`):

| Repo (mission-scoped) | Image / service on mgmt | Build job | Branch/ref to deploy | Deploy mechanism | Built? |
|-----------------------|-------------------------|-----------|----------------------|------------------|--------|
| `SafeBreach/safebreach-mcp` (GitHub) | pip-baked into `mcp-proxy` image | mcp-proxy multibranch (`integrationPipeline`) | `bugfix/SAF-33511-get-tests-return-queued-tests` (repin `requirements.txt @<sha>`) | repin → build `mcp-proxy` → `mgmt_docker pull_image service=mcp-proxy tag=<sha>` | **no — build in instantiate** |
| `safebreach/mcp-proxy` (bitbucket) | `mcp-proxy` service (`sbmcp-proxy.service`, :4150) | same | a mcp-proxy branch carrying the repin | same | **no — build in instantiate** |

- Deploy strategy: **per-service** — only `mcp-proxy` is swapped; management/UI/orchestrator/data run the env's
  default develop/AMI build. The feature makes no server-side console change, so no `management_ami_branch` swap.
- Verification that our build is live: `mgmt_docker inspect mcp-proxy` tag == `<sha>`; `sbmcp-proxy.service`
  healthy; behavioral proof = a Helm MCP-tool call returns queued data.

**Management images:** none swapped (feature is MCP-only).
**Endpoint simulator build:** none (agent stack not touched — stock simulator).

**Confirm before build:** (1) `safebreach-mcp` feature branch is the ref pinned into `mcp-proxy`; (2) the
`mcp-proxy` feature image is built before the deploy step; (3) `mcp-proxy` is the only swapped service; (4) if it
is NOT deployed, Helm exercises stock `get_tests` and the E2E is meaningless — this row is the whole point of the
build.

## Hosts (endpoints)   — see references/hosts.md
| # | Role | OS (version) | EDR sensor | Software | Notes |
|---|------|--------------|-----------|----------|-------|
| 1 | EP simulator (host-level target/attacker) | ubuntu22 | — | — | produces ≥1 predicted sim for a host quick-run so submitted tests occupy execution slots |

- Cloud/network simulator: **yes** — the default cloud attacker ships with the Validate env (used if the
  Helm-authored test prefers a network attack; the host Linux sim covers host attacks like the pentest01 probe).
- Domain Controller: **no** (not Propagate).
- Sizing rationale: the 5 validate execution slots are a **console-level** capacity, so a single connected
  simulator suffices to saturate them — submitting 6 tiny quick-run tests fills 5 slots + 1 queued regardless of
  simulator count. One `ubuntu22` sim keeps the build minimal.

## Console configuration   — see references/console.md, run-helm-tests env contract
- **AI stack (required for Helm):** `enable_ai_features()` (global `enableAiFeatures=true`) + `enable_aws_bedrock()`.
- **Helm flags (required):** `feature.aiAgentChat=true` + `enableAiAgentActions=true`
  (`conftest.enable_helm_settings`).
- **Bedrock reachability:** the LLM-as-judge is `AnthropicBedrock` (model on Bedrock) keyed off the env AWS region +
  the automation AWS/SSM session — no separate Anthropic key; verify a trivial judge call in the run preflight.
- **Simulator roles & assets:** default; the host sim connected + enabled so quick-runs predict > 0 sims.
- **Cloud integrations / EDR-SIEM connectors / email / impersonated users / RBAC:** none required for this feature.

## Credential sources (no secrets here)
- Management API token / login ← the env's own mgmt (per hosts.md §4 access notes).
- Bedrock / automation AWS ← ambient dev SSO session (account 400469752855) / SSM `/automation/*`.
- EC2 key ← `~/.ssh/us-east-1.pem`.

## Decisions needed
- **Test-plan vehicle reconciliation (needs a plan update).** The plan's e2e tests **T-16/T-19/T-20/T-21** are
  authored as **repo-local pytest e2e** that call the MCP data functions in-process against a console. The user's
  directive is to verify **through Helm chat**. `run-helm-tests` does not run repo pytest — it **authors its own**
  Helm pytest test from the automation-repo pattern library. Decision: add a Helm e2e case to `test-plan.md`
  (Automation lives in `automation/tests/automation_team/pen_test/ui/ai/helm/…`) that these T-ids map to, and treat
  the in-process pytest e2e as a secondary/local check. (Proposed: realize the queued-visibility assertion as the
  Helm case; keep the pytest e2e runnable against any live console for local use.)
- Windows vs Linux simulator: Linux (`ubuntu22`) chosen for cost; confirm no Windows-specific attack is required
  (the queued-state precondition only needs *any* attack that predicts > 0 sims).

## Gaps
- **"queued" state cannot be backend-seeded.** Unlike a normal Helm data-query (seed `executionsHistory` then ask),
  a *queued* test is live, ephemeral orchestrator state. The authored Helm test must **saturate the 5 execution
  slots by submitting real Validate tests** (via the API/MCP) *before* asking Helm to list — i.e. this data-query
  case carries an attack-like precondition (a connected simulator + submitted runs). Flagged so the run step
  provisions submissions, not a static seed. `references/executions-history-seed.md` seeds history, not live queue
  depth — not sufficient alone here.
- **mcp-proxy feature image not yet built.** `deploy-mcp-server-under-test` performs the repin→build→pull in the
  instantiate/deploy step; the image does not exist until then (Built? = no above).
