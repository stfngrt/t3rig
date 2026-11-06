"""Run a rig's seats as T3 threads. The thread title links a seat to its thread."""

import shlex
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from t3rig.mcp import ACCESS_LEVELS, McpClient, load_credential
from t3rig.spec import Rig, Seat
from t3rig.t3 import T3Cli, T3Error

PROVIDERS = {"claude-code": "claudeAgent", "codex": "codex"}
BUSY_STATUSES = {"preparing", "queued", "starting", "running", "waiting"}
# Seats are told to pass --from, so a send without it is taken to be from a person. An
# unknown-sender label made a dispatcher tell a seat to disregard a person's instructions.
DEFAULT_SENDER = "operator"
EFFORT_OPTIONS = {"claude-code": "effort", "codex": "reasoningEffort"}


class RigError(Exception):
    """The rig can't do what was asked."""


class Tools(Protocol):
    def call(self, tool: str, **arguments: Any) -> Any: ...


def connect_mcp() -> tuple[Tools, str]:
    """A client for T3's /mcp tools and the access level it's signed in at."""
    return McpClient.from_credential(), load_credential()["access"]


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


def ago(timestamp: str | None) -> str:
    """How long ago an ISO timestamp was, as `ps` shows it."""
    if not timestamp:
        return "-"
    seconds = int((datetime.now(UTC) - datetime.fromisoformat(timestamp)).total_seconds())
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return f"{max(seconds, 0)}s ago"


def t3rig_command(*arguments: str) -> str:
    """A shell command for this t3rig, which works for a seat without t3rig on its PATH."""
    return shlex.join([sys.executable, "-m", "t3rig", *arguments])


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
    send_command = t3rig_command("send", "--from", seat.qualified_id, str(rig.path))
    others = [s.qualified_id for s in rig.seats if s != seat]
    parts = [
        f"You are seat {seat.qualified_id} in the agent team (rig) {rig.name}.",
        f"Your working directory for this rig is {seat.cwd}. Change to it before working.",
    ]
    if rig.summary:
        parts.append(f"Team summary: {rig.summary}")
    if others:
        parts.append(f"Other seats: {', '.join(others)}")
        parts.append(f'To message a seat, run: {send_command} <seat> "<message>"')
    peers = _peer_lines(rig, seat)
    if peers:
        parts.append("Your relationships:\n" + "\n".join(peers))
    for item in seat.startup:
        parts.append(f"Instructions from {item.path}:\n{item.text.strip()}")
    parts.append("Reply with one short line saying you're ready, then wait for instructions.")
    return "\n\n".join(parts)


def _needs_mcp(seat: Seat) -> bool:
    return seat.runtime_mode is not None or seat.effort is not None


def _project_id(tools: Tools, directory: Path) -> str:
    """The T3 project holding this folder; the deepest one if several do."""
    projects: list[dict[str, Any]] = []
    cursor = None
    while True:
        args = {"limit": 100, **({"cursor": cursor} if cursor is not None else {})}
        page = tools.call("t3_project_list", **args)
        projects += page.get("projects", [])
        cursor = page.get("nextCursor")
        if cursor is None:
            break
    holding = [
        p
        for p in projects
        if p.get("workspaceRoot") and directory.is_relative_to(p["workspaceRoot"])
    ]
    if not holding:
        raise RigError(f"{directory} isn't inside a T3 project; add it with `t3 project add`")
    return max(holding, key=lambda p: len(p["workspaceRoot"]))["id"]


def _archive_quietly(tools: Tools, thread_id: str) -> None:
    try:
        tools.call("t3_thread_organize", action="archive", threadId=thread_id)
    except T3Error:
        pass  # The caller is already reporting the failure that led here.


def _launch(rig: Rig, tools: Tools, t3: T3Cli, seat: Seat, status: SeatStatus) -> None:
    """Launch idle, check T3 applied the settings, and only then send the first message."""
    arguments: dict[str, Any] = {
        "projectId": _project_id(tools, seat.cwd),
        "title": status.session_name,
    }
    option = EFFORT_OPTIONS[seat.runtime]
    if seat.runtime_mode:
        arguments["runtimeMode"] = seat.runtime_mode
    if seat.model:
        arguments["modelSelection"] = {
            "instanceId": PROVIDERS[seat.runtime],
            "model": seat.model,
            **({"options": {option: seat.effort}} if seat.effort else {}),
        }
    launched = tools.call("t3_thread_launch", **arguments)
    thread_id = launched["threadId"]
    thread = t3.show_thread(thread_id, messages=0).get("thread", {})
    applied_options = launched.get("modelSelection", {}).get("options") or []
    checks = [
        ("mode", seat.runtime_mode, thread.get("runtimeMode")),
        ("provider", PROVIDERS[seat.runtime], thread.get("providerInstanceId")),
        ("model", seat.model, thread.get("model")),
        (
            "effort",
            seat.effort,
            next((o.get("value") for o in applied_options if o.get("id") == option), None),
        ),
    ]
    for name, wanted, actual in checks:
        if wanted is not None and wanted != actual:
            _archive_quietly(tools, thread_id)
            raise RigError(
                f"{seat.qualified_id}: wanted {name} {wanted}, but T3 applied {actual}; "
                "archived the thread before it started"
            )
    t3.send(thread_id, seat_brief(rig, seat))


