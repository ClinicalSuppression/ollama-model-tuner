# Agent Guidelines & Workflow Rules

## 1. Commits and Releases
- Make focused, reviewable commits after appropriate verification; avoid committing unrelated user changes.
- Push verified work directly to the default branch by default. Use a feature branch or pull request when requested or when separate review is warranted.
- Reserve version tags and GitHub releases for major, stable release milestones.

## 2. Standardized Release Assets
Every major stable release must include:
- Source Zip: A normalized source archive (`<repo-name>-vX.Y.Z-src.zip`).
- Terminal Installation Instructions: Clear instructions in `README.md` for terminal/CLI installation (e.g., `git clone`).
- Executables (`.exe`): Include both portable package and/or installer candidate when applicable.

## 3. Emoji Usage
Do not add emojis to text you create, including documentation, code comments, commit messages, and user-facing copy, unless an emoji is structurally necessary or genuinely helpful. When editing existing text, remove emojis unless they meet that exception. Apply this rule in every repository and in GitHub content.

## 4. Source of Truth
- The working copy in `%USERPROFILE%\.config\opencode\` is what OpenCode runs.
  This repository mirrors it.
- When changing `commands/`, `skills/`, or `scripts/`, update both locations so
  the repo and the live config stay identical.