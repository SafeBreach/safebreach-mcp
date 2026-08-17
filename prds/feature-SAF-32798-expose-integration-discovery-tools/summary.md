# Ticket Summary: SAF-32798

## Overview
**Mode**: Improving existing
**Project**: SAF (Task, Medium, label `CTEM-dev`)
**Reporter**: Gal Turgeman · **Assignee**: Yossi Attas
**Repositories**:
- `/Users/yossiattas/Public/safebreach-mcp` (Python — migration target)
- `/Users/yossiattas/projects/integrations/siem` (TypeScript — source of the tools)

---

## Current State
**Original summary**: Expose integration-discovery tools (getIntegrations, getInstalledIntegrations,
getInstalledIntegration, getTiIntegrations) as public tools in the SafeBreach MCP.

**Gaps in the original ticket**:
- Assumed a simple "make public" / re-registration. Investigation shows the TS tools read the SIEM
  service's **in-process** connector registry (no API call), so they cannot be lifted as-is into the
  Python repo — they must be **re-implemented over HTTP**.
- File paths in the ticket (`integrationsTools.ts`, `tiTools.ts`) are wrong — tools live in
  per-tool directories under `src/mcp/tools/<tool>/`.
- Did not identify that **two of the four tools have no matching REST endpoint** and that the SIEM
  REST endpoints **do not apply the tools' secret redaction**.
- Did not state the host package (now decided: `safebreach_mcp_config`).

---

## Investigation Summary

### siem (TypeScript — source)
- Four tools defined per-directory under `src/mcp/tools/<tool>/{index.ts,handler.ts}`, aggregated in
  `src/mcp/tools/index.ts`, mounted Streamable HTTP at `/api/siem/mcp` (`McpService.ts:8,34`).
- Data source is **in-process** (`config.value.connectors`) — no request-time HTTP call.
- `getInstalledIntegration` redaction: masks schema-`sensitive` fields to `@enc:SENSITIVE_FIELD` and
  force-masks `proxyPass`+`headers` (`getInstalledIntegration/handler.ts:16-23`,
  `ConnectorManager.ts:485-492`).
- RBAC/consent enforced only in the MCP lib layer (`ToolAuthorizer.ts:63-97`); for these read-only
  tools only the RBAC leg is active. No "public/internal" tool flag exists.
- **REST surface** (`swagger.yaml`, base `/api/siem`):
  - catalog → `GET /v1/accounts/{accountId}/config/integrations` (`getProvidersDefaults`) ✅
  - installed → `GET /v1/accounts/{accountId}/config/integrations/installed` (`getProvidersConfig`) ✅ (raw/full)
  - single connector → **no GET** (only PUT/DELETE) ✗
  - TI connectors → **no list endpoint** (`getTiV2Connectors()` is MCP-only) ✗
  - REST returns connectors **unredacted** vs the MCP tools (`$PAM:INTERNAL_VAULT:...` vault refs;
    `headers`/`proxyPass` not masked). SIEM REST routes have **no in-app RBAC**.

### safebreach-mcp (Python — target)
- Multi-server MCP; **Config Server** (`safebreach_mcp_config`, 8000) is the chosen host
  ("configuration/infrastructure management").
- No integration/SIEM/connector/TI tools exist today.
- `'siem'` is already a routable endpoint (`environments_metadata.py:102`); an existing SIEM call
  template lives at `data_functions.py:1245-1261`.
- Layering to match: `config_types.py` → `config_functions.py` (`sb_*`) → `config_server.py`
  (`@self.mcp.tool(readOnlyHint=True)`) → `tests/`.
- Canonical HTTP+auth pattern: `get_api_base_url(console,'siem')` + `get_api_account_id(console)` +
  `get_auth_headers_for_console(console)` + `requests.get(..., timeout=120)` +
  `check_rbac_response(response)` (403 → `PermissionError` with `RBAC_DENIED_HINT`). Do not use legacy
  `SafeBreachAuth`.
