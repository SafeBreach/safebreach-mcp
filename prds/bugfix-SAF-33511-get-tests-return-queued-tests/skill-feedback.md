# Skill Feedback — building a test environment + running a Helm E2E (SAF-33511)

> **Purpose of this document.** Honest, constructive feedback on the SafeBreach dev/env skills that were
> exercised end-to-end while implementing and verifying JIRA ticket **SAF-33511**. It is written to be
> **self-contained for a fresh Claude Code session with no prior context** — you should be able to act on
> every item without having seen the original run. Collected live on **2026-07-28**. The goal is to bake
> these fixes back into the skills so the next run is smoother.
>
> If you are that fresh session and your job is to apply these fixes: start at
> **"Recommended skill edits (bake-in list)"** at the bottom — it maps each finding to an exact file and
> change. The narrative sections above it explain *why* each fix matters, with the real commands, error
> messages, and outputs observed.

---

## 0. Context — what was being done (so the findings make sense)

**The ticket (SAF-33511):** a bug in the **`safebreach-mcp`** repo (an MCP server that bridges AI agents to
the SafeBreach Breach-and-Attack-Simulation platform). Its `get_tests` MCP tool did not return tests that were
**waiting in the platform's execution queue** — only running/terminal tests. The fix makes `get_tests` merge
the orchestrator queue so queued tests appear with `status='queued'` and a `queue_position`.

**Why an environment + Helm were involved:** the reviewed test plan required verifying the fix **through
Helm** — SafeBreach's built-in agentic AI chat in the console (internally *BreachGenie*). Helm calls MCP
tools, including our `get_tests`. So to prove the fix E2E we had to:
1. Build a dedicated SafeBreach **Validate (BAS)** console for the ticket.
2. Deploy **our feature branch of `safebreach-mcp`** into that console's in-console MCP server (so Helm runs
   *our* code, not stock).
3. Enable the AI agent (Helm) + AWS Bedrock on the console.
4. Drive Helm by chat to create queued tests and then list them, confirming our feature surfaces them.

**The skill pipeline exercised** (all skills live in two marketplace plugins — see §1 for on-disk paths):
- `sb-dev-base`: `planning-dev-task`, `authoring-test-plan`, `tdd-implementing-prd`, `running-phase-tests`.
- `safebreach-environment-provisioner`: `provision-feature-environment` → `design-test-environment` →
  `instantiate-test-environment` → `create-validate-environment`, `deploy-mcp-server-under-test`,
  `run-helm-tests`.

**The concrete environment that got built** (facts a fresh session may need to reproduce/inspect):
| Fact | Value |
|------|-------|
| Env name / owning ticket | `saf-33511` / `SAF-33511` (EC2 tag `sb_ticket=SAF-33511`) |
| Management console URL | `https://saf-33511.dev.sbops.com` |
| Account ID | `3475543660` |
| Mgmt login | `devops@safebreach.com` / `S@f3breach` (dev console; not a real secret) |
| Mgmt EC2 | `i-07e7dfacbe8dfe318`, private IP `200.11.126.70`, SSH `ubuntu@…` key `~/.ssh/keys/Dev/us-east-1.pem` |
| Simulators | 1× `ubuntu22` EP sim + 1× cloud sim (both connected+enabled) |
| Retention | 48h auto-teardown (`terminate_at` ~2026-07-30 09:12 UTC) |
| AWS | dev account `400469752855`, region `us-east-1`, ambient SSO creds (env vars) valid; the `dev` **profile** SSO was expired |
| safebreach-mcp feature branch | `bugfix/SAF-33511-get-tests-return-queued-tests`, commit `7225955f1a43718e440578fa37d53503064bb58a` (GitHub `SafeBreach/safebreach-mcp`) |
| mcp-proxy repin branch | `feature/SAF-33511-mcp-proxy-repin`, HEAD `94a97937354ccb84133e98bac35e75b34a6ade58` (Bitbucket `safebreach/mcp-proxy`); image pushed to dev ECR under tag `94a9793…` |
| Jenkins (butler) | `https://butler.sbops.com`; `jcli` present + `$JENKINS_AUTH` set (base64 `user:token`) |

