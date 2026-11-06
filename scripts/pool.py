"""What every script here agrees on: where a record lives and how one is written."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SITES = ROOT / "sites"

# The pool's own registry token: the directory a contribution lives in, the DiveJSON
# extension key its provenance sits under, and the registry a record is named in.
REGISTRY = "opendivingcommons"

# Fixed text rather than derived from wherever the repository lives: a seed's uuid is a
# function of this string, so moving the repository must not change it. DECISIONS.md
# records it.
SEED_UUID_PREFIX = "https://github.com/opendiving/opendiving-commons/sites/"

# The registries whose identifier a record lists in `external_ids`, a public fact a reader can
# follow: `sites/<registry>/<identifier>.geojson`, one identifier form per registry.
ENTRY_REGISTRIES = {
    "openstreetmap": re.compile(r"(node|way|relation)/[1-9][0-9]*"),
    "wikidata": re.compile(r"Q[1-9][0-9]*"),
}

# The curated sources: public datasets, each named publisher, place where the publisher has
# several, then subject. The token is the record's directory, its `source` and its
# `seeded_from.registry`. Its identifier is provenance and stays in `seeded_from`: no record
# lists one in `external_ids`, where it would show as raw text for what is mostly a slug of the
# site's name.
_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
CURATED_SOURCES = {
    "noaa-florida-keys-moorings": _SLUG,
    "noaa-thunder-bay-moorings": _SLUG,
    "fwc-artificial-reefs": re.compile(r"[A-Z]{2}[0-9]{4}"),
}

_IDENTIFIER_FORMS = {
    **ENTRY_REGISTRIES,
    **CURATED_SOURCES,
    REGISTRY: re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
}

SOURCE_OF_REGISTRY = {
    "openstreetmap": "openstreetmap",
    "wikidata": "wikidata",
    **{token: token for token in CURATED_SOURCES},
    REGISTRY: "contribution",
}


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
    """The one text a record is written as, so that "unchanged" is a byte comparison."""
    return json.dumps(feature, ensure_ascii=False, indent=2) + "\n"
