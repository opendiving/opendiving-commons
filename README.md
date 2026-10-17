# OpenDiving Commons

An open pool of dive sites. Each site is one GeoJSON file under `sites/`, its properties a
[DiveJSON](https://divejson.org) dive site; the pool is seeded from OpenStreetMap and Wikidata,
grows by divers' pull requests, and is published in releases that any logbook can read.

The code — the scripts, their tests and the workflows — is MIT (`LICENSE`). The data as a whole is
under the Open Database License 1.0 (`LICENSE-ODbL`), and every contributed record is dedicated to
the public domain under CC0 1.0 (`LICENSE-CC0`).

**Credit:** © OpenDiving Commons contributors, © OpenStreetMap contributors.

## One file per site, at a path that is its identity

```
sites/openstreetmap/node/255316037.geojson   a seed from OpenStreetMap (node/, way/ or relation/)
sites/wikidata/Q14213816.geojson             a seed from Wikidata
sites/opendivingcommons/<uuid>.geojson       a contributed site
```

A seed lives at the registry and identifier it came from; a contribution lives at its own UUID.
Two contributions never touch the same file, so they never conflict. GitHub shows a `.geojson`
file as a map, so opening a record shows where it is.

GitHub's directory listing stops at 1,000 entries and `sites/openstreetmap/node/` holds more than
that. The listing is not how a record is found: its path is, and so are the release artifacts.

A record looks like this:

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [33.920048, 27.814092] },
  "properties": {
    "uuid": "74c091ba-1ec3-5a6b-b70e-fe31c5438605",
    "name": "SS Thistlegorm",
    "external_ids": [{ "registry": "openstreetmap", "identifier": "node/255316037" }],
    "extensions": {
      "opendivingcommons": { "source": "openstreetmap", "license": "ODbL-1.0", "retrieved": "2026-10-17" }
    }
  }
}
```

Coordinates are longitude first, as GeoJSON requires. `CONTRIBUTING.md` lists the rules every
record keeps, and what each pull request is checked for.

## Licence and attribution

The records and the artifacts built from them are one database under the ODbL 1.0. The
OpenStreetMap seeds make it a Derivative Database of OpenStreetMap, so the whole stays ODbL:
whoever takes a substantial part of it shares it alike and keeps the notice.

Each record states its own terms in `extensions.opendivingcommons.license`:

- **`ODbL-1.0`** — a seed from OpenStreetMap.
- **`CC0-1.0`** — a seed from Wikidata, and every contribution. A diver adding a site dedicates it to
  the public domain in the pull request, and that dedication stays with the record. A contribution
  can therefore go on to OpenStreetMap or Wikidata, both of which refuse share-alike sources.

Credit both lines wherever the data appears: **© OpenDiving Commons contributors** and
**© OpenStreetMap contributors** ([osm.org/copyright](https://osm.org/copyright)).

`scripts/seed.py` is how the seed was made, and is checked in beside it for that reason.

## Policy

**Sensitive sites.** Archaeological sites, war graves and fragile sites can be taken down on
request: open an issue naming the record's path, and say as much about why as you are comfortable
saying in public. The maintainers may also refuse such a record, or coarsen its position, without
being asked.

**No scraping.** A pull request that bulk-adds sites copied from PADI, SSI, Garmin, a book, a
website or another app is refused on provenance, whatever licence it claims. A data set that labels
itself open is not enough: one "ODbL" dive-site map turned out to be almost entirely one training
agency's rows. Every contribution is a diver's own, and attests to it.

**Attribution and licence.** The ODbL covers the pool as a whole and CC0 covers each contribution.
Use the two credit lines above, and read a record's `license` member to tell which terms apply to
it.

## Possible duplicates

Every pull request gets a report of the existing records close to each record it changes. The
report is advisory: it never fails the check, and nothing is ever merged automatically. It flags
another record:

- within 20 m, whatever its name;
- within 200 m, when the names are similar;
- within 5 km, when a name is the same and is not a generic one like `Diving Spot` or `House Reef`.

These thresholds come from the catalogue the seed came from, and they are floors to be tuned on real
contributions. Two things the data cannot settle: whether two differently named records 10 m apart
are one site measured twice or two features of one site, and how a diver and OpenStreetMap name the
same place. The seed's own Wikidata-against-OpenStreetMap dedupe dropped every cross-source pair
inside 200 m, so there is nothing to learn that from yet.

Over the seed as committed on 2026-10-17, `python scripts/dedup.py` flags 359 pairs among 3,712
records. Each pair is counted under the first rule it meets: 103 within 20 m, 218 similar names
within 200 m, and 38 same names within 5 km.
