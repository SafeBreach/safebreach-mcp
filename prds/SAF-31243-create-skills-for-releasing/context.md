# Ticket Context: SAF-31243

## Status
Phase 5: Problem Analysis Complete

## Mode
Improving

## Original Ticket (if improving)
- **Summary**: [safebreach-mcp] Create a repo-specific claude skills to automate the releases of the SafeBreach MCP
- **Description**: Create a `/mcp-create-release` skill that bumps version, generates changelog, creates branch/PR. Inspired by VS Code extension release skills.
- **Acceptance Criteria**: None specified
- **Status**: To Do

## Task Scope
Investigate the current release process, versioning, changelog format, GitHub Actions, and the reference VS Code extension skills to prepare a detailed ticket for building the `/mcp-create-release` skill.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp
- /Users/yossiattas/projects/rules/plugins/sb-vsextension/skills

## Investigation Findings

### safebreach-mcp (target repo)

**Version Management:**
- Version declared in `pyproject.toml` line 3: `version = "1.1.0"`
- Single source of truth, no dynamic versioning
- Semantic versioning (MAJOR.MINOR.PATCH)
- No `__version__.py` or other version files

**CHANGELOG.md Format:**
- "Keep a Changelog" standard
- Entry format: `## X.Y.Z — YYYY-MM-DD` (em-dash separator, no brackets)
- Sections: Added, Changed, Fixed (only include non-empty sections)
- Entry style: descriptive bullet points with feature names

**GitHub Actions (release.yml):**
- Triggers on push to `main` when `pyproject.toml` changes
- Extracts version from pyproject.toml
- Validates CHANGELOG entry exists for that version
- Creates annotated git tag (format: `X.Y.Z`, no "v" prefix)
- Creates GitHub Release with notes extracted from CHANGELOG
- Fully automated — no manual publish step needed

**Git Tags:**
- Current tag: `1.1.0`
- 6 commits since last tag on main
- Tag format: bare semantic version (no "v" prefix)

**Branch Conventions:**
- Feature: `SAF-XXXXX-description`
- Release: `release_X.Y.Z` (underscore separator)
- Existing release branch: `release_1.2.0`

**Change Identification:**
- No PRDs directory convention for changelog — changes identified from git commit history
- Commit format: `SAF-XXXXX: Description (#PR)` or plain descriptions
- 6 commits since 1.1.0 tag covering features and CI fixes

**PR Workflow:**
- GitHub-hosted (not Bitbucket)
- No PR template defined
- PRs use `gh` CLI for creation

### sb-vsextension reference skills

**Two-Skill Pattern:**
1. `vse-create-release` — prepare release (bump, changelog, branch, PR)
2. `vse-complete-release` — merge PR, package, publish to marketplace

**Key Patterns Identified:**
- 11-step workflow with validation gates and user confirmations
- Environment validation first (check config file, git status)
- Version bump type choice (minor/major) via AskUserQuestion
- Last version marker found via `git log --grep="chore: bump version to"`
- PRD-based changelog generation (scans `prds/` directory)
- Batch summary + approval before commit
- Branch collision handling (use existing, suffix, abort)
- HEREDOC commit messages with Co-Authored-By trailer
- Comprehensive error handling table
- Clear limitations section (will/won't)

**Differences from MCP repo:**
| Aspect | VS Code Extension | SafeBreach MCP |
|--------|------------------|----------------|
| Version file | package.json | pyproject.toml |
| Bump tool | `npm version` | Manual edit |
| Source control | Bitbucket | GitHub |
| PR tool | Bitbucket MCP | `gh` CLI |
| Changelog source | PRD files | Git commit history |
| Changelog format | `## [X.Y.Z] - YYYY-MM-DD` | `## X.Y.Z — YYYY-MM-DD` |
| Release branch | `marketplace-release-version-X.Y.Z` | `release_X.Y.Z` |
| Publish step | Manual (vsce publish) | Automated (GitHub Actions) |
| Skills needed | 2 (create + complete) | 1 (create only) |

## Problem Analysis

**Core Problem**: The SafeBreach MCP release process is manual — version bumping, changelog writing, branch creation, and PR creation are all done by hand. This is error-prone and slow.

**Solution**: A single `/mcp-create-release` skill that automates the entire preparation flow. Only one skill is needed because GitHub Actions handles tagging and release creation automatically when pyproject.toml changes land on main.

**Key Design Decisions:**
1. Use `Edit` tool for pyproject.toml version bump (no npm equivalent)
2. Use `gh pr create` via Bash for GitHub PR creation
3. Generate changelog from git commit history since last tag (not PRDs)
4. Follow VS Code extension skill structure for consistency
5. Single skill — no "complete release" needed
