# Ticket Summary: SAF-29415

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp

---

## Current State

**Original Summary**: Add the new Peer Benchmark Score API to the DATA MCP

**Issues Identified in the original ticket**:
- Parameter names in the description don't align with the Data MCP convention. Existing tools use `start_date`/`end_date` for date windows (`get_tests_history`) and `_filter`-suffixed Optional[str] comma-separated strings for multi-value filters (`playbook_attack_id_filter`, `mitre_technique_filter`). The ticket should spell out the tool's snake_case contract explicitly and how it maps to the API's camelCase.
- Datetime format is under-specified (API needs ISO 8601 UTC `Z`; Data MCP tools accept epoch **or** ISO and normalize to epoch ms — this tool must additionally convert back to ISO for the body).
- No mention of the established Data-server layering (`data_types.py` → `data_functions.py` → `data_server.py` → `tests/`) or the `x-apitoken` auth header used by Data APIs.
- Caching strategy unstated; the project already has a `SafeBreachCache` pattern gated by `SB_MCP_CACHE_DATA` (size convention `maxsize=3, ttl=600` for data tools) that should be reused.
- No acceptance criteria beyond DOD bullets — missing concrete, testable checks.
- No note about staging/private-dev frozen peer snapshots or the semantics of `snapshotMonth` / `dataThroughDate` / `customAttackIdsFiltered` (documented in ticket comments but not in the description).

---

## Investigation Summary

### safebreach-mcp
- **Data server layering confirmed**: `data_types.py` (transforms) → `data_functions.py` (`sb_*` logic + caching + HTTP) → `data_server.py` (`@self.mcp.tool` registration, timestamp normalization) → `tests/`.
- **HTTP pattern** (confirmed at `safebreach_mcp_data/data_functions.py:658-687`):
  - URL: `f"{get_api_base_url(console, 'data')}/api/data/v1/accounts/{get_api_account_id(console)}/<endpoint>"`
  - Header: `{"Content-Type": "application/json", "x-apitoken": apitoken}` (NOT Bearer)
  - `requests.post(..., timeout=120)` → `response.raise_for_status()`
- **Caching**: `SafeBreachCache` thread-safe TTLCache; convention for Data tools is `maxsize=3, ttl=600`; gate with `is_caching_enabled("data")`.
- **Datetime mismatch**: `normalize_timestamp()` produces epoch ms (matches most SafeBreach APIs). Peer Benchmark API takes ISO 8601; use `convert_epoch_to_datetime(ms)["iso_datetime"]` to render back before POSTing.
- **Tool-registration template**: `get_test_simulations_tool` (`data_server.py:100-137`) — typed Optional params + normalization + delegate.
- **Test patterns** in `safebreach_mcp_data/tests/` — unit mocks `requests.post`, `get_secret_for_console`, `get_api_base_url`, `get_api_account_id`; E2E uses `@pytest.mark.e2e` + `e2e_console` fixture. <!-- pragma: allowlist secret -->
- **Relevant files**:
  - `safebreach_mcp_data/data_server.py`
  - `safebreach_mcp_data/data_functions.py`
  - `safebreach_mcp_data/data_types.py`
  - `safebreach_mcp_data/tests/test_data_functions.py`
  - `safebreach_mcp_data/tests/test_e2e.py`
  - `safebreach_mcp_core/datetime_utils.py`
  - `safebreach_mcp_core/safebreach_cache.py`
  - `CLAUDE.md`

---

## Problem Analysis

### Problem Description
The SafeBreach Peer Benchmark Score API (`POST /api/data/v1/accounts/{account_id}/score`, delivered by SAF-27621) returns customer/peer/industry posture scores and security-control-category breakdowns. It is currently only reachable from the UI or directly via HTTP. SAF-29415 adds a Data-server MCP tool that wraps this endpoint so MCP clients (including the console AI chat) can answer natural-language questions like "How does my posture compare to peers last month?".

The task is integration-focused — not a new capability. The tool must slot into the existing Data server patterns (auth, caching, parameter style, error handling) and faithfully surface the API's output, including the metadata fields that explain data freshness (`snapshotMonth`, `dataThroughDate`, `customAttackIdsFiltered`).

### Impact Assessment
- **MCP Data server**: new tool, new cache instance, ~+1 API integration. No changes to existing tools.
- **Docs**: `CLAUDE.md` needs updates to the Data Server tools list and Caching section.
- **User experience**: unlocks NL queries about benchmark posture; aligns with DOD goal of console AI-chat parity.

