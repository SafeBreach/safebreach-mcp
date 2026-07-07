# MCP Semantics: "Evaluating Test" and "Quick Run"

## 1. Overview

Rename two confusing user-facing concepts in the studio MCP tools: the "dry run" preview state becomes "evaluating test" semantics, and the `run_adhoc_scenario` tool becomes `quick_run` to match platform naming.

**Business Problem:** Users see "dry run" when a test is being evaluated, which is confusing, and the "ad-hoc" tool name is inconsistent with the platform's "Quick Run" terminology.

**Key Benefits:**
- The evaluation preview reads as what it is: evaluating a test before queuing it.
- Tool naming matches the SafeBreach platform vocabulary ("Quick Run").

**Target Consumer:** MCP agent users running or evaluating tests through the studio MCP tools.

> **Scope decisions:**
> 1. The rename goes all the way: parameter (`dry_run` -> `evaluate`), response status (`'dry_run'` -> `'evaluating'`), and all wording. Verified safe: the concept never reaches the SafeBreach REST API (both tools return the preview before `_submit_to_queue`), and no known consumer references the parameter, status value, or tool names on the wire — MCP clients discover tools dynamically.
> 2. New wire-level tool name is `quick_run`.
> 3. The delete-preview `dry_run` in `manage_test`/`sb_delete_test`/`sb_manage_test` is a SEPARATE confirm-before-destroy mechanism and is NOT touched.

---

## 2. Core Feature Components

### Current State
- `safebreach_mcp_studio/studio_server.py` registers `run_scenario` with `dry_run: bool = False` and `run_adhoc_scenario` with `dry_run: bool = True`, via `@self.mcp.tool(name=..., annotations=..., description=...)`.
- Preview responses carry `'status': 'dry_run'` and render Markdown headers "## Dry Run — Simulation Prediction" / "## Ad-hoc Scenario — Dry Run Preview".
- Ad-hoc internals: `sb_run_adhoc_scenario`, `_build_adhoc_steps`, `_apply_adhoc_overrides` in `studio_functions.py`; default test name `f"Ad-hoc Test ({len(steps)} attacks)"`; rate-limit bucket `"run_adhoc_scenario"`.
- Cross-package hint in `safebreach_mcp_config/config_types.py` tells the model to use `run_scenario ... dry_run=True`.

### Target State
- Tool `quick_run` (was `run_adhoc_scenario`) with `evaluate: bool = True` parameter; `run_scenario` with `evaluate: bool = False`.
- Preview responses carry `'status': 'evaluating'`; headers read "## Evaluating Test — Simulation Prediction" / "## Quick Run — Test Evaluation"; hints say "call again with evaluate=False" to queue the test.
- Default ad-hoc test name becomes `f"Quick Run ({len(steps)} attacks)"`; rate-limit bucket `"quick_run"`.
- Internal names follow: `sb_quick_run`, `_build_quick_run_steps`, `_apply_quick_run_overrides`.
- Docs (CLAUDE.md catalog + gate table) and the config-package hint updated. Delete-preview `dry_run` untouched.

---

## 3. Technical Specifications

### API Changes (MCP tool contract)
- Tool rename: `run_adhoc_scenario` -> `quick_run` (wire-level `name=` in the FastMCP decorator; `ToolAnnotations` unchanged: `readOnlyHint=False, destructiveHint=True`).
- Parameter rename on `run_scenario` and `quick_run`: `dry_run` -> `evaluate` (same types/defaults: `False` for `run_scenario`, `True` for `quick_run`).
- Response status value: `'dry_run'` -> `'evaluating'` in the two run-evaluation preview dicts (NOT in the delete preview).

### Data Model Changes
- None (no persistence).

### Configuration Changes
- None.

### Dependencies
- None. Verified: no upstream REST parameter depends on the old names; rate-limit buckets are free-form call-site strings; no RBAC/allowlist is keyed by tool name.

---

## 4. Definition of Done

