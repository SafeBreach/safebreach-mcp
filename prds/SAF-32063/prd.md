# PRD: HELM reports COMPLETED while a test is still correlating — SAF-32063

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | Surface the security-event correlation phase so HELM stops reporting still-correlating tests as COMPLETED |
| **JIRA** | SAF-32063 |
| **Task Type** | Bug |
| **Component** | `safebreach_mcp_data` (Data Server) |
| **Purpose** | When asked "is that test done?", HELM returns `Status: ✅ COMPLETED` while the test is still in "Waiting to correlate" / "Correlating security events". The MCP must reflect the true completion state. |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Implemented |
| **Last Updated** | 2026-06-29 |
| **Branch** | `feature/SAF-32063` |

## 2. Solution Description

### Root cause (confirmed against live pentest01 data)

A test summary's `status` flips to `COMPLETED` when **simulation execution** ends, but every test then runs an asynchronous **security-event log-correlation** phase whose progress is tracked only by `logProcessingCompletionPercentage`. The MCP relayed `status` and never read that field, so it reported `COMPLETED` while correlation was still pending.

Per the integrations team, `logProcessingCompletionPercentage` is the authoritative completion signal: it **always exists and always reaches `1` (100%) for every test, regardless of whether any connector / security-control integration is attached** — correlation simply runs with a delay. A test is fully done only when this field reaches `1`.

Evidence (raw `testsummaries`, all with `status=COMPLETED`, `isCompleted=True`):

| UI phase | `logProcessingCompletionPercentage` |
|----------|-------------------------------------|
| Waiting to correlate | `None` (not yet started) |
| Correlating security events | `0.72` |
| Completed | `1.0` |

The SafeBreach UI derives the phase from exactly this field (`ui-react .../HomePage/utils.tsx:percentageToTestPhase`).

### Chosen Solution

Derive a `test_phase` from `logProcessingCompletionPercentage` inside `get_reduced_test_summary_mapping` — the single transform both `get_tests` and `get_test_details` flow through — and expose it alongside the raw percentage. `status` is left untouched (existing `status_filter` and consumers depend on it). `get_test_details` emits a `hint_to_agent` instructing the agent not to report a still-correlating test as done.

Phase derivation (mirrors the UI), applied only when `status == 'completed'`:

| `logProcessingCompletionPercentage` | `test_phase` |
|-------------------------------------|--------------|
| `None` or `0` | `Waiting to correlate` |
| `0 < pct < 1` | `Correlating security events` |
| `1` | `Completed` |
| otherwise | `Invalid` |

Gating on `status == 'completed'` is intentional: `completed` is the only status value that is misleading. `running` / `paused` / `cancelled` / `failed` already read correctly, so no `test_phase` is added for them.

### Alternatives Considered

| Option | Why not chosen |
|--------|----------------|
| Use the `isCompleted` boolean | Disproved by live data — `isCompleted=True` during the correlation phase. |
| Overwrite the `status` field itself | Breaks `status_filter='completed'` and other consumers that rely on raw status. |
| Add an integration-config check (`isAnyDefinedIntegration` from the config service) to disambiguate `pct=None` | Made obsolete by the integrations team's confirmation that the field is universal and always reaches 1 — no integration check is needed, and it avoids a cross-domain call from the data server into config. |

## 3. Core Feature Components

- **`data_types.py`** — `_percentage_to_test_phase(pct)` helper; `get_reduced_test_summary_mapping` adds `test_phase` (always when completed) and `log_processing_completion_percentage` (when present).
- **`data_functions.py`** — `sb_get_test_details` emits a correlation-aware `hint_to_agent` when `test_phase` is `Waiting to correlate` / `Correlating security events`.
- **`data_server.py`** — `get_tests` and `get_test_details` tool descriptions document `test_phase` and state it is the authoritative completion signal.

## 4. API Endpoints and Integration

No new endpoints. Reads the existing `logProcessingCompletionPercentage` field already returned by `GET /api/data/v1/accounts/{account_id}/testsummaries`.

## 5. Tests

- `test_data_types.py::TestTestSummaryMapping` — correlating / waiting / completed / invalid / absent-percentage / non-completed-status cases.
- `test_data_functions.py::TestDataFunctions::test_sb_get_test_details_correlation_pending_hint` — verifies the hint steers the agent away from COMPLETED and surfaces progress.
- Updated `TestStorageHintForTerminalTests::test_terminal_test_has_delete_hint` to represent a fully-correlated test (`logProcessingCompletionPercentage: 1`).

## 6. Definition of Done

- `get_test_details` / `get_tests` expose `test_phase`; a completed-but-correlating test reports a non-`Completed` phase and a hint not to call it done. ✅
- `status` semantics unchanged. ✅
- Data-server suite green. ✅