- Pagination convention: `page_number` + `PAGE_SIZE=10` + `total_pages`/`applied_filters`/
  `hint_to_agent`. No existing field-redaction facility → new capability required.

---

## Problem Analysis

### Problem Description
Migrate the four read-only SIEM/TI integration-discovery tools from the TypeScript siem repo into
`safebreach_mcp_config` as native Python tools, re-implemented to fetch their data over HTTP from the
SIEM backend API (through the RBAC gateway), matching the existing safebreach-mcp tool conventions
for naming, parameters, filters, validation, pagination, annotations, and tests. Because the source
tools read an in-process registry and rely on the MCP layer for redaction and RBAC, the migration
must reconstruct: (1) HTTP data access, (2) slim/redacted output shaping, and (3) RBAC-denial relay.

### Impact Assessment
- **New Config Server tools** (4): `get_integrations`, `get_installed_integrations`,
  `get_installed_integration`, `get_ti_integrations`.
- **New redaction pattern** in `config_types.py` (first field-level secret masking in the repo).
- **Docs**: `CLAUDE.md` Config Server tool list + README.
- **Cross-ticket**: step 1 of 2 with SAF-35067 (later withdraws the SIEM-MCP copies).

### Risks & Edge Cases
- **Secret leakage (highest severity)**: REST does not redact; `headers`/`proxyPass` and vault paths
  come back raw. `get_installed_integration` must redact in Python and be verified by test.
- **Missing endpoints** *(resolved by reporter Gal Turgeman, Slack 2026-08-16)*: no dedicated API for
  single-connector read or TI list. Single-connector read is synthesized from the installed list
  filtered by `id`; TI list is derived by filtering the installed list on type/`isTi`. Residual risk:
  `isTi` vs in-process `tiV2` capability may differ → validate TI classification on a live env.
- **RBAC dependency**: enforcement relies on the gateway gating `/api/siem/.../config/integrations*`;
  must be verified on a live env, else a backend/gateway dependency.
- Backend shapes assumed from `swagger.yaml` — confirm against a live SIEM env.
- Single-tenant/in-console vs multi-console auth paths both apply.
- `categories` on installed connectors is capability-derived in TS; may not be reproducible over REST.

---

## Proposed Ticket Content

### Summary (Title)
Migrate integration-discovery tools (get_integrations, get_installed_integrations,
get_installed_integration, get_ti_integrations) into the SafeBreach MCP Config Server

### Description

**Background**
Expose the four read-only SIEM/TI integration-discovery tools — currently in the `integrations/siem`
repo's MCP (`/api/siem/mcp`) — as public tools in the public SafeBreach MCP, so external/customer
consumers can discover and inspect SIEM and TI integrations. Step 1 of 2 (SAF-35067 later withdraws
the SIEM-MCP copies).

**Decision**
Host the four tools in `safebreach_mcp_config` (Config Server, port 8000). Migrate TS → Python with
consistency to the existing safebreach-mcp tool conventions (naming, parameters, filters,
validations, pagination, annotations, tests).

**Technical Context**
- The TS tools read the SIEM service's in-process connector registry (`config.value.connectors`) — no
  request-time HTTP. The Python tools must fetch over HTTP from the SIEM backend via the canonical
  RBAC-safe pattern (`get_api_base_url(console,'siem')` + `get_api_account_id` +
  `get_auth_headers_for_console` + `check_rbac_response`).
- REST mapping: catalog → `GET /api/siem/v1/accounts/{accountId}/config/integrations`; installed →
  `GET .../config/integrations/installed` (returns raw/full connectors — project to slim shape);
  single connector → **no GET** (fetch installed list, filter by `id`); TI list → **no endpoint**
  (derive from installed by filtering on type/`isTi`). *Reporter (Gal Turgeman) confirmed there is no
  dedicated API for the last two — use the installed listing with id/type filters.*
