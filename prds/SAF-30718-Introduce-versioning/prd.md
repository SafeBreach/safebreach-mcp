# Git Tag Versioning for safebreach-mcp — SAF-30718

## 1. Overview

- **Task Type**: Feature (infrastructure/developer tooling)
- **Purpose**: Enable consumers of safebreach-mcp to pin to explicit, stable versions instead of pulling the
  latest `main` branch. Eliminates non-deterministic builds, enables rollback, and provides a structured
  release communication channel.
- **Target Consumer**: Downstream consumers of safebreach-mcp (deployment engineers, integration teams)
- **Key Benefits**:
  - Deterministic builds: same dependency spec always produces the same installation
  - Rollback capability: consumers can revert to any prior tagged version
  - Release communication: CHANGELOG and GitHub Releases document what changed per version
- **Business Alignment**: Improves reliability and maintainability of the SafeBreach MCP integration layer,
  reducing sync-related outages and debugging time
- **Originating Request**: SAF-30718 — downstream consumers currently install unpinned `git+https://...`
  with no way to pin to a specific version

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-05-07 15:00 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution: Path-Filtered GitHub Actions Workflow

A lightweight GitHub Actions workflow that triggers only when `pyproject.toml` is modified on `main`.
It extracts the version string, verifies a matching CHANGELOG entry exists, then creates a git tag
(`X.Y.Z`) and a GitHub Release with the CHANGELOG excerpt as release notes.

**Key characteristics:**
- `pyproject.toml` version field remains the single source of truth
- Tags follow `X.Y.Z` semver format (e.g., `1.1.0`) — no `v` prefix, matching pyproject.toml directly
- CHANGELOG gate: workflow refuses to tag if CHANGELOG.md lacks an entry for the new version
- No external dependencies beyond standard GitHub Actions

### Alternatives Considered

| Approach | Description | Why Rejected |
|----------|-------------|--------------|
| **Version-Diff (every push)** | Runs on every push to main, compares version vs latest tag | Wastes CI minutes on non-version commits |
| **python-semantic-release** | Automated version bumps from conventional commits | Overkill; requires team-wide conventional commit adoption; removes manual version control |

### Decision Rationale
Path-filtered approach is simple, efficient (runs only when pyproject.toml changes), self-contained
(~50 lines YAML), and preserves manual control over when versions are bumped. It matches the team's
preference for explicit, readable, reliable versioning.

---

## 3. Core Feature Components

### Component A: GitHub Actions Release Workflow

- **Purpose**: New CI workflow (`.github/workflows/release.yml`) that automates git tag creation and
  GitHub Release publishing when the version in `pyproject.toml` changes on `main`
- **Key Features**:
  - Triggers on push to `main` with path filter on `pyproject.toml`
  - Extracts version from `pyproject.toml` using grep/sed
  - Checks if tag `{version}` already exists (idempotent — skips if tag present)
  - Validates CHANGELOG.md contains a `## {version}` heading (CHANGELOG gate)
  - Creates annotated git tag `{version}`
  - Creates GitHub Release with CHANGELOG excerpt between current and previous version headings
  - Uses `GITHUB_TOKEN` for authentication (no additional secrets required)

### Component B: CHANGELOG.md

- **Purpose**: New file tracking notable changes per version in Keep a Changelog format
- **Key Features**:
  - Initial entry for `1.1.0` documenting the current feature set
  - Structured sections: Added, Changed, Fixed (as applicable per version)
  - `## {version}` heading format matched by the release workflow CHANGELOG gate
  - Included in MANIFEST.in for distribution

### Component C: Documentation Updates

- **Purpose**: Update README.md and CLAUDE.md installation instructions to include version-pinned examples
- **Key Features**:
  - Add version-pinned install examples alongside existing unpinned URLs
  - Preserve existing unpinned URLs for users who want latest
  - Cover all 4 installation methods in README.md and 2 in CLAUDE.md

---

## 4. API Endpoints and Integration

*Omitted — no API changes involved.*

---

## 5. Example Customer Flow

*Omitted — backend/infrastructure change with no user-facing workflow.*

---

## 6. Non-Functional Requirements

### Technical Constraints

- **Backward Compatibility**: Existing unpinned git URLs continue to work (point to latest main). Version
  pinning is additive — consumers opt in by appending `@vX.Y.Z` to their dependency URL.
- **GitHub Actions Permissions**: The workflow needs `contents: write` permission to create tags and releases
  using `GITHUB_TOKEN`.
- **CHANGELOG Format**: Must use `## vX.Y.Z` heading format consistently so the workflow can parse and
  extract release notes programmatically.

---

## 7. Definition of Done