def _preflight(seats: list[Seat], connect: Callable[[], tuple[Tools, str]]) -> Tools | None:
    """Refuse before starting anything, so a rig isn't left half up."""
    missing_model = [
        s.qualified_id for s in seats if not s.model and (s.runtime != "claude-code" or s.effort)
    ]
    if missing_model:
        # T3 takes a provider and effort only with a model, so these would run on the default.
        raise RigError(f"these seats need a model for their runtime or effort: {missing_model}")
    restricted = [s for s in seats if _needs_mcp(s)]
    if not restricted:
        return None
    tools, access = connect()
    for seat in restricted:
        mode = seat.runtime_mode
        if mode and ACCESS_LEVELS.index(mode) > ACCESS_LEVELS.index(access):
            raise RigError(
                f"{seat.qualified_id} needs {mode}, but you're signed in at {access}; "
                f"run `t3rig login --access {mode}` if you want to allow that"
            )
    return tools


def up(rig: Rig, t3: T3Cli, connect: Callable[[], tuple[Tools, str]] = connect_mcp) -> list[str]:
    """Start a thread for each seat without one. Safe to re-run. Returns status lines."""
    lines = []
    to_start = []
    for status in seat_statuses(rig, t3):
        if status.thread is None:
            to_start.append(status)
        else:
            name = status.seat.qualified_id
            lines.append(f"{name}: already has thread {status.thread['threadId']}")
    tools = _preflight([s.seat for s in to_start], connect)

    for status in to_start:
        seat = status.seat
        if _needs_mcp(seat):
            _launch(rig, tools, t3, seat, status)
        else:
            provider = PROVIDERS[seat.runtime] if seat.model else None
            t3.start_thread(
                str(seat.cwd), status.session_name, seat_brief(rig, seat), provider, seat.model
            )

    started = {status.seat for status in to_start}
    for status in seat_statuses(rig, t3):
        seat = status.seat
        if seat not in started:
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
        mode = status.thread.get("runtimeMode", "unknown mode")
        lines.append(f"{seat.qualified_id}: started {status.thread['threadId']} ({mode})")
    return lines


def down(
    rig: Rig,
    t3: T3Cli,
    seat: str | None = None,
    connect: Callable[[], tuple[Tools, str]] = connect_mcp,
) -> tuple[list[str], bool]:
    """Interrupt and archive seats' threads, keeping transcripts. Returns lines and success."""
    seats = select_seats(rig, seat, everyone=seat is None)
    names = {rig.session_name(s): s.qualified_id for s in seats}
    projects = sorted({str(s.cwd) for s in seats})
    # Older threads with a seat's title go too, or the next one would become the seat's thread.
    threads = [t for p in projects for t in t3.list_threads(p) if t["title"] in names]
    if not threads:
        return ["no threads to stop"], True
    tools, _ = connect()
    lines, ok = [], True
    for thread in threads:
        name, thread_id = names[thread["title"]], thread["threadId"]
        try:
            if thread.get("status") in BUSY_STATUSES:
                tools.call("t3_thread_interrupt", threadId=thread_id)
            tools.call("t3_thread_organize", action="archive", threadId=thread_id)
            lines.append(f"{name}: archived {thread_id}")
        except T3Error as error:
            lines.append(f"{name}: couldn't stop {thread_id}: {error}")
            ok = False
    still_listed = {t["threadId"] for p in projects for t in t3.list_threads(p)}
    for thread in threads:
        if thread["threadId"] in still_listed and ok:
            lines.append(f"{names[thread['title']]}: {thread['threadId']} is still active")
            ok = False
    return lines, ok


def stop(
    rig: Rig,
    t3: T3Cli,
    seat: str,
    connect: Callable[[], tuple[Tools, str]] = connect_mcp,
    sleep: Callable[[float], None] = time.sleep,
    wait_seconds: float = 30,
) -> str:
    """Interrupt a seat's current run, keeping its thread so it can be messaged again."""
    (chosen,) = select_seats(rig, seat)
    thread = next(s.thread for s in seat_statuses(rig, t3) if s.seat == chosen)
    if thread is None:
        raise RigError(f"{chosen.qualified_id} has no thread; run `t3rig up` first")
    if thread.get("status") not in BUSY_STATUSES:
        return f"{chosen.qualified_id}: nothing to stop ({thread.get('status')})"
    thread_id = thread["threadId"]
    tools, _ = connect()
    tools.call("t3_thread_interrupt", threadId=thread_id, reason="Stopped with t3rig stop")
    deadline = time.monotonic() + wait_seconds
    while True:
        status = t3.show_thread(thread_id, messages=0).get("thread", {}).get("status")
        if status not in BUSY_STATUSES:
            return f"{chosen.qualified_id}: stopped ({status}); it can be messaged again"
        if time.monotonic() >= deadline:
            return f"{chosen.qualified_id}: stop requested, but it's still {status}"
        sleep(2)


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
    body = message if raw else envelope(sender or DEFAULT_SENDER, recipients, message)
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


def log(rig: Rig, t3: T3Cli, seat: str, messages: int) -> str:
    """A seat's latest messages, as `t3 thread show` prints them."""
    if messages < 1:
        raise RigError("--messages must be at least 1")
    (chosen,) = select_seats(rig, seat)
    thread = next(s.thread for s in seat_statuses(rig, t3) if s.seat == chosen)
    if thread is None:
        raise RigError(f"{chosen.qualified_id} has no thread; run `t3rig up` first")
    return t3.thread_text(thread["threadId"], messages)
