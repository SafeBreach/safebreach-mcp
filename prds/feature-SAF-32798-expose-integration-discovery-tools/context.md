# Ticket Context: SAF-32798

## Status
Planning COMPLETE — prd.md + test-plan.md (19 tests, validator clean) authored; ticket In Progress;
draft PR https://github.com/SafeBreach/safebreach-mcp/pull/88. Test plan Status=Draft (→Reviewed on
review). Next: implement per prd.md §8 phases A–F (tdd-implementing-prd).
Preparing-ticket phase 9 done: refinement posted to SAF-32798 as comment 203713 (2026-08-17).

## Live API Research (pentest01, 2026-08-17) — see api-research.md
All 4 tools' data sources validated live: installed listing is already slim `{id,type,name,enabled}`;
catalog is type-keyed with `isTiV2` (TI derivation) and `fields[].sensitive` (redaction schema);
single-connector GET is 404 (use `/config` blob filtered by id); `/config` exposes secrets as `$PAM:`
vault refs + raw `headers` object → Python redaction confirmed required. Envelope `{error,result}`.

## User Direction (mid-refinement)
- Host the four tools in **`safebreach_mcp_config`** (Config Server, port 8000).
- **Migrate TS → Python** with *perfect consistency* to the current safebreach-mcp tool
  conventions: naming (snake_case, verb-first, no server prefix), parameters, filters,
  validations, pagination, annotations, and testing patterns. Match the existing repo's
  idioms rather than copying the TS surface verbatim.

## Mode
Improving

## Original Ticket
- **Summary**: Expose integration-discovery tools (getIntegrations, getInstalledIntegrations, getInstalledIntegration, getTiIntegrations) as public tools in the SafeBreach MCP
- **Type**: Task | **Status**: To Do | **Priority**: Medium | **Labels**: CTEM-dev
- **Reporter**: Gal Turgeman | **Assignee**: Yossi Attas
- **Description**: Make the SIEM MCP integration-discovery tools available as public tools in the
  SafeBreach MCP, so external/customer consumers can discover and inspect SIEM and TI integrations.
  These tools live in `siem/src/mcp/tools/integrationsTools.ts` and `tiTools.ts`, registered via
  `siem/src/mcp/tools/index.ts` (`McpService`, Streamable HTTP at `/api/siem/mcp`). All are
  read-only and gated per-request by RBAC + write-consent.
- **Scope — tools to make public**:
  - `getIntegrations` — catalog of available connector *types* (no account data, no secrets)
  - `getInstalledIntegrations` — installed connectors, slim `id/type/name/enabled` (no secrets)
  - `getInstalledIntegration` — full config of one connector, secrets redacted as `@enc:SENSITIVE_FIELD`
  - `getTiIntegrations` — installed Threat Intelligence feeds, slim `id/type/name/enabled`
- **Out of scope**: removing the four tools from the SIEM MCP once public (SAF-35067); TI data-plane
  tools (`getThreats`, `getThreatInfo`, `getThreatsFilters`) — separate decision/ticket.
- **Acceptance Criteria (original)**:
  - Four tools exposed as public SafeBreach MCP tools with clear names/descriptions/schemas
  - RBAC remains enforced for all four (esp. `getInstalledIntegration`)
  - Redaction of sensitive fields (`@enc:SENSITIVE_FIELD`, `proxyPass`, `headers`) verified for `getInstalledIntegration`
  - Tests cover public registration of the four tools

