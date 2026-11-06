"""The `serve` page with made-up seats and issues, for screenshots and design work.

It runs on the in-memory T3 adapter and a made-up tracker, so it starts no T3 thread, reads no
issue tracker, and writes its watch state only in a temporary folder.

    uv run python -m t3rig.serve_demo --port 8766
"""

import argparse
import os
import tempfile
from pathlib import Path
from typing import Any

import uvicorn

from t3rig.serve import HOST, RigServer, _Uvicorn, create_app
from t3rig.spec import Edge, Rig, Seat, TrackerSettings
from t3rig.threads import MemoryT3
from t3rig.tracker import Issue

REPO = "https://github.com/example/demo/issues"
MODEL = "claude-opus-5-5"
ISSUES = [
    (9, "Traceable seat sessions and watch health", {"rig-queue", "in-progress"}),
    (12, "Bring a rig up and keep it running with one command", {"rig-queue"}),
    (14, "Notify the project manager when the rig needs attention", {"rig-queue"}),
    (7, "Per-seat skills: which design should we build?", {"needs-answer"}),
    (13, "Make showing the skill plan safe", {"needs-approval"}),
    (16, "Share outside-repo excerpts through one file", {"needs-approval"}),
]
LONG_REPLY = (
    "I've made the round-1 fixes. The list and show data are now kept apart, as real T3 does:\n"
    "- list_threads leaves out the fields only `t3 thread show` gives\n"
    "- sending to an archived thread raises T3Error\n"
    "- two new tests cover both\n"
    "Checks: pytest 270 passed, ruff clean, sphinx -W exit 0."
)


class DemoTracker:
    """A tracker with fixed issues and no comments."""

    def open_issues(self) -> list[Issue]:
        return [Issue(n, f"{REPO}/{n}", frozenset(labels), title) for n, title, labels in ISSUES]

    def comments(self, number: int) -> list[str]:
        return []


def _seat(t3: MemoryT3, member: str, **fields: Any) -> str:
    title = f"dev-{member}@demo"
    t3.put(
        title,
        model=MODEL,
        runtimeMode="auto",
        providerInstanceId="claudeAgent",
        link=f"https://app.t3.codes/threads/demo/{member}",
        latestRunId="run1",
        runCount=1,
        **fields,
    )
    return f"id-{title}"


def demo_server(root: Path) -> RigServer:
    """A server for a four-seat rig whose seats are working, idle, waiting and failed."""
    os.environ["XDG_STATE_HOME"] = str(root / "state")  # Watch state stays in `root`.
    common = {"pod": "dev", "cwd": root, "agent_ref": "local:agents", "profile": "default"}
    seats = tuple(
        Seat(id=member, runtime="claude-code", model=MODEL, **common)
        for member in ("lead", "impl", "review", "pm")
    )
    rig = Rig(
        name="demo",
        path=root / "rig.yaml",
        seats=seats,
        edges=(
            Edge("delegates_to", "dev.lead", "dev.impl"),
            Edge("delegates_to", "dev.lead", "dev.review"),
        ),
        tracker=TrackerSettings("github", "example/demo", "dev.lead"),
    )
    t3 = MemoryT3(access_level=None)
    t3.say(_seat(t3, "pm", status="failed"), "The tracker didn't answer; I'll try again.")
    t3.say(
        _seat(t3, "review", status="running", pendingRequestCount=1),
        "Running the docs build to confirm a finding.",
    )
    t3.say(_seat(t3, "impl", status="running"), LONG_REPLY)
    t3.say(_seat(t3, "lead", status="completed"), "Handed the fixes to dev.impl; waiting for it.")
    tracker = DemoTracker()
    server = RigServer(
        rig, t3, interval=5, tracker_interval=5, make_tracker=lambda _: tracker, out=print
    )
    for line in (
        "dev.review: completed → running",
        "pinged dev.lead: dev.impl",
        "dev.impl: completed → running",
    ):
        server.log(line, "seat" if "→" in line else "watch")
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8766, help="port on 127.0.0.1 (default: 8766)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="t3rig-demo-") as root:
        server = demo_server(Path(root))
        print(f"t3rig serve demo: http://{HOST}:{args.port}/", flush=True)
        config = uvicorn.Config(create_app(server), host=HOST, port=args.port, log_level="warning")
        _Uvicorn(config, server.close_streams).run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:  # Ctrl-C is how the demo stops.
        pass
