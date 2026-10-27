# Answer-delivery Jira migration

[Jira](https://jgwesterfield.atlassian.net/browse/LIB-1) is the sole mutable
task and milestone ledger. Read the applicable epic and task before editing;
record ownership, scope, dependencies, evidence, review findings, and handoff
there. The versioned roadmap and design documents remain in Git.

## Verified migration provenance

- **Readback:** 11 epics and 66 tasks, with milestone parent counts
  `1/13/3/22/4/3/4/5/5/2/4` for M00–M10; 39 tasks Done, one In Progress, and
  26 To Do.
- **Source snapshot:**
  `c68471b11d4e186c048b35d365bbd40fbd2559de`, plus verified active snapshots
  for AD-M03-15 and AD-M03-22.
- **Dependencies:** 85 blocking links and 33 strict-sequencing flags were
  verified in Jira. The policy is expressed by Jira dependency links and
  contributor discipline; no automatic Jira workflow validator is configured.
- **Unmerged work:** [LIB-43](https://jgwesterfield.atlassian.net/browse/LIB-43)
  preserves AD-M03-15's active snapshot as To Do and blocked. [LIB-50](https://jgwesterfield.atlassian.net/browse/LIB-50)
  preserves AD-M03-22 as In Progress; task 22 has no immutable `c684` blob, so
  its verified unmerged provenance comes from the active snapshot.

The legacy task files, freshness manifest, and local freshness checker were
retired after the verified import and explicit approval. This pointer is not a
task mirror. New work is strictly sequential: every ticket and epic in all
preceding milestones must be Done and the required technical exit evidence
satisfied before a later milestone begins.

| Milestone | Jira epic |
| --- | --- |
| M00 | [LIB-1](https://jgwesterfield.atlassian.net/browse/LIB-1) |
| M01 | [LIB-2](https://jgwesterfield.atlassian.net/browse/LIB-2) |
| M02 | [LIB-3](https://jgwesterfield.atlassian.net/browse/LIB-3) |
| M03 | [LIB-4](https://jgwesterfield.atlassian.net/browse/LIB-4) |
| M04 | [LIB-5](https://jgwesterfield.atlassian.net/browse/LIB-5) |
| M05 | [LIB-6](https://jgwesterfield.atlassian.net/browse/LIB-6) |
| M06 | [LIB-7](https://jgwesterfield.atlassian.net/browse/LIB-7) |
| M07 | [LIB-8](https://jgwesterfield.atlassian.net/browse/LIB-8) |
| M08 | [LIB-9](https://jgwesterfield.atlassian.net/browse/LIB-9) |
| M09 | [LIB-10](https://jgwesterfield.atlassian.net/browse/LIB-10) |
| M10 | [LIB-11](https://jgwesterfield.atlassian.net/browse/LIB-11) |
