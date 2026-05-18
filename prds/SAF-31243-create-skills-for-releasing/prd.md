# PRD: /mcp-create-release Skill

**Ticket**: [SAF-31243](https://safebreach.atlassian.net/browse/SAF-31243)
**Status**: Complete
**Author**: Yossi Attas

## Problem Statement

The SafeBreach MCP release process is fully manual: version bumping in `pyproject.toml`,
changelog authoring, release branch creation, and PR submission are all done by hand. This
introduces risk of inconsistent changelogs, incorrect formatting, wrong branch naming, and
wasted developer time (~15-20 min per release).

## Solution

A repo-local Claude Code skill at `.claude/commands/mcp-create-release.md` that automates
the entire release preparation workflow. Only one skill is needed because GitHub Actions
(`release.yml`) automatically handles tagging and release creation after the PR merges to main.

## Technical Design

### Skill Location

`.claude/commands/mcp-create-release.md` — local to the safebreach-mcp repo. Activates as
`/mcp-create-release` when Claude Code runs in this repository.

### Workflow (11 Steps)

| Step | Action | Tool |
|------|--------|------|
| 1 | Validate environment (`pyproject.toml` exists, clean tree) | Read, Bash |
| 2 | Ask version bump type (minor/major) | AskUserQuestion |
| 3 | Parse current version, calculate next | Read |
| 4 | Create `release_{version}` branch from main | Bash |
| 5 | Bump version in `pyproject.toml` | Edit |
| 6 | Generate changelog from `git log` since last tag | Bash |
| 7 | Present changelog draft for user review | AskUserQuestion |
| 8 | Insert new section into `CHANGELOG.md` | Edit |
| 9 | Present batch summary for final approval | AskUserQuestion |
| 10 | Commit and push | Bash |
| 11 | Create GitHub PR via `gh pr create` | Bash |

### Key Design Decisions

1. **Single skill, no "complete release"** — GitHub Actions handles post-merge automatically
   (validates CHANGELOG, creates tag, creates GitHub Release).

2. **Git commit history for changelog** (not PRDs) — commits since last tag are categorized
   into Added/Changed/Fixed sections. SAF ticket prefixes and PR numbers are stripped for
   user-facing readability.

3. **Em-dash format** (`## X.Y.Z — YYYY-MM-DD`) — matches existing `CHANGELOG.md` convention.
   The skill includes explicit correct/wrong examples and reinforcement at the Edit step to
   prevent double-hyphen substitution.

4. **`git stash --include-untracked`** for dirty tree handling — plain `git stash` doesn't
   capture untracked files, which was caught during testing.

5. **Scope-constrained** — only modifies `pyproject.toml` and `CHANGELOG.md`. Does NOT touch
   `README.md`, `CLAUDE.md`, or any other files (unlike unconstrained baseline which modified
   4+ files).

6. **Branch naming**: `release_{version}` (underscore) per existing convention, with collision
   handling (reuse existing, suffix with `-v2`, or abort).

### Reference Implementation

Modeled after the VS Code extension release skills at
`/Users/yossiattas/projects/rules/plugins/sb-vsextension/skills`:
- `vse-create-release` — 11-step workflow with validation gates
- `vse-complete-release` — merge + publish workflow (not needed for MCP)

Key adaptations:
- `pyproject.toml` + Edit tool instead of `package.json` + `npm version`
- GitHub `gh` CLI instead of Bitbucket MCP tools
- Git commit history instead of PRD-based changelog generation

### Integration with Existing Infrastructure

- **GitHub Actions** (`release.yml`): Triggers on `pyproject.toml` changes to main.
  Validates CHANGELOG entry with `grep -q "^## $VERSION" CHANGELOG.md`, extracts
  release notes, creates annotated tag, creates GitHub Release.
- **Pre-commit hooks**: Gitleaks scan runs on commit. Workspace artifacts excluded
  via `.gitleaks.toml` allowlist.
- **Git tags**: Bare semantic version (e.g., `1.1.0`, no "v" prefix).

## Testing

Tested using the skill-creator evaluation framework across 2 iterations:

### Iteration 1 (80% pass rate)
- Found 2 bugs: em-dash rendered as double-hyphen in actual file, stash missing `--include-untracked`

### Iteration 2 (100% pass rate)
- Both bugs fixed and verified
- 21/21 assertions passed across 3 test cases (minor release, major release, dirty tree)

### Skill vs Baseline Comparison

| Metric | With Skill | Without Skill |
|--------|-----------|---------------|
| Pass rate | 100% | 43% |
| Mean tokens | 51k | 57k |
| Mean duration | 127s | 170s |

Baseline failures: wrong branch naming (`release/` vs `release_`), no `chore:` commit prefix,
SAF ticket refs in changelog, modified extra files (README, CLAUDE.md), non-standard changelog
sections ("Enhanced").

## Files Changed

| File | Change |
|------|--------|
| `.claude/commands/mcp-create-release.md` | New skill file (216 lines) |
| `.gitignore` | Exclude workspace + `.claude/settings.local.json` |
| `.gitleaks.toml` | Allowlist workspace path for false positive suppression |
| `prds/SAF-31243-create-skills-for-releasing/context.md` | Investigation context |
| `prds/SAF-31243-create-skills-for-releasing/summary.md` | Ticket summary |
| `prds/SAF-31243-create-skills-for-releasing/prd.md` | This document |