**Glossary (terms used below):**
- **Helm / BreachGenie** — the console's AI chat agent; calls MCP tools. Gated by feature flags
  `feature.aiAgentChat` + `enableAiAgentActions` (+ `enableAiFeatures`, `enableAmazonBedrock`).
- **mcp-proxy / SIMP** — the in-console container (Bitbucket `safebreach/mcp-proxy`) that hosts the
  safebreach-mcp servers. It **pip-installs the safebreach-mcp source at build time**, so deploying an MCP
  change means rebuilding the mcp-proxy image and pulling it into the console (no runtime file-swap).
- **dpull** — SafeBreach helper on the mgmt host (`/home/safebreach/support/dpull <service> <tag>`) that
  pulls a dev-ECR image and restarts the service.
- **sb-env MCP** — the `safebreach-env` MCP server (tools `mgmt_config`, `mgmt_docker`, `mgmt_service`) for
  inspecting/operating a console. Connects over SSH or SSM depending on env.
- **SSM** — AWS Systems Manager (agentless remote exec). Dev consoles here are "SSM-only" for sb-env.
- **execution slots** — the platform runs at most **5 tests concurrently**; a 6th+ submission **queues**.
  This 5-slot limit is the entire subject of SAF-33511.
- **planRunId** — a test-run id, e.g. `1785233359209.58`; its numeric prefix is the submission epoch-ms.
- **quick_run** — a safebreach-mcp Studio tool that submits an ad-hoc test from playbook attack ids.
- **executionsHistory** — the backend index of past simulation results (what a normal Helm "data-query"
  test seeds). NOT the same as live queue depth.
- **two-legged verification** — the run-helm-tests discipline: never trust Helm's chat text alone; cross-check
  every claim against an independent backend read.

**On-disk evidence from this run** (committed in this PRD folder):
- `test-results/phase-5.md` — the audited Phase-5 results + accounting.
- `test-results/evidence/saf-33511-helm-queued-tests-clean.png` — the clean Helm-driven run (5 queued shown).
- `test-results/evidence/saf-33511-helm-queued-tests.png` — the earlier run.

---

## 1. Where the skills live on disk (anchors for every "Fix" below)

The two plugins were loaded from a local marketplace checkout at
`/Users/yossiattas/projects/rules/plugins/` (they may also resolve from the marketplace cache
`~/.claude/plugins/cache/safebreach-marketplace/<plugin>/<version>/`). Verified paths used below:

- **safebreach-environment-provisioner plugin root:**
  `/Users/yossiattas/projects/rules/plugins/safebreach-environment-provisioner/`
  - `skills/deploy-mcp-server-under-test/SKILL.md`
  - `skills/run-helm-tests/SKILL.md`
  - `skills/create-validate-environment/SKILL.md`
  - `skills/design-test-environment/SKILL.md`
  - `skills/instantiate-test-environment/SKILL.md`
  - `references/jenkins-access.md`
  - `references/automation-pytest-preflight.md`
  - `references/mcp-artifact-under-test.md`
  - `references/executions-history-seed.md`
- **sb-dev-base plugin root:** `/Users/yossiattas/projects/rules/plugins/sb-dev-base/`
  - `skills/running-phase-tests/SKILL.md`

When an item below says e.g. "`deploy-mcp-server-under-test` SKILL.md", it means
`…/safebreach-environment-provisioner/skills/deploy-mcp-server-under-test/SKILL.md`.

---

## 2. What worked well (keep / don't regress)

