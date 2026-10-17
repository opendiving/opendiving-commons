"""Tests for `scripts/seed.py`.

It is tested despite running only by hand because two of its rules fail *silently*: a
selection filter that deletes real dive sites still produces a plausible pool, and a refresh
that overwrites a maintainer's edit loses it without a word.
"""

import json
import uuid
from pathlib import Path

import pytest

import seed
from pool import serialise


def _record(name: str, latitude: float, longitude: float, registry: str = "openstreetmap", identifier: str = "node/1"):
    return seed._Record(name, None, latitude, longitude, registry, identifier)


class TestTheBusinessExclusion:
    @pytest.mark.parametrize(
        "tags",
        [
            {"amenity": "dive_centre"},
            {"shop": "scuba_diving"},
            {"shop": "sports"},
            {"club": "scuba_diving"},
            {"office": "company"},
            # OSM's `;` multi-value convention. Without splitting on it this reads as neither
            # a restaurant nor a dive centre, and the resort ships as a place to dive.
            {"amenity": "restaurant;dive_centre"},
        ],
    )
    def test_a_business_is_not_a_dive_site(self, tags: dict[str, str]):
        """Submersion's bundled catalog skipped this step, and ships `Dive Otago` and
        `Go Dive Pacific` among the first five records of its site list."""
        assert seed._is_business(tags)

    @pytest.mark.parametrize("tags", [{"natural": "reef"}, {"historic": "wreck"}, {"leisure": "divespot"}, {}])
    def test_a_dive_site_is_not_a_business(self, tags: dict[str, str]):
        assert not seed._is_business(tags)


class TestTheIndoorExclusion:
    @pytest.mark.parametrize(
        "tags",
        [
            {"leisure": "sports_centre"},
            {"leisure": "swimming_pool"},
            {"leisure": "fitness_centre"},
            {"leisure": "sports_hall"},
            {"building": "yes"},
            {"building": "school"},
            {"amenity": "school"},
            {"amenity": "community_centre"},
            {"amenity": "sport_school"},
            {"amenity": "public_bath"},
        ],
    )
    def test_an_indoor_facility_is_not_a_dive_site(self, tags: dict[str, str]):
        assert seed._is_indoor(tags)

    @pytest.mark.parametrize("value", ["pitch", "water_park"])
    def test_the_dutch_convention_survives(self, value: str):
        """**The trap in the whole selection rule.** `leisure=pitch` is how Zeeland tags a
        dive site - `Flauwers West`, `Goese Sas`, `Noordbout` - and 35 of its 43 named
        features carry scuba attributes; `water_park` is the same story at 6 of 7. A filter
        that excluded sports-shaped `leisure` values wholesale would delete every one."""
        assert not seed._is_indoor({"leisure": value, "sport": "scuba_diving"})

    def test_a_mapper_saying_it_is_a_divespot_overrides_the_shape(self):
        """A flooded quarry tagged `leisure=sports_centre` because a club runs it is still
        somewhere people dive - which is exactly what rescues `Oolderhuuske` and `Berendonk`."""
        assert not seed._is_indoor({"leisure": "sports_centre", "scuba_diving:divespot": "yes"})
        assert not seed._is_indoor({"building": "yes", "scuba_diving:divespot": "yes"})

    def test_any_other_divespot_value_does_not_rescue(self):
        """`=yes` specifically. The key carries dozens of values that are site names misused
        as the value, and none of those is a mapper asserting anything."""
        assert seed._is_indoor({"leisure": "swimming_pool", "scuba_diving:divespot": "Blue Lagoon"})


class TestSelection:
    def test_a_way_takes_the_centre_overpass_computed(self):
        """`out center;`, never bare `out;`. A way has no position of its own, and the bare
        form is how Submersion's catalog came to carry 356 records with no coordinates."""
        records = seed._osm_records(
            [{"type": "way", "id": 1, "center": {"lat": 1.5, "lon": 2.5}, "tags": {"name": "Wall"}}]
        )

        assert [(r.latitude, r.longitude, r.identifier) for r in records] == [(1.5, 2.5, "way/1")]

    def test_an_element_with_no_position_is_dropped_rather_than_written_at_null_island(self):
        assert seed._osm_records([{"type": "relation", "id": 2, "tags": {"name": "Reef"}}]) == []

    def test_an_unnamed_feature_is_dropped(self):
        assert seed._osm_records([{"type": "node", "id": 3, "lat": 1, "lon": 2, "tags": {"name": "  "}}]) == []

    def test_an_english_name_equal_to_the_local_one_is_not_carried_twice(self):
        records = seed._osm_records(
            [{"type": "node", "id": 4, "lat": 1, "lon": 2, "tags": {"name": "Blue Hole", "name:en": "Blue Hole"}}]
        )

        assert records[0].name_en is None

    def test_an_english_name_that_says_something_new_is_kept(self):
        records = seed._osm_records(
            [{"type": "node", "id": 5, "lat": 1, "lon": 2, "tags": {"name": "砂辺", "name:en": "Sunabe"}}]
        )

        assert (records[0].name, records[0].name_en) == ("砂辺", "Sunabe")

    def test_a_position_is_rounded_to_six_decimals(self):
        """The most the record rules accept."""
        records = seed._osm_records(
            [{"type": "node", "id": 6, "lat": 27.81409234, "lon": 33.92004871, "tags": {"name": "Wreck"}}]
        )

        assert (records[0].latitude, records[0].longitude) == (27.814092, 33.920049)


