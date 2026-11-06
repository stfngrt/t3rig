"""Seats' T3 threads, behind one seam.

A seat's thread is the newest thread titled with its session name (ADR 0001). Callers find a seat's
thread here and act on it through the `T3` interface. Which of T3's two interfaces does each action,
the `t3` CLI or the signed-in `/mcp` tools, stays inside the adapters: `T3Code` for a running
T3 Code, and `MemoryT3`, which keeps threads in memory, for tests.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from t3rig.mcp import McpClient, load_credential
from t3rig.spec import Rig, Seat
from t3rig.t3 import T3Cli, T3Error

BUSY_STATUSES = {"preparing", "queued", "starting", "running", "waiting"}
NO_THREAD = "no thread; run `t3rig up` first"


class RigError(Exception):
    """The rig can't do what was asked."""


class T3(Protocol):
    """What t3rig needs from T3 Code."""

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        """Threads in the project holding this folder, newest first. Archived ones aren't listed."""
        ...

    def show_thread(self, thread_id: str, messages: int = 1) -> dict[str, Any]:
        """A thread's state under "thread" and its latest messages under "messages"."""
        ...

    def thread_text(self, thread_id: str, messages: int) -> str: ...

    def start_thread(
        self, project: str, title: str, message: str, provider: str | None, model: str | None
    ) -> str: ...

    def send(self, thread_id: str, message: str, wait: bool = False) -> str: ...

    # These need the /mcp sign-in, which is made on first use.
    def access(self) -> str:
        """The access level of the sign-in."""
        ...

    def projects(self) -> list[dict[str, Any]]: ...

    def launch(self, **arguments: Any) -> dict[str, Any]:
        """Start an idle thread with `t3_thread_launch`'s arguments."""
        ...

    def interrupt(self, thread_id: str, reason: str | None = None) -> None: ...

    def archive(self, thread_id: str) -> None: ...

    def activity(self, thread_id: str, after: int, limit: int) -> dict[str, Any]:
        """One page of a thread's activity, oldest item first."""
        ...


class Tools(Protocol):
    def call(self, tool: str, **arguments: Any) -> Any: ...


def connect_mcp() -> tuple[Tools, str]:
    """A client for T3's /mcp tools and the access level it's signed in at."""
    return McpClient.from_credential(), load_credential()["access"]


class T3Code:
    """The adapter for a running T3 Code: the `t3` CLI, and /mcp for what the CLI can't do."""

    def __init__(
        self, cli: T3Cli | None = None, connect: Callable[[], tuple[Tools, str]] = connect_mcp
    ) -> None:
        self.cli = cli or T3Cli()
        self.connect = connect
        self.signed_in: tuple[Tools, str] | None = None

    def _call(self, tool: str, **arguments: Any) -> Any:
        if self.signed_in is None:
            self.signed_in = self.connect()
        try:
            return self.signed_in[0].call(tool, **arguments)
        except T3Error:
            self.signed_in = None  # Sign in afresh next time, in case the session went stale.
            raise

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        return self.cli.list_threads(project)

    def show_thread(self, thread_id: str, messages: int = 1) -> dict[str, Any]:
        return self.cli.show_thread(thread_id, messages)

    def thread_text(self, thread_id: str, messages: int) -> str:
        return self.cli.thread_text(thread_id, messages)

    def start_thread(
        self, project: str, title: str, message: str, provider: str | None, model: str | None
    ) -> str:
        return self.cli.start_thread(project, title, message, provider, model)

    def send(self, thread_id: str, message: str, wait: bool = False) -> str:
        return self.cli.send(thread_id, message, wait)

    def access(self) -> str:
        if self.signed_in is None:
            self.signed_in = self.connect()
        return self.signed_in[1]

    def projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        cursor = None
        while True:
            args = {"limit": 100, **({"cursor": cursor} if cursor is not None else {})}
            page = self._call("t3_project_list", **args)
            projects += page.get("projects", [])
            cursor = page.get("nextCursor")
            if cursor is None:
                return projects

    def launch(self, **arguments: Any) -> dict[str, Any]:
        return self._call("t3_thread_launch", **arguments)

    def interrupt(self, thread_id: str, reason: str | None = None) -> None:
        self._call(
            "t3_thread_interrupt", threadId=thread_id, **({"reason": reason} if reason else {})
        )

    def archive(self, thread_id: str) -> None:
        self._call("t3_thread_organize", action="archive", threadId=thread_id)

    def activity(self, thread_id: str, after: int, limit: int) -> dict[str, Any]:
        return self._call(
            "t3_thread_read", threadId=thread_id, view="activity", afterPosition=after, limit=limit
        )