- **`provision-feature-environment` → `design-test-environment` → `instantiate-test-environment`** is a
  coherent flow. The design→human-review-gate→build sequencing is genuinely useful, and the `env-design.md`
  **DEPLOY MAP** forced the single load-bearing decision to the surface early: *deploy our safebreach-mcp
  branch into mcp-proxy, or the whole build proves nothing* (Helm would run stock `get_tests`). Catching
  that at design time was high value.
- **`references/mcp-artifact-under-test.md`** is excellent and matched reality exactly — the two-repo
  pip-bake chain (safebreach-mcp → mcp-proxy), the deterministic commit-SHA image tag, and the dpull deploy.
  Its "verify the pip ref inside the container" idea is what definitively proved our commit was live.
- **`create-validate-environment`**: the guidance "read the `team` ChoiceParameter choices via the `getJob`
  REST tree, never trust a hardcoded list" was correct; the Validate build succeeded first try (~10 min).
- **`references/jenkins-access.md`** curl-only fallback (using `$JENKINS_AUTH` as a Basic header) worked
  end-to-end to trigger/poll/read builds when the Jenkins MCP was not connected.

---

## 3. Friction / bugs found (ranked by impact) — with the real evidence

### 3.1 sb-env MCP is SSM-blocked on a fresh dev console → the MCP deploy path doesn't work
- **What happened:** every `safebreach-env` MCP call against `saf-33511.dev.sbops.com` returned
  `{"success": false, "error": "Unsupported connection type: ssm"}` — for `mgmt_config nodes_list`,
  `mgmt_docker images`, and `mgmt_docker pull_image`. This is the documented SAF-32090 caveat.
- **Why it's a bug for the skills:** `deploy-mcp-server-under-test` **Step 5** deploys via
  `mgmt_docker pull_image` and **Step 6** verifies via `mgmt_docker inspect` — both are sb-env MCP calls,
  so both are unusable on this env class. I had to fall back to SSH.
- **What worked instead (SSH fallback):**
  `ssh -i ~/.ssh/keys/Dev/us-east-1.pem ubuntu@200.11.126.70 "sudo /home/safebreach/support/dpull mcp-proxy <sha>"`
  → pulled the image and restarted `sbmcp-proxy`.
- **Verify subtlety:** `mgmt_docker inspect` / `docker inspect --format '{{.Config.Image}}'` shows only the
  local tag (`mcp-proxy`), because `dpull` retags locally and **removes** the SHA tag (its log prints
  `Untagged: …:<sha>` + `Remove pulled image`). So a tag-match verify **fails even on success**. The
  definitive verify is **inside the container**:
  `sudo docker exec mcp-proxy pip freeze | grep safebreach-mcp` →
  `safebreach-mcp-server @ git+https://github.com/SafeBreach/safebreach-mcp.git@7225955…` (proves the exact
  commit is serving), plus `tail /datadb/logs/sbmcp-proxy.log` for "SIMP service ready".
- **Fix:** see bake-in #1.

### 3.2 jenkins-access.md REST examples use raw `[` `]` brackets
- **What happened:** `curl ".../api/json?tree=property[parameterDefinitions[name,choices]]"` returned an
  empty/non-JSON body (JSON parse crashed). Only after URL-encoding the brackets
  (`tree=property%5BparameterDefinitions%5Bname,choices%5D%5D`) did it return the `team` choices.
- **Fix:** see bake-in #2.

### 3.3 zsh word-splitting breaks the `aws … $ids` snippets (bit me twice)
- **What happened:** the shell here is **zsh**, which (unlike bash) does **not** word-split an unquoted
  variable. `aws ec2 create-tags --resources $ids …` (from `create-validate-environment` Step 6) passed all
  three instance ids as **one** argument → `InvalidID: The ID 'i-… i-… i-…' is not valid`. Same failure hit
  the cleanup `curl -X DELETE .../queue/$IDS` loop later.
- **What worked:** `for tid in ${=ALL}; do …; done` (zsh split operator) or an explicit per-id loop, or
  passing ids literally.
