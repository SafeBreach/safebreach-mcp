# Manual Test Plan — Peer Benchmark Score MCP Tool (SAF-29415)

> Generated from PRD: `prds/saf-29415-add-peer-benchmark-to-data-mcp/prd.md`
> Branch: `saf-29415-add-peer-benchmark-to-data-mcp`
> Date: 2026-04-13

## Context for the Tester

Automated coverage on this branch:
- **36 unit tests** (10 transform + 16 business logic + 10 MCP wrapper) cover Python-side
  contracts: rename mapping, HTTP body shape, ISO conversion, cache behavior, hint composition,
  204 handling, mutual exclusivity, token-leak in `logger.error` format strings, FastMCP tool
  registration via `list_tools()`.
- **1 E2E smoke** (`@pytest.mark.e2e`, `peer_benchmark_e2e_console` fixture) verified live against
  `staging.sbops.com` (customer 0.80 vs all-peers 0.53).

The cases below cover what those tests structurally **cannot** verify — LLM behavior, MCP
transport boundary, real-server log rendering, and the in-console / desktop UX surface called
out in the ticket DOD.

---

## Tier 1: Direct Mission Critical

- [ ] **T1.1 — Claude Desktop tool surface (transport boundary)** | Risk: High
  - **Why**: Unit tests verify the tool registers Python-side via `list_tools()`. Manual
    must confirm it survives the `mcp-remote` / SSE / streamable-http transport into Claude
    Desktop and is invokable from there.
  - **Steps**:
    1. Start the data server locally: `uv run -m safebreach_mcp_data.data_server`.
    2. Confirm `safebreach-data` (or your equivalent) entry exists in
       `/Library/Application Support/Claude/claude_desktop_config.json` (see CLAUDE.md
       § Claude Desktop Integration).
    3. Restart Claude Desktop; in a fresh chat, type
       *"What tools do you have for SafeBreach?"*.
  - **Expected**: `get_peer_benchmark_score` appears in the listed tools with a description
    derived from the PRD-mandated docstring (peers-vs-industry paragraph included).

- [ ] **T1.2 — Console AI chat (ticket DOD)** | Risk: High
  - **Why**: The ticket DOD explicitly requires the tool be accessible from the console AI
    chat, not just Claude Desktop. Different MCP host; different transport plumbing.
  - **Steps**:
    1. Open the SafeBreach console AI chat (in an environment where the data MCP is wired in
       and the `/score` endpoint is deployed — i.e., `staging.sbops.com` today).
    2. Ask: *"How does my security posture compare to my peers last month?"*.
  - **Expected**: The chat invokes `get_peer_benchmark_score` with a sane 30-day window,
    receives the response, and produces a coherent narrative referencing customer score,
    all-peers score, and (if any) the customer's industry score.

- [ ] **T1.3 — LLM peers-vs-industry disambiguation** | Risk: High
  - **Why**: The docstring is the **only** signal the LLM has to distinguish
    `all_peers_score` (cross-industry mean) from `customer_industry_scores` (own-industry only,
    not overridable). Unit tests verify the field names; manual verifies the LLM actually
    reasons about them correctly when the user asks ambiguous follow-ups.
  - **Steps** (in either Claude Desktop or console AI chat):
    1. Run a successful query first (e.g., last 30 days).
    2. Follow up with: *"Are these peer scores from companies in my industry?"*.
    3. Then: *"Can I change my industry filter?"*.
  - **Expected**:
    - Step 2: LLM correctly explains `all_peers_score` is across **all** SafeBreach customers
      regardless of industry, and `customer_industry_scores` is scoped to the customer's own
      industry only.
    - Step 3: LLM correctly says it can't be overridden — it's determined server-side by a
      Salesforce industry mapping.

---

## Tier 2: Immediate Neighbors

- [ ] **T2.1 — Cross-tool composition with utilities server** | Risk: Medium | Why:
  utilities-server feeds epoch values into this tool when the user asks in natural-language
  date terms ("last month", "Q1"). Unit tests verify the math in isolation; this verifies the
  agent flow.
  - **Steps**: In the same MCP client, ask: *"Show benchmark scores for January 1 through
    January 31, 2026."*.
  - **Expected**: The agent calls `convert_datetime_to_epoch` (utilities, port 8002) twice,
    then `get_peer_benchmark_score` with those epoch values; result echoes
    `start_date: 2026-01-01...` and `end_date: 2026-01-31...`.

- [ ] **T2.2 — Frozen-snapshot hint surfaces in narrative** | Risk: Medium | Why: The
  `hint_to_agent` field is the LLM's signal to explain "no peer data" rather than invent
  numbers. Unit tests verify the hint string content; manual verifies the LLM actually
  consumes and surfaces it.
  - **Steps**: On a staging/private-dev console with a frozen peer snapshot, ask:
    *"Compare my posture to peers last week."*.
  - **Expected**: The LLM responds explaining no peer data is available for the window
    (mentions frozen snapshot or staging caveat) — no fabricated peer percentages.

- [ ] **T2.3 — Cache visibility in stats logger** | Risk: Low | Why: Phase 2 added
    `peer_benchmark_cache`. The 5-min `SafeBreachCache` background task should pick it up.
  - **Steps**:
    1. Start data server with `SB_MCP_CACHE_DATA=true uv run -m safebreach_mcp_data.data_server`.
    2. Trigger two identical tool calls (via Claude Desktop or `curl` through mcp-remote).
    3. Wait up to 5 min for the cache stats log line.
  - **Expected**: A log line includes `peer_benchmark` cache stats (size 1, hits ≥ 1).

---

## Tier 3: Ripple Effect

- [ ] **T3.1 — Token leak audit on real server logs (500 path)** | Risk: Low | Why: Test 13
  asserts no token in `logger.error`'s format string, but real server logs pass through
  uvicorn / structured logging / SSE wrappers. Cheap eyeball.
  - **Steps**: Force a 500 (e.g., temporarily point at an invalid `DATA_URL`, or use an
    expired token), tail the data-server stdout/stderr, trigger one `get_peer_benchmark_score`
    call.
  - **Expected**: The error log line carries the console name and URL but NOT the token
    value; no `Authorization`/`x-apitoken` header value appears anywhere in the captured
    output.

- [ ] **T3.2 — Pentest01 (endpoint-not-deployed) error UX** | Risk: Medium | Why: As of
  2026-04-13 `/score` isn't on pentest01 — the default `E2E_CONSOLE` for this repo. Users
  pointing the tool at pentest01 will get a 404. The error message that bubbles up to the
  LLM should be intelligible enough for the agent to react gracefully.
  - **Steps**: Manually invoke the tool against `pentest01.safebreach.com`. Either:
    - Override `E2E_CONSOLE=pentest01` and run the tool from a Python REPL (bypassing the
      Phase 4 fixture), or
    - Configure pentest01 in your client and call the tool from Claude Desktop.
  - **Expected**: A clean HTTPError surfaces to the agent (status 404 or routing error),
    no stack trace leak; agent narrative apologizes and suggests trying a different console.

---

Total: 8 tests (3 critical, 3 neighbor, 2 ripple)
Estimated time: ~14 minutes (3×3 + 3×2 + 2×2 = ~17 min, optimistic 14 if T2.3 cache wait
overlaps with T1 walkthrough)

**Sequencing tip**: Run T1.1 → T1.2 → T1.3 → T2.2 in one Claude Desktop / console AI chat
session (they share the same setup); kick off T2.3 cache observation in the background; do
T2.1 in the same session. Run T3.1 and T3.2 in a separate terminal session afterward.