def _binding(qid: str, label: str, point: str) -> dict:
    return {
        "site": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "siteLabel": {"value": label},
        "coordinate": {"value": point},
    }


class TestTheWikidataPatch:
    def test_an_item_with_several_coordinates_is_one_record_at_the_first(self):
        """The query yields a row per `P625` claim; a dozen items came back two to four times
        each, which as records would be one site several times over."""
        records = seed._wikidata_records(
            [
                _binding("Q1", "Maidstone Rock", "Point(18.46 -34.19)"),
                _binding("Q1", "Maidstone Rock", "Point(18.47 -34.20)"),
                _binding("Q2", "Bells", "Point(18.5 -34.1)"),
            ]
        )

        assert [(r.identifier, r.longitude, r.latitude) for r in records] == [("Q1", 18.46, -34.19), ("Q2", 18.5, -34.1)]

    def test_an_item_with_no_label_is_dropped(self):
        """It answers with its own QID, which is not a name a diver can read."""
        assert seed._wikidata_records([_binding("Q3", "Q3", "Point(1 2)")]) == []

    def test_a_dropped_row_does_not_hide_the_items_next_claim(self):
        records = seed._wikidata_records(
            [_binding("Q4", "Reef", "not a point"), _binding("Q4", "Reef", "Point(3 4)")]
        )

        assert [(r.longitude, r.latitude) for r in records] == [(3.0, 4.0)]

    def test_a_shared_qid_is_the_same_site(self):
        osm = [_record("Blue Hole", 28.57, 34.54)]
        wikidata = [_record("Blue Hole", 28.60, 34.60, "wikidata", "Q123")]

        assert seed._deduped(wikidata, osm, {"Q123"}) == []

    def test_two_records_at_the_same_spot_are_the_same_site(self):
        osm = [_record("Blue Hole", 28.57, 34.54)]
        wikidata = [_record("Anything At All", 28.5701, 34.5401, "wikidata", "Q123")]

        assert seed._deduped(wikidata, osm, set()) == []

    def test_a_kilometre_apart_needs_the_names_to_agree_as_well(self):
        """Deliberately not proximity alone at a kilometre. Two genuinely different sites on
        one reef are routinely that close, and the point of this source is its coverage."""
        osm = [_record("Blue Hole", 28.57, 34.54)]
        near_same_name = [_record("blue hole", 28.576, 34.54, "wikidata", "Q1")]
        near_other_name = [_record("Bells", 28.576, 34.54, "wikidata", "Q2")]

        assert seed._deduped(near_same_name, osm, set()) == []
        assert [r.identifier for r in seed._deduped(near_other_name, osm, set())] == ["Q2"]

    def test_a_site_nowhere_near_the_osm_set_is_kept(self):
        osm = [_record("Blue Hole", 28.57, 34.54)]
        wikidata = [_record("Maidstone Rock", -34.19, 18.46, "wikidata", "Q14213816")]

        assert [r.identifier for r in seed._deduped(wikidata, osm, set())] == ["Q14213816"]


class TestTheRecord:
    def test_the_uuid_is_derived_from_the_fixed_url_string(self):
        """The string is what DECISIONS.md records; a move of the repository must not move it."""
        written = seed.feature(_record("SS Thistlegorm", 27.814092, 33.920048, identifier="node/255316037"), "2026-10-17")

        assert written["properties"]["uuid"] == str(
            uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/opendiving/opendiving-commons/sites/openstreetmap/node/255316037")
        )

    def test_longitude_comes_first(self):
        written = seed.feature(_record("SS Thistlegorm", 27.814092, 33.920048), "2026-10-17")

        assert written["geometry"] == {"type": "Point", "coordinates": [33.920048, 27.814092]}

    @pytest.mark.parametrize(("registry", "identifier", "licence"), [("openstreetmap", "node/1", "ODbL-1.0"), ("wikidata", "Q1", "CC0-1.0")])
    def test_a_seed_states_its_source_and_licence(self, registry: str, identifier: str, licence: str):
        written = seed.feature(_record("Reef", 1.0, 2.0, registry, identifier), "2026-10-17")

        assert written["properties"]["external_ids"] == [{"registry": registry, "identifier": identifier}]
        assert written["properties"]["extensions"] == {
            "opendivingcommons": {"source": registry, "license": licence, "retrieved": "2026-10-17"}
        }

    def test_the_english_name_rides_the_extension(self):
        record = seed._Record("砂辺", "Sunabe", 26.3, 127.7, "openstreetmap", "node/5")

        assert seed.feature(record, "2026-10-17")["properties"]["extensions"]["opendivingcommons"]["name_en"] == "Sunabe"


