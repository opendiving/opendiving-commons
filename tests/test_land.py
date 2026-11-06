"""Tests for `scripts/land.py`, against a stand-in for GitHub that answers as the API does."""

import subprocess
import urllib.error
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

import land

BRANCH = "publish/sites"
TITLE = "chore(sites): publish the records the instance holds"
FILES = {"sites/wikidata/Q1.geojson": "{}\n", "sites/wikidata/Q2.geojson": "{}\n"}


class FakeGitHub:
    repository = "opendiving/opendiving-commons"

    def __init__(self, *, branch_exists: bool = False, open_pulls: list[int] | None = None) -> None:
        self.branch_exists = branch_exists
        self.open_pulls = open_pulls or []
        self.checks: list[list[dict[str, Any]]] = [[_passed("validate"), _passed("semantic-title")]]
        self.merge_answers: list[int] = []
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method: str, path: str, body: Any = None) -> Any:
        self.calls.append((method, path, body))
        if path == "git/ref/heads/main":
            return {"object": {"sha": "main-sha"}}
        if path == f"git/ref/heads/{BRANCH}":
            if not self.branch_exists:
                raise land.GitHubError(404, "no such ref")
            return {"object": {"sha": "old"}}
        if path == "git/commits/main-sha":
            return {"tree": {"sha": "main-tree"}}
        if path == "git/trees":
            return {"sha": "new-tree"}
        if path == "git/commits":
            return {"sha": "new-sha"}
        if path.startswith("pulls?"):
            return [{"number": number} for number in self.open_pulls]
        if (method, path) == ("POST", "pulls"):
            return {"number": 7}
        if path.startswith("commits/new-sha/check-runs"):
            return {"check_runs": self.checks.pop(0) if len(self.checks) > 1 else self.checks[0]}
        if path.endswith("/merge") and self.merge_answers:
            raise land.GitHubError(self.merge_answers.pop(0), "not mergeable yet")
        return {}

    def made(self, method: str, path: str) -> list[Any]:
        return [body for made_method, made_path, body in self.calls if (made_method, made_path) == (method, path)]


def _passed(name: str) -> dict[str, Any]:
    return {"name": name, "status": "completed", "conclusion": "success"}


def _land(github: FakeGitHub, files: dict[str, str] = FILES) -> None:
    land.land(github, github, branch=BRANCH, title=TITLE, files=files, sleep=lambda seconds: None)


class TestTheCommit:
    def test_it_is_one_tree_on_top_of_main_with_the_contents_inline(self):
        github = FakeGitHub()

        _land(github)

        assert github.made("POST", "git/trees") == [
            {
                "base_tree": "main-tree",
                "tree": [{"path": path, "mode": "100644", "type": "blob", "content": "{}\n"} for path in FILES],
            }
        ]

    def test_its_request_count_does_not_grow_with_the_files(self):
        few, many = FakeGitHub(), FakeGitHub()

        _land(few, {"sites/wikidata/Q1.geojson": "{}\n"})
        _land(many, {f"sites/wikidata/Q{n}.geojson": "{}\n" for n in range(1, 5000)})

        assert len(few.calls) == len(many.calls)

    def test_it_names_no_author_so_github_verifies_it(self):
        github = FakeGitHub()

        _land(github)

        assert github.made("POST", "git/commits") == [{"message": TITLE, "tree": "new-tree", "parents": ["main-sha"]}]


class TestThePullRequest:
    def test_the_first_run_opens_one_and_squashes_it(self):
        github = FakeGitHub()

        _land(github)

        assert github.made("POST", "git/refs") == [{"ref": f"refs/heads/{BRANCH}", "sha": "new-sha"}]
        assert [(pull["title"], pull["head"], pull["base"]) for pull in github.made("POST", "pulls")] == [
            (TITLE, BRANCH, "main")
        ]
        assert github.made("PUT", "pulls/7/merge") == [{"sha": "new-sha", "merge_method": "squash"}]

    def test_the_next_run_updates_the_one_that_is_open(self):
        github = FakeGitHub(branch_exists=True, open_pulls=[5])

        _land(github)

        assert github.made("PATCH", f"git/refs/heads/{BRANCH}") == [{"sha": "new-sha", "force": True}]
        assert github.made("POST", "pulls") == []
        assert github.made("PUT", "pulls/5/merge") == [{"sha": "new-sha", "merge_method": "squash"}]

    def test_a_leftover_branch_with_no_pull_request_gets_a_new_one(self):
        github = FakeGitHub(branch_exists=True)

        _land(github)

        assert len(github.made("POST", "pulls")) == 1

    def test_nothing_to_land_commits_nothing(self):
        github = FakeGitHub()

        _land(github, {})

        assert [method for method, _, _ in github.calls] == ["GET"]

    def test_nothing_to_land_closes_what_is_open(self):
        github = FakeGitHub(branch_exists=True, open_pulls=[5])

        _land(github, {})

        assert github.made("PATCH", "pulls/5") == [{"state": "closed"}]
        assert github.made("POST", "git/commits") == []


