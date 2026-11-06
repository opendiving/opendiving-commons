"""Tests for `scripts/validate.py`, the record rules every record is held to."""

import copy
from pathlib import Path

import pytest

import validate
from pool import seed_uuid, serialise

CONTRIBUTION_UUID = "8c0b6b3e-1f2a-4b3c-9d4e-5f6a7b8c9d0e"
CONTRIBUTION_PATH = f"sites/opendivingcommons/{CONTRIBUTION_UUID}.geojson"
SEED_PATH = "sites/openstreetmap/node/255316037.geojson"


def _seed() -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [33.920048, 27.814092]},
        "properties": {
            "uuid": seed_uuid("openstreetmap", "node/255316037"),
            "name": "SS Thistlegorm",
            "external_ids": [{"registry": "openstreetmap", "identifier": "node/255316037"}],
            "extensions": {
                "opendivingcommons": {
                    "source": "openstreetmap",
                    "license": "ODbL-1.0",
                    "retrieved": "2026-10-17",
                    "seeded_from": {"registry": "openstreetmap", "identifier": "node/255316037"},
                }
            },
        },
    }


def _contribution() -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [34.53851, 28.57211]},
        "properties": {
            "uuid": CONTRIBUTION_UUID,
            "name": "Bells",
            "other_names": ["The Bells"],
            "location": {"name": "Dahab"},
            "depth_from": 5,
            "depth_to": 30,
            "water_type": "salt",
            "entry_types": ["shore"],
            "extensions": {"opendivingcommons": {"source": "contribution", "license": "CC0-1.0"}},
        },
    }


def _errors(path: str, feature: dict) -> list[str]:
    return validate.record_errors(path, feature)


def _tree(tmp_path: Path, records: dict[str, dict]) -> Path:
    for path, feature in records.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialise(feature), encoding="utf-8")
    return tmp_path


class TestAValidRecord:
    def test_a_seed_passes(self):
        assert _errors(SEED_PATH, _seed()) == []

    def test_a_contribution_passes(self):
        assert _errors(CONTRIBUTION_PATH, _contribution()) == []

    def test_a_seed_may_name_its_locality_and_other_names(self):
        feature = _seed()
        feature["properties"] |= {"location": {"name": "Red Sea, Egypt"}, "other_names": ["Thistlegorm"]}

        assert _errors(SEED_PATH, feature) == []

    def test_both_pass_the_divejson_half_too(self, tmp_path: Path):
        root = _tree(tmp_path, {SEED_PATH: _seed(), CONTRIBUTION_PATH: _contribution()})

        result = validate.validate([SEED_PATH, CONTRIBUTION_PATH], root)

        assert dict(result.errors) == {}


class TestThePath:
    @pytest.mark.parametrize(
        "path",
        [
            "sites/openstreetmap/255316037.geojson",
            "sites/openstreetmap/node/255316037.json",
            "sites/wikidata/14213816.geojson",
            "sites/opendivingcommons/not-a-uuid.geojson",
            "sites/opendivingcommons/8C0B6B3E-1F2A-4B3C-9D4E-5F6A7B8C9D0E.geojson",
            "sites/somewhere/x.geojson",
            "sites/README.md",
        ],
    )
    def test_a_file_off_the_record_paths_is_refused(self, path: str):
        assert any("not a record path" in error for error in _errors(path, _seed()))

    def test_a_seed_uuid_must_be_the_one_its_path_derives(self):
        feature = _seed()
        feature["properties"]["uuid"] = CONTRIBUTION_UUID

        assert any("derived from its path" in error for error in _errors(SEED_PATH, feature))

    def test_a_contributions_uuid_is_its_file_name(self):
        feature = _contribution()
        feature["properties"]["uuid"] = "00000000-0000-4000-8000-000000000000"

        assert any("its file name" in error for error in _errors(CONTRIBUTION_PATH, feature))

    def test_a_seed_carries_the_entry_its_path_names(self):
        feature = _seed()
        feature["properties"]["external_ids"] = [{"registry": "wikidata", "identifier": "Q1"}]

        assert any("the entry its path names" in error for error in _errors(SEED_PATH, feature))


