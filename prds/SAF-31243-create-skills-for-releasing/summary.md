# Ticket Summary: SAF-31243

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp, sb-vsextension (reference)

---

## Current State
**Summary**: [safebreach-mcp] Create a repo-specific claude skills to automate the releases of the SafeBreach MCP
**Issues Identified**: Ticket lacks acceptance criteria, detailed workflow steps, and adaptation specifics for the MCP repo (vs the VS Code extension reference).

---

## Investigation Summary

### safebreach-mcp
- Version in `pyproject.toml` (line 3), semantic versioning, single source of truth
- CHANGELOG.md uses "Keep a Changelog" format: `## X.Y.Z — YYYY-MM-DD` (em-dash, no brackets)
- GitHub Actions (`release.yml`) auto-creates tag + GitHub Release when `pyproject.toml` changes on main — validates CHANGELOG entry first
- Git tags use bare semantic version (no "v" prefix), current: `1.1.0`
- Release branch convention: `release_X.Y.Z`
- Changes tracked via git commit history (not PRDs)
- PRs created via `gh` CLI on GitHub

### sb-vsextension (reference)
- Two skills: `vse-create-release` (11-step workflow) and `vse-complete-release` (8-step)
- Well-structured: validation gates, user confirmations, error handling tables, limitations
- Uses Bitbucket MCP, `npm version`, PRD-based changelog generation
- Pattern is proven and can be adapted for the MCP repo

---

## Problem Analysis

### Problem Description
The SafeBreach MCP release process is fully manual: version bumping, changelog authoring, branch creation, and PR submission are all done by hand. This introduces risk of inconsistent changelogs, forgotten version bumps, and wasted developer time.

### Impact Assessment
- **Developer productivity**: Each release requires ~15-20 min of manual steps
- **Quality**: Manual changelog writing risks missing changes or inconsistent formatting
- **Reliability**: Automated GitHub Actions depend on correct pyproject.toml + CHANGELOG.md format

### Risks & Edge Cases
- No commits since last tag — skill must detect and abort
- Dirty working tree — must offer stash/abort
- Release branch collision — must handle (reuse, suffix, abort)
- Existing changelog entry for target version — must detect
- Mixed commit message formats — changelog generation must handle with/without SAF tickets

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Create `/mcp-create-release` skill to automate release preparation

### Description

**Background**
The SafeBreach MCP repo currently requires manual release preparation: bumping the version in `pyproject.toml`, writing changelog entries from commit history, creating a release branch, and opening a PR. Once the PR is merged to main, GitHub Actions automatically validates the changelog, creates a git tag, and publishes a GitHub Release. A Claude Code skill should automate the preparation steps.

**Technical Context**
* Version source of truth: `pyproject.toml` line 3 (`version = "X.Y.Z"`)
* Changelog format: "Keep a Changelog" — `## X.Y.Z — YYYY-MM-DD` with Added/Changed/Fixed sections
* GitHub Actions `release.yml` triggers on pyproject.toml changes to main, validates changelog, creates tag + release
* Git tag format: bare semantic version (e.g., `1.1.0`, no "v" prefix)
* Release branch convention: `release_{version}` (e.g., `release_1.2.0`)
* Changes are identified from git commit history since the last tag (not PRDs)
* PRs are created via `gh pr create` on GitHub

**Skill Workflow** (`/mcp-create-release`)
1. Validate environment — read `pyproject.toml`, check git status is clean
2. Ask version bump type — minor or major (via AskUserQuestion)
3. Read current version from `pyproject.toml` and calculate next version
4. Create release branch: `release_{next_version}` from main
5. Bump version in `pyproject.toml` using Edit tool
6. Generate changelog entries from `git log {last_tag}..HEAD --oneline`
7. Present changelog draft to user for review/editing
8. Update `CHANGELOG.md` — insert new version section at top
9. Present full summary for approval
10. Commit: `git add pyproject.toml CHANGELOG.md && git commit`
11. Push and create GitHub PR via `gh pr create`

**Reference Implementation**
The VS Code extension release skills at `/Users/yossiattas/projects/rules/plugins/sb-vsextension/skills` provide the structural pattern to follow. Key adaptations:
* `pyproject.toml` + Edit tool instead of `package.json` + `npm version`
* GitHub `gh` CLI instead of Bitbucket MCP tools
* Git commit history instead of PRD-based changelog
* Single skill only — no "complete release" needed (GitHub Actions handles post-merge)

