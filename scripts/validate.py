"""Check records against the pool's rules.

    python scripts/validate.py                    # every record under sites/, as the check runs it
    python scripts/validate.py sites/wikidata/Q14213816.geojson

Exits non-zero on any broken record.

A record is valid when it is a valid DiveJSON dive site once its geometry is folded back into
`position` - the `divejson` package decides that, so the member names, the `other_names` rules
and the depth arithmetic are the format's - and when it keeps the pool's own rules on top:
README.md and CONTRIBUTING.md say what they are and why.
"""

from __future__ import annotations

import argparse
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from divejson import SPEC_VERSION
from divejson.validate import parse_document, validate_document

from pool import (
    CURATED_SOURCES,
    ENTRY_REGISTRIES,
    REGISTRY,
    ROOT,
    SOURCE_OF_REGISTRY,
    identity_of,
    seed_uuid,
    site_files,
)

LICENCE_OF_SOURCE = {
    "openstreetmap": "ODbL-1.0",
    "wikidata": "CC0-1.0",
    "contribution": "CC0-1.0",
    "noaa-florida-keys-moorings": "LicenseRef-US-Gov-PD",
    "noaa-thunder-bay-moorings": "LicenseRef-US-Gov-PD",
    "fwc-artificial-reefs": "LicenseRef-FWC-PD",
}

# What a record may carry: the identity and the structured facts, never what a diver writes
# for themself - `notes`, `tags`, `created_at` - and never `position`, which the geometry is.
_MEMBERS = frozenset(
    {
        "uuid",
        "name",
        "other_names",
        "location",
        "external_ids",
        "depth_from",
        "depth_to",
        "water_type",
        "altitude",
        "entry_types",
        "extensions",
    }
)
_PROVENANCE_MEMBERS = frozenset({"source", "license", "retrieved", "seeded_from"})

_MAX_DECIMALS = 6

# A job summary is capped at 1 MiB; a tree breaking thousands of records needs the count and
# a sample, not every line.
_SUMMARY_LINES = 200

NOT_A_RECORD_PATH = (
    "not a record path: records live at sites/openstreetmap/<node|way|relation>/<id>.geojson, "
    f"sites/wikidata/<Q-id>.geojson, sites/{REGISTRY}/<uuid>.geojson "
    "or sites/<curated source>/<identifier>.geojson"
)


@dataclass
class Result:
    checked: int = 0
    errors: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add(self, path: str, message: str) -> None:
        self.errors[path].append(message)


@dataclass(frozen=True, slots=True)
class _Identity:
    """The parts of a record the cross-record rules read."""

    path: str
    uuid: str
    entries: tuple[tuple[str, str], ...]


def _identity(path: str, feature: Any) -> _Identity | None:
    """None when a record is too broken to compare; the record rules say what is wrong with it."""
    try:
        properties = feature["properties"]
        entries = tuple((entry["registry"], entry["identifier"]) for entry in properties.get("external_ids", []))
        return _Identity(path, properties["uuid"], entries) if isinstance(properties["uuid"], str) else None
    except (KeyError, TypeError, AttributeError):
        return None


def _decimals(value: float) -> int:
    exponent = Decimal(repr(value)).as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _geometry_errors(geometry: Any) -> list[str]:
    if not isinstance(geometry, dict) or set(geometry) != {"type", "coordinates"} or geometry["type"] != "Point":
        return ['geometry must be {"type": "Point", "coordinates": [longitude, latitude]} and nothing else']
    coordinates = geometry["coordinates"]
    if not isinstance(coordinates, list) or len(coordinates) != 2 or not all(_is_number(c) for c in coordinates):
        return ["geometry.coordinates must be two numbers, longitude first"]
    longitude, latitude = coordinates
    errors = []
    if not -180 <= longitude <= 180:
        errors.append(f"longitude {longitude} is out of range; GeoJSON puts longitude first")
    if not -90 <= latitude <= 90:
        errors.append(f"latitude {latitude} is out of range; GeoJSON puts longitude first")
    if longitude == 0 and latitude == 0:
        errors.append("the position is 0, 0 - a missing position, not a dive site")
    for axis, value in (("longitude", longitude), ("latitude", latitude)):
        if _decimals(value) > _MAX_DECIMALS:
            errors.append(f"{axis} {value!r} has more than {_MAX_DECIMALS} decimals; round it to {_MAX_DECIMALS}")
    return errors


