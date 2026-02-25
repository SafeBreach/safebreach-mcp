# PRD: Add Missing `cachetools` Dependency to requirements.txt — SAF-28615

## 1. Overview

| Field | Value |
|-------|-------|
| **Task Type** | Bug fix |
| **Purpose** | Ensure all installation methods resolve cachetools correctly |
| **Target Consumer** | External open-source consumers and internal deployment pipelines |
| **Key Benefits** | Standalone `pip install -r requirements.txt` deployments work without ImportError |
| **Originating Request** | [SAF-28615](https://safebreach.atlassian.net/browse/SAF-28615) |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-02-25 |
| **Owner** | Yossi Attas |
| **Current Phase** | Complete |

## 2. Solution Description

### Chosen Solution

Add `cachetools==7.0.1` to `requirements.txt` in alphabetical order.

### Root Cause Analysis

The project maintains two dependency manifests:

| Manifest | `cachetools` present? | Used by |
|----------|----------------------|---------|
| `pyproject.toml` | `cachetools>=5.3.0` (added in SAF-28428) | `uv sync`, `uv tool install`, `pip install .` |
| `uv.lock` | `cachetools==7.0.1` (auto-resolved) | `uv sync` (lockfile) |
| `requirements.txt` | **Missing** (now fixed) | `pip install -r requirements.txt` |

**Why mcp-proxy was unaffected**: The mcp-proxy and all uv-based deployments install via `uv sync` or
`uv tool install`, which resolve dependencies from `pyproject.toml` -> `uv.lock`. Since `pyproject.toml`
correctly declared `cachetools>=5.3.0` since the SAF-28428 caching work, the dependency was always installed
in uv-managed environments.

**Who would be affected**: Only consumers installing via `pip install -r requirements.txt` directly, bypassing
`pyproject.toml`. Since safebreach-mcp is open source on GitHub, external users may use `requirements.txt` as
their installation method.

**Decision**: Keep `requirements.txt` as a parallel manifest since the MCP servers are open source and consumers
may use different installation methods.

### Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| Remove `requirements.txt` entirely | Eliminates sync drift risk | Breaks external consumers using `pip install -r` |
| Auto-generate from `uv pip compile` | Always in sync | Adds CI complexity; may include dev deps |
| **Manual addition (chosen)** | Simple, immediate fix | Requires discipline to keep in sync |

## 3. Core Feature Components

### Component: requirements.txt Update

- **Purpose**: Add missing `cachetools==7.0.1` entry to the manually-maintained requirements file
- **Key Features**:
  - Single-line addition between `botocore` and `certifi` (alphabetical order maintained)
  - Version pinned to 7.0.1 to match uv.lock resolution
  - No code changes required — pure dependency manifest fix

## 7. Definition of Done

- [x] `cachetools==7.0.1` added to `requirements.txt`
- [x] Alphabetical order maintained in requirements.txt
- [x] `uv sync` completes without errors
- [x] `cachetools` importable in uv environment (`import cachetools` succeeds)
- [x] No duplicate entries or version conflicts

## 8. Testing Strategy

### Verification Steps

1. **Dependency resolution**: `uv sync` completes without errors
2. **Import check**: `uv run python -c "import cachetools; print(cachetools.__version__)"` prints `7.0.1`
3. **No regression**: Existing test suite passes (`uv run pytest -m "not e2e"`)

No new unit tests required — this is a dependency manifest fix, not a code change.

## 9. Implementation Phases

### Phase Status Tracking

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Add cachetools to requirements.txt | ✅ Complete | 2026-02-25 | c9f88c7 | |

### Phase 1: Add cachetools to requirements.txt

- **Semantic Change**: Add missing `cachetools==7.0.1` dependency to requirements.txt
- **Deliverables**: Updated requirements.txt with cachetools entry
- **Implementation Details**:
  - Insert `cachetools==7.0.1` on line 6 of requirements.txt, between `botocore==1.39.12` and `certifi==2025.7.14`
  - Maintain alphabetical ordering convention
  - Run `uv sync` to verify no conflicts
  - Verify import succeeds in uv environment
- **Changes**:

| File | Action | Description |
|------|--------|-------------|
| `requirements.txt` | Modify | Add `cachetools==7.0.1` entry |

- **Test Plan**: `uv sync` + import verification + existing test suite
- **Git Commit**: `fix: add cachetools to requirements.txt for standalone deployment (SAF-28615)`

## 12. Executive Summary

- **Issue**: `cachetools` library was added to `pyproject.toml` during SAF-28428 caching work but was not added
  to `requirements.txt`, causing ImportError for consumers using `pip install -r requirements.txt`
- **What Was Built**: Added `cachetools==7.0.1` to `requirements.txt` in alphabetical order
- **Key Technical Decision**: Keep `requirements.txt` as a parallel manifest alongside `pyproject.toml` since the
  MCP servers are open source and external consumers may use different installation methods
- **Root Cause**: Two dependency manifests (`pyproject.toml` and `requirements.txt`) maintained independently;
  the mcp-proxy was unaffected because it uses `uv sync` which reads `pyproject.toml`
- **Business Value**: All installation paths now work correctly for open-source consumers
