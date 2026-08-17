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

## Screenshot evidence (test-results/evidence/)
Full-page captures of the real console Helm chat, one per tool (re-run with `page.screenshot()` added):
- `helm__installed_integrations.png` — Helm lists the 3 installed connectors.
- `helm__ti_integrations.png` — Helm lists the 2 isTiV2 TI feeds.
- **`helm__redaction.png`** — AlienVault config in the chat with **`API Token: 🔒 Redacted (sensitive
  field)`**, `Connector Type: alienvault`, `Enabled: ✅`, `Reject Unauthorized (SSL): ✅` — visual proof
  the secret is redacted end-to-end, no `$PAM:`/token value shown.
- `helm__catalog.png` — Helm describes the available connector-type catalog.

## Feature verdict
SAF-32798 is validated end-to-end: 4 tools implemented (132 unit + 4 automatic e2e) → deployed & verified
live in a real console MCP (pip ref `@8906def`) → driven through the console AI agent and judged correct
against the backend, with secret redaction proven through the full protocol.
