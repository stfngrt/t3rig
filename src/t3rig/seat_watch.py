"""Seat watching: ping a seat's dispatcher when the seat finishes a run or needs input.

The dispatcher of a seat is the seat with a `delegates_to` edge to it. A ping only points at the
seat's thread. What has been pinged is kept under "seats" in the watch state, by session name.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from t3rig.delivery import Delivery, Ping
from t3rig.rig import t3rig_command
from t3rig.spec import Rig
from t3rig.t3 import T3Error
from t3rig.threads import T3, SeatThread, is_busy, seat_threads, thread_ids

EXCERPT_CHARS = 120
ACTIVITY_WINDOW = 100
STOPPED_STATUSES = {"interrupted", "cancelled"}
# T3 has no field for this, so it's read from the failed run's last reply.
USAGE_LIMIT = re.compile(r"\b(usage|rate|session|weekly|\d+-hour) limit\b|hit your .*limit", re.I)
CLOSING = (
    "Each line above points at a seat's thread; read it with `t3 thread show <id> --messages 3`. "
    "Reply to a seat only if there's more for it to do, and end your turn otherwise."
)


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
class SeatEvent:
    seat: str
    session_name: str
    dispatcher: str | None
    line: str
    updates: dict[str, Any] = field(default_factory=dict)
    needs_person: bool = False


def _thread_line(prefix: str, thread: dict[str, Any]) -> str:
    return f"- {prefix} Thread {thread['threadId']}: {thread.get('link', '')}".rstrip()


def waiting_approval(t3: T3, thread_id: str, item_count: int) -> str | None:
    """The newest approval a thread is waiting on, read from its activity, oldest item first."""
    after = max(item_count - ACTIVITY_WINDOW, 0)
    found = None
    while True:
        page = t3.activity(thread_id, after, ACTIVITY_WINDOW)
        for item in page.get("items", []):
            if item.get("type") == "approval_request" and item.get("status") == "waiting":
                found = item.get("text")
        if not page.get("hasMore") or page.get("nextPosition", after) <= after:
            return found
        after = page["nextPosition"]


def _check_seat(
    rig: Rig,
    status: SeatThread,
    entry: dict[str, Any] | None,
    dispatcher: str | None,
    t3: T3,
    waiting_on: Callable[[str, int], str | None],
) -> tuple[list[SeatEvent], dict[str, Any]]:
    """What happened on a seat since it was last checked, and the updates needing no ping."""
    thread = status.thread
    run = thread.get("latestRunId") if thread else None
    if thread is None or run is None:
        return [], {}
    seat = status.seat.seat_id
    busy = is_busy(thread)
    first_seen = entry is None
    known: dict[str, Any] = entry or {"run": None, "asked": None}
    if not busy and run == known["run"]:
        return [], {"asked": None} if known["asked"] else {}

    # `t3 thread list` lacks these fields, so only busy or changed threads pay for `show`.
    detail = t3.show_thread(thread["threadId"], messages=1)
    details = detail.get("thread", {})
    pending = details.get("pendingRequestCount", 0)
    events: list[SeatEvent] = []
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
                SeatEvent(
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
            # History from before watching, or the seat's reply to its brief.
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
                SeatEvent(
                    seat,
                    status.session_name,
                    dispatcher,
                    line,
                    {"run": run},
                    needs_person=bool(limited),
                )
            )
    return events, updates


class SeatWatch:
    """Each seat's runs and pending requests, compared with what the state says was pinged."""

    def __init__(self, rig: Rig, t3: T3, state: dict[str, Any], delivery: Delivery) -> None:
        self.rig, self.t3, self.delivery = rig, t3, delivery
        self.seats: dict[str, Any] = state.setdefault("seats", {})
        self.dispatchers = dispatchers(rig)

    def _waiting_on(self, thread_id: str, item_count: int) -> str | None:
        """What a seat is waiting on. A ping without it is still useful, so errors are dropped."""
        try:
            return waiting_approval(self.t3, thread_id, item_count)
        except T3Error:
            return None

    def _apply(self, session_name: str, updates: dict[str, Any]) -> None:
        if updates:
            self.seats.setdefault(session_name, {"run": None, "asked": None}).update(updates)

    def check(self) -> None:
        """One round: ping dispatchers about every seat that changed."""
        statuses = seat_threads(self.rig, self.t3)
        by_dispatcher: dict[str, list[Ping]] = {}
        for status in statuses:
            dispatcher = self.dispatchers.get(status.seat.seat_id)
            entry = self.seats.get(status.session_name)
            events, updates = _check_seat(
                self.rig, status, entry, dispatcher, self.t3, self._waiting_on
            )
            self._apply(status.session_name, updates)
            for event in events:
                # A dispatcher can't fix these, so a person has to hear about them too.
                if event.needs_person:
                    self.delivery.alert(event.line.removeprefix("- "))
                if event.dispatcher is None:
                    self._apply(event.session_name, event.updates)
                else:
                    by_dispatcher.setdefault(event.dispatcher, []).append(
                        Ping(
                            event.seat,
                            event.line,
                            lambda e=event: self._apply(e.session_name, e.updates),
                        )
                    )
        threads = thread_ids(statuses)
        for dispatcher, pings in by_dispatcher.items():
            self.delivery.send(dispatcher, pings, CLOSING, threads)
