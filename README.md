# OpenDiving Commons

An open pool of dive sites. Each site is one GeoJSON file under `sites/`, its properties a
[DiveJSON](https://divejson.org) dive site. The pool was seeded from OpenStreetMap and Wikidata, and
it grows in the app at [opendiving.app](https://opendiving.app), where divers propose sites and
changes and a reviewer reads each one on a map.

**This repository is the Commons' published copy.** The records live in the database of the instance
the project operates, which serves them at
[`/api/v1/commons/dive-sites`](https://opendiving.app/api/v1/commons/dive-sites). A scheduled
workflow brings `sites/` in line with that export every day, so this repository takes no pull
requests to `sites/`: a site is added or corrected in the app, and `CONTRIBUTING.md` says how.

The code — the scripts, their tests and the workflows — is MIT (`LICENSE`). The data as a whole is
under the Open Database License 1.0 (`LICENSE-ODbL`), and every contributed record is dedicated to
the public domain under CC0 1.0 (`LICENSE-CC0`).

**Credit for the pool:** © OpenDiving Commons contributors, © OpenStreetMap contributors.

## One file per site, at a path that is its identity

```
sites/openstreetmap/node/255316037.geojson   a seed from OpenStreetMap (node/, way/ or relation/)
sites/wikidata/Q14213816.geojson             a seed from Wikidata
sites/opendivingcommons/<uuid>.geojson       a contributed site
```

A seed lives at the registry and identifier it came from; a contribution lives at its own UUID.
GitHub shows a `.geojson` file as a map, so opening a record shows where it is.

GitHub's directory listing stops at 1,000 entries and `sites/openstreetmap/node/` holds more than
that. The listing is not how a record is found: its path is.

A record looks like this:

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [33.920048, 27.814092] },
  "properties": {
    "uuid": "74c091ba-1ec3-5a6b-b70e-fe31c5438605",
    "name": "SS Thistlegorm",
    "location": { "name": "South Sinai, Egypt" },
    "external_ids": [{ "registry": "openstreetmap", "identifier": "node/255316037" }],
    "extensions": {
      "opendivingcommons": {
        "source": "openstreetmap",
        "license": "ODbL-1.0",
        "retrieved": "2026-10-17",
        "seeded_from": { "registry": "openstreetmap", "identifier": "node/255316037" }
      }
    }
  }
}
```

Coordinates are longitude first, as GeoJSON requires. `CONTRIBUTING.md` lists the rules every
record keeps.

## Licence and attribution

The records are one database under the ODbL 1.0. The OpenStreetMap seeds make it a Derivative
Database of OpenStreetMap, so the whole stays ODbL: whoever takes a substantial part of it shares it
alike and keeps the notice.

Each record states its own terms in `extensions.opendivingcommons.license`:

- **`ODbL-1.0`** — a seed from OpenStreetMap.
- **`CC0-1.0`** — a seed from Wikidata, and every contribution. A diver proposing a site dedicates it
  to the public domain with a tick at the button that sends the proposal, and that dedication stays
  with the record. A contribution can therefore go on to OpenStreetMap or Wikidata, both of which
  refuse share-alike sources.

An accepted change to a seed leaves that seed under its source's licence. A seed's `location` was
resolved from Natural Earth, which is public domain and adds no terms.

Both credit lines are for whoever takes the pool: **© OpenDiving Commons contributors** and
**© OpenStreetMap contributors** ([osm.org/copyright](https://osm.org/copyright)). A screen showing
one record credits that record's source.

`scripts/seed.py` is how the seed was made, and is checked in beside it for that reason. Its output
is no longer how a record enters, and refreshing the pool from OpenStreetMap and Wikidata is
unsolved.

## Policy

**Reporting a record.** Anyone, with an account or without, can report a record: a pin that shows
more than it should, such as an archaeological site, a war grave or a fragile site; a wrong name;
something that should not be there. Use the [support page](https://opendiving.app/support), or open
an issue here naming the record's path and saying as much about why as you are comfortable saying
in public. A report is answered by changing the record, a reviewer coarsening the pin or changing
the name through the review queue, and the change reaches this repository with the next publish.
A record cannot yet be removed or merged. A reviewer may also decline a proposal for such a site, or coarsen
a pin, without being asked.

**No scraping.** A proposal copied from PADI, SSI, Garmin, a book, a website or another app is
declined on provenance, whatever licence it claims. A data set that labels itself open is not
enough: one "ODbL" dive-site map turned out to be almost entirely one training agency's rows. Every
contribution is a diver's own, and attests to it.

**Attribution and licence.** The ODbL covers the pool as a whole and CC0 covers each contribution.
Whoever takes the pool uses the two credit lines above, a screen showing one record credits that
record's source, and a record's `license` member says which terms apply to it.