## Task Scope
Refine SAF-32798 into an implementation-ready ticket: understand how the four SIEM-MCP
integration-discovery tools work today (siem repo), how the SafeBreach MCP exposes public tools
(safebreach-mcp repo), and describe precisely what "expose as public tools in the SafeBreach MCP"
requires — data source, RBAC/redaction preservation, naming, schemas, tests. No solution design
(that is planning-dev-task's job).

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp (Python, public SafeBreach MCP — implementation target)
- /Users/yossiattas/projects/integrations/siem (TypeScript, SIEM MCP — current home of the tools)

## Investigation Findings

### Source repo — `integrations/siem` (TypeScript, current home of the tools)

**Actual file layout** (ticket's `integrationsTools.ts`/`tiTools.ts` paths are wrong): each tool is a
directory `src/mcp/tools/<toolName>/` with `index.ts` (definition + JSON schemas) and `handler.ts`
(logic). All four aggregated in `src/mcp/tools/index.ts` (`toolDefinitions`/`toolHandlers` maps),
registered via `McpService.ts:33` `registerTools(...)`, mounted Streamable HTTP at `/api/siem/mcp`
(`McpService.ts:8,34`). Built through `defineTool` (`src/mcp/lib/defineTool.ts:39-58`) which stamps
read/write MCP annotations.

**Per-tool contract (name / title / input / output):**
- `getIntegrations` — "List Available Integration Types". Input: `category?` (enum-ish string:
  siem/security_control/ti/workflow/file_provider/secret_provider/custom), `limit?` (int 1..200,
  default 50). Output `{ integrations: [{type,name,description,category,vendor,product,isTi,isVm,
  supportsCollectorNode}], totalCount }`. `read:'local'`, `category:'config'`.
- `getInstalledIntegrations` — "List Installed Integrations". Input: `limit?` (int 1..200, default
  50). Output `{ installedIntegrations: [{id,type,name,enabled,categories}], totalCount }`. No
  secrets. `read:'local'`, `category:'config'`.
- `getInstalledIntegration` — "Get Installed Integration Config". Input: `id` (string, **required**).
  Output: open object (id/type/name/enabled + connector-specific config), **secrets redacted**.
  `read:'local'`, `category:'config'`.
- `getTiIntegrations` — "List Threat Intelligence Connectors". Input: **none**. Output
  `{ tiIntegrations: [{id,type,name,enabled}], totalCount }`. `read:'local'`, `category:'ti'`.

**Redaction (`getInstalledIntegration`)**: `REDACTED='@enc:SENSITIVE_FIELD'`;
`ALWAYS_REDACTED_FIELDS=['proxyPass','headers']`. Handler fetches the connector's `configSchema`
and calls `connectorManager.sanitizeSensetiveFields(schema, connector)` (`ConnectorManager.ts:485-492`)
which masks every schema field flagged `sensitive`, then force-masks `proxyPass`/`headers` as a
backstop. Stored secrets are already vault paths, not plaintext; sanitizer masks them entirely.

**Data source**: NONE of the four make an outbound HTTP call at request time. They read the SIEM
service's in-process config/connector registry (`config.value.connectors`, backing key
`sb/configuration/siem`, sourced from the SafeBreach configuration service). Hence `read:'local'` /
`openWorldHint:false`. *(Implication for Python: the equivalent data must be fetched over HTTP from a
SafeBreach backend API — this is the biggest open question; see Problem Analysis.)*

**RBAC / consent gating**: Enforced per-request in the MCP lib layer (`ToolAuthorizer.decideAccess`,
`ToolAuthorizer.ts:63-97`), not in handlers. Chain: RBAC (`POST /api/rbac/mcp-check` to ui-server,
fail-closed) → connector-enabled policy → write-consent (only if `write===true`) → per-connector
deny dial. For these four read-only, non-resourceRef tools **only the RBAC leg is active**;
write-consent structurally does not apply. Identity from `originaldata` header / token resolution.

**Public vs internal**: There is **no** "public/internal" flag today. Exposure is controlled by
read/write annotations (hints, not a security boundary), `category`+feature-flag gating
(`feature.mcpToolsConfig` / `feature.mcpToolsTi`), and per-request RBAC. The only "internal" notion
is an introspection principal. Consistent with the ticket's premise that these are not currently
"public".

### Target repo — `safebreach-mcp` (Python, migration target = Config Server)

**Host decision confirmed**: Config Server (`safebreach_mcp_config`, port 8000) — "configuration /
infrastructure management" (`config_server.py:2-5,33`). Today it holds simulators + scenarios; **no**
integration/SIEM/connector/TI tools exist anywhere in the repo.

**Existing SIEM plumbing already present**:
- `environments_metadata.py:102` — `get_api_base_url()` already whitelists `'siem'` as a routable
  endpoint (alongside data/config/moves/queue/playbook/orchestrator).
- `data_functions.py:1245-1261` — the only live SIEM call today:
  `GET {siem_base}/api/siem/v1/accounts/{account_id}/eventLogs?...` (event logs, not integrations) —
  a working template for the HTTP + auth pattern against the SIEM API.

**Layering pattern** (must be matched): `*_types.py` (pure transforms/filter/paginate) →
`*_functions.py` (`sb_*` logic + HTTP) → `*_server.py` (`@self.mcp.tool(...)` FastMCP registration
via `SafeBreachMCPBase`) → `tests/`. Concrete reference tool end-to-end: `get_console_simulators`
(`config_server.py:42-75` → `config_functions.py:43-198` → `config_types.py` transforms).

**Backend API access pattern** (canonical, RBAC-safe): `get_api_base_url(console,'siem'|'config')` +
`get_api_account_id(console)` + `headers = {"Content-Type":"application/json",
**get_auth_headers_for_console(console)}` + `requests.get(url, headers=headers, timeout=120)` +
`check_rbac_response(response)`. Do **not** use legacy `SafeBreachAuth` (bypasses RBAC gateway,
removed in SAF-29974 per `safebreach_base.py:35-36`).

**RBAC in Python**: Delegated to the backend gateway (OPA). No per-caller authz logic in the repo.
`check_rbac_response()` (`secret_utils.py:76-88`) turns backend HTTP 403 into a `PermissionError`
with an LLM-facing `RBAC_DENIED_HINT`. This is the entire RBAC surface — matches source's per-request
RBAC by relaying backend denials. Read-only tools use `ToolAnnotations(readOnlyHint=True)` and do
**not** invoke the rate limiter (rate limiting is write-only).

**Naming (snake_case) mapping**: `get_integrations`, `get_installed_integrations`,
`get_installed_integration`, `get_ti_integrations`. Follows the repo's verb-first, no-prefix snake
convention.

**Pagination**: module-level `PAGE_SIZE = 10`, 0-based `page_number` param, `total_pages`,
`applied_filters`, `hint_to_agent` fields. *(Note: source uses a `limit` 1..200/default-50 cap, not
page-based — "perfect consistency with the safebreach-mcp repo" means adopting the repo's
`page_number`+`PAGE_SIZE` pagination, an intentional divergence from the TS `limit`.)*

**Redaction gap**: No field-level secret-redaction exists in any `*_types.py` today (transforms are
allow-list mappings that exclude secrets only incidentally). A `get_installed_integration` that must
redact `@enc:SENSITIVE_FIELD` / `proxyPass` / `headers` introduces a **new explicit redaction
pattern** — the redaction must be verified server-side, not assumed from the backend.

**Testing conventions**: per-server `tests/` with `test_*_functions.py` (mock `get_api_base_url` /
`get_api_account_id` / `requests.get` by import path, set `.json.return_value`/`.status_code`),
`test_*_types.py` (transform units), `test_*_server.py` (registration), `test_e2e*.py`
(`@pytest.mark.e2e`, real auth via `conftest.py`, `E2E_CONSOLE`).

## Problem Analysis

### Problem statement
Re-implement four read-only SIEM/TI integration-discovery tools as native Python tools in
`safebreach_mcp_config`, fetching their data over HTTP from the SafeBreach SIEM backend API, with
behaviour (names, params, filters, validation, pagination, redaction, RBAC relay) consistent with
both the source TS tools' intent and the existing safebreach-mcp Python conventions.

### The core structural difference (biggest risk)
The TS tools do **not** call an API — they read the SIEM service's own in-process connector registry
(`config.value.connectors`). The Python tools have no such registry; they must call SIEM REST
endpoints. The REST surface only partially matches the four tools:

- **`get_integrations`** (catalog) → `GET /api/siem/v1/accounts/{accountId}/config/integrations`
  (`getProvidersDefaults`). Direct match.
- **`get_installed_integrations`** → `GET .../config/integrations/installed` (`getProvidersConfig`).
  Returns **full/raw** connector objects; Python must project to slim `{id,type,name,enabled}`
  (+ `categories` if derivable).
- **`get_installed_integration`** (single, redacted) → **no dedicated REST GET** (only PUT/DELETE on
  `/installed/{id}`). **[Confirmed by Gal Turgeman, reporter]** No dedicated endpoint exists; fetch
  the installed list and **filter by `id`**, then redact.
- **`get_ti_integrations`** → **no REST list endpoint**; `getTiV2Connectors()` (a `tiV2`-capability
  filter) is in-process TS only. **[Confirmed by Gal Turgeman, reporter]** No dedicated endpoint;
  derive TI connectors from the installed list by **filtering on type / `isTi`**.

> **Reporter confirmation (Gal Turgeman, 2026-08-16 Slack)**: points 1 & 2 above are correct — there
> is no dedicated API for the single-connector read or the TI-connector list. Use the
> installed-integrations listing with specific filters (id, type, or others) to identify what's
> needed for both. Points 3 (redaction) and 4 (RBAC gateway) were not addressed → treated as
> implementation-verified items (redact in Python; verify RBAC on a live env).

### Redaction (must be re-built in Python — new pattern for this repo)
REST returns connectors **unredacted relative to the MCP tools**: schema-`sensitive` fields appear as
`$PAM:INTERNAL_VAULT:...` vault references (secret value stays in vault, but the path is exposed) and
`headers`/`proxyPass` are **not** masked. The TS tool masks all schema-`sensitive` fields to
`@enc:SENSITIVE_FIELD` and force-masks `headers`+`proxyPass`. The Python `get_installed_integration`
must reproduce this: obtain each connector type's config schema (available via the catalog
`getProvidersDefaults` response) to know which fields are `sensitive`, mask them, and force-mask
`headers`/`proxyPass`. No field-redaction facility exists in the repo today → new `*_types.py`
capability. **This must be verified by test, not assumed from the backend.**