- [ ] `.github/workflows/release.yml` exists and is syntactically valid
- [ ] Workflow triggers only on pushes to `main` that modify `pyproject.toml`
- [ ] Workflow extracts version from `pyproject.toml` correctly
- [ ] Workflow skips gracefully if tag `{version}` already exists
- [ ] Workflow fails with clear error if CHANGELOG.md lacks `## {version}` entry
- [ ] Workflow creates annotated git tag `{version}` on success
- [ ] Workflow creates GitHub Release with CHANGELOG excerpt as body
- [ ] `CHANGELOG.md` exists with `## 1.1.0` entry
- [ ] `MANIFEST.in` includes `CHANGELOG.md`
- [ ] `README.md` shows version-pinned installation examples for all 4 methods
- [ ] `CLAUDE.md` shows version-pinned installation examples for both references
- [ ] Consumers can install via `pip install git+https://github.com/SafeBreach/safebreach-mcp.git@1.1.0`
- [ ] Initial `1.1.0` tag is created manually on `main` after PR merges

---

## 8. Testing Strategy

### Manual Verification

Since this feature is CI infrastructure + documentation, testing is primarily manual:

- **Workflow syntax**: Validate YAML with `actionlint` or GitHub's built-in workflow validator
- **Version extraction**: Test the grep/sed command locally against pyproject.toml
- **CHANGELOG parsing**: Test the sed/awk command that extracts release notes between version headings
- **Tag creation**: After merging, manually create `1.1.0` tag and verify GitHub Release
- **Consumer install**: Run `pip install git+https://github.com/SafeBreach/safebreach-mcp.git@1.1.0`
  from a clean environment to verify version pinning works

### Workflow Dry-Run

- Push a test branch with a modified pyproject.toml version to verify the workflow triggers
  (will not create tags since it only runs on `main`)
- Review workflow run logs for correct version extraction and CHANGELOG validation

### Coverage Gaps

- Full end-to-end workflow test requires merging to `main` — cannot be fully tested pre-merge
- GitHub Release body formatting can only be verified after first real release

---

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: CHANGELOG.md | ⏳ Pending | - | - | |
| Phase 2: Release Workflow | ⏳ Pending | - | - | |
| Phase 3: Documentation Updates | ⏳ Pending | - | - | |
| Phase 4: MANIFEST.in Update | ⏳ Pending | - | - | |
| Phase 5: Manual Tag Creation | ⏳ Pending | - | - | Post-merge |

### Phase 1: CHANGELOG.md

**Semantic Change**: Create initial changelog with 1.1.0 entry

**Deliverables**: `CHANGELOG.md` at repository root with first version entry

**Implementation Details**:
- Create `CHANGELOG.md` following Keep a Changelog conventions
- Include a top-level title and a brief description of the changelog purpose
- Add `## 1.1.0` heading with the current date (YYYY-MM-DD)
- Under 1.1.0, summarize the current state of the project as the baseline release:
  - Multi-server MCP architecture (Config, Data, Utilities, Playbook, Studio servers)
  - External connection support with Bearer token authentication
  - Playbook attack filtering (MITRE ATT&CK, platform)
  - Drift analysis tools (test-run-centric and time-window-based)
  - Scenario execution and management tools
  - Per-user RBAC enforcement
  - Peer benchmark scoring
  - Caching with bounded TTL and monitoring
- Use "Added" section since this is the initial release entry

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `CHANGELOG.md` | Create | Initial changelog with 1.1.0 entry |

**Git Commit**: `docs: add CHANGELOG.md with initial 1.1.0 entry`

---

### Phase 2: Release Workflow

**Semantic Change**: Add GitHub Actions workflow for automated tagging and releases

**Deliverables**: `.github/workflows/release.yml` — path-filtered workflow

**Implementation Details**:
- Create workflow file triggered on push to `main` with path filter `pyproject.toml`
- Job runs on `ubuntu-latest` with `contents: write` permission
- Step 1: Checkout repository with `actions/checkout@v4`
- Step 2: Extract version — read version field from `pyproject.toml` using grep to match the line
  `version = "X.Y.Z"` and extract only the version string. Store as a step output.
- Step 3: Check existing tag — use `git tag -l "v{version}"` to see if the tag already exists.
  If it does, set an output flag and skip remaining steps.
- Step 4: CHANGELOG gate — search `CHANGELOG.md` for a line matching `## {version}`. If not found,
  fail the workflow with a clear error message stating that a CHANGELOG entry is required.
- Step 5: Extract release notes — use sed/awk to extract the content between the `## {version}` heading
  and the next `## v` heading (or end of file). This becomes the GitHub Release body.
- Step 6: Create tag — use `git tag -a "v{version}" -m "Release v{version}"` followed by `git push origin "v{version}"`.
- Step 7: Create GitHub Release — use `gh release create "v{version}" --title "v{version}" --notes "{extracted notes}"`.
  The `gh` CLI is pre-installed on GitHub Actions runners and authenticates via `GITHUB_TOKEN`.
- Each step after the tag-exists check should use a conditional (`if` clause) to skip when tag already exists.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `.github/workflows/release.yml` | Create | Auto-tag and release workflow |

**Git Commit**: `ci: add release workflow for automated git tagging and GitHub Releases`

---

### Phase 3: Documentation Updates

**Semantic Change**: Add version-pinned installation examples to README.md and CLAUDE.md

**Deliverables**: Updated installation sections in both files with `@vX.Y.Z` examples

