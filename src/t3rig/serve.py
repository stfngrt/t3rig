"""Run one rig's orchestration as a server, with a live, read-only status page on localhost.

The `watch` loop runs as an asyncio task. The page reads the same sources as `ps`, `log` and
`watch`, and keeps only a short in-memory list of recent events.
"""

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, PackageLoader

from t3rig.rig import ago, connect_mcp, seat_rows
from t3rig.spec import Rig
from t3rig.t3 import T3Cli, T3Error
from t3rig.tracker import Issue, Tracker, tracker_for
from t3rig.watch import (
    ANSWER_LABEL,
    IN_PROGRESS_LABEL,
    QUEUE_LABEL,
    Watcher,
    dispatchers,
    last_check,
    single_watcher,
    state_path,
)

HOST = "127.0.0.1"  # No login, so never reachable from another machine.
ALLOWED_HOSTS = [HOST, "localhost"]
MAX_EVENTS = 200
KEEPALIVE_SECONDS = 15
APPROVAL_LABEL = "needs-approval"
FRAGMENTS = ("seats", "issues", "events")


def seats_with_activity(rig: Rig, t3: T3Cli) -> list[dict[str, Any]]:
    """`ps`'s rows, each with the seat's latest message, as `log --messages 1` shows it."""
    rows = seat_rows(rig, t3)
    for row in rows:
        last = None
        if row["thread_id"]:
            messages = t3.show_thread(row["thread_id"], messages=1).get("messages") or []
            if messages:
                last = {"role": messages[-1].get("role"), "text": messages[-1].get("text") or ""}
        row["last_activity"] = last
    return rows


def _issue_row(issue: Issue) -> dict[str, Any]:
    return {
        "number": issue.number,
        "title": issue.title,
        "url": issue.url,
        "labels": sorted(issue.labels),
    }


def sort_issues(issues: list[Issue]) -> dict[str, list[dict[str, Any]]]:
    """Issues waiting on the operator, and the lead's queue. `rig-queue` wins over approval."""
    needs_you, queue = [], []
    for issue in sorted(issues, key=lambda i: i.number):
        labels = issue.labels
        if ANSWER_LABEL in labels or (APPROVAL_LABEL in labels and QUEUE_LABEL not in labels):
            needs_you.append(_issue_row(issue))
        elif labels & {QUEUE_LABEL, IN_PROGRESS_LABEL}:
            queue.append(_issue_row(issue))
    return {"needs_you": needs_you, "queue": queue}


def sse_message(event: str, data: str) -> str:
    lines = "".join(f"data: {line}\n" for line in data.splitlines() or [""])
    return f"event: {event}\n{lines}\n"


