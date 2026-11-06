"""Ping each dispatcher when a seat it delegates to finishes a run or needs input.

With a tracker in `rig.t3rig.yaml`, also ping a seat when an issue is queued or answered.

This module runs the rounds and keeps the state file; `seat_watch` and `issue_watch` decide what to
ping about, and `delivery` sends the pings. The state file records what has been pinged, so a
restart neither repeats old pings nor misses new ones. Delivery is at least once: a crash can
repeat a ping, never lose it.
"""

import fcntl
import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t3rig.delivery import Delivery
from t3rig.issue_watch import IssueWatch
from t3rig.seat_watch import SeatWatch, dispatchers
from t3rig.spec import Rig
from t3rig.t3 import T3Error
from t3rig.threads import T3, RigError
from t3rig.tracker import Issue, Tracker, TrackerError, tracker_for


def state_path(rig: Rig) -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    digest = hashlib.sha256(str(rig.path).encode()).hexdigest()[:8]
    return base / "t3rig" / f"{rig.name}-{digest}.json"


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {"seats": {}}
    except (OSError, ValueError) as error:
        raise RigError(f"can't read watch state {path}: {error}") from error


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(state, handle, indent=2)
    os.replace(handle.name, path)


def last_check(rig: Rig) -> str | None:
    """When `watch` last checked this rig, if it ever has."""
    return load_state(state_path(rig)).get("updated_at")


class Watcher:
    """One rig's watch: seat watching, and issue watching with a tracker, sharing one state file
    and one ping delivery."""

    def __init__(
        self,
        rig: Rig,
        t3: T3,
        path: Path,
        out: Callable[[str], None] = print,
        tracker: Tracker | None = None,
        tracker_interval: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rig, self.path, self.out = rig, path, out
        self.tracker_interval, self.clock = tracker_interval, clock
        self.next_poll = clock()
        self.state = load_state(path)
        self.delivery = Delivery(rig, t3, out, self.state)
        self.seat_watch = SeatWatch(rig, t3, self.state, self.delivery)
        self.issue_watch = (
            IssueWatch(rig, t3, tracker, self.state, self.delivery) if tracker else None
        )

    def open_issues(self) -> list[Issue]:
        """Open issues as of the last tracker poll; none without a tracker."""
        return self.issue_watch.open_issues() if self.issue_watch else []

    def tick(self) -> None:
        """Check the seats once."""
        self.seat_watch.check()
        self.delivery.send_notices()
        self.state["updated_at"] = datetime.now(UTC).isoformat()
        save_state(self.path, self.state)

    def poll_tracker(self) -> None:
        """Check the open issues once."""
        assert self.issue_watch is not None
        self.issue_watch.poll()
        self.delivery.send_notices()
        save_state(self.path, self.state)

    def step(self) -> None:
        """One round of `watch`: check the seats, and the tracker when it's due."""
        try:
            self.tick()
        except T3Error as error:
            self.out(f"can't read seats, will retry: {error}")
        if self.issue_watch is not None and self.clock() >= self.next_poll:
            self.next_poll = self.clock() + self.tracker_interval
            try:
                self.poll_tracker()
            except (T3Error, TrackerError) as error:
                self.out(f"can't read the tracker, will retry: {error}")


def check_watchable(rig: Rig) -> None:
    if not dispatchers(rig) and rig.tracker is None:
        raise RigError(f"rig {rig.name} has no delegates_to edges, so there's nobody to ping")


def watch_running(rig: Rig) -> bool:
    """Whether a `watch` or `serve` holds the rig's lock. Creates no file or folder."""
    try:
        lock = open(state_path(rig).with_suffix(".lock"), "rb")
    except FileNotFoundError:
        return False
    with lock:
        try:
            # shortcut: a watch starting in this instant would be refused; it can be started again.
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
        return False


@contextmanager
def single_watcher(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RigError("another `t3rig watch` is already running for this rig") from error
        yield


def watch(
    rig: Rig,
    t3: T3,
    interval: float,
    once: bool = False,
    out: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    tracker_interval: float = 60,
    make_tracker: Callable[..., Tracker] = tracker_for,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    check_watchable(rig)
    path = state_path(rig)
    tracker = make_tracker(rig.tracker) if rig.tracker else None
    with single_watcher(path):
        watcher = Watcher(
            rig, t3, path, out, tracker, tracker_interval=tracker_interval, clock=clock
        )
        while True:
            watcher.step()
            if once:
                return
            sleep(interval)
