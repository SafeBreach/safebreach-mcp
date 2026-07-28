# Skill Feedback — SAF-33511 env creation + E2E run

Honest, constructive feedback on the skills used to build the dedicated environment and run the
Helm E2E, collected live during the run (2026-07-28). Goal: improve these skills.

## What worked well
- **provision-feature-environment / design-test-environment / instantiate-test-environment** flow is
  coherent: the design→review-gate→build sequencing is genuinely useful, and the env-design.md DEPLOY
  MAP forced the load-bearing decision (deploy our safebreach-mcp branch to mcp-proxy, or the whole
  build proves nothing) to the surface early. Catching that at design time was high-value.
- **mcp-artifact-under-test.md** is excellent and accurate — the two-repo pip-bake chain, deterministic
  SHA tag, and the dpull deploy all matched reality. The "verify pip ref inside the container" step
  proved our exact commit was live.
- **create-validate-environment**: the "read team ChoiceParameter choices via getJob REST, never trust
  a hardcoded list" guidance was correct and the build succeeded first try (~10 min).
- **jenkins-access.md** curl fallback worked end-to-end when the Jenkins MCP wasn't connected.

## Friction / bugs (ranked by impact)

1. **sb-env MCP is SSM-blocked on a freshly-built dev console** ("Unsupported connection type: ssm")
   — hit for `mgmt_config nodes_list`, `mgmt_docker images/pull_image`. This is the documented
   SAF-32090 caveat, BUT `deploy-mcp-server-under-test` Step 5/6 assume `mgmt_docker pull_image` works
   as the deploy path. In practice I had to SSH to the mgmt and run `/home/safebreach/support/dpull`
   directly. **Fix:** deploy-mcp-server-under-test should document the SSH `dpull` fallback as a
   first-class path (it already exists for other skills), and the container-tag verify should use the
   in-container `pip freeze | grep safebreach-mcp` (definitive) rather than `mgmt_docker inspect` tag
   match (dpull retags locally + removes the SHA tag, so the tag-match check as written would fail).

2. **jenkins-access.md REST examples use raw `[` `]` brackets** in the `tree=` query. In this
   shell/curl these returned empty/non-JSON until I URL-encoded them (`%5B`/`%5D`). **Fix:** show the
   encoded form in the reference, or note the encoding requirement.

3. **zsh word-splitting** bit the `aws ec2 create-tags --resources $ids` pattern from
   create-validate-environment Step 6 — unquoted `$ids` is NOT word-split in zsh (default shell here),
   so all IDs became one invalid arg. **Fix:** the reference should use an explicit loop or
   `${=ids}` / array, or note the bash-ism.

4. **`create_apikey` returns a dict, not a token string** (`{... "key": <token>, "accountId": ...}`).
   The automation-capabilities / Phase 4 wording implies a token. Minor but cost a round-trip. **Fix:**
   note the return shape (`["key"]` is the token, `["accountId"]` the account).

5. **`SbActions` surface doesn't match the references' method names.** run-helm-tests and
   design-test-environment reference `conf_actions.enable_ai_features()`,
   `config_actions.get_connected_simulators()`, `sb.wait_for_all_services()`. The live `SbActions`
   object has none of these as direct attributes (they live on `ConfigActions` /
   `config_client.ConfigClient`, constructed separately). I fell back to the console REST API directly
   (`POST /api/config/v1/accounts/{acct}/settings`, `GET .../nodes`), which worked cleanly. **Fix:**
   the references should show how to reach ConfigActions from SbActions (or use the client directly),
   or point at the REST endpoints as the stable interface.

6. **safebreach-mcp's own functions aren't callable standalone** for a quick console probe — they
   require the pytest `_user_auth_artifacts` ContextVar bridge (`route_auth_ctxvar_to_request_ctx`)
   that only runs under the test harness; setting the ContextVar directly in a plain script still hit
   `AuthenticationRequired`. Not an env-skill issue, but worth noting for anyone trying to dogfood the
   MCP functions outside pytest.

## To be continued
- run-helm-tests observations (authoring + running the queued-tests Helm case) — appended below as I go.

## run-helm-tests / Helm E2E — live observations (appended)