@dataclass
class MemoryT3:
    """The in-memory adapter: threads, messages and what was sent, with no T3 running."""

    provider: str = "claudeAgent"
    project_root: str = "/"
    access_level: str | None = "auto"  # None: not signed in to /mcp.
    applied_mode: str | None = None  # Launch with this mode whatever was asked.
    threads: list[dict[str, Any]] = field(default_factory=list)  # Newest first.
    archived: list[dict[str, Any]] = field(default_factory=list)
    messages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    activity_pages: list[dict[str, Any]] = field(default_factory=list)
    sent: list[tuple[str, str, bool]] = field(default_factory=list)
    started: list[dict[str, Any]] = field(default_factory=list)
    actions: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # /mcp calls.
    shown: list[tuple[str, int]] = field(default_factory=list)  # `thread_text` calls.
    read: list[str] = field(default_factory=list)  # `show_thread` calls.
    send_error: Exception | None = None
    fail_archive: bool = False
    keep_running: bool = False  # Ignore interrupts.

    def put(self, title: str, **fields: Any) -> dict[str, Any]:
        """Add a thread as the newest, or update the one with the same id (default `id-<title>`)."""
        thread_id = fields.pop("threadId", f"id-{title}")
        found = next((t for t in self.threads if t["threadId"] == thread_id), None)
        if found is None:
            found = {"threadId": thread_id, "title": title}
            self.threads.insert(0, found)
        found.update(fields)
        return found

    def say(self, thread_id: str, text: str, role: str = "assistant") -> None:
        self.messages.setdefault(thread_id, []).append({"role": role, "text": text})

    def _signed_in(self, action: str, **arguments: Any) -> None:
        if self.access_level is None:
            raise T3Error("not signed in to T3's /mcp; run `t3rig login --access <level>`")
        self.actions.append((action, arguments))

    def _find(self, thread_id: str) -> dict[str, Any]:
        for thread in [*self.threads, *self.archived]:
            if thread["threadId"] == thread_id:
                return thread
        raise T3Error(f"`thread show` exited 1: Thread {thread_id} is no longer available.")

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        return list(self.threads)

    def show_thread(self, thread_id: str, messages: int = 1) -> dict[str, Any]:
        self.read.append(thread_id)
        thread = self._find(thread_id)
        latest = self.messages.get(thread_id, [])[-messages:] if messages else []
        return {"thread": thread, "messages": latest}

    def thread_text(self, thread_id: str, messages: int) -> str:
        self._find(thread_id)
        self.shown.append((thread_id, messages))
        latest = self.messages.get(thread_id, [])[-messages:]
        return "".join(f"[{m['role']}]\n{m['text']}\n" for m in latest)

    def start_thread(
        self, project: str, title: str, message: str, provider: str | None, model: str | None
    ) -> str:
        self.started.append(
            {"title": title, "message": message, "provider": provider, "model": model}
        )
        thread = self.put(title, status="running", providerInstanceId=self.provider)
        return thread["threadId"]

    def send(self, thread_id: str, message: str, wait: bool = False) -> str:
        if self.send_error:
            raise self.send_error
        self.sent.append((thread_id, message, wait))
        return "Sent."

    def access(self) -> str:
        if self.access_level is None:
            raise T3Error("not signed in to T3's /mcp; run `t3rig login --access <level>`")
        return self.access_level

    def projects(self) -> list[dict[str, Any]]:
        self._signed_in("projects")
        return [{"id": "p1", "workspaceRoot": self.project_root}]

    def launch(self, **arguments: Any) -> dict[str, Any]:
        self._signed_in("launch", **arguments)
        selection = arguments.get("modelSelection", {})
        thread = self.put(
            arguments["title"],
            status="idle",
            providerInstanceId=selection.get("instanceId", self.provider),
            model=selection.get("model", "default-model"),
            runtimeMode=self.applied_mode or arguments.get("runtimeMode", "full-access"),
        )
        options = [{"id": k, "value": v} for k, v in selection.get("options", {}).items()]
        return {"threadId": thread["threadId"], "modelSelection": {"options": options}}

    def interrupt(self, thread_id: str, reason: str | None = None) -> None:
        self._signed_in("interrupt", threadId=thread_id)
        if not self.keep_running:
            self._find(thread_id)["status"] = "interrupted"

    def archive(self, thread_id: str) -> None:
        self._signed_in("archive", threadId=thread_id)
        if self.fail_archive:
            raise T3Error("nope")
        thread = self._find(thread_id)
        self.threads.remove(thread)
        self.archived.insert(0, thread)

    def activity(self, thread_id: str, after: int, limit: int) -> dict[str, Any]:
        self._signed_in("activity", threadId=thread_id, afterPosition=after, limit=limit)
        return self.activity_pages.pop(0) if self.activity_pages else {"items": []}