### RBAC (relay, not local — verify the gateway)
The SIEM REST routes have no in-app RBAC; the siem repo's RBAC lives only in its MCP layer. The
Python repo relies on the RBAC gateway fronting the SIEM API and surfaces backend 403 via
`check_rbac_response`. AC "RBAC remains enforced" therefore hinges on the gateway actually gating
`/api/siem/.../config/integrations*`. This needs verification against a live env; if the gateway does
not gate these paths, RBAC enforcement is an open dependency (possibly a backend/gateway ticket).

### Affected areas
- `safebreach_mcp_config/config_types.py` — 4 new transforms (catalog entry, slim installed, redacted
  single connector, slim TI) + a new sensitive-field redaction helper.
- `safebreach_mcp_config/config_functions.py` — 4 new `sb_*` functions (HTTP via
  `get_api_base_url(console,'siem')` + `get_api_account_id` + `get_auth_headers_for_console` +
  `check_rbac_response`), pagination (`PAGE_SIZE`), filters, validation; caching if desired.
- `safebreach_mcp_config/config_server.py` — 4 new `@self.mcp.tool(readOnlyHint=True)` registrations.
- `safebreach_mcp_config/tests/` — unit (functions/types/server) + e2e; assert redaction explicitly.
- Docs: `CLAUDE.md` Config Server tool list; README.

