"""How the seed records were made from OpenStreetMap and Wikidata. Not run any more.

    python scripts/seed.py

The hosted instance holds the records, so nothing this writes reaches it, and what it writes is
not the shape the record rules accept: the English name sits in the extension block and the
file names no `seeded_from`. Refreshing from upstream is unsolved.

**The records are an ODbL Derivative Database of OpenStreetMap**, which is why this script is
checked in beside them: ODbL 4.6 wants the method of making a derivative reachable by whoever
receives it. Do not add a source whose terms are NC or ND - the pool is ODbL as a whole and
cannot carry them.

Two upstreams, doing different jobs:

- **OpenStreetMap**, via Overpass, is the pool. See `_is_business` and `_is_indoor` for what
  gets dropped and why the exclusion sets are floors rather than enumerations.
- **Wikidata** is a regional patch, not a second global source. OSM had exactly three named
  `sport=scuba_diving` features in the whole of South Africa when this was written, and most
  of Wikidata's recreational dive sites are South African. Deduped against OSM it fires on a
  couple of dozen records, precisely because the two sets barely intersect.

**A re-run never overwrites a record a maintainer has edited.** A file is rewritten only while
it is byte-identical to what this script writes for the same upstream data and the file's own
`retrieved` date - so a coarsened position, a corrected name or a merge's aliases survive a
refresh, and an upstream change to such a record is listed in the report for a maintainer to
carry by hand. A record that is gone upstream is listed and kept, and an upstream object that
another record already carries in its `external_ids` - the survivor of a merge - is not
written again.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pool import REGISTRY, ROOT, path_of, seed_uuid, serialise, site_files

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# `out center;`, never bare `out;`. A way or relation has no position of its own, and the
# bare form ships them with no coordinates at all - which is how Submersion's bundled
# catalog came to have 356 of its 3,612 records unusable, a number exactly equal to its
# ways plus its relations.
OVERPASS_QUERY = (
    '[out:json][timeout:280];(nwr["sport"="scuba_diving"];nwr["scuba_diving:divespot"="yes"];);out tags center;'
)

WIKIDATA_URL = "https://query.wikidata.org/sparql"

# Q2141554 is "recreational dive site" and has no subclasses, so `wdt:P31` and the
# transitive form return the same set. Coordinates are required rather than optional: a
# record with no position is not a record here.
WIKIDATA_QUERY = """
SELECT ?site ?siteLabel ?coordinate WHERE {
  ?site wdt:P31 wd:Q2141554 ; wdt:P625 ?coordinate .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# Wikidata blocks the default urllib user agent outright, and Overpass asks for a
# descriptive one. It names the project and nobody in it.
USER_AGENT = "OpenDiving-Commons-seed/0.1 (https://github.com/opendiving/opendiving-commons)"

_DOWNLOAD_TIMEOUT_SECONDS = 300

# ~11 cm, and the most the record rules accept. These are point features surveyed by hand;
# the rounding is only about not writing float noise.
_PRECISION = 6

# Wikidata records this close to an OSM record are the same site. 200 m is tight on purpose:
# these are point features, and the two sets barely overlap, so a loose radius costs real
# South African coverage to remove duplicates that are not there.
_DEDUPE_METRES = 200.0

# The looser radius, used only when the normalised names also match.
_NAMED_DEDUPE_METRES = 1000.0

# Degrees per kilometre, for the local planar approximation in `_distance_km`.
_KM_PER_DEGREE_LATITUDE = 110.574
_KM_PER_DEGREE_LONGITUDE = 111.320

LICENCE = {"openstreetmap": "ODbL-1.0", "wikidata": "CC0-1.0"}

# A business, not a dive site. Submersion's bundled catalog skipped this step and ships
# `Dive Otago` and `Go Dive Pacific` as places to dive.
#
# **A floor, not an enumeration.** Re-derive it before a refresh by dumping the tag set of
# the non-business features and reading the value distributions of `leisure`, `building` and
# `amenity`; the tagging vocabulary moves. `amenity=scuba_diving` is deliberately *not* here
# - 23 uses globally and no wiki page, so there is no evidence it means "business" rather
# than "dive site", and guessing costs a real record.
_BUSINESS_AMENITIES = frozenset({"dive_centre"})
_BUSINESS_CLUBS = frozenset({"scuba_diving"})
_BUSINESS_KEYS = ("shop", "office")

# An indoor training facility, not a dive site. Same floor caveat as above; `fitness_centre`
# and `sports_hall` were added on the same evidence `sports_centre` and `swimming_pool` rest
# on - the same family of value, and not one of the named records carries a scuba attribute.
#
# **`leisure=pitch` and `leisure=water_park` are deliberately absent, and this is the trap
# in the whole selection rule.** `pitch` is the Dutch convention for a dive site in Zeeland
# (`Flauwers West`, `Goese Sas`, `Noordbout`) and 35 of its 43 named features carry scuba
# attributes; `water_park` is the same story at 6 of 7. A filter that excluded
# sports-shaped `leisure` values wholesale would delete them.
_INDOOR_LEISURE = frozenset({"sports_centre", "swimming_pool", "fitness_centre", "sports_hall"})
_INDOOR_AMENITIES = frozenset({"school", "community_centre", "sport_school", "public_bath"})


@dataclass(slots=True)
class _Record:
    """One upstream object, as the seed writes it."""

    name: str
    name_en: str | None
    latitude: float
    longitude: float
    registry: str
    identifier: str


def _fetch(url: str, *, data: bytes) -> Any:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())


