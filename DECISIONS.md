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
renaming the repository must not change an id that divers' logbooks already hold.

## A seed names the entry its path was made from

`external_ids` is a fact a review can change, so it cannot place a file: a record that gains a second
entry would otherwise have two candidate paths. `seeded_from` never changes, which keeps a seed at
one path for good and lets the publish place it without guessing.

## A Wikidata item takes its first coordinate

The seed's SPARQL query returns one row per `P625` (coordinate location) claim, so an item with
several coordinates arrives several times. On 2026-10-17, 331 rows held 312 items. The seed wrote
one record per item, at the coordinate of the first row the query service returned for it. That
choice is arbitrary: the query sets no order.

## The instance holds the records, and this repository copies them

A record has one home, the database of the instance the project operates: a review writes it there,
and a curated batch enters it through the bundle in the instance's image. So the database is the
truth and the repository is what publishes it. The copy is how the pool outlives that instance,
and with the export it is the offer ODbL 4.6 asks of whoever publicly uses a database they alter.
Git as the truth would put a GitHub secret on the instance and show an approval only after a round
trip.

## A record's `license` can be a `LicenseRef-`

SPDX has no identifier for a public-domain work that is not a dedication, and `CC0-1.0` would claim
a dedication neither publisher made. So a NOAA record says `LicenseRef-US-Gov-PD` and a Florida
register record `LicenseRef-FWC-PD`, SPDX's form for an unlisted licence. Both enter an ODbL database
as they are. A CC BY row does not: CC BY 4.0 forbids technological measures that ODbL 4.7(b) allows,
so such a source waits for its publisher's waiver.

## `validate` checks every record, every time

A publish can touch any record, and the whole tree takes seconds, so nothing scopes the check to a
pull request's changes. That also means a rule change is tested against everything it governs, and
one record shape is valid at any time.

## A publish never removes a file

Nothing retires a Commons record, so a record missing from the export is a fault at the other end,
and treating it as a deletion would let a 404 or an error body empty the repository. Whoever builds
retiring builds its path here too.

## A publish merges as an App of its own

A pull request opened with a workflow's own token starts no workflow, so the required checks would
never report; an App's token starts them, and a commit it makes through the API is verified. It is
an App of its own because the release bot's key reaches repositories that deploy on every merge, and
a data repository's secrets are the wrong place for that.

## The heartbeat keeps the schedule alive

GitHub disables a schedule after 60 days without repository activity, and a quiet month of proposals
is ordinary. So when 30 days have passed since the last commit on `main`, whoever made it, the
workflow merges `published.json`. It lands in a pull request of its own and goes first, because a
publish stuck red must not stop the repository counting as active.
