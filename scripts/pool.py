"""What every script here agrees on: where a record lives, how one is read, and which changed."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SITES = ROOT / "sites"

REPOSITORY = "opendiving/opendiving-commons"

# The pool's own registry token: the directory a contribution lives in, the DiveJSON
# extension key its provenance sits under, and the registry a diver's site names it in.
REGISTRY = "opendivingcommons"

# Fixed text rather than derived from wherever the repository lives: a seed's uuid is a
# function of this string, so moving the repository must not change it. DECISIONS.md
# records it.
SEED_UUID_PREFIX = "https://github.com/opendiving/opendiving-commons/sites/"

# `sites/<registry>/<identifier>.geojson`, one identifier form per registry the pool holds.
_IDENTIFIER_FORMS = {
    "openstreetmap": re.compile(r"(node|way|relation)/[1-9][0-9]*"),
    "wikidata": re.compile(r"Q[1-9][0-9]*"),
    REGISTRY: re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
}

SOURCE_OF_REGISTRY = {"openstreetmap": "openstreetmap", "wikidata": "wikidata", REGISTRY: "contribution"}


def seed_uuid(registry: str, identifier: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{SEED_UUID_PREFIX}{registry}/{identifier}"))


def path_of(registry: str, identifier: str) -> str:
    return f"sites/{registry}/{identifier}.geojson"


def identity_of(path: str) -> tuple[str, str] | None:
    """The `(registry, identifier)` a path under `sites/` names, or None for any other path."""
    match = re.fullmatch(r"sites/(?P<registry>[^/]+)/(?P<identifier>.+)\.geojson", path)
    if match is None:
        return None
    form = _IDENTIFIER_FORMS.get(match["registry"])
    if form is None or not form.fullmatch(match["identifier"]):
        return None
    return match["registry"], match["identifier"]


def site_files(root: Path = ROOT) -> Iterator[str]:
    """Every file under `sites/`, record or not, as a repository-relative path."""
    sites = root / "sites"
    if not sites.is_dir():
        return
    for path in sorted(sites.rglob("*")):
        if path.is_file():
            yield path.relative_to(root).as_posix()


def serialise(feature: dict[str, Any]) -> str:
    """The one text a seed writes, so that "unchanged since the seed wrote it" is a byte comparison."""
    return json.dumps(feature, ensure_ascii=False, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class Record:
    """The parts of a record that the dedup report and the cross-record rules read."""

    path: str
    uuid: str
    name: str
    aliases: tuple[str, ...]
    latitude: float
    longitude: float
    source: str
    entries: tuple[tuple[str, str], ...]


def summarise(path: str, feature: Any) -> Record | None:
    """A Record from a parsed feature, or None when it is too broken to compare.

    The validator says what is wrong with a broken one; everything else only needs to skip it.
    """
    try:
        properties = feature["properties"]
        longitude, latitude = feature["geometry"]["coordinates"]
        name = properties["name"]
        extension = (properties.get("extensions") or {}).get(REGISTRY) or {}
        aliases = [name, *properties.get("other_names", [])]
        # The English name is an alias like any other to a reviewer: a contribution written
        # in Latin letters next to a seed named in Japanese matches on it or not at all.
        if extension.get("name_en"):
            aliases.append(extension["name_en"])
        entries = tuple((entry["registry"], entry["identifier"]) for entry in properties.get("external_ids", []))
        if not isinstance(name, str) or not isinstance(properties["uuid"], str):
            return None
        return Record(
            path=path,
            uuid=properties["uuid"],
            name=name,
            aliases=tuple(alias for alias in aliases if isinstance(alias, str)),
            latitude=float(latitude),
            longitude=float(longitude),
            source=str(extension.get("source", "")),
            entries=entries,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def changed_files(base: str, root: Path = ROOT) -> dict[str, str]:
    """`{path: status}` for every file changed between `base` and HEAD, status A, M or D.

    `--no-renames`, so that a moved record reads as the deletion and the addition it is: the
    path is the identity, and a new path is a new record to every rule.
    """
    output = subprocess.run(
        ["git", "-C", str(root), "diff", "--no-renames", "--name-status", "-z", base, "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    fields = output.split("\0")
    return {path: status[:1] for status, path in zip(fields[0::2], fields[1::2], strict=False) if path}