# -------------- OpenStreetMap --------------


def _values(tags: dict[str, str], key: str) -> list[str]:
    """A tag's values, split on OSM's `;` multi-value convention.

    Without this `amenity=restaurant;dive_centre` reads as neither a restaurant nor a dive
    centre and the feature ships as a dive site - which it is not.
    """
    raw = tags.get(key)
    return [value.strip() for value in raw.split(";")] if raw else []


def _is_business(tags: dict[str, str]) -> bool:
    return (
        any(value in _BUSINESS_AMENITIES for value in _values(tags, "amenity"))
        or any(value in _BUSINESS_CLUBS for value in _values(tags, "club"))
        or any(key in tags for key in _BUSINESS_KEYS)
    )


def _is_indoor(tags: dict[str, str]) -> bool:
    """An indoor facility - a pool, a training centre, a building.

    `scuba_diving:divespot=yes` rescues one regardless: a flooded quarry tagged
    `leisure=sports_centre` because a club runs it is still somewhere people dive, and the
    mapper saying so explicitly is better evidence than the `leisure` value.
    """
    if tags.get("scuba_diving:divespot") == "yes":
        return False
    return (
        any(value in _INDOOR_LEISURE for value in _values(tags, "leisure"))
        or any(value in _INDOOR_AMENITIES for value in _values(tags, "amenity"))
        or "building" in tags
    )


def _position(element: dict[str, Any]) -> tuple[float, float] | None:
    """A node's own position, or the centre Overpass computed for a way or relation."""
    if element.get("lat") is not None and element.get("lon") is not None:
        return float(element["lat"]), float(element["lon"])
    centre = element.get("center")
    if isinstance(centre, dict) and centre.get("lat") is not None and centre.get("lon") is not None:
        return float(centre["lat"]), float(centre["lon"])
    return None


def _osm_records(elements: Iterable[dict[str, Any]]) -> list[_Record]:
    records: list[_Record] = []
    for element in elements:
        tags = element.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name or _is_business(tags) or _is_indoor(tags):
            continue
        position = _position(element)
        if position is None:
            continue
        latitude, longitude = position

        # Only where it says something the `name` does not. `name:en` equal to `name` is the
        # common case for anywhere already named in Latin script, and carrying it would
        # double the field for no reachable search term.
        name_en = (tags.get("name:en") or "").strip() or None
        if name_en == name:
            name_en = None

        records.append(
            _Record(
                name=name,
                name_en=name_en,
                latitude=round(latitude, _PRECISION),
                longitude=round(longitude, _PRECISION),
                registry="openstreetmap",
                identifier=f"{element['type']}/{element['id']}",
            )
        )
    return records


