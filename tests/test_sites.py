"""The tree itself: the seed's size, and every record holding the rules."""

import validate
from pool import site_files

# The seed's records, not the pool's: every merged contribution moves the total, and a pin
# on it would fail on the first share. A re-run of the seed moves this on purpose, and the
# pull request that carries the re-run says why the number moved.
SEED_RECORDS = 3712


def test_the_seed_count_is_pinned():
    seeds = [path for path in site_files() if path.startswith(("sites/openstreetmap/", "sites/wikidata/"))]

    assert len(seeds) == SEED_RECORDS


def test_every_record_holds_the_rules():
    paths = list(site_files())

    result = validate.validate(paths, set())

    assert dict(result.errors) == {}
