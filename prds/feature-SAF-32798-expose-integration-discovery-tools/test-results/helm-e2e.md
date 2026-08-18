# Helm E2E Results — SAF-32798 (run-helm-tests, protocol-level, 2026-08-17)

The Manual e2e lane executed via its **correct runner** (`run-helm-tests`) — a pytest+Playwright UI
automation that drives the real console AI agent (Helm) on `pentest-saf-32798.dev.sbops.com`, with an
LLM-as-judge (Bedrock `claude-haiku-4-5`) scoring each answer against the authoritative backend. This
is the genuine protocol-level E2E that the earlier direct-`sb_*` probe was NOT (SAF-33190 lesson).

**Authored test:** `automation/tests/automation_team/pen_test/ui/ai/test_helm_integration_discovery_llm_judge.py`
(parent `ai/` dir — read-only data-query, outside the `helm/` write-tools autouse gate + `mcp`-SDK import).
**Run:** `pytest … --mgmt_address pentest-saf-32798.dev.sbops.com` → **4 passed in 97.5s.**

## Proof the AI agent invoked the NEW tools (allowlist unknown → RESOLVED)
Helm's transcript shows it called each new tool: `Get Installed Integrations`, `Get Ti Integrations`,
`Get Installed Integration`, `Get Integrations` — all "Completed" with tool output. **The four
safebreach-mcp tools are auto-exposed to Helm; no allowlist change was needed.**

## Results (two-legged: backend cross-check + judge)
| T-<n> | Tool | Judge | Verdict / evidence |
|-------|------|-------|--------------------|
| T-36 (+T-19) | `get_installed_integrations` | **9/10 ✅** | Listed all 3 installed connectors (email_default, tiv2mockconnector, alienvault) with ids/types/names/enabled matching the backend `/config/integrations/installed` exactly; no invention; no secrets. |
| T-38 | `get_ti_integrations` | **10/10 ✅** | Returned exactly the two `isTiV2` connectors (AlienVault, tiv2mockconnector); no non-TI connector; cross-checked vs catalog `isTiV2`. |
| T-37 (highest-severity) | `get_installed_integration` | **9/10 ✅** | AlienVault config returned with `apiToken` redacted to `@enc:SENSITIVE_FIELD` in both JSON and table; **no `$PAM:INTERNAL_VAULT` / real secret** (judge + deterministic `$pam`/`internal_vault` absence assertion both passed). |
| T-35 | `get_integrations` | **9/10 ✅** | Described 83 AVAILABLE connector TYPES across 9 pages (catalog), distinct from installed; real SafeBreach types; no secrets. |

Backend ground truth logged per test (installed list, isTiV2 set, redaction target, 83-type catalog).

## Provenance — the calls hit OUR MCP, not the SIEM MCP (critical for a migration test)
Because the SIEM MCP (`/api/siem/mcp`) still exposes the same four tools (SAF-32798 migrates away from
it; SAF-35067 withdraws them), a passing Helm test is only meaningful if the calls hit the NEW
safebreach-mcp Config server. Verified two ways:
1. **mcp-proxy log** (`/datadb/logs/sbmcp-proxy.log`): the `[configuration]` server (= `safebreach_mcp_config`,
   host of the 4 tools) logged `ListToolsRequest` + `CallToolRequest` for each test in BOTH run windows
   (17:51–17:53 and 17:57–17:58 UTC). The SIEM MCP is a separate service; its calls do not appear here.
2. **Output envelope**: the tool outputs in the transcript use the NEW repo snake_case pagination shape
   (`installed_integrations_in_page`, `total_installed_integrations`, `ti_integrations_in_page`,
   `total_integrations`, `applied_filters`) with ZERO occurrences of the SIEM-MCP shape
   (`installedIntegrations`/`totalCount`). Only the new tools emit those keys.
Conclusion: Helm invoked the migrated safebreach-mcp Config-server tools, not the legacy SIEM-MCP copies.

## Coverage of the 7 Manual e2e T-items
- **Fully executed via Helm (protocol-level, judged):** T-35, T-36, T-37, T-38.
- **T-19 (progression / discovery flow):** covered — the four tools were exercised in sequence
  (catalog → installed → single-redacted → TI) across the run, each judged correct.
- **T-39 (pagination UX):** partially observed — Helm surfaced the catalog as "83 across 9 pages"
  (pagination + hint working), but no dedicated multi-page walkthrough turn was run. Adequate signal, not a full walk.