### Risks & Edge Cases
- **Frozen snapshots**: staging / private-dev use a frozen production peer snapshot. Tool must expose `snapshotMonth`/`dataThroughDate` untouched and emit a `hint_to_agent` when peer/industry scores are absent.
- **Datetime format divergence**: peer benchmark API expects ISO 8601 `Z`-suffixed UTC; normalize input to epoch ms (for cache keys) then re-render to ISO 8601 for the body.
- **RBAC / permissions**: handle 403s without leaking auth context; standard `raise_for_status()` with logging.
- **Cache correctness**: key must include console + both dates + sorted `includeTestIds` + sorted `excludeTestIds`.
- **Response shape quirks**: `totalSimulations` only on `customerScore`; `industryScores` may be empty; per-category `securityControlCategory[]` shape is identical across customer/peer/industry but with different fields populated.
- **Custom attack filtering**: `customAttackIdsFiltered` is API-side behavior — surface the count in the response and document the reason in the tool docstring.

---

## Proposed Ticket Content

### Summary (Title)
Add `get_peer_benchmark_score` MCP tool to the Data Server wrapping the Peer Benchmark Score API

### Description

**Background**
SafeBreach's Peer Benchmark Score API (delivered in SAF-27621) exposes `POST /api/data/v1/accounts/{account_id}/score`, returning customer/peer/industry posture scores with security-control-category breakdowns. MCP clients (including the console AI chat) currently cannot query it, forcing users back to the UI. This ticket adds an MCP tool so natural-language posture-comparison queries become possible.

**Technical Context**
- Target server: **Data Server** (port 8001, `safebreach_mcp_data/`).
- Existing layering to mirror: `data_types.py` → `data_functions.py` → `data_server.py` → `tests/`.
- Auth pattern (Data module): `x-apitoken` header (not Bearer); account-scoped URL built from `get_api_base_url(console, 'data')` + `get_api_account_id(console)`.
- Caching pattern: `SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)` gated by `is_caching_enabled("data")`.
- Datetime handling: accept `str | int` at the MCP boundary; normalize via `normalize_timestamp()` → epoch ms (for validation + cache keys); convert back to ISO 8601 `Z` via `convert_epoch_to_datetime()` before POSTing (API expects ISO).

**API Contract** (upstream SAF-27621)
- Request: `POST /api/data/v1/accounts/{account_id}/score`
  - Body: `{startDate, endDate, includeTestIds?, excludeTestIds?}` (ISO 8601 UTC strings; test-ID arrays optional)
- Response: `{startDate, endDate, snapshotMonth, dataThroughDate, attackIds[], attackIdsQueried, customAttackIdsFiltered, customerScore, peerScore, industryScores[]}`
  - Each score object has `score`, `scoreBlocked`, `scoreDetected`, `scoreUnblocked`, + `securityControlCategory[]` (customer also has `totalSimulations`)
  - Score formula: `score = 1.0 * blocked + 0.5 * detected`

**Tool Contract** (MCP-facing — follows Data MCP conventions precisely)
- Tool name: `get_peer_benchmark_score` (matches `get_*` convention).
- Parameters (snake_case at MCP boundary, same style/vocabulary as other Data tools):
  - `console: str = "default"` — SafeBreach console name (identical to all other Data tools)
  - `start_date: Optional[str | int]` (required) — "epoch ms/seconds or ISO 8601 string, e.g. '2026-03-01T00:00:00Z'" (same docstring phrase as `get_tests_history`). Maps to API `startDate`.
  - `end_date: Optional[str | int]` (required) — same format. Maps to API `endDate`.
  - `include_test_ids_filter: Optional[str] = None` — comma-separated planRun IDs to include (mirrors `playbook_attack_id_filter` style). Maps to API `includeTestIds[]`.
  - `exclude_test_ids_filter: Optional[str] = None` — comma-separated planRun IDs to exclude. Maps to API `excludeTestIds[]`.
