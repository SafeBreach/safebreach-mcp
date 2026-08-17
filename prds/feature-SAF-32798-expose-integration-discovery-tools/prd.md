# MCP: Migrate Integration-Discovery Tools into the Config Server — SAF-32798

## Section 1: Overview

### Driver
Expose the four read-only SIEM/TI integration-discovery tools — currently only in the
`integrations/siem` repo's MCP (`/api/siem/mcp`) — as public tools in the public SafeBreach MCP, so
external/customer consumers can discover and inspect SIEM and TI integrations. This is **step 1 of 2**:
expose publicly here; SAF-35067 later withdraws the SIEM-MCP copies.

The four tools:
- `get_integrations` — catalog of available connector *types* (no account data, no secrets).
- `get_installed_integrations` — installed connectors, slim `id/type/name/enabled` (no secrets).
- `get_installed_integration` — full config of one connector, **secrets redacted**.
- `get_ti_integrations` — installed Threat-Intelligence feeds, slim `id/type/name/enabled`.

### Decision (from the assignee)
Host all four in **`safebreach_mcp_config`** (Config Server, port 8000). Migrate TypeScript → Python
with **full consistency** to the existing safebreach-mcp Config-server tool conventions: naming,
parameters, filters, validation, pagination, annotations, transforms, and tests. Match the repo's
idioms, not the TS surface verbatim.

## Section 1.5: Document Status

| Field | Value |
|-------|-------|
| Ticket | SAF-32798 (Task, Medium, `CTEM-dev`) |
| Branch | `feature/SAF-32798-expose-integration-discovery-tools` |
| Status | PRD drafted; ready for implementation |
| Live API research | Complete — validated on `pentest01` 2026-08-17 (see `api-research.md`) |
| Reporter confirmation | Gal Turgeman confirmed no dedicated API for single-connector / TI list |

## Section 2: Solution Description

Re-implement the four tools natively in the Config server. Because the TS tools read an in-process
connector registry, the Python tools fetch the equivalent data over HTTP from the SIEM backend via
the canonical RBAC-safe pattern, then transform/redact/paginate the responses to match the existing
Config-server tool contracts.

**Data-source map (all live-validated on pentest01; envelope is `{ "error": 0, "result": ... }`):**

| Tool | SIEM endpoint | Transform |
|------|---------------|-----------|
| `get_integrations` | `GET /api/siem/v1/accounts/{account}/config/integrations` | catalog is an object keyed by `type` → list of `{type, name, description, category, vendor, product, is_ti, is_vm, ...}`; filter by `category`; paginate |
| `get_installed_integrations` | `GET .../config/integrations/installed` | already slim `{id,type,name,enabled}` → pass-through; optional `category` joined from catalog; paginate |
| `get_installed_integration` | `GET .../config` → `.connectors[]`, filter by `id` | redact (Section 2.1); "not found" hint if `id` absent |
| `get_ti_integrations` | `GET .../config/integrations/installed` + catalog | keep installed whose `catalog[type].isTiV2 == true` → slim; paginate |

Note: `/config/integrations/installed/{id}` returns **404** (no single-connector GET) — confirmed
live and by the reporter; the single-connector read is synthesized from `/config`.

### Section 2.0: Tool signatures (consistent with existing Config list/detail tools)
Filter surface mirrors `get_console_simulators` / `get_scenarios` / `get_playbook_attacks`: `<field>_filter`
partial/case-insensitive string matches, `<field>_filter` booleans, and `order_by`/`order_direction` on
every list tool; detail tool takes `<entity>_id` (never bare `id`); `console` first, `page_number` for
paginated tools. Client-side filtering in `config_types.py` (same as siblings — the SIEM API has no
query params for these).

```
get_integrations(console="default", page_number=0,
    name_filter=None, category_filter=None, vendor_filter=None,
    ti_only=None, vm_only=None,
    order_by="name", order_direction="asc")            # order_by: name|type|category|vendor

get_installed_integrations(console="default", page_number=0,
    name_filter=None, type_filter=None, enabled_filter=None,
    order_by="name", order_direction="asc")            # order_by: name|type|id|enabled

get_installed_integration(console="default", integration_id=<required>)   # detail tool, no filters

get_ti_integrations(console="default", page_number=0,
    name_filter=None, type_filter=None, enabled_filter=None,
    order_by="name", order_direction="asc")            # order_by: name|type|id|enabled
```

