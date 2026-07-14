# MCP: AI Agent Tag Actions — SAF-29870

## Section 1: Overview

- **Title**: MCP: AI Agent Tag Actions — SAF-29870
- **Task Type**: Feature (cross-repo: new MCP tools in safebreach-mcp + proxy integration in mcp-proxy)
- **Purpose**: Extend the AI Agent's MCP tool surface with a second, tag-focused action set so the
  agent can (a) add/remove a custom tag on a single playbook attack and (b) retrieve playbook
  attacks or simulation results filtered by tags — all restricted to the predefined privileged roles.
- **Target Consumer**: The SafeBreach AI Agent (and, through it, customer users operating within the
  allowed roles). Internal: MCP tool authors.
- **Target Roles (RBAC)**: The SAF-31410 role set — **Administrator**, **Operator**, or
  **Content Developer**; **or** a custom role holding (AND) at least: Attack{Running Center: manage,
  Scenarios: manage, Playbook: view}, Analyze{Test Results: manage, Simulation Results: manage},
  Mobilize{Dashboards: view, Reports: view}.
- **Key Benefits**:
  1. AI Agent can organize and retrieve content by tag without leaving the MCP surface.
  2. Reuses the existing OPA role gate (SAF-31410), the AI-actions write gate, and the in-repo
     rate limiter — minimal new enforcement plumbing.
  3. Single-item, no-bulk scope keeps the blast radius of agent-driven tagging small and auditable.
- **Business Alignment**: Part of epic SAF-29873 ("MCP and BG Actions and Guardrails"), the second
  action set after the part-1 basic actions (SAF-29859, Done).
- **Originating Request**: JIRA **SAF-29870** (Story, In Progress), reporter Tal Rotem, assignee Dan Almog.

---

## Section 1.5: Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-07-14 14:30 |
| **Owner** | Dan Almog (AI-assisted) |
| **Current Phase** | Phase C complete (retrieval tools shipped); next: Phase B (write tools) / Phase D (release) |

> Revised after cloning and investigating `safebreach-mcp` locally (v1.7.0). Grounding for every
> file:line reference below is recorded in `context.md` → "### safebreach-mcp (tool implementation repo)".

---

## Section 2: Solution Description

**Chosen Solution — implement the tools where they live (safebreach-mcp), reuse the existing gates.**
Author four new MCP tools in the `safebreach-mcp` package: two write tools + one read tool in the
**playbook** server, and one read tool in the **data** server. Integrate through mcp-proxy/SIMP by a
version-pin bump + gate-coverage tests. The tools reuse safebreach-mcp's existing plumbing:
`get_api_base_url` + `get_auth_headers_for_console` + `check_rbac_response` (so OPA enforces the
SAF-31410 roles at the ui-server gateway, SAF-29974), `ToolAnnotations(readOnlyHint=False)` on the
write tools (so the AI-actions gate hides them when closed, SAF-29865/SAF-30318), and the in-repo
`rate_limiter` gates (mandatory for write tools). "Attacks by tags" reuses the existing moves fetch
and filters `move.tags` **client-side** (no backend change).

**Key correction from the local investigation:** the part-1 action tools (`run_scenario`,
`manage_test`, …) live in the **studio** server; the playbook and data servers hold only read-only
tools today. So the tag-write tools are the **first write tools in the playbook server**, and the
pattern to port is the studio write-tool pattern (annotations + rate gates + auth + cache invalidation).

**Alternatives Considered:**

1. **Add a backend tag-filter param to the moves endpoint** (for attacks-by-tag).
   - *Pros*: server-side filtering; avoids fetching the full move list.
   - *Cons*: cross-repo change (content-manager/configuration + orchestrator); larger review surface;
     unnecessary since the move object already exposes `tags` and `filter_attacks_by_criteria` already
     does MITRE-tag-style filtering.
   - *Rejected*: client-side filtering is sufficient at current scale (decision locked with owner).

2. **Include per-simulation-result label write in the write action.**
   - *Pros*: symmetric with retrieval (which spans sim-result labels).
   - *Cons*: expands the write surface beyond "custom Tag to a playbook attack"; two backends to gate.
   - *Rejected*: write action is scoped to move-definition tags only (decision locked with owner).