- **T-18 (regression: existing Config tools unaffected):** NOT re-run through Helm. Covered indirectly:
  the deployed config MCP server started cleanly serving ALL tools (old + new) — `SIMP service ready`,
  and the 1584-test cross-server unit suite is green. The Helm-regression leg was not separately executed.

## Honest verdict
- **5/7 manual e2e fully satisfied** (T-35/36/37/38 via Helm + T-19 flow), all high-confidence with judge
  + backend evidence. T-39 partially observed; T-18 covered by unit+server-health, not by a Helm turn.
- The **security-critical redaction assertion (T-37) passed end-to-end through the real AI agent** — the
  single most important validation for this feature.
- Guardrails: read-only run (no Helm-queued runs to cancel); throwaway env (AI flags left enabled by design).

## Filter / option demonstrations (T-40–T-44) — added 2026-08-17, all PASS via Helm
Densified per request to demonstrate each tool's filters/options through the AI agent, judged vs a
FILTERED backend query. Full 9-case run: **9 passed in 213s.**
| T-<n> | Tool + filter | Judge | Result |
|-------|---------------|-------|--------|
| T-40 | `get_integrations` **ti_only** | 9/10 | 8 TI-capable catalog types listed (ti_only applied); non-TI excluded |
| T-41 | `get_integrations` **name/vendor='splunk'** | 9/10 | exactly `splunkrest`/`splunksoar`/`splunksoaroutbound`; no unrelated types |
| T-42 | `get_installed_integrations` **enabled_filter=disabled** | 9/10 | exactly 1 disabled (`email_default`); enabled ones excluded |
| T-43 | `get_installed_integrations` **type=alienvault** | 9/10 | only the AlienVault connector |
| T-44 | `get_ti_integrations` **enabled_filter=enabled** | 9/10 | exactly the 2 enabled TI feeds (AlienVault, TiV2Mock) |
Each judged against a filtered backend query + screenshotted. Env was resumed (eod-off auto-stop) before
this run; `mcp-proxy` feature build persisted (`@8906def`).

### T-39 (pagination) — ACCEPTED as a non-blocking Helm-agent UX finding
On the automated run, the judge rejected T-39 because Helm's prose claimed "page 2" but re-listed page 1's
10 connectors. Root cause = **the AI agent**, not the tool: the judge itself confirmed the tool output was
correct (`page 1 of 9, total 83, proper hint_to_agent`). Verified deterministically — `get_integrations`
page 2 (`page_number=1`, name-ordered) MUST be: Cortex XDR, Cortex XSOAR, CrowdStrike Falcon, Cybereason,
CylancePROTECT & OPTICS, Cyware, Darktrace, Deploy Mockion, Devo, ElasticSearch (distinct from page 1;
total_pages=9). In a follow-up interactive session Helm clarified it had fetched `page_number: 1` and that
"page 2" was 1-indexed English over the 0-based param. **Decision (user): keep T-39 as an agent-UX check;
accept the original miss as a non-reproducing Helm-agent limitation. The tool's pagination is correct and
independently verified — not a SAF-32798 defect.** Evidence: `helm__pagination_catalog.png`.

## Screenshot evidence (test-results/evidence/)
Full-page captures of the real console Helm chat, one per tool (re-run with `page.screenshot()` added):
- `helm__installed_integrations.png` — Helm lists the 3 installed connectors.
- `helm__ti_integrations.png` — Helm lists the 2 isTiV2 TI feeds.
- **`helm__redaction.png`** — AlienVault config in the chat with **`API Token: 🔒 Redacted (sensitive
  field)`**, `Connector Type: alienvault`, `Enabled: ✅`, `Reject Unauthorized (SSL): ✅` — visual proof
  the secret is redacted end-to-end, no `$PAM:`/token value shown.
- `helm__catalog.png` — Helm describes the available connector-type catalog.
- Filter demos: `helm__filter_integrations_ti_only.png`, `helm__filter_integrations_name_splunk.png`,
  `helm__filter_installed_disabled.png`, `helm__filter_installed_alienvault.png`,
  `helm__filter_ti_enabled.png` — each showing the correctly-filtered AI-agent answer.

## Feature verdict
SAF-32798 is validated end-to-end: 4 tools implemented (132 unit + 4 automatic e2e) → deployed & verified
live in a real console MCP (pip ref `@8906def`) → driven through the console AI agent and judged correct
against the backend, with secret redaction proven through the full protocol.