### Consistency decisions to lock (TS vs safebreach-mcp conventions)
- **Naming**: `get_integrations`, `get_installed_integrations`, `get_installed_integration`,
  `get_ti_integrations` (snake_case, repo convention).
- **Pagination**: adopt repo's `page_number` + `PAGE_SIZE=10` + `total_pages`/`applied_filters`/
  `hint_to_agent`, **replacing** the TS `limit` (1..200, default 50) cap. (Divergence justified by
  "consistency with the safebreach-mcp repo".) — confirm with reviewer.
- **`console` param**: every tool takes `console` like all existing Config tools (TS tools had no
  console — they were single-tenant in-process).
- **Filters**: mirror TS where sensible (`category` on catalog) and add repo-style filters
  (name/type/enabled substring) to match sibling list tools — scope in planning.

### Risks & edge cases
- Backend endpoint paths/shapes assumed from `swagger.yaml`; must be confirmed against a live SIEM
  env (versions may differ).
- Deriving TI connectors without a dedicated endpoint may misclassify (catalog `isTi` vs in-process
  `tiV2` capability may not be identical).
- Over-redaction vs under-redaction: getting the `sensitive` field set wrong risks leaking secrets
  (headers/proxyPass) — highest-severity correctness concern.
- `categories` field on installed connectors is derived in TS from in-process capability probes; may
  not be reproducible over REST → may be dropped or approximated.
- Single-tenant/in-console (`ACCOUNT_ID`, `mcp_in_console`) vs multi-console auth paths both apply.

### Dependencies
- Live SIEM backend endpoints (`/config/integrations`, `/config/integrations/installed`) reachable
  through the RBAC gateway for the target console.
- Coordination with SAF-35067 (withdraw the SIEM-MCP copies) — this ticket is step 1 of 2.
- Possible backend/gateway dependency if RBAC is not enforced on these REST paths.

## Proposed Improvements
(Phase 6)