3. **Implement gating logic inside SIMP or inside the new tools.**
   - *Pros*: centralized.
   - *Cons*: redundant — RBAC is enforced by OPA at the gateway, the write-hiding gate is generic via
     `readOnlyHint`, and rate limiting is a shared core helper. Would duplicate SAF-29974/SAF-29871.
   - *Rejected*: no bespoke gating code needed; reuse the three existing mechanisms.

**Decision Rationale**: Maximize reuse of the mechanisms already shipped and validated (SAF-31410
roles, SAF-29865 write gate, SAF-29871 rate limiter), keep the tool surface single-item to satisfy
the no-bulk requirement, and avoid backend changes the current scale does not justify.

---

## Section 3: Core Feature Components

**Component A — Playbook attack tag write tools (safebreach-mcp, playbook server) [new — first write tools here]**
- **Purpose**: Let the AI Agent add, remove, or rename a custom tag on a single playbook attack (move).
- **Proposed tools** (names TBD with team; may be a single `manage_playbook_attack_tag(action=…)`
  mirroring `manage_test`): `add_playbook_attack_tag(attack_id, tag_value, console)`,
  `remove_playbook_attack_tag(attack_id, tag_value, console)`, and
  `rename_playbook_attack_tag(attack_id, old_value, new_value, console)` (rename/update — added to scope
  2026-07-14; backend `updateMoveTags` `PUT .../moves/{moveId}/tags` body `{oldValue,newValue}`,
  `movesController.js:725`, swagger `:8323`).
- **Key Features / requirements**:
  - Annotated `ToolAnnotations(readOnlyHint=False, destructiveHint=False)` (tagging is non-destructive)
    → auto-hidden from `tools/list` when the AI-actions gate is closed.
  - **Rate-limited** (mandatory for `readOnlyHint=False`): `rate_limiter.check_limit(caller_id, name)`
    after param validation and before the mutating call; `rate_limiter.record_action(caller_id, name)`
    after success. `playbook_functions.py` must add `from safebreach_mcp_core.rate_limiter import
    rate_limiter, get_caller_identity`.
  - Single `attack_id` + single `tag_value`; array-of-ids rejected; bulk endpoints not wired.
  - Backend call via `get_api_base_url` + `get_auth_headers_for_console` + `check_rbac_response`.
  - `clear_playbook_cache()` after a successful write (playbook attacks are cached per-user).

**Component B — Retrieval-by-tag tools (safebreach-mcp) [new]**
- **Purpose**: Let the AI Agent find attacks or simulation results by tag.
- **Proposed tools**: `get_playbook_attacks_by_tags(tags, console)` (playbook server),
  `get_simulation_results_by_tags(tags, console)` (data server).
- **Key Features**:
  - `get_playbook_attacks_by_tags`: reuse `_get_all_attacks_from_cache_or_api`
    (`GET /api/kb/vLatest/moves?details=true`) and filter the transformed `move.tags` in
    `filter_attacks_by_criteria` (same mechanism as `mitre_technique_filter`); `readOnlyHint=True`.
  - `get_simulation_results_by_tags`: `POST /api/data/v1/.../executionsHistoryResults` with a Lucene
    `query` including `labels:<tag>` clauses (AND/OR combinable); `readOnlyHint=True`.
  - Tag-value case handling consistent with the write path (sim-result `labels` are upper-cased
    server-side; move tags are not).

**Component C — mcp-proxy/SIMP integration [modification]**
- **Purpose**: Ship the new tools through the proxy and prove the gate covers them.
- **Key Features**:
  - Bump the `safebreach-mcp` pin in `requirements.txt` to the release containing the new tools (`@1.8.0`).
  - Regression tests asserting the two write tools join `DISABLE_TOOL_LIST` when the gate is closed and
    are visible when open; retrieval tools always visible.

**Component D — safebreach-mcp release [release]**
- Minor bump `pyproject.toml` 1.7.0 → 1.8.0 + em-dash CHANGELOG "Added" entry; merge → GH Actions
  auto-tags `1.8.0` and cuts the GitHub Release.

