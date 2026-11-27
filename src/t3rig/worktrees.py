"""The git side of task threads' worktrees (ADR 0009): an issue's branch, its worktree if there is
one, and what a new one starts from. T3 itself makes the worktree, or binds an existing one."""

import re
import subprocess
from pathlib import Path
from typing import Any

from t3rig.threads import RigError, issue_of


def issue_branch(task: str) -> str:
    """The branch an issue is worked on: `#18` and `#18 r2` both use `issue-18`."""
    issue = issue_of(task).removeprefix("#")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", issue):
        raise RigError(f'can\'t name a branch after task {task!r}; use a task such as "#18"')
    return f"issue-{issue}"


def _git(cwd: Path, *args: str) -> str | None:
    """git's output, or None if it failed."""
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def find_worktree(cwd: Path, branch: str) -> Path | None:
    """The worktree that has `branch` checked out, in the repository holding `cwd`."""
    listing = _git(cwd, "worktree", "list", "--porcelain")
    if listing is None:
        raise RigError(
            f"{cwd} isn't in a git repository, so task threads can't get worktrees; "
            "set `worktrees: false` in rig.t3rig.yaml"
        )
    path = None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line == f"branch refs/heads/{branch}" and path:
            return Path(path)
    return None


def seat_folder(cwd: Path, worktree: Path) -> Path:
    """Where a seat's folder `cwd` is in a worktree of its repository: the same subfolder."""
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return worktree / cwd.resolve().relative_to(Path(top).resolve()) if top else worktree


def new_worktree(cwd: Path, branch: str) -> dict[str, Any]:
    """T3's `workspaceStrategy` for a new worktree on `branch`. It starts from the remote's default
    branch, or the remote copy of the folder's current branch, or without a remote that branch."""
    current = _git(cwd, "branch", "--show-current")
    remote = _git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    tracked = current and _git(cwd, "rev-parse", "--verify", f"refs/remotes/origin/{current}")
    if not remote and tracked:
        remote = f"origin/{current}"
    if remote:
        return {"type": "worktree", "branch": branch, "baseRef": remote, "startFromOrigin": True}
    if not current:
        raise RigError(f"{cwd} has no branch checked out to start {branch} from")
    return {"type": "worktree", "branch": branch, "baseRef": current, "startFromOrigin": False}
