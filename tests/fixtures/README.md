# Test Fixtures

`answer_delivery/v1/boundary_inventory.json` is the versioned M01 inventory of
every direct legacy broker factory and its API or host entry points. Its static
contract test keeps an unrecorded R0 caller from reaching M03 migration.

`answer_delivery/v1/synthetic_answer_cases.json` is the versioned M01 answer
delivery corpus. It has fixed request IDs, source revisions and hashes,
candidate IDs, fake-provider outcomes, expected final results, and public event
sequences. It uses only synthetic passages and runs without Docker, credentials,
private books, or model access. Python lifecycle checks and the browser event
schema test consume the same bank so later runtime, gRPC, and SSE work retain a
single deterministic baseline.

`sample.epub` is a deterministic EPUB used as a parser source of truth.

The unzipped source files live in `epub_source/` so expected title, author, and
body text can be reviewed without opening the binary EPUB. If the fixture needs
to change, rebuild the EPUB with fixed ZIP metadata so its hash remains stable
across machines.