- **Fix:** see bake-in #4.

### 3.4 `create_apikey` returns a dict, not a token string
- **What happened:** `create_apikey(mgmt, email, password, role_id="administrator")` returns a **dict**
  with keys `['accountId','createdAt','createdBy','description','id','key','lastUsed','name','role',
  'roleId','updatedAt']`. The token is `result["key"]`; the account is `result["accountId"]`. Treating the
  return as a string (`f.write(token)`) raised `TypeError: write() argument must be str, not dict`.
- **Fix:** see bake-in #7.

### 3.5 `SbActions` surface doesn't match the references' method names
- **What happened:** `run-helm-tests` and `design-test-environment` reference
  `sb_actions.conf_actions.enable_ai_features()`, `config_actions.get_connected_simulators()`, and
  `sb.wait_for_all_services()`. On the live `SbActions` object (automation repo
  `/Users/yossiattas/projects/automation`, `src/sb_client/actions/sb_actions.py`) **none** of these are
  direct attributes — `dir(SbActions)` shows high-level methods only (e.g. `run_scenario_and_wait_for_results_v3`,
  `execute_plan_by_test_id`). The enable helpers live on `ConfigActions`
  (`src/sb_client/actions/config_actions.py`, e.g. `enable_ai_features`→`enableAiFeatures`,
  `enable_aws_bedrock`→`enableAmazonBedrock`), constructed separately.
- **What worked instead (stable):** call the console REST API directly with the api token
  (`x-apitoken` header):
  - enable a flag: `POST https://<mgmt>/api/config/v1/accounts/<acct>/settings` body
    `{"key":"enableAiFeatures","value":"true"}` (value must be the STRING "true"). Used for all 4 Helm flags.
  - list nodes: `GET https://<mgmt>/api/config/v1/accounts/<acct>/nodes?details=true`.
- **Fix:** see bake-in #7.

### 3.6 safebreach-mcp's own functions aren't callable standalone (auth-context gotcha)
- **What happened:** trying to dogfood our MCP functions (`sb_get_tests`, `sb_quick_run`) directly from a
  script hit `AuthenticationRequired("… no user credentials in request context")`. `get_auth_headers_for_console`
  (`safebreach_mcp_core/secret_utils.py`) reads auth from the MCP request context; under pytest a conftest
  fixture (`route_auth_ctxvar_to_request_ctx`) bridges the `_user_auth_artifacts` ContextVar into it, but that
  bridge doesn't run in a plain script.
- **What worked:** the standalone fallback path — set **`SAFEBREACH_ENVS_FILE`** (NOT `SAFEBREACH_LOCAL_ENV`)
  to a JSON file registering the console with an `env_var` secret provider, and export the token env var.
  With `SAFEBREACH_LOCAL_ENV` **unset**, `get_auth_headers_for_console` falls back to the env-var API key and
  the functions work. (With `SAFEBREACH_LOCAL_ENV` set, it deliberately raises — "embedded/RBAC mode".)
  Example envs file used:
  `{"saf-33511": {"url":"saf-33511.dev.sbops.com","account":"3475543660","secret_config":{"provider":"env_var","parameter_name":"saf_33511_apitoken"}}}`
  with `export saf_33511_apitoken=<token>`.
- **Note:** this is a safebreach-mcp repo behavior, not an env-skill bug — captured so a future session can
  dogfood the tools quickly. See bake-in #7 (last line).

---

## 4. Helm E2E — live observations (the heart of the run)

### 4.1 Our MCP tools ARE correctly exposed to Helm and callable
Confirmed live: asking Helm "list my tests" invoked our **Get Tests** MCP tool (a visible tool-call chip
"Get Tests / Completed" in the chat), and on the empty console it correctly answered "no completed, running,
or queued tests." Asking Helm to run tests invoked **Get Console Simulators**, **Get Scenarios**, and
**Run Scenario**. So the deployed feature branch is genuinely serving through the AI agent.

