# Librarian work tracking

[Jira](https://jgwesterfield.atlassian.net/browse/LIB-1) is the sole mutable
task and milestone ledger for the answer-delivery program. Read the applicable
Jira epic and task before editing; record ownership, dependencies, evidence,
review findings, and handoff there.

The repository keeps technical design and implementation evidence in Git. The
legacy answer-delivery task records, freshness manifest, and local freshness
checker were retired after a verified Jira import and explicit approval; the remaining
[Jira pointer](answer-delivery/README.md) preserves that provenance only. This
directory does not maintain duplicate task files, lifecycle status, or a
freshness manifest. New milestone work is strictly sequential: all tickets and
epics in every preceding milestone must be Done and their technical exit
evidence satisfied before the next milestone begins.