- Internal normalization: `start_date`/`end_date` via `normalize_timestamp()` → epoch ms (for validation + cache keys) → back to ISO 8601 UTC `Z` via `convert_epoch_to_datetime()` for the POST body. Comma-separated ID filters split via `[v.strip() for v in s.split(",") if v.strip()]`.
- Returns: the full API response, pass-through. Includes a `hint_to_agent` field when peer/industry data is empty (same field name used elsewhere in Data MCP responses for agent guidance).
- Docstring must explain `snapshotMonth` (peer comparison month), `dataThroughDate` (ETL freshness), `customAttackIdsFiltered` (auto-filtered custom attacks), and the score formula — following the "Detailed parameter docs" format used by existing Data tools.

**Function contract** (business logic):
- `sb_get_peer_benchmark_score(console, start_date, end_date, include_test_ids_filter=None, exclude_test_ids_filter=None)` — mirrors `sb_get_tests_history` style (console first-positional default, Optional filters after).
- Cache instance: `peer_benchmark_cache = SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)` — declared alongside other caches at `data_functions.py` module top.
- Cache key: `f"peer_benchmark_{console}_{start_ms}_{end_ms}_{sorted_includes}_{sorted_excludes}"` — consistent with existing cache-key patterns.
- Error handling: `try/except` around `requests.post(..., timeout=120)` + `response.raise_for_status()` + `logger.error(...)` — identical to other Data tools.

**Problem Description**
- No MCP access to peer benchmark today.
- API uses camelCase + ISO datetimes, while MCP tools use snake_case + epoch-friendly inputs — the wrapper handles the translation.
- Staging/private-dev uses a frozen peer snapshot; responses must surface this transparently via `snapshotMonth` / `dataThroughDate`.

**Affected Areas**
- `safebreach_mcp_data/data_functions.py` — add `sb_get_peer_benchmark_score` + `peer_benchmark_cache`
- `safebreach_mcp_data/data_server.py` — register `get_peer_benchmark_score` MCP tool
- `safebreach_mcp_data/data_types.py` — optional shaping helpers (if needed)
- `safebreach_mcp_data/tests/test_data_functions.py` — unit tests
- `safebreach_mcp_data/tests/test_e2e.py` — smoke E2E (`@pytest.mark.e2e`)
- `CLAUDE.md` — Data Server tools list (add item 15, renumber) + Caching Strategy (add `peer_benchmark` cache line)

### Acceptance Criteria

- [ ] New MCP tool `get_peer_benchmark_score` is registered on the Data Server (port 8001) via `@self.mcp.tool(...)` in `data_server.py` — following the exact pattern used by `get_tests_history_tool`.
- [ ] Tool parameters (snake_case, consistent with existing Data MCP tools): `console: str = "default"`, `start_date: Optional[str | int]` (required), `end_date: Optional[str | int]` (required), `include_test_ids_filter: Optional[str] = None` (comma-separated), `exclude_test_ids_filter: Optional[str] = None` (comma-separated).
- [ ] `start_date` / `end_date` accept "epoch ms/seconds or ISO 8601 string, e.g. '2026-03-01T00:00:00Z'" — using the identical docstring phrasing as `get_tests_history`.
- [ ] Wrapper normalizes both dates via `normalize_timestamp()` → epoch ms; business logic converts epoch ms back to ISO 8601 UTC `Z` via `convert_epoch_to_datetime()` before building the POST body.
- [ ] Business logic calls `POST {get_api_base_url(console, 'data')}/api/data/v1/accounts/{get_api_account_id(console)}/score` with `x-apitoken` header and `timeout=120` — matching the pattern at `data_functions.py:658-687`.
- [ ] POST body uses camelCase keys: `{startDate, endDate, includeTestIds?, excludeTestIds?}`. Test ID filters split via `[v.strip() for v in s.split(",") if v.strip()]` and only included in the body when non-empty.
- [ ] Response contains customer/peer/industry scores with `securityControlCategory[]` breakdowns, plus `snapshotMonth`, `dataThroughDate`, `attackIds[]`, `attackIdsQueried`, `customAttackIdsFiltered` (pass-through).
- [ ] When peer or industry scores are empty, response includes a `hint_to_agent` field explaining the likely cause (frozen snapshot on staging/private-dev, or insufficient data) — same field name used elsewhere in Data MCP.
- [ ] Response matches the UI/API output exactly (verified via E2E on a console with benchmark data).
- [ ] New cache `peer_benchmark_cache = SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)` declared alongside existing caches in `data_functions.py`. Cache gated by `is_caching_enabled("data")`. Cache key format: `f"peer_benchmark_{console}_{start_ms}_{end_ms}_{sorted_includes}_{sorted_excludes}"`.
- [ ] Errors handled with the existing convention: `response.raise_for_status()` inside `try/except`, `logger.error(...)` on failure, no token leakage in logs.
- [ ] Tool docstring documents all parameters (stock phrasing where possible), `snapshotMonth`, `dataThroughDate`, `customAttackIdsFiltered`, score formula (`1.0*blocked + 0.5*detected`), and the ISO-datetime contract.
- [ ] Unit tests in `test_data_functions.py` cover: happy path, include-only filter, exclude-only filter, epoch-input normalization, ISO-input normalization, empty peer/industry → `hint_to_agent`, 403 error, 400 error. Mocks: `requests.post`, `get_secret_for_console`, `get_api_base_url`, `get_api_account_id`. `setup_method` clears `peer_benchmark_cache`.
- [ ] One E2E test in `test_e2e.py` (`@pytest.mark.e2e` + `e2e_console` fixture) validates the tool against a real console.
- [ ] `CLAUDE.md` updated: Data Server tools list gains the new tool; Caching Strategy bullet list gains a `peer_benchmark — maxsize=3, ttl=600s` line.
- [ ] Tool is accessible from the console AI chat (per DOD).