### 4.2 The write-action APPROVAL GATE is the core obstacle to a queued-tests E2E via chat
- **What it is:** every `Run Scenario` (a *write* action, gated by `enableAiAgentActions`) surfaces an
  **Approve / Reject** button pair in the chat. When Helm queues several runs in one turn, only **one** shows
  "Awaiting approval" at a time; the rest show "Queued for approval" until the prior is actioned. So approvals
  **serialize**.
- **Why it fights a queued-state test:** combined with the 5-slot concurrency and short scenarios that finish
  in seconds, if you approve one-at-a-time (~15–30s apart) the earlier runs **complete before** you approve
  the 6th, so the queue never reaches depth and no test ever enters `queued`. My first attempt this way
  produced **zero** tests (both `testsummaries` and the orchestrator queue were empty after approvals) — the
  short scenarios finished (or produced 0 sims) before overlapping.
- **Also:** the chat **input textarea is disabled for the entire multi-run turn** until every approval gate is
  resolved (approve or reject). You cannot send the follow-up "list queued tests" prompt until the run turn
  finishes.
- **Also:** some ready-to-run scenarios produce **0 simulations** on a minimal 2-sim console (their
  target/attacker filters don't match the connected sims); Helm auto-skips those and cycles to working ones.

### 4.3 What actually worked — the correct recipe (clean, Helm-driven, two-legged)
1. **Reset** the orchestrator queue to empty first (cancel any running/queued runs) so the result is
   unambiguous.
2. **One prompt** asking Helm to run **N > slot-count** tests (used N=10) using a scenario that yields sims on
   the built sims (e.g. "Network Perimeter Infiltration").
3. **Approve all N fast** with an **in-page async auto-approve loop** (Playwright `browser_evaluate`) so the
   runs overlap into a real queue — this is far faster and more reliable than one approval per tool call:
   ```js
   async () => {
     let clicks = 0; const t0 = Date.now();
     while (Date.now() - t0 < 50000) {
       const b = Array.from(document.querySelectorAll('button'))
         .find(x => (x.textContent||'').trim() === 'Approve' && x.offsetParent !== null);
       if (b) { b.click(); clicks++; await new Promise(r=>setTimeout(r,400)); }
       else   { await new Promise(r=>setTimeout(r,700)); }
     }
     return clicks;
   }
   ```
   Result: **5 running + 5 queued**, all Helm-created.
4. **Read immediately** — once the turn ends and the input unlocks, send "list all queued tests…". The queue
   drains 5-at-a-time over a few minutes, so the read must be prompt.
5. **Two-legged verify** — cross-check Helm's reply against the **independent** orchestrator queue read
   (`GET /api/orch/v4/accounts/<acct>/queue` → `data.queue[]`), NOT against `get_tests` (that would be
   circular).

### 4.4 RESULT — feature verified end-to-end through Helm
Helm, calling our in-console `get_tests` (mcp-proxy @ safebreach-mcp `7225955`), returned **5 queued tests**
with `status=queued` and Queue Positions 1–5:
```
Queue Position | Test Name         | Test ID            | Status
1              | Queue Fill Run 6  | 1785233359209.58   | queued
2              | Queue Fill Run 7  | 1785233363615.64   | queued
3              | Queue Fill Run 8  | 1785233370407.70   | queued
4              | Queue Fill Run 9  | 1785233374468.76   | queued
5              | Queue Fill Run 10 | 1785233377070.82   | queued
```
The planRunIds + order + statuses matched the backend orchestrator `/queue` read taken seconds earlier,
**exactly**. Baseline (empty console) correctly showed 0 queued. Before SAF-33511, `get_tests` returned
nothing for queued tests at all. Evidence:
`test-results/evidence/saf-33511-helm-queued-tests-clean.png`.

### 4.5 Honest correction (a compromise I made and then fixed)
My **first** "successful" attempt saturated the queue **out-of-band** — a direct `quick_run` burst rather
than through Helm — and by the time Helm read, only **1** of the 5 queued tests remained. I initially
presented that as the result; that was a **compromise in interpretation** and not the clean Helm-driven E2E
the ticket asked for. The re-run in §4.3/§4.4 created the queue **entirely via Helm** and read **5/5** matching
the backend. **Lesson for `run-helm-tests`:** the saturation must be part of the observed Helm flow, and the
read must happen while the queue is genuinely deep — not reconstructed after the fact.

---

## 5. AWS / automation-pytest preflight (needed before run-helm-tests can even collect)

Running the automation-repo Helm pytest suite (`pytest --collect-only`) crashed twice before it could
collect — worth documenting precisely because the reference's remediation was incomplete:

1. **`UnauthorizedSSOTokenError` during `pytest_configure`.** The conftest's `AwsClient(aws_profile="dev")`
   first tries assume-role `automation-user` (via the default cred chain) and, on failure, falls back to
   `boto3.Session(profile_name="dev")` — which is an **expired SSO** profile → hard crash, even for a test
   needing no AWS secrets. My **ambient** SSO creds (env vars, account `400469752855`) were valid, but that
   is a different path.
   - **Remediation that the reference gets half-right:** point pytest at an isolated static-creds file built
     from the ambient env creds. But setting only `AWS_SHARED_CREDENTIALS_FILE` was **ignored** — because
     `~/.aws/config` defines `[profile dev]` as an **SSO** profile and SSO config wins. You must **also** set
     an isolated `AWS_CONFIG_FILE` where `dev` is a plain profile:
     ```bash
     printf '[profile dev]\nregion=us-east-1\noutput=json\n' > /tmp/sb-cfg
     printf '[dev]\naws_access_key_id=%s\naws_secret_access_key=%s\naws_session_token=%s\n' \
       "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" "$AWS_SESSION_TOKEN" > /tmp/sb-creds
     export AWS_CONFIG_FILE=/tmp/sb-cfg AWS_SHARED_CREDENTIALS_FILE=/tmp/sb-creds   # pytest process only
     ```
2. **`ConnectionError` in `pytest_sessionstart` → `create_apikey`.** After the AWS fix, collection still
   crashed because the conftest mints an api key against the target console at session start and didn't know
   which console. **Fix:** pass `--mgmt_address saf-33511.dev.sbops.com --account_id 3475543660
   --api_token <token>` to the pytest run — the conftest then **skips** `create_apikey` and uses them
   directly. After both, `pytest --collect-only` succeeded (2 template tests collected).
- **Fix:** see bake-in #3.

---

## Recommended skill edits (bake-in list — mapped to target file + exact change)

Each item: **target file → concrete change**. Ordered by impact. Paths are under the plugin roots in §1.

1. **`deploy-mcp-server-under-test` SKILL.md (Steps 5–6).** The deploy + verify assume the sb-env MCP
   `mgmt_docker pull_image`/`inspect` work; on an SSM-only dev console they fail with
   `Unsupported connection type: ssm`. **Add a first-class SSH fallback** for the deploy:
   `ssh -i <key> ubuntu@<mgmt-ip> "sudo /home/safebreach/support/dpull mcp-proxy <sha>"`. **Change the verify**
   from an `mgmt_docker inspect` tag-match to the in-container check
   `sudo docker exec mcp-proxy pip freeze | grep safebreach-mcp` (proves the exact commit) — the tag-match
   FAILS on success because `dpull` retags locally and removes the SHA tag. *(Single biggest friction.)*

2. **`references/jenkins-access.md`.** Every `tree=…[…]` example must show **URL-encoded brackets**
   (`%5B`/`%5D`); raw brackets return an empty/non-JSON body via curl. E.g.
   `tree=property%5BparameterDefinitions%5Bname,choices%5D%5D`.

3. **`references/automation-pytest-preflight.md` §2.** The isolated-creds remediation is incomplete: setting
   only `AWS_SHARED_CREDENTIALS_FILE` is **ignored** when `~/.aws/config` defines the profile (`dev`) as SSO
   (SSO wins). Must **also** set an isolated `AWS_CONFIG_FILE` with `[profile dev]\nregion=us-east-1` (no
   `sso_session`). Document both env vars together (see §5 snippet). **Also** document the `create_apikey`
   bootstrap: pass `--mgmt_address`, `--account_id`, `--api_token` to the pytest run to skip the
   `pytest_sessionstart` `create_apikey` `ConnectionError`.

4. **`create-validate-environment` Step 6 (and any `aws … $ids` snippet in the provisioner skills).** The
   shell here is **zsh**, which does not word-split unquoted vars, so `--resources $ids` sends one bad arg.
   Use `${=ids}` (zsh split) or an explicit per-id loop, or note the bash-ism. Bit me twice (tagging + cancel).

5. **`run-helm-tests` SKILL.md — add a "queued-state / write-action case" subsection.**
   - A *queued-state* data-query case is NOT the standard seeded-`executionsHistory` shape: queue depth is
     live and ephemeral and can only be produced by **submitting real runs**. `references/executions-history-seed.md`
     does not help here — say so.
   - The Helm **write-action approval gate serializes submissions** and **locks the chat input for the whole
     run turn**. The working recipe (see §4.3): (a) reset the queue to empty; (b) one prompt to run
     **N > 5** tests using a scenario that yields sims on the built sims; (c) an **in-page async auto-approve
     loop** (poll+click `Approve` every ~400ms for ~50s) to approve all N fast so they overlap; (d) once the
     turn ends and input unlocks, immediately send the "list queued tests" prompt and read while the queue is
     still deep (drains 5 at a time).
   - **Two-legged cross-check against the orchestrator `/queue` read**
     (`GET /api/orch/v4/accounts/<acct>/queue` → `data.queue[]`), NOT against `get_tests` (circular).
   - Note the honest-accounting rule: out-of-band saturation + late read is NOT a clean pass (see §4.5).

6. **`design-test-environment` / `run-helm-tests` env contract.** A Helm queued-state case needs **≥1
   simulator AND a scenario that actually produces simulations on it**; several OOB scenarios yield 0 sims on
   a minimal 2-sim console. Have the design pick/verify a sim-producing scenario up front.

7. **`references/*` SbActions + REST guidance.** The referenced helpers
   (`conf_actions.enable_ai_features`, `config_actions.get_connected_simulators`, `wait_for_all_services`) are
   **not** direct `SbActions` attributes — show the correct accessor (they live on `ConfigActions` /
   `ConfigClient`) or, simpler and stable, point at the REST endpoints:
   - enable a flag: `POST /api/config/v1/accounts/<acct>/settings` body `{"key":…,"value":"true"}` (string!);
   - list nodes: `GET /api/config/v1/accounts/<acct>/nodes?details=true`.
   - `create_apikey(...)` returns a **dict** — token is `["key"]`, account is `["accountId"]`, not a string.
   - To dogfood safebreach-mcp functions standalone, use `SAFEBREACH_ENVS_FILE` + an `env_var` provider token
     and leave `SAFEBREACH_LOCAL_ENV` **unset** (see §3.6).

8. **`running-phase-tests` SKILL.md.** For the `safebreach-mcp` repo, the phase's unit tests run via
   `uv run pytest` — not jest/vitest and not the automation-repo pytest — and the orchestrator's dispatch
   table has no clean mode for a standalone-pytest repo. Either add a `uv-pytest` source-repo dispatch mode,
   or document that safebreach-mcp unit suites are run directly (`uv run pytest <dirs> -m "not e2e"`) and only
   the Helm e2e dispatches to a runner (`run-helm-tests`).
