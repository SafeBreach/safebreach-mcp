# Changelog

All notable changes to the safebreach-mcp project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
