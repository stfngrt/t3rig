"""Read a rig's issue tracker through the `gh` or `glab` command-line tool."""

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

from t3rig.spec import TrackerSettings

TIMEOUT_SECONDS = 60


class TrackerError(Exception):
    """A tracker command failed or couldn't run."""


@dataclass(frozen=True)
class Issue:
    number: int
    url: str
    labels: frozenset[str]
    title: str = ""


class Tracker(Protocol):
    limit: int  # The most open issues `open_issues` returns.

    def open_issues(self) -> list[Issue]: ...
    def comments(self, number: int) -> list[str]: ...  # Bodies, oldest first.


def _run_json(command: list[str]) -> Any:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
    except FileNotFoundError as error:
        raise TrackerError(f"can't find `{command[0]}`; is it installed?") from error
    except subprocess.TimeoutExpired as error:
        raise TrackerError(f"`{' '.join(command[:3])}` timed out") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise TrackerError(f"`{' '.join(command[:3])}` exited {result.returncode}: {detail}")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise TrackerError(f"`{' '.join(command[:3])}` didn't return JSON") from error


class GitHub:
    limit = 1000

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def open_issues(self) -> list[Issue]:
        # shortcut: at most 1000 open issues are seen; page with `gh api` if a repo has more.
        rows = _run_json(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                self.repo,
                "--state",
                "open",
                "--limit",
                str(self.limit),
            ]
            + ["--json", "number,title,url,labels"]
        )
        return [
            Issue(
                row["number"],
                row["url"],
                frozenset(label["name"] for label in row["labels"]),
                row["title"],
            )
            for row in rows
        ]

    def comments(self, number: int) -> list[str]:
        data = _run_json(
            ["gh", "issue", "view", str(number), "--repo", self.repo, "--json", "comments"]
        )
        return [comment["body"] for comment in data["comments"]]


class GitLab:
    limit = 100

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def open_issues(self) -> list[Issue]:
        # shortcut: only the first 100 open issues are seen; page if a project has more.
        rows = _run_json(
            ["glab", "issue", "list", "--repo", self.repo]
            + ["--per-page", str(self.limit), "--output", "json"]
        )
        return [
            Issue(row["iid"], row["web_url"], frozenset(row["labels"]), row["title"])
            for row in rows
        ]

    def comments(self, number: int) -> list[str]:
        # shortcut: only the newest 100 notes are read; page if older ones are ever needed.
        project = quote(self.repo, safe="")
        notes = _run_json(
            ["glab", "api", f"projects/{project}/issues/{number}/notes?sort=desc&per_page=100"]
        )
        return [note["body"] for note in reversed(notes) if not note.get("system")]


def tracker_for(settings: TrackerSettings) -> Tracker:
    return GitHub(settings.repo) if settings.kind == "github" else GitLab(settings.repo)
