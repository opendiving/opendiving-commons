"""Bring `sites/` in line with what the hosted instance serves.

    python scripts/publish.py                                  # the hosted instance's export
    python scripts/publish.py http://localhost:8000/api/v1/commons/dive-sites

The instance holds the records and this repository is their published copy. This only writes
the working tree; `land.py` is what commits it, and `.github/workflows/publish.yml` runs both.

**It never removes a file.** Nothing removes a Commons record, so an export that is not a 200
`FeatureCollection`, or that lacks a record the tree holds, is a fault at the other end: the run
fails having written nothing, which is what keeps an instance answering 404, or an error body
read as an empty list, from emptying the repository.

It also keeps the schedule alive: once `HEARTBEAT_DAYS` have passed since the last commit it
rewrites `published.json`, and DECISIONS.md says why.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pool import REGISTRY, ROOT, identity_of, path_of, serialise, site_files

EXPORT_URL = "https://opendiving.app/api/v1/commons/dive-sites"

# It names the project and nobody in it.
USER_AGENT = "OpenDiving-Commons-publish/0.1 (https://github.com/opendiving/opendiving-commons)"

_FETCH_TIMEOUT_SECONDS = 120

STAMP = "published.json"

# GitHub disables a schedule after 60 days without repository activity.
HEARTBEAT_DAYS = 30


class PublishError(Exception):
    """The export cannot be published, and nothing was written."""


def fetch(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise PublishError(f"{url} answered {response.status}")
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PublishError(f"{url} could not be read: {exc}") from exc


def record_path(feature: Any) -> str:
    """Where a record lives: a seed where its provenance says, a contribution by its uuid.

    The answer comes off the network and becomes a path to write, so only a record path will do.
    """
    try:
        properties = feature["properties"]
        seeded_from = properties["extensions"][REGISTRY].get("seeded_from")
        path = (
            path_of(seeded_from["registry"], seeded_from["identifier"])
            if seeded_from
            else path_of(REGISTRY, properties["uuid"])
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise PublishError(f"a feature names no place in the tree: {feature!r}") from exc
    if identity_of(path) is None:
        raise PublishError(f"a feature names a path that is not a record's: {path!r}")
    return path


def records_of(collection: Any) -> dict[str, str]:
    """`{path: text}` for every record the export holds."""
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise PublishError("the export is not a FeatureCollection")
    features = collection.get("features")
    if not isinstance(features, list):
        raise PublishError("the export carries no list of features")
    records: dict[str, str] = {}
    for feature in features:
        path = record_path(feature)
        if path in records:
            raise PublishError(f"the export holds two records at {path}")
        records[path] = serialise(feature)
    return records


def write_records(records: dict[str, str], root: Path = ROOT) -> list[str]:
    """Bring the tree in line with `records`, and say which files changed."""
    missing = [path for path in site_files(root) if path not in records]
    if missing:
        raise PublishError(f"the export lacks {len(missing)} record(s) the tree holds, {missing[0]} among them")
    written = []
    for path, text in records.items():
        target = root / path
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            written.append(path)
    return written


def stamp_is_due(last_commit: date, today: date) -> bool:
    return (today - last_commit).days >= HEARTBEAT_DAYS


def _last_commit(root: Path) -> date:
    seconds = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--format=%ct", "HEAD"], check=True, capture_output=True, text=True
    ).stdout
    return datetime.fromtimestamp(int(seconds), UTC).date()


def write_stamp(today: date, held: int, root: Path = ROOT) -> None:
    text = json.dumps({"checked": today.isoformat(), "records": held}, indent=2) + "\n"
    (root / STAMP).write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("export", nargs="?", default=EXPORT_URL, help="the address of the export")
    args = parser.parse_args(argv)

    try:
        records = records_of(fetch(args.export))
        held = sum(1 for _ in site_files(root))
        written = write_records(records, root)
    except PublishError as exc:
        print(f"publish failed: {exc}", file=sys.stderr)
        return 1
    print(f"{len(records)} record(s) in the export, {len(written)} written")

    today = datetime.now(UTC).date()
    if stamp_is_due(_last_commit(root), today):
        write_stamp(today, held, root)
        print(f"{HEARTBEAT_DAYS} days since the last commit: stamped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
