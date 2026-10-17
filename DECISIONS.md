# Decisions

The choices the code cannot explain by itself. Each entry says what was decided and why.

## A seed's uuid is derived from a fixed string

A seed's `uuid` is

```
uuid5(NAMESPACE_URL, "https://github.com/opendiving/opendiving-commons/sites/<registry>/<identifier>")
```

where `<registry>/<identifier>` is the record's path under `sites/` without `.geojson`, for example
`openstreetmap/node/255316037` or `wikidata/Q14213816`. The string is fixed text
(`SEED_UUID_PREFIX` in `scripts/pool.py`), not wherever the repository happens to live. Moving or
renaming the repository must not change an id that divers' logbooks already hold. Because the id is
deterministic, re-running the seed reproduces every id it wrote before.

## A Wikidata item takes its first coordinate

The seed's SPARQL query returns one row per `P625` (coordinate location) claim, so an item with
several coordinates arrives several times. On 2026-10-17, 331 rows held 312 items. The seed writes
one record per item, at the coordinate of the first row the query service returns for it.

That choice is arbitrary. The query sets no order, so a later run can pick another of the item's
claims. A refresh that does so lists the record as differing rather than moving it, because the
seed never overwrites a record that differs from what it would write.

## A refresh rewrites only what it wrote, and only the date

`scripts/seed.py` rewrites a file only when the file is byte-identical to what it would write from
the new upstream data stamped with the file's own `retrieved` date. In that case the only change is
the date. Any other difference is left in place and listed: a maintainer's coarsened position, a
merge's added entries, or an upstream rename. With the file alone, the seed cannot tell those apart.
`retrieved` therefore means the date the record was last confirmed against its upstream.

## The checks scope themselves to what a pull request changes

`validate` checks the records a pull request adds or changes, against the whole tree for the
cross-record rules. It checks every record only when the pull request changes the rules themselves
(`scripts/`, `requirements.txt`, the workflow). Because the `main` ruleset does not require a branch
to be up to date before it merges, two pull requests can each pass alone and conflict once both are
in. A contributor's pull request is not failed for a record it never touched; the next change to
the rules surfaces such a conflict.

The duplicate report's thresholds are floors calibrated on the catalogue the seed came from: 20 m
whatever the name, 200 m for similar names, and 5 km for the same non-generic name. A rule moves when
real contributions show it is wrong, and the change says which pairs moved. The baseline in
`README.md` is what such a change compares against.
