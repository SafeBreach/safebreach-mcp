# Ticket Context: SAF-29415

## Status
Phase 6: PRD Created

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

### SafeBreach backend `data` service (/Users/yossiattas/projects/data) — ground-truth research

Route: `POST /data/v1/accounts/{accountId}/score`, OperationId `getScore`, defined in `src/api/dashboardapi.json` (OpenAPI 2.0 Swagger). Handler chain:
- `src/dashboardApi/api/scoreApi.js` — `ScoreApi.getScore({accountId, params})`
- `src/dashboardApi/controller/scoreController.js` — business logic
- `src/common/dal/executionsHistoryDao.js` — Elasticsearch aggregation
- `src/dashboardApi/service/dataInsightsService.js` — POST `/api/v1.0/peer-benchmark` to data-insights-gateway

**Auth**: standard signed-request via `@safebreach/common` (x-account-id + signed header). **No endpoint-level RBAC** — all users in an account can call it.

**Request schema** (body as `params`):
- `startDate` (required, ISO 8601 date-time string, UTC)
- `endDate` (required, ISO 8601 date-time string, UTC)
- `includeTestIds` (optional, array of strings — planRunIds)
- `excludeTestIds` (optional, array of strings — planRunIds)
- **No other fields.** No query-string params. No pagination. No platform/industry override.

**Backend validation** (scoreApi.js `validateParams`, lines ~37-53):
1. `startDate` and `endDate` both required → 400 `"startDate and endDate are required"`
2. `startDate < endDate` enforced → 400 `"startDate must be before endDate"`
3. `includeTestIds` XOR `excludeTestIds` (mutually exclusive when both non-empty) → 400 `"Cannot provide both includeTestIds and excludeTestIds..."`
4. Empty/omitted both → defaults to "all tests in range"
5. Dates are ISO-only — **no epoch accepted at backend**

**Response schema** — authoritative, from Swagger + handler + tests:

Top-level `ScoreResponse` fields (all present unless noted):
- `startDate`, `endDate` — echo of request
- `snapshotMonth` — `YYYY-MM`; backend falls back to `endDate.slice(0,7)` if gateway omits
- `dataThroughDate` — `YYYY-MM-DD`; **can be `null`** if gateway has no snapshot
- `attackIds: string[]` — standard (non-custom) attack IDs queried
- `attackIdsQueried: int`
- `customAttackIdsFiltered: int` — count of custom attacks (moveId ≥ `10_000_000`) filtered out
- `customerScore: ScoreBreakdown | null` — null when no executions
- `peerScore: ScoreBreakdown | null` — null when gateway has no `all_industries` bucket
- `industryScores: ScoreBreakdown[]` — filtered to non-null scores; can be empty

`ScoreBreakdown`:
- `score: float` (= 1.0 × blocked + 0.5 × detected)
- `scoreBlocked: float`
- `scoreDetected: float`
- `scoreUnblocked: float`
- `totalSimulations: int` — **customerScore only**
- `industry: string` — **industryScores elements only**
- `securityControlCategory: ControlScore[]`

`ControlScore`:
- `name: string` (e.g., "Network Inspection", "Network Access", "Email")
- `score`, `scoreBlocked`, `scoreDetected` — floats
- `scoreUnblocked: float` — **customerScore entries only; omitted in peer/industry**

**HTTP response codes**:
- `200 OK` — normal success (with payload above)
- `204 No Content` — empty body when: no executions in ES match the filters, OR all returned attacks are custom (moveId ≥ 10,000,000). **Real code path, not error.**
- `400` — validation failures (see list)
- `401` — signed-auth failure (upstream middleware)
- `403` — not expected from this endpoint (no RBAC gate), but possible from upstream deployment blocker
- `404` — not returned by this endpoint
- `500` — ES query failure or gateway timeout/unavailable

**Business-logic nuggets** (for docstring accuracy):
- `customAttackIdsFiltered` semantics: custom-attack IDs (≥ 10M) are never unique across accounts, so they are excluded from peer comparison automatically
- Industry of customer is determined server-side from Salesforce mapping; callers cannot override
- Peer aggregation uses a monthly S3 snapshot via data-insights-gateway; no caching on data service itself
- Staging / private-dev gateways use a frozen prod snapshot
- Score formula documented literally: `score = 1.0 × blocked + 0.5 × detected`

**Test fixture example** (from `test/dashboardApi/api/scoreApi.test.js`):
```js
GATEWAY_RESPONSE = {
  snapshot_month: '2026-02',
  data_through_date: '2026-02-28',
  scores: [
    { attackid: '10054', industry_bucket: 'all_industries', security_control_category: 'Network Inspection', blocked_percentage: 0.7, detected_percentage: 0.04, total_all: 48000 },
    { attackid: '10054', industry_bucket: 'Healthcare', security_control_category: 'Network Inspection', blocked_percentage: 0.75, detected_percentage: 0.01, total_all: 6000 },
  ]
}
```

