# Environment — SAF-33511

**Env name:** saf-33511   **Mgmt URL:** https://saf-33511.dev.sbops.com
**Owning ticket:** SAF-33511   **Created:** 2026-07-28 (build create-custom-environment #52475)
**sb_ticket tag:** SAF-33511   **Account ID:** 3475543660   **Retention:** terminate_at 2026-07-30 09:12 UTC (48h)
**Credentials:** mgmt login (devops@safebreach.com) + minted admin API key — NOT stored here (scratchpad only);
Bedrock/automation via ambient dev SSO (account 400469752855).
**Offering:** Validate (BAS)   **Builder:** create-custom-environment (team DevOps, craft_branch master, online)

## Infrastructure
| Resource | Instance ID | Role / OS | sb_ticket | Verify |
|----------|-------------|-----------|-----------|--------|
| management | i-07e7dfacbe8dfe318 | management (t3.xlarge) | ✅ | up (HTTP 302) |
| cloud-sim | i-06d4f50da43688318 | cloud simulator (t3.medium) | ✅ | connected + enabled |
| saf-33511-ubuntu22 | i-044ed65d2e7211c34 | EP simulator / ubuntu22 (t3a.medium) | ✅ | connected + enabled |

## Console configuration applied
- AI features + AWS Bedrock: ✅ `enableAiFeatures=true`, `enableAmazonBedrock=true` (verified)
- Helm flags: ✅ `feature.aiAgentChat=true`, `enableAiAgentActions=true` (verified)
- Cloud integrations / EDR-SIEM / email / impersonated users / RBAC: none (not needed)

## Artifacts under test (verified running tags)   — see references/mcp-artifact-under-test.md
| Repo | Service/image | Expected ref | Running (verified) | OK |
|------|---------------|--------------|--------------------|----|
| SafeBreach/safebreach-mcp (→ mcp-proxy) | `mcp-proxy` service | safebreach-mcp @ 7225955 | container pip ref `safebreach-mcp-server @ ...@7225955f1a43718e440578fa37d53503064bb58a`; image digest sha256:0fca2acf…; SIMP ready on :4150; sbmcp-proxy active | ✅ |

- mcp-proxy repin branch: `feature/SAF-33511-mcp-proxy-repin` (HEAD 94a9793); build mcp-proxy #2 SUCCESS; deployed
  via `dpull` over SSH (sb-env MCP SSM-blocked on this env).
- Management/UI/orchestrator/data services run stock develop by design (feature is MCP-only).

## Status
**torn-down 2026-07-28T13:36 UTC+3** — Helm E2E completed successfully (queued tests verified via the AI chat,
see test-results/phase-5.md), then all 3 instances terminated
(i-07e7dfacbe8dfe318, i-06d4f50da43688318, i-044ed65d2e7211c34). No env-specific security groups or external EDR
records existed. Re-scan by `sb_ticket=SAF-33511` confirms nothing remains.
