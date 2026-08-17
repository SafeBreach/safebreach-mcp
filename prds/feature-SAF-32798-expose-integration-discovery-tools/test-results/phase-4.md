# Test Results — Phase 4 (SAF-32798)
> Plan: ../test-plan.md | Run: 2026-08-17 (running-phase-tests, --phase 4) | Mode: run

Phase 4 is the last numbered phase → cumulative set = every Active T-item (Passes after ≤ 4) = **39 tests**
(no `Final` tests in this plan). Repo = standalone-Python (uv-pytest); no UI, no jest, no Playwright.

## Accounting
| T-<n> | Level | Execution | Env | Runner (intended) | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|-------------------|---------|-------------------|
| T-1..T-6 | unit | Automatic | none | source-repo uv-pytest | executed ✅ | `uv run pytest test_config_types.py -m "not e2e"` — part of 132 passed |
| T-7..T-13 | unit | Automatic | none | source-repo uv-pytest | executed ✅ | 132 passed (functions + server registration) |
| T-20..T-34 | unit | Automatic | none | source-repo uv-pytest | executed ✅ | 132 passed (per-filter/ordering/compose/zero-match) |
| T-14 | e2e | Automatic | console env | source-repo uv-pytest (`-m e2e`) | executed ✅ | `uv run pytest test_e2e_integrations.py -m e2e` — 4 passed, live pentest01 |
| T-15 | e2e | Automatic | console env | source-repo uv-pytest (`-m e2e`) | executed ✅ | 4 passed, live pentest01 |
| T-16 | e2e | Automatic | console env | source-repo uv-pytest (`-m e2e`) | executed ✅ | 4 passed — redaction assertion on live secrets |
| T-17 | e2e | Automatic | console env | source-repo uv-pytest (`-m e2e`) | executed ✅ | 4 passed, live pentest01 |
| T-18 | e2e | Manual | console env | **run-helm-tests** (MCP-protocol / AI-agent) | **manual-substitution** | probe: direct `sb_*` regression walk (manual-e2e.md); NOT the planned protocol-level test — still owes a real run |
| T-19 | e2e | Manual | console env | **run-helm-tests** | **manual-substitution** | probe: direct `sb_*` discovery walk; NOT the planned test — still owes a real run |
| T-35 | e2e | Manual | console env | **run-helm-tests** | **manual-substitution** | probe: direct `sb_get_integrations` exploration; not protocol-level |
| T-36 | e2e | Manual | console env | **run-helm-tests** | **manual-substitution** | probe: direct `sb_get_installed_integrations` exploration; not protocol-level |
| T-37 | e2e | Manual | console env | **run-helm-tests** | **manual-substitution** | probe: direct redaction sweep over 20 types; not protocol-level |
| T-38 | e2e | Manual | console env | **run-helm-tests** | **manual-substitution** | probe: direct TI cross-check; not protocol-level |
| T-39 | e2e | Manual | console env | **run-helm-tests** | **manual-substitution** | probe: direct pagination walk; not protocol-level |

Ledgered = 39 = selected. No test dropped.

## Cumulative readiness
- Selected (Passes after ≤ 4, Active): T-1..T-39 (39)
- Green (executed with evidence): T-1..T-17 (32 tests)
- Manual-substitution (owe a real run): T-18, T-19, T-35, T-36, T-37, T-38, T-39 (7)
- BLOCKED / Unwritten-planned / Delegated: none
- **Phase verdict: INCOMPLETE** — the 7 Manual e2e were probed at the wrong seam (direct `sb_*` function
  calls), not executed via their planned runner. The planned runner is `run-helm-tests` (drive the tools
  through the MCP protocol / AI-agent chat on a **deployed** console), which is not provisioned in this
  working environment.

## Evidence
- T-1..T-13, T-20..T-34: executed — `uv run pytest safebreach_mcp_config/tests/{test_config_types,test_config_functions,test_config_server}.py -m "not e2e"` → **132 passed**.
- T-14..T-17: executed — `uv run pytest safebreach_mcp_config/tests/test_e2e_integrations.py -m e2e` → **4 passed**, live pentest01.

## Hand-off (delegated / BLOCKED)
- (none BLOCKED) — but see Manual substitutions: the planned Manual e2e require the MCP-protocol runner.

## To author (unwritten-planned)
- none — all planned tests are authored.

## Manual substitutions (not the planned test)
- T-18, T-19, T-35–T-39: **manual-substitution** — an informal probe (`scratchpad/manual_tests.py`, results
  in `manual-e2e.md`) called the `sb_*` functions directly against pentest01. This is the SAME seam as the
  Automatic e2e and does NOT exercise the MCP registration/protocol layer or a real MCP client. The planned
  test for each is a `run-helm-tests` run (AI-agent chat invoking the tools on a deployed pentest console);
  none of these ran. They still owe a real protocol-level run and are NOT counted green.

## Smell observations
- The test-plan routes the Automatic e2e (T-14..T-17) to repo uv-pytest, which calls `sb_*` directly — a
  live-integration seam, not the MCP protocol. Consider whether the plan should route at least one e2e per
  tool through `run-helm-tests` for genuine protocol-through-client coverage. (Plan-design note, not a run defect.)

## Verdict
- **INCOMPLETE** — 32/39 executed green; 7 Manual e2e are open manual-substitutions owing a real
  `run-helm-tests` run against a deployed pentest console (not provisionable in this working env).