- `name_filter`/`category_filter`/`vendor_filter`/`type_filter`: partial, case-insensitive (repo convention).
- `ti_only`/`vm_only` (catalog) and `enabled_filter` (installed/TI): `Optional[bool]`, mirroring
  `critical_only`/`recommended_filter`.
- Each tool's docstring carries the standard `Parameters:` enumeration line.

### Section 2.1: Redaction (`get_installed_integration`) — highest-severity requirement
The SIEM REST endpoints do **not** apply the MCP tools' redaction. Live on pentest01, `/config`
returns sensitive values as `$PAM:INTERNAL_VAULT:...` vault references, non-sensitive fields as
plaintext, and `headers` as a **raw object** (not schema-flagged sensitive → can carry auth tokens).
Raw secret *values* stay in vault, but vault paths and `headers` would leak without redaction.

The redaction schema is the catalog: `catalog[type].fields[]` entries with `sensitive == true` list
the fields to mask per connector type (live-verified: e.g. `custom_splunkrest` → `token, password,
proxyPass`; `threatconnect` → `apiSecret, apiToken, proxyPass`).

**Algorithm (mirrors TS `sanitizeSensetiveFields` + `ALWAYS_REDACTED_FIELDS`):**
1. Fetch the catalog; for the connector's `type`, mask every field with `sensitive == true` →
   set value to the literal `@enc:SENSITIVE_FIELD` (regardless of current value / vault-ref).
2. Force-mask `headers` and `proxyPass` → `@enc:SENSITIVE_FIELD` if present (backstop; `headers` is
   not schema-`sensitive`).
3. Unknown connector type (no catalog entry) → **fail safe**: mask a conservative default set and
   still force-mask `headers`/`proxyPass`; never return the connector unredacted.

### Section 2.2: TI derivation (`get_ti_integrations`)
No dedicated TI-list endpoint. Derive by joining the installed list against the catalog and keeping
connectors whose `catalog[type].isTiV2 == true` (matches the TS `supportsTiV2()` capability; live:
`alienvault`, `threatconnect`, `custom_mitreattack`, `custom_tiv2mockconnector`). Primary flag
`isTiV2`; `isTi` retained as documented fallback.

### Why re-implement rather than proxy the TS MCP
The public SafeBreach MCP is a distinct Python service; it cannot call the siem service's in-process
registry. Re-implementation is the only path and is the explicit ticket intent (with SAF-35067
withdrawing the duplicates afterward).

## Section 3: Affected Components

### 3.1 `safebreach_mcp_config/config_functions.py`
Add four `sb_*` functions following `sb_get_console_simulators` (`config_functions.py:43-198`):
`sb_get_integrations`, `sb_get_installed_integrations`, `sb_get_installed_integration`,
`sb_get_ti_integrations`. Each: validate params → `get_api_base_url(console,'siem')` +
`get_api_account_id(console)` + `headers={"Content-Type":"application/json",
**get_auth_headers_for_console(console)}` → `requests.get(url, headers=headers, timeout=120)` →
`check_rbac_response(response)` → read `response.json()["result"]` → transform → paginate. Reuse
module-level `PAGE_SIZE`. Catalog is fetched by `get_integrations`, `get_installed_integration`
(for redaction schema) and `get_ti_integrations` (for `isTiV2`) — factor a private
`_get_catalog_from_cache_or_api(console)` helper; add a bounded `SafeBreachCache` entry if caching
is enabled for the Config server (mirror the simulators cache).

### 3.2 `safebreach_mcp_config/config_types.py`
Add four transforms + one redaction helper, following `map_reduced_entity` / `get_minimal_*` /
`get_*_detail_view` conventions:
- `get_integration_catalog_entry(raw_type_def)` — catalog entry (allow-list mapping).
- `get_minimal_installed_integration(raw)` — slim `{id,type,name,enabled}` (+ optional `category`).
- `get_installed_integration_detail_view(raw_connector, catalog)` — full config **after** redaction.
- `get_minimal_ti_integration(raw)` — slim TI shape.
- `redact_sensitive_fields(connector, catalog)` — the Section 2.1 algorithm (new capability;
  first field-level redaction in this repo). Include `hint_to_llm`/`hint_to_agent` fields per repo
  convention where a list/detail tool returns them.

