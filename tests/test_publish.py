"""Tests for `scripts/publish.py`. What matters here fails quietly: an export that empties the
repository, a path off the network written anywhere, a schedule that stops."""

import json
import os
import subprocess
import threading
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import publish
from pool import seed_uuid, serialise

UUID = "8c0b6b3e-1f2a-4b3c-9d4e-5f6a7b8c9d0e"
SEED_PATH = "sites/openstreetmap/node/255316037.geojson"
CONTRIBUTION_PATH = f"sites/opendivingcommons/{UUID}.geojson"


def _seed(name: str = "SS Thistlegorm") -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [33.920048, 27.814092]},
        "properties": {
            "uuid": seed_uuid("openstreetmap", "node/255316037"),
            "name": name,
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
            "uuid": UUID,
            "name": "Bells",
            "extensions": {"opendivingcommons": {"source": "contribution", "license": "CC0-1.0"}},
        },
    }


def _curated() -> dict:
    token, identifier = "fwc-artificial-reefs", "BA0001"
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-81.2, 24.5]},
        "properties": {
            "uuid": seed_uuid(token, identifier),
            "name": "USS Vandenberg",
            "extensions": {
                "opendivingcommons": {
                    "source": token,
                    "license": "LicenseRef-FWC-PD",
                    "retrieved": "2026-11-06",
                    "seeded_from": {"registry": token, "identifier": identifier},
                }
            },
        },
    }


def _collection(*features: dict) -> dict:
    return {"type": "FeatureCollection", "licence": "ODbL 1.0", "features": list(features)}


def _tree(root: Path, *features: dict) -> dict[str, str]:
    records = publish.records_of(_collection(*features))
    publish.write_records(records, root)
    return records


class TestWhereARecordGoes:
    def test_a_seed_goes_where_its_provenance_says(self):
        assert publish.record_path(_seed()) == SEED_PATH

    def test_a_contribution_goes_under_the_pools_own_directory_by_its_uuid(self):
        assert publish.record_path(_contribution()) == CONTRIBUTION_PATH

    def test_a_curated_record_goes_where_its_provenance_says(self):
        assert publish.record_path(_curated()) == "sites/fwc-artificial-reefs/BA0001.geojson"

    @pytest.mark.parametrize(
        "seeded_from",
        [
            {"registry": "openstreetmap", "identifier": "../../../.github/workflows/publish"},
            {"registry": "fwc-artificial-reefs", "identifier": "../../../.github/workflows/publish"},
            {"registry": "noaa-florida-keys-moorings", "identifier": "french-reef\n"},
            {"registry": "../.github", "identifier": "Q1"},
            {"registry": "openstreetmap", "identifier": "node/1\n"},
            {"registry": "somewhere", "identifier": "Q1"},
            {"registry": "openstreetmap"},
            "openstreetmap",
        ],
    )
    def test_nothing_but_a_record_path_is_written(self, seeded_from):
        feature = _seed()
        feature["properties"]["extensions"]["opendivingcommons"]["seeded_from"] = seeded_from

        with pytest.raises(publish.PublishError):
            publish.record_path(feature)

    @pytest.mark.parametrize("uuid", ["../../README", "not-a-uuid", None])
    def test_a_contributions_uuid_has_to_be_one(self, uuid):
        feature = _contribution()
        feature["properties"]["uuid"] = uuid

        with pytest.raises(publish.PublishError):
            publish.record_path(feature)


