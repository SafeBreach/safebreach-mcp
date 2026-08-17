# Skill / KB Feedback — SAF-32798 mission (running log)

Constructive feedback captured live for improving the skills + knowledge bases exercised in this
mission. Grouped by skill/KB. Severity: 🔴 blocked work · 🟠 cost time · 🟡 papercut. Keep appending.

> A separate JIRA bug **SAF-35147** already covers the tdd-implementing-prd Manual-lane defect. This
> file is the broader running log across the whole chain (planning → TDD → provisioning → deploy → Helm).

## tdd-implementing-prd  (→ SAF-35147, keep for context)
- 🔴 Manual/AI-executed test lane silently skipped when the caller hand-rolls `pytest` instead of
  invoking `running-phase-tests`; no downstream gate enforces the phase sign-off artifact. Fixes
  (4 defects) specified in SAF-35147.
- 🟠 Even the after-the-fact "manual" execution ran at the wrong seam (direct `sb_*` calls, same as the
  automatic e2e) because the orchestrator — which owns runner selection by (Level × Execution × Env) —
  was bypassed. Lesson: never hand-roll; the orchestrator picks the runner.

## running-phase-tests
- 🟡 No wired dispatch row for a **non-Helm, non-attack e2e in a standalone uv-pytest repo** (our
  T-14..T-17 hit `sb_*` directly against a live console). It falls under "source-repo uv-pytest (-m e2e)"
  by improvisation. Consider an explicit row / note so it's not ambiguous.
- 🟡 For a headless-MCP repo, `Manual → sb-ui:manual-ui-testing` is the default but is a browser/UI
  runner and N/A here; the true manual-e2e runner is `run-helm-tests`. The (Level×Exec×Env) table
  could special-case "console-env Manual on a headless MCP → run-helm-tests".

## automation-capabilities.md  /  console.md  (driving SbActions)
- 🔴 **Undocumented `Config.data` bootstrap.** Driving `SbActions(mgmt, token)` is NOT enough — the
  action clients build request URLs from `Config.data['management_endpoint_address']`, so **every** call
  raises `KeyError: 'management_endpoint_address'` unless you first set
  `Config.data['management_endpoint_address'] = <mgmt>`. Cost a full failed config run (~5 min + retries).
  **Fix:** automation-capabilities.md should show the minimal bootstrap snippet
  (`from src.automation_config import Config; Config.data['management_endpoint_address']=mgmt`) before the
  `SbActions` example, and note that SSM-backed creds (SPLUNK_*, etc.) must also be loaded into
  `Config.data`, they are not auto-populated.
- 🟠 **Splunk cred location wrong/unconfirmed.** console.md §3 states creds at SSM `/automation/splunk`
  (`SPLUNK_BASE_URL/USER/PASSWORD`), but `aws ssm get-parameters-by-path --path /automation/splunk`
  returns empty in dev. The real path/param names (or the Config loader that populates them) is
  unconfirmed. **Fix:** verify and correct the exact SSM path, or document the Config loader that fills
  `Config.data['SPLUNK_*']`. (Worked around by dropping Splunk; alienvault + tiv2mock cover the assertions.)
- 🟡 Good news worth keeping: `siem_actions.install_ti_v2_mock_connector()` and the
  `INTEGRATION_ALIENVAULT_PROVIDER_DATA` constant are ready-made and exactly right for a TI/redaction
  target — console.md could point to them explicitly as the "cheap TI connector for tests" recipe.

