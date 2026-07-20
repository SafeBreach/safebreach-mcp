# Ticket Context: SAF-29870

## Status
Phase 6: PRD Created + revised after local safebreach-mcp investigation (prds/SAF-29870/prd.md)

## Mode
Improving (existing ticket, IMPROVE mode)

## Original Ticket (from JIRA)
- **Key / Type**: SAF-29870 / Story
- **Summary**: MCP: Actions for use by the AI Agent - Tags
- **Project**: SAF (SafeBreach SCRUM)
- **Status**: To Do
- **Priority**: Medium
- **Assignee**: Dan Almog · **Reporter**: Tal Rotem
- **Labels**: CTEM-dev
- **Parent epic**: SAF-29873 — "MCP and BG Actions and Guardrails"
- **Links**:
  - `is blocked by` SAF-29859 — "MCP: Support a set of basic simple actions … (part 1)" (Done)
  - `split to` SAF-31410 — "MCP: Enable for additional RBAC roles apart for Admin" (Done) — **this is the "linked story" that defines the allowed roles**
  - `split to` SAF-31511 — "MCP: Support Propagate actions for use by the AI Agent" (To Do)
  - `split to` SAF-31910 — "MCP: Actions for AI Agent - custom scenario creation" (To Do)
  - `relates to` SAF-29871 — "MCP: Limit the rate of repeated actions" (Done)
  - `relates to` SAF-29953 — "MCP: Allow the client to indicate if actions are allowed …" (Cancelled)

### Original Description (verbatim summary)
> The MCP server should support a second set of actions for use by the AI Agent, limited to the predefined roles only. This step includes tags lookup, assignment, creation and deletion.
>
> **Functional Requirements**
> 1. Add or Remove a custom Tag to/from existing single playbook attack.
> 2. Retrieve playbook attacks or simulation results based on given tags.
>
> **Non-Functional**: Prevent at this point bulk actions.
>
> **DoD**: The above actions available via MCP for use by the allowed roles defined in the linked ticket.

## Task Scope
Add a second set of MCP tools for the AI Agent, gated to the predefined roles, covering TAGS:
1. Add/remove a custom tag to/from a **single** existing playbook attack.
2. Retrieve playbook attacks OR simulation results filtered by given tags.
Non-functional: no bulk actions. Determine the concrete MCP tools, their role-gating, and the backend APIs they call.

## Repositories Under Investigation
- **Primary (tool implementation)**: /Users/dan/dev/repos/safebreach-mcp — now cloned locally, on `main` @ `1.7.0` (matches the mcp-proxy pin). This is where the MCP *tools* actually live and where Phases B/C/D are implemented. See "### safebreach-mcp (tool implementation repo)" below.
- **Integration**: /Users/dan/dev/repos/mcp-proxy (SIMP — the MCP proxy; this worktree/branch) — Phase E (pin bump + gate tests).
- **Backend (read-only, tag APIs)**: /Users/dan/dev/repos/configuration, /Users/dan/dev/repos/content-manager, /Users/dan/dev/repos/data, /Users/dan/dev/repos/orchestrator

## Investigation Findings

### mcp-proxy / SIMP (primary repo)

**Architecture — SIMP does NOT define individual MCP tools.** It is a FastAPI proxy/manager
that boots and gates a set of packaged SafeBreach MCP servers. The tools themselves (and any new
"tag" tools) live in the external `safebreach-mcp` package.
- `requirements.txt:6` — `git+https://github.com/SafeBreach/safebreach-mcp.git@1.7.0` (the source of all MCP tools).
- `src/simp/mcp_manager.py:119-163` — the server catalog SIMP manages: `configuration` (8000),
  `utilities` (8001), `data` (8002), `playbook` (8003), `studio` (8004), `moves` (8050, FF-gated
  `feature.mcpThreatDeveloper`). Tag tools would belong to the **playbook** server (attack tagging)
  and **data** server (simulation-results-by-tag).

**RBAC / role enforcement is external to SIMP (OPA at the ui-server).** SAF-29974 made SIMP the auth
gate and routes all MCP-tool backend calls through the ui-server so OPA enforces per-user permissions.
- `src/simp/gateway.py:24-26` — forwards user auth (`x-apitoken`, `x-token`, `cookie`); any one is
  sufficient because OPA has already validated.
