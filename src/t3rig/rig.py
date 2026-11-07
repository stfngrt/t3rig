"""Run a rig's seats as T3 threads. The thread title links a seat to its thread."""

import shlex
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t3rig.mcp import ACCESS_LEVELS
from t3rig.spec import Rig, Seat
from t3rig.t3 import T3Error
from t3rig.threads import (
    BUSY_STATUSES,
    NO_THREAD,
    T3,
    RigError,
    all_seat_threads,
    check_task,
    earlier_thread,
    is_busy,
    issue_of,
    issue_threads,
    seat_thread,
    seat_threads,
    task_threads,
    task_title,
    thread_label,
)

PROVIDERS = {"claude-code": "claudeAgent", "codex": "codex"}
# Seats are told to pass --from, so a send without it is taken to be from a person. An
# unknown-sender label made a dispatcher tell a seat to disregard a person's instructions.
DEFAULT_SENDER = "operator"
EFFORT_OPTIONS = {"claude-code": "effort", "codex": "reasoningEffort"}


@dataclass(frozen=True)
class SendResult:
    seat: Seat
    output: str = ""
    error: str | None = None


def seat_rows(rig: Rig, t3: T3) -> list[dict[str, Any]]:
    """Each seat's state for `ps`, including requests only `t3 thread show` reports."""
    rows = []
    for status in seat_threads(rig, t3):
        thread = status.thread or {}
        pending = 0
        if is_busy(thread):
            details = t3.show_thread(thread["threadId"], messages=0).get("thread", {})
            pending = details.get("pendingRequestCount", 0)
        rows.append(
            {
                "seat": status.seat.seat_id,
                "task": status.task,
                "session_name": status.session_name,
                "title": status.title,
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
        if edge.source == seat.seat_id:
            lines.append(f"- You {edge.kind} {edge.target}")
        elif edge.target == seat.seat_id:
            lines.append(f"- {edge.source} {edge.kind} you")
    return lines


def _task_lines(rig: Rig, seat: Seat, task: str | None, send_command: str) -> list[str]:
    """What the brief says about task threads (ADR 0008)."""
    lines = []
    if task:
        lines.append(
            f"This thread is for one task, {task}, and ends with it. The seat that delegates to "
            "you sends the task next; work only on it here."
        )
    workers = [
        e.target
        for e in rig.edges
        if e.kind == "delegates_to" and e.source == seat.seat_id and rig.per_task.get(e.target)
    ]
    if workers:
        lines.append(
            f"These seats get a new T3 thread per task: {', '.join(workers)}. Start one with "
            f'{send_command} --new --task "#N" <seat> "<task>" (a review round: --task "#N r2"), '
            f'reach it again with --task "#N", and archive an issue\'s task threads with '
            f'{t3rig_command("down", str(rig.path))} --task "#N".'
        )
    return lines


def seat_brief(rig: Rig, seat: Seat, task: str | None = None) -> str:
    """A seat's brief: the first message its thread receives. A task thread's says its task."""
    send_command = t3rig_command("send", "--from", seat.seat_id, str(rig.path))
    others = [s.seat_id for s in rig.seats if s != seat]
    parts = [
        f"You are seat {seat.seat_id} in the agent team (rig) {rig.name}.",
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
    parts += _task_lines(rig, seat, task, send_command)
    for item in seat.startup:
        parts.append(f"Instructions from {item.path}:\n{item.text.strip()}")
    parts.append("Reply with one short line saying you're ready, then wait for instructions.")
    return "\n\n".join(parts)


def _needs_mcp(seat: Seat) -> bool:
    return seat.runtime_mode is not None or seat.effort is not None


def _project_id(t3: T3, directory: Path) -> str:
    """The T3 project holding this folder; the deepest one if several do."""
    holding = [
        p
        for p in t3.projects()
        if p.get("workspaceRoot") and directory.is_relative_to(p["workspaceRoot"])
    ]
    if not holding:
        raise RigError(f"{directory} isn't inside a T3 project; add it with `t3 project add`")
    return max(holding, key=lambda p: len(p["workspaceRoot"]))["id"]


def _archive_quietly(t3: T3, thread_id: str) -> None:
    try:
        t3.archive(thread_id)
    except T3Error:
        pass  # The caller is already reporting the failure that led here.


def _launch(rig: Rig, t3: T3, seat: Seat, title: str, brief: str) -> None:
    """Launch idle, check T3 applied the settings, and only then send the brief."""
    arguments: dict[str, Any] = {
        "projectId": _project_id(t3, seat.cwd),
        "title": title,
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
    launched = t3.launch(**arguments)
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
            _archive_quietly(t3, thread_id)
            raise RigError(
                f"{seat.seat_id}: wanted {name} {wanted}, but T3 applied {actual}; "
                "archived the thread before it started"
            )
    t3.send(thread_id, brief)


def _start(rig: Rig, t3: T3, seat: Seat, title: str, brief: str) -> None:
    """Start a thread titled `title` for a seat, with its settings, and send it the brief."""
    if _needs_mcp(seat):
        _launch(rig, t3, seat, title, brief)
    else:
        provider = PROVIDERS[seat.runtime] if seat.model else None
        t3.start_thread(str(seat.cwd), title, brief, provider, seat.model)


def _check_started(seat: Seat, title: str, thread: dict[str, Any] | None) -> str:
    """Check T3 started the thread on the seat's runtime. Returns its line for the output."""
    if thread is None:
        raise RigError(f"{seat.seat_id}: started, but no thread titled {title}")
    provider = thread.get("providerInstanceId")
    if provider != PROVIDERS[seat.runtime]:
        raise RigError(
            f"{seat.seat_id}: expected {seat.runtime}, but T3 used {provider}. "
            "Set a model on this seat or change the project's default."
        )
    return f"started {thread['threadId']} ({thread.get('runtimeMode', 'unknown mode')})"


def _preflight(seats: list[Seat], t3: T3) -> None:
    """Refuse before starting anything, so a rig isn't left half up."""
    missing_model = [
        s.seat_id for s in seats if not s.model and (s.runtime != "claude-code" or s.effort)
    ]
    if missing_model:
        # T3 takes a provider and effort only with a model, so these would run on the default.
        raise RigError(f"these seats need a model for their runtime or effort: {missing_model}")
    restricted = [s for s in seats if _needs_mcp(s)]
    if not restricted:
        return
    access = t3.access()
    for seat in restricted:
        mode = seat.runtime_mode
        if mode and ACCESS_LEVELS.index(mode) > ACCESS_LEVELS.index(access):
            raise RigError(
                f"{seat.seat_id} needs {mode}, but you're signed in at {access}; "
                f"run `t3rig login --access {mode}` if you want to allow that"
            )


def up(rig: Rig, t3: T3) -> list[str]:
    """Start a thread for each seat without one. Safe to re-run. Returns status lines."""
    lines = []
    to_start = []
    for status in seat_threads(rig, t3):
        if rig.is_per_task(status.seat):
            if status.task is None:  # One line per seat, not per task thread.
                lines.append(
                    f"{status.seat.seat_id}: per-task seat, started per task with "
                    "`send --new --task`"
                )
            continue
        if status.thread is None:
            to_start.append(status)
        else:
            name = status.seat.seat_id
            lines.append(f"{name}: already has thread {status.thread['threadId']}")
    _preflight([s.seat for s in to_start], t3)

    for status in to_start:
        _start(rig, t3, status.seat, status.session_name, seat_brief(rig, status.seat))

    started = {status.seat for status in to_start}
    for status in seat_threads(rig, t3):
        if status.seat in started:
            started_line = _check_started(status.seat, status.session_name, status.thread)
            lines.append(f"{status.seat.seat_id}: {started_line}")
    return lines


def start_task(rig: Rig, t3: T3, seat: Seat, task: str) -> str:
    """Start a per-task seat's thread for a task, with its brief. Returns a line for the output.

    Refused if the seat isn't per-task, the task has a live thread already, or the seat would
    work on more than `max_parallel` issues at once.
    """
    if not rig.is_per_task(seat):
        raise RigError(
            f"{seat.seat_id} isn't a per-task seat; add it to per_task in rig.t3rig.yaml"
        )
    task = check_task(task)
    live = task_threads(rig, t3, seat)
    if any(s.task == task for s in live):
        raise RigError(f"{seat.seat_id} already has a live thread for task {task}")
    issues = {issue_of(s.task or "") for s in live}
    if issue_of(task) not in issues and len(issues) >= rig.max_parallel:
        raise RigError(
            f"{seat.seat_id} already works on {', '.join(sorted(issues))}, and max_parallel is "
            f"{rig.max_parallel}; archive a finished issue's threads with `down --task` first"
        )
    _preflight([seat], t3)
    title = task_title(rig.session_name(seat), task)
    _start(rig, t3, seat, title, seat_brief(rig, seat, task))
    thread = next((s.thread for s in task_threads(rig, t3, seat) if s.task == task), None)
    return f"{seat.seat_id} {task}: {_check_started(seat, title, thread)}"


def down(
    rig: Rig, t3: T3, seat: str | None = None, task: str | None = None
) -> tuple[list[str], bool]:
    """Interrupt and archive seats' threads, keeping transcripts. Returns lines and success.

    With `task`, only that issue's task threads, every seat's and every round's.
    """
    seats = select_seats(rig, seat, everyone=seat is None)
    if task is not None:
        found = issue_threads(rig, t3, check_task(task))
        threads = [(s, t) for s, _, t in found if s in seats]
    else:
        # Older threads with a seat's title go too, or the next would become the seat's thread.
        threads = all_seat_threads(rig, t3, seats)
    if not threads:
        return ["no threads to stop"], True
    t3.access()  # Sign in first, so a missing sign-in is one error rather than one per thread.
    lines, ok = [], True
    for owner, thread in threads:
        name, thread_id = thread_label(rig, owner, thread["title"]), thread["threadId"]
        try:
            if is_busy(thread):
                t3.interrupt(thread_id)
            t3.archive(thread_id)
            lines.append(f"{name}: archived {thread_id}")
        except T3Error as error:
            lines.append(f"{name}: couldn't stop {thread_id}: {error}")
            ok = False
    still_listed = {
        t["threadId"] for p in sorted({str(s.cwd) for s in seats}) for t in t3.list_threads(p)
    }
    for owner, thread in threads:
        if thread["threadId"] in still_listed and ok:
            label = thread_label(rig, owner, thread["title"])
            lines.append(f"{label}: {thread['threadId']} is still active")
            ok = False
    return lines, ok


def stop(
    rig: Rig,
    t3: T3,
    seat: str,
    sleep: Callable[[float], None] = time.sleep,
    wait_seconds: float = 30,
    task: str | None = None,
) -> str:
    """Interrupt a seat's current run, keeping its thread so it can be messaged again."""
    (chosen,) = select_seats(rig, seat)
    thread = seat_thread(rig, t3, chosen, check_task(task) if task else None)
    if not is_busy(thread):
        return f"{chosen.seat_id}: nothing to stop ({thread.get('status')})"
    thread_id = thread["threadId"]
    t3.interrupt(thread_id, reason="Stopped with t3rig stop")
    deadline = time.monotonic() + wait_seconds
    while True:
        status = t3.show_thread(thread_id, messages=0).get("thread", {}).get("status")
        if status not in BUSY_STATUSES:
            return f"{chosen.seat_id}: stopped ({status}); it can be messaged again"
        if time.monotonic() >= deadline:
            return f"{chosen.seat_id}: stop requested, but it's still {status}"
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
            known = ", ".join(s.seat_id for s in rig.seats)
            raise RigError(f"no seat {seat!r} in rig {rig.name} (seats: {known})")
        return [found]
    if pod is not None and not any(s.pod == pod for s in rig.seats):
        raise RigError(f"no pod {pod!r} in rig {rig.name}")
    chosen = [s for s in rig.seats if (everyone or s.pod == pod) and s.seat_id != sender]
    if not chosen:
        raise RigError("nobody to send to; the sender is the only seat selected")
    return chosen


def send(
    rig: Rig,
    t3: T3,
    seats: list[Seat],
    message: str,
    sender: str | None = None,
    raw: bool = False,
    wait: bool = False,
    task: str | None = None,
) -> list[SendResult]:
    """Message each seat. One seat failing doesn't stop the others.

    A per-task seat gets it on its `task`'s thread, or on its only live task thread.
    """
    task = check_task(task) if task is not None else None
    threads = {s.seat: s.thread for s in seat_threads(rig, t3) if not s.task}
    recipients = ", ".join(seat.seat_id for seat in seats)
    body = message if raw else envelope(sender or DEFAULT_SENDER, recipients, message)
    results = []
    for seat in seats:
        if rig.is_per_task(seat) or task is not None:
            try:
                thread = seat_thread(rig, t3, seat, task)
            except RigError as error:
                results.append(SendResult(seat, error=str(error)))
                continue
        else:
            thread = threads.get(seat)
        if thread is None:
            results.append(SendResult(seat, error=NO_THREAD))
            continue
        try:
            results.append(SendResult(seat, t3.send(thread["threadId"], body, wait=wait)))
        except T3Error as error:
            results.append(SendResult(seat, error=str(error)))
    return results


def log(
    rig: Rig,
    t3: T3,
    seat: str,
    messages: int,
    thread_id: str | None = None,
    task: str | None = None,
) -> str:
    """A seat's latest messages, as `t3 thread show` prints them; or the earlier `thread_id`.
    A per-task seat's come from its `task`'s thread, or its only live task thread."""
    if messages < 1:
        raise RigError("--messages must be at least 1")
    (chosen,) = select_seats(rig, seat)
    if thread_id is None:
        thread_id = seat_thread(rig, t3, chosen, check_task(task) if task else None)["threadId"]
    else:
        earlier_thread(rig, t3, chosen, thread_id)
    return t3.thread_text(thread_id, messages)