# -------------- Wikidata --------------


def _wikidata_records(bindings: Iterable[dict[str, Any]]) -> list[_Record]:
    """One record per item, at the first coordinate the query returns for it.

    The query yields a row per `P625` claim, so an item with several coordinates arrives
    several times - a dozen items did, two to four rows each. Which claim is "first" is up to
    the query service; DECISIONS.md records that as a known arbitrariness.
    """
    records: list[_Record] = []
    seen: set[str] = set()
    for binding in bindings:
        qid = binding["site"]["value"].rsplit("/", 1)[-1]
        if qid in seen:
            continue
        label = binding.get("siteLabel", {}).get("value", "").strip()
        # An item with no label answers with its own QID, which is not a name a diver can
        # read.
        if not label or label == qid:
            continue
        point = binding["coordinate"]["value"]
        if not point.startswith("Point(") or not point.endswith(")"):
            continue
        longitude_text, _, latitude_text = point[len("Point(") : -1].partition(" ")
        try:
            longitude, latitude = float(longitude_text), float(latitude_text)
        except ValueError:
            continue

        seen.add(qid)
        records.append(
            _Record(
                name=label,
                # The label already is the English name, so a separate `name_en` would only
                # repeat it. Unlike OSM, where `name` is whatever the site is called locally.
                name_en=None,
                latitude=round(latitude, _PRECISION),
                longitude=round(longitude, _PRECISION),
                registry="wikidata",
                identifier=qid,
            )
        )
    return records


def _normalised(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())