- [ ] Evaluation preview presents "evaluating test" wording everywhere the user/model sees it (headers, hints, docstrings, status).
- [ ] The ad-hoc tool is named `quick_run` and described as "Quick Run" everywhere.
- [ ] Delete-preview `dry_run` behavior and wording unchanged.
- [ ] `run_scenario` description's cross-reference and `config_types.py` hint updated.
- [ ] CLAUDE.md tool catalog and rate-limiting gate table updated.
- [ ] "Quick Run" wording does not conflate with `run_studio_attack`'s existing "parity with a UI quick-run" phrasing (that description gets clarified if needed).
- [ ] Unit tests written and passing
- [ ] Code coverage maintained or improved
- [ ] Code follows existing repository patterns
- [ ] No unnecessary changes outside task scope

---

## 5. Implementation Phases

### Phase 1: Rename the evaluation concept (dry_run -> evaluate/evaluating)
**Scope:** `run_scenario` + `run_adhoc_scenario` evaluation flow only; delete preview excluded.

**Deliverables:**
- `evaluate` parameter on both tools, `'evaluating'` status, all user/model-facing wording updated.

**Files to modify:**
- `safebreach_mcp_studio/studio_server.py`: `run_scenario` signature/description/examples, status branch, Markdown header, hint texts; `run_adhoc_scenario` signature/description, status branch, header, hint.
- `safebreach_mcp_studio/studio_functions.py`: `sb_run_scenario`, `sb_run_adhoc_scenario` signatures, docstrings, preview dicts, hint strings, internal uses.
- `safebreach_mcp_config/config_types.py`: hint text.

### Phase 2: Rename the tool (run_adhoc_scenario -> quick_run)
**Scope:** Wire name, descriptions, internals, rate-limit bucket, default test name.

**Files to modify:**
- `safebreach_mcp_studio/studio_server.py`: `name="quick_run"`, description, inner def, import; `run_scenario` description cross-reference; headers "## Quick Run ...", error text.
- `safebreach_mcp_studio/studio_functions.py`: `sb_quick_run`, `_build_quick_run_steps`, `_apply_quick_run_overrides`, default test name, rate-limit labels, log messages, section comment.

### Phase 3: Tests and docs
**Files to modify:**
- `safebreach_mcp_studio/tests/test_e2e_run_adhoc_scenario.py` -> rename to `test_e2e_quick_run.py`, update tool/function references.
- `safebreach_mcp_studio/tests/test_e2e_run_scenario.py`, `test_studio_functions.py`, `test_rate_limiting.py`: `evaluate`/`'evaluating'`/`sb_quick_run` updates, test function renames (`test_dry_run*` -> `test_evaluate*`), keeping delete-preview tests (`test_delete_dry_run_*`) unchanged.
- `CLAUDE.md`: tool catalog entries, gate table.
- `CHANGELOG.md`: new entry for the rename.

---

## 6. Testing Strategy

### Unit Tests
- Evaluation preview (`evaluate=True`) returns `'status': 'evaluating'` with prediction fields, without calling the queue API or rate-limit gates.
- `quick_run` queues a test when `evaluate=False` and the default test name starts with "Quick Run".
- Rate limiting keys on the `"quick_run"` bucket.

### Edge Cases
- `manage_test action='delete'` still returns `'status': 'dry_run'` and `dry_run: True` (proves the delete preview was not conflated).
- Markdown output contains the new headers and no "dry run"/"ad-hoc" strings in the evaluation flow.

### Error Scenarios
- `quick_run` with attacks that produce 0 simulations returns the updated error wording.

---

## 7. Risks and Mitigation

### Technical Risks
- **Existing clients calling `run_adhoc_scenario` or passing `dry_run`:** breaking change on the MCP wire contract. Mitigation: MCP clients discover tools dynamically; saved prompts referencing old names will get a tool-not-found — acceptable per the rename's intent; flagged in CHANGELOG.
- **Conflating the delete preview:** mitigated by explicit exclusion (Phase 1 scope) and regression coverage.
- **"Quick Run" collision with `run_studio_attack`'s "UI quick-run" phrasing:** clarify that description if it becomes ambiguous.

### Dependencies
- None.
