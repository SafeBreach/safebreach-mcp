# Test Plan — Migrate Integration-Discovery Tools into the Config Server (SAF-32798)

> PRD: ./prd.md  |  Branch: feature/SAF-32798-expose-integration-discovery-tools  |  Status: Draft  |  Updated: 2026-08-17 11:45

## Status & Review

| Field | Value |
|-------|-------|
| Status | Signed off — 32/39 automatic green + Manual lane executed via `run-helm-tests` (protocol-level, judged): T-35/36/37/38 PASS (9–10/10) + T-19 flow; T-39 partially observed; T-18 unit+server-health covered. Redaction (T-37) proven through the real AI agent. See test-results/helm-e2e.md. |
| Offering / surface | console (MCP tools over a live SafeBreach console's SIEM API) + repo-harness (unit) |

## Requirements Traceability

Sources: JIRA acceptance criteria ∪ PRD §6 Definition of Done (user-confirmed at the authoring gate).

| Req | Requirement (from SAF-32798 ∪ PRD §6) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1  | Expose `get_integrations` (connector-type catalog, no secrets) | T-1, T-7, T-13, T-14, T-20, T-21, T-22, T-23, T-24, T-34, T-35, T-39 | Covered |
| R2  | Expose `get_installed_integrations` (slim id/type/name/enabled, no secrets) | T-2, T-8, T-13, T-15, T-25, T-26, T-27, T-28, T-33, T-36 | Covered |
| R3  | Expose `get_installed_integration` (one connector, secrets redacted) | T-9, T-13, T-16, T-37 | Covered |
| R4  | Expose `get_ti_integrations` (installed TI feeds, slim) | T-6, T-10, T-13, T-17, T-29, T-30, T-31, T-32, T-38 | Covered |
| R5  | All four have clear public-facing names, descriptions, input/output schemas | T-13 | Covered |
| R6  | RBAC remains enforced (esp. `get_installed_integration`) | T-11 | Covered (unit: 403 surfaced with RBAC hint via sibling catch-and-return; live enforcement is ui-server's standard mechanism — see Out of scope) |
| R7  | Redaction of sensitive fields (`@enc:SENSITIVE_FIELD`, `proxyPass`, `headers`) verified | T-3, T-4, T-5, T-16, T-37 | Covered |
| R8  | Tests cover public registration of the four tools | T-13 | Covered |

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| `safebreach_mcp_config/config_types.py` | T-1, T-2, T-3, T-4, T-5, T-6 | — |
| `safebreach_mcp_config/config_functions.py` | T-7, T-8, T-9, T-10, T-11, T-12, T-20–T-34 | — |
| `safebreach_mcp_config/config_server.py` | T-13 | — |
| `safebreach_mcp_config/tests/test_config_types.py` | — | test code — it *is* the coverage for the transforms/redaction |
| `safebreach_mcp_config/tests/test_config_functions.py` | — | test code — it *is* the coverage for the `sb_*` functions + filters |
| `safebreach_mcp_config/tests/test_config_server.py` | — | test code — it *is* the registration coverage (T-13) |
| `safebreach_mcp_config/tests/test_e2e_integrations.py` | — | test code — e2e coverage (T-14–T-19, T-35–T-39) |
| `CLAUDE.md` | — | docs-only, no runtime surface |
| `README.md` | — | docs-only, no runtime surface |

## Risk Landscape

- Known risk areas (PRD §9): (1) **secret leakage** in `get_installed_integration` — highest severity;
  the SIEM REST layer returns secrets as `$PAM:` vault refs and `headers` as a raw object, so Python-side
  redaction is the only guard. (2) TI misclassification (`isTiV2` vs in-process `tiV2`). (3) backend shape
  drift across console versions. (4) envelope handling (`{error,result}` unwrap). (5) **filter-surface
  inconsistency** — a filter that behaves differently from sibling Config tools (non-partial, case-
  sensitive, missing `order_by`) breaks the uniform agent contract.
- Existing coverage (investigated): Config-server tools are unit-tested in
  `safebreach_mcp_config/tests/test_config_functions.py` / `test_config_types.py` and e2e-tested in
  `test_e2e_scenarios.py` (pattern this plan follows). No integration-discovery coverage exists — this
  plan is net-new.
- What we protect: no secret material (vault paths, header values) ever leaves `get_installed_integration`;
  the four tools' filter/order semantics match their siblings exactly; existing Config-server tools keep
  working; read-only tools never mutate.
- Intentionally out of scope:
  - **Live RBAC-deny e2e** — RBAC is enforced by the ui-server gateway exactly as for every other
    SafeBreach backend API; proving a 403 live needs a restricted ui-server principal that is not part of
    this ticket's surface. The Python obligation (route through the gateway, relay 403) is unit-covered by
    T-11; re-verifying ui-server's own RBAC is out of scope.
  - **Write operations** on integrations (create/update/delete) — this ticket is read-only.
  - **Withdrawing the siem-MCP copies** — SAF-35067.

## Coverage Summary (generated)

| Execution | unit | integration | system | e2e | Total |
|-----------|------|-------------|--------|-----|-------|
| Automatic | 28   | 0           | 0      | 4   | 32    |
| Manual    | 0    | 0           | 0      | 7   | 7     |

## Environment Requirements (aggregated)

- Environment classes: repo-harness / none (unit — mocked HTTP); console environment (E2E — a live
  SafeBreach console with SIEM/TI connectors installed; `E2E_CONSOLE`, default `pentest01`).

Capability checklist (answered from the plan's system/e2e tests only):

- [x] Simulators required? — **No.** The tools read integration/connector configuration, not simulations.
- [x] Running simulations / attacks required? — **No.** A static console with pre-existing installed
  connectors is sufficient; no execution needed.
- [x] Mockulators sufficient? — **N/A** (no simulators involved). E2E needs a real console whose SIEM
  connectors are already configured; unit tests mock the HTTP layer entirely.
- [x] Console-specific configuration required? — **Yes.** A console with SIEM integrations installed —
  including several connectors with sensitive fields (diverse types: splunk/crowdstrike/threatconnect/wiz)
  and ≥1 TI (`isTiV2`) feed. `pentest01` already satisfies this (25 connectors incl. those types + TI
  feeds; verified live 2026-08-17). No special RBAC role needed for the happy-path tests.
- [x] Lateral-movement topology required? — **No.** N/A for this feature.
- Required additions (beyond class defaults): none — `pentest01` is already configured and is the E2E console.
- Artifacts under test: the `safebreach-mcp` build under test; no feature-branch console images required.

## Regression

- CI that must pass: the `safebreach-mcp` repository CI — the full cross-server pytest suite
  (`uv run pytest safebreach_mcp_config/tests/ ... -m "not e2e"`). This standalone public MCP repo has no
  mapped `Automation-Pen-Testing-*` suite.
- Regression tests in this plan: T-18 (Manual).

## Tests

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|--------------|------|
| T-1  | Catalog transform maps a raw type-def to the public catalog entry | API-contract | Phase 1 | safebreach_mcp_config |
| T-2  | Installed transform produces slim id/type/name/enabled (no secrets) | API-contract | Phase 2 | safebreach_mcp_config |
| T-3  | Redaction masks every schema-`sensitive` field to `@enc:SENSITIVE_FIELD` | security | Phase 3 | safebreach_mcp_config |
| T-4  | Redaction force-masks `headers` and `proxyPass` even when not schema-sensitive | security | Phase 3 | safebreach_mcp_config |
| T-5  | Redaction fail-safe: unknown connector type never returns unredacted | security | Phase 3 | safebreach_mcp_config |
| T-6  | TI transform produces slim id/type/name/enabled | API-contract | Phase 4 | safebreach_mcp_config |
| T-7  | `sb_get_integrations` core: endpoint, `{error,result}` unwrap, pagination, applied-filters metadata | API-contract | Phase 1 | safebreach_mcp_config |
| T-8  | `sb_get_installed_integrations` core: endpoint, slim passthrough, pagination | API-contract | Phase 2 | safebreach_mcp_config |
| T-9  | `sb_get_installed_integration`: fetch /config, filter by `integration_id`, redact, not-found handled | API-contract | Phase 3 | safebreach_mcp_config |
| T-10 | `sb_get_ti_integrations` core: `isTiV2` derivation + pagination | API-contract | Phase 4 | safebreach_mcp_config |
| T-11 | Backend 403 on the shared `check_rbac_response` path → error dict carrying the RBAC denial hint (sibling catch-and-return convention) | security | Phase 1 | safebreach_mcp_config |
| T-12 | Out-of-range `page_number` handled per repo pagination convention | regression | Phase 1 | safebreach_mcp_config |
| T-13 | All four tools registered with `readOnlyHint=True`, public names/descriptions/schemas (incl. filter params) | API-contract | Phase 4 | safebreach_mcp_config |
| T-20 | `get_integrations` `name_filter` — partial, case-insensitive | API-contract | Phase 1 | safebreach_mcp_config |
| T-21 | `get_integrations` `category_filter` — partial, case-insensitive | API-contract | Phase 1 | safebreach_mcp_config |
| T-22 | `get_integrations` `vendor_filter` — partial, case-insensitive | API-contract | Phase 1 | safebreach_mcp_config |
| T-23 | `get_integrations` `ti_only` / `vm_only` boolean flags | API-contract | Phase 1 | safebreach_mcp_config |
| T-24 | `get_integrations` `order_by` (name/type/category/vendor) × `order_direction` | API-contract | Phase 1 | safebreach_mcp_config |
| T-25 | `get_installed_integrations` `name_filter` — partial, case-insensitive | API-contract | Phase 2 | safebreach_mcp_config |
| T-26 | `get_installed_integrations` `type_filter` — partial, case-insensitive | API-contract | Phase 2 | safebreach_mcp_config |
| T-27 | `get_installed_integrations` `enabled_filter` boolean | API-contract | Phase 2 | safebreach_mcp_config |
| T-28 | `get_installed_integrations` `order_by` (name/type/id/enabled) × `order_direction` | API-contract | Phase 2 | safebreach_mcp_config |
| T-29 | `get_ti_integrations` `name_filter` — partial, case-insensitive | API-contract | Phase 4 | safebreach_mcp_config |
| T-30 | `get_ti_integrations` `type_filter` — partial, case-insensitive | API-contract | Phase 4 | safebreach_mcp_config |
| T-31 | `get_ti_integrations` `enabled_filter` boolean | API-contract | Phase 4 | safebreach_mcp_config |
| T-32 | `get_ti_integrations` `order_by` (name/type/id/enabled) × `order_direction` | API-contract | Phase 4 | safebreach_mcp_config |
| T-33 | Filters compose (AND semantics) and `applied_filters` echoes every active filter | API-contract | Phase 2 | safebreach_mcp_config |
| T-34 | Zero-match filter → empty page + `hint_to_agent`, no exception | regression | Phase 1 | safebreach_mcp_config |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-14 | Live `get_integrations` returns the connector-type catalog; category filter works | Automatic | API-contract | Phase 1 | safebreach_mcp_config | console environment |
| T-15 | Live `get_installed_integrations` returns the slim installed list | Automatic | API-contract | Phase 2 | safebreach_mcp_config | console environment |
| T-16 | Live `get_installed_integration` redaction holds + cross-layer identity consistency | Automatic | security, API-contract | Phase 3 | safebreach_mcp_config | console environment |
| T-17 | Live `get_ti_integrations` returns the installed TI feeds | Automatic | API-contract | Phase 4 | safebreach_mcp_config | console environment |
| T-18 | Existing Config-server tools still work alongside the four new ones (nothing regressed) | Manual | regression | Phase 4 | — | console environment |
| T-19 | End-to-end discovery walkthrough of the new feature through the MCP | Manual | progression | Phase 4 | — | console environment |
| T-35 | Explore `get_integrations` on the live console: filter/order combinations + catalog usefulness | Manual | progression, exploratory | Phase 1 | — | console environment |
| T-36 | Explore `get_installed_integrations`: filter combinations + confirm slim/no-secret output | Manual | exploratory | Phase 2 | — | console environment |
| T-37 | Explore `get_installed_integration` redaction across MULTIPLE diverse connector types | Manual | security, exploratory | Phase 3 | — | console environment |
| T-38 | Explore `get_ti_integrations`: correctness vs catalog `isTiV2` + filters | Manual | exploratory | Phase 4 | — | console environment |
| T-39 | Pagination + `hint_to_agent` guidance across the large live catalog | Manual | UX, exploratory | Phase 1 | — | console environment |

### T-1 — Catalog entry transform

- Description: Proves the catalog transform exposes the intended public fields for a connector type and nothing extraneous.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A wrong mapping could omit `is_ti`/`is_vm`/`category` (breaking downstream filtering) or leak internal fields.
- Risk source: PRD §9
- Verify: Call the catalog transform with a raw type-def fixture (modeled on the pentest01 `/config/integrations` shape).
- Expected: Returns `{type, name/displayName, description, category, vendor, product, is_ti, is_vm, ...}` allow-list only; no unlisted keys.
- Evidence required: CI run (repo pytest suite) — green with the new assertions.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_types.py`
- Environment needs: none

### T-7 — sb_get_integrations core

- Description: Proves the catalog function calls the right endpoint, unwraps the `{error,result}` envelope, paginates, and returns the standard metadata — filter logic is covered by T-20–T-24.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong endpoint/envelope handling returns nothing; broken pagination breaks the contract with sibling tools.
- Risk source: PRD §9
- Verify: Mock `get_api_base_url`/`get_api_account_id`/`requests.get` (by import path) returning `{"error":0,"result":<catalog map>}`; call unfiltered across pages.
- Expected: Calls `GET .../config/integrations`; returns catalog entries paginated with `total_pages`/`applied_filters`/`hint_to_agent`.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-11 — Backend 403 → PermissionError/RBAC_DENIED_HINT (shared path)

- Description: Proves an unauthorized backend response is surfaced with the RBAC denial hint via the shared `check_rbac_response` path all four functions use — gated at Phase 1 so any RBAC-relay regression is caught immediately.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: security
- Risk: Swallowing or mis-handling a 403 would hide an authorization failure; the path is shared, so a break affects all four tools.
- Risk source: PRD §6 (R6), §4
- Verify: Mock `requests.get` to return `status_code=403`; call `sb_get_integrations` (representative of the shared `check_rbac_response` path; later tools reuse it — confirmed by their core tests T-8/T-9/T-10).
- Expected: `check_rbac_response` raises `PermissionError` internally; the function catches it (sibling `sb_get_console_simulators`/`sb_get_scenarios` convention) and returns an `{"error": ...}` dict whose message contains the RBAC denial hint (`Access denied (403 Forbidden)` / `RBAC_DENIED_HINT` text); no connector data is returned.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-12 — Pagination out-of-range handling

- Description: Proves out-of-range `page_number` behaves like sibling Config tools (no crash, clear signal) on the shared pagination path.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Inconsistent pagination breaks the uniform contract agents rely on across tools.
- Risk source: PRD §9 (consistency), repo convention
- Verify: Call `sb_get_integrations` (representative list tool; pagination is shared logic) with `page_number` beyond `total_pages`.
- Expected: Same behavior as existing Config list tools (empty page + `total_pages` + `hint_to_agent`), no exception.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-20 — get_integrations name_filter

- Description: Proves the catalog `name_filter` matches partially and case-insensitively, like sibling tools.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A case-sensitive or exact-only filter diverges from every other Config list tool.
- Risk source: PRD §2.0, §9 (filter consistency)
- Verify: Seed a catalog fixture with mixed-case names (e.g. `Splunk`, `CrowdStrike`, `QRadar`); call with `name_filter="splunk"` and `name_filter="STRIKE"`.
- Expected: Returns only entries whose name contains the term case-insensitively; `applied_filters.name_filter` echoes the term; non-matching entries absent.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-21 — get_integrations category_filter

- Description: Proves the catalog `category_filter` narrows by category, partial and case-insensitive.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong category matching returns the wrong connector types.
- Risk source: PRD §2.0
- Verify: Seed a catalog with multiple categories (e.g. `siem`, `ti`, `security_control`); call with `category_filter="ti"` and a mixed-case variant.
- Expected: Only entries in the matching category returned; `applied_filters.category_filter` echoed.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-22 — get_integrations vendor_filter

- Description: Proves the catalog `vendor_filter` narrows by vendor, partial and case-insensitive.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Vendor filter absent/incorrect breaks parity with the per-field filter pattern of sibling tools.
- Risk source: PRD §2.0
- Verify: Seed a catalog with distinct vendors; call `vendor_filter` with a partial, mixed-case term.
- Expected: Only matching-vendor entries returned; `applied_filters.vendor_filter` echoed.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-23 — get_integrations ti_only / vm_only flags

- Description: Proves the boolean catalog flags filter to TI-capable / VM-capable connector types (mirrors `critical_only`/`recommended_filter`).
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A wrong boolean semantic (e.g. treating `False` as "no filter") would silently mislead.
- Risk source: PRD §2.0
- Verify: Seed a catalog mixing `isTi`/`isVm` true/false entries; call `ti_only=True`, `vm_only=True`, and both `None`.
- Expected: `ti_only=True` → only `is_ti` entries; `vm_only=True` → only `is_vm` entries; `None` → no filtering; flags echoed in `applied_filters`.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-24 — get_integrations ordering

- Description: Proves `order_by` × `order_direction` sort the catalog deterministically across the allowed keys.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Missing/broken ordering diverges from sibling tools that all support `order_by`/`order_direction`.
- Risk source: PRD §2.0
- Verify: Seed a catalog with distinguishable name/type/category/vendor; call each `order_by` in `asc` and `desc`.
- Expected: Results sorted by the chosen key/direction; default (`name`,`asc`) matches sibling defaults.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-34 — Zero-match filter yields empty page + hint

- Description: Proves a filter matching nothing returns an empty page with a guiding `hint_to_agent`, not an error, on the shared list path.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: A crash or bare empty list (no hint) on zero matches breaks the sibling-consistent UX agents rely on.
- Risk source: PRD §9 (consistency)
- Verify: Call `sb_get_integrations` (representative list tool) with a filter value that matches nothing.
- Expected: Empty result set, `total_pages` consistent, `hint_to_agent` present guiding a broader query; no exception.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-14 — Live catalog retrieval + filter

- Description: Proves `get_integrations` returns a real connector-type catalog from a live console and that `category` filtering works.
- Status: Active
- Passes after: Phase 1
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: Backend shape drift or wrong endpoint would surface only against a real console.
- Risk source: PRD §9 (shape drift)
- Verify: Against `E2E_CONSOLE`, call `sb_get_integrations` unfiltered and with a `category` present in the response.
- Expected: Non-empty catalog of connector types; filtered call returns a strict, non-empty subset all matching the category.
- Evidence required: transcript/command log + captured tool output (observed vs expected), from the e2e run.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_e2e_integrations.py`
- Environment needs: console environment

### T-35 — Explore get_integrations on the live console

- Description: Exercises the catalog tool the way a user would — varied filter/order combinations against real data — and judges the catalog's usefulness and description quality.
- Status: Active
- Passes after: Phase 1
- Level: e2e
- Execution: Manual
- Aspect: progression, exploratory
- Risk: Deterministic assertions (T-14) can pass while the tool is awkward to use — poor descriptions, filters that surprise the user, unhelpful ordering.
- Risk source: reviewer input (manual functionality coverage)
- Verify: AI agent, against `E2E_CONSOLE`, calls `get_integrations` with several ad-hoc combinations — `name_filter`, `category_filter`, `vendor_filter`, `ti_only`, `vm_only`, and different `order_by`/`order_direction` — comparing results across calls.
- Expected: Filters visibly narrow the catalog as their names imply; `ti_only`/`vm_only` select the expected families; ordering changes are correct and stable; catalog entries carry human-legible descriptions/vendor/product.
- Evidence required: transcript/command log + captured outputs per combination + observed-vs-expected narrative; BLOCKED if unreachable.
- Manual because: exploratory judgment over filter ergonomics and description quality — not a single deterministic assertion.
- Environment needs: console environment

### T-39 — Pagination and hint_to_agent guidance across the large catalog

- Description: Assesses the paging UX on the largest real result set (the catalog, ~90 types), confirming `hint_to_agent` guides the next action coherently.
- Status: Active
- Passes after: Phase 1
- Level: e2e
- Execution: Manual
- Aspect: UX, exploratory
- Risk: Pagination metadata or hints that are correct in unit fixtures may still be confusing at real scale.
- Risk source: reviewer input; PRD §9 (consistency)
- Verify: Against `E2E_CONSOLE`, page through `get_integrations` from page 0 to the last page and one past it; read `total_pages`/`hint_to_agent` at each step.
- Expected: Page counts are consistent with the total; each page advances without gaps/overlaps; hints correctly indicate whether more pages exist and how to proceed; past-the-end page behaves like sibling tools.
- Evidence required: transcript + captured page outputs + observed-vs-expected narrative; BLOCKED if unreachable.
- Manual because: exploratory UX judgment over paging ergonomics at real scale.
- Environment needs: console environment

### T-2 — Slim installed-integration transform

- Description: Proves the installed transform reduces a connector to the slim public shape without secrets.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Passing through extra fields could leak configuration or secrets in the list tool.
- Risk source: PRD §9
- Verify: Call the transform with a full connector fixture (with sensitive fields present).
- Expected: Returns exactly `{id, type, name, enabled}` (plus optional non-secret `category` if adopted); no secret/config fields.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_types.py`
- Environment needs: none

### T-8 — sb_get_installed_integrations core

- Description: Proves the installed-list function hits the installed endpoint and returns the slim, paginated list — filter logic is covered by T-25–T-28.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Returning raw connectors would leak config; wrong endpoint returns nothing.
- Risk source: PRD §9
- Verify: Mock the backend seams returning `{"error":0,"result":[{id,type,name,enabled},...]}`; call unfiltered across pages.
- Expected: Calls `GET .../config/integrations/installed`; returns slim entries, paginated, with metadata fields.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-25 — get_installed_integrations name_filter

- Description: Proves the installed `name_filter` matches partially and case-insensitively.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Divergent match semantics break the uniform contract.
- Risk source: PRD §2.0
- Verify: Seed an installed list with mixed-case names; call `name_filter` partial/mixed-case.
- Expected: Only matching entries; `applied_filters.name_filter` echoed.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-26 — get_installed_integrations type_filter

- Description: Proves the installed `type_filter` narrows by connector type, partial and case-insensitive.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong type matching returns the wrong connectors.
- Risk source: PRD §2.0
- Verify: Seed installed connectors of several types (e.g. `splunkrest`, `cortexxdr`, `alienvault`); call `type_filter="splunk"`.
- Expected: Only matching-type entries; filter echoed.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-27 — get_installed_integrations enabled_filter

- Description: Proves the boolean `enabled_filter` selects enabled/disabled connectors correctly.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: `enabled_filter=False` must mean "only disabled", not "no filter".
- Risk source: PRD §2.0
- Verify: Seed an asymmetric mix (more enabled than disabled); call `enabled_filter=True`, `False`, `None`.
- Expected: `True` → only enabled; `False` → only disabled; `None` → all; filter echoed.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-28 — get_installed_integrations ordering

- Description: Proves `order_by` (name/type/id/enabled) × `order_direction` sorts deterministically.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Missing/broken ordering diverges from sibling tools.
- Risk source: PRD §2.0
- Verify: Seed distinguishable installed connectors; call each `order_by` in both directions.
- Expected: Sorted by chosen key/direction; default `name`/`asc`.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-33 — Filters compose (AND semantics)

- Description: Proves multiple filters on one tool combine with AND semantics and every active filter is echoed in `applied_filters`.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: OR-combining or dropping a filter would return too many results and mislead the agent.
- Risk source: PRD §2.0, §9
- Verify: On `get_installed_integrations`, seed connectors so that `name_filter` + `type_filter` + `enabled_filter` each match different overlapping subsets; call with all three set.
- Expected: Only connectors satisfying ALL three; `applied_filters` lists all three with their values; a connector matching only two is absent.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-15 — Live installed-integrations list

- Description: Proves `get_installed_integrations` returns the slim installed list from a live console.
- Status: Active
- Passes after: Phase 2
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: Real installed data may expose shape issues the mocks miss.
- Risk source: PRD §9
- Verify: Against `E2E_CONSOLE`, call `sb_get_installed_integrations`.
- Expected: Non-empty list; every item has exactly the slim keys; no secret/config fields present.
- Evidence required: transcript + captured output.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_e2e_integrations.py`
- Environment needs: console environment

### T-36 — Explore get_installed_integrations on the live console

- Description: Exercises the installed-list tool with real data and confirms, by inspection, that filters behave and the slim output never carries secrets.
- Status: Active
- Passes after: Phase 2
- Level: e2e
- Execution: Manual
- Aspect: exploratory
- Risk: A filter regression or an accidental non-slim field would show up only against the variety of real connectors.
- Risk source: reviewer input; PRD §9 (no-secret guarantee)
- Verify: Against `E2E_CONSOLE`, call `get_installed_integrations` unfiltered, then with `name_filter`, `type_filter`, and `enabled_filter=True/False`; inspect a sample of returned items.
- Expected: Each filter narrows as expected; every returned item is exactly `{id,type,name,enabled}` (+ optional non-secret `category`); no secret/config/`$PAM:`/`headers` fields appear anywhere.
- Evidence required: transcript + captured outputs + observed-vs-expected narrative; BLOCKED if unreachable.
- Manual because: exploratory judgment over filter behavior and no-secret confirmation across diverse real connectors.
- Environment needs: console environment

### T-3 — Redaction masks schema-sensitive fields

- Description: Proves `redact_sensitive_fields` masks every field the catalog flags `sensitive`, regardless of its current value (incl. `$PAM:` vault refs).
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: security
- Risk: A missed sensitive field leaks a vault path or credential from `get_installed_integration`.
- Risk source: PRD §9 (highest-severity)
- Verify: Given a connector fixture with `$PAM:INTERNAL_VAULT:...` and plaintext values, and a catalog whose `fields[].sensitive` marks the secret fields, run the redaction.
- Expected: Every schema-`sensitive` field value == `@enc:SENSITIVE_FIELD`; non-sensitive fields (e.g. `host`, `clientId`) unchanged; no `$PAM:` substring survives in any sensitive field.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_types.py`
- Environment needs: none

### T-4 — Redaction force-masks headers and proxyPass

- Description: Proves the `headers`/`proxyPass` backstop masks them even when the schema does not flag them sensitive (headers can carry bearer tokens).
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: security
- Risk: `headers` comes back as a raw object over REST and is not schema-`sensitive`; without the backstop, auth headers leak.
- Risk source: PRD §9 (live-confirmed on pentest01: `custom_wiz.headers` returned as raw object)
- Verify: Run redaction on a connector fixture carrying a `headers` object and a `proxyPass` value, with a catalog that does NOT flag them sensitive.
- Expected: `headers` and `proxyPass` == `@enc:SENSITIVE_FIELD`; no header key/value survives.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_types.py`
- Environment needs: none

### T-5 — Redaction fail-safe on unknown connector type

- Description: Proves an unknown/absent catalog type never yields an unredacted connector.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: security
- Risk: A connector whose type is missing from the catalog could bypass schema-driven masking and leak secrets.
- Risk source: PRD §9, §2.1 fail-safe requirement
- Verify: Run redaction with a connector whose `type` has no catalog entry.
- Expected: A conservative default set plus `headers`/`proxyPass` are masked to `@enc:SENSITIVE_FIELD`; no `$PAM:` value survives; function does not raise.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_types.py`
- Environment needs: none

### T-9 — sb_get_installed_integration function

- Description: Proves the single-connector function fetches `/config`, filters by `integration_id`, returns the redacted connector, and handles a missing id.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong source/filter returns the wrong connector or unredacted data; missing-id must not 500.
- Risk source: PRD §9
- Verify: Mock `/config` (`{"error":0,"result":{"connectors":[...]}}`) and the catalog fetch; call with a present `integration_id` and an absent one.
- Expected: Present `integration_id` → the matching connector, redacted (delegates to the T-3/T-4 redaction); absent → a clear not-found result/`hint_to_agent`, no exception. (Param is `integration_id`, not bare `id`, per repo detail-tool convention.)
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-16 — Live redaction + cross-layer identity consistency

- Description: The critical safety test — proves `get_installed_integration` on a real connector with sensitive fields returns them redacted and never leaks vault paths or header values, and that its identity matches the list tool.
- Status: Active
- Passes after: Phase 3
- Level: e2e
- Execution: Automatic
- Aspect: security, API-contract
- Risk: Any redaction miss leaks a real credential path / auth header — the highest-severity failure.
- Risk source: PRD §9 (highest), §2.1
- Verify: Against `E2E_CONSOLE`, self-discover a connector id from `get_installed_integrations` whose catalog type has ≥1 `sensitive` field (or `headers`); fetch it via `get_installed_integration`.
- Expected: Every schema-`sensitive` field and `headers`/`proxyPass` == `@enc:SENSITIVE_FIELD`; the response contains NO `$PAM:` substring and no raw header value; the returned `id/type/name` equal the values from the list tool. (Never hardcode a connector id.)
- Evidence required: transcript + captured (redacted) output showing masked fields + the negative-space assertion.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_e2e_integrations.py`
- Environment needs: console environment

### T-37 — Explore redaction across multiple connector types

- Description: The highest-value manual check — confirms `get_installed_integration` redaction holds across DIVERSE connector types (different sensitive-field sets and a `headers`-bearing type), and that the redacted output is still useful.
- Status: Active
- Passes after: Phase 3
- Level: e2e
- Execution: Manual
- Aspect: security, exploratory
- Risk: Redaction is schema-driven per type; a gap could exist for one connector type but not another — a single automatic sample (T-16) cannot cover the breadth.
- Risk source: PRD §9 (highest-severity), §2.1
- Verify: Against `E2E_CONSOLE`, self-discover installed connectors of several types with sensitive fields (e.g. `splunkrest`, `custom_crowdstrike`, `threatconnect`, and a `custom_wiz`/`headers`-bearing one); fetch each via `get_installed_integration`.
- Expected: For every type, all schema-`sensitive` fields and `headers`/`proxyPass` are `@enc:SENSITIVE_FIELD`; no `$PAM:` path or header value appears in any response; non-secret fields remain present so the config is still informative.
- Evidence required: transcript + captured (redacted) outputs per connector type + explicit negative-space check; BLOCKED if no such connectors exist on the console.
- Manual because: exploratory security judgment over redaction breadth across heterogeneous connector types — beyond the single deterministic sample in T-16.
- Environment needs: console environment

### T-6 — Slim TI-integration transform

- Description: Proves the TI transform emits the slim public TI shape.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Extra fields could leak config; wrong shape breaks the TI list contract.
- Risk source: PRD §9
- Verify: Call the TI transform with a TI connector fixture.
- Expected: Returns exactly `{id, type, name, enabled}`.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_types.py`
- Environment needs: none

### T-10 — sb_get_ti_integrations core

- Description: Proves TI derivation keeps only installed connectors whose catalog type has `isTiV2 == true`, and paginates — filter logic is covered by T-29–T-32.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong join could include non-TI connectors or drop real TI feeds.
- Risk source: PRD §9 (TI misclassification)
- Verify: Mock installed list (mix of TI and non-TI types) + catalog with `isTiV2` flags; call unfiltered across pages.
- Expected: Returns only the `isTiV2==true` connectors, slim-shaped, paginated with metadata.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-29 — get_ti_integrations name_filter

- Description: Proves the TI `name_filter` matches partially and case-insensitively over the derived TI set.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Filtering before/after the `isTiV2` derivation could drop valid TI feeds.
- Risk source: PRD §2.0
- Verify: Seed installed TI + non-TI connectors with mixed-case names; call `name_filter`.
- Expected: Only `isTiV2` connectors whose name matches; filter echoed; non-TI never appears.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-30 — get_ti_integrations type_filter

- Description: Proves the TI `type_filter` narrows by type within the derived TI set.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong ordering of derivation vs filter could leak non-TI or drop TI.
- Risk source: PRD §2.0
- Verify: Seed TI connectors of several types (e.g. `alienvault`, `threatconnect`); call `type_filter`.
- Expected: Only matching-type TI connectors; filter echoed.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-31 — get_ti_integrations enabled_filter

- Description: Proves the boolean `enabled_filter` works within the derived TI set.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: `False` must mean "only disabled TI feeds".
- Risk source: PRD §2.0
- Verify: Seed enabled + disabled TI connectors; call `enabled_filter=True/False/None`.
- Expected: Correct subset per flag; filter echoed; all still `isTiV2`.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-32 — get_ti_integrations ordering

- Description: Proves `order_by` (name/type/id/enabled) × `order_direction` sorts the TI set deterministically.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Missing/broken ordering diverges from sibling tools.
- Risk source: PRD §2.0
- Verify: Seed distinguishable TI connectors; call each `order_by` in both directions.
- Expected: Sorted by chosen key/direction; default `name`/`asc`.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-13 — Public registration of the four tools

- Description: Proves all four tools are registered on the Config server with read-only annotations and clear public schemas incl. the full filter parameter set (R5, R8) — green only once the fourth tool is registered.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A tool missing, mis-named, not read-only, or missing a filter param breaks discovery or the sibling-consistent contract.
- Risk source: PRD §6 (R5, R8), §2.0
- Verify: Introspect the registered Config-server tools (as existing `test_config_*` registration tests do).
- Expected: `get_integrations`, `get_installed_integrations`, `get_installed_integration`, `get_ti_integrations` present, each `readOnlyHint=True`, with non-empty description and a typed input schema exposing `console`, the `<field>_filter`/bool-flag params, `order_by`/`order_direction` (list tools), `page_number` (list tools), and `integration_id` (detail tool).
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_server.py`
- Environment needs: none

### T-17 — Live TI integrations list

- Description: Proves `get_ti_integrations` returns the installed TI feeds from a live console.
- Status: Active
- Passes after: Phase 4
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: TI derivation (`isTiV2` join) could misclassify against real data.
- Risk source: PRD §9 (TI misclassification)
- Verify: Against `E2E_CONSOLE`, call `sb_get_ti_integrations` and cross-check that every returned type has `isTiV2==true` in the live catalog.
- Expected: Returns the console's TI feeds, slim-shaped; every returned type is `isTiV2` in the catalog; a known non-TI connector is absent.
- Evidence required: transcript + captured output.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_e2e_integrations.py`
- Environment needs: console environment

### T-38 — Explore get_ti_integrations on the live console

- Description: Confirms the TI list is correct against real data and cross-checks it against the live catalog's `isTiV2`, plus filter behavior.
- Status: Active
- Passes after: Phase 4
- Level: e2e
- Execution: Manual
- Aspect: exploratory
- Risk: TI misclassification (`isTiV2` vs actual capability) could add non-TI or drop real TI feeds — visible only against real data.
- Risk source: PRD §9 (TI misclassification)
- Verify: Against `E2E_CONSOLE`, call `get_ti_integrations`; independently call `get_integrations` and note which types are `isTiV2`; cross-check membership; then apply `name_filter`/`type_filter`/`enabled_filter`.
- Expected: Every returned TI connector's type is `isTiV2` in the catalog; known non-TI connectors are absent; filters narrow correctly.
- Evidence required: transcript + captured outputs + the cross-check table; BLOCKED if unreachable.
- Manual because: exploratory correctness judgment joining two live tools — not a single deterministic assertion.
- Environment needs: console environment

### T-18 — Regression: existing Config tools unaffected

- Description: Confirms the four additions did not break the Config server — existing tools still serve correctly on a live console.
- Status: Active
- Passes after: Phase 4
- Level: e2e
- Execution: Manual
- Aspect: regression
- Risk: Shared module edits (imports, registration, cache helper) could break sibling tools like `get_console_simulators`/`get_scenarios`.
- Risk source: PRD §9 (consistency), reviewer input
- Verify: AI agent exercises the running Config server against `E2E_CONSOLE`: lists the tools, invokes `get_console_simulators` and `get_scenarios`, then the four new tools, observing all respond without error and the tool inventory is complete.
- Expected: Pre-existing tools return their usual data; the four new tools coexist; no registration/import breakage.
- Evidence required: transcript/command log + per-tool observed output; BLOCKED (not pass) if the console is unreachable.
- Manual because: cross-tool, whole-server judgment over the live product — an exploratory confidence check, not a single deterministic assertion.
- Environment needs: console environment

### T-19 — Progression: new-feature discovery walkthrough

- Description: Sign-off walkthrough of the new capability as a user would experience it, end to end through the MCP.
- Status: Active
- Passes after: Phase 4
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: Individually-green tools may still not compose into a coherent discovery flow.
- Risk source: reviewer input (progression mandate)
- Verify: AI agent, against `E2E_CONSOLE`, walks: `get_integrations` (browse types) → `get_installed_integrations` (pick an installed one) → `get_installed_integration` (inspect its redacted config) → `get_ti_integrations` (list TI feeds), following ids discovered at each step.
- Expected: The flow completes coherently; each step's output feeds the next; redacted config is readable and secret-free; the experience matches the tool descriptions.
- Evidence required: transcript/command log + captured outputs at each step + observed-vs-expected narrative; BLOCKED if unreachable.
- Manual because: exploratory end-to-end judgment for sign-off confidence, beyond the deterministic e2e assertions.
- Environment needs: console environment

## Tests by Phase (readiness view — generated)

Cumulative: at the end of phase N, EVERY test with "Passes after" <= N must be green.

| After phase | Newly green | Cumulative green |
|-------------|-------------|------------------|
| Phase 1 | T-1, T-7, T-11, T-12, T-14, T-20, T-21, T-22, T-23, T-24, T-34, T-35, T-39 | 13 |
| Phase 2 | T-2, T-8, T-15, T-25, T-26, T-27, T-28, T-33, T-36 | 22 |
| Phase 3 | T-3, T-4, T-5, T-9, T-16, T-37 | 28 |
| Phase 4 | T-6, T-10, T-13, T-17, T-18, T-19, T-29, T-30, T-31, T-32, T-38 | 39 |

## Sign-off

- [x] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [x] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — Manual regression T-18 is a manual-substitution (direct `sb_*` probe), NOT the planned `run-helm-tests` run; owes a real run
- [ ] Progression evidence — Manual progression T-19/T-35 are manual-substitutions, not the planned protocol-level runs; owe a real run
- [x] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Phase 4) — 32/39 executed green (132 unit + 4 automatic e2e); 7 Manual e2e are open manual-substitutions (test-results/phase-4.md)
- [ ] Accepted gaps listed and approved: pending — Manual e2e lane owes a `run-helm-tests` run on a deployed console

## Change Log

| Date | Change |
|------|--------|
| 2026-08-17 10:30 | Test plan created from PRD v1 |
| 2026-08-17 11:20 | Densified filter coverage — narrowed T-7/T-8/T-10 to core; added granular per-filter/ordering unit tests T-20–T-34 and per-capability manual E2E T-35–T-39. |
| 2026-08-17 11:45 | Re-keyed every test to its soonest phase against the vertical-slice PRD §8 (per-tool phases 1–4); rescoped shared-path tests T-11/T-12/T-34 to Phase 1. |
