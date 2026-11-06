# Contributing

Pull requests here change the scripts, the tests, the workflows, the documentation and what
`sources/` holds. They do not change `sites/`, which is a copy: a publish overwrites any edit to a record, and fails on a record
the instance does not hold.

## Adding or correcting a dive site

In the app at [opendiving.app](https://opendiving.app). On a site of your own, *Propose for
OpenDiving Commons*; on a Commons site, *Propose a change*. The dialog that sends it carries an
attestation you tick, which for a new site reads:

> I am adding this dive site from my own diving. It is not copied from another database, app or
> publication. I dedicate it to the public domain under CC0 1.0.

A reviewer reads the proposal on a map and accepts it, or declines it with a reason you can read. An
accepted site or change reaches this repository with the next publish.

## Adding a curated source

`README.md`'s *Policy* says what qualifies. A dataset enters as a batch, not as proposals: a
maintainer runs an importer checked into `opendiving-api`, the batch goes into the bundle its image
carries, the instance inserts it at its next start, and the next publish copies it here.

The source comes here first. Its token and identifier form go in `CURATED_SOURCES` in
`scripts/pool.py`, its licence in `LICENCE_OF_SOURCE` in `scripts/validate.py`, and its credit in the
README's *Sources* table, because a publish fails on a registry this repository does not know.

## Reporting a record

`README.md`'s *Policy* says how. A report is answered by changing the record, a coarsened pin or a
new name, through the review queue. A record cannot yet be removed, and two records cannot yet be
merged.

## The record rules

`scripts/validate.py` holds every record to these on every pull request, and the instance holds an
accepted proposal to the same rules, so a publish should never break one:

- **A record is a valid DiveJSON dive site** once its geometry is folded back into `position`. The
  [`divejson`](https://pypi.org/project/divejson/) package decides that, so member names, the
  `other_names` rules, the external-id forms and `depth_from ≤ depth_to` follow the format.
- **The path is the identity.** A seed's `uuid` is derived from its path (`DECISIONS.md` has the
  formula), and an OpenStreetMap or Wikidata seed carries the registry entry its path names. A
  contribution's `uuid` is its file name. A curated source's identifier is a lowercase slug, letters
  and digits joined by single hyphens, for the NOAA sources, and the register's deployment id, two
  capitals and four digits, for `fwc-artificial-reefs`.
- **A record never names its own `uuid` in `external_ids`.**
- **No record carries an entry whose registry is a curated source.** Its source and identifier are
  provenance, in `seeded_from` alone.
- **`extensions.opendivingcommons` is required.** It holds `source` (`openstreetmap`, `wikidata`,
  `contribution` or a curated source's token, matching the directory) and `license` (`ODbL-1.0` for
  an OpenStreetMap seed, `CC0-1.0` for a Wikidata seed or a contribution, and for a curated source
  the value the README's *Sources* table gives). A seed, curated or not, also holds `retrieved`, the
  date it was taken from upstream, and `seeded_from`, the source and identifier its path names.
  Nothing else goes in `extensions`. An English name that differs from `name` is in `other_names`,
  like any other.
- **One Point, longitude first, in range, not at 0, 0, and to six decimals at most.** A seventh
  decimal is false precision on a position nobody measured to the decimetre.
- **A record carries the site's identity and its structured facts, and nothing else.** That means no
  `notes`, `tags` or `created_at`, no `position` (the geometry is the position), and a `location`
  that is the locality's `name` alone.
- **Across the pool,** no two records share a `uuid` or carry the same registry entry. A record
  naming another as merged into it means that other record is gone.

## What a pull request runs

`.github/workflows/validate.yml` has two jobs:

- **`validate`**, the required check, runs the record rules over every record.
- **`tests`** runs the `pytest` suite when the pull request touches `scripts/`, `tests/`, `sources/`,
  `README.md`, `requirements.txt` or the workflow. It is not required, and a publish skips it:
  `validate` reads every record the suite does.

`.github/workflows/pr-title.yml` checks the title, the other required check. Every pull request
needs a semantic title, `<type>[(scope)][!]: <description>`, where type is one of `feat`, `fix`,
`refactor`, `docs`, `test`, `chore`, `perf`, `ci`, `build` or `revert`. Pull requests are
squash-merged, so the title becomes the commit subject on `main`.

## How the copy is published

`.github/workflows/publish.yml` runs daily and on demand, and is skipped until the repository has the
publisher App's variable. `scripts/publish.py` fetches the export and writes `sites/`, and
`scripts/land.py` opens a pull request as the App and squash-merges it once `validate` and
`semantic-title` pass.

A publish adds and rewrites files and never removes one. An export that is not a 200
`FeatureCollection`, or that lacks a record the tree holds, fails the run with nothing committed. A
red `validate` fails the run, names the broken records and leaves the pull request open for the next
run to update; the failed run is the alarm.

When 30 days have passed since the last commit on `main`, the same workflow merges `published.json`
in a pull request of its own. It says when the copy was last checked against the export and how
many records it held.

## Working on the scripts

Python 3.10 or newer:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python -m pytest                          # the suite
python scripts/validate.py                # the record rules, over every record
python scripts/validate.py sites/wikidata/Q14213816.geojson
python scripts/publish.py http://localhost:8000/api/v1/commons/dive-sites  # write sites/ from an export
```

`scripts/publish.py` only writes the working tree, and with no address it reads the hosted instance.

`scripts/seed.py` made the seed and is not run: nothing it writes reaches the instance, and the
record rules refuse its shape.