**Component E — OPA role coverage verification (ui-server) [verification]**
- Confirm (and extend only if missing) OPA coverage on the move-tag write endpoint and
  `/api/data/v1/.../executionsHistoryResults` for the SAF-31410 permission set.

---

## Section 4: API Endpoints and Integration

**How tools talk to backends (safebreach-mcp convention):** each `sb_*` function calls `requests.*`
directly, building the URL with `get_api_base_url(console, endpoint)`
(`safebreach_mcp_core/environments_metadata.py:91`; `endpoint` ∈
`data|config|moves|queue|siem|playbook|orchestrator`) and headers with
`get_auth_headers_for_console(console)` (`secret_utils.py:91`), then calls
`check_rbac_response(response)` (`:76`, 403 → actionable hint). In embedded mode SIMP injects the
gateway URL via `SAFEBREACH_LOCAL_ENV`, so all calls route through OPA.

**Existing APIs to Consume:**

1. **Read playbook attacks (moves)** — `GET {playbook_base}/api/kb/vLatest/moves?details=true`
   - safebreach-mcp `playbook_functions.py:69` (`_get_all_attacks_from_cache_or_api`).
   - Returned move object **exposes a `tags` array** (transformed by `_transform_tags`,
     `playbook_types.py:66-117`) → reused for `get_playbook_attacks_by_tags` client-side filtering.
   - Per-user bounded cache (`playbook_cache`, `:27`); `clear_playbook_cache()` (`:290`).

2. **Query simulation results by tag** — `POST /api/data/v1/accounts/{accountId}/executionsHistoryResults`
   - safebreach-mcp `data_functions.py:807-830`; payload includes a Lucene `"query"` string; tag field
     on results is `labels` → filter `labels:<tag>`.

3. **Add / remove a custom tag on a single move (WRITE — endpoint pinned in Phase A)**
   - ADD: `POST /api/content/v3/accounts/{accountId}/moves/{moveId}/tags`, body `{"values":["<tag>"]}` →
     `addMoveTags` (configuration `src/server/newControllers/movesController.js:677`; swagger `:8210`), 201.
   - REMOVE: `DELETE /api/content/v3/accounts/{accountId}/moves/{moveId}/tags?values=<tag>`
     (`collectionFormat: pipes` → `?values=a|b`) → `deleteMoveTags` (`:753`; swagger `:8270`), 200.
   - **Base-URL token = `config`** (resolved; the configuration service hosts `/content/v3`; `'moves'`
     token is unused/unrouted, `'playbook'` is the KB service). Build like the config tools:
     `f"{get_api_base_url(console,'config')}/api/content/v3/accounts/{account_id}/moves/{move_id}/tags"`.
   - **Still live-pending**: OPA role behavior (privileged 2xx / non-privileged 403) — no auth middleware
     on these routes in the configuration repo; enforcement is upstream at the gateway/ui-server.

**Bulk endpoints that MUST NOT be wired** (non-functional "no bulk"):
`/content/v3/accounts/{accountId}/moves/tags` — `addMoveTagsBulk` / `deleteMoveTagsBulk` /
`updateMoveTagsBulk` (configuration `movesController.js:793,803,797`, body `{moveIds:[...], values:[...]}`).

**No new APIs are created.**

---

## Section 6: Non-Functional Requirements

**Security & Compliance**
- **RBAC**: all four actions permitted only for the SAF-31410 role set; rejected (OPA 403) for others.
  Inherited for free by using `get_api_base_url` + `get_auth_headers_for_console` +
  `check_rbac_response` (SAF-29974). No authorization logic in the tool or SIMP.
- **AI-actions consent gate**: write tools hidden unless FF `feature.performActionsByAiAgent` AND
  setting `enableAiAgentActions == 'true'` (fail-safe: any error → CLOSED).
- **Rate limiting (mandatory)**: safebreach-mcp requires every `readOnlyHint=False` tool to add
  `rate_limiter.check_limit` / `record_action` gates (`safebreach_mcp_core/rate_limiter.py`; CLAUDE.md
  gate-placement table). Env-configurable, disabled by default.

**Technical Constraints**
- **No bulk**: tools accept a single attack id + single tag value; array-of-ids rejected; bulk
  configuration endpoints not wired.