class TestTheChecks:
    def test_it_waits_for_both(self):
        github = FakeGitHub()
        github.checks = [
            [],
            [{"name": "validate", "status": "in_progress", "conclusion": None}, _passed("semantic-title")],
            [_passed("validate"), _passed("semantic-title")],
        ]

        _land(github)

        assert len(github.made("PUT", "pulls/7/merge")) == 1
        assert sum(path.startswith("commits/") for _, path, _ in github.calls) == 3

    def test_a_check_it_does_not_require_is_not_waited_on(self):
        github = FakeGitHub()
        github.checks = [
            [
                _passed("validate"),
                _passed("semantic-title"),
                {"name": "tests", "status": "in_progress", "conclusion": None},
                {"name": "label", "status": "completed", "conclusion": "failure"},
            ]
        ]

        _land(github)

        assert len(github.made("PUT", "pulls/7/merge")) == 1

    @pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
    def test_a_red_check_fails_the_run_and_leaves_the_pull_request_open(self, conclusion: str):
        github = FakeGitHub()
        github.checks = [[{"name": "validate", "status": "completed", "conclusion": conclusion}]]

        with pytest.raises(land.LandError, match="#7 stays open"):
            _land(github)

        assert github.made("PUT", "pulls/7/merge") == []
        assert github.made("PATCH", "pulls/7") == []

    def test_a_check_that_never_reports_times_out_without_merging(self):
        github = FakeGitHub()
        github.checks = [[]]
        now = iter(range(0, 100_000, 600))

        with pytest.raises(land.LandError, match="stays open"):
            land.land(
                github,
                github,
                branch=BRANCH,
                title=TITLE,
                files=FILES,
                sleep=lambda seconds: None,
                clock=lambda: next(now),
            )

        assert github.made("PUT", "pulls/7/merge") == []


class TestTheMerge:
    def test_it_waits_out_github_working_out_the_merge(self):
        github = FakeGitHub()
        github.merge_answers = [405, 405]

        _land(github)

        assert len(github.made("PUT", "pulls/7/merge")) == 3

    def test_any_other_refusal_stops_the_run(self):
        github = FakeGitHub()
        github.merge_answers = [403]

        with pytest.raises(land.GitHubError):
            _land(github)

        assert len(github.made("PUT", "pulls/7/merge")) == 1

    def test_it_stops_asking_in_the_end(self):
        github = FakeGitHub()
        github.merge_answers = [405] * 100

        with pytest.raises(land.GitHubError):
            _land(github)


class TestTheClient:
    @staticmethod
    def _client(monkeypatch: pytest.MonkeyPatch, answers: list[Any]) -> tuple[land.GitHub, list[Any]]:
        seen: list[Any] = []

        def urlopen(request, timeout):
            seen.append(request)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer

            class Response(BytesIO):
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Response(answer)

        monkeypatch.setattr(land.urllib.request, "urlopen", urlopen)
        return land.GitHub("token", "opendiving/opendiving-commons", sleep=lambda seconds: None), seen

    @staticmethod
    def _http_error(status: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("https://api.github.com", status, "no", {}, BytesIO(b'{"message": "no"}'))

    def test_a_5xx_is_retried(self, monkeypatch: pytest.MonkeyPatch):
        github, seen = self._client(monkeypatch, [self._http_error(502), b'{"sha": "x"}'])

        assert github.request("GET", "git/ref/heads/main") == {"sha": "x"}
        assert len(seen) == 2

    def test_a_dropped_connection_is_retried(self, monkeypatch: pytest.MonkeyPatch):
        github, _ = self._client(monkeypatch, [urllib.error.URLError("reset"), b"{}"])

        assert github.request("GET", "git/ref/heads/main") == {}

    def test_a_4xx_is_not(self, monkeypatch: pytest.MonkeyPatch):
        github, seen = self._client(monkeypatch, [self._http_error(404)])

        with pytest.raises(land.GitHubError) as caught:
            github.request("GET", "git/ref/heads/x")

        assert caught.value.status == 404
        assert len(seen) == 1

    def test_it_gives_up_after_three(self, monkeypatch: pytest.MonkeyPatch):
        github, seen = self._client(monkeypatch, [self._http_error(500) for _ in range(5)])

        with pytest.raises(land.GitHubError):
            github.request("GET", "git/ref/heads/main")

        assert len(seen) == 3

    def test_an_empty_answer_is_none(self, monkeypatch: pytest.MonkeyPatch):
        github, _ = self._client(monkeypatch, [b""])

        assert github.request("PATCH", "pulls/5", {"state": "closed"}) is None


def test_changed_files_are_what_differs_from_head_new_files_included(tmp_path: Path):
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    (tmp_path / "sites").mkdir()
    (tmp_path / "sites" / "same.geojson").write_text("same\n")
    (tmp_path / "sites" / "moved.geojson").write_text("before\n")
    (tmp_path / "published.json").write_text("{}\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    (tmp_path / "sites" / "moved.geojson").write_text("after\n")
    (tmp_path / "sites" / "new.geojson").write_text("new 砂辺\n")
    (tmp_path / "published.json").write_text('{"records": 1}\n')

    assert land.changed_files("sites", tmp_path) == {"sites/moved.geojson": "after\n", "sites/new.geojson": "new 砂辺\n"}
    assert land.changed_files("nothing.json", tmp_path) == {}
    assert land.changed_files("published.json", tmp_path) == {"published.json": '{"records": 1}\n'}
