"""Land what `publish.py` wrote: one verified commit, one pull request, merged once it is green.

    python scripts/land.py --path sites --branch publish/sites --title "chore(sites): ..."

Takes whatever under `--path` differs from HEAD, and needs `PUBLISHER_TOKEN`, the App's token
that writes, `GITHUB_TOKEN`, the workflow's own that reads the checks, and `GITHUB_REPOSITORY`.

**The commit is made through the API.** The `signatures` ruleset covers the branch and a runner's
`git commit` is signed by nobody, while a commit the App creates with no author, committer or
signature of its own is verified by GitHub.

**Its tree is built in chunks whose entries carry their contents inline, each on the last through
`base_tree`.** The first publish touches thousands of files: a blob per file would run into GitHub's
cap on content-generating requests, and a single tree of them times out with a 422. A chunk that
fails stops the run before the commit exists, so nothing lands.

**A red check fails the run and leaves the pull request open.** The next run commits to the same
branch, which updates that pull request. A run with nothing to land closes it, since whatever
broke no longer differs from `main`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from pool import ROOT

API = "https://api.github.com"
BASE = "main"

# The `main` ruleset's required checks. The repository has auto-merge off, so waiting on them
# is this script's job.
REQUIRED_CHECKS = ("validate", "semantic-title")

# GitHub timed out on a tree of about 3,665 files, 2 to 3 MB, after some 10 seconds. This keeps a
# request well inside that and a first publish at a dozen or so.
_TREE_CHUNK_FILES = 300

_REQUEST_TIMEOUT_SECONDS = 120
_ATTEMPTS = 3
_POLL_SECONDS = 15
_CHECKS_WAIT_SECONDS = 1200

# GitHub answers 405 for a moment after the checks pass, while it works out the merge.
_MERGE_ATTEMPTS = 8


class LandError(Exception):
    """The run stops here, and whatever is open stays open."""


class GitHubError(LandError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class Api(Protocol):
    repository: str

    def request(self, method: str, path: str, body: Any = None) -> Any: ...


class GitHub:
    """The repository's REST API. A 5xx or a dropped connection is retried, anything else is not."""

    def __init__(self, token: str, repository: str, sleep: Callable[[float], None] = time.sleep) -> None:
        self.token = token
        self.repository = repository
        self.sleep = sleep

    def _once(self, method: str, path: str, data: bytes | None) -> Any:
        request = urllib.request.Request(
            f"{API}/repos/{self.repository}/{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
        return json.loads(payload) if payload else None

    def request(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                return self._once(method, path, data)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")
                failure = GitHubError(exc.code, f"{method} {path} answered {exc.code}: {detail}")
                if exc.code < 500:
                    raise failure from exc
            except (urllib.error.URLError, OSError) as exc:
                failure = GitHubError(0, f"{method} {path} failed: {exc}")
            if attempt < _ATTEMPTS:
                self.sleep(attempt * 5)
        raise failure


def changed_files(path: str, root: Path = ROOT) -> dict[str, str]:
    """`{path: text}` for every file under `path` that differs from HEAD, new ones included."""
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--modified", "--others", "--exclude-standard", "--", path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {name: (root / name).read_text(encoding="utf-8") for name in listed.split("\0") if name}


def commit(github: Api, branch: str, message: str, files: dict[str, str]) -> str:
    """One commit on top of `main` holding `files`, with `branch` moved to it. Its sha."""
    parent = github.request("GET", f"git/ref/heads/{BASE}")["object"]["sha"]
    tree = github.request("GET", f"git/commits/{parent}")["tree"]["sha"]
    entries = [{"path": path, "mode": "100644", "type": "blob", "content": text} for path, text in files.items()]
    for start in range(0, len(entries), _TREE_CHUNK_FILES):
        chunk = entries[start : start + _TREE_CHUNK_FILES]
        tree = github.request("POST", "git/trees", {"base_tree": tree, "tree": chunk})["sha"]
    sha = github.request("POST", "git/commits", {"message": message, "tree": tree, "parents": [parent]})["sha"]
    try:
        github.request("GET", f"git/ref/heads/{branch}")
    except GitHubError as exc:
        if exc.status != 404:
            raise
        github.request("POST", "git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})
    else:
        github.request("PATCH", f"git/refs/heads/{branch}", {"sha": sha, "force": True})
    return sha


def wait_for_checks(
    github: Api,
    sha: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    deadline = clock() + _CHECKS_WAIT_SECONDS
    while True:
        runs = github.request("GET", f"commits/{sha}/check-runs?per_page=100")["check_runs"]
        concluded = {run["name"]: run["conclusion"] for run in runs if run["status"] == "completed"}
        failed = [name for name in REQUIRED_CHECKS if concluded.get(name, "success") != "success"]
        if failed:
            raise LandError(", ".join(f"{name} concluded {concluded[name]}" for name in failed))
        if all(name in concluded for name in REQUIRED_CHECKS):
            return
        if clock() >= deadline:
            raise LandError(f"its checks had not passed after {_CHECKS_WAIT_SECONDS} seconds")
        sleep(_POLL_SECONDS)


def merge(github: Api, number: int, sha: str, *, sleep: Callable[[float], None] = time.sleep) -> None:
    for attempt in range(1, _MERGE_ATTEMPTS + 1):
        try:
            github.request("PUT", f"pulls/{number}/merge", {"sha": sha, "merge_method": "squash"})
            return
        except GitHubError as exc:
            if exc.status != 405 or attempt == _MERGE_ATTEMPTS:
                raise
        sleep(_POLL_SECONDS)


def land(
    writer: Api,
    reader: Api,
    *,
    branch: str,
    title: str,
    files: dict[str, str],
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    owner = writer.repository.split("/")[0]
    open_pulls = writer.request("GET", f"pulls?state=open&head={owner}:{branch}")
    if not files:
        for pull in open_pulls:
            writer.request("PATCH", f"pulls/{pull['number']}", {"state": "closed"})
        print(f"nothing to land on {branch}")
        return

    sha = commit(writer, branch, title, files)
    if open_pulls:
        number = open_pulls[0]["number"]
    else:
        body = "Written by `.github/workflows/publish.yml`."
        number = writer.request("POST", "pulls", {"title": title, "head": branch, "base": BASE, "body": body})["number"]
    print(f"{len(files)} file(s) in pull request #{number}, at {sha}")

    try:
        wait_for_checks(reader, sha, sleep=sleep, clock=clock)
    except LandError as exc:
        raise LandError(f"pull request #{number} stays open: {exc}") from exc
    merge(writer, number, sha, sleep=sleep)
    print(f"merged #{number}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--path", required=True, help="what to land, a file or a directory")
    parser.add_argument("--branch", required=True, help="the branch its pull request lives on")
    parser.add_argument("--title", required=True, help="the commit message and the pull request's title")
    args = parser.parse_args(argv)

    repository = os.environ["GITHUB_REPOSITORY"]
    writer = GitHub(os.environ["PUBLISHER_TOKEN"], repository)
    reader = GitHub(os.environ["GITHUB_TOKEN"], repository)
    try:
        land(writer, reader, branch=args.branch, title=args.title, files=changed_files(args.path))
    except LandError as exc:
        print(f"landing failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