- **Backward compatibility**: additive only; no changes to existing tools or backend endpoints.
- **Deployment**: gated behind the existing AI-actions FF + consent setting; no new feature flag.
- **Cross-repo sequencing**: mcp-proxy pin bump (@1.8.0) depends on the safebreach-mcp release.
- **Cache coherence**: invalidate the playbook cache after a tag write so reads reflect the change.

**Monitoring & Observability**
- New write actions should be traceable through the same path as the studio write tools. Confirm the
  tag writes are captured wherever agent write actions are logged.

---

## Section 7: Definition of Done

**Core Functionality**
- [ ] Add a custom tag to a single playbook attack via MCP (one attack id + one tag value).
- [ ] Remove a custom tag from a single playbook attack via MCP.
- [x] Retrieve playbook attacks filtered by one or more given tags (client-side filter on `move.tags`). *(Phase C)*
- [x] Retrieve simulation results filtered by one or more given tags (`labels:` Lucene on `executionsHistoryResults`). *(Phase C)*

**Quality Gates**
- [ ] Write tools annotated `ToolAnnotations(readOnlyHint=False, destructiveHint=False)`; hidden when
      the gate is closed, visible when open. Retrieval tools `readOnlyHint=True`, always visible.
- [ ] Write tools add `rate_limiter.check_limit` (pre-mutate) + `record_action` (post-success) gates;
      ordering covered by a test (per the studio `test_rate_limiting.py` model).
- [ ] Playbook cache invalidated (`clear_playbook_cache()`) after a successful tag write.
- [ ] All four actions permitted only for the SAF-31410 roles, rejected (403) for others — live env.
- [ ] No-bulk enforced: single attack id only; array-of-ids rejected; bulk endpoints not wired.
- [ ] Tag-value case handling consistent between write and query paths.
- [x] safebreach-mcp unit tests pass (`uv run pytest safebreach_mcp_playbook/tests safebreach_mcp_data/tests -m "not e2e"`) — 698 passed incl. 42 new. *(Phase C; re-verify after Phase B)*
- [ ] mcp-proxy regression tests assert the write tools join `DISABLE_TOOL_LIST` when the gate is closed.

**Deployment Readiness**
- [ ] safebreach-mcp Minor-bumped 1.7.0 → 1.8.0 with an em-dash CHANGELOG "Added" entry; release PR merged (GH Actions tags `1.8.0`).
- [ ] mcp-proxy `requirements.txt` bumped to `@1.8.0`; existing tests green.
- [ ] OPA coverage on the tag endpoints confirmed (or extended if missing).

---

## Section 8: Testing Strategy

**Unit Testing (safebreach-mcp — pytest + unittest.mock)**
- Patch module-level `requests.*`, `get_api_base_url`, `get_api_account_id` inside `playbook_functions`
  / `data_functions`; return `MagicMock(.json.return_value=fixture)`; set the `_user_auth_artifacts`
  ContextVar (auth) as in `conftest.py`.
- **Write tools**: assert URL/payload for add/remove (single value), array-of-ids rejection, and the
  **`check_limit → mutate → record_action` ordering** (model: `safebreach_mcp_studio/tests/test_rate_limiting.py`
  using `side_effect` recording), plus `clear_playbook_cache()` called after success and NOT on failure.
- **Read tools**: `get_playbook_attacks_by_tags` filter logic (match/no-match, multi-tag, case) against
  a fixture moves list; `get_simulation_results_by_tags` Lucene `query` construction (`labels:` clauses).
- Test files land in `safebreach_mcp_playbook/tests/` and `safebreach_mcp_data/tests/` following the
  `test_<name>_functions.py` / `test_<name>_server.py` split.

**Unit Testing (mcp-proxy — pytest)**
- Extend `tests/test_ai_actions_gate.py` and `tests/test_mcp_manager.py`: the two new write tools are
  added to `DISABLE_TOOL_LIST` when the gate is closed and absent when open; retrieval tools never
  gated. Keyed on the actual shipped tool names.

**Integration / E2E (live env)**
- Gate open vs closed → write tools appear/disappear in `tools/list`.
- Role gating: privileged role succeeds; non-privileged → OPA 403 on each action.
- Tag a move → query attacks-by-tag and sim-results-by-tag returns it (propagation path).
- No-bulk: array input → rejected. Optional e2e files mirror `test_e2e_manage_test.py`.