class TestARerun:
    """A re-run must never overwrite a record a maintainer has edited."""

    def _seeded(self, tmp_path: Path, record) -> Path:
        seed.write_records([record], "2026-10-17", tmp_path)
        return tmp_path / "sites" / record.registry / f"{record.identifier}.geojson"

    def test_a_first_run_writes_the_record_at_its_path(self, tmp_path: Path):
        record = _record("Reef", 1.0, 2.0)

        report = seed.write_records([record], "2026-10-17", tmp_path)

        assert report.written == ["sites/openstreetmap/node/1.geojson"]
        assert (tmp_path / report.written[0]).read_text() == serialise(seed.feature(record, "2026-10-17"))

    def test_an_untouched_record_takes_the_new_retrieved_date(self, tmp_path: Path):
        record = _record("Reef", 1.0, 2.0)
        path = self._seeded(tmp_path, record)

        report = seed.write_records([record], "2026-11-01", tmp_path)

        assert report.refreshed == ["sites/openstreetmap/node/1.geojson"]
        assert json.loads(path.read_text())["properties"]["extensions"]["opendivingcommons"]["retrieved"] == "2026-11-01"

    def test_a_rerun_on_the_same_day_changes_nothing(self, tmp_path: Path):
        record = _record("Reef", 1.0, 2.0)
        self._seeded(tmp_path, record)

        report = seed.write_records([record], "2026-10-17", tmp_path)

        assert (report.written, report.refreshed, report.kept) == ([], [], [])

    def test_a_coarsened_position_survives(self, tmp_path: Path):
        record = _record("Wreck", 1.123456, 2.123456)
        path = self._seeded(tmp_path, record)
        edited = json.loads(path.read_text())
        edited["geometry"]["coordinates"] = [2.12, 1.12]
        path.write_text(serialise(edited))

        report = seed.write_records([record], "2026-11-01", tmp_path)

        assert report.kept == ["sites/openstreetmap/node/1.geojson"]
        assert json.loads(path.read_text())["geometry"]["coordinates"] == [2.12, 1.12]

    def test_an_upstream_change_is_reported_rather_than_applied(self, tmp_path: Path):
        """The seed cannot tell an upstream rename from a maintainer's correction, so it
        touches neither and says so."""
        path = self._seeded(tmp_path, _record("Reef", 1.0, 2.0))
        before = path.read_text()

        report = seed.write_records([_record("Reef North", 1.0, 2.0)], "2026-11-01", tmp_path)

        assert report.kept == ["sites/openstreetmap/node/1.geojson"]
        assert path.read_text() == before

    def test_an_object_a_merge_absorbed_is_not_written_again(self, tmp_path: Path):
        survivor = self._seeded(tmp_path, _record("Reef", 1.0, 2.0))
        merged = json.loads(survivor.read_text())
        merged["properties"]["external_ids"].append({"registry": "openstreetmap", "identifier": "node/2"})
        survivor.write_text(serialise(merged))

        report = seed.write_records(
            [_record("Reef", 1.0, 2.0), _record("The Reef", 1.0001, 2.0, identifier="node/2")], "2026-11-01", tmp_path
        )

        assert report.held == [("sites/openstreetmap/node/2.geojson", "sites/openstreetmap/node/1.geojson")]
        assert not (tmp_path / "sites/openstreetmap/node/2.geojson").exists()

    def test_a_record_gone_upstream_is_reported_and_kept(self, tmp_path: Path):
        path = self._seeded(tmp_path, _record("Reef", 1.0, 2.0))

        report = seed.write_records([_record("Other", 3.0, 4.0, identifier="node/9")], "2026-11-01", tmp_path)

        assert report.gone == ["sites/openstreetmap/node/1.geojson"]
        assert path.exists()

    def test_a_contribution_is_never_called_gone(self, tmp_path: Path):
        contribution = tmp_path / "sites" / "opendivingcommons" / "8c0b6b3e-0000-4000-8000-000000000000.geojson"
        contribution.parent.mkdir(parents=True)
        contribution.write_text("{}")

        report = seed.write_records([_record("Reef", 1.0, 2.0)], "2026-10-17", tmp_path)

        assert report.gone == []
