# Codex Instructions

## GitHub

- Prefer the GitHub connector for reading PRs, comments, review threads, issues,
  and repository metadata.
- When creating pull requests through the GitHub connector, omit
  `maintainer_can_modify`. GitHub may reject that option for the connector
  identity with `must be a collaborator` even when the app has repository read
  and write permissions.
- If connector PR creation fails, use the authenticated local `gh` CLI as the
  fallback.
- For review follow-up, read unresolved PR review threads through the connector,
  patch locally, push commits, and reply to the relevant PR comments when useful.

## Local Data

- Do not commit EPUB files or local runtime data.
- Local EPUB test folders such as `Epub-Books/` are intentionally ignored.
- The EPUB source directory should remain configurable rather than hard-coded.