class TestTheGeometry:
    @pytest.mark.parametrize(
        ("coordinates", "fragment"),
        [
            ([27.814092, 233.920048], "out of range"),
            ([200.0, 27.8], "longitude 200.0 is out of range"),
            ([0, 0], "0, 0"),
            ([33.9200481, 27.814092], "more than 6 decimals"),
            ([33.92, 27.81, 4.0], "two numbers"),
            ([True, 27.81], "two numbers"),
            (["33.92", 27.81], "two numbers"),
        ],
    )
    def test_a_bad_position_is_refused(self, coordinates: list, fragment: str):
        feature = _seed()
        feature["geometry"]["coordinates"] = coordinates

        assert any(fragment in error for error in _errors(SEED_PATH, feature))

    def test_six_decimals_and_whole_numbers_are_fine(self):
        feature = _seed()
        feature["geometry"]["coordinates"] = [34, -27.000001]

        assert _errors(SEED_PATH, feature) == []

    def test_anything_but_a_point_is_refused(self):
        feature = _seed()
        feature["geometry"] = {"type": "MultiPoint", "coordinates": [[33.92, 27.81]]}

        assert any("Point" in error for error in _errors(SEED_PATH, feature))

    def test_a_feature_collection_is_not_a_record(self):
        assert _errors(SEED_PATH, {"type": "FeatureCollection", "features": [_seed()]}) == [
            "a record is one GeoJSON Feature with type, geometry and properties, and nothing else"
        ]


class TestWhatARecordCarries:
    @pytest.mark.parametrize(
        ("member", "value"),
        [("notes", "gate code 1234"), ("tags", ["mine"]), ("created_at", "2026-10-17T10:00:00Z")],
    )
    def test_nothing_a_diver_writes_for_themself(self, member: str, value):
        feature = _contribution()
        feature["properties"][member] = value

        assert any(member in error for error in _errors(CONTRIBUTION_PATH, feature))

    def test_no_position_beside_the_geometry(self):
        feature = _seed()
        feature["properties"]["position"] = {"latitude": 27.8, "longitude": 33.9}

        assert any("the geometry is the position" in error for error in _errors(SEED_PATH, feature))

    def test_the_locality_is_a_name_alone(self):
        feature = _contribution()
        feature["properties"]["location"] = {"name": "Dahab", "position": {"latitude": 28.5, "longitude": 34.5}}

        assert any("name alone" in error for error in _errors(CONTRIBUTION_PATH, feature))

    def test_no_other_extension(self):
        feature = _contribution()
        feature["properties"]["extensions"]["opendiving"] = {"anything": 1}

        assert any("extensions carries only" in error for error in _errors(CONTRIBUTION_PATH, feature))

    def test_a_contribution_may_carry_registry_entries(self):
        """A review can add one, and acceptance holds it to the cross-record rule."""
        feature = _contribution()
        feature["properties"]["external_ids"] = [{"registry": "openstreetmap", "identifier": "node/1"}]

        assert _errors(CONTRIBUTION_PATH, feature) == []

    def test_a_merged_contribution_may_carry_the_absorbed_ones_uuid(self):
        feature = _contribution()
        feature["properties"]["external_ids"] = [
            {"registry": "opendivingcommons", "identifier": "11111111-2222-4333-8444-555555555555"}
        ]

        assert _errors(CONTRIBUTION_PATH, feature) == []

    def test_no_record_names_its_own_uuid(self):
        feature = _contribution()
        feature["properties"]["external_ids"] = [{"registry": "opendivingcommons", "identifier": CONTRIBUTION_UUID}]

        assert any("own uuid" in error for error in _errors(CONTRIBUTION_PATH, feature))


class TestTheProvenance:
    def test_it_is_required(self):
        feature = _seed()
        del feature["properties"]["extensions"]

        assert any("is required" in error for error in _errors(SEED_PATH, feature))

    @pytest.mark.parametrize(
        ("path", "make", "change", "fragment"),
        [
            (SEED_PATH, _seed, {"source": "contribution"}, "source 'openstreetmap'"),
            (SEED_PATH, _seed, {"license": "CC0-1.0"}, "licensed 'ODbL-1.0'"),
            (CONTRIBUTION_PATH, _contribution, {"license": "ODbL-1.0"}, "licensed 'CC0-1.0'"),
            (CONTRIBUTION_PATH, _contribution, {"retrieved": "2026-10-17"}, "no retrieved date"),
            (CONTRIBUTION_PATH, _contribution, {"seeded_from": {"registry": "wikidata"}}, "no seeded_from"),
            (SEED_PATH, _seed, {"retrieved": "17 October"}, "YYYY-MM-DD"),
            (SEED_PATH, _seed, {"retrieved": "2026-02-30"}, "YYYY-MM-DD"),
            (SEED_PATH, _seed, {"seeded_from": {"registry": "openstreetmap", "identifier": "node/1"}}, "seeded_from"),
            (SEED_PATH, _seed, {"seeded_from": "openstreetmap"}, "seeded_from"),
            (SEED_PATH, _seed, {"name_en": "The Thistlegorm"}, "does not define"),
            (SEED_PATH, _seed, {"country": "Egypt"}, "does not define"),
        ],
    )
    def test_its_rules(self, path: str, make, change: dict, fragment: str):
        feature = make()
        feature["properties"]["extensions"]["opendivingcommons"].update(change)

        assert any(fragment in error for error in _errors(path, feature))

    def test_a_seed_says_what_it_was_seeded_from(self):
        feature = _seed()
        del feature["properties"]["extensions"]["opendivingcommons"]["seeded_from"]

        assert any("seeded_from" in error for error in _errors(SEED_PATH, feature))

    def test_a_wikidata_seed_is_cc0(self):
        feature = _seed()
        feature["properties"]["uuid"] = seed_uuid("wikidata", "Q14213816")
        feature["properties"]["external_ids"] = [{"registry": "wikidata", "identifier": "Q14213816"}]
        feature["properties"]["extensions"]["opendivingcommons"].update(
            source="wikidata", license="CC0-1.0", seeded_from={"registry": "wikidata", "identifier": "Q14213816"}
        )

        assert _errors("sites/wikidata/Q14213816.geojson", feature) == []


