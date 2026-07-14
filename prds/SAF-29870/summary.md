# Ticket Summary: SAF-29870

## Overview
**Mode**: Improving existing
**Project**: SAF (SafeBreach SCRUM) — Story, under epic SAF-29873 "MCP and BG Actions and Guardrails"
**Repositories**: safebreach-mcp (primary — tools live here, now cloned locally & verified @1.7.0), mcp-proxy/SIMP (integration), configuration + data + content-manager (tag backends), ui-server/OPA (role enforcement)

---

## Current State (improving)
**Summary**: "MCP: Actions for use by the AI Agent - Tags"
**Issues identified in the original ticket**:
- "the linked story" for allowed roles is unnamed → it is **SAF-31410** (Done), which enumerates the exact roles/permissions.
- Ambiguous "tags lookup, assignment, creation and deletion" wording vs. the two concrete functional requirements; no note that tag "creation/deletion" is implicit (a tag exists once applied, disappears when unused — there is no tag-registry CRUD to build).
- "custom Tag to a playbook attack" is not disambiguated from simulation-result labels — they are different backends.
- No mention of *which* repo/tool the work lands in, which backend APIs are called, or how the roles are actually enforced (OPA), or how "no bulk" is realized.
- No acceptance criteria.

---

## Investigation Summary

### safebreach-mcp (primary — tools live here; cloned locally & verified @1.7.0)
- **Tools are plain FastMCP** (`@self.mcp.tool(...)` in a `_register_tools()` of a `SafeBreachMCPBase` subclass); 3-file convention per server (`_server`/`_functions`/`_types`); naming `verb_noun`, internal fn `sb_<name>`.
- **Correction: part-1 action tools (`run_scenario`, `manage_test`, `run_studio_attack`, …) live in the STUDIO server, not playbook/data.** Playbook & data servers hold only `readOnlyHint=True` tools today → the tag-write tools will be the **first write tools in the playbook server**; copy the studio write-tool pattern.
- **`readOnlyHint` via `ToolAnnotations`** (`mcp.types`): read `True`; tagging = write non-destructive → `readOnlyHint=False, destructiveHint=False`.
- **Rate limiting is MANDATORY** for every `readOnlyHint=False` tool (repo CLAUDE.md rule + `safebreach_mcp_core/rate_limiter.py`): add `check_limit` (pre-mutate) + `record_action` (post-success) gates; `playbook_functions.py` must import `rate_limiter`/`get_caller_identity`.
- **Backend calls**: direct `requests.*` in `sb_*`; URL via `get_api_base_url(console, endpoint)` (tokens incl. unused `'moves'`), auth via `get_auth_headers_for_console`, RBAC via `check_rbac_response` (403→hint) — so a tag-write tool inherits OPA gating for free.
- **Reuse**: attacks read via `GET /api/kb/vLatest/moves?details=true`; **move object already exposes `tags`** (transformed by `_transform_tags`) → attacks-by-tag = client-side filter in `filter_attacks_by_criteria` (like the MITRE filter). Sim results via `POST /api/data/v1/.../executionsHistoryResults` Lucene `query`, tag field = `labels`. After a tag write, `clear_playbook_cache()`.
- **GAP**: no tag-write endpoint exists in safebreach-mcp; the move-tag write endpoint + its gateway base-url token + OPA coverage must be pinned in Phase A. No existing tag tooling; all four tools are net-new.
- **Release**: Minor bump `pyproject.toml` 1.7.0→1.8.0 + em-dash CHANGELOG "Added" entry; GH Actions auto-tags on merge.

### mcp-proxy / SIMP (integration)
- SIMP is a proxy/manager, **not** where tools are defined. It boots packaged servers — configuration/utilities/data/**playbook**/studio/moves (`src/simp/mcp_manager.py:119-163`). Tools come from the external `safebreach-mcp` package (`requirements.txt:6`, pinned `@1.7.0`).
- **Role enforcement is external (OPA at ui-server).** SIMP forwards user auth (`src/simp/gateway.py:24-26`) and routes every tool backend call through `MCP_API_GATEWAY_URL` (`_build_local_env_config`, `src/simp/mcp_manager.py:170-214`) so OPA enforces per-user RBAC (SAF-29974; `prds/SAF-29974-mcp-enforce-rbac.md`).
- **Write actions are auto-gated by annotation.** The AI-actions gate (`feature.performActionsByAiAgent` + `enableAiAgentActions` consent, `src/simp/mcp_manager.py:31-32`) hides every tool whose annotation has `readOnlyHint != True` when closed (`_discover_write_tools` `:277-312`, `_effective_deny_list` `:254-267`). So a new add/remove-tag tool is gated for free if annotated `readOnlyHint=False`.