def _provenance_errors(provenance: Any, registry: str, identifier: str) -> list[str]:
    if not isinstance(provenance, dict):
        return [f"properties.extensions.{REGISTRY} is required: the record's source and licence"]
    errors = []
    unknown = sorted(set(provenance) - _PROVENANCE_MEMBERS)
    if unknown:
        errors.append(f"properties.extensions.{REGISTRY} carries {', '.join(unknown)}, which the pool does not define")
    source = provenance.get("source")
    expected_source = SOURCE_OF_REGISTRY[registry]
    if source != expected_source:
        errors.append(f"a record under sites/{registry}/ has source {expected_source!r}, not {source!r}")
    licence = provenance.get("license")
    if licence != LICENCE_OF_SOURCE[expected_source]:
        errors.append(f"a {expected_source} record is licensed {LICENCE_OF_SOURCE[expected_source]!r}, not {licence!r}")

    retrieved = provenance.get("retrieved")
    if expected_source == "contribution":
        if "retrieved" in provenance:
            errors.append("a contribution carries no retrieved date; that is a seed's")
        if "seeded_from" in provenance:
            errors.append("a contribution carries no seeded_from; that is a seed's")
    else:
        try:
            date.fromisoformat(retrieved if isinstance(retrieved, str) and len(retrieved) == 10 else "")
        except ValueError:
            errors.append(f"a seed carries the date it was retrieved, as YYYY-MM-DD, not {retrieved!r}")
        if provenance.get("seeded_from") != {"registry": registry, "identifier": identifier}:
            errors.append(f"a seed's seeded_from is the entry its path names, {{{registry}, {identifier}}}")
    return errors


def record_errors(path: str, feature: Any) -> list[str]:
    """The pool's own rules for one parsed record. The DiveJSON half is checked separately, in bulk."""
    identity = identity_of(path)
    if identity is None:
        return [NOT_A_RECORD_PATH]
    registry, identifier = identity

    if not isinstance(feature, dict) or set(feature) != {"type", "geometry", "properties"}:
        return ["a record is one GeoJSON Feature with type, geometry and properties, and nothing else"]
    if feature["type"] != "Feature":
        return ['type must be "Feature"']
    errors = _geometry_errors(feature["geometry"])

    properties = feature["properties"]
    if not isinstance(properties, dict):
        return [*errors, "properties must be an object"]
    unknown = sorted(set(properties) - _MEMBERS)
    if "position" in unknown:
        errors.append("properties carries no position; the geometry is the position")
    if other := [member for member in unknown if member != "position"]:
        errors.append(f"properties carries {', '.join(other)}, which a pool record never holds")

    location = properties.get("location")
    if isinstance(location, dict) and set(location) != {"name"}:
        errors.append("location is the locality's name alone, with no position or box")

    extensions = properties.get("extensions")
    if isinstance(extensions, dict) and set(extensions) - {REGISTRY}:
        errors.append(f"extensions carries only {REGISTRY}")
    provenance = extensions.get(REGISTRY) if isinstance(extensions, dict) else None
    errors.extend(_provenance_errors(provenance, registry, identifier))

    record_uuid = properties.get("uuid")
    if registry == REGISTRY:
        if record_uuid != identifier:
            errors.append(f"a contribution's uuid is its file name, {identifier}")
    elif record_uuid != seed_uuid(registry, identifier):
        errors.append(f"a seed's uuid is {seed_uuid(registry, identifier)}, derived from its path")

    entries = properties.get("external_ids")
    pairs = (
        [(entry.get("registry"), entry.get("identifier")) for entry in entries if isinstance(entry, dict)]
        if isinstance(entries, list)
        else []
    )
    if registry in ENTRY_REGISTRIES and (registry, identifier) not in pairs:
        errors.append(f"a seed carries the entry its path names, {{{registry}, {identifier}}}, in external_ids")
    for curated in sorted({entry_registry for entry_registry, _ in pairs if entry_registry in CURATED_SOURCES}):
        errors.append(f"external_ids names {curated}, a curated source; its identifier is in seeded_from alone")
    if (REGISTRY, record_uuid) in pairs:
        errors.append("external_ids names this record's own uuid")
    return errors


def _as_site(feature: dict[str, Any]) -> dict[str, Any]:
    longitude, latitude = feature["geometry"]["coordinates"]
    return {**feature["properties"], "position": {"latitude": latitude, "longitude": longitude}}


