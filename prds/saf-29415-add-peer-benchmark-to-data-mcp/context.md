# Ticket Context: SAF-29415

## Status
Phase 8: JIRA Updated

## Mode
Improving

## Original Ticket
- **Summary**: Add the new Peer Benchmark Score API to the DATA MCP
- **Status**: In Progress
- **Assignee**: Yossi Attas
- **Reporter**: Shahaf Raviv
- **Priority**: Medium
- **Created**: 2026-03-24
- **Link**: https://safebreach.atlassian.net/browse/SAF-29415

### Description (original)
**User Story**: As a SafeBreach user via MCP, I want to query Peer Benchmark scores using natural language, so that I can compare my security posture to peers and industry without using the UI.

**UX/UI**: No UI changes (MCP-only). Exposed as MCP tool. Return structured JSON (agent-friendly). Support summarized + raw data.

Example queries:
- "What is my peer benchmark score?"
- "Compare me to my industry peers last month"
- "Show benchmark scores for Jan 1–31"
- "Include tests X, Y" / "Exclude test Z"
- "Breakdown by control category"

**Functional Requirements** (upstream API: SAF-27621):
1. Expose Peer Benchmark via MCP (uses existing API)
2. Return: customer score, peer score, customer's industry score, security control category breakdown
3. Support filters: `start_time`, `end_time`, `include_test_ids[]`, `exclude_test_ids[]`
4. Support combined filters
5. Translate natural language → API request
6. Return structured response with filters + results
7. Handle errors (invalid input, no data, permissions)

**Non-Functional**: Match API/UI exactly; respect RBAC (viewer supported); fast/interactive; consistent schema.

**DOD**: MCP tool implemented + accessible from console AI chat; supports time + test filters; returns customer/peer/industry + breakdown; NL queries work; results match API/UI; product reviewed.

