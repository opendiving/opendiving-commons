# Contributing

Most pull requests here add one dive site. The rest are a maintainer's corrections and merges, or
changes to the scripts and workflows that check and build the pool.

## Adding a dive site

**From the OpenDiving app:** open the site, choose *Add to OpenDiving Commons*, tick the attestation
and follow the link to GitHub. The link opens GitHub's new-file page with the record already written
at its path. *Propose new file* forks the repository to your account and opens the pull request; tick
the box in its description again.

**By hand:** add one file at `sites/opendivingcommons/<uuid>.geojson`, where `<uuid>` is a new
lowercase UUID (`python3 -c 'import uuid; print(uuid.uuid4())'`) that is also the record's `uuid`:

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [34.53851, 28.57211] },
  "properties": {
    "uuid": "8c0b6b3e-1f2a-4b3c-9d4e-5f6a7b8c9d0e",
    "name": "Bells",
    "other_names": ["The Bells"],
    "location": { "name": "Dahab" },
    "depth_from": 5,
    "depth_to": 30,
    "water_type": "salt",
    "entry_types": ["shore"],
    "extensions": { "opendivingcommons": { "source": "contribution", "license": "CC0-1.0" } }
  }
}
```

Only `uuid`, `name`, the geometry and the `extensions` block are required. Leave out anything you
are unsure of.

### The attestation

The pull request template carries this line. Tick it:

> I am adding this dive site from my own diving. It is not copied from another database, app or
> publication. I dedicate it to the public domain under CC0 1.0, and I understand the record and
> this attestation are public and kept indefinitely.

The check fails a pull request that adds a site without it ticked, and runs again when you edit the
description.

## The record rules

`scripts/validate.py` enforces these on every pull request, and you can run it yourself:

- **A record is a valid DiveJSON dive site** once its geometry is folded back into `position`. The
  [`divejson`](https://pypi.org/project/divejson/) package decides that, so member names, the
  `other_names` rules, the external-id forms and `depth_from ≤ depth_to` follow the format.
- **The path is the identity.** A seed's `uuid` is derived from its path (`DECISIONS.md` has the
  formula), and it carries the registry entry its path names. A contribution's `uuid` is its file
  name.
- **A record never names its own `uuid` in `external_ids`, and a new contribution carries no
  `external_ids` at all.** A site already in OpenStreetMap or Wikidata belongs to that seed.
- **`extensions.opendivingcommons` is required.** It holds `source` (`openstreetmap`, `wikidata` or
  `contribution`, matching the directory) and `license` (`ODbL-1.0` for an OpenStreetMap seed,
  `CC0-1.0` for everything else). A seed also holds `retrieved`, and an OpenStreetMap seed holds
  `name_en` where OpenStreetMap has an English name that differs from `name`. Nothing else goes in
  `extensions`.
- **One Point, longitude first, in range, not at 0, 0, and to six decimals at most.** A seventh
  decimal is false precision on a position nobody measured to the decimetre.
- **A record carries the site's identity and its structured facts, and nothing else.** That means no
  `notes`, `tags` or `created_at`, no `position` (the geometry is the position), and a `location`
  that is the locality's `name` alone. A record carries no country or region either: the release
  build resolves those.
- **Across the pool,** no two records share a `uuid` or carry the same registry entry. A record
  naming another as merged into it means that other record is gone.

## What a pull request runs

`.github/workflows/validate.yml` has two jobs:

- **`validate`**, the required check. It runs the record rules over every record the pull request
  adds or changes, or over every record when it changes the scripts, `requirements.txt` or the
  workflow itself. It checks the attestation when a contribution is added. Then it writes the
  possible-duplicates report from `scripts/dedup.py` into the job summary: the existing records near
  each changed one, with distances and a map link. That report never fails the job.
- **`tests`** runs the `pytest` suite when the pull request touches `scripts/`, `tests/`,
  `requirements.txt`, the workflow, or a seed under `sites/openstreetmap/` or `sites/wikidata/`. It
  is not required, and a contribution never triggers it.

`.github/workflows/pr-title.yml` checks the title. A pull request that changes only files under
`sites/` passes with whatever title its author wrote. Every other pull request needs a semantic
title, `<type>[(scope)][!]: <description>`, where type is one of `feat`, `fix`, `refactor`, `docs`,
`test`, `chore`, `perf`, `ci`, `build` or `revert`. Pull requests are squash-merged, so the title
becomes the commit subject on `main`.

## Reviewing a contribution

A run on a pull request from outside the organisation waits for a maintainer, every time. Approving
it runs the fork's own copy of the workflow and the scripts, so:

1. Check that every changed file is under `sites/`. If anything else changed, do not approve the
   run until you have read that change.
2. Approve the run.
3. Read the job summary. Open the record's file to see it on a map, and look at the flagged
   neighbours.
4. Merge, or ask. Two records the report flags are often two real sites; a merge is a decision you
   make, never the report's.

**Merging two records** is a pull request of its own. Delete the absorbed record's file. Then add
its registry entries to the survivor's `external_ids`, together with
`{"registry": "opendivingcommons", "identifier": "<the absorbed uuid>"}`, so that a diver holding
the absorbed record still finds the survivor.

**Deleting a seed** — the absorbed half of a merge, or a takedown — lowers `SEED_RECORDS` in
`tests/test_sites.py` in the same pull request. The suite pins the seed count, and the `tests` job
runs on any change to a seed so that a stale pin fails there, not in somebody else's pull request.

**Coarsening a position** for a sensitive site means rounding its coordinates in place. A later
refresh of the seed leaves an edited record alone.

## Working on the scripts

Python 3.10 or newer:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python -m pytest                          # the suite
python scripts/validate.py                # the record rules, over every record
python scripts/validate.py sites/wikidata/Q14213816.geojson
python scripts/dedup.py                   # possible duplicates across the whole pool, by rule
python scripts/dedup.py --base origin/main  # the report a pull request gets
```

**Refreshing the seed** is `python scripts/seed.py`, run by hand. It fetches from Overpass and the
Wikidata query service, which takes a minute or two. A record that is still exactly what the seed
wrote, from upstream data that has not changed, only takes the new `retrieved` date. A record that differs from what it would write is left alone and
listed, whether a maintainer edited it or the upstream object changed. Carry upstream changes into
those records by hand. A new upstream object that some record already carries in its `external_ids`
is not written again. Commit the result, and update `SEED_RECORDS` in `tests/test_sites.py`: the
suite pins the seed count, not the total, because every contribution moves the total.
