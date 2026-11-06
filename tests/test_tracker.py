import json
import stat
from pathlib import Path

import pytest

from t3rig.spec import TrackerSettings
from t3rig.tracker import GitHub, GitLab, Issue, TrackerError, tracker_for


def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, output: object) -> Path:
    """A `gh` or `glab` on PATH that records its arguments and prints fixed JSON."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / f"{name}.args"
    script = bin_dir / name
    script.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {log}\ncat <<'EOF'\n{json.dumps(output)}\nEOF\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    return log


def test_github_lists_open_issues_with_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels = [{"name": "rig-queue", "id": "x"}]
    rows = [{"number": 7, "title": "T", "url": "https://g/7", "labels": labels}]
    log = fake_cli(tmp_path, monkeypatch, "gh", rows)
    assert GitHub("o/r").open_issues() == [Issue(7, "https://g/7", frozenset({"rig-queue"}), "T")]
    args = log.read_text().split()
    assert args[:2] == ["issue", "list"] and "o/r" in args and "open" in args


def test_github_reads_comment_bodies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = fake_cli(tmp_path, monkeypatch, "gh", {"comments": [{"body": "a"}, {"body": "b"}]})
    assert GitHub("o/r").comments(7) == ["a", "b"]
    assert log.read_text().split()[:3] == ["issue", "view", "7"]


def test_gitlab_lists_open_issues_with_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [{"iid": 3, "title": "T", "web_url": "https://l/3", "labels": ["needs-answer"]}]
    log = fake_cli(tmp_path, monkeypatch, "glab", rows)
    expected = [Issue(3, "https://l/3", frozenset({"needs-answer"}), "T")]
    assert GitLab("g/p").open_issues() == expected
    args = log.read_text().split()
    assert args[:2] == ["issue", "list"] and "g/p" in args and "json" in args


def test_gitlab_reads_notes_without_system_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Newest first, as requested, so long threads still show the latest notes.
    notes = [{"body": "b"}, {"body": "added label", "system": True}, {"body": "a", "system": False}]
    log = fake_cli(tmp_path, monkeypatch, "glab", notes)
    assert GitLab("g/sub/p").comments(3) == ["a", "b"]
    url = log.read_text().split()[1]
    assert url.startswith("projects/g%2Fsub%2Fp/issues/3/notes") and "sort=desc" in url


def test_failures_are_tracker_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(TrackerError, match="can't find `gh`"):
        GitHub("o/r").open_issues()
    fake_cli(tmp_path, monkeypatch, "glab", "x")
    (tmp_path / "bin" / "glab").write_text("#!/bin/sh\necho nope >&2\nexit 1\n")
    with pytest.raises(TrackerError, match="exited 1: nope"):
        GitLab("g/p").open_issues()


def test_tracker_for_picks_the_backend() -> None:
    assert isinstance(tracker_for(TrackerSettings("github", "o/r", "dev.lead")), GitHub)
    assert isinstance(tracker_for(TrackerSettings("gitlab", "g/p", "dev.lead")), GitLab)