class TestTheDivejsonHalf:
    def test_the_formats_own_rules_apply(self, tmp_path: Path):
        """`depth_from <= depth_to` and the `other_names` rules are DiveJSON's, not the pool's."""
        feature = _contribution()
        feature["properties"]["depth_from"] = 40
        feature["properties"]["other_names"] = ["bells"]
        root = _tree(tmp_path, {CONTRIBUTION_PATH: feature})

        errors = validate.validate([CONTRIBUTION_PATH], root).errors[CONTRIBUTION_PATH]

        assert any("depth" in error for error in errors)
        assert any("other_names" in error for error in errors)

    def test_an_unknown_enum_value_is_refused(self, tmp_path: Path):
        feature = _contribution()
        feature["properties"]["water_type"] = "salty"
        root = _tree(tmp_path, {CONTRIBUTION_PATH: feature})

        assert validate.validate([CONTRIBUTION_PATH], root).errors[CONTRIBUTION_PATH]

    def test_a_duplicate_member_is_refused(self, tmp_path: Path):
        target = tmp_path / CONTRIBUTION_PATH
        target.parent.mkdir(parents=True)
        target.write_text(serialise(_contribution()).replace('"name": "Bells",', '"name": "Bells", "name": "Other",'))

        errors = validate.validate([CONTRIBUTION_PATH], tmp_path).errors[CONTRIBUTION_PATH]

        assert any("duplicate member" in error for error in errors)


class TestAcrossRecords:
    def test_two_records_carrying_one_entry_are_refused(self, tmp_path: Path):
        survivor = _seed()
        survivor["properties"]["external_ids"].append({"registry": "openstreetmap", "identifier": "node/2"})
        absorbed = copy.deepcopy(_seed())
        absorbed["properties"]["uuid"] = seed_uuid("openstreetmap", "node/2")
        absorbed["properties"]["external_ids"] = [{"registry": "openstreetmap", "identifier": "node/2"}]
        root = _tree(tmp_path, {SEED_PATH: survivor, "sites/openstreetmap/node/2.geojson": absorbed})

        errors = validate.validate([SEED_PATH], root).errors[SEED_PATH]

        assert errors == ["the entry {openstreetmap, node/2} is also carried by sites/openstreetmap/node/2.geojson"]

    def test_a_merge_must_delete_the_record_it_absorbed(self, tmp_path: Path):
        other_uuid = "11111111-2222-4333-8444-555555555555"
        survivor = _contribution()
        survivor["properties"]["external_ids"] = [{"registry": "opendivingcommons", "identifier": other_uuid}]
        absorbed = _contribution()
        absorbed["properties"]["uuid"] = other_uuid
        root = _tree(tmp_path, {CONTRIBUTION_PATH: survivor, f"sites/opendivingcommons/{other_uuid}.geojson": absorbed})

        errors = validate.validate([CONTRIBUTION_PATH], root).errors[CONTRIBUTION_PATH]

        assert any("still exists" in error for error in errors)


def test_a_stray_file_under_sites_is_named_as_one(tmp_path: Path):
    (tmp_path / "sites").mkdir()
    (tmp_path / "sites" / "notes.txt").write_text("not json")

    assert validate.validate(["sites/notes.txt"], tmp_path).errors["sites/notes.txt"] == [validate.NOT_A_RECORD_PATH]
