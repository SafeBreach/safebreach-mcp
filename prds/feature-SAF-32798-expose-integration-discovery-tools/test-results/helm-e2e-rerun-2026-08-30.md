# Helm E2E Rerun — SAF-32798 new contract (2026-08-30)

Rerun of the full test-plan against the **current** 3-tool `category_filter` design (commit `f6402b0`),
after the PR review reshaped the tools (dropped `get_ti_integrations`, added derived `categories` +
`category_filter`, envelope + `redacted_fields`, filter rejection).

## Environment (provisioned fresh for this rerun)
- **Console:** `saf-32798.dev.sbops.com` — fresh **Validate** (management-only), Jenkins build
  `create-custom-environment#54935` SUCCESS. Tagged `sb_ticket=SAF-32798`, stop_at/terminate_at set
  (auto-reaps 2026-08-31 13:15).
- **MCP build under test:** `mcp-proxy` rebuilt (`mcp-proxy#3`, branch `feature/SAF-32798-mcp-proxy-repin`
  @ `8c3a647`) repinned to safebreach-mcp `f6402b0`, deployed via `sbcli docker dpull`. **Verified live:**
  container pip ref = `safebreach-mcp-server @ …@f6402b0…`, `SIMP service ready`.
- **AI/Helm flags** enabled (`enableAiFeatures`, `enableAmazonBedrock`, `feature.aiAgentChat`,
  `enableAiAgentActions`, `feature.performActionsByAiAgent`).
- **Seeded integrations:** `emailnotifications` (workflow), `tiv2mockconnector` (ti/isTiV2),
  `vmmockconnector` (vulnerability_management/isVm, with a `proxyPass` secret), `mockconnector`
  (security_control).

## Automated lanes — GREEN (new contract)
- Unit (`safebreach_mcp_config`): **145 passed**.
- Live API-contract e2e (`test_e2e_integrations.py` vs pentest01): **4 passed**.

## Helm protocol-level lane — PASS (in-console, via the mcp-proxy gateway Helm uses)
Driven with an MCP streamable-http client **inside the container**, through the proxy endpoint
`127.0.0.1:4150/api/mcp/configuration` (auth: x-apitoken) → `configuration` server (deployed f6402b0),
against the live seeded backend:

| Check | Result |
|-------|--------|
| Tool inventory | 7 tools; **`get_ti_integrations` absent** ✓ |
| `get_installed_integrations(category_filter='ti')` | `tiv2mockconnector` → `categories:['ti']` ✓ (replaces the removed TI tool) |
| `get_installed_integrations(category_filter='vulnerability_management')` | `vmmockconnector` → `categories:['vulnerability_management']` ✓ (VM now listable) |
| `get_installed_integration` (VM connector) | envelope `{console, integration_id, integration, redacted_fields}`; **`redacted_fields:['proxyPass']`** — secret redacted end-to-end ✓ |
| `get_integrations(ti_only=True)` | rejected: "The 'ti_only' filter was removed. Use category_filter='ti' … Valid categories: …" ✓ |
| `get_integrations(category_filter='not_a_category')` | rejected: "Invalid category_filter … Valid categories: custom, siem, security_control, ti, …" ✓ |

This exercises the deployed feature build over the exact protocol path Helm uses (agent → mcp-proxy →
config server), confirming the new contract works live in-console including redaction.

## AI-agent natural-language judge harness — PASS (4/4)
Authored `test_helm_integration_discovery_new_contract.py` (ai/ dir, new contract) and ran it live via
pytest+Playwright driving the console AI agent (Helm), each answer scored by the Bedrock LLM-judge
(`claude-haiku-4-5`) against the authoritative backend. **4 passed in 93s.**

| T-case | Prompt → Helm | Judge | Evidence |
|--------|---------------|-------|----------|
| TI via category | "which installed integrations are TI feeds?" | **9/10** | listed exactly `TI Mock Feed` (tiv2mockconnector); no non-TI, no secrets |
| VM via category | "which are Vulnerability Management connectors?" | **9/10** | listed exactly `VM Mock Scanner` (vmmockconnector) — VM now answerable (was impossible pre-PR) |
| Redaction (highest-severity) | "show the full config of VM Mock Scanner" | **9/10** | `proxyPass` → `@enc:SENSITIVE_FIELD`, `redacted_fields` array shown, **no `$PAM:`/secret** (judge + deterministic assertion) |
| Catalog | "what connector TYPES are available?" | **9/10** | real SafeBreach types (arcsight, carbonblack, checkpoint…); no invention |

Screenshots: `test-results/evidence/helm__newc_*.png`.

### Conftest blocker workaround (the known SAF-33511 remediation)
The automation conftest's AWS-auth/`create_apikey` crash was resolved exactly as in the prior cycle:
extract **boto3 frozen credentials** from the `dev` SSO session → write an isolated `AWS_CONFIG_FILE`
(+`AWS_SHARED_CREDENTIALS_FILE`) with `dev` as a *plain* profile, and pass
`--mgmt_address/--account_id/--api_token` so the conftest skips `create_apikey`. (This CLI lacks
`aws configure export-credentials`, so boto3 `get_frozen_credentials()` is the extraction path.)

## Verdict
SAF-32798's new 3-tool `category_filter` contract is validated end-to-end for this rerun: automated
(145 unit + 4 live e2e) → deployed & verified live in-console (`@f6402b0`) → in-console MCP protocol lane
(via the mcp-proxy gateway) → AI-agent NL judge lane (4/4 @ 9/10), with redaction proven through the full
protocol. Environment torn down after the run.