### Allowed roles — SAF-31410 (the "linked story", Done, validated by SAF-32777)
Admin, Operator, or Content Developer; **or** a custom role holding (AND) at least: Attack{Running Center: manage, Scenarios: manage, Playbook: view}, Analyze{Test Results: manage, Simulation Results: manage}, Mobilize{Dashboards: view, Reports: view}. Bulk actions out of scope.

### Tag backends
- **Playbook-attack (move) tag add/remove — `configuration`** `/content/v3/accounts/{accountId}/moves/{moveId}/tags`: `POST addMoveTags` (`movesController.js:677`, body `{values:[...]}`), `DELETE deleteMoveTags` (`:753`, `?values=`). **Single-move.** Bulk variants at `/content/v3/.../moves/tags` (`:793,803`) — must NOT be exposed.
- **Attacks by tags** — no standalone endpoint; orchestrator applies `attacksFilter.tags` only at plan-submission (`playbook_filter.js:223`); content-manager moves list has no tag filter. Gap → filter client-side in the tool or add a backend filter.
- **Simulation results by tags — `data`** `GET|POST /api/data/v1/accounts/{accountId}/executionsHistoryResults` with Lucene `query` (`tags:` / `labels:`) (`src/api/dashboardapi.json:1419,1537`; `executionUtils.js:205`). Single-item sim-result label add/remove also exists (`executionsHistoryController.js:306,310`).

---

## Problem Analysis

### Problem Description
Extend the AI Agent's MCP tool surface with a second, tag-focused action set, gated to the SAF-31410 roles: (1) add/remove a custom tag on a single playbook attack; (2) retrieve playbook attacks or simulation results by tags. Implementation is primarily in safebreach-mcp (playbook + data servers); SIMP most likely only bumps the package pin and adds gate-coverage tests; role enforcement is via OPA on the backend endpoints. No bulk.

### Impact Assessment
- **safebreach-mcp** (primary): playbook server — add/remove attack tag [write, **first write tools in this server**, rate-limited] + get-attacks-by-tags [read, reuse existing moves fetch + tag filter]; data server — get-sim-results-by-tags [read, `labels:` Lucene]. `playbook_functions.py` gains a `rate_limiter` import.
- **mcp-proxy**: `requirements.txt:6` pin bump to the new release; regression tests in `tests/test_ai_actions_gate.py` / `tests/test_mcp_manager.py`.
- **configuration/data**: backend endpoints already exist (single-item); no change expected (client-side filter chosen for attacks-by-tag).
- **ui-server/OPA**: verify the tag endpoints require the SAF-31410 permission set.

### Risks & Edge Cases
- Move-definition tag vs simulation-result label ambiguity — confirm semantics with product.
- No native attacks-by-tag endpoint (gap) — client-side filter vs new backend param affects effort.
- Bulk must stay closed — tool takes exactly one attack id + one tag value; do not wire bulk endpoints.
- `readOnlyHint` mis-annotation would leak the write action past the gate — cover with a test.
- OPA policy must actually cover the tag endpoints, else non-privileged roles could tag via MCP.
- Tag value case normalization (sim labels are upper-cased server-side; move tags are not).

---

## Proposed Ticket Content

### Summary (Title)
MCP: AI Agent tag actions — tag a single playbook attack and query attacks/simulation-results by tag (predefined roles, no bulk)

### Description

**Background**
Second action set for the AI Agent MCP surface (epic SAF-29873), following the part-1 basic actions (SAF-29859, Done). It adds tag capabilities, restricted to the predefined roles defined in **SAF-31410** (Done): Administrator, Operator, Content Developer, or a custom role holding at least — Attack{Running Center: manage, Scenarios: manage, Playbook: view}, Analyze{Test Results: manage, Simulation Results: manage}, Mobilize{Dashboards: view, Reports: view}.

**Technical Context**
* MCP tools live in the `safebreach-mcp` package (mcp-proxy `requirements.txt:6`, pinned `@1.7.0`); mcp-proxy/SIMP proxies and gates them. Tools are plain FastMCP; tag tools go in the **playbook** server (attack tagging + attacks-by-tag) and **data** server (sim-results-by-tag). These are the **first write tools in the playbook server** — copy the studio server's write-tool pattern.
* Role enforcement is via OPA at the ui-server — SIMP routes all tool backend calls through `MCP_API_GATEWAY_URL` (SAF-29974). A tool inherits OPA gating for free by using `get_api_base_url` + `get_auth_headers_for_console` + `check_rbac_response`.
* The add/remove-tag tool is a write tool: annotate `ToolAnnotations(readOnlyHint=False, destructiveHint=False)` so the AI-actions gate (`feature.performActionsByAiAgent` + `enableAiAgentActions`) auto-hides it when closed; retrieval tools annotate `readOnlyHint=True`.
* **Rate limiting**: safebreach-mcp requires every `readOnlyHint=False` tool to add `rate_limiter.check_limit` (pre-mutate) + `record_action` (post-success) gates.
* Backend endpoints (single-item only):
  * Attack tag add/remove → move-tag write endpoint reached via the MCP gateway (configuration exposes `POST`/`DELETE /content/v3/accounts/{accountId}/moves/{moveId}/tags`; the exact `get_api_base_url` token is pinned in Phase A). After a successful write, `clear_playbook_cache()`.
  * Attacks by tag → **no native filter endpoint**; reuse the existing moves fetch (`GET /api/kb/vLatest/moves?details=true`) and filter the transformed `move.tags` client-side (the move object already exposes `tags`).
  * Simulation-results by tag → data `POST /api/data/v1/accounts/{accountId}/executionsHistoryResults` with a Lucene `query` including `labels:<tag>`.

