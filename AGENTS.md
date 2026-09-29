# Codex Instructions

## Active architecture roadmap

- At the start of every repository task, read
  [`docs/answer-delivery/README.md`](docs/answer-delivery/README.md).
  For answer delivery, chat, broker, gRPC, streaming, configuration, testing,
  or architecture work, also read the ADR, technical design, compatibility
  plan, and acceptance charter linked from that roadmap.
- The M00–M10 answer-delivery sequence is the active course. Do not start a
  later milestone before its documented exit conditions pass, and do not resume
  or reprioritize the higher-level README roadmap until this roadmap reaches its
  documented handoff or the user explicitly changes direction.
- Treat issue #87 as the progress ledger after the roadmap documentation is
  published. Keep technical decisions in the versioned documents rather than
  duplicating them in issues or pull requests.

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

## Developement

- Prefer code reuse and DRY principles
- More code is more things to break. Opt for less code when possible
- For each new FastAPI endpoint added, the api-endpoints.md file must also be updated to contain user info for each endpoint including descriptions of request and response as well as examples

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
- For each commit, the link to the PR must be included in the commit message

## Local Data

- Do not commit EPUB files or local runtime data.
- Local EPUB test folders such as `Epub-Books/` are intentionally ignored.
- The EPUB source directory should remain configurable rather than hard-coded.
