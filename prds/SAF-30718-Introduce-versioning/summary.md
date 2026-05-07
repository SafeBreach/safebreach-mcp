# Ticket Summary: SAF-30718

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp, mcp-proxy

---

## Current State
**Summary**: [safebreach-mcp] Create a versioning mechanism allowing consumers of the codebase to
explicitly sync to a particular version
**Issues Identified**: Ticket describes the problem well but lacks acceptance criteria, technical
details about current state, and specific implementation requirements.

---

## Investigation Summary

### safebreach-mcp
- Version `1.1.0` exists in `pyproject.toml` but no git tags — consumers cannot pin
- No CHANGELOG, no release CI/CD workflow, no tag automation
- Multi-package architecture (6 servers) sharing single version
- Uses setuptools build backend with auto-discovery
- README documents installation via unpinned git URLs only
- Relevant files: `pyproject.toml`, `.github/workflows/security-scan.yml`, `README.md`

### mcp-proxy
- `requirements.txt` line 5: completely unpinned `git+https://...safebreach-mcp.git`
- All other PyPI deps pinned to exact versions — safebreach-mcp is the outlier
- Dynamic imports via `__import__()` — low breaking risk from version changes
- Already tracks safebreach-mcp git commit hash at runtime (`src/simp/version_info.py`)
- Three Dockerfiles (dev/prod/integ) all install unpinned
- Relevant files: `requirements.txt`, `src/simp/version_info.py`, `src/simp/mcp_manager.py`

---

## Problem Analysis

### Problem Description
The safebreach-mcp repository has a static version string (`1.1.0`) in `pyproject.toml` but no
mechanism to expose it as a pinnable reference for downstream consumers. Without git tags, consumers
like mcp-proxy are forced to pull the latest `main` branch, resulting in non-deterministic builds.
Any commit to main can silently break downstream builds or introduce behavioral changes without notice.
This is especially problematic because all other dependencies in mcp-proxy's requirements.txt are
pinned to exact versions.

### Impact Assessment
- **Build reproducibility**: Same requirements.txt produces different installs depending on when
  `pip install` runs — breaks deterministic CI/CD
- **Debugging difficulty**: When issues arise, there's no easy way to identify which safebreach-mcp
  version is deployed (only runtime commit hash logging)
- **Rollback friction**: Cannot easily revert to a known-good version of safebreach-mcp
- **Test flakiness**: mcp-proxy integration tests can fail due to unrelated safebreach-mcp main changes

### Risks & Edge Cases
- **Multi-package consistency**: All 6 servers share one version — version bump must cover the whole repo
- **Consumer migration**: Existing consumers must update dependency specs when upgrading
- **Tag format convention**: Must choose and document (e.g., `v1.1.0` vs `1.1.0`)
- **Stale build artifacts**: `safebreach_mcp_server.egg-info/` caches old version metadata

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Introduce git tag versioning for deterministic consumer dependency pinning

### Description

**Background**

Consumers of safebreach-mcp (e.g., mcp-proxy) install the package via git URLs without version
pinning. While `pyproject.toml` declares version `1.1.0`, no git tags exist, so consumers cannot
reference a specific release. This causes non-deterministic builds and sync issues.

**Technical Context**

* `pyproject.toml` version field is already set to `1.1.0` (single source of truth)
* No git tags have ever been created on the repository
* No CHANGELOG or release workflow exists
* mcp-proxy's `requirements.txt` uses unpinned `git+https://...safebreach-mcp.git`
* All other mcp-proxy PyPI dependencies are pinned to exact versions
* mcp-proxy already has runtime commit hash tracking via `version_info.py`

**Problem Description**

* Builds are non-deterministic: same `requirements.txt` produces different installs over time
* No rollback mechanism to a known-good safebreach-mcp version
* Integration tests can flake due to unrelated main branch changes
* No structured way to communicate breaking changes to consumers

**Affected Areas**

* safebreach-mcp: `pyproject.toml`, git tags, CI workflows, `README.md`, new `CHANGELOG.md`
* mcp-proxy: `requirements.txt` (version pinning after tags are available)

### Acceptance Criteria

- [ ] Git tags following `vX.Y.Z` format (semver) are created for the current version (`v1.1.0`)
- [ ] `pyproject.toml` version remains the single source of truth
- [ ] CHANGELOG.md is created with at least the current version entry
- [ ] README.md installation instructions updated with version-pinned examples
      (e.g., `git+https://github.com/SafeBreach/safebreach-mcp.git@v1.1.0`)
- [ ] GitHub Actions workflow added to automate tag creation when version in pyproject.toml changes
      on main
- [ ] Consumers can install a specific version via `pip install git+...@v1.1.0`
- [ ] `.egg-info/` directory is added to `.gitignore` if not already

### Suggested Labels/Components
- Component: infrastructure
- Labels: versioning, developer-experience

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
Consumers of safebreach-mcp (e.g., mcp-proxy) install the package via git URLs without version
pinning. While pyproject.toml declares version 1.1.0, no git tags exist, so consumers cannot
reference a specific release. This causes non-deterministic builds and sync issues.

### Technical Context
* pyproject.toml version field is already set to 1.1.0 (single source of truth)
* No git tags have ever been created on the repository
* No CHANGELOG or release workflow exists
* mcp-proxy requirements.txt uses unpinned git+https://...safebreach-mcp.git
* All other mcp-proxy PyPI dependencies are pinned to exact versions

### Problem Description
* Builds are non-deterministic: same requirements.txt produces different installs over time
* No rollback mechanism to a known-good safebreach-mcp version
* Integration tests can flake due to unrelated main branch changes
* No structured way to communicate breaking changes to consumers

### Affected Areas
* safebreach-mcp: pyproject.toml, git tags, CI workflows, README.md, new CHANGELOG.md
* mcp-proxy: requirements.txt (version pinning after tags are available)
```

**Acceptance Criteria:**
```markdown
* Git tags following vX.Y.Z format (semver) created for current version (v1.1.0)
* pyproject.toml version remains the single source of truth
* CHANGELOG.md created with at least the current version entry
* README.md installation instructions updated with version-pinned examples
* GitHub Actions workflow added to automate tag creation on version change in main
* Consumers can install specific version via pip install git+...@v1.1.0
* .egg-info/ directory added to .gitignore if not already
```