### Suggested Labels/Components
- Component: `data-mcp`, `peer-benchmark` (if labels exist)
- Labels: none required beyond existing ticket labels

---

## Proposed Ticket Content — JIRA Markdown

**Description (Markdown for JIRA):**
```markdown
### Background

SafeBreach's Peer Benchmark Score API (delivered in SAF-27621) exposes `POST /api/data/v1/accounts/{account_id}/score`, returning customer/peer/industry posture scores with security-control-category breakdowns. MCP clients (including the console AI chat) currently cannot query it, forcing users back to the UI. This ticket adds an MCP tool so natural-language posture-comparison queries become possible.

### Technical Context

* Target server: **Data Server** (port 8001, `safebreach_mcp_data/`)
* Layering to mirror: `data_types.py` → `data_functions.py` → `data_server.py` → `tests/`
* Auth pattern: `x-apitoken` header (not Bearer); URL built from `get_api_base_url(console, 'data')` + `get_api_account_id(console)`
* Caching: `SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)` gated by `is_caching_enabled("data")`
* Datetime: accept ISO 8601 or epoch at MCP boundary; normalize via `normalize_timestamp()` → epoch ms (validation + cache keys); convert back to ISO 8601 `Z` via `convert_epoch_to_datetime()` before POSTing (API expects ISO)

### API Contract (upstream SAF-27621)

* Request: `POST /api/data/v1/accounts/{account_id}/score`
* Request body: `{startDate, endDate, includeTestIds?, excludeTestIds?}` — ISO 8601 UTC strings
* Response: `{startDate, endDate, snapshotMonth, dataThroughDate, attackIds[], attackIdsQueried, customAttackIdsFiltered, customerScore, peerScore, industryScores[]}`
* Score fields: `score`, `scoreBlocked`, `scoreDetected`, `scoreUnblocked`, + `securityControlCategory[]` (customer also has `totalSimulations`)
* Score formula: `score = 1.0 * blocked + 0.5 * detected`

### Tool Contract (MCP-facing — follows Data MCP conventions)

* Tool name: `get_peer_benchmark_score`
* Parameters (snake_case, consistent with existing Data MCP tools):
** `console: str = "default"`
** `start_date: Optional[str | int]` (required) — epoch ms/seconds or ISO 8601 string, e.g. `'2026-03-01T00:00:00Z'`. Maps to API `startDate`
** `end_date: Optional[str | int]` (required) — same format. Maps to API `endDate`
** `include_test_ids_filter: Optional[str] = None` — comma-separated planRun IDs. Maps to API `includeTestIds[]` (mirrors `playbook_attack_id_filter` style)
** `exclude_test_ids_filter: Optional[str] = None` — comma-separated planRun IDs. Maps to API `excludeTestIds[]`
* Wrapper normalizes dates via `normalize_timestamp()` → epoch ms; business logic converts back to ISO 8601 UTC `Z` via `convert_epoch_to_datetime()` before POSTing
* Returns: full API response pass-through, plus `hint_to_agent` when peer/industry is empty
* Docstring explains `snapshotMonth`, `dataThroughDate`, `customAttackIdsFiltered`, score formula, and ISO-datetime contract

### Function Contract (business logic)

* `sb_get_peer_benchmark_score(console, start_date, end_date, include_test_ids_filter=None, exclude_test_ids_filter=None)` — mirrors `sb_get_tests_history` style
* New cache: `peer_benchmark_cache = SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)` gated by `is_caching_enabled("data")`
* Cache key: `f"peer_benchmark_{console}_{start_ms}_{end_ms}_{sorted_includes}_{sorted_excludes}"`
* HTTP: `requests.post(...)` with `x-apitoken` header and `timeout=120` (matches existing Data MCP pattern)
* Errors: `response.raise_for_status()` + `logger.error(...)` — same convention as other Data tools

### Problem Description

* No MCP access to peer benchmark today
* API uses camelCase + ISO datetimes; MCP tools use snake_case + epoch-friendly inputs — wrapper handles translation
* Staging/private-dev uses a frozen peer snapshot; response must surface this via `snapshotMonth` / `dataThroughDate`

### Affected Areas

* `safebreach_mcp_data/data_functions.py` — `sb_get_peer_benchmark_score` + `peer_benchmark_cache`
* `safebreach_mcp_data/data_server.py` — register `get_peer_benchmark_score` MCP tool
* `safebreach_mcp_data/data_types.py` — optional shaping helpers
* `safebreach_mcp_data/tests/test_data_functions.py` — unit tests
* `safebreach_mcp_data/tests/test_e2e.py` — smoke E2E
* `CLAUDE.md` — Data Server tools list + Caching section
```