### 3.3 `safebreach_mcp_config/config_server.py`
Register four `@self.mcp.tool(name=..., annotations=ToolAnnotations(readOnlyHint=True),
description=...)` async wrappers in `_register_tools()`, mirroring `get_console_simulators`
(`config_server.py:42-75`): `console` param (single-tenant auto-resolve), filter params,
`page_number`. Wrappers delegate to the `sb_*` functions. No rate-limiter calls (all read-only).

### 3.4 `safebreach_mcp_config/tests/`
- `test_config_functions.py` — unit tests per tool: mock `get_api_base_url`, `get_api_account_id`,
  `requests.get` (by import path), set `.json.return_value={"error":0,"result":...}`,
  `.status_code=200`; cover filters, pagination, error/empty, and 403→`PermissionError`.
- `test_config_types.py` — transform units + **explicit redaction tests** asserting every
  schema-`sensitive` field, `headers`, and `proxyPass` are `@enc:SENSITIVE_FIELD` and no
  `$PAM:`/vault path or header value survives; unknown-type fail-safe test.
- `test_config_server.py` — registration/annotation tests for the four tools.
- `test_e2e_integrations.py` (new) — `@pytest.mark.e2e`, real auth via `conftest.py` (`E2E_CONSOLE`);
  validates all four against a live console incl. a redaction assertion.

### 3.5 Docs
`CLAUDE.md` (Config Server tool list + filtering section) and `README.md`: add the four tools.

### 3.6 Explicitly NOT touched
`integrations/siem` (SAF-35067 handles withdrawal); other servers; auth/core modules (reused as-is).

## Section 4: Backend Dependency

Relies on the SIEM backend endpoints for the target console: `/config/integrations`,
`/config/integrations/installed`, `/config`. All returned HTTP 200 on pentest01 with a valid token.

**RBAC**: enforced by the **ui-server** component (`/Users/yossiattas/projects/ui`), the gateway all
SafeBreach backend API calls route through — the same mechanism that gates every other backend API.
The Python MCP does not implement RBAC itself: in embedded/SIMP mode `get_api_base_url(console,'siem')`
resolves to the ui-server gateway, so an unauthorized caller receives HTTP 403, which
`check_rbac_response` maps to `PermissionError` + `RBAC_DENIED_HINT`. This is the standard, already-in-
place enforcement path — **not** a new dependency or a gap. The Python-side obligation is only to route
through the gateway (canonical pattern) and relay the 403; no backend/gateway change is required.

## Section 5: Out of Scope
- Removing the four tools from the `integrations/siem` MCP once public — **SAF-35067**.
- TI data-plane tools (`getThreats`, `getThreatInfo`, `getThreatsFilters`) — separate ticket.
- Any **write** operation on integrations (create/update/delete) — these tools are read-only.

## Section 6: Definition of Done
- [x] Four read-only tools registered in `safebreach_mcp_config` with `readOnlyHint=True`, a `console`
      param, and clear public-facing descriptions/schemas.
- [x] Names + conventions consistent with the repo: `get_integrations`, `get_installed_integrations`,
      `get_installed_integration`, `get_ti_integrations`; `page_number`/`PAGE_SIZE=10` pagination with
      `total_pages`/`applied_filters`/`hint_to_agent`; repo-style validation.
- [x] Filter surface matches sibling list tools (§2.0): `<field>_filter` partial/case-insensitive
      string filters, `Optional[bool]` flag filters, and `order_by`/`order_direction` on every list
      tool; detail tool uses `integration_id` (not bare `id`); each docstring has a `Parameters:` line.
- [x] Data fetched via `get_api_base_url(console,'siem')` + `get_api_account_id` +
      `get_auth_headers_for_console` + `check_rbac_response`; envelope `result` unwrapped; legacy
      `SafeBreachAuth` not used.
