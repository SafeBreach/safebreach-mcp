# SAF-28585: Concurrency rate limiter is not effective

## Ticket Information

- **ID**: SAF-28585
- **Title**: [safebreach-mcp] Concurrency rate limiter is not effective
- **Type**: Bug
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Reporter**: Yossi Attas
- **Priority**: Medium
- **Created**: Feb 24, 2026

**Link**: https://safebreach.atlassian.net/browse/SAF-28585

## Problem Statement

The per-session concurrency limiter (SAF-28298, Component C) is completely non-functional. Every POST /messages/ request
bypasses the semaphore check because `contextvars.ContextVar` does not propagate between separate HTTP requests.
The limiter never rejects any request, regardless of concurrent load.

**Root Cause**: ContextVars are per-async-task in Python. Each HTTP request handled by uvicorn runs as a separate asyncio
task with its own context copy. The ContextVar set during the SSE GET request is invisible to subsequent POST /messages/
request handlers — `_mcp_session_id.get()` always returns `None`.

**Evidence**: During pressure testing on staging (2026-02-24), 3 concurrent requests exceeded the limit of 2 at multiple
points across data and playbook servers. Zero HTTP 429 responses returned. Zero concurrency-related warning logs appeared.

**Why Unit Tests Passed**: Tests manually inject session IDs into `_session_semaphores` dict, bypassing the ContextVar
mechanism entirely. The 429 response logic works correctly in isolation — it's the session lookup via ContextVar that fails.

**Suggested Fix**: Parse `session_id` from the URL query string (already present in every POST /messages/ request)
instead of relying on ContextVar. Also need integration tests exercising real SSE→POST flow.

**Affected Code**:
- `safebreach_mcp_core/safebreach_base.py:38` — `_mcp_session_id` ContextVar definition
- `safebreach_mcp_core/safebreach_base.py:484-547` — `_create_concurrency_limited_app()` middleware
- `tests/test_concurrency_limiter.py` — Tests bypass ContextVar, don't catch the bug

**Impact**: High — no protection against agents firing many expensive tool calls simultaneously.

## Current Phase

Phase 3: Create Context File

## Investigation Scope

- Repository: /Users/yossiattas/Public/safebreach-mcp
- Focus Areas:
  1. Concurrency limiter middleware in `safebreach_base.py`
  2. ContextVar usage and SSE→POST session propagation
  3. How FastMCP assigns session IDs and passes them in query strings
  4. Existing unit tests in `test_concurrency_limiter.py`
  5. Semaphore creation, usage, and cleanup flow

## Investigation Findings

_To be populated after codebase exploration_

## Brainstorming Results

_To be populated after brainstorming session_

## Status

Phase 3: Create Context File ✅