**Acceptance Criteria:**
```markdown
* MCP tool `get_peer_benchmark_score` is registered on the Data Server (port 8001) via `@self.mcp.tool(...)` — following the `get_tests_history_tool` pattern
* Tool parameters (snake_case, consistent with existing Data MCP tools): `console: str = "default"`, `start_date: Optional[str | int]` (required), `end_date: Optional[str | int]` (required), `include_test_ids_filter: Optional[str] = None` (comma-separated), `exclude_test_ids_filter: Optional[str] = None` (comma-separated)
* `start_date` / `end_date` accept "epoch ms/seconds or ISO 8601 string, e.g. '2026-03-01T00:00:00Z'" — identical docstring phrasing as `get_tests_history`
* Wrapper normalizes dates via `normalize_timestamp()` → epoch ms; business logic converts back to ISO 8601 UTC `Z` via `convert_epoch_to_datetime()` before POSTing
* Business logic calls `POST {base_url}/api/data/v1/accounts/{account_id}/score` with `x-apitoken` header and `timeout=120` (matches `data_functions.py:658-687`)
* POST body uses camelCase: `{startDate, endDate, includeTestIds?, excludeTestIds?}`; filters split via `[v.strip() for v in s.split(",") if v.strip()]` and only included when non-empty
* Response contains customer/peer/industry scores with `securityControlCategory[]` breakdowns, plus `snapshotMonth`, `dataThroughDate`, `attackIds[]`, `attackIdsQueried`, `customAttackIdsFiltered` (pass-through)
* Empty peer/industry scores → response includes `hint_to_agent` explaining the cause (frozen snapshot or insufficient data)
* Response matches UI/API output exactly (verified via E2E on a console with benchmark data)
* New cache `peer_benchmark_cache = SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)` declared alongside existing caches; gated by `is_caching_enabled("data")`; key `f"peer_benchmark_{console}_{start_ms}_{end_ms}_{sorted_includes}_{sorted_excludes}"`
* RBAC (403) and API errors handled via `response.raise_for_status()` inside `try/except` with `logger.error(...)`; no token leakage
* Tool docstring documents all params, `snapshotMonth`, `dataThroughDate`, `customAttackIdsFiltered`, score formula (`1.0*blocked + 0.5*detected`), ISO-datetime contract
* Unit tests in `test_data_functions.py` cover: happy path, include-only, exclude-only, epoch input, ISO input, empty peer/industry hint, 403, 400 — mocks: `requests.post`, `get_secret_for_console`, `get_api_base_url`, `get_api_account_id`; `setup_method` clears `peer_benchmark_cache`
* One E2E test (`@pytest.mark.e2e` + `e2e_console` fixture) in `test_e2e.py` validates against a real console
* `CLAUDE.md` updated: Data Server tools list + Caching Strategy adds `peer_benchmark — maxsize=3, ttl=600s` line
* Tool accessible from console AI chat (per DOD)
```
