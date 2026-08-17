# Environment — SAF-32798

**Env name:** pentest-saf-32798   **Mgmt URL:** https://pentest-saf-32798.dev.sbops.com
**Owning ticket:** SAF-32798   **Created:** 2026-08-17   **sb_ticket tag:** SAF-32798
**Offering:** Propagate (pentest)   **Retention:** terminate_at 2026-08-20 16:05 (72h), TF=eod-off
**Credentials:** mgmt login + minted admin API key are in the build (not stored here). No secrets in this file.

## Infrastructure
| Resource | Instance ID | Role / OS | PrivateIP | sb_ticket | Verify |
|----------|-------------|-----------|-----------|-----------|--------|
| management | i-08e7a4c3e8f7b6160 | management | 200.11.117.75 | ✅ | up (console reachable) |
| DC | i-02285c9b6ee7f8d4c | windows-server-dc (pentest.lab) | 200.11.205.10 | ✅ | running, domain-joined |
| patient-zero | i-021c35211b5355592 | windows-11 (SafeBreach agent, master) | 200.11.205.248 | ✅ | running, domain-joined |

No victim hosts, no cloud sim (data-query Helm case; minimal pentest topology).

## Console configuration applied (verified present)
- **Helm / AI-agent flags (all `true`):** enableAiFeatures, enableAmazonBedrock, feature.aiAgentChat, enableAiAgentActions.
- **SIEM/TI connectors (installed + enabled):**
  - `tiv2mockconnector` id `syod-ZA8PYm-XzM2fWTY2` (isTiV2 TI — mock, no creds) → get_ti_integrations target.
  - `alienvault` id `JrXF3jzy0JR-pL2kg2lFA` (isTiV2 TI + sensitive `apiToken`) → get_ti_integrations + redaction target.
  - `emailnotifications` (`email_default`) — default, present.
- Splunk connector **dropped**: SSM `/automation/splunk` path empty in dev (skill-feedback.md). alienvault + tiv2mock cover the TI + redaction assertions.

## Artifacts under test (DEPLOY MAP status)
| Artifact | Target | Status |
|----------|--------|--------|
| safebreach-mcp `feature/SAF-32798` (HEAD `8906def`) → mcp-proxy branch `feature/SAF-32798-mcp-proxy-repin` (`b28face`) | console `mcp-proxy` (:4150) | ✅ **deployed + verified** |

**Deploy evidence:** dev-ECR image `mcp-proxy:b28face` (digest `sha256:7542…`) pulled via `dpull`;
running container pip ref = `safebreach-mcp-server @ git+https://github.com/SafeBreach/safebreach-mcp.git@8906def`
(the exact feature-branch commit); `SIMP service ready`, server on :4150, no errors.

## Status
built + console-configured + **MCP feature build deployed & verified** → run-helm-tests (T-18,T-19,T-35–T-39) next.
