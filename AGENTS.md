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

## Commits

- Prefer small, discrete commits organized by feature or bug fix.
- Do not bundle an entire roadmap milestone or phase milestone into one commit unless explicitly
  requested.
- When implementing multiple features in one session, commit each completed
  feature separately with a focused commit message.
- Keep unrelated refactors, formatting, generated assets, and test updates
  grouped only with the feature or fix they directly support.
- Before committing, review the staged diff to ensure it represents one coherent
  change.

## Local Data

- Do not commit EPUB files or local runtime data.
- Local EPUB test folders such as `Epub-Books/` are intentionally ignored.
- The EPUB source directory should remain configurable rather than hard-coded.