## run-helm-tests / automation-pytest-preflight.md
- 🔴 **automation venv missing `mcp` SDK** — `helm/conftest.py` does `from mcp import ClientSession` +
  `from mcp.client.streamable_http import streamablehttp_client`; the venv had no `mcp` at all, and a
  plain `pip install mcp` pulled a version too old to have `streamablehttp_client`. The helm/ suite
  can't even collect until `mcp` is present at the right version. **Fix:** pin `mcp>=<ver with
  streamablehttp_client>` in the automation requirements, and add this exact signature +
  remediation to `references/automation-pytest-preflight.md`.
- 🟠 `pytest --collect-only` on the ai/ suite runs **>120s** (heavy work in conftest at collection
  time). Preflight "smoke collect" guidance should budget for this / use a tighter target, else the
  preflight itself times out.
- 🟡 (pending) Open question the runner must answer: does **Helm's tool registry actually expose newly
  added MCP tools** (my 4 integration-discovery tools) to the chat, or is there a curated allowlist?
  If the latter, exposing a new safebreach-mcp tool needs a corresponding Helm/ui-server allowlist
  change — worth documenting as a dependency for "new MCP tool → testable via Helm".
- 🔴 **conftest AWS path crashes on expired `dev` SSO even with valid ambient creds.** The root
  conftest's `pytest_configure` loads `/automation/` SSM via `AwsClient(aws_profile="dev")`, which
  forces the `dev` SSO profile; with SSO expired it hard-crashes `UnauthorizedSSOTokenError` before any
  test — despite valid ambient env creds. This is documented in `automation-pytest-preflight.md`
  (isolated static-creds file: write env creds to `/tmp/sb-creds` under `[dev]` + a non-SSO
  `AWS_CONFIG_FILE`), and the doc itself notes the **proper fix**: `AwsClient` should fall back to
  `boto3.Session()` ambient creds before a broken named profile. Strongly second that repo fix — this
  is the single biggest run-helm-tests footgun and cost the first live run.
- 🟠 **Root conftest requires `--mgmt_address` + `--password` (or `--api_token`) to even collect/bootstrap.**
  A bare `pytest --collect-only` fails with a retried `TypeError` (empty `management_endpoint_address`).
  Preflight should pass these up front; `run-helm-tests` Step 1 should state them as required pytest opts.
- 🟡 The `create_apikey()` returning a **dict** (`key["key"]`/`key["accountId"]`, not a bare token) is
  noted in run-helm-tests Step 1 but NOT in console.md/automation-capabilities — add it there too, since
  any SbActions bootstrap outside the conftest hits it (cost my first console-config run a 401).
- 🟠 **Screenshot evidence is lost when a read-only data-query test is authored in the parent `ai/` dir.**
  The skill (correctly) says to author read-only cases in `ai/` to dodge the `helm/` write-tools autouse
  gate — but the `helm__<label>.png` **screenshot fixture also lives in `helm/conftest.py`**, so a test
  in `ai/` produces transcript+judge evidence but **no screenshots** unless it calls
  `sb_pages.ai_chat_page.page.screenshot()` itself. The user caught this. **Fix:** run-helm-tests Step 5
  should explicitly require the authored test to capture per-answer screenshots even in `ai/` (or lift a
  screenshot helper to the parent `ai/conftest.py`), so evidence is complete regardless of dir.

## run-helm-tests — provenance assertion for MIGRATION tests (important)
- 🟠 **A Helm test for a *migrated* tool must assert tool PROVENANCE, not just a correct answer.** Here
  the SIEM MCP still exposes the same four tools, so "Helm answered correctly" does NOT prove the NEW
  safebreach-mcp tool ran — the legacy SIEM-MCP copy could have served it (false positive). I only
  checked this after the user asked. **Fix:** for a migration/dedup case, run-helm-tests should (a) grep
  the `mcp-proxy` log for the `[<server>]` that handled the `CallToolRequest`, and/or (b) assert a
  discriminating field in the tool output (here: snake_case `*_in_page`/`applied_filters` vs the TS
  `installedIntegrations`/`totalCount`). Add "verify which MCP served the call" to Step 5 evidence when
  the case is a migration. (Verified here: `[configuration]` server + snake_case envelope = ours.)

## SUCCESS — what worked well (keep)
- The pattern-library template `test_helm_simulation_search.py` (parent `ai/` dir, data-query) was an
  excellent, copyable model — `AiChatPage` + `claude_judge` + backend cross-check via `Config.data`.
- **Resolved unknown:** Helm **auto-exposes newly-deployed safebreach-mcp tools** — no ui-server/Helm
  allowlist change was needed. The AI agent invoked all 4 new tools and the judge scored 9–10/10; the
  security-critical redaction held end-to-end (screenshot `helm__redaction.png`). Worth documenting as
  the happy-path: "add a public safebreach-mcp tool → deploy via mcp-proxy → immediately Helm-testable."
- `deploy-mcp-server-under-test` worked cleanly first try (repin → build → SSH `dpull` → pip-ref verify);
  the SSH `dpull` fallback + pip-ref verify were exactly right for the SSM-only pentest console.

## design-test-environment / provision-feature-environment
- 🟡 A pure **data-query Helm case** is forced onto a full **pentest** topology (DC + patient-zero)
  solely because `run-helm-tests` requires a pentest console — heavier/costlier than the feature needs.
  Worth a note in offerings.md, or letting run-helm-tests accept a Validate console for data-query cases.
- 🟡 The console-config step (instantiate Phase 4) is "drive automation" freeform; there's no reusable
  "apply env-design console config" helper, so every caller re-implements apikey-mint + Config bootstrap
  + connector loop and can hit the Config.data footgun above. A small helper would prevent that.

## Environment / tooling papercuts (mostly already in memory)
- 🟡 AWS: ambient SSO env-creds were valid while `--profile dev` was expired — lead with the ambient
  chain (no `--profile`). Also `$P="--profile dev --region us-east-1"` unquoted does NOT word-split
  under zsh (passes as one arg → "Unknown options"). Use inline flags or `${=P}`. (See
  [[feedback_bash_sandbox_path_and_network]].)