**Key implications for MCP tool**:
1. Must handle HTTP 204 — `response.status_code == 204` → return a friendly structured result with `hint_to_agent` explaining "no executions in window or all attacks are custom".
2. Must handle null `customerScore` / `peerScore` / `dataThroughDate` and empty `industryScores[]` gracefully — include `hint_to_agent` per condition.
3. `include_test_ids_filter` vs `exclude_test_ids_filter` — decide whether to enforce mutual exclusivity client-side or let backend 400 be surfaced. (Decision deferred to brainstorm.)
4. Date validation at MCP boundary is optional (backend validates), but catching `start >= end` locally gives better UX.
5. Tool docstring should explicitly document the custom-attack threshold (`moveId ≥ 10_000_000`), the 204 case, null fields, and the peer industry mapping (server-side, not overridable).
6. No RBAC gating needed — remove 403 test from the AC's unit-test list (keep generic "API error" case).

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

## Brainstorm Outcomes (Phase 5)

**Locked-in decisions** (all approved by user):

1. **Response shape — A1: Pass-through with rename mapping + additive hint_to_agent.**
   - Applied via a key-rename mapping in `data_types.py` (same pattern as `reduced_test_summary_mapping` at lines 13-20).
   - Semantic content preserved 1:1; no field dropped; no score re-computation.
   - Rename mapping:
     | Backend (camelCase) | MCP response | Why |
     |---|---|---|
     | `startDate` / `endDate` | `start_date` / `end_date` | snake_case |
     | `snapshotMonth` | `peer_snapshot_month` | clarify this is peer snapshot, not query window |
     | `dataThroughDate` | `peer_data_through_date` | explicit: peer data freshness |
     | `attackIds` | `attack_ids` | snake_case |
     | `attackIdsQueried` | `attack_ids_count` | clarify it's a count |
     | `customAttackIdsFiltered` | `custom_attacks_filtered_count` | clarify count; "IDs filtered" ambiguous |
     | `customerScore` | `customer_score` | snake_case |
     | `peerScore` | `all_peers_score` | disambiguate: **all SafeBreach peers** (not customer's industry peers) |
     | `industryScores` | `customer_industry_scores` | explicit scope: customer's own industry only (Salesforce mapping, server-side, not overridable) |
     | `industry` (inside) | `industry_name` | explicit |
     | `score` / `scoreBlocked` / `scoreDetected` / `scoreUnblocked` | `score` / `score_blocked` / `score_detected` / `score_unblocked` | snake_case |
     | `totalSimulations` | `total_simulations` | snake_case |
     | `securityControlCategory` (array) | `security_control_breakdown` | it's a breakdown *by* category |
     | `name` (inside breakdown) | `control_category_name` | explicit |
   - Additive top-level field: `hint_to_agent: str` — only present when HTTP 204 or any of `customer_score` / `all_peers_score` / `industry_scores` are null/empty.

2. **Caching — B1: Full-key cache.**
   - `peer_benchmark_cache = SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)`.
   - Key: `f"peer_benchmark_{console}_{start_ms}_{end_ms}_{sorted_includes_csv}_{sorted_excludes_csv}"`.
   - Gated by `is_caching_enabled("data")` (env var `SB_MCP_CACHE_DATA`).

3. **Filter-ID style — C1: Comma-separated string + `_filter` suffix.**
   - `include_test_ids_filter: Optional[str] = None`, `exclude_test_ids_filter: Optional[str] = None`.
   - Split via `[v.strip() for v in s.split(",") if v.strip()]`.
   - Omitted from API body when empty/null.

4. **Mutual exclusivity — validate at MCP boundary.**
   - If both `include_test_ids_filter` and `exclude_test_ids_filter` are non-empty after parsing, raise a clean `ValueError` with a clear message (faster agent feedback than a backend 400).
   - Still surface backend 400s gracefully in case of ordering / date issues.

5. **HTTP 204 / null scores — structured empty result with hint.**
   - On 204: return `{start_date, end_date, customer_score: None, all_peers_score: None, industry_scores: [], hint_to_agent: "No executions in the requested window, or all matched attacks were custom (peer benchmark excludes custom attack IDs >= 10_000_000)."}`.
   - On 200 with `customerScore == null`: pass through with hint explaining "no executions in window".
   - On 200 with `peerScore == null` / `industryScores == []`: hint explaining "no peer data for this window (possibly frozen snapshot on staging/private-dev)".
   - Hints are composed when multiple conditions apply.

6. **Docstring requirements** (from backend findings):
   - Document custom-attack threshold: `moveId >= 10_000_000`.
   - Document that industry is server-side determined (Salesforce mapping, not overridable).
   - Document peer snapshot monthly granularity + ETL daily-update behavior.
   - Document 204 handling.
   - Drop 403 from unit tests (no RBAC on this endpoint); keep generic 500/backend-error case.

**Out of scope (confirmed non-goals)**:
- NL intent parsing (MCP client's responsibility).
- Score re-computation.
- Explainability beyond what API returns.
- Platform / industry override (API doesn't support it).