class RigServer:
    """One rig's watch loop and the status the page shows."""

    def __init__(
        self,
        rig: Rig,
        t3: T3Cli,
        interval: float = 15,
        tracker_interval: float = 60,
        make_tracker: Callable[..., Tracker] = tracker_for,
        connect: Callable[..., Any] | None = connect_mcp,
        out: Callable[[str], None] = print,
    ) -> None:
        self.rig, self.t3, self.interval, self.print = rig, t3, interval, out
        self.seats: list[dict[str, Any]] = []
        self.issues: list[Issue] = []
        self.events: deque[dict[str, str]] = deque(maxlen=MAX_EVENTS)
        self.version = 0
        self.changed = asyncio.Condition()
        self.templates = Environment(loader=PackageLoader("t3rig", "templates"), autoescape=True)
        self.templates.filters["ago"] = ago
        self.watcher: Watcher | None = None
        self.closing = False
        self.loop: asyncio.AbstractEventLoop | None = None
        if dispatchers(rig) or rig.tracker:
            tracker = make_tracker(rig.tracker) if rig.tracker else None
            path = state_path(rig)
            self.watcher = Watcher(
                rig, t3, path, self.log, connect, tracker, tracker_interval=tracker_interval
            )

    def log(self, text: str, kind: str = "watch") -> None:
        """Print a line as `watch` does, and add it to the page's stream. Safe from any thread."""
        self.print(text)
        self.events.appendleft(
            {"time": datetime.now().astimezone().isoformat(), "kind": kind, "text": text}
        )

    def refresh(self) -> None:
        """Read the seats again, noting each status change. Blocking, so run it in a thread."""
        try:
            seats = seats_with_activity(self.rig, self.t3)
        except T3Error as error:
            self.log(f"can't read seats, will retry: {error}", "error")
            return
        before = {row["seat"]: row["status"] for row in self.seats}
        for row in seats:
            old = before.get(row["seat"])
            if old is not None and old != row["status"]:
                self.log(f"{row['seat']}: {old} → {row['status']}", "seat")
        self.seats = seats
        if self.watcher is not None:
            self.issues = self.watcher.issues

    async def notify(self) -> None:
        async with self.changed:
            self.version += 1
            self.changed.notify_all()

    def close_streams(self) -> None:
        """End every open event stream, so the server can stop. Safe from a signal handler."""
        self.closing = True
        if self.loop is not None:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self.notify()))

    async def run(self) -> None:
        """The watch loop, then a refresh of the page's data, every interval."""
        if self.watcher is None:
            self.log("nothing to watch: the rig has no delegates_to edges and no tracker")
        while True:
            try:
                if self.watcher is not None:
                    await asyncio.to_thread(self.watcher.step)
                await asyncio.to_thread(self.refresh)
            except Exception as error:  # A dead loop would leave the page up but nothing pinged.
                self.log(f"ALERT: watch round failed, will retry: {error!r}", "error")
            await self.notify()
            await asyncio.sleep(self.interval)

    def api_seats(self) -> dict[str, Any]:
        return {"rig": self.rig.name, "seats": self.seats, "watch_last_check": last_check(self.rig)}

    def api_issues(self) -> dict[str, Any]:
        return {"rig": self.rig.name, "tracker": self.rig.tracker is not None} | sort_issues(
            self.issues
        )

    def api_events(self) -> dict[str, Any]:
        return {"rig": self.rig.name, "events": list(self.events)}

    def fragment(self, name: str) -> str:
        data = {"seats": self.api_seats, "issues": self.api_issues, "events": self.api_events}
        return self.templates.get_template(f"_{name}.html").render(**data[name]())

    def page(self) -> str:
        fragments = {name: self.fragment(name) for name in FRAGMENTS}
        return self.templates.get_template("page.html").render(rig=self.rig.name, **fragments)

    async def stream(self, disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
        """Server-sent events: every fragment when the data changes, and a keepalive otherwise."""
        seen = None
        while not self.closing and not await disconnected():
            if seen != self.version:
                seen = self.version
                for name in FRAGMENTS:
                    yield sse_message(name, self.fragment(name))
            idle = False
            async with self.changed:
                if seen == self.version:  # Checked under the lock, so no notify is missed.
                    try:
                        await asyncio.wait_for(self.changed.wait(), KEEPALIVE_SECONDS)
                    except TimeoutError:
                        idle = True
            if idle:  # Outside the lock, so a slow client can't hold up notify().
                yield ": keepalive\n\n"


def create_app(server: RigServer) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        server.loop = asyncio.get_running_loop()
        task = asyncio.create_task(server.run())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title=f"t3rig: {server.rig.name}", lifespan=lifespan)
    # Refuses DNS rebinding: another site's page resolving its name to 127.0.0.1. Ports are ignored.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return server.page()

    @app.get("/api/seats")
    def seats() -> dict[str, Any]:
        return server.api_seats()

    @app.get("/api/issues")
    def issues() -> dict[str, Any]:
        return server.api_issues()

    @app.get("/api/events")
    def events() -> dict[str, Any]:
        return server.api_events()

    @app.get("/api/stream")
    def stream(request: Request) -> StreamingResponse:
        headers = {"Cache-Control": "no-cache"}
        return StreamingResponse(
            server.stream(request.is_disconnected), media_type="text/event-stream", headers=headers
        )

    return app


class _Uvicorn(uvicorn.Server):
    """Ends the event streams on Ctrl-C; otherwise an open page keeps the server waiting."""

    def __init__(self, config: uvicorn.Config, on_exit: Callable[[], None]) -> None:
        super().__init__(config)
        self.on_exit = on_exit

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self.on_exit()
        super().handle_exit(sig, frame)


def serve(rig: Rig, t3: T3Cli, port: int, interval: float, tracker_interval: float) -> None:
    with single_watcher(state_path(rig)):  # Refuses if `t3rig watch` or another serve runs.
        # Built under the lock, so the watch state is read only once nobody else writes it.
        server = RigServer(
            rig, t3, interval, tracker_interval, out=lambda line: print(line, flush=True)
        )
        print(f"t3rig serve: http://{HOST}:{port}/ ({rig.name})", flush=True)
        config = uvicorn.Config(create_app(server), host=HOST, port=port, log_level="warning")
        _Uvicorn(config, server.close_streams).run()