def _distance_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Local planar approximation; every distance this compares is under a kilometre."""
    mean_latitude = math.radians((latitude_a + latitude_b) / 2)
    north = (latitude_a - latitude_b) * _KM_PER_DEGREE_LATITUDE
    east = (longitude_a - longitude_b) * _KM_PER_DEGREE_LONGITUDE * math.cos(mean_latitude)
    return math.hypot(north, east)


def _deduped(wikidata: list[_Record], osm: list[_Record], osm_qids: set[str]) -> list[_Record]:
    """Wikidata records that are not already in the OSM set.

    Three signals, in decreasing confidence: the OSM feature names the QID in its own
    `wikidata` tag; the two positions are within `_DEDUPE_METRES`; or they are within
    `_NAMED_DEDUPE_METRES` *and* the normalised names match. The last one is deliberately not
    proximity alone at a kilometre - two genuinely different sites on one reef are routinely
    that close, and the point of this source is the coverage it adds.
    """
    kept: list[_Record] = []
    for candidate in wikidata:
        if candidate.identifier in osm_qids:
            continue
        duplicate = False
        for existing in osm:
            metres = _distance_km(candidate.latitude, candidate.longitude, existing.latitude, existing.longitude) * 1000
            if metres <= _DEDUPE_METRES or (
                metres <= _NAMED_DEDUPE_METRES and _normalised(candidate.name) == _normalised(existing.name)
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


# -------------- the records --------------


def feature(record: _Record, retrieved: str) -> dict[str, Any]:
    provenance: dict[str, str] = {
        "source": record.registry,
        "license": LICENCE[record.registry],
        "retrieved": retrieved,
    }
    if record.name_en:
        provenance["name_en"] = record.name_en
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [record.longitude, record.latitude]},
        "properties": {
            "uuid": seed_uuid(record.registry, record.identifier),
            "name": record.name,
            "external_ids": [{"registry": record.registry, "identifier": record.identifier}],
            "extensions": {REGISTRY: provenance},
        },
    }


@dataclass
class Report:
    written: list[str] = field(default_factory=list)
    refreshed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    held: list[tuple[str, str]] = field(default_factory=list)
    gone: list[str] = field(default_factory=list)


def _retrieved_of(text: str) -> str | None:
    try:
        value = json.loads(text)["properties"]["extensions"][REGISTRY]["retrieved"]
    except (ValueError, KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _held_entries(root: Path) -> dict[tuple[str, str], str]:
    """Every registry entry some record already carries, and the record carrying it."""
    held: dict[tuple[str, str], str] = {}
    for path in site_files(root):
        try:
            entries = json.loads((root / path).read_text(encoding="utf-8"))["properties"].get("external_ids", [])
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("registry"), str):
                held[entry["registry"], str(entry.get("identifier"))] = path
    return held


def write_records(records: list[_Record], today: str, root: Path = ROOT) -> Report:
    report = Report()
    held = _held_entries(root)
    upstream = set()
    for record in records:
        path = path_of(record.registry, record.identifier)
        upstream.add(path)
        target = root / path
        fresh = serialise(feature(record, today))
        if target.exists():
            text = target.read_text(encoding="utf-8")
            retrieved = _retrieved_of(text)
            if retrieved is not None and text == serialise(feature(record, retrieved)):
                if text != fresh:
                    target.write_text(fresh, encoding="utf-8")
                    report.refreshed.append(path)
            else:
                report.kept.append(path)
            continue
        holder = held.get((record.registry, record.identifier))
        if holder is not None:
            report.held.append((path, holder))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fresh, encoding="utf-8")
        report.written.append(path)

    for path in site_files(root):
        if path.startswith(("sites/openstreetmap/", "sites/wikidata/")) and path not in upstream:
            report.gone.append(path)
    return report


def _print_report(report: Report) -> None:
    print(
        f"{len(report.written)} new, {len(report.refreshed)} refreshed, "
        f"{len(report.kept)} kept as edited, {len(report.held)} carried by another record, "
        f"{len(report.gone)} gone upstream",
        file=sys.stderr,
    )
    for path in report.kept:
        print(f"  kept: {path} differs from what the seed would write; carry any upstream change by hand", file=sys.stderr)
    for path, holder in report.held:
        print(f"  not written: {path} - {holder} carries its registry entry", file=sys.stderr)
    for path in report.gone:
        print(f"  gone upstream: {path} - kept; delete it by hand if the site is really gone", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--today", default=date.today().isoformat(), help="the `retrieved` date to write")
    args = parser.parse_args(argv)

    try:
        print(f"Fetching {OVERPASS_URL} ...", file=sys.stderr)
        elements = _fetch(OVERPASS_URL, data=urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode())["elements"]
        print(f"Fetching {WIKIDATA_URL} ...", file=sys.stderr)
        payload = _fetch(WIKIDATA_URL, data=urllib.parse.urlencode({"query": WIKIDATA_QUERY, "format": "json"}).encode())
        bindings = payload["results"]["bindings"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        print(f"upstream fetch failed: {exc}", file=sys.stderr)
        return 1

    osm = _osm_records(elements)
    wikidata = _wikidata_records(bindings)
    # An OSM feature naming a QID in its own `wikidata` tag *is* that Wikidata item, which is
    # the one dedupe signal that needs no distance at all.
    osm_qids = {qid for element in elements if (qid := (element.get("tags") or {}).get("wikidata"))}
    patch = _deduped(wikidata, osm, osm_qids)
    print(
        f"{len(elements)} OSM elements -> {len(osm)} sites; "
        f"{len(bindings)} Wikidata rows -> {len(wikidata)} items -> {len(patch)} after dedupe",
        file=sys.stderr,
    )
    if not osm:
        print("no OpenStreetMap records selected; refusing to write a seed without them", file=sys.stderr)
        return 1

    _print_report(write_records(osm + patch, args.today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