class TestTheExportsShape:
    @pytest.mark.parametrize(
        "body",
        [
            [],
            {"detail": "Not found"},
            {"type": "Feature"},
            {"type": "FeatureCollection"},
            {"type": "FeatureCollection", "features": {}},
            {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
        ],
    )
    def test_anything_but_a_feature_collection_of_records_is_refused(self, body):
        with pytest.raises(publish.PublishError):
            publish.records_of(body)

    def test_two_records_at_one_path_are_refused(self):
        with pytest.raises(publish.PublishError, match="two records"):
            publish.records_of(_collection(_seed(), _seed("Thistlegorm")))


class TestBringingTheTreeInLine:
    def test_it_adds_and_rewrites(self, tmp_path: Path):
        _tree(tmp_path, _seed())

        records = publish.records_of(_collection(_seed("Thistlegorm"), _contribution()))
        written = publish.write_records(records, tmp_path)

        assert sorted(written) == [CONTRIBUTION_PATH, SEED_PATH]
        assert (tmp_path / SEED_PATH).read_text(encoding="utf-8") == serialise(_seed("Thistlegorm"))
        assert (tmp_path / CONTRIBUTION_PATH).read_text(encoding="utf-8") == serialise(_contribution())

    def test_the_second_run_changes_nothing(self, tmp_path: Path):
        records = _tree(tmp_path, _seed(), _contribution())
        before = {path: (tmp_path / path).stat().st_mtime_ns for path in records}

        assert publish.write_records(records, tmp_path) == []
        assert {path: (tmp_path / path).stat().st_mtime_ns for path in records} == before

    def test_an_export_lacking_a_record_writes_nothing(self, tmp_path: Path):
        _tree(tmp_path, _seed())

        with pytest.raises(publish.PublishError, match="lacks 1"):
            publish.write_records(publish.records_of(_collection(_contribution())), tmp_path)

        assert (tmp_path / SEED_PATH).read_text(encoding="utf-8") == serialise(_seed())
        assert not (tmp_path / CONTRIBUTION_PATH).exists()

    def test_an_empty_export_cannot_empty_the_tree(self, tmp_path: Path):
        _tree(tmp_path, _seed())

        with pytest.raises(publish.PublishError):
            publish.write_records(publish.records_of(_collection()), tmp_path)

        assert (tmp_path / SEED_PATH).exists()

    def test_a_record_with_unicode_is_written_as_itself(self, tmp_path: Path):
        _tree(tmp_path, _seed("砂辺"))

        assert "砂辺" in (tmp_path / SEED_PATH).read_text(encoding="utf-8")


class TestTheHeartbeat:
    LAST_COMMIT = date(2026, 11, 6)

    @pytest.mark.parametrize(("days", "due"), [(0, False), (29, False), (30, True), (31, True)])
    def test_it_is_due_after_30_days(self, days: int, due: bool):
        assert publish.stamp_is_due(self.LAST_COMMIT, self.LAST_COMMIT + timedelta(days=days)) is due

    def test_the_day_after_a_stamp_it_is_not_due(self):
        """The stamp's own merge is the last commit, which is what stops a daily stamp from day 31."""
        stamped = self.LAST_COMMIT + timedelta(days=30)

        assert not publish.stamp_is_due(stamped, stamped + timedelta(days=1))

    def test_the_stamp_says_when_and_how_many(self, tmp_path: Path):
        publish.write_stamp(date(2026, 12, 6), 3712, tmp_path)

        assert json.loads((tmp_path / publish.STAMP).read_text()) == {"checked": "2026-12-06", "records": 3712}


class _Export(BaseHTTPRequestHandler):
    status = 200
    body = b""
    agent = ""

    def do_GET(self):
        type(self).agent = self.headers["User-Agent"]
        self.send_response(self.status)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def export() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Export)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()
    thread.join()


class TestTheFetch:
    def test_a_200_is_read_and_names_only_the_project(self, export: str, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(_Export, "status", 200)
        monkeypatch.setattr(_Export, "body", json.dumps(_collection(_seed())).encode())

        assert publish.fetch(export) == _collection(_seed())
        assert _Export.agent == publish.USER_AGENT

    @pytest.mark.parametrize(
        ("status", "body"), [(404, b'{"detail":"Not found"}'), (503, b""), (204, b""), (200, b"<html>")]
    )
    def test_anything_else_is_a_failure(self, export: str, monkeypatch: pytest.MonkeyPatch, status: int, body: bytes):
        monkeypatch.setattr(_Export, "status", status)
        monkeypatch.setattr(_Export, "body", body)

        with pytest.raises(publish.PublishError):
            publish.fetch(export)


class TestTheCommandLine:
    @staticmethod
    def _repo(root: Path, committed: datetime) -> None:
        def git(*args: str) -> None:
            subprocess.run(
                ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
                check=True,
                capture_output=True,
                env={**os.environ, "GIT_COMMITTER_DATE": committed.isoformat()},
            )

        git("init", "-q", "-b", "main")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "test")
        _tree(root, _seed())
        git("add", ".")
        git("commit", "-q", "-m", "base")

    def test_a_failed_export_exits_non_zero_and_writes_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._repo(tmp_path, datetime.now(timezone.utc) - timedelta(days=40))
        monkeypatch.setattr(publish, "fetch", lambda url: {"detail": "Not found"})

        assert publish.main([], tmp_path) == 1
        assert not (tmp_path / publish.STAMP).exists()

    def test_it_reads_the_address_it_is_given(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._repo(tmp_path, datetime.now(timezone.utc))
        asked = []
        monkeypatch.setattr(publish, "fetch", lambda url: asked.append(url) or _collection(_seed()))

        assert publish.main(["http://localhost:8000/api/v1/commons/dive-sites"], tmp_path) == 0
        assert asked == ["http://localhost:8000/api/v1/commons/dive-sites"]

    def test_a_recent_commit_is_not_stamped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._repo(tmp_path, datetime.now(timezone.utc) - timedelta(days=29))
        monkeypatch.setattr(publish, "fetch", lambda url: _collection(_seed()))

        assert publish.main([], tmp_path) == 0
        assert not (tmp_path / publish.STAMP).exists()

    def test_a_quiet_month_is_stamped_with_what_the_copy_held(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._repo(tmp_path, datetime.now(timezone.utc) - timedelta(days=31))
        monkeypatch.setattr(publish, "fetch", lambda url: _collection(_seed(), _contribution()))

        assert publish.main([], tmp_path) == 0
        assert json.loads((tmp_path / publish.STAMP).read_text()) == {
            "checked": datetime.now(timezone.utc).date().isoformat(),
            "records": 1,
        }