def _divejson_errors(features: dict[str, dict[str, Any]], result: Result) -> None:
    """One document holding every record, so the schema is compiled once rather than per file."""
    paths = list(features)
    document = {
        "format": "divejson",
        "version": SPEC_VERSION,
        "exported_at": "2026-01-01T00:00:00Z",
        "sites": [_as_site(features[path]) for path in paths],
    }
    for issue in validate_document(document):
        match = re.match(r"sites/(\d+)(?:/(.*))?$", issue.path)
        if match is None:
            # Nothing outside `sites` is built from a record, so this is the validator itself.
            result.add("(divejson)", str(issue))
            continue
        member = (match[2] or "").replace("/", ".")
        # Duplicate uuids are reported against the second record by DiveJSON and against
        # both by the cross-record rules below, which name the other file.
        if issue.message.startswith("uuid ") and "already used at" in issue.message:
            continue
        result.add(paths[int(match[1])], f"DiveJSON: {member or 'site'}: {issue.message}")


def _cross_record_errors(checked: set[str], records: dict[str, _Identity], result: Result) -> None:
    by_uuid: dict[str, list[str]] = defaultdict(list)
    by_entry: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in records.values():
        by_uuid[record.uuid].append(record.path)
        for entry in record.entries:
            by_entry[entry].append(record.path)

    for path in sorted(checked):
        record = records.get(path)
        if record is None:
            continue
        for other in by_uuid[record.uuid]:
            if other != path:
                result.add(path, f"uuid {record.uuid} is also {other}'s")
        for entry in record.entries:
            for other in by_entry[entry]:
                if other != path:
                    result.add(path, f"the entry {{{entry[0]}, {entry[1]}}} is also carried by {other}")
            if entry[0] == REGISTRY and entry[1] != record.uuid:
                for other in by_uuid.get(entry[1], []):
                    result.add(path, f"names {other} as merged into it, but that record still exists")


def _load(root: Path, path: str, result: Result) -> Any:
    try:
        return parse_document((root / path).read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        result.add(path, "not UTF-8 text")
    except ValueError as exc:
        result.add(path, f"not valid JSON: {exc}")
    return None


def validate(paths: list[str], root: Path = ROOT) -> Result:
    """Check `paths`, each against the whole tree."""
    result = Result(checked=len(paths))
    checking = set(paths)
    records: dict[str, _Identity] = {}
    for path in site_files(root):
        feature = _load(root, path, Result()) if path not in checking else None
        if feature is not None and (record := _identity(path, feature)) is not None:
            records[path] = record

    valid_shape: dict[str, dict[str, Any]] = {}
    for path in paths:
        if identity_of(path) is None:
            result.add(path, NOT_A_RECORD_PATH)
            continue
        feature = _load(root, path, result)
        if feature is None:
            continue
        for message in record_errors(path, feature):
            result.add(path, message)
        if (record := _identity(path, feature)) is not None:
            records[path] = record
        if isinstance(feature, dict) and not _shape_broken(feature):
            valid_shape[path] = feature

    if valid_shape:
        _divejson_errors(valid_shape, result)
    _cross_record_errors(checking, records, result)
    return result


def _shape_broken(feature: dict[str, Any]) -> bool:
    """Too broken to fold into a DiveJSON site; the pool's own rules have already said why."""
    try:
        coordinates = feature["geometry"]["coordinates"]
        return not (
            isinstance(feature["properties"], dict)
            and isinstance(coordinates, list)
            and len(coordinates) == 2
        )
    except (KeyError, TypeError):
        return True


def _relative(path: str, root: Path) -> str:
    return (Path.cwd() / path).resolve().relative_to(root.resolve()).as_posix()


def _summary(result: Result) -> str:
    lines = ["## The record rules", ""]
    if not result.errors:
        lines.append(f"{result.checked} record(s) checked, all valid.")
    else:
        lines.append(f"{result.checked} record(s) checked; {len(result.errors)} broken.")
        lines.append("")
        listed = [(path, message) for path, messages in sorted(result.errors.items()) for message in messages]
        for path, message in listed[:_SUMMARY_LINES]:
            lines.append(f"- `{path}`: {message}")
        if len(listed) > _SUMMARY_LINES:
            lines.append(f"- and {len(listed) - _SUMMARY_LINES} more; run the script locally for the rest")
    return "\n".join(lines) + "\n"


def _annotate(result: Result) -> None:
    for path, messages in sorted(result.errors.items()):
        for message in messages:
            print(f"::error file={path}::{message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check pool records against the record rules.")
    parser.add_argument("paths", nargs="*", help="records to check; every record under sites/ when none is given")
    args = parser.parse_args(argv)

    result = validate([_relative(path, ROOT) for path in args.paths] or list(site_files()))

    summary = _summary(result)
    print(summary, end="")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        _annotate(result)
    if step_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(summary)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