- `src/simp/gateway.py` proxy routes reject unauthenticated requests (401); `/health` `/status` exempt.
- `src/simp/mcp_manager.py:170-214` (`_build_local_env_config`) — sets every backend service URL in
  `SAFEBREACH_LOCAL_ENV` to `MCP_API_GATEWAY_URL` (ui-server, default `http://127.0.0.1:1990`) so tool
  backend calls pass through OPA. Per-role gating for the new tag actions is therefore realized by the
  **OPA rules on the backend tag endpoints**, not by SIMP code.
- `prds/SAF-29974-mcp-enforce-rbac.md` documents this enforcement layer.

**Write-action gating (SAF-29865 / SAF-30318) auto-covers new write tools.** An "add/remove tag" tool
is a *write* tool and is automatically hidden unless the AI-actions gate is OPEN:
- `src/simp/mcp_manager.py:31-32` — gate = FF `feature.performActionsByAiAgent` AND consent setting
  `enableAiAgentActions == 'true'`; anything else (incl. fetch error) → CLOSED (fail-safe).
- `src/simp/mcp_manager.py:277-312` (`_discover_write_tools`) — classifies a tool as *write* when its
  annotation `readOnlyHint != True`, read from FastMCP `list_tools()` at server-start.
- `src/simp/mcp_manager.py:254-275` — when the gate is closed, all write tools across servers are added
  to `DISABLE_TOOL_LIST`, so `tools/list` hides them; enforcement is inside safebreach-mcp.
- **Implication**: the add/remove-tag tool must be annotated `readOnlyHint=False` (so it is gated as an
  action); the retrieval-by-tag tools must be `readOnlyHint=True` (always visible, read-only).
- No SIMP code change is required to gate the new write tool — the mechanism is generic. SIMP's only
  likely change is bumping the `safebreach-mcp` version pin once the new tools ship (`requirements.txt:6`).

**Existing action tools already shipped** via the blocked-by SAF-29859 (part 1 basic actions — run
scenario, pause/resume, delete test) and the role-widening SAF-31410 (both Done), so the plumbing
(gate + OPA roles) that this ticket relies on is already in place.

### safebreach-mcp (tool implementation repo) — VERIFIED LOCALLY (v1.7.0)

Repo `/Users/dan/dev/repos/safebreach-mcp`, `main` @ `1.7.0`. Six server packages
(`config`, `data`, `utilities`, `playbook`, `studio`) + shared `safebreach_mcp_core`.

**KEY CORRECTION — where write tools live.** The part-1 action tools the ticket references
(`run_scenario`, `manage_test` = pause/resume/cancel/delete, `quick_run`, `run_studio_attack`,
`set_studio_attack_status`, `save/update/create_studio_attack_draft`) ALL live in the **studio**
server (`safebreach_mcp_studio/`). The **playbook** and **data** servers currently contain
**only `readOnlyHint=True` tools** — there is no write tool in either yet. So SAF-29870's tag-write
tools will be the **FIRST write tools in the playbook server**, and the pattern to port comes from
the **studio** server, not from playbook/data.

**Tool-authoring pattern (plain FastMCP, no custom registry).**
- Base class `SafeBreachMCPBase` (`safebreach_mcp_core/safebreach_base.py:129`) creates
  `self.mcp = FastMCP(server_name)` (`:148`).
- Each server subclasses it and registers tools in `_register_tools()` with `@self.mcp.tool(...)`.
  Playbook: `safebreach_mcp_playbook/playbook_server.py:24` (class), `:36` (`_register_tools`),
  `:39-58` (`get_playbook_attacks`), `:161-169` (`get_playbook_attack_details`).
- **3-file convention per server**: `<name>_server.py` (FastMCP class + decorators + `main()`),
  `<name>_functions.py` (business logic `sb_*` funcs + `requests.*` calls + cache),
  `<name>_types.py` (pure transforms). Playbook `main()` runs port 8003 (`playbook_server.py:302`);
  data port 8001.
