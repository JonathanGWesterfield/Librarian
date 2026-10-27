# Codex Instructions

## Active architecture roadmap

- At the start of every repository task, read
  [`docs/answer-delivery/README.md`](docs/answer-delivery/README.md) and the
  applicable Jira epic and task in the
  [LIB project](https://jgwesterfield.atlassian.net/browse/LIB-1).
  For answer delivery, chat, broker, gRPC, streaming, configuration, testing,
  or architecture work, also read the ADR, technical design, compatibility
  plan, and acceptance charter linked from that roadmap.
- The M00–M10 answer-delivery sequence is the active course. Do not start a
  later milestone before its documented exit conditions pass, and do not resume
  or reprioritize the higher-level README roadmap until this roadmap reaches its
  documented handoff or the user explicitly changes direction.
- Jira is the sole mutable task and milestone ledger. Before editing, read the
  selected Jira task and epic, then claim it there with owner,
  branch/worktree, exact reserved paths, coordination contact, validation
  evidence, review findings, and handoff. Keep technical decisions in the
  versioned design documents rather than duplicating them in Jira or pull
  requests.
- When changing a canonical answer-delivery source document, review every
  affected Jira task and update its anchors, scope, acceptance, dependencies,
  or handoff in Jira. There is no repository freshness manifest or local task
  lifecycle record.

## Coordination and milestone status

- Jira epics and tasks are authoritative for every branch and agent. Before
  starting work, read the roadmap for technical constraints and Jira for the
  current state; do not infer eligibility from a branch name, chat history, or
  an unmerged commit.
- Milestones are strictly sequential: do not start new work in a milestone
  until every ticket and epic in every preceding milestone is Done and their
  technical exit evidence is satisfied. Historical later-milestone
  implementation remains provenance only; it does not waive this gate. Jira
  dependency links and contributor discipline express this policy; no automatic
  Jira workflow validator is configured.
- When a PR changes completion, a blocker, or the next eligible work, update
  the relevant Jira task and epic. An unmerged implementation does not advance
  a milestone.

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
