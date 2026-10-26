# Answer-delivery task ledger

This is the highly discoverable, file-backed work queue for the active
[answer-delivery roadmap](../../answer-delivery/README.md). Start here after reading the roadmap
and its linked [ADR](../../answer-delivery/adr-internal-rpc-transport.md), [technical design](../../answer-delivery/technical-design.md),
[compatibility plan](../../answer-delivery/compatibility-and-migration.md), and [acceptance charter](../../answer-delivery/acceptance.md).

**Authoritative milestone state remains the [roadmap](../../answer-delivery/README.md#milestones) and
[issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87).** A task
record coordinates a slice; it does not by itself mark a milestone complete or
make a release ready.

## How to read a task

Every task has two anchor layers. **Read first** keeps the program outcome and
component boundaries in view. **Direct requirements for this task** links only
the design, ADR, compatibility, and acceptance clauses that constrain that
slice. Read both before claiming work; an exact anchor narrows the task, but
never overrides the program-wide design.

## Freshness gate

[`freshness.json`](freshness.json) records the canonical source documents and
the task IDs reviewed against their exact content. When a roadmap, technical
design, ADR, compatibility plan, or acceptance charter changes, identify every
affected task and update its direct anchors, scope, acceptance criteria, or
handoff in the same PR. Then refresh the record with a named reviewer, the
affected task IDs, and a concise decision note:

```sh
python3 scripts/check_task_ledger.py --refresh \
  --reviewed-by <person-or-agent> \
  --task-id AD-M03-02 \
  --note "Reviewed the chat migration task after the compatibility change."
```

`scripts/check.sh` and CI run `scripts/check_task_ledger.py`. They fail if a
canonical source digest, local design anchor, lifecycle, or required task
section drifts. Refreshing a hash is an attestation that the listed task files
were reviewed; it never replaces the task-file update or its append-only note.

## Find work

| Milestone | Deliverable | Task files |
| --- | --- | --- |
| [M00](./M00/) | Design publication and approval | 1 |
| [M01](./M01/) | Contracts, toolchain, inventory, and fixtures | 13 |
| [M02](./M02/) | In-process answer-runtime extraction and parity | 3 |
| [M03](./M03/) | Atomic gRPC Codex-broker migration | 18 |
| [M04](./M04/) | Buffered JSON and progressive SSE delivery adapters | 4 |
| [M05](./M05/) | Configuration, capabilities, and feature off-switch | 3 |
| [M06](./M06/) | Web reducer and truthful progress UI | 4 |
| [M07](./M07/) | Compatibility, failure, Chrome UAT, and independent review | 5 |
| [M08](./M08/) | Measured broker optimization | 5 |
| [M09](./M09/) | Separate answer-runtime deployment decision | 2 |
| [M10](./M10/) | Controlled rollout and operational handoff | 4 |

Use `rg -n "Lifecycle status: \*\*planned\*\*" docs/tasks/answer-delivery` to
find available work. `blocked` records name the prerequisite; completed
historical records preserve only documented provenance and do not invent test
evidence.

## Contributor protocol

1. **Orient.** Read `docs/answer-delivery/README.md`, its linked design set, this
   index, the milestone index, and the selected task. Check issue #87 and the
   working tree before claiming anything.
2. **Claim atomically.** Edit only the selected task’s **Ownership / claim
   record** with agent/person, branch/worktree, date, intended files, and a
   coordination contact. Change `planned` to `claimed`, then to `in progress`
   when edits begin. Do not claim a task whose reserved surface is actively
   owned without written coordination in both task files.
3. **Work in scope.** Keep implementation, test commands/results, PR/SHA,
   redacted report locations, decisions, and reviewer findings in the task’s
   **Append-only log, artifacts, and notes**. Preserve local data, secrets, and EPUB text outside
   Git and task records.
4. **Coordinate dependencies.** A task may be implemented in parallel only when
   its prerequisites do not require an unfinished behavior. Record whether a
   dependency gates implementation or only acceptance/release. Explicitly
   synchronous/release-gate tasks say so in their reservation sections.
5. **Review and close.** Move `in progress` to `in review` with the PR and
   evidence. Only a merged, reviewed slice with its stated evidence becomes
   `complete`. Update the roadmap milestone table and issue #87 in that PR if
   the slice changes completion, blocker, or next eligible work. Task completion
   never advances milestone status by itself.
6. **Stale claims.** A claim with no recorded update for five calendar days is
   stale. Ask the recorded coordinator to renew or release it; if unavailable,
   record the takeover decision and timestamp in **Append-only log, artifacts, and notes** before
   changing ownership. Never silently overwrite an active claim.

## Lifecycle vocabulary

| Status | Meaning |
| --- | --- |
| `planned` | Available; no worktree or owner has reserved it. |
| `claimed` | Owner reserved the surfaces but has not begun edits. |
| `in progress` | Owner is changing or validating the slice. |
| `in review` | PR/evidence is ready for independent review; implementation may still need repairs. |
| `complete` | Merged, reviewed task evidence is linked, or documented historical provenance is explicitly labeled. |
| `blocked` | Cannot proceed; the exact prerequisite, external condition, and next owner are recorded. |

## Dependency and release rules

- [AD-M03-06](M03/06-atomic-cutover-and-rollback-live-proof.md) is the atomic cutover/rollback release gate; it gates M04
  acceptance and release even though M04 adapter work can proceed in parallel.
- [AD-M04-02](M04/02-delivery-adapter-acceptance.md), [AD-M07-04](M07/04-independent-review-and-full-gate.md), [AD-M09-01](M09/01-runtime-extraction-decision.md), and [AD-M10-03](M10/03-final-uat-and-handoff.md) are synchronous
  acceptance, architecture, or release gates. Do not parallelize their final
  conclusions with unreviewed prerequisite work.
- [AD-M08-01](M08/01-baseline-instrumentation-and-measurement.md) is measurable only after [AD-M03-06](M03/06-atomic-cutover-and-rollback-live-proof.md) and [AD-M07-05](M07/05-full-local-gate.md); [AD-M09-02](M09/02-conditional-runtime-service.md) remains non-claimable until [AD-M09-01](M09/01-runtime-extraction-decision.md) approves it.
