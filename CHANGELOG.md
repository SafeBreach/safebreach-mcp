# Changelog

All notable changes to the safebreach-mcp project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.2.0 — 2026-05-18

### Added

- Support for per-caller (user) rate limiting of non-readonly actions. Caps are applied on a rolling window
  with per tool counts and a total-tools counts. Rate limiting is disabled by default and configurable via env vars: SAFEBREACH_MCP_RATE_LIMIT_ENABLED, SAFEBREACH_MCP_ACTION_LIMIT, SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT, SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES.
- get_tests_history renamed to get_tests and supports fetching and filtering by `running` tests
- get_studio_attack_latest_result enriched with test-level context
- manage_test tool is idempotent in transitions from paused->paused, running->running and supports also `cancel` and `delete`

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
