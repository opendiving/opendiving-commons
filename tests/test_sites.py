"""The tree itself: every record holding the rules, and what travels beside the records."""

from pathlib import Path

import validate
from pool import ROOT, site_files

FLORIDA_METADATA = "sources/fwc-artificial-reefs/metadata.xml"


def test_every_record_holds_the_rules():
    paths = list(site_files())

    result = validate.validate(paths)

    assert dict(result.errors) == {}


def test_the_florida_registers_metadata_travels_with_the_repository():
    metadata = (ROOT / FLORIDA_METADATA).read_text(encoding="utf-8")

    assert "This data set is in the public domain" in metadata
    assert "Metadata must be distributed with the data set." in metadata


def test_the_readme_links_that_metadata():
    assert f"]({FLORIDA_METADATA})" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_rules_read_sites_alone(tmp_path: Path):
    document = tmp_path / FLORIDA_METADATA
    document.parent.mkdir(parents=True)
    document.write_text("<metadata/>", encoding="utf-8")

    assert list(site_files(tmp_path)) == []
    assert validate.validate(list(site_files(tmp_path)), tmp_path).errors == {}
