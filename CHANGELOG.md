# Changelog

All notable changes to the safebreach-mcp project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Paginated, filterable simulation logs via two new read-only data tools backed by the data v3
  `/simulationLogs` endpoint:
  - `get_paginated_simulation_logs` — fetch one simulation's logs incrementally and filtered by
    level/type/time/message, page by page. Use it only when the simulation object and steps
    (`get_simulation_details`) aren't enough; pull smartly by severity (errors first for failed
    simulations). `get_full_simulation_logs` remains for the full embedded blob / old-format sims.
  - `search_simulation_logs` — cross-simulation / fleet-wide log search (e.g. "every ERROR
    containing X in the last day"); pass a pipe-delimited `simulation_ids` list or omit it to
    search all simulations.
  - Filters: `min_level` (threshold) or explicit `levels`, `message_contains`, `start_time`/
    `end_time`, `log_type` (LOGS/OUTPUT/ALL), `sort_order`, and `node_id` (scope to a single
    simulator node — e.g. only the attacker or only the target node of a dual-script attack);
    offset pagination via `page`/`page_size` (max 1000) returning
    `{ logs, total, page, page_size, has_more }`. Results cached ~10 minutes.

### Changed

- `get_test_simulation_details` now returns the **raw simulation result** from the data v3 result
  endpoint (logs excluded): the full document including per-node simulation steps
  (`dataObj.data[..].details.SIMULATION_STEPS`) and the `logsEmbedded` hint, with the heavy
  LOGS/OUTPUT blobs stripped. This makes it the primary investigation entry point — inspect the
  result + steps first, and only escalate to `get_paginated_simulation_logs` when they aren't
  enough (or `get_full_simulation_logs` when `logsEmbedded=true`). Optional enrichments
  (MITRE techniques, basic attack logs, drift info) are merged on top of the raw result.
  Falls back to the list-API summary on older consoles without the v3 endpoint.
  **Breaking shape change:** the response is now the raw camelCase API document instead of the
  previous curated snake_case entity.
- `get_full_simulation_logs` now fetches via the data v3 result endpoint with `includeLogs=true`
  (falling back to v1 on older consoles) and exposes a new `logs_embedded` field: `true` means an
  old-format simulation whose logs exist only in the embedded blob (not in the logs index) — for
  those, use this tool rather than the paginated/search logs tools, which will return empty.

## 1.3.0 — 2026-05-21

### Added

- Ad-hoc attack execution via `run_adhoc_scenario` — run specific playbook attacks by ID with simulator targeting,
  dry-run preview, and per-attack override support

## 1.2.0 — 2026-05-18

### Added

- Delete historic test results via `manage_test` with storage impact preview — see how much space will be freed
  before committing
- See who launched each test with the new `launched_by` field in `get_tests` and `get_test_details`, plus filter
  test history by user
- Rate limiting for write operations to prevent accidental bulk actions
- Automated release preparation workflow via `/mcp-create-release`
- Test overview context in `get_studio_attack_latest_result` — see test status, duration, and simulation breakdown
  at a glance

### Changed

- `get_tests_history` renamed to `get_tests` — now also supports filtering for currently running tests
- Rate limiting is off by default and opt-in for deployments that need it
- `manage_test` lifecycle actions (pause, resume, cancel) now verify current state before acting, preventing
  conflicting operations

### Fixed

- Reduced false positive security alerts in CI scanning

## 1.1.0 — 2026-05-07

### Added

- Multi-server MCP architecture with domain-specific servers: Config (port 8000), Data (port 8001),
  Utilities (port 8002), Playbook (port 8003), Studio (port 8004)
- External connection support with Bearer token authentication and localhost bypass
- SSE and Streamable HTTP transport modes
- Playbook attack filtering by MITRE ATT&CK techniques/tactics and attacker/target platform
- Drift analysis tools: test-run-centric (`get_test_drifts`) and time-window-based
  (`get_simulation_result_drifts`, `get_simulation_status_drifts`)
- Scenario execution (`run_scenario`) with three-turn augmentation workflow, dry-run mode,
  step overrides, and constraint diagnostics
- Test lifecycle management (`manage_test`) for pause, resume, and cancel operations
- Per-user RBAC enforcement across all MCP servers
- Peer benchmark scoring (`get_peer_benchmark_score`) with industry comparison
- Full simulation log retrieval (`get_full_simulation_logs`) for forensic analysis
- Bounded TTL caching (`SafeBreachCache`) with per-type LRU eviction and background monitoring
- Pluggable secret provider interface (AWS SSM, AWS Secrets Manager, environment variables)
- Dynamic environment loading via `SAFEBREACH_ENVS_FILE` and `SAFEBREACH_LOCAL_ENV`
- Concurrent multi-server launcher (`start_all_servers.py`)
- Security scanning CI workflow (Gitleaks, TruffleHog, GitGuardian, detect-secrets)
