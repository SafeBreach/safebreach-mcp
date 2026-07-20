---
name: mcp-create-release
description: >-
  Prepare a release candidate for the SafeBreach MCP servers.
  Bumps version in pyproject.toml, generates changelog from git history, and creates a GitHub PR.
  Use when "create release", "prepare release", "version bump", or "new MCP release".
---

# Create MCP Release

Prepare a release candidate for the SafeBreach MCP servers.
Bumps version in `pyproject.toml`, generates changelog from git history, and creates a GitHub PR.

## Step 1: Validate Environment

1. Read `pyproject.toml` in the repo root — confirm it contains `name = "safebreach-mcp-server"`.
   If not found, halt: "This command must be run from the safebreach-mcp repository root."
2. Check working tree is clean:
   ```bash
   git status --porcelain
   ```
   If dirty, present options via AskUserQuestion:
   - "Stash changes" — run `git stash push --include-untracked -m "pre-release stash"` then continue
     (the `--include-untracked` flag is required to capture new/untracked files, not just modified ones)
   - "Abort" — stop the workflow

## Step 2: Ask Version Bump Type

Present the choice via AskUserQuestion:

- **Minor** — increment minor version, reset patch (e.g., 1.1.0 → 1.2.0)
- **Major** — increment major version, reset minor and patch (e.g., 1.1.0 → 2.0.0)

## Step 3: Determine Current Version and Calculate Next

1. Read `pyproject.toml` and extract the `version` field from line 3
   (format: `version = "X.Y.Z"`)
2. Parse into major, minor, patch integers
3. Apply the bump:
   - Minor: increment minor, set patch to 0
   - Major: increment major, set minor and patch to 0
4. Display: `Version: {current} → {next}`

## Step 4: Create Release Branch

1. Ensure on main with latest:
   ```bash
   git checkout main && git pull origin main
   ```
2. Construct branch name: `release_{next_version}` (e.g., `release_1.2.0`)
3. Check if branch already exists:
   ```bash
   git branch -a --list "*release_{next_version}*"
   ```
4. If it exists, ask the user via AskUserQuestion:
   - "Use existing branch" — checkout the existing branch
   - "Create with suffix" — use `release_{next_version}-v2`
   - "Abort" — stop the workflow
5. Create and checkout: `git checkout -b {branch_name}`

## Step 5: Bump Version

Use the Edit tool to update `pyproject.toml` line 3, changing the old version string to the new one:
```
version = "{current}" → version = "{next}"
```

Read back `pyproject.toml` to verify the change took effect.

Then regenerate the lock file to reflect the new version:
```bash
uv lock
```

## Step 6: Generate Changelog Entries

1. Find the most recent tag:
   ```bash
   git describe --tags --abbrev=0
   ```
   If no tags exist, use the initial commit:
   ```bash
   git rev-list --max-parents=0 HEAD
   ```
2. List commits since that tag:
   ```bash
   git log {last_tag}..HEAD --oneline --no-merges
   ```
3. If no commits found, halt: "No changes since last release tag. Nothing to release."
4. Categorize each commit into changelog sections:
   - **Added** — new features, new tools, new capabilities
   - **Changed** — modifications to existing behavior, renames, config changes
   - **Fixed** — bug fixes, corrections
   Use the commit message prefix and content to decide the category.
   Strip SAF ticket prefixes and PR numbers from the entry text — keep just the
   meaningful description. Write each entry as a concise, user-facing summary
   (not a raw commit message).
5. Format the new changelog section. The date separator MUST be an em-dash character (`—`,
   Unicode U+2014), not a double hyphen (`--`). This is critical — the existing CHANGELOG.md
   uses em-dash and the format must be consistent. Here is the exact template:
   ```
   ## {next_version} — {YYYY-MM-DD}

   ### Added

   - Entry one
   - Entry two

   ### Changed

   - Entry three

   ### Fixed

   - Entry four
   ```
   Only include sections that have entries. Use today's date.
   
   **Example of CORRECT format**: `## 1.2.0 — 2026-05-18` (with em-dash `—`)
   **Example of WRONG format**: `## 1.2.0 -- 2026-05-18` (with double hyphen `--`)

## Step 7: Present Changelog Draft

Show the user the generated changelog section and ask via AskUserQuestion:

- "Approve" — proceed as-is
- "Edit" — let user provide corrections (apply them and re-present)
- "Abort" — clean up branch and stop

This is the most important review gate — the changelog is what appears in the
GitHub Release and is the public-facing record of what changed.

## Step 8: Update CHANGELOG.md

Use the Edit tool to insert the new version section into `CHANGELOG.md`, immediately
after the header block (after the line starting with `and this project adheres to`)
and before the first existing `## ` version entry.

The insertion point is between the header paragraph and the first `## X.Y.Z` line.
Add a blank line before and after the new section.

**Critical**: When writing the Edit, copy the changelog section exactly as formatted in
Step 6 — including the em-dash (`—`) character. Do NOT substitute `--` for `—`.
The existing entry reads `## 1.1.0 — 2026-05-07` and the new one must match that style.

## Step 9: Present Batch Summary

Display a summary of everything that will be committed:

- Version bump: `{current}` → `{next}`
- Branch: `{branch_name}`
- Files modified: `pyproject.toml`, `uv.lock`, `CHANGELOG.md`
- Changelog entries: (list them)

Ask for final approval via AskUserQuestion:
- "Approve and commit" — proceed to commit
- "Abort" — clean up (checkout main, delete branch)

## Step 10: Commit and Push

1. Stage the modified files:
   ```bash
   git add pyproject.toml uv.lock CHANGELOG.md
   ```
2. Commit with HEREDOC:
   ```bash
   git commit -m "$(cat <<'EOF'
   chore: bump version to {next_version} and update changelog

   Co-Authored-By: Claude <noreply@anthropic.com>
   EOF
   )"
   ```
3. Push with upstream:
   ```bash
   git push -u origin {branch_name}
   ```

## Step 11: Create GitHub PR

1. Create PR via `gh` CLI:
   ```bash
   gh pr create \
     --title "Release {next_version}" \
     --body "$(cat <<'EOF'
   ## Release {next_version}

   {changelog section from Step 6}

   ---
   Once this PR is merged to main, GitHub Actions will automatically:
   1. Validate the CHANGELOG entry
   2. Create git tag `{next_version}`
   3. Create a GitHub Release with the changelog notes
   EOF
   )" \
     --base main \
     --head {branch_name}
   ```
2. Report the PR URL to the user
3. Remind: "Once the PR is approved and merged, GitHub Actions will automatically
   create the tag and GitHub Release."

## Error Handling

| Error | Action |
|-------|--------|
| Not safebreach-mcp repo | Halt with clear message |
| Dirty working tree | Offer stash or abort |
| Branch already exists | Offer use existing, suffix, or abort |
| No tags found | Fall back to initial commit for changelog range |
| No commits since last tag | Halt — nothing to release |
| Version parse fails | Halt with error details |
| `gh` CLI not available | Halt: "Install GitHub CLI: `brew install gh`" |
| PR creation fails | Display error, suggest manual `gh pr create` |
| Git push fails | Display error, do not force push |

## Limitations

**Will:**
- Bump version in `pyproject.toml`
- Generate changelog from git commit history
- Create release branch, commit, push, and open PR

**Will Not:**
- Merge the PR (user must review and approve)
- Create git tags or GitHub Releases (GitHub Actions handles this automatically)
- Handle pre-release or patch versions
- Modify files beyond `pyproject.toml`, `uv.lock`, and `CHANGELOG.md`
