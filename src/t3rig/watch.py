"""Ping each dispatcher when a seat it delegates to finishes a run or needs input.

With a tracker in `rig.t3rig.yaml`, also ping a seat when an issue is queued or answered.

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

from t3rig.rig import (
    BUSY_STATUSES,
    RigError,
    SeatStatus,
    Tools,
    connect_mcp,
    envelope,
    seat_statuses,
    t3rig_command,
)
from t3rig.spec import Rig
from t3rig.t3 import T3Cli, T3Error
from t3rig.tracker import Issue, Tracker, TrackerError, tracker_for

EXCERPT_CHARS = 120
ALERT_AFTER_FAILURES = 3
SENDER = "t3rig watch"
ACTIVITY_WINDOW = 100
STOPPED_STATUSES = {"interrupted", "cancelled"}
# T3 has no field for this, so it's read from the failed run's last reply.
USAGE_LIMIT = re.compile(r"\b(usage|rate|session|weekly|\d+-hour) limit\b|hit your .*limit", re.I)
CLOSING = (
    "Each line above points at a seat's thread; read it with `t3 thread show <id> --messages 3`. "
    "Reply to a seat only if there's more for it to do, and end your turn otherwise."
)
QUEUE_LABEL = "rig-queue"
ANSWER_LABEL = "needs-answer"
SIGNATURE = re.compile(r"^\s*🤖\s*([\w.-]+)", re.M)
ISSUE_CLOSING = "Read each issue above and its comments before you act on it."


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
    issue: str | None = None  # Set for tracker events, whose updates go to the issue's state.


def _thread_line(prefix: str, thread: dict[str, Any]) -> str:
    return f"- {prefix} Thread {thread['threadId']}: {thread.get('link', '')}".rstrip()


def waiting_approval(tools: Tools, thread_id: str, item_count: int) -> str | None:
    """The newest approval a thread is waiting on, read from its activity, oldest item first."""
    after = max(item_count - ACTIVITY_WINDOW, 0)
    found = None
    while True:
        page = tools.call(
            "t3_thread_read",
            threadId=thread_id,
            view="activity",
            afterPosition=after,
            limit=ACTIVITY_WINDOW,
        )
        for item in page.get("items", []):
            if item.get("type") == "approval_request" and item.get("status") == "waiting":
                found = item.get("text")
        if not page.get("hasMore") or page.get("nextPosition", after) <= after:
            return found
        after = page["nextPosition"]


def _check_seat(
    rig: Rig,
    status: SeatStatus,
    entry: dict[str, Any] | None,
    dispatcher: str | None,
    t3: T3Cli,
    waiting_on: Callable[[str, int], str | None],
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
            waiting = waiting_on(thread["threadId"], details.get("itemCount", 0))
            said = f' Waiting on: "{excerpt(waiting)}"' if waiting else ""
            stop_command = t3rig_command("stop", str(rig.path), seat)
            line = _thread_line(
                f"{seat} needs input ({pending} pending request).{said} You can't approve this. "
                f"If it can't wait for a person, run `{stop_command}` and message the seat.",
                thread,
            )
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
            # The newest message can be one sent to the seat, which isn't a reply.
            last = (detail.get("messages") or [{}])[-1]
            reply = excerpt(last.get("text") or "") if last.get("role") == "assistant" else ""
            said = f' Last reply: "{reply}"' if reply else ""
            limited = thread.get("status") != "completed" and USAGE_LIMIT.search(reply)
            if limited:
                prefix = (
                    f"{seat} stopped at a usage limit and won't continue on its own; "
                    f"message it again after the limit resets.{said}"
                )
            elif thread.get("status") in STOPPED_STATUSES:
                prefix = (
                    f"{seat}'s run was stopped before it finished ({thread.get('status')}), "
                    "so treat it as having no result."
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
    def __init__(
        self,
        rig: Rig,
        t3: T3Cli,
        path: Path,
        out: Callable[[str], None] = print,
        connect: Callable[[], tuple[Tools, str]] | None = None,
        tracker: Tracker | None = None,
    ) -> None:
        self.rig, self.t3, self.path, self.out = rig, t3, path, out
        self.connect, self.tracker = connect, tracker
        self.dispatchers = dispatchers(rig)
        self.state = load_state(path)
        self.failures: dict[tuple[str, str], int] = {}

    def _waiting_on(self, thread_id: str, item_count: int) -> str | None:
        """What a seat is waiting on. A ping without it is still useful, so errors are dropped."""
        if self.connect is None:
            return None
        try:
            tools, _ = self.connect()
            return waiting_approval(tools, thread_id, item_count)
        except T3Error:
            return None

    def _apply(self, session_name: str, updates: dict[str, Any]) -> None:
        if updates:
            seat = self.state["seats"].setdefault(session_name, {"run": None, "asked": None})
            seat.update(updates)

    def _apply_issue(self, key: str, updates: dict[str, Any]) -> None:
        issues = self.state.setdefault("issues", {})
        entry = issues.setdefault(key, {QUEUE_LABEL: False, ANSWER_LABEL: False, "asker": None})
        entry.update(updates)
        if not entry[QUEUE_LABEL] and not entry[ANSWER_LABEL]:
            del issues[key]  # Forgetting it is the same as never having seen either label.

    def _deliver(
        self,
        dispatcher: str,
        events: list[Event],
        threads: dict[str, str],
        closing: str = CLOSING,
    ) -> None:
        summary = ", ".join(event.seat for event in events)
        key = (dispatcher, closing)
        try:
            thread_id = threads.get(dispatcher)
            if thread_id is None:
                raise RigError(f"{dispatcher} has no thread")
            lines = "\n".join(event.line for event in events)
            self.t3.send(thread_id, envelope(SENDER, dispatcher, f"{lines}\n\n{closing}"))
        except (RigError, T3Error) as error:
            count = self.failures.get(key, 0) + 1
            self.failures[key] = count
            prefix = "ALERT: " if count >= ALERT_AFTER_FAILURES else ""
            self.out(f"{prefix}can't ping {dispatcher} about {summary} (try {count}): {error}")
            return
        self.failures.pop(key, None)
        for event in events:
            if event.issue is None:
                self._apply(event.session_name, event.updates)
            else:
                self._apply_issue(event.issue, event.updates)
        self.out(f"pinged {dispatcher}: {summary}")

    def _asker(self, number: int) -> str | None:
        """The seat that signed the newest signed comment, which asked the question."""
        assert self.tracker is not None
        for body in reversed(self.tracker.comments(number)):
            if found := SIGNATURE.search(body):
                return found[1] if self.rig.seat(found[1]) else None
        return None

    def _issue_events(self, issue: Issue, entry: dict[str, Any] | None) -> list[Event]:
        """Pings for one open issue's label changes; other changes are remembered at once."""
        assert self.rig.tracker is not None
        key, queue_seat = str(issue.number), self.rig.tracker.queue_seat
        queued = entry is not None and entry[QUEUE_LABEL]
        waiting = entry is not None and entry[ANSWER_LABEL]
        events: list[Event] = []
        updates: dict[str, Any] = {}

        def ping(seat: str, text: str, change: dict[str, Any]) -> None:
            line = f"- {text}: {issue.url}"
            events.append(Event(f"#{key}", "", seat, line, change, issue=key))

        if QUEUE_LABEL in issue.labels and not queued:
            ping(queue_seat, f"An issue was queued with `{QUEUE_LABEL}`", {QUEUE_LABEL: True})
        elif QUEUE_LABEL not in issue.labels and queued:
            updates[QUEUE_LABEL] = False
        if ANSWER_LABEL in issue.labels and not waiting:
            # Read now, before the answer adds signed comments of its own.
            updates |= {ANSWER_LABEL: True, "asker": self._asker(issue.number)}
        elif ANSWER_LABEL not in issue.labels and waiting:
            seat = (entry or {}).get("asker") or queue_seat
            text = f"The operator answered, and `{ANSWER_LABEL}` was removed"
            ping(seat, text, {ANSWER_LABEL: False, "asker": None})
        if updates:
            self._apply_issue(key, updates)
        return events

    def poll_tracker(self) -> None:
        """Ping when an open issue gains `rig-queue` or loses `needs-answer`."""
        assert self.tracker is not None
        issues = self.tracker.open_issues()
        known = self.state.setdefault("issues", {})
        open_keys = {str(issue.number) for issue in issues}
        for key in [key for key in known if key not in open_keys]:
            del known[key]  # Closed: a reopened issue starts afresh.
        by_seat: dict[str, list[Event]] = {}
        for issue in issues:
            for event in self._issue_events(issue, known.get(str(issue.number))):
                assert event.dispatcher is not None
                by_seat.setdefault(event.dispatcher, []).append(event)
        if by_seat:
            statuses = seat_statuses(self.rig, self.t3)
            threads = {s.seat.qualified_id: s.thread["threadId"] for s in statuses if s.thread}
            for seat, events in by_seat.items():
                self._deliver(seat, events, threads, ISSUE_CLOSING)
        save_state(self.path, self.state)

    def tick(self) -> None:
        statuses = seat_statuses(self.rig, self.t3)
        by_dispatcher: dict[str, list[Event]] = {}
        for status in statuses:
            dispatcher = self.dispatchers.get(status.seat.qualified_id)
            entry = self.state["seats"].get(status.session_name)
            events, updates = _check_seat(
                self.rig, status, entry, dispatcher, self.t3, self._waiting_on
            )
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
    tracker_interval: float = 60,
    make_tracker: Callable[..., Tracker] = tracker_for,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    if not dispatchers(rig) and rig.tracker is None:
        raise RigError(f"rig {rig.name} has no delegates_to edges, so there's nobody to ping")
    path = state_path(rig)
    tracker = make_tracker(rig.tracker) if rig.tracker else None
    with _single_watcher(path):
        watcher = Watcher(rig, t3, path, out, connect_mcp, tracker)
        next_poll = clock()
        while True:
            try:
                watcher.tick()
            except T3Error as error:
                out(f"can't read seats, will retry: {error}")
            if tracker is not None and clock() >= next_poll:
                next_poll = clock() + tracker_interval
                try:
                    watcher.poll_tracker()
                except (T3Error, TrackerError) as error:
                    out(f"can't read the tracker, will retry: {error}")
            if once:
                return
            sleep(interval)