**Affected Areas**
* New skill: to be created under a skills directory (TBD — either repo-local or in the rules repo)
* Reads: `pyproject.toml`, `CHANGELOG.md`, git tags/log
* Modifies: `pyproject.toml`, `CHANGELOG.md`
* Creates: release branch, GitHub PR

### Acceptance Criteria

- [ ] Skill triggers on `/mcp-create-release` and related phrases ("create release", "prepare release", "version bump")
- [ ] Validates environment: confirms `pyproject.toml` exists and git working tree is clean
- [ ] Asks user to choose between minor and major version bump
- [ ] Correctly calculates next version (minor: 1.1.0 -> 1.2.0, major: 1.1.0 -> 2.0.0)
- [ ] Creates `release_{version}` branch from latest main
- [ ] Handles branch collision (branch already exists: reuse, suffix, or abort)
- [ ] Bumps version in `pyproject.toml`
- [ ] Generates changelog entries from git commit history since last tag
- [ ] Presents changelog draft to user for review before writing
- [ ] Updates `CHANGELOG.md` in correct format (`## X.Y.Z — YYYY-MM-DD` with Added/Changed/Fixed sections)
- [ ] Commits with descriptive message and Co-Authored-By trailer
- [ ] Pushes branch and creates GitHub PR via `gh pr create`
- [ ] Handles edge cases: no commits since last tag, dirty tree, no tags exist
- [ ] Includes comprehensive error handling table and limitations section
- [ ] Follows the structural pattern of the VS Code extension release skills

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
The SafeBreach MCP repo currently requires manual release preparation: bumping the version in `pyproject.toml`, writing changelog entries from commit history, creating a release branch, and opening a PR. Once the PR is merged to main, GitHub Actions automatically validates the changelog, creates a git tag, and publishes a GitHub Release. A Claude Code skill should automate the preparation steps.

### Technical Context
* Version source of truth: `pyproject.toml` line 3 (`version = "X.Y.Z"`)
* Changelog format: "Keep a Changelog" — `## X.Y.Z — YYYY-MM-DD` with Added/Changed/Fixed sections
* GitHub Actions `release.yml` triggers on pyproject.toml changes to main, validates changelog, creates tag + release
* Git tag format: bare semantic version (e.g., `1.1.0`, no "v" prefix)
* Release branch convention: `release_{version}` (e.g., `release_1.2.0`)
* Changes identified from git commit history since last tag (not PRDs)
* PRs created via `gh pr create` on GitHub

### Skill Workflow (`/mcp-create-release`)
1. Validate environment — read `pyproject.toml`, check git status is clean
2. Ask version bump type — minor or major (via AskUserQuestion)
3. Read current version from `pyproject.toml` and calculate next version
4. Create release branch: `release_{next_version}` from main
5. Bump version in `pyproject.toml` using Edit tool
6. Generate changelog entries from `git log {last_tag}..HEAD --oneline`
7. Present changelog draft to user for review/editing
8. Update `CHANGELOG.md` — insert new version section at top
9. Present full summary for approval
10. Commit: `git add pyproject.toml CHANGELOG.md && git commit`
11. Push and create GitHub PR via `gh pr create`

### Reference Implementation
The VS Code extension release skills at the rules repo (`sb-vsextension` plugin) provide the structural pattern. Key adaptations: `pyproject.toml` + Edit instead of `package.json` + `npm version`, GitHub `gh` CLI instead of Bitbucket MCP, git commit history instead of PRD-based changelog, single skill (no "complete release" — GitHub Actions handles post-merge).
```

**Acceptance Criteria:**
```markdown
* Skill triggers on `/mcp-create-release` and related phrases ("create release", "prepare release", "version bump")
* Validates environment: confirms `pyproject.toml` exists and git working tree is clean
* Asks user to choose between minor and major version bump
* Correctly calculates next version (minor: 1.1.0 -> 1.2.0, major: 1.1.0 -> 2.0.0)
* Creates `release_{version}` branch from latest main
* Handles branch collision (branch already exists: reuse, suffix, or abort)
* Bumps version in `pyproject.toml`
* Generates changelog entries from git commit history since last tag
* Presents changelog draft to user for review before writing
* Updates `CHANGELOG.md` in correct format (`## X.Y.Z — YYYY-MM-DD` with Added/Changed/Fixed sections)
* Commits with descriptive message and Co-Authored-By trailer
* Pushes branch and creates GitHub PR via `gh pr create`
* Handles edge cases: no commits since last tag, dirty tree, no tags exist
* Includes comprehensive error handling table and limitations section
* Follows the structural pattern of the VS Code extension release skills
```
