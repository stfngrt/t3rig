"""Run a rig's seats as T3 threads. The thread title links a seat to its thread."""

import shlex
import sys
from dataclasses import dataclass
from typing import Any

from t3rig.spec import Rig, Seat
from t3rig.t3 import T3Cli

PROVIDERS = {"claude-code": "claudeAgent", "codex": "codex"}


class RigError(Exception):
    """The rig can't do what was asked."""


@dataclass(frozen=True)
class SeatStatus:
    seat: Seat
    session_name: str
    thread: dict[str, Any] | None


def seat_statuses(rig: Rig, t3: T3Cli) -> list[SeatStatus]:
    threads: dict[str, dict[str, Any]] = {}
    for project in sorted({str(seat.cwd) for seat in rig.seats}):
        for thread in t3.list_threads(project):
            threads.setdefault(thread["title"], thread)  # Newest first, so the newest wins.
    return [
        SeatStatus(seat, rig.session_name(seat), threads.get(rig.session_name(seat)))
        for seat in rig.seats
    ]


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
    send = shlex.join([sys.executable, "-m", "t3rig", "send", str(rig.path)])
    others = [s.qualified_id for s in rig.seats if s != seat]
    parts = [
        f"You are seat {seat.qualified_id} in the agent team (rig) {rig.name}.",
        f"Your working directory for this rig is {seat.cwd}. Change to it before working.",
    ]
    if rig.summary:
        parts.append(f"Team summary: {rig.summary}")
    if others:
        parts.append(f"Other seats: {', '.join(others)}")
        parts.append(f'To message a seat, run: {send} <seat> "<message>"')
    peers = _peer_lines(rig, seat)
    if peers:
        parts.append("Your relationships:\n" + "\n".join(peers))
    if rig.culture:
        parts.append(f"Team culture:\n{rig.culture.strip()}")
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


def send(rig: Rig, t3: T3Cli, qualified_id: str, message: str, wait: bool = False) -> str:
    seat = rig.seat(qualified_id)
    if seat is None:
        known = ", ".join(s.qualified_id for s in rig.seats)
        raise RigError(f"no seat {qualified_id!r} in rig {rig.name} (seats: {known})")
    status = next(s for s in seat_statuses(rig, t3) if s.seat == seat)
    if status.thread is None:
        raise RigError(f"{qualified_id} has no thread; run `t3rig up` first")
    return t3.send(status.thread["threadId"], message, wait=wait)