**Coverage Gaps**: the tag-write backend endpoint is pinned in Phase A; write-tool tests depend on
that endpoint shape.

---

## Section 9: Implementation Phases

**The Iron Law**: each step = one semantic, independently testable/committable change. Use TodoWrite
before starting. Each code change → verify (test/lint) → commit.

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase A: Backend + OPA verification (no code) | ✅ Complete | 2026-07-14 | - | endpoint pinned from code (token=`config`); OPA role check folded into Phase F (E2E) |
| Phase B: safebreach-mcp — playbook write tools (rate-limited) | ⏳ Pending | - | - | first write tools in playbook |
| Phase C: safebreach-mcp — retrieval tools | ✅ Complete | 2026-07-14 | - | `get_playbook_attacks_by_tags` + `get_simulation_results_by_tags`; 42 tests, 698 suite green |
| Phase D: safebreach-mcp release (1.8.0) | ⏳ Pending | - | - | Minor bump + changelog |
| Phase E: mcp-proxy pin bump + gate regression tests | ⏳ Pending | - | - | this branch; pin `@1.8.0` |
| Phase F: E2E verification on live env | ⏳ Pending | - | - | roles/gate/no-bulk/rate |

### Phase A — Backend + OPA verification (no code)
- **Semantic Change**: Pin the move-tag write endpoint and confirm the three backends + OPA behavior.
- **Deliverables**: a verification note in context.md recording — the exact move-tag write endpoint
  reachable via the MCP gateway and the correct `get_api_base_url` token; request/response for
  add/remove; the Lucene `labels:` query that returns sim-results; the moves-list shape used for
  client-side filtering; and OPA behavior (privileged 2xx / non-privileged 403) per endpoint.
- **Implementation Details**: with a live env + a privileged and a non-privileged token, exercise the
  candidate configuration `/content/v3/.../moves/{moveId}/tags` write through the gateway, the data
  `executionsHistoryResults` query, and the `kb` moves read. Record actual field names + case behavior.
- **What can go wrong**: endpoint not reachable via the gateway / not covered by OPA (non-privileged
  succeeds) → raise as a dependency before B; base-url token ambiguity → resolve here.
- **Git Commit**: `docs(SAF-29870): record backend + OPA verification for tag endpoints`

### Phase B — safebreach-mcp playbook write tools (rate-limited)
- **Semantic Change**: Add the add/remove/rename-attack-tag write tools to the playbook server (its first).
- **Functions**: `sb_add_playbook_attack_tag(console, attack_id, tag_value)`,
  `sb_remove_playbook_attack_tag(...)`, and `sb_rename_playbook_attack_tag(console, attack_id, old_value,
  new_value)` (rename via `PUT .../moves/{moveId}/tags` `{oldValue,newValue}`) in `playbook_functions.py`;
  thin `@self.mcp.tool(...)` wrappers in `playbook_server.py` with
  `ToolAnnotations(readOnlyHint=False, destructiveHint=False)`. All three rate-limited.
- **I/O**: input single `attack_id` (moveId) + single `tag_value`; output success/failure dict with a
  `hint_to_agent`. Reject list/array id input.
- **Steps**: validate single-item input → `caller_id = get_caller_identity()` →
  `rate_limiter.check_limit(caller_id, tool_name)` → build the Phase-A write request via
  `get_api_base_url` + `get_auth_headers_for_console` → send → `check_rbac_response` →
  `clear_playbook_cache()` → `rate_limiter.record_action(caller_id, tool_name)` → return.
- **What can go wrong**: mis-annotated `readOnlyHint` leaks the write past the gate → set `False`,
  cover in Phase E; `record_action` must NOT run on failure; forgetting the rate_limiter import.
- **Changes**:
  | File (safebreach-mcp) | Description |
  |---|---|
  | `safebreach_mcp_playbook/playbook_functions.py` | add rate_limiter import + `sb_add/remove_playbook_attack_tag` + cache invalidation |
  | `safebreach_mcp_playbook/playbook_server.py` | register the two write tools with write annotations |
  | `safebreach_mcp_playbook/tests/` | unit tests: payload, array rejection, gate ordering, cache-clear |