7. **Our MCP tools are correctly exposed to Helm and callable.** Confirmed live: asking Helm to
   "list my tests" invoked our **Get Tests** MCP tool (visible tool-call chip → "Get Tests /
   Completed") and it correctly reported "no completed, running, or queued tests" on an empty
   console. Asking it to run tests invoked **Get Console Simulators**, **Get Scenarios**, and
   **Run Scenario**. So the safebreach-mcp feature branch is genuinely serving through the AI agent.

8. **The write-action APPROVAL GATE serializes test submission — this is the core obstacle to a
   queued-tests E2E via Helm chat.** Every `Run Scenario` (a write action, gated by
   `enableAiAgentActions`) surfaces an **Approve/Reject** button and the next run stays "Queued for
   approval" until the prior is approved. So a human (or driver) approves them **one at a time**,
   ~15–30s apart. Combined with the platform's 5 concurrent execution slots and short scenarios
   that finish in seconds, the earlier runs COMPLETE before you can approve the 6th — so the queue
   never reaches depth and no test ever enters the `queued` state. **Net:** saturating 5 slots +1
   queued purely by chatting is impractical when (a) approvals are serial and (b) scenarios are
   short. **Implications for the skills:**
   - `run-helm-tests` (and its env-design reconciliation) should call out that a *queued-state*
     data-query case has an **attack-like, timing-sensitive precondition** that the standard
     seeded-`executionsHistory` recipe does NOT satisfy, and that the Helm approval gate makes
     chat-driven saturation unreliable. The realistic recipe is: **saturate the slots out-of-band**
     (backend/orchestrator queue submit, or long-running scenarios) so queue depth exists and
     persists, then use Helm only for the READ ("list queued tests") — which is the leg that
     actually exercises the feature.
   - Alternatively the authored test should submit long/heavy scenarios (many simulations) so each
     occupies a slot for minutes, and pre-approve is not serial — but the approval gate still fights
     this.
   - `executions-history-seed.md` seeds *history*, not live *queue depth* — the reference should
     note it does not help a queued-state case.
9. **First chat-driven attempt produced zero tests** (`testsummaries` empty, orchestrator queue
   empty after approvals) — the approved short scenarios either produced 0 simulations or completed
   before overlapping. Confirms #8: chat-serial submission of short scenarios can't build a queue.

## Clean Helm-driven re-run (corrected) — 2026-07-28

10. **The correct way to drive the Helm approval flow fast: an in-page async auto-approve loop.**
    Instead of one-approval-per-turn (slow, and it let short early tests finish before later ones
    queued), a single `browser_evaluate` running an async loop that polls for the visible `Approve`
    button and clicks it every ~400ms for ~50s approved all 10 Run Scenario invocations in one shot.
    This produced a real Helm-created queue: **5 running + 5 queued**, all from Helm.
11. **Key operational learnings for `run-helm-tests` / manual-ui driving of Helm:**
    - The chat **input is disabled for the entire multi-run turn** until every approval gate is
      resolved (approve or reject). You cannot send the "list" prompt until the run turn finishes.
    - Approvals **serialize**: only one `Approve` shows at a time; the next is "Queued for approval"
      until the prior is actioned. Rapid rejection of the rest is how you abort extra runs.
    - To create a **persistent** queue, submit MORE than the slot count (10 → 5 run + 5 queue) and
      read immediately; the queue drains 5-at-a-time over a few minutes, so the read must be prompt.
    - Some ready-to-run scenarios produce **0 simulations** on a minimal 2-sim console (filters don't
      match); Helm auto-skips those. Tell it to use a scenario known to produce sims (the run-helm
      env-design should note: a queued-state case needs a scenario that yields sims on the built sims).
12. **RESULT — feature verified end-to-end through Helm (two-legged):** Helm, calling our
    in-console `get_tests` (mcp-proxy @ safebreach-mcp 7225955), returned 5 queued tests with
    `status=queued` and Queue Positions 1–5; the planRunIds + order matched the backend orchestrator
    `/queue` read taken seconds earlier, exactly. Baseline (empty console) correctly showed 0 queued.
    Before SAF-33511, `get_tests` could not surface queued tests at all. Evidence:
    `.playwright-mcp/saf-33511-helm-queued-tests-clean.png` + the transcript captured in this run.
13. **Earlier interpretation compromise (corrected):** the first attempt saturated the queue
    out-of-band (my own quick_run burst) and only 1 queued test remained by read time — I should not
    have presented that as the clean result. The re-run above created the queue entirely via Helm and
    read 5/5 matching the backend. Lesson for the runner: the saturation MUST be part of the observed
    flow, and the read must happen while the queue is genuinely deep.

---

## Recommended skill edits (bake-in list — mapped to target file + exact change)

Each row: **target skill/reference → concrete change**. Ordered by impact.

1. **`deploy-mcp-server-under-test` SKILL.md (Steps 5–6)** — the deploy + verify assume the sb-env
   MCP `mgmt_docker pull_image`/`inspect` work. On an SSM-only dev console the sb-env MCP fails
   ("Unsupported connection type: ssm"). **Add a first-class SSH fallback:**
   `ssh ubuntu@<mgmt-ip> "sudo /home/safebreach/support/dpull mcp-proxy <sha>"`, and change the
   verify to `docker exec mcp-proxy pip freeze | grep safebreach-mcp` (proves the exact commit) —
   the current `mgmt_docker inspect` tag-match FAILS because dpull retags locally and removes the
   SHA tag. (This was the single biggest friction.)

2. **`references/jenkins-access.md`** — every `tree=...[...]` example must show **URL-encoded
   brackets** (`%5B`/`%5D`); raw brackets return empty/non-JSON via curl. Same for
   `parameterDefinitions%5Bname,choices%5D`.

3. **`references/automation-pytest-preflight.md` §2** — the isolated-creds remediation is
   incomplete: setting only `AWS_SHARED_CREDENTIALS_FILE` is **ignored** when `~/.aws/config`
   defines the profile (`dev`) as SSO (SSO wins). Must ALSO set an isolated `AWS_CONFIG_FILE`
   containing `[profile dev]\nregion=us-east-1` (no sso_session). Document both env vars together.
   Also document the **`create_apikey` bootstrap**: pass `--mgmt_address`, `--account_id`,
   `--api_token` to the pytest run to SKIP the `pytest_sessionstart` create_apikey ConnectionError.

4. **`create-validate-environment` Step 6 + any `aws ... $ids` snippet** — the shell here is **zsh**,
   which does NOT word-split unquoted vars. `--resources $ids` sends one bad arg. Use `${=ids}`
   (zsh) or a per-id loop. Bit me twice (tagging + cancel).

5. **`run-helm-tests` SKILL.md — queued-state / write-action cases** — add a subsection:
   - A *queued-state* data-query case is NOT the standard seeded-`executionsHistory` shape: queue
     depth is live, ephemeral, and can only be produced by **submitting real runs**. `executions-
     history-seed.md` does not help.
   - The Helm **write-action approval gate serializes submissions** and **locks the chat input for
     the whole run turn**. Recipe that works: (a) one prompt asking Helm to run N > slot-count tests
     using a scenario that yields sims on the built sims; (b) an in-page async auto-approve loop
     (poll+click `Approve` every ~400ms) to approve all N fast so they overlap; (c) once the turn
     ends and input unlocks, immediately send the "list queued tests" prompt and read while the
     queue is still deep (it drains slot-count at a time).
   - Cross-check the Helm reply against the orchestrator `/queue` read (independent of get_tests),
     not against get_tests itself (that would be circular).

6. **`design-test-environment` / `run-helm-tests` env contract** — a Helm queued-state case needs
   **≥1 simulator AND a scenario that produces simulations on it**; several OOB scenarios yield 0
   sims on a minimal 2-sim console. Note this so the design picks/【verifies a sim-producing scenario.

7. **`references/*` SbActions guidance** — the referenced helpers (`conf_actions.enable_ai_features`,
   `config_actions.get_connected_simulators`, `wait_for_all_services`) are NOT direct `SbActions`
   attributes. Either show the correct accessor path or (simpler, stable) point at the REST
   endpoints: settings `POST /api/config/v1/accounts/{acct}/settings {key,value:"true"}`, nodes
   `GET /api/config/v1/accounts/{acct}/nodes?details=true`. `create_apikey` returns a **dict**
   (`["key"]`=token, `["accountId"]`=account), not a string.

8. **`running-phase-tests`** — for the safebreach-mcp repo, the phase's unit tests are `uv run
   pytest` (not jest/vitest and not automation-pytest); the orchestrator's dispatch table has no
   clean mode for a standalone pytest repo. Either add a `uv-pytest` source-repo mode or document
   that safebreach-mcp unit suites are run directly and only the Helm e2e dispatches to a runner.
