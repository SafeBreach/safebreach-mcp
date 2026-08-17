# Test Plan — Migrate Integration-Discovery Tools into the Config Server (SAF-32798)

> PRD: ./prd.md  |  Branch: feature/SAF-32798-expose-integration-discovery-tools  |  Status: Draft  |  Updated: 2026-08-17 10:30

## Status & Review

| Field | Value |
|-------|-------|
| Status | Draft |
| Offering / surface | console (MCP tools over a live SafeBreach console's SIEM API) + repo-harness (unit) |

## Requirements Traceability

Sources: JIRA acceptance criteria ∪ PRD §6 Definition of Done (user-confirmed at the authoring gate).

| Req | Requirement (from SAF-32798 ∪ PRD §6) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1  | Expose `get_integrations` (connector-type catalog, no secrets) | T-1, T-7, T-13, T-14 | Covered |
| R2  | Expose `get_installed_integrations` (slim id/type/name/enabled, no secrets) | T-2, T-8, T-13, T-15 | Covered |
| R3  | Expose `get_installed_integration` (one connector, secrets redacted) | T-9, T-13, T-16 | Covered |
| R4  | Expose `get_ti_integrations` (installed TI feeds, slim) | T-6, T-10, T-13, T-17 | Covered |
| R5  | All four have clear public-facing names, descriptions, input/output schemas | T-13 | Covered |
| R6  | RBAC remains enforced (esp. `get_installed_integration`) | T-11 | Covered (unit 403→PermissionError; live enforcement is ui-server's standard mechanism — see Out of scope) |
| R7  | Redaction of sensitive fields (`@enc:SENSITIVE_FIELD`, `proxyPass`, `headers`) verified | T-3, T-4, T-5, T-16 | Covered |
| R8  | Tests cover public registration of the four tools | T-13 | Covered |

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| `safebreach_mcp_config/config_types.py` | T-1, T-2, T-3, T-4, T-5, T-6 | — |
| `safebreach_mcp_config/config_functions.py` | T-7, T-8, T-9, T-10, T-11, T-12 | — |
| `safebreach_mcp_config/config_server.py` | T-13 | — |
| `safebreach_mcp_config/tests/test_config_types.py` | — | test code — it *is* the coverage for the transforms/redaction |
| `safebreach_mcp_config/tests/test_config_functions.py` | — | test code — it *is* the coverage for the `sb_*` functions |
| `safebreach_mcp_config/tests/test_config_server.py` | — | test code — it *is* the registration coverage (T-13) |
| `safebreach_mcp_config/tests/test_e2e_integrations.py` | — | test code — e2e coverage (T-14–T-19) |
| `CLAUDE.md` | — | docs-only, no runtime surface |
| `README.md` | — | docs-only, no runtime surface |

## Risk Landscape

- Known risk areas (PRD §9): (1) **secret leakage** in `get_installed_integration` — highest severity;
  the SIEM REST layer returns secrets as `$PAM:` vault refs and `headers` as a raw object, so Python-side
  redaction is the only guard. (2) TI misclassification (`isTiV2` vs in-process `tiV2`). (3) backend shape
  drift across console versions. (4) envelope handling (`{error,result}` unwrap).
- Existing coverage (investigated): Config-server tools are unit-tested in
  `safebreach_mcp_config/tests/test_config_functions.py` / `test_config_types.py` and e2e-tested in
  `test_e2e_scenarios.py` (pattern this plan follows). No integration-discovery coverage exists — this
  plan is net-new.
- What we protect: no secret material (vault paths, header values) ever leaves `get_installed_integration`;
  existing Config-server tools keep working; read-only tools never mutate.
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
| Automatic | 13   | 0           | 0      | 4   | 17    |
| Manual    | 0    | 0           | 0      | 2   | 2     |

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
  including connectors with sensitive fields and ≥1 TI (`isTiV2`) feed. `pentest01` already satisfies this
  (25 connectors incl. splunk/crowdstrike/threatconnect and TI feeds; verified live 2026-08-17). No special
  RBAC role needed for the happy-path tests.
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
| T-1  | Catalog transform maps a raw type-def to the public catalog entry | API-contract | Phase A | safebreach_mcp_config |
| T-2  | Installed transform produces slim id/type/name/enabled (no secrets) | API-contract | Phase A | safebreach_mcp_config |
| T-3  | Redaction masks every schema-`sensitive` field to `@enc:SENSITIVE_FIELD` | security | Phase A | safebreach_mcp_config |
| T-4  | Redaction force-masks `headers` and `proxyPass` even when not schema-sensitive | security | Phase A | safebreach_mcp_config |
| T-5  | Redaction fail-safe: unknown connector type never returns unredacted | security | Phase A | safebreach_mcp_config |
| T-6  | TI transform produces slim id/type/name/enabled | API-contract | Phase A | safebreach_mcp_config |
| T-7  | `sb_get_integrations` hits catalog endpoint, unwraps result, filters by category, paginates | API-contract | Phase B | safebreach_mcp_config |
| T-8  | `sb_get_installed_integrations` hits installed endpoint, returns slim, paginates | API-contract | Phase B | safebreach_mcp_config |
| T-9  | `sb_get_installed_integration` fetches /config, filters by id, returns redacted; not-found handled | API-contract | Phase B | safebreach_mcp_config |
| T-10 | `sb_get_ti_integrations` keeps only installed connectors whose catalog `isTiV2` is true | API-contract | Phase B | safebreach_mcp_config |
| T-11 | Backend 403 is surfaced as `PermissionError` + `RBAC_DENIED_HINT` | security | Phase B | safebreach_mcp_config |
| T-12 | Out-of-range `page_number` handled per repo pagination convention | regression | Phase B | safebreach_mcp_config |
| T-13 | All four tools registered with `readOnlyHint=True`, public names/descriptions/schemas | API-contract | Phase C | safebreach_mcp_config |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-14 | Live `get_integrations` returns the connector-type catalog; category filter works | Automatic | API-contract | Phase D | safebreach_mcp_config | console environment |
| T-15 | Live `get_installed_integrations` returns the slim installed list | Automatic | API-contract | Phase D | safebreach_mcp_config | console environment |
| T-16 | Live `get_installed_integration` redaction holds + cross-layer identity consistency | Automatic | security, API-contract | Phase D | safebreach_mcp_config | console environment |
| T-17 | Live `get_ti_integrations` returns the installed TI feeds | Automatic | API-contract | Phase D | safebreach_mcp_config | console environment |
| T-18 | Existing Config-server tools still work alongside the four new ones (nothing regressed) | Manual | regression | Phase D | — | console environment |
| T-19 | End-to-end discovery walkthrough of the new feature through the MCP | Manual | progression | Phase D | — | console environment |

### T-1 — Catalog entry transform

- Description: Proves the catalog transform exposes the intended public fields for a connector type and nothing extraneous.
- Status: Active
- Passes after: Phase A
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

### T-2 — Slim installed-integration transform

- Description: Proves the installed transform reduces a connector to the slim public shape without secrets.
- Status: Active
- Passes after: Phase A
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

### T-3 — Redaction masks schema-sensitive fields

- Description: Proves `redact_sensitive_fields` masks every field the catalog flags `sensitive`, regardless of its current value (incl. `$PAM:` vault refs).
- Status: Active
- Passes after: Phase A
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
- Passes after: Phase A
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
- Passes after: Phase A
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

### T-6 — Slim TI-integration transform

- Description: Proves the TI transform emits the slim public TI shape.
- Status: Active
- Passes after: Phase A
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

### T-7 — sb_get_integrations function

- Description: Proves the catalog function calls the right endpoint, unwraps the `{error,result}` envelope, filters by category, and paginates per repo convention.
- Status: Active
- Passes after: Phase B
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong endpoint/envelope handling returns nothing; broken pagination breaks the contract with sibling tools.
- Risk source: PRD §9
- Verify: Mock `get_api_base_url`/`get_api_account_id`/`requests.get` (by import path) returning `{"error":0,"result":<catalog map>}`; call with and without `category_filter` and across pages.
- Expected: Calls `GET .../config/integrations`; returns paginated catalog entries with `total_pages`/`applied_filters`/`hint_to_agent`; `category` filter narrows results.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-8 — sb_get_installed_integrations function

- Description: Proves the installed-list function hits the installed endpoint and returns the slim, paginated list.
- Status: Active
- Passes after: Phase B
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Returning raw connectors would leak config; wrong endpoint returns nothing.
- Risk source: PRD §9
- Verify: Mock the backend seams returning `{"error":0,"result":[{id,type,name,enabled},...]}`; call across pages.
- Expected: Calls `GET .../config/integrations/installed`; returns slim entries, paginated, with metadata fields.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-9 — sb_get_installed_integration function

- Description: Proves the single-connector function fetches `/config`, filters by `id`, returns the redacted connector, and handles a missing id.
- Status: Active
- Passes after: Phase B
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong source/filter returns the wrong connector or unredacted data; missing-id must not 500.
- Risk source: PRD §9
- Verify: Mock `/config` (`{"error":0,"result":{"connectors":[...]}}`) and the catalog fetch; call with a present id and an absent id.
- Expected: Present id → the matching connector, redacted (delegates to the T-3/T-4 redaction); absent id → a clear not-found result/`hint_to_agent`, no exception.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-10 — sb_get_ti_integrations function

- Description: Proves TI derivation keeps only installed connectors whose catalog type has `isTiV2 == true`.
- Status: Active
- Passes after: Phase B
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Wrong join could include non-TI connectors or drop real TI feeds.
- Risk source: PRD §9 (TI misclassification)
- Verify: Mock installed list (mix of TI and non-TI types) + catalog with `isTiV2` flags; call the function.
- Expected: Returns only the `isTiV2==true` connectors, slim-shaped, paginated.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-11 — Backend 403 → PermissionError/RBAC_DENIED_HINT

- Description: Proves an unauthorized backend response is relayed as the standard RBAC error, satisfying the Python side of R6.
- Status: Active
- Passes after: Phase B
- Level: unit
- Execution: Automatic
- Aspect: security
- Risk: Swallowing or mis-handling a 403 would hide an authorization failure or crash the tool.
- Risk source: PRD §6 (R6), §4
- Verify: Mock `requests.get` to return `status_code=403`; call each of the four `sb_*` functions.
- Expected: `check_rbac_response` raises `PermissionError` carrying `RBAC_DENIED_HINT`; no data returned.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-12 — Pagination out-of-range handling

- Description: Proves out-of-range `page_number` behaves like sibling Config tools (no crash, clear signal).
- Status: Active
- Passes after: Phase B
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Inconsistent pagination breaks the uniform contract agents rely on across tools.
- Risk source: PRD §9 (consistency), repo convention
- Verify: Call a list tool with `page_number` beyond `total_pages`.
- Expected: Same behavior as existing Config list tools (empty page + `total_pages` + `hint_to_agent`), no exception.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_functions.py`
- Environment needs: none

### T-13 — Public registration of the four tools

- Description: Proves all four tools are registered on the Config server with read-only annotations and clear public schemas (R5, R8).
- Status: Active
- Passes after: Phase C
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A tool missing, mis-named, or not marked read-only breaks discovery or the read-only contract.
- Risk source: PRD §6 (R5, R8)
- Verify: Introspect the registered Config-server tools (as existing `test_config_*` registration tests do).
- Expected: `get_integrations`, `get_installed_integrations`, `get_installed_integration`, `get_ti_integrations` present, each `readOnlyHint=True`, with non-empty description and typed input schema incl. `console`.
- Evidence required: CI run — green.
- Automation lives in: planned: `safebreach_mcp_config/tests/test_config_server.py`
- Environment needs: none

### T-14 — Live catalog retrieval + filter

- Description: Proves `get_integrations` returns a real connector-type catalog from a live console and that `category` filtering works.
- Status: Active
- Passes after: Phase D
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

### T-15 — Live installed-integrations list

- Description: Proves `get_installed_integrations` returns the slim installed list from a live console.
- Status: Active
- Passes after: Phase D
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

### T-16 — Live redaction + cross-layer identity consistency

- Description: The critical safety test — proves `get_installed_integration` on a real connector with sensitive fields returns them redacted and never leaks vault paths or header values, and that its identity matches the list tool.
- Status: Active
- Passes after: Phase D
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

### T-17 — Live TI integrations list

- Description: Proves `get_ti_integrations` returns the installed TI feeds from a live console.
- Status: Active
- Passes after: Phase D
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

### T-18 — Regression: existing Config tools unaffected

- Description: Confirms the four additions did not break the Config server — existing tools still serve correctly on a live console.
- Status: Active
- Passes after: Phase D
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
- Passes after: Phase D
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
| Phase A | T-1, T-2, T-3, T-4, T-5, T-6 | T-1…T-6 |
| Phase B | T-7, T-8, T-9, T-10, T-11, T-12 | T-1…T-12 |
| Phase C | T-13 | T-1…T-13 |
| Phase D | T-14, T-15, T-16, T-17, T-18, T-19 | all (T-1…T-19) |

## Sign-off

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [ ] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — ≥1 Manual regression test (T-18) + post-ship CI named
- [ ] Progression evidence — ≥1 Manual progression test (T-19) walking the new feature
- [ ] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Phase D) — evidence: test-results/<phase-or-date>.md
- [ ] Accepted gaps listed and approved: none

## Change Log

| Date | Change |
|------|--------|
| 2026-08-17 10:30 | Test plan created from PRD v1 |
