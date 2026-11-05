"""Run a rig's seats as T3 threads. The thread title links a seat to its thread."""

import shlex
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

from t3rig.spec import Rig, Seat
from t3rig.t3 import T3Cli, T3Error

PROVIDERS = {"claude-code": "claudeAgent", "codex": "codex"}
BUSY_STATUSES = {"preparing", "queued", "starting", "running", "waiting"}
UNKNOWN_SENDER = "<unknown sender>"


class RigError(Exception):
    """The rig can't do what was asked."""


@dataclass(frozen=True)
class SeatStatus:
    seat: Seat
    session_name: str
    thread: dict[str, Any] | None
    duplicates: int = 0


@dataclass(frozen=True)
class SendResult:
    seat: Seat
    output: str = ""
    error: str | None = None


def seat_statuses(rig: Rig, t3: T3Cli) -> list[SeatStatus]:
    threads: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for project in sorted({str(seat.cwd) for seat in rig.seats}):
        for thread in t3.list_threads(project):
            threads.setdefault(thread["title"], thread)  # Newest first, so the newest wins.
            counts[thread["title"]] += 1
    statuses = []
    for seat in rig.seats:
        name = rig.session_name(seat)
        statuses.append(SeatStatus(seat, name, threads.get(name), max(counts[name] - 1, 0)))
    return statuses


def seat_rows(rig: Rig, t3: T3Cli) -> list[dict[str, Any]]:
    """Each seat's state for `ps`, including requests only `t3 thread show` reports."""
    rows = []
    for status in seat_statuses(rig, t3):
        thread = status.thread or {}
        pending = 0
        if thread.get("status") in BUSY_STATUSES:
            details = t3.show_thread(thread["threadId"], messages=0).get("thread", {})
            pending = details.get("pendingRequestCount", 0)
        rows.append(
            {
                "seat": status.seat.qualified_id,
                "session_name": status.session_name,
                "runtime": status.seat.runtime,
                "model": thread.get("model") or status.seat.model,
                "mode": thread.get("runtimeMode"),
                "status": thread.get("status", "not started"),
                "pending_requests": pending,
                "updated_at": thread.get("updatedAt"),
                "thread_id": thread.get("threadId"),
                "link": thread.get("link"),
                "extra_threads": status.duplicates,
            }
        )
    return rows


def envelope(sender: str, recipient: str, body: str) -> str:
    """OpenRig's From/To wrapper, so the recipient can tell who a message is from."""
    return f"From: {sender}\nTo: {recipient}\n---\n{body}"


def _peer_lines(rig: Rig, seat: Seat) -> list[str]:
    lines = []
    for edge in rig.edges:
        if edge.source == seat.qualified_id:
            lines.append(f"- You {edge.kind} {edge.target}")
        elif edge.target == seat.qualified_id:
            lines.append(f"- {edge.source} {edge.kind} you")
    return lines


def seat_brief(rig: Rig, seat: Seat) -> str:
    """The first message a seat's thread receives."""
    send_command = [sys.executable, "-m", "t3rig", "send", "--from", seat.qualified_id]
    send_command.append(str(rig.path))
    others = [s.qualified_id for s in rig.seats if s != seat]
    parts = [
        f"You are seat {seat.qualified_id} in the agent team (rig) {rig.name}.",
        f"Your working directory for this rig is {seat.cwd}. Change to it before working.",
    ]
    if rig.summary:
        parts.append(f"Team summary: {rig.summary}")
    if others:
        parts.append(f"Other seats: {', '.join(others)}")
        parts.append(f'To message a seat, run: {shlex.join(send_command)} <seat> "<message>"')
    peers = _peer_lines(rig, seat)
    if peers:
        parts.append("Your relationships:\n" + "\n".join(peers))
    for item in seat.startup:
        parts.append(f"Instructions from {item.path}:\n{item.text.strip()}")
    parts.append("Reply with one short line saying you're ready, then wait for instructions.")
    return "\n\n".join(parts)


def up(rig: Rig, t3: T3Cli) -> list[str]:
    """Start a thread for each seat without one. Safe to re-run. Returns status lines."""
    missing_model = [
        s.qualified_id for s in rig.seats if s.runtime != "claude-code" and not s.model
    ]
    if missing_model:
        # `t3 thread start` takes a provider only with a model, so this would run on the default.
        raise RigError(f"these seats need a model to run on their own runtime: {missing_model}")

    lines = []
    started = []
    for status in seat_statuses(rig, t3):
        seat = status.seat
        if status.thread is not None:
            lines.append(f"{seat.qualified_id}: already has thread {status.thread['threadId']}")
            continue
        provider = PROVIDERS[seat.runtime] if seat.model else None
        t3.start_thread(
            str(seat.cwd), status.session_name, seat_brief(rig, seat), provider, seat.model
        )
        started.append(seat.qualified_id)

    for status in seat_statuses(rig, t3):
        seat = status.seat
        if seat.qualified_id not in started:
            continue
        if status.thread is None:
            raise RigError(
                f"{seat.qualified_id}: started, but no thread titled {status.session_name}"
            )
        provider = status.thread.get("providerInstanceId")
        if provider != PROVIDERS[seat.runtime]:
            raise RigError(
                f"{seat.qualified_id}: expected {seat.runtime}, but T3 used {provider}. "
                "Set a model on this seat or change the project's default."
            )
        lines.append(f"{seat.qualified_id}: started {status.thread['threadId']}")
    return lines


def select_seats(
    rig: Rig,
    seat: str | None = None,
    pod: str | None = None,
    everyone: bool = False,
    sender: str | None = None,
) -> list[Seat]:
    """The seats a message goes to. Fan-out never includes the sender."""
    if sender is not None and rig.seat(sender) is None:
        raise RigError(f"--from: no seat {sender!r} in rig {rig.name}")
    if seat is not None:
        found = rig.seat(seat)
        if found is None:
            known = ", ".join(s.qualified_id for s in rig.seats)
            raise RigError(f"no seat {seat!r} in rig {rig.name} (seats: {known})")
        return [found]
    if pod is not None and not any(s.pod == pod for s in rig.seats):
        raise RigError(f"no pod {pod!r} in rig {rig.name}")
    chosen = [s for s in rig.seats if (everyone or s.pod == pod) and s.qualified_id != sender]
    if not chosen:
        raise RigError("nobody to send to; the sender is the only seat selected")
    return chosen


def send(
    rig: Rig,
    t3: T3Cli,
    seats: list[Seat],
    message: str,
    sender: str | None = None,
    raw: bool = False,
    wait: bool = False,
) -> list[SendResult]:
    """Message each seat. One seat failing doesn't stop the others."""
    threads = {s.seat: s.thread for s in seat_statuses(rig, t3)}
    recipients = ", ".join(seat.qualified_id for seat in seats)
    body = message if raw else envelope(sender or UNKNOWN_SENDER, recipients, message)
    results = []
    for seat in seats:
        thread = threads.get(seat)
        if thread is None:
            results.append(SendResult(seat, error="no thread; run `t3rig up` first"))
            continue
        try:
            results.append(SendResult(seat, t3.send(thread["threadId"], body, wait=wait)))
        except T3Error as error:
            results.append(SendResult(seat, error=str(error)))
    return results
