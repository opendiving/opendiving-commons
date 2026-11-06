"""The tree itself: the seed's size, and every record holding the rules."""

import validate
from pool import site_files

# The seed's records, not the pool's: every accepted contribution moves the total, and lands
# under `sites/opendivingcommons/`, which this never counts. Nothing adds or removes a seed.
SEED_RECORDS = 3712


def test_the_seed_count_is_pinned():
    seeds = [path for path in site_files() if path.startswith(("sites/openstreetmap/", "sites/wikidata/"))]

    assert len(seeds) == SEED_RECORDS


def test_every_record_holds_the_rules():
    paths = list(site_files())

    result = validate.validate(paths)

    assert dict(result.errors) == {}