- REST endpoints return connectors **unredacted** vs the MCP tools (vault refs `$PAM:...`; `headers`/
  `proxyPass` unmasked). `get_installed_integration` must re-implement redaction:
  schema-`sensitive` → `@enc:SENSITIVE_FIELD` plus force-mask `headers`+`proxyPass`.
- SIEM REST routes have no in-app RBAC; enforcement relies on the RBAC gateway fronting the API —
  verify it gates the `/config/integrations*` paths.
- Pagination follows repo convention: `page_number` + `PAGE_SIZE=10` (replacing the TS `limit`).

**Affected Areas**
- `safebreach_mcp_config/config_functions.py`: 4 new `sb_*` functions (HTTP, filters, validation,
  pagination).
- `safebreach_mcp_config/config_types.py`: 4 new transforms + a sensitive-field redaction helper.
- `safebreach_mcp_config/config_server.py`: 4 new `@self.mcp.tool(readOnlyHint=True)` registrations.
- `safebreach_mcp_config/tests/`: unit (functions/types/server) + e2e; explicit redaction assertions.
- `CLAUDE.md` + `README.md`: Config Server tool documentation.

### Acceptance Criteria

- [ ] Four read-only tools registered in `safebreach_mcp_config`: `get_integrations`,
      `get_installed_integrations`, `get_installed_integration`, `get_ti_integrations`, each with
      `ToolAnnotations(readOnlyHint=True)`, a `console` param, and clear public-facing
      descriptions/schemas.
- [ ] Tools follow safebreach-mcp conventions: snake_case names, `page_number`/`PAGE_SIZE=10`
      pagination with `total_pages`/`applied_filters`/`hint_to_agent`, and repo-style parameter
      validation.
- [ ] Data fetched over HTTP via the canonical RBAC-safe pattern
      (`get_api_base_url(console,'siem')` + `get_api_account_id` + `get_auth_headers_for_console` +
      `check_rbac_response`); legacy `SafeBreachAuth` not used.
- [ ] `get_installed_integrations` returns the slim `id/type/name/enabled` shape (secrets absent).
- [ ] `get_installed_integration` returns one connector by `id` (fetched from the installed list) with
      **secrets redacted in Python**: schema-`sensitive` fields → `@enc:SENSITIVE_FIELD` and
      `headers`+`proxyPass` force-masked; redaction covered by an explicit unit/e2e test asserting no
      secret material (incl. vault paths for `headers`/`proxyPass`) leaks.
- [ ] `get_integrations` returns the connector-type catalog with `category` filtering.
- [ ] `get_ti_integrations` returns installed TI connectors (`id/type/name/enabled`); the TI-derivation
      approach is documented and tested.
- [ ] RBAC is enforced for all four (backend 403 surfaced as `PermissionError`/`RBAC_DENIED_HINT`);
      verified that the RBAC gateway gates the underlying `/config/integrations*` paths (or a follow-up
      backend/gateway dependency is filed if it does not).
- [ ] Unit tests cover registration, transforms, filters, pagination, and redaction; e2e tests
      (`@pytest.mark.e2e`) validate against a live console.
- [ ] `CLAUDE.md` and `README.md` updated with the four new Config Server tools.

### Suggested Labels/Components
- Labels: `CTEM-dev` (existing)

---

## Proposed Ticket Content

<!-- Markdown for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
Expose the four read-only SIEM/TI integration-discovery tools — currently in the integrations/siem repo's MCP (`/api/siem/mcp`) — as public tools in the public SafeBreach MCP, so external/customer consumers can discover and inspect SIEM and TI integrations. Step 1 of 2 (SAF-35067 later withdraws the SIEM-MCP copies).

### Decision
Host the four tools in `safebreach_mcp_config` (Config Server, port 8000). Migrate TypeScript → Python with consistency to the existing safebreach-mcp tool conventions (naming, parameters, filters, validations, pagination, annotations, tests).

