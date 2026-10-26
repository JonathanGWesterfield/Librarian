# Librarian task ledgers

This directory is the discoverable home for file-backed execution ledgers. A
ledger breaks an active program into independently claimable tasks and preserves
its ownership, dependencies, evidence, review findings, and handoff notes.

## Active ledger

[Answer delivery](answer-delivery/README.md) is the current M00–M10 execution
ledger. It defines the task lifecycle and claim protocol; read that program
ledger, its milestone index, and the selected task before editing.

Individual task files are authoritative for a slice’s implementation artifacts, command results, reports, review findings, and handoff notes. The answer-delivery roadmap and [issue #87](https://github.com/JonathanGWesterfield/Librarian/issues/87) are authoritative for milestone state and cross-milestone acceptance/release evidence. A task file does not independently advance a milestone.