### Comments (summarized)
1. **Endpoint examples (Yossi, 2026-04-13)**: `POST /api/data/v1/accounts/{account}/score` with body `{startDate, endDate, includeTestIds?, excludeTestIds?}`. Response shape includes `snapshotMonth`, `dataThroughDate`, `attackIds`, `attackIdsQueried`, `customAttackIdsFiltered`, `customerScore`, `peerScore`, `industryScores[]`. Each score: `score`, `scoreBlocked`, `scoreDetected`, `scoreUnblocked` + `securityControlCategory[]`. Formula: `score = 1.0*blocked + 0.5*detected`.
2. **Q&A (Yossi, 2026-04-13)**:
   - `snapshotMonth`: full month peer snapshot used for comparison (customer score still uses exact range)
   - `dataThroughDate`: last day ETL included; freshness indicator; ETL daily
   - `customAttackIdsFiltered`: count of custom attacks excluded (custom IDs aren't unique across customers)
   - Staging/private-dev uses frozen production snapshot

## Task Scope
Add a new MCP tool to the Data Server (port 8001) that wraps the Peer Benchmark Score API. Should follow existing data-server patterns (types → functions → server → tests), integrate with `SafeBreachAuth`, be cached if appropriate, and support the documented filters (`startDate`, `endDate`, `includeTestIds`, `excludeTestIds`).

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp (branch: saf-29415-add-peer-benchmark-to-data-mcp)

## Investigation Findings

### safebreach-mcp (Data Server)

**Layer architecture** (for every new tool):
1. `safebreach_mcp_data/data_types.py` — mapping dicts + transform funcs (e.g., `get_reduced_test_summary_mapping`)
2. `safebreach_mcp_data/data_functions.py` — business logic: `sb_get_*` async-style funcs; HTTP via `requests`; caching; pagination/filtering
3. `safebreach_mcp_data/data_server.py` — MCP tool registration via `@self.mcp.tool(name=..., description=...)` decorator under `_register_tools()`; normalizes timestamps then delegates

**HTTP / Auth pattern (data module uses `x-apitoken`, NOT Bearer):**
```python
apitoken = get_secret_for_console(console)
base_url = get_api_base_url(console, 'data')
account_id = get_api_account_id(console)
api_url = f"{base_url}/api/data/v1/accounts/{account_id}/<endpoint>"
headers = {"Content-Type": "application/json", "x-apitoken": apitoken}
response = requests.post(api_url, headers=headers, json=data, timeout=120)
response.raise_for_status()
```
Confirmed by `data_functions.py:659-687`. Peer benchmark endpoint `POST /api/data/v1/accounts/{account_id}/score` slots into this pattern unchanged.

**Caching:** `SafeBreachCache` (cachetools.TTLCache wrapper, thread-safe). Declared at module top (lines 32-35). Usage:
```python
if is_caching_enabled("data"):
    cached = xxx_cache.get(cache_key); if cached is not None: return cached
# ... API call ...
if is_caching_enabled("data"):
    xxx_cache.set(cache_key, result)
```
Toggle via `SB_MCP_CACHE_DATA=true`. Size convention for data tools: `maxsize=3, ttl=600` (10 min). Cache key pattern: `f"{name}_{console}_{param1}_{param2}..."`.

**Datetime handling mismatch (important):**
- Convention for existing tools: wrapper accepts epoch int OR ISO 8601 str via `normalize_timestamp()` → returns **epoch ms**, which downstream APIs expect.
- Peer benchmark API, per endpoint docs in ticket comments, expects **ISO 8601 strings** in the request body (`"startDate": "2026-03-15T00:00:00.000Z"`). So this tool must accept epoch+ISO like the others, normalize to epoch ms, then convert **back** to ISO 8601 (UTC `Z` suffix) using `convert_epoch_to_datetime(ms)["iso_datetime"]` before POSTing.

**Tool registration pattern to mirror** — `get_test_simulations_tool` (data_server.py:100-137) is a good template: typed Optional params, timestamp normalization, delegate to `sb_*` function.

**Test conventions:**
- Unit tests: `safebreach_mcp_data/tests/test_data_functions.py` — mock `requests.post`, `get_secret_for_console`, `get_api_account_id`, `get_api_base_url`. `setup_method` clears caches.
- Integration tests: `test_integration.py` — multi-function flows with same mocks.
- E2E tests: `test_e2e.py` — `@pytest.mark.e2e` + `e2e_console` fixture skips if `E2E_CONSOLE` unset.

**Naming (matches convention):** `get_peer_benchmark_score` (tool), `sb_get_peer_benchmark_score` (function), `peer_benchmark_cache = SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)`.

**Docs consumers to update:**
- `CLAUDE.md` "Data Server (Port 8001)" tools list + Caching section (add new cache line)
- `README.md` if it enumerates tools
- Cache-config env var docs (no new env var; reuses `SB_MCP_CACHE_DATA`)

**No pre-existing peer/benchmark code** in `safebreach_mcp_data/` — greenfield addition.

## Problem Analysis

**Problem Scope**: Peer Benchmark Score API (SAF-27621) is unreachable from MCP clients. SAF-29415 adds a Data-server MCP tool wrapping `POST /api/data/v1/accounts/{account_id}/score` so MCP clients and the console AI chat can retrieve customer/peer/industry scores + control-category breakdowns via natural language.

**Affected Areas**:
- `safebreach_mcp_data/data_functions.py` — new `sb_get_peer_benchmark_score`; new `peer_benchmark_cache`
- `safebreach_mcp_data/data_types.py` — optional shaping helpers (pass-through preferred)
- `safebreach_mcp_data/data_server.py` — new `get_peer_benchmark_score` MCP tool wrapper
- `safebreach_mcp_data/tests/test_data_functions.py` — unit tests mocking `requests.post`
- `safebreach_mcp_data/tests/test_e2e.py` — smoke E2E
- `CLAUDE.md` — Data Server tools list + Caching section

**Input Contract Decisions**:
- Parameter names: snake_case at MCP boundary (`start_time`, `end_time`, `include_test_ids`, `exclude_test_ids`); convert to camelCase (`startDate`, etc.) in POST body.
- Accept `str | int` timestamps; normalize via `normalize_timestamp()` → epoch ms (for cache-key stability + validation), then convert back to ISO 8601 UTC (`Z` suffix) via `convert_epoch_to_datetime()` for the API body.
- `start_time` and `end_time` both **required**.
- Response: return full payload by default (small size; supports both summarized + raw needs).

**Risks & Edge Cases**:
- Empty/frozen peer snapshot on staging/private-dev → surface `snapshotMonth` / `dataThroughDate` transparently; emit `hint_to_agent` if peer/industry scores absent.
- Invalid date range / permission errors → rely on API `raise_for_status()`; log + re-raise clean error.
- `include_test_ids` vs `exclude_test_ids` mutual exclusivity — treated as open question; default to pass-through (let API validate).
- Cache key must include: console + startDate + endDate + sorted include/exclude lists.
- `totalSimulations` exists on customerScore only.
- `customAttackIdsFiltered` auto-handled server-side — document in docstring.

**Dependencies**: Upstream API (SAF-27621) must be deployed on target console for E2E. No new Python deps; reuses `SB_MCP_CACHE_DATA`.

**Non-Goals**: NL intent parsing (MCP client's job); new datetime helpers; explainability computed locally.

## Proposed Improvements
(Phase 6)
