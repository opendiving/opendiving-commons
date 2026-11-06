# OpenDiving Commons

An open pool of dive sites. Each site is one GeoJSON file under `sites/`, its properties a
[DiveJSON](https://divejson.org) dive site. The pool was seeded from OpenStreetMap and Wikidata. It
grows in the app at [opendiving.app](https://opendiving.app), where divers propose sites and changes
and a reviewer reads each one on a map, and by batches a maintainer imports from the open datasets
listed under [*Sources*](#sources).

**This repository is the Commons' published copy.** The records live in the database of the instance
the project operates, which serves them at
[`/api/v1/commons/dive-sites`](https://opendiving.app/api/v1/commons/dive-sites). A scheduled
workflow brings `sites/` in line with that export every day, so this repository takes no pull
requests to `sites/`: a diver adds or corrects a site in the app, and `CONTRIBUTING.md` says how.

The code — the scripts, their tests and the workflows — is MIT (`LICENSE`). The data as a whole is
under the Open Database License 1.0 (`LICENSE-ODbL`), and every contributed record is dedicated to
the public domain under CC0 1.0 (`LICENSE-CC0`).

**Credit for the pool:** © OpenDiving Commons contributors, © OpenStreetMap contributors, and the
publishers of the curated sources under [*Sources*](#sources).

## One file per site, at a path that is its identity

```
sites/openstreetmap/node/255316037.geojson            a seed from OpenStreetMap (node/, way/ or relation/)
sites/wikidata/Q14213816.geojson                      a seed from Wikidata
sites/noaa-florida-keys-moorings/french-reef.geojson  a seed from a curated source
sites/fwc-artificial-reefs/BA0001.geojson             the same, under the publisher's own id
sites/opendivingcommons/<uuid>.geojson                a contributed site
```

A seed lives at the registry or curated source and the identifier it came from; a contribution lives
at its own UUID.
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

Coordinates are longitude first, as GeoJSON requires. A record from a curated source has no entry
for that source in `external_ids`: its `seeded_from` says where it came from. `CONTRIBUTING.md` lists
the rules every record keeps.

## Sources

| Token | Dataset | `license` | Credit |
| --- | --- | --- | --- |
| `openstreetmap` | [OpenStreetMap](https://www.openstreetmap.org) | `ODbL-1.0` | [Data © OpenStreetMap contributors, ODbL 1.0.](https://osm.org/copyright) |
| `wikidata` | [Wikidata](https://www.wikidata.org) | `CC0-1.0` | [Data from Wikidata, CC0 1.0.](https://www.wikidata.org/wiki/Wikidata:Licensing) |
| `noaa-florida-keys-moorings` | [Florida Keys National Marine Sanctuary buoys](https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/PubFKNMSBuoy2025/FeatureServer/0), NOAA | `LicenseRef-US-Gov-PD` | [Data from NOAA Florida Keys National Marine Sanctuary, public domain.](https://floridakeys.noaa.gov/mbuoy/) |
| `noaa-thunder-bay-moorings` | [Thunder Bay National Marine Sanctuary buoys](https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/arcgisOnline_BuoysOnly_Update20230703/FeatureServer/0), NOAA | `LicenseRef-US-Gov-PD` | [Data from NOAA Thunder Bay National Marine Sanctuary, public domain.](https://thunderbay.noaa.gov/) |
| `fwc-artificial-reefs` | [Artificial Reef Locations in Florida](https://gis.myfwc.com/mapping/rest/services/Open_Data/Artificial_Reef_Locations_in_Florida/MapServer/12), Florida Fish and Wildlife Conservation Commission; [its metadata](sources/fwc-artificial-reefs/metadata.xml), fetched 2026-11-06 | `LicenseRef-FWC-PD` | [Data from the Florida Fish and Wildlife Conservation Commission (FWC-FWRI), public domain.](https://github.com/opendiving/opendiving-commons/tree/main/sources/fwc-artificial-reefs) |

The last three are the curated sources. The Florida register's publisher asks that its metadata be
distributed with the data, so `sources/fwc-artificial-reefs/` holds a copy as the publisher's service
serves it.

A position in the pool is where a source or a diver placed a site, and none of it is for navigation.
The Florida register says so of its own positions, and the same goes for every other record.

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
- **`LicenseRef-US-Gov-PD`** — a seed from a NOAA source. A work of the US federal government carries
  no copyright (17 U.S.C. §105).
- **`LicenseRef-FWC-PD`** — a seed from the Florida register, whose metadata places it in the public
  domain.

An accepted change to a seed leaves that seed under its source's licence. A seed's `location` was
resolved from Natural Earth, which is public domain and adds no terms.

These credit lines are for whoever takes the pool: **© OpenDiving Commons contributors**,
**© OpenStreetMap contributors** ([osm.org/copyright](https://osm.org/copyright)), and the credit of
each curated source under [*Sources*](#sources). A screen showing one record credits that record's
source.

`scripts/seed.py` is how the seed was made, and is checked in beside it for that reason. Its output
is no longer how a record enters, and refreshing a record from its source is unsolved.

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

**Curated sources.** What separates a curated source from scraping is a property of the source, not
a label on it. It is a public dataset named with its publisher. Its terms are public domain, CC0 or
an Open Government Licence, or its CC BY publisher has given a written waiver. A maintainer imports
it by running a script checked into
[`opendiving-api`](https://github.com/opendiving/opendiving-api). And it is never a site list copied
from a product, whatever a mirror of that list claims.

**Attribution and licence.** The ODbL covers the pool as a whole, CC0 covers each contribution, and
a public-domain record stays public domain. Whoever takes the pool uses the credit lines above, a
screen showing one record credits that record's source, and a record's `license` member says which
terms apply to it.