**Problem Description**
* AI Agent currently cannot tag playbook attacks or find attacks/results by tag through MCP.
* "Creation/deletion" of tags is implicit — a custom tag exists once applied and disappears when unused; there is no separate tag-registry CRUD to build.
* Bulk tagging endpoints exist in configuration but are explicitly out of scope for this step.

**Affected Areas**
* safebreach-mcp (primary): playbook server `playbook_server.py`/`playbook_functions.py`/`playbook_types.py` (attack tag add/remove + attacks-by-tag; first write tools here), data server (sim-results-by-tag), `pyproject.toml`+`CHANGELOG.md` (release).
* mcp-proxy: `requirements.txt` pin bump; `tests/test_ai_actions_gate.py`, `tests/test_mcp_manager.py`.
* configuration `/content/v3` + data `/api/data/v1` (backends, exist today).
* ui-server/OPA: role coverage for the tag endpoints.

### Acceptance Criteria
- [ ] MCP tool adds a custom tag to a single playbook attack (one attack id + one tag value), via the move-tag write endpoint through the MCP gateway.
- [ ] MCP tool removes a custom tag from a single playbook attack.
- [ ] MCP tool retrieves playbook attacks filtered by one or more given tags (client-side filter on `move.tags`).
- [ ] MCP tool retrieves simulation results filtered by one or more given tags, backed by data `executionsHistoryResults` (`labels:` Lucene).
- [ ] The two write tools are annotated `ToolAnnotations(readOnlyHint=False, destructiveHint=False)` and hidden from `tools/list` when the AI-actions gate is closed; retrieval tools are `readOnlyHint=True` and always visible.
- [ ] The two write tools add `rate_limiter.check_limit` (pre-mutate) + `record_action` (post-success) gates per the safebreach-mcp rate-limiting rule; ordering covered by a test.
- [ ] Playbook cache is invalidated (`clear_playbook_cache()`) after a successful tag write.
- [ ] All four actions are permitted only for the SAF-31410 roles and rejected (OPA 403) for other roles — verified on a live env.
- [ ] No bulk: tools accept a single attack id and reject/omit array-of-ids input; the configuration bulk endpoints are not wired.
- [ ] safebreach-mcp is Minor-bumped (1.7.0 → 1.8.0) with an em-dash CHANGELOG "Added" entry; mcp-proxy `requirements.txt` is bumped to `@1.8.0`.
- [ ] mcp-proxy regression tests assert the new write tools join `DISABLE_TOOL_LIST` when the gate is closed.
- [ ] Tag-value case handling is consistent between write and query paths.

### Suggested Labels/Components
- Labels: `CTEM-dev` (existing), consider `mcp`, `ai-agent`
- Components: none set on the project; primary work in safebreach-mcp + mcp-proxy

---

## Assumptions Made (in place of interactive prompts)
1. **"The linked story" = SAF-31410** (the `split to` link titled "Enable for additional RBAC roles apart for Admin", Done) — it is the only linked ticket that enumerates roles.
2. Kept **IMPROVE** mode; did not create sub-tasks or a new ticket.
3. Interpreted "custom Tag to a playbook attack" as a **move-definition** tag (configuration `/content/v3`), and the retrieval half as spanning both attacks (moves) and simulation results (data) — flagged for product confirmation.
4. Treated tag **creation/deletion** as implicit (label/tag springs into existence on first apply; no registry CRUD to build), per both backend investigations.
5. Assumed the primary implementation is in **safebreach-mcp**, with mcp-proxy limited to a version bump + gate-coverage tests — since mcp-proxy defines no tools itself.
6. Assumed the backend single-item tag endpoints already satisfy the requirement; the only possible new backend work is a tag-filtered "list attacks" endpoint (gap B).
7. **HARD STOP honored**: no JIRA write, no commit, no push, no branch change. PRD files written only under the worktree.