- [x] `get_installed_integrations` returns slim `id/type/name/enabled` (no secrets).
- [x] `get_installed_integration` returns one connector by `id` (from `/config`) with secrets redacted
      in Python (schema-`sensitive` → `@enc:SENSITIVE_FIELD`; `headers`+`proxyPass` force-masked);
      explicit test asserts no secret material (incl. vault paths and header values) leaks;
      unknown-type fail-safe covered.
- [x] `get_integrations` returns the connector-type catalog with `category` filtering.
- [x] `get_ti_integrations` returns installed TI connectors via `isTiV2`; derivation documented + tested.
- [x] RBAC: tools route through the ui-server gateway (canonical `get_api_base_url` pattern) and
      surface a backend 403 with the RBAC denial hint — `check_rbac_response` raises `PermissionError`,
      which the function catches and returns as an `{"error": ...}` dict carrying `RBAC_DENIED_HINT`
      (sibling `sb_get_console_simulators`/`sb_get_scenarios` convention); verified by a unit test
      mocking a 403 (real enforcement is ui-server's standard mechanism, same as all backend APIs).
- [x] Unit tests (functions/types/server) + e2e (`@pytest.mark.e2e`) pass; full cross-server unit
      suite green.
- [x] `CLAUDE.md` + `README.md` updated.

## Section 7: Testing Strategy

### 7.1 Baseline
No integration-discovery tools exist today; net-new surface. Baseline = existing Config-server suite
green on `origin/main`.

### 7.2 Unit
Mock the three backend seams by import path in `config_functions`. Assert: correct URL/endpoint per
tool; envelope `result` unwrap; slim vs detail shaping; `category`/name/type/enabled filters;
pagination math and out-of-range handling; empty-result `hint_to_agent`; 403→`PermissionError`.
Redaction gets a dedicated `test_config_types.py` block with fixtures modeled on the pentest01
shapes (vault-ref secrets, raw `headers` object) asserting full masking + fail-safe.

### 7.3 Live E2E
`test_e2e_integrations.py` (`@pytest.mark.e2e`, `E2E_CONSOLE=pentest01`): each tool returns data;
`get_installed_integration` on a connector with sensitive fields asserts `@enc:SENSITIVE_FIELD` and
absence of `$PAM:`/header values; `get_ti_integrations` returns the known TI connectors. Self-
discovering (pick an id from the installed list at runtime — never hardcode a connector id).

### 7.4 Verification commands
`uv run pytest safebreach_mcp_config/tests/ -v -m "not e2e"` (unit); full cross-server unit suite;
`source .vscode/set_env.sh && uv run pytest safebreach_mcp_config/tests/ -v -m e2e` (live).

## Section 8: Implementation Phases

### Phase Status Tracking
**Vertical per-tool slices** (Elephant-Carpaccio): each phase delivers ONE tool end-to-end —
transform → `sb_*` function → registration → its unit tests → its e2e test — so every test gates the
soonest phase at which it can be green. Within a slice the repo's bottom-up order (types → functions →
server → tests) still holds. Ordering is dependency-driven: Phase 1 builds the shared
`_get_catalog_from_cache_or_api` helper (reused by Phases 3 & 4); Phase 3 builds `redact_sensitive_fields`.

