"""Ping each dispatcher when a seat it delegates to finishes a run or needs input.

The dispatcher of a seat is the seat with a `delegates_to` edge to it. A ping only points at the
seat's thread, and a small state file records what has been pinged, so a restart neither repeats
old pings nor misses new ones. Delivery is at least once: a crash can repeat a ping, never lose it.
"""

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t3rig.rig import BUSY_STATUSES, RigError, SeatStatus, envelope, seat_statuses
from t3rig.spec import Rig
from t3rig.t3 import T3Cli, T3Error

EXCERPT_CHARS = 120
ALERT_AFTER_FAILURES = 3
SENDER = "t3rig watch"
# T3 has no field for this, so it's read from the failed run's last reply.
USAGE_LIMIT = re.compile(r"\b(usage|rate|session|weekly|\d+-hour) limit\b|hit your .*limit", re.I)
CLOSING = (
    "Each line above points at a seat's thread; read it with `t3 thread show <id> --messages 3`. "
    "Reply to a seat only if there's more for it to do, and end your turn otherwise."
)


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


def dispatchers(rig: Rig) -> dict[str, str]:
    """Map each seat to its dispatcher. If several delegate to a seat, the first edge wins."""
    result: dict[str, str] = {}
    for edge in rig.edges:
        if edge.kind == "delegates_to":
            result.setdefault(edge.target, edge.source)
    return result


def excerpt(text: str) -> str:
    """One bounded line of a seat's reply, unable to forge lines in the ping."""
    cleaned = "".join(
        " " if unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} else ch for ch in text
    )
    flat = " ".join(cleaned.split())
    if len(flat) <= EXCERPT_CHARS:
        return flat
    return flat[: EXCERPT_CHARS - 1].rstrip() + "…"


@dataclass
class Event:
    seat: str
    session_name: str
    dispatcher: str | None
    line: str
    updates: dict[str, Any] = field(default_factory=dict)
    needs_person: bool = False


def _thread_line(prefix: str, thread: dict[str, Any]) -> str:
    return f"- {prefix} Thread {thread['threadId']}: {thread.get('link', '')}".rstrip()


def _check_seat(
    status: SeatStatus, entry: dict[str, Any] | None, dispatcher: str | None, t3: T3Cli
) -> tuple[list[Event], dict[str, Any]]:
    """What happened on a seat since it was last checked, and the updates needing no ping."""
    thread = status.thread
    run = thread.get("latestRunId") if thread else None
    if thread is None or run is None:
        return [], {}
    seat = status.seat.qualified_id
    busy = thread.get("status") in BUSY_STATUSES
    first_seen = entry is None
    known: dict[str, Any] = entry or {"run": None, "asked": None}
    if not busy and run == known["run"]:
        return [], {"asked": None} if known["asked"] else {}

    # `t3 thread list` lacks these fields, so only busy or changed threads pay for `show`.
    detail = t3.show_thread(thread["threadId"], messages=1)
    details = detail.get("thread", {})
    pending = details.get("pendingRequestCount", 0)
    events: list[Event] = []
    updates: dict[str, Any] = {}
    if first_seen:
        updates = dict(known)

    if pending:
        key = f"{run}:{pending}"
        if known["asked"] != key:
            line = _thread_line(f"{seat} needs input ({pending} pending request).", thread)
            events.append(
                Event(
                    seat,
                    status.session_name,
                    dispatcher,
                    line,
                    {"asked": key},
                    needs_person=dispatcher is None,
                )
            )
        return events, updates
    if known["asked"]:
        updates["asked"] = None

    if not busy and run != known["run"]:
        if first_seen or details.get("runCount", 0) <= 1:
            # History from before watching, or the seat's reply to its first message.
            updates["run"] = run
        else:
            messages = detail.get("messages") or [{}]
            reply = excerpt(messages[-1].get("text") or "")
            said = f' Last reply: "{reply}"' if reply else ""
            limited = thread.get("status") != "completed" and USAGE_LIMIT.search(reply)
            if limited:
                prefix = (
                    f"{seat} stopped at a usage limit and won't continue on its own; "
                    f"message it again after the limit resets.{said}"
                )
            else:
                prefix = f"{seat} finished a run ({thread.get('status')}).{said}"
            line = _thread_line(prefix, thread)
            events.append(
                Event(
                    seat,
                    status.session_name,
                    dispatcher,
                    line,
                    {"run": run},
                    needs_person=bool(limited),
                )
            )
    return events, updates


class Watcher:
    def __init__(self, rig: Rig, t3: T3Cli, path: Path, out: Callable[[str], None] = print) -> None:
        self.rig, self.t3, self.path, self.out = rig, t3, path, out
        self.dispatchers = dispatchers(rig)
        self.state = load_state(path)
        self.failures: dict[str, int] = {}

    def _apply(self, session_name: str, updates: dict[str, Any]) -> None:
        if updates:
            seat = self.state["seats"].setdefault(session_name, {"run": None, "asked": None})
            seat.update(updates)

    def _deliver(self, dispatcher: str, events: list[Event], threads: dict[str, str]) -> None:
        summary = ", ".join(event.seat for event in events)
        try:
            thread_id = threads.get(dispatcher)
            if thread_id is None:
                raise RigError(f"{dispatcher} has no thread")
            lines = "\n".join(event.line for event in events)
            self.t3.send(thread_id, envelope(SENDER, dispatcher, f"{lines}\n\n{CLOSING}"))
        except (RigError, T3Error) as error:
            count = self.failures.get(dispatcher, 0) + 1
            self.failures[dispatcher] = count
            prefix = "ALERT: " if count >= ALERT_AFTER_FAILURES else ""
            self.out(f"{prefix}can't ping {dispatcher} about {summary} (try {count}): {error}")
            return
        self.failures.pop(dispatcher, None)
        for event in events:
            self._apply(event.session_name, event.updates)
        self.out(f"pinged {dispatcher}: {summary}")

    def tick(self) -> None:
        statuses = seat_statuses(self.rig, self.t3)
        by_dispatcher: dict[str, list[Event]] = {}
        for status in statuses:
            dispatcher = self.dispatchers.get(status.seat.qualified_id)
            entry = self.state["seats"].get(status.session_name)
            events, updates = _check_seat(status, entry, dispatcher, self.t3)
            self._apply(status.session_name, updates)
            for event in events:
                # A dispatcher can't fix these, so a person has to hear about them too.
                if event.needs_person:
                    self.out(f"ALERT: {event.line.removeprefix('- ')}")
                if event.dispatcher is None:
                    self._apply(event.session_name, event.updates)
                else:
                    by_dispatcher.setdefault(event.dispatcher, []).append(event)
        threads = {s.seat.qualified_id: s.thread["threadId"] for s in statuses if s.thread}
        for dispatcher, events in by_dispatcher.items():
            self._deliver(dispatcher, events, threads)
        self.state["updated_at"] = datetime.now(UTC).isoformat()
        save_state(self.path, self.state)


@contextmanager
def _single_watcher(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RigError("another `t3rig watch` is already running for this rig") from error
        yield


def watch(
    rig: Rig,
    t3: T3Cli,
    interval: float,
    once: bool = False,
    out: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    if not dispatchers(rig):
        raise RigError(f"rig {rig.name} has no delegates_to edges, so there's nobody to ping")
    path = state_path(rig)
    with _single_watcher(path):
        watcher = Watcher(rig, t3, path, out)
        while True:
            try:
                watcher.tick()
            except T3Error as error:
                out(f"can't read seats, will retry: {error}")
            if once:
                return
            sleep(interval)
