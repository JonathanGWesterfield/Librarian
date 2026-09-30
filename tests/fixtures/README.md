# Test Fixtures

`answer_delivery/v1/boundary_inventory.json` is the versioned M01 inventory of
every direct legacy broker factory and its API or host entry points. Its static
contract test keeps an unrecorded R0 caller from reaching M03 migration.

`sample.epub` is a deterministic EPUB used as a parser source of truth.

The unzipped source files live in `epub_source/` so expected title, author, and
body text can be reviewed without opening the binary EPUB. If the fixture needs
to change, rebuild the EPUB with fixed ZIP metadata so its hash remains stable
across machines.
