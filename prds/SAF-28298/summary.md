# SAF-28298: Implementation Summary

## Overview

Three performance and resiliency improvements for safebreach-mcp servers to deliver better in-console Agent results.

## Item 1: Drift Count Performance

**Problem:** `get_test_details(include_simulations_statistics=True)` fetches ALL simulations into memory just to count
drifted ones. A test with 10,000 simulations triggers 100 API calls and ~10MB+ buffered data for a single integer.

**Solution:**
- **Always inline `finalStatus` counts** (missed/stopped/prevented/reported/logged/no-result) in test details output —
  these come free from the test summary API with zero extra cost
- **Rename parameter** from `include_simulations_statistics` to `include_drift_count` (default `False`)
- **Stream page-by-page** when drift count requested — iterate simulation pages, count `is_drifted=True`, discard each
  page before fetching next. Memory: O(page_size) instead of O(all_simulations)

**Files:** `data_types.py`, `data_functions.py`, `data_server.py`, tests

## Item 2: Propagate Findings in Test Summary

**Problem:** Agents always call `get_test_findings_counts` after `get_test_details` for Propagate tests. The findings
data (`findingsCount`, `compromisedHosts`) is already in the test summary API response but gets dropped by the mapping.

**Solution:**
- For Propagate (ALM) tests (detected via `systemTags` containing "ALM"), extract `findingsCount` and
  `compromisedHosts` from the test summary API response
- Include these fields in `get_test_details` output, saving agents a separate API call

**Files:** `data_types.py`, tests

## Item 3: Per-Agent Concurrency Limiter

**Problem:** Tools buffer 100% of data before filtering (simulations, attacks). Multiple parallel tool invocations from
the same agent can cause excessive memory usage and API load.

**Solution:**
- **SSE connection-scoped semaphore** — each SSE connection gets a unique session ID via `contextvars`
- **ASGI middleware** checks the `ContextVar` and applies `asyncio.Semaphore(limit)` per session
- Default limit: 2, configurable via `SAFEBREACH_MCP_CONCURRENCY_LIMIT` env var
- When exceeded: HTTP 429 (Too Many Requests) with retry hint
- Automatic cleanup when SSE connection drops

**Files:** `safebreach_base.py`, tests

## Estimate

4 hours total (as per ticket).