def is_busy(thread: dict[str, Any] | None) -> bool:
    return bool(thread) and thread.get("status") in BUSY_STATUSES


@dataclass(frozen=True)
class SeatThread:
    """A seat, its session name, its current thread if any, and how many older threads share it."""

    seat: Seat
    session_name: str
    thread: dict[str, Any] | None
    duplicates: int = 0


def _listed(rig: Rig, t3: T3, seats: tuple[Seat, ...] | list[Seat]) -> list[dict[str, Any]]:
    """Every listed thread in the seats' projects, newest first."""
    return [t for p in sorted({str(s.cwd) for s in seats}) for t in t3.list_threads(p)]


def seat_threads(rig: Rig, t3: T3) -> list[SeatThread]:
    """Each seat's current thread: the newest thread titled with its session name."""
    threads: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for thread in _listed(rig, t3, rig.seats):
        threads.setdefault(thread["title"], thread)  # Newest first, so the newest wins.
        counts[thread["title"]] += 1
    found = []
    for seat in rig.seats:
        name = rig.session_name(seat)
        found.append(SeatThread(seat, name, threads.get(name), max(counts[name] - 1, 0)))
    return found


def seat_thread(rig: Rig, t3: T3, seat: Seat) -> dict[str, Any]:
    """The seat's current thread, or a RigError saying to start it."""
    thread = next(s.thread for s in seat_threads(rig, t3) if s.seat == seat)
    if thread is None:
        raise RigError(f"{seat.qualified_id} has {NO_THREAD}")
    return thread


def thread_ids(found: list[SeatThread]) -> dict[str, str]:
    """Seat id to current thread id, for the seats that have one."""
    return {s.seat.qualified_id: s.thread["threadId"] for s in found if s.thread}


def all_seat_threads(rig: Rig, t3: T3, seats: list[Seat]) -> list[tuple[Seat, dict[str, Any]]]:
    """Every listed thread titled with one of these seats' session names, older ones included."""
    by_name = {rig.session_name(s): s for s in seats}
    return [(by_name[t["title"]], t) for t in _listed(rig, t3, seats) if t["title"] in by_name]


def earlier_thread(rig: Rig, t3: T3, seat: Seat, thread_id: str) -> None:
    """Check that a thread, perhaps archived and so unlisted, is one of the seat's."""
    title = t3.show_thread(thread_id, messages=0).get("thread", {}).get("title")
    name = rig.session_name(seat)
    if title != name:
        raise RigError(f"thread {thread_id} is {title!r}, not {seat.qualified_id}'s {name!r}")