| Phase | Deliverable (end-to-end) | Changes | Status |
|-------|--------------------------|---------|--------|
| Phase 1 | `get_integrations` — catalog fetch helper + `get_integration_catalog_entry` + `sb_get_integrations` (name/category/vendor/ti_only/vm_only filters, ordering, pagination) + registration | `config_types.py`, `config_functions.py`, `config_server.py`, `tests/test_config_types.py`, `tests/test_config_functions.py`, `tests/test_config_server.py`, `tests/test_e2e_integrations.py` | ✅ Complete (453903d, 2026-08-17) |
| Phase 2 | `get_installed_integrations` — `get_minimal_installed_integration` + `sb_get_installed_integrations` (name/type/enabled filters, ordering, pagination) + registration | `config_types.py`, `config_functions.py`, `config_server.py`, `tests/test_config_types.py`, `tests/test_config_functions.py`, `tests/test_config_server.py`, `tests/test_e2e_integrations.py` | ✅ Complete (212059b, 2026-08-17) |
| Phase 3 | `get_installed_integration` — `redact_sensitive_fields` + `get_installed_integration_detail_view` + `sb_get_installed_integration` (fetch `/config`, filter by `integration_id`, redact) + registration | `config_types.py`, `config_functions.py`, `config_server.py`, `tests/test_config_types.py`, `tests/test_config_functions.py`, `tests/test_config_server.py`, `tests/test_e2e_integrations.py` | ✅ Complete (8f58c52, 2026-08-17) |
| Phase 4 | `get_ti_integrations` — `get_minimal_ti_integration` + `sb_get_ti_integrations` (isTiV2 derivation, name/type/enabled filters, ordering, pagination) + registration; + cross-tool hardening (403 relay across all four, pagination out-of-range, all-four registration, compose, whole-server regression, full-flow progression) | `config_types.py`, `config_functions.py`, `config_server.py`, `tests/test_config_types.py`, `tests/test_config_functions.py`, `tests/test_config_server.py`, `tests/test_e2e_integrations.py` | ✅ Complete (00c0f5a, 2026-08-17) |
| Phase 5 | Docs | `CLAUDE.md`, `README.md` | ✅ Complete (2026-08-17) |
| Phase 6 | PR | — | 🔄 In Progress (PR #88) |

## Section 9: Risks and Assumptions

### Risks
- **Secret leakage (high)**: wrong `sensitive` set or missed `headers` leaks credentials. Mitigation:
  schema-driven masking from catalog + hard force-mask of `headers`/`proxyPass` + explicit tests +
  fail-safe on unknown type.
- **TI misclassification (low/med)**: `isTiV2` vs in-process `tiV2` capability could diverge on some
  connector; mitigated by using the same capability flag the TS tool relies on and an e2e check.
- **Backend shape drift (low)**: shapes validated on pentest01 (26.2.x) may differ across versions;
  transforms use defensive allow-list mapping + `.get()` access.
- ~~RBAC not enforced at gateway~~ **Resolved**: RBAC is enforced by ui-server exactly like all other
  backend APIs; no gap. Residual Python-side risk is only failing to route through the gateway or
  swallowing the 403 — covered by the canonical pattern + a unit test.

### Assumptions
- In embedded/SIMP mode, `get_api_base_url(console,'siem')` resolves to the ui-server gateway (as for
  all backend API calls), so RBAC is enforced and 403s propagate.
- `/config` remains the source of full connector config (no dedicated single-GET is planned backend-side).
- Catalog `fields[].sensitive` is the authoritative sensitivity source (matches TS `configSchema`).

## Section 10: Open Questions
- Should `get_installed_integrations` include a derived `category` (join from catalog) to match the TS
  `categories` field, or stay strictly `{id,type,name,enabled}`? (Leaning: include `category` as an
  additive, non-secret convenience; confirm at review.)
- Caching: enable a Config-server catalog cache (the catalog is 442KB on pentest01) or fetch per call?
  (Leaning: cache behind the existing `SB_MCP_CACHE_CONFIG` toggle.)

## Section 11: Executive Summary
Add four read-only integration-discovery tools to the Config server, re-implemented in Python over the
SIEM REST API (validated live on pentest01). The listing/catalog endpoints map cleanly; the single-
connector read and TI list are synthesized (filter `/config` by id; filter installed by catalog
`isTiV2`) per the reporter's guidance. The one genuinely new capability is Python-side secret
redaction for `get_installed_integration`, required because the REST layer returns vault refs and raw
`headers` — this is the highest-severity item and is covered by explicit tests and a fail-safe. RBAC
is relayed from the gateway and must be verified. Everything else follows existing Config-server
conventions exactly.

## Section 12: Change Log
| Date | Change |
|------|--------|
| 2026-08-17 | Initial PRD from investigation + live pentest01 API research; host=Config, pagination=repo convention, redaction re-implemented in Python. |
| 2026-08-17 | Added §2.0 explicit tool signatures — full filter/order surface consistent with `get_console_simulators`/`get_scenarios`/`get_playbook_attacks` (`<field>_filter`, bool flags, `order_by`/`order_direction`, `integration_id`). RBAC reframed as ui-server-enforced. |