- **Git Commit**: `feat(playbook): add/remove custom tag on a single playbook attack (rate-limited, no bulk)`

### Phase C — safebreach-mcp retrieval tools
- **Semantic Change**: Add attacks-by-tag (client-side filter) and sim-results-by-tag (Lucene) reads.
- **Functions**: `sb_get_playbook_attacks_by_tags(console, tags)` (playbook),
  `sb_get_simulation_results_by_tags(console, tags)` (data); `readOnlyHint=True` wrappers.
- **Steps**: attacks — reuse `_get_all_attacks_from_cache_or_api`, filter transformed `move.tags` in
  `filter_attacks_by_criteria` (case-normalized). Sim-results — build a Lucene `query` with
  `labels:<tag>` clauses and call `executionsHistoryResults`; map via `get_reduced_simulation_result_entity`.
- **What can go wrong**: case mismatch (sim labels upper-cased) → normalize before compare; large move
  list from client-side filter → acceptable at current scale.
- **Changes**:
  | File (safebreach-mcp) | Description |
  |---|---|
  | `safebreach_mcp_playbook/playbook_functions.py` + `_server.py` | `get_playbook_attacks_by_tags`, read annotation, tag filter |
  | `safebreach_mcp_data/data_functions.py` + `_server.py` | `get_simulation_results_by_tags`, `labels:` Lucene query |
  | per-package `tests/` | filter logic, query construction, case handling |
- **Git Commit**: `feat(mcp): retrieve attacks and simulation results by tag (read-only)`

### Phase D — safebreach-mcp release (1.8.0)
- **Semantic Change**: Publish a release containing the four new tools.
- **Steps**: run the `mcp-create-release` skill — Minor bump `pyproject.toml:3` 1.7.0 → 1.8.0, add an
  em-dash (`—`) CHANGELOG "Added" section naming the tools `(SAF-29870)`, branch `release_1.8.0` off
  `main`, PR to `main`; GH Actions tags `1.8.0` + cuts the Release on merge.
- **Git Commit**: `chore: bump version to 1.8.0 and update changelog`

### Phase E — mcp-proxy pin bump + gate regression tests (this branch)
- **Semantic Change**: Consume the new release and prove the write gate covers the new tools.
- **Files**:
  | File (mcp-proxy) | Description |
  |---|---|
  | `requirements.txt:6` | bump `safebreach-mcp` pin to `@1.8.0` |
  | `tests/test_ai_actions_gate.py` | assert add/remove tag tools in `DISABLE_TOOL_LIST` when closed, absent when open |
  | `tests/test_mcp_manager.py` | assert retrieval tools never gated; write discovery via `readOnlyHint` |
- **Steps**: bump pin → run existing suite → add gate-coverage assertions keyed on the actual shipped
  tool names → run the changed test files.
- **What can go wrong**: test tool names must match shipped names (depends on B/C).
- **Git Commit**: `test(SAF-29870): cover AI-agent tag write-tool gating; bump safebreach-mcp pin to 1.8.0`

### Phase F — E2E verification on live env
- **Semantic Change**: Validate the full behavior end-to-end (verification, not code).
- **Deliverables**: note covering gate open/closed visibility, role gating (403 for non-privileged on
  all four actions), tag→query propagation, no-bulk rejection, and rate-limit gate behavior.
- **Git Commit**: `docs(SAF-29870): record E2E verification results`

---

## Section 10: Risks and Assumptions

**Technical Risks**
- **Tag-write backend endpoint** (Impact: High → **mitigated**). Pinned in Phase A: configuration
  `POST`/`DELETE /api/content/v3/accounts/{accountId}/moves/{moveId}/tags`, base-URL token `config`.
  Residual: OPA role coverage still needs live verification before B ships.
- **`readOnlyHint` mis-annotation leaks a write action** (Impact: High). Mitigation: explicit
  `readOnlyHint=False` + mcp-proxy regression test (Phase E).
- **Missing rate-limit gates on a write tool** (Impact: Medium; violates repo rule). Mitigation:
  gate-ordering unit test (Phase B), model on `test_rate_limiting.py`.