**Implementation Details**:
- **README.md** — For each of the 4 installation methods (lines 312, 329, 335, 339), add a version-pinned
  variant directly below the existing unpinned command. Format: show the unpinned URL first (labeled as
  "latest"), then the pinned URL with `@1.1.0` (labeled as "specific version"). Do not remove the
  unpinned URLs.
  - Option 1 SSH: add `git+ssh://git@github.com/SafeBreach/safebreach-mcp.git@1.1.0`
  - Option 2 HTTPS: add `git+https://github.com/SafeBreach/safebreach-mcp.git@1.1.0`
  - Option 3 pip: add `git+ssh://git@github.com/SafeBreach/safebreach-mcp.git@1.1.0`
  - Option 4 uv run: add `git+ssh://git@github.com/SafeBreach/safebreach-mcp.git@1.1.0`
- **CLAUDE.md** — Same pattern for the 2 git URLs (lines 86, 589). Add pinned variants below each.
- Add a brief note explaining the `@vX.Y.Z` syntax and where to find available versions
  (link to GitHub releases page or `git tag -l` command)

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `README.md` | Modify | Add version-pinned install examples (4 locations) |
| `CLAUDE.md` | Modify | Add version-pinned install examples (2 locations) |

**Git Commit**: `docs: add version-pinned installation examples to README and CLAUDE.md`

---

### Phase 4: MANIFEST.in Update

**Semantic Change**: Include CHANGELOG.md in package distribution

**Deliverables**: Updated MANIFEST.in with CHANGELOG.md entry

**Implementation Details**:
- Add `include CHANGELOG.md` line to `MANIFEST.in` alongside existing includes (README.md, CLAUDE.md, etc.)

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `MANIFEST.in` | Modify | Add `include CHANGELOG.md` |

**Git Commit**: `chore: include CHANGELOG.md in MANIFEST.in`

---

### Phase 5: Manual Tag Creation (Post-Merge)

**Semantic Change**: Create initial 1.1.0 tag on main after PR is merged

**Deliverables**: Git tag `1.1.0` on the merge commit + GitHub Release

**Implementation Details**:
- After the PR merges to main, checkout main and pull latest
- Create annotated tag: `git tag -a 1.1.0 -m "Release 1.1.0"`
- Push tag: `git push origin 1.1.0`
- Create GitHub Release manually or via `gh release create 1.1.0 --title "1.1.0" --notes-file -`
  piping the CHANGELOG 1.1.0 section as release notes
- Verify consumers can install: `pip install git+https://github.com/SafeBreach/safebreach-mcp.git@1.1.0`

**Changes**: None (git operations only, no file changes)

**Git Commit**: N/A (tag, not a commit)

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Version extraction regex breaks on pyproject.toml format change | Medium | Use simple, well-documented grep pattern; test in workflow |
| CHANGELOG parsing fails on edge-case formatting | Low | Document exact heading format required (`## vX.Y.Z`) |
| `GITHUB_TOKEN` permissions insufficient for tag/release creation | Medium | Explicitly set `permissions: contents: write` in workflow |
| Workflow runs but tag push fails due to branch protection | Medium | Verify branch protection allows tag creation via GitHub Actions |

### Assumptions

- `GITHUB_TOKEN` has sufficient permissions to create tags and releases on this repository
- The repository's branch protection rules do not block tag creation from GitHub Actions
- The `gh` CLI is available on `ubuntu-latest` runners (currently pre-installed)
- Consumers already know how to use `@tag` syntax with `pip install git+...` (standard pip feature)

---

## 11. Future Enhancements

- **PyPI publishing**: Publish safebreach-mcp to a private PyPI registry so consumers can use
  `pip install safebreach-mcp==1.1.0` without git URLs
- **Automated version bump PR**: GitHub Action that creates a PR to bump the version when triggered manually
- **Version compatibility matrix**: Document which safebreach-mcp versions are compatible with which
  consumer versions
- **Pre-release tags**: Support `1.2.0rc1` tags for release candidates (PEP 440 format)

---

## 12. Executive Summary

- **Issue/Feature Description**: safebreach-mcp lacks git tags and a release workflow, forcing consumers to
  depend on the unpinned latest `main` branch
- **What Will Be Built**: A GitHub Actions release workflow that auto-creates git tags and GitHub Releases
  when the version in pyproject.toml changes, plus a CHANGELOG and updated installation docs
- **Key Technical Decisions**: Path-filtered workflow (only runs when pyproject.toml changes); CHANGELOG gate
  enforces documentation; `X.Y.Z` tag format with pyproject.toml as single source of truth
- **Scope**: safebreach-mcp repository only; consumer-side pinning is out of scope
- **Business Value Delivered**: Deterministic builds, rollback capability, and structured release
  communication for all consumers of safebreach-mcp

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-07 15:00 | PRD created — initial draft |
| 2026-05-07 15:15 | Removed internal component references (mcp-proxy) to keep PRD public-safe |
| 2026-05-07 15:20 | Changed tag format from `vX.Y.Z` to `X.Y.Z` (no prefix) for PEP 440 alignment |