- **Naming**: `verb_noun` snake_case, no per-server prefix; internal fn is `sb_<toolname>`.
  Existing playbook tools: `get_playbook_attacks`, `get_playbook_attack_details`. Data: 17 read tools.

**Read vs write annotation (`readOnlyHint`) — via `ToolAnnotations` from `mcp.types`.**
- Read: `annotations=ToolAnnotations(readOnlyHint=True)` (all playbook/data tools).
- Write, non-destructive: `ToolAnnotations(readOnlyHint=False, destructiveHint=False)` —
  `save_studio_attack_draft` (`studio_server.py:186`), `update_studio_attack_draft` (`:367`),
  `create_new_studio_attack` (`:848`). **Tagging = non-destructive → use this pair.**
- Write, destructive: `readOnlyHint=False, destructiveHint=True` — `run_scenario` (`:1028`),
  `run_studio_attack` (`:536`), `set_studio_attack_status` (`:945`).

**Rate limiting is MANDATORY in-repo for every `readOnlyHint=False` tool** (CLAUDE.md hard rule +
gate-placement table) — `safebreach_mcp_core/rate_limiter.py`. Two-phase gate:
`rate_limiter.check_limit(caller_id, tool_name)` (`:72`, pre-mutation, raises ToolError if over) and
`rate_limiter.record_action(caller_id, tool_name)` (`:113`, post-success). `caller_id =
get_caller_identity()` (`:148`, auth-token SHA256[:16]). Config env vars default DISABLED
(`SAFEBREACH_MCP_RATE_LIMIT_ENABLED=false`, action limit 10, identical-action 5, window 30m).
Closest analog to copy: `sb_set_studio_attack_status` (read pre-check → `check_limit` → mutate →
`record_action`), `studio_functions.py:1693/1753/1865`. **`playbook_functions.py` does NOT yet import
`rate_limiter`/`get_caller_identity` — must add** `from safebreach_mcp_core.rate_limiter import
rate_limiter, get_caller_identity`.

**Backend HTTP call mechanism (no shared client — direct `requests.*` in `sb_*` funcs).**
- URL: `get_api_base_url(console, endpoint)` (`safebreach_mcp_core/environments_metadata.py:91`);
  `endpoint` ∈ `data|config|moves|queue|siem|playbook|orchestrator` (`:102`). Priority: (1)
  `SAFEBREACH_LOCAL_ENV` service URL (set by SIMP → RBAC gateway), with a `'default'`-env fallback
  that PREVENTS bypassing OPA with an unknown console (`:111-125`); (2) per-service `f'{EP}_URL'`
  env (standalone); (3) metadata default. Account id: `get_api_account_id(console)` (`:143`).
