"""Tests for `scripts/dedup.py`, the near-duplicate report.

The thresholds are floors calibrated on the catalogue the pool was seeded from; these pin the
behaviour each one was chosen for, so that tuning one is a visible decision.
"""

import math

import pytest

import dedup
from pool import Record

_METRES_PER_DEGREE_LATITUDE = 111_195.0


def _site(name: str, north_metres: float = 0.0, *, path: str | None = None, aliases: tuple[str, ...] = ()) -> Record:
    return Record(
        path=path or f"sites/opendivingcommons/{name}-{north_metres}.geojson",
        uuid=f"{name}-{north_metres}",
        name=name,
        aliases=(name, *aliases),
        latitude=28.5 + north_metres / _METRES_PER_DEGREE_LATITUDE,
        longitude=34.5,
        source="openstreetmap",
        entries=(),
    )


def _flag(new: Record, existing: Record):
    found = dedup.flags([existing, new], {new.path})
    return found[0] if found else None


class TestTheRules:
    def test_an_unrelated_name_fifty_metres_away_is_not_flagged(self):
        """Most close pairs are differently named features of one lake or one reef."""
        assert _flag(_site("Bells", 50), _site("Blue Hole")) is None

    def test_anything_within_twenty_metres_is_flagged(self):
        flag = _flag(_site("Canyon", 15), _site("Blue Hole"))

        assert flag is not None and flag.rule == "within 20 m"

    def test_the_same_name_one_hundred_and_fifty_metres_away_is_flagged_as_similar(self):
        flag = _flag(_site("Blue Hole", 150), _site("Blue Hole"))

        assert flag is not None and flag.rule == "similar name within 200 m"

    def test_shark_point_four_hundred_kilometres_away_is_not_flagged(self):
        """`Shark Point` is in four countries and never nearer itself than 300 km."""
        assert _flag(_site("Shark Point", 400_000), _site("Shark Point")) is None

    def test_the_same_name_two_kilometres_away_is_flagged(self):
        flag = _flag(_site("SS Thistlegorm", 2_000), _site("SS Thistlegorm"))

        assert flag is not None and flag.rule == "same name within 5 km"

    def test_a_generic_name_two_kilometres_away_is_not_flagged(self):
        """The seven `Diving Spot` placeholders of one archipelago."""
        assert _flag(_site("Diving Spot", 2_000), _site("Diving Spot")) is None

    def test_another_name_is_compared_as_an_alias(self):
        flag = _flag(_site("Thistlegorm", 2_000, aliases=("SS Thistlegorm",)), _site("SS Thistlegorm"))

        assert flag is not None and flag.rule == "same name within 5 km"

    def test_qualifier_siblings_are_flagged_with_a_note(self):
        """`Housereef West` and `Housereef East` are similar names and two sites."""
        flag = _flag(_site("Housereef West", 120), _site("Housereef East"))

        assert flag is not None and flag.note is not None

    def test_a_changed_record_is_never_its_own_neighbour(self):
        record = _site("Blue Hole")

        assert dedup.flags([record], {record.path}) == []


class TestSimilarNames:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("Blue Hole", "blue hole"),
            ("Umbria", "SS Umbria, Wreck"),
            ("Marsa Nakari South reef", "Marsa Nakari North reef"),
            ("Ras Ghozlani", "Ras el-Ghazlani"),
            ("Café del Mar", "Cafe del Mar"),
        ],
    )
    def test_similar(self, a: str, b: str):
        assert dedup._names_similar(dedup.normalise(a), dedup.normalise(b))

    @pytest.mark.parametrize(("a", "b"), [("Bells", "Canyon"), ("The Alternatives", "Shark Point"), ("Di", "Dive")])
    def test_not_similar(self, a: str, b: str):
        assert not dedup._names_similar(dedup.normalise(a), dedup.normalise(b))


class TestNormalising:
    def test_accents_case_and_punctuation_go(self):
        assert dedup.normalise("  Café-du-Port, (Nord)!") == "cafe du port nord"

    def test_a_name_in_another_script_survives(self):
        """An ASCII strip empties every name with no Latin letter, and then they all match."""
        assert dedup.normalise("砂辺") == "砂辺"
        assert dedup.normalise("砂辺") != dedup.normalise("真栄田岬")


def test_the_distance_is_a_haversine():
    a = _site("A")
    b = Record("b", "b", "B", ("B",), a.latitude, a.longitude + 1, "openstreetmap", ())

    assert dedup.metres_between(a, b) == pytest.approx(111_195 * math.cos(math.radians(28.5)), rel=1e-3)


class TestTheReport:
    def test_a_changed_record_gets_both_links_and_its_neighbours(self):
        new = _site("Blue Hole", 150, path="sites/opendivingcommons/new.geojson")
        existing = _site("Blue Hole", path="sites/openstreetmap/node/1.geojson")

        text = dedup.report([existing, new], {new.path})

        assert "https://github.com/opendiving/opendiving-commons/blob/main/sites/opendivingcommons/new.geojson" in text
        assert "https://www.openstreetmap.org/?mlat=" in text
        assert "| Blue Hole | 150 m | openstreetmap | similar name within 200 m |" in text

    def test_a_fork_links_to_its_own_branch(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DEDUP_HEAD_REPOSITORY", "diver/opendiving-commons")
        monkeypatch.setenv("DEDUP_HEAD_SHA", "abc123")
        new = _site("Bells", path="sites/opendivingcommons/new.geojson")

        assert "https://github.com/diver/opendiving-commons/blob/abc123/sites/opendivingcommons/new.geojson" in dedup.report(
            [new], {new.path}
        )

    def test_a_record_with_no_neighbour_says_so(self):
        new = _site("Bells")

        assert "No existing record nearby" in dedup.report([new], {new.path})

    def test_a_huge_change_is_counted_rather_than_listed(self):
        records = [_site(f"Site {index}", index * 1_000) for index in range(60)]

        text = dedup.report(records, {record.path for record in records})

        assert "Too many changed records" in text
        assert "###" not in text