- **OPA does not cover the tag endpoints** (Impact: High) → non-privileged could tag. Mitigation:
  Phase A verification; extend policy if missing.
- **Stale playbook cache after a write** (Impact: Medium). Mitigation: `clear_playbook_cache()` after success.
- **Client-side attacks-by-tag filter pulls the full move list** (Impact: Medium at scale). Mitigation:
  accepted for current scale; backend filter tracked as Future.
- **Tag-value case divergence** (sim labels upper-cased, move tags not) (Impact: Medium). Mitigation:
  normalize on compare; verify Phase A/F.
- **Cross-repo sequencing** (pin bump depends on release) (Impact: Low). Mitigation: Phase D gates Phase E.

**Assumptions Under Question**
- The configuration `/content/v3/.../moves/{moveId}/tags` write is reachable via the MCP gateway and
  covered by OPA. — validate in Phase A (the single biggest open item).
- "Custom Tag to a playbook attack" = move-definition tag (locked with owner); retrieval spans move
  tags + sim-result labels.

**Risk Mitigation Strategies**: existing AI-actions FF + consent gate; verification-first (Phase A)
before any tool code; unit tests for gate ordering + write-tool hiding; rate limiter disabled by
default but wired.

---

## Section 11: Future Enhancements

- **Backend tag-filter param** on the moves endpoint — replace client-side filtering for scale.
- **Bulk tag actions** — currently out of scope; a future step could expose the bulk configuration
  endpoints under stricter guardrails.
- **Per-simulation-result label write** — add/remove a label on a single sim-result row, if product
  wants symmetric write.
- **Sibling AI-agent action sets** — Propagate actions (SAF-31511) and custom scenario creation
  (SAF-31910), both split from this ticket.

---

## Section 12: Executive Summary

- **Issue/Feature Description**: The AI Agent cannot tag playbook attacks or find attacks/results by
  tag through MCP; SAF-29870 adds that as a second, role-gated action set.
- **What Was Built** (planned): four MCP tools in safebreach-mcp — two rate-limited write tools +
  one read tool in the playbook server (the server's first write tools), one read tool in the data
  server — integrated through mcp-proxy via a pin bump to `@1.8.0` + gate-coverage tests, reusing the
  SAF-31410 OPA role gate, the SAF-29865 write gate, and the SAF-29871 rate limiter.
- **Key Technical Decisions**: implement in safebreach-mcp where tools live (playbook + data servers);
  port the studio write-tool pattern; client-side filtering for attacks-by-tag; write action scoped to
  move-definition tags; strictly single-item (no bulk); no bespoke gating code.
- **Scope Changes**: attacks-by-tag realized client-side (no backend filter); per-sim-result label
  write excluded — both narrowing decisions locked with the owner. Rate limiting added as a required
  deliverable after the local safebreach-mcp investigation.
- **Business Value Delivered**: completes the tag half of the AI-Agent MCP action surface (epic
  SAF-29873) with minimal new enforcement surface and a small, auditable, single-item blast radius.

---

## Section 14: Change Log

| Date | Change Description |
|------|-------------------|
| 2026-07-13 16:43 | PRD created — initial draft |
| 2026-07-14 09:00 | Revised after local safebreach-mcp (v1.7.0) investigation: corrected server placement (writes model = studio; playbook's first write tools), added mandatory rate-limiting, `kb` read path + client-side tag filter, `labels:` Lucene, cache invalidation, concrete file/function detail per phase, Minor-bump/em-dash-changelog release flow, and flagged the tag-write endpoint as the Phase-A open item |
| 2026-07-14 12:00 | Phase A started — pinned the move-tag write endpoint from code (configuration `POST`/`DELETE /api/content/v3/.../moves/{moveId}/tags`, base-URL token `config`, single-move only); OPA role behavior remains a live-env item |
| 2026-07-14 14:30 | Phase A closed (endpoint pinned; OPA→Phase F). Phase C implemented via TDD — `get_playbook_attacks_by_tags` (playbook, client-side tag filter) + `get_simulation_results_by_tags` (data, `labels:` Lucene), both `readOnlyHint=True`; added `tag_filter`/`include_tags` to playbook types; 42 new tests, full 698-test suite green. Rename/update tool added to Phase B scope |