- Auth: `get_auth_headers_for_console(console)` (`secret_utils.py:91`) — takes auth ONLY from the
  live MCP request context (user's `x-apitoken`/`x-token`/`cookie`); embedded mode with no creds
  raises `AuthenticationRequired`. RBAC: `check_rbac_response(response)` (`:76-88`) replaces
  `raise_for_status()` and turns 403 → `PermissionError` with `RBAC_DENIED_HINT`.
- **So a new tag-write tool inherits RBAC gating for free** as long as it uses `get_api_base_url` +
  `get_auth_headers_for_console` + `check_rbac_response`.

**Existing tag/moves/executions handling (reuse targets).**
- Playbook fetch: `sb`/`_get_all_attacks_from_cache_or_api` (`playbook_functions.py:33`) →
  `GET {playbook_base}/api/kb/vLatest/moves?details=true` (`:69`) — **NOTE: reads via the `kb` API,
  not `/content/v3`.** Bounded per-user cache (`playbook_cache` maxsize=5 ttl=1800, `:27`); invalidate
  via `clear_playbook_cache()` (`:290`) after a tag write.
- **Move object exposes `tags`** — type layer maps `'tags':'tags'` and includes it in the full
  transform (`playbook_types.py` ~`:281`, `:356-358`); `_transform_tags` (`:66-117`) handles both the
  nested `[{id,name,values:[{id,value,displayName}]}]` shape and simple string lists. A custom tag
  lands in this same array → "get attacks by tags" can filter transformed `tags` in
  `filter_attacks_by_criteria` exactly like `mitre_technique_filter` does (`playbook_functions.py:169-183`).
- Data results query: `POST /api/data/v1/accounts/{account_id}/executionsHistoryResults` with a
  Lucene `"query"` string; **the tag field on results is `labels`** (e.g. `data_functions.py:807-830`).
  So "get sim results by tags" extends that `query` with `labels:<tag>` clauses (AND/OR combinable).

**GAP — tag WRITE endpoint not present in safebreach-mcp.** grep for
`add_tag|attack_tag|by_tag|userTag|customTag|moveTag` → no matches; playbook/data have no
`readOnlyHint=False` tools; no SAF-29870 PRD in the repo. The move-tag write endpoint lives in the
**configuration** repo and is pinned in the Phase A section below.

### Phase A verification — endpoint pinned (CODE-DERIVED; live OPA check still pending)

Investigated `configuration`, `content-manager`, and safebreach-mcp routing locally (2026-07-14).

**Move-tag write endpoint (configuration service, single-move):**
- **ADD**: `POST /api/content/v3/accounts/{accountId}/moves/{moveId}/tags`, body `{"values":["<tag>"]}`
  (array of strings) → handler `addMoveTags` (`configuration/src/server/newControllers/movesController.js:677`;
  swagger `src/server/REST/swagger.json:8210`, basePath `/api` at `:9`). Returns 201 with the updated tags.
- **REMOVE**: `DELETE /api/content/v3/accounts/{accountId}/moves/{moveId}/tags?values=<tag>` —
  `collectionFormat: pipes` so multiple = `?values=a|b` → handler `deleteMoveTags` (`movesController.js:753`;
  swagger `:8270`). Returns 200 with remaining tags. `moveId` = the attack id (same id space as the kb read).
- Routing is swagger-operationId dispatch (`x-swagger-router-controller: swaggerApi`, mounted in
  `configuration/src/server/Context.js:491`); config service listens on `CONFIGURATION_PORT` (`Context.js:139`).
- **AVOID bulk**: `/content/v3/accounts/{accountId}/moves/tags` `{moveIds:[...]}` (`movesController.js:793,803`;
  swagger `:8384`) — the no-bulk requirement.

**Base-URL token — RESOLVED = `'config'`** (supersedes the earlier "'moves' vs 'config' vs 'playbook'" open
question). `/content/v3` is on the configuration service; the MCP config tools already hit it with
`get_api_base_url(console,'config')` + `/api/config/v1/...` (`config_functions.py:158`). The `'moves'` token
is enum-only and **never routed** in MCP code — do NOT use it. `'playbook'` is the KB service (`:5100`,
`/api/kb/...`) — wrong for writes. Build: `f"{get_api_base_url(console,'config')}/api/content/v3/accounts/{account_id}/moves/{move_id}/tags"`.

**content-manager**: no single-move tag write (only GET `moves`/`tags`); the write lives in configuration only.

**OPA**: NO auth/OPA/permission middleware on these routes in the configuration repo (only
helmet/bodyParser/audit/swagger — `Context.js:458-510`). Enforcement is upstream at the gateway/ui-server
(not local), so the role-behavior check (privileged 2xx / non-privileged 403) is a **live-env** item.

**Remaining Phase-A items (need a live dev env + tokens):**
1. Smoke-test ADD then REMOVE against a live env (reversible) — confirm 201/200 + response shape.
2. OPA role behavior — privileged succeeds, non-privileged → 403. Needs a NON-privileged token (only admin
   tokens are configured locally).
3. Confirm the `labels:` Lucene query on `executionsHistoryResults` returns tagged sim-results (code-known;
   quick live sanity).

**Tests: pytest + unittest.mock.** Per-package `tests/` dirs + root `tests/` + root `conftest.py`.
Unit tests patch module-level `requests.*` / `get_api_base_url` / `get_api_account_id` inside the
`*_functions` module and return `MagicMock(.json.return_value=fixture)`. Write-tool model:
`safebreach_mcp_studio/tests/test_rate_limiting.py` asserts `check_limit → API call → record_action`
ordering (via `side_effect` recording) and sets `_user_auth_artifacts` ContextVar. E2E files per tool
(`test_e2e_manage_test.py`, etc.); `conftest.py` `set_e2e_auth_context` resolves tokens.

**Versioning/release (`.claude/skills/mcp-create-release`).** Version single-source =
`pyproject.toml:3`. CHANGELOG.md Keep-a-Changelog, newest on top, **date separator MUST be em-dash
`—` (U+2014)**. Only Minor/Major bumps (no patch). Release skill branches `release_{next}` off `main`,
commits only `pyproject.toml`+`CHANGELOG.md`, PRs to `main`; **git tag + GitHub Release are automated
by GH Actions on merge** (skill does NOT tag). mcp-proxy consumes via `requirements.txt`
`git+...@{version}`. For SAF-29870: Minor bump **1.7.0 → 1.8.0** + a CHANGELOG "Added" entry naming
the three tools `(SAF-29870)`.

**Proposed tool names (mirror convention; final names TBD with team):**
`add_playbook_attack_tag` + `remove_playbook_attack_tag` (or one `manage_playbook_attack_tag` with an
`action` param, matching the `manage_test` precedent), `get_playbook_attacks_by_tags`,
`get_simulation_results_by_tags`.

### Allowed roles — from SAF-31410 (the "linked story", Done)
The tag actions must be limited to these roles (OPA-enforced):
- **Administrator**, **Operator**, or **Content Developer**; OR
- a **custom role** carrying (AND) at least:
  - **Attack**: Running Center — *manage*; Scenarios — *manage*; Playbook — *view*
  - **Analyze**: Test Results — *manage*; Simulation Results — *manage*
  - **Mobilize**: Dashboards — *view*; Reports — *view*
- Bulk actions explicitly out of scope (matches this ticket's non-functional requirement).
- SAF-31410 is Done and validated by SAF-32777 (AI Agent HELM RBAC — Done), so the role gate already exists.

### Backend tag APIs — where tags actually live (three distinct concepts)

There are **three** different "tag" concepts; the ticket touches two of them:

| Concept | Meaning | Owning service |
|---|---|---|
| **move `tags`** | custom tag on a **playbook-attack / move definition** | **configuration** (`/content/v3`) |
| simulation **`labels`** | user custom tag on a single **simulation result** row | data (`/api/data/v1`) |
| execution **`Tags`/`moveTags`** | move-derived tags copied onto execution docs (read/queryable) | data (read-only) |

**(A) Add/remove custom tag on a single playbook attack (move) → `configuration` repo.**
Path `/content/v3/accounts/{accountId}/moves/{moveId}/tags` (single-move; `moveId` = the attack id):
- `POST addMoveTags` — body `{ "values": ["tag1", ...] }` — configuration `src/server/newControllers/movesController.js:677`; swagger `:8208`.
- `DELETE deleteMoveTags` — query `?values=` (pipe-delimited) — `movesController.js:753`; swagger `:8268`.
- `GET getMoveTags` — `movesController.js:669`; `PUT updateMoveTags` (rename) — `:735`.
- Custom tags stored as an overlay row (`OVERLAY_SOURCE='CUSTOM_TAGS'`, tag name `'Tags'`) on the move — `movesController.js:646-662`.
- **Bulk variants exist and MUST NOT be exposed** (non-functional "no bulk"):
  `/content/v3/accounts/{accountId}/moves/tags` — `addMoveTagsBulk`/`deleteMoveTagsBulk`/`updateMoveTagsBulk`
  (`movesController.js:793,803,797`) taking `{ moveIds: [...], values: [...] }`.
- Base tag entities/definitions live in **content-manager** (`src/tags/entities/tag.entity.ts`; `GET` tags at `src/tags/tags.controller.ts:19`).

**(B) Retrieve playbook attacks by tags → no clean standalone endpoint (dependency/gap).**
The orchestrator only applies a `tags` sub-filter inside a plan-submission body (`attacksFilter.tags`,
orchestrator `src/server/other/playbook_filter.js:223`, `PlanPreparation.js:412`), and content-manager's
moves list (`src/moves/moves.controller.ts:28`) has **no tag-filter query param**. So "get attacks by tags"
must be realized by fetching moves and filtering by `move.tags` client-side inside the playbook MCP tool,
unless a filtered moves endpoint is added. Move tag shape: `{ id, name, values:[{ id, value }] }`.

**(C) Retrieve simulation results by tags → `data` repo.**
- Query endpoint: `GET /api/data/v1/accounts/{accountId}/executionsHistoryResults` (operationId `list`,
  swagger `src/api/dashboardapi.json:1419`) and its `POST` variant (`:1537`). The `query` param is an
  Elasticsearch/Lucene string — filter with `tags:<value>` and/or `labels:<value>`.
  Field mappings: `tags`→`Tags.value.keyword` (`src/common/utils/executionUtils.js:205`,
  `src/common/utils/fieldMapper.js:288`). Move-derived tags (incl. custom ones propagated from the move
  definition via `src/common/configurationProxy/configurationProxy.js:364-373`) are queryable here — so
  tagging a move (A) makes its simulations findable by that tag (C).
- Simulation-result **labels** add/remove (single item) also exist if per-result tagging is wanted:
  `POST`/`DELETE /api/data/v1/accounts/{accountId}/rt/simulation/{simulationId}/labels/{labelValue}`
  (`src/dashboardApi/controller/executionsHistoryController.js:306,310`); list distinct labels
  `GET .../executionsHistory/labels` (`:314`). These are **single-item only** (no bulk today).

**Role-gating happens at OPA on these backend endpoints**, not in the MCP tools. Because SIMP routes all
tool backend calls through the ui-server gateway (SAF-29974), OPA enforces the SAF-31410 permission set on
`/content/v3/.../moves/{moveId}/tags` and `/api/data/v1/.../executionsHistoryResults`. This must be verified.

## Problem Analysis

**Where the work lands (multi-repo):**
1. **safebreach-mcp (external, primary implementation)** — add the new tools to the **playbook** server
   (attack tagging + attacks-by-tag) and **data** server (sim-results-by-tag). Annotate the add/remove tool
   `readOnlyHint=False` (so the AI-actions write-gate hides it when closed) and the retrieval tools
   `readOnlyHint=True`. Tools must call the single-item backend endpoints only.
2. **mcp-proxy / SIMP (this repo)** — most likely only a version bump of the `safebreach-mcp` pin
   (`requirements.txt:6`) once the tools ship; no gating code change needed (the write-tool gate is generic
   via `readOnlyHint`). Add regression tests asserting the new write tool(s) join `DISABLE_TOOL_LIST` when
   the gate is closed (`tests/test_ai_actions_gate.py`, `tests/test_mcp_manager.py`).
3. **configuration / data backends** — endpoints already exist (single-item). Likely no new API needed
   except possibly a tag-filtered "list moves" endpoint for goal (B) if client-side filtering is unacceptable.
4. **OPA (ui-server)** — confirm the tag endpoints require the SAF-31410 role/permission set.

**Risks & edge cases:**
- **"Custom Tag" ambiguity** — the ticket says tag "to a playbook attack", which maps to move-definition
  tags in `configuration`, NOT simulation-result `labels` in `data`. The retrieval half spans both attacks
  (moves) and simulation results. Need to confirm the intended semantics with product.
- **No native "attacks by tags" endpoint** (gap B) — either accept client-side filtering in the tool or
  request a backend filter param. Impacts effort/estimate.
- **Bulk must stay closed** — the bulk configuration endpoints and any array-of-ids body must not be
  wired into the tool surface; the add/remove tool takes exactly one attack id + one tag value.
- **Write-gate coverage** — the add/remove tool is only hidden while closed if its `readOnlyHint`
  annotation is correct; a mis-annotation would leak a write action past the gate. Cover with a test.
- **OPA parity** — if the tag backend endpoints are not covered by the SAF-31410 OPA policy, a
  non-privileged role could tag via MCP. Must verify.
- **Tag value normalization** — sim-result labels are upper-cased server-side; move tags are not — the
  retrieval tool should account for case when matching.

## Proposed Improvements
(see summary.md for the refined ticket content)

## Phase 5 — Design Decisions (planning-dev-task, locked with user)

**Scope decisions (user-confirmed):**
1. **Implementation scope = Cross-repo, full.** The PRD covers authoring the tools in
   `safebreach-mcp` (playbook + data servers) AND the mcp-proxy version bump + gate-coverage
   tests + OPA verification, as one effort.
2. **Attacks-by-tags = client-side filter in the tool.** No backend change: the playbook MCP
   tool fetches moves and filters by `move.tags`. (Backend tag-filter endpoint explicitly NOT
   pursued.)
3. **Write-action tag semantics = move-definition tags** (configuration `/content/v3/.../moves/{moveId}/tags`).
   Retrieval spans both move tags (attacks) and sim-result labels (data). Sim-result per-row
   label write is NOT in scope for the write action.

**Repo access UPDATE (2026-07-13):** `safebreach-mcp` is now cloned locally and fully investigated
(see "### safebreach-mcp (tool implementation repo)"). The earlier "specify at contract level / mirror
part-1 tools / confirm later" caveat is RESOLVED. Two corrections it forced:
- The write-tool pattern to copy is the **studio** server (part-1 tools live there), and the tag-write
  tools are the **first write tools in the playbook server**.
- **Rate limiting gates are MANDATORY** for the write tools (safebreach-mcp CLAUDE.md rule) — this was
  absent from the first PRD draft and is now a required deliverable + DoD + test.
Still-open (not invented): the exact tag-**write** backend endpoint + its `get_api_base_url` token +
OPA coverage — pinned in Phase A.

**Tool surface (4 tools in safebreach-mcp; names TBD):**
| Tool (proposed) | Server | Kind | Annotations | Backend / reuse |
|---|---|---|---|---|
| `add_playbook_attack_tag` | playbook | write + **rate-limited** | `readOnlyHint=False, destructiveHint=False` | move-tag write endpoint via `get_api_base_url(console,'moves'|'config')` (Phase A); then `clear_playbook_cache()` |
| `remove_playbook_attack_tag` | playbook | write + **rate-limited** | `readOnlyHint=False, destructiveHint=False` | same |
| `get_playbook_attacks_by_tags` | playbook | read | `readOnlyHint=True` | reuse `_get_all_attacks_from_cache_or_api` (`GET /api/kb/vLatest/moves?details=true`) → filter transformed `move.tags` in `filter_attacks_by_criteria` |
| `get_simulation_results_by_tags` | data | read | `readOnlyHint=True` | `POST /api/data/v1/.../executionsHistoryResults` with Lucene `query` incl. `labels:<tag>` |

(The two writes may instead be a single `manage_playbook_attack_tag(action=add|remove)` mirroring `manage_test`.)

**Implementation phases (backend-first):**
- **A. Backend + OPA verification (no code)** — pin the move-tag write endpoint + its gateway base-url
  token; confirm the 3 endpoints behave as documented and that the SAF-31410 set gates them (403 for
  non-privileged) on a live env.
- **B. safebreach-mcp — playbook write tools** — add/remove attack tag; `readOnlyHint=False,
  destructiveHint=False`; **add `check_limit`/`record_action` rate gates** (import rate_limiter into
  `playbook_functions.py`); single `moveId` + single tag value; `clear_playbook_cache()` after mutate;
  bulk not wired.
- **C. safebreach-mcp — retrieval tools** — `get_playbook_attacks_by_tags` (client-side filter on
  transformed `tags`), `get_simulation_results_by_tags` (`labels:` Lucene); both `readOnlyHint=True`;
  consistent tag-case handling.
- **D. safebreach-mcp release** — Minor bump `pyproject.toml` 1.7.0 → 1.8.0 + em-dash CHANGELOG "Added"
  entry; merge PR → GH Actions auto-tags `1.8.0`.
- **E. mcp-proxy (this branch)** — bump `requirements.txt:6` pin to `@1.8.0`; add regression tests in
  `tests/test_ai_actions_gate.py` + `tests/test_mcp_manager.py` asserting both write tools join
  `DISABLE_TOOL_LIST` when the gate is closed (keyed on the real shipped tool names).
- **F. E2E verification** — gate open/closed visibility, role gating, no-bulk rejection, tag-case parity,
  rate-limit gate ordering.

**No code changes** in configuration/data/content-manager (endpoints exist; client-side filter chosen).
OPA policy: verify coverage, extend only if the tag endpoints are not already covered by SAF-31410.
