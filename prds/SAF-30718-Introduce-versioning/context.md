# Ticket Context: SAF-30718

## Status
Phase 6: PRD Created (planning-dev-task)

## Mode
Improving

## Original Ticket
- **Summary**: [safebreach-mcp] Create a versioning mechanism allowing consumers of the codebase to explicitly sync to a particular version
- **Description**: Currently the consumers (like mcp-proxy) of the safebreach-mcp repository on public GitHub simply clone and sync to the latest main branch. This is causing many sync problems. We want to introduce official versioning to the safebreach-mcp repo to allow consumers to pin to a specific version (e.g., `git+https://github.com/SafeBreach/safebreach-mcp.git@version_1.1`). The mechanism should be explicit, readable, reliable, and easy to set on the repo.
- **Acceptance Criteria**: Not yet defined
- **Status**: To Do

## Task Scope
1. Versioning mechanism: git tags, pyproject.toml version, changelog, CI considerations
2. Consumer impact analysis: how mcp-proxy and deployment scripts currently depend on this repo

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp
- /Users/yossiattas/projects/mcp-proxy

## Investigation Findings

### safebreach-mcp

- **Version defined**: `version = "1.1.0"` in `pyproject.toml` (line 3) — single source of truth
- **No git tags**: `git tag -l` returns empty — no tags have ever been created
- **No CHANGELOG**: No CHANGELOG.md, RELEASES, or HISTORY file exists
- **No `__version__`**: No runtime version attributes in any package `__init__.py`
- **Build system**: setuptools (`pyproject.toml` lines 56-58), auto-discovery for `safebreach_mcp_*` packages
- **6 entry points**: config-server, data-server, utilities-server, playbook-server, studio-server, all-servers
- **CI/CD**: Only `.github/workflows/security-scan.yml` (Gitleaks/TruffleHog). No release, publish, or tag workflows
- **Pre-commit**: Only secret detection (gitleaks). No version management hooks
- **Lock files**: `uv.lock` and `requirements.txt` exist for reproducibility
- **README**: Documents version 1.1.0 and installation via git URLs (no version pinning examples)
- **Installation docs**: All methods use unpinned git URLs (`git+ssh://...safebreach-mcp.git`)

### mcp-proxy

- **Dependency**: `requirements.txt` line 5: `git+https://github.com/SafeBreach/safebreach-mcp.git` — completely unpinned
- **History**: Was temporarily pinned to `streamable-http` branch, then moved back to unpinned main
- **Not in setup.py**: safebreach-mcp is only in requirements.txt, not `install_requires`
- **Dynamic imports**: mcp-proxy uses string-based `__import__()` for all 5 MCP server classes — no compile-time checks
- **Runtime version tracking**: `src/simp/version_info.py` reads git commit hash from `direct_url.json` metadata at startup
- **Three Dockerfiles**: dev, prod, integ — all install via `pip install -r requirements.txt`, all unpinned
- **Jenkins CI**: `integrationPipeline()` with `prepareSshDeps()`. No version override build parameters
- **Other unpinned deps**: moves-runner and python-common (SSH git URLs) are also unpinned
- **PyPI deps pinned**: fastapi==0.115.12, uvicorn==0.34.0, httpx==0.28.1 — explicit version pinning
- **No lock files**: No uv.lock, poetry.lock, or requirements.lock in mcp-proxy

## Problem Analysis

### Problem Scope
The safebreach-mcp repo has a version string (`1.1.0`) in pyproject.toml but no mechanism to make it
accessible to consumers. No git tags, no release workflow, no changelog exist. Consumers like mcp-proxy
pull latest `main`, creating non-deterministic builds where any commit can break downstream without notice.

### Affected Areas
- **safebreach-mcp**: pyproject.toml, git tags, CI workflows, README/docs, CHANGELOG
- **mcp-proxy**: requirements.txt (pinning), potentially Jenkinsfile (version override)
- **Other consumers**: Deployment scripts, `uv tool install` commands in CLAUDE.md

### Risks & Edge Cases
- Multi-package consistency: all 6 servers share one version — bump must cover whole repo
- Consumer adoption: existing consumers must update dependency specs on upgrade
- Tag format choice: need convention (e.g., `v1.1.0`) and adherence
- Stale egg-info: cached version in `safebreach_mcp_server.egg-info/` could cause confusion

### Dependencies
- No external blockers — internal tooling decision
- mcp-proxy changes can be coordinated after tags are published

## Clarified Requirements (Phase 2)
- **Tag strategy**: Auto-tag on version change in pyproject.toml when merged to main
- **GitHub Releases**: Create GitHub Release objects with CHANGELOG entry as release notes
- **CHANGELOG scope**: Start fresh with v1.1.0 only (no retroactive history)
- **Tag format**: `X.Y.Z` (semver, no `v` prefix — matches pyproject.toml directly, PEP 440 aligned)
- **Source of truth**: pyproject.toml version field remains canonical

## Implementation-Specific Findings (Phase 4)

### Files Requiring Changes
- **pyproject.toml** (line 3): `version = "1.1.0"` — source of truth, no change needed
- **README.md**: 4 unpinned git URLs at lines 312, 329, 335, 339 — add version-pinned examples
- **CLAUDE.md**: 2 unpinned git URLs at lines 86, 589 — add version-pinned examples
- **New file**: `.github/workflows/release.yml` — auto-tag + GitHub Release workflow
- **New file**: `CHANGELOG.md` — initial entry for v1.1.0
- **MANIFEST.in**: May need to include CHANGELOG.md

### No Changes Needed
- `.gitignore`: Already has `*.egg-info/` (line 24)
- `safebreach_mcp_server.egg-info/`: Not tracked in git (confirmed via `git ls-files`)
- Build system: setuptools with pyproject.toml — standard, works well
- Pre-commit hooks: No version-related hooks needed

### CI Workflow Style Reference
- Existing workflow: `.github/workflows/security-scan.yml` (45 lines)
- Triggers on push/PR to main and develop
- Single-job structure, ubuntu-latest, consistent YAML formatting
- Uses `${{ secrets.X }}` pattern for sensitive values

### Version References in Codebase
- `pyproject.toml` line 3: canonical source
- `PKG-INFO` (generated): auto-derived from pyproject.toml
- README.md: mentions version 1.1.0 in multiple places
- TEMPLATE_VERSION in studio_templates.py: separate constant "1.0.0" (not package version)

## Brainstorming Results (Phase 5)

### Chosen Approach: Path-Filtered Workflow (Approach B)
- Triggers on push to main, filtered by `paths: ['pyproject.toml']`
- Extracts version from pyproject.toml, checks if tag `v{version}` exists
- Verifies CHANGELOG.md has entry for new version (gate)
- Creates git tag + GitHub Release with CHANGELOG excerpt as release notes
- Simple, self-contained, no external dependencies

### Rejected Alternatives
- **Approach A (Version-Diff)**: Runs on every push — wasteful CI minutes
- **Approach C (Semantic Release)**: Overkill, requires conventional commit adoption

### Additional Decisions
- CHANGELOG gate: workflow validates CHANGELOG has `## v{version}` section before tagging
- Initial v1.1.0 tag: created manually after PR merges (not by workflow)

## Proposed Improvements
(Phase 6)