### Technical Context
* The TS tools read the SIEM service's in-process connector registry (`config.value.connectors`) — no request-time HTTP call. The Python tools must fetch over HTTP from the SIEM backend via the canonical RBAC-safe pattern (`get_api_base_url(console,'siem')` + `get_api_account_id` + `get_auth_headers_for_console` + `check_rbac_response`); legacy `SafeBreachAuth` must not be used.
* REST mapping: catalog → `GET /api/siem/v1/accounts/{accountId}/config/integrations`; installed → `GET .../config/integrations/installed` (returns raw/full connectors — project to a slim shape); single connector → NO REST GET (fetch installed list, filter by `id`); TI list → NO endpoint (derive from installed by filtering on type/`isTi`). Reporter confirmed there is no dedicated API for the last two — use the installed listing with id/type filters.
* REST endpoints return connectors UNREDACTED relative to the MCP tools (secrets as `$PAM:INTERNAL_VAULT:...` vault refs; `headers`/`proxyPass` not masked). `get_installed_integration` must re-implement redaction: schema-`sensitive` fields → `@enc:SENSITIVE_FIELD`, plus force-mask `headers`+`proxyPass`.
* SIEM REST routes have no in-app RBAC; enforcement relies on the RBAC gateway fronting the API — verify it gates the `/config/integrations*` paths.
* Pagination follows repo convention: `page_number` + `PAGE_SIZE=10` (replacing the TS `limit` cap).

### Affected Areas
* `safebreach_mcp_config/config_functions.py`: 4 new `sb_*` functions (HTTP, filters, validation, pagination)
* `safebreach_mcp_config/config_types.py`: 4 new transforms + sensitive-field redaction helper
* `safebreach_mcp_config/config_server.py`: 4 new `@self.mcp.tool(readOnlyHint=True)` registrations
* `safebreach_mcp_config/tests/`: unit + e2e with explicit redaction assertions
* `CLAUDE.md` + `README.md`: Config Server tool documentation

### Out of Scope
* Removing the four tools from the integrations/siem MCP once public — SAF-35067.
* TI data-plane tools (`getThreats`, `getThreatInfo`, `getThreatsFilters`) — separate ticket.
```

**Acceptance Criteria:**
```markdown
* Four read-only tools registered in `safebreach_mcp_config` — `get_integrations`, `get_installed_integrations`, `get_installed_integration`, `get_ti_integrations` — each with `ToolAnnotations(readOnlyHint=True)`, a `console` param, and clear public-facing descriptions/schemas.
* Tools follow safebreach-mcp conventions: snake_case names, `page_number`/`PAGE_SIZE=10` pagination with `total_pages`/`applied_filters`/`hint_to_agent`, repo-style validation.
* Data fetched over HTTP via the canonical RBAC-safe pattern; legacy `SafeBreachAuth` not used.
* `get_installed_integrations` returns slim `id/type/name/enabled` (no secrets).
* `get_installed_integration` returns one connector by `id` with secrets redacted in Python (schema-`sensitive` → `@enc:SENSITIVE_FIELD`; `headers`+`proxyPass` force-masked); an explicit test asserts no secret material (incl. vault paths for `headers`/`proxyPass`) leaks.
* `get_integrations` returns the connector-type catalog with `category` filtering.
* `get_ti_integrations` returns installed TI connectors (`id/type/name/enabled`); TI-derivation approach documented and tested.
* RBAC enforced for all four (backend 403 → `PermissionError`/`RBAC_DENIED_HINT`); verified the gateway gates the underlying `/config/integrations*` paths, or a follow-up backend/gateway dependency is filed.
* Unit tests cover registration, transforms, filters, pagination, redaction; e2e tests (`@pytest.mark.e2e`) validate against a live console.
* `CLAUDE.md` and `README.md` updated with the four new tools.
```
