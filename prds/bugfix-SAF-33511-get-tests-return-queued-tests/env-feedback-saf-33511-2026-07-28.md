# Env-creation retrospection — SAF-33511 · saf-33511 · 2026-07-28

Scope: design → instantiate (infra + console + host config) → deploy-mcp-server-under-test → run-helm-tests use.
Full detail (commands, errors, outputs, per-skill bake-in list) lives alongside this in
`skill-feedback.md` — this record is the teardown-time summary with impact ratings.

## What worked well
- `provision-feature-environment → design-test-environment → instantiate-test-environment` flow is coherent;
  the `env-design.md` DEPLOY MAP surfaced the load-bearing decision (deploy our safebreach-mcp branch to
  mcp-proxy) at design time.
- `references/mcp-artifact-under-test.md` matched reality exactly (two-repo pip-bake chain, SHA image tag,
  dpull); the "verify pip ref inside the container" idea gave the definitive proof our commit was live.
- `create-validate-environment`: the live-`getJob` `team` ChoiceParameter guidance was correct; build green
  first try (~10 min).
- `references/jenkins-access.md` curl-only fallback worked end-to-end (Jenkins MCP not connected).

## What could improve / Blockers & gaps (with impact)
- **[blocker] `deploy-mcp-server-under-test` assumes the sb-env MCP works.** On this SSM-only dev console the
  sb-env MCP returned `Unsupported connection type: ssm` for `mgmt_docker pull_image`/`inspect` (Steps 5–6).
  Had to deploy via SSH `sudo /home/safebreach/support/dpull mcp-proxy <sha>` and verify with
  `docker exec mcp-proxy pip freeze | grep safebreach-mcp`. The skill's `mgmt_docker inspect` tag-match also
  fails-on-success (dpull retags locally + removes the SHA tag). Needs a first-class SSH fallback + the
  in-container verify.
- **[moderate] `references/automation-pytest-preflight.md` §2 remediation is incomplete.** Isolating only
  `AWS_SHARED_CREDENTIALS_FILE` is ignored when `~/.aws/config` defines `dev` as SSO (SSO wins); must also set
  an isolated `AWS_CONFIG_FILE`. And the conftest's `pytest_sessionstart` `create_apikey` crashes with
  `ConnectionError` unless `--mgmt_address/--account_id/--api_token` are passed. Both blocked `pytest
  --collect-only` for run-helm-tests until worked around.
- **[moderate] `run-helm-tests` has no recipe for a queued-state case.** Queue depth is live/ephemeral (not
  seeded `executionsHistory`), and Helm's write-action approval gate serializes submissions + locks the chat
  input for the whole run turn — so naive chat saturation yields zero queued tests. The working recipe
  (reset queue → run N>5 via one prompt → in-page async auto-approve loop → read immediately → cross-check
  orchestrator `/queue`) should be documented. Also: pick a scenario that yields sims on the built sims
  (several OOB scenarios produce 0 on a 2-sim console).
- **[moderate] `references/jenkins-access.md` REST examples use raw `[ ]` brackets** in `tree=` — must be
  URL-encoded (`%5B`/`%5D`) or curl returns empty/non-JSON.
- **[moderate] SbActions surface mismatch.** `conf_actions.enable_ai_features` / `config_actions.get_connected_simulators`
  / `wait_for_all_services` are not direct `SbActions` attributes; the stable path is the console REST API
  (`POST …/settings`, `GET …/nodes`). `create_apikey` returns a dict (`["key"]`, `["accountId"]`), not a string.
- **[minor] zsh word-splitting** breaks `aws … --resources $ids` snippets (create-validate-environment Step 6 +
  cleanup); use `${=ids}` or a per-id loop.
- **[minor] `running-phase-tests`** has no clean dispatch mode for a standalone-pytest repo (safebreach-mcp unit
  tests run via `uv run pytest`, not jest/vitest or automation-pytest).

## Prioritized improvements (most → least impactful)
1. `deploy-mcp-server-under-test`: SSH `dpull` fallback + in-container `pip freeze` verify (removes a hard stop).
2. `automation-pytest-preflight.md`: complete the AWS creds isolation (`AWS_CONFIG_FILE` too) + document the
   `create_apikey` bootstrap flags.
3. `run-helm-tests`: add the queued-state / write-action-approval recipe + two-legged orchestrator-queue check.
4. `jenkins-access.md`: URL-encode `tree=` brackets.
5. SbActions→REST guidance + `create_apikey` dict return.
6. zsh word-splitting note; `running-phase-tests` uv-pytest mode.

## Outcome
Despite the friction, the feature was verified end-to-end through Helm (two-legged): Helm's `get_tests` surfaced
5 queued tests with `status=queued` + queue positions 1–5, matching the backend orchestrator queue exactly.
`max_rating = blocker`.
