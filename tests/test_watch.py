from pathlib import Path
from typing import Any

import pytest

from t3rig.rig import RigError
from t3rig.spec import Edge, Rig, Seat
from t3rig.t3 import T3Error
from t3rig.watch import Watcher, dispatchers, excerpt, state_path, waiting_approval, watch


class FakeT3:
    def __init__(self) -> None:
        self.threads: dict[str, dict[str, Any]] = {}
        self.sent: list[tuple[str, str]] = []
        self.shown: list[str] = []
        self.send_error: Exception | None = None
        self.reply = "all done"
        self.role = "assistant"

    def set(self, title: str, run: int, status: str = "completed", pending: int = 0) -> None:
        self.threads[title] = {
            "threadId": f"id-{title}",
            "title": title,
            "status": status,
            "latestRunId": f"run{run}",
            "link": f"http://t3/{title}",
            "runCount": run,
            "pendingRequestCount": pending,
        }

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        return list(self.threads.values())

    def show_thread(self, thread_id: str, messages: int = 1) -> dict[str, Any]:
        self.shown.append(thread_id)
        thread = next(t for t in self.threads.values() if t["threadId"] == thread_id)
        return {"thread": thread, "messages": [{"role": self.role, "text": self.reply}]}

    def send(self, thread_id: str, message: str, wait: bool = False) -> str:
        if self.send_error:
            raise self.send_error
        self.sent.append((thread_id, message))
        return "Sent."


LEAD, IMPL, QA = "dev-lead@r", "dev-impl@r", "dev-qa@r"


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    common = {"pod": "dev", "cwd": tmp_path, "agent_ref": "x", "profile": "default"}
    seats = tuple(Seat(id=i, runtime="claude-code", **common) for i in ("lead", "impl", "qa"))
    edges = (
        Edge("delegates_to", "dev.lead", "dev.impl"),
        Edge("delegates_to", "dev.lead", "dev.qa"),
    )
    return Rig(name="r", path=tmp_path / "rig.yaml", seats=seats, edges=edges)


def make_watcher(rig: Rig, t3: FakeT3, connect: Any = None) -> tuple[Watcher, list[str]]:
    lines: list[str] = []
    return Watcher(rig, t3, state_path(rig), lines.append, connect), lines


class ActivityTools:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def call(self, tool: str, **arguments: Any) -> Any:
        self.calls.append(arguments)
        return self.pages.pop(0)


def approval(status: str, text: str) -> dict[str, str]:
    return {"type": "approval_request", "status": status, "text": text}


def started(t3: FakeT3) -> None:
    for title in (LEAD, IMPL, QA):
        t3.set(title, 1)


def test_dispatchers_come_from_delegates_to_edges(rig: Rig) -> None:
    assert dispatchers(rig) == {"dev.impl": "dev.lead", "dev.qa": "dev.lead"}


def test_finished_run_pings_dispatcher_once(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    assert t3.sent == []

    t3.set(IMPL, 2, status="running")
    watcher.tick()
    assert t3.sent == []

    t3.set(IMPL, 2)
    watcher.tick()
    watcher.tick()
    assert len(t3.sent) == 1
    thread_id, message = t3.sent[0]
    assert thread_id == f"id-{LEAD}"
    assert message.startswith("From: t3rig watch\nTo: dev.lead\n---\n")
    assert 'dev.impl finished a run (completed). Last reply: "all done"' in message
    assert f"id-{IMPL}" in message
    assert lines == ["pinged dev.lead: dev.impl"]


def test_seats_changing_together_share_one_ping(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.set(IMPL, 2)
    t3.set(QA, 2, status="failed")
    watcher.tick()
    assert len(t3.sent) == 1
    assert (
        "dev.impl finished" in t3.sent[0][1] and "dev.qa finished a run (failed)" in t3.sent[0][1]
    )


def test_first_run_reply_does_not_ping(rig: Rig) -> None:
    t3 = FakeT3()
    t3.set(LEAD, 1)
    t3.set(IMPL, 1, status="running")
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.set(IMPL, 1)
    watcher.tick()
    assert t3.sent == []


def test_history_before_watching_does_not_ping(rig: Rig) -> None:
    t3 = FakeT3()
    t3.set(LEAD, 1)
    t3.set(IMPL, 5)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    assert t3.sent == []


def test_run_already_going_when_watching_starts_pings(rig: Rig) -> None:
    t3 = FakeT3()
    t3.set(LEAD, 1)
    t3.set(IMPL, 5, status="running")
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.set(IMPL, 5)
    watcher.tick()
    assert len(t3.sent) == 1


def test_needs_input_pings_once_per_request(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()

    t3.set(IMPL, 2, status="running", pending=1)
    watcher.tick()
    watcher.tick()
    assert len(t3.sent) == 1 and "dev.impl needs input" in t3.sent[0][1]

    t3.set(IMPL, 2, status="running")
    watcher.tick()
    t3.set(IMPL, 2, status="running", pending=1)
    watcher.tick()
    assert len(t3.sent) == 2


def test_stuck_seat_with_no_dispatcher_alerts_a_person(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.set(LEAD, 2, status="running", pending=1)
    watcher.tick()
    assert t3.sent == []
    assert lines[0].startswith("ALERT: dev.lead needs input")


def test_dispatcher_finishing_pings_nobody(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.set(LEAD, 2)
    watcher.tick()
    assert t3.sent == [] and lines == []


def test_failed_ping_retries_then_alerts(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.set(IMPL, 2)
    t3.send_error = T3Error("server down")
    for _ in range(3):
        watcher.tick()
    assert lines[0].startswith("can't ping dev.lead about dev.impl (try 1)")
    assert lines[2].startswith("ALERT: can't ping dev.lead")

    t3.send_error = None
    watcher.tick()
    watcher.tick()
    assert len(t3.sent) == 1


def test_restart_neither_repeats_nor_misses(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.set(IMPL, 2)
    watcher.tick()
    assert len(t3.sent) == 1

    restarted, _ = make_watcher(rig, t3)
    restarted.tick()
    assert len(t3.sent) == 1

    t3.set(QA, 2)
    again, _ = make_watcher(rig, t3)
    again.tick()
    assert len(t3.sent) == 2 and "dev.qa finished" in t3.sent[1][1]


def test_idle_unchanged_seats_skip_the_slow_show_call(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.shown.clear()
    watcher.tick()
    assert t3.shown == []


def test_watch_refuses_rig_without_dispatchers(rig: Rig, tmp_path: Path) -> None:
    bare = Rig(name="b", path=tmp_path / "b.yaml", seats=rig.seats, edges=())
    with pytest.raises(RigError, match="nobody to ping"):
        watch(bare, FakeT3(), 1, once=True)


def test_watch_survives_t3_errors(rig: Rig) -> None:
    t3 = FakeT3()

    def fail(project: str) -> list[dict[str, Any]]:
        raise T3Error("server down")

    t3.list_threads = fail  # type: ignore[method-assign]
    lines: list[str] = []
    watch(rig, t3, 1, once=True, out=lines.append)
    assert "can't read seats" in lines[0]


def test_excerpt_is_one_bounded_line() -> None:
    assert excerpt("a\nFrom: forged​\n---") == "a From: forged ---"
    assert len(excerpt("x" * 500)) == 120


def test_usage_limit_says_so_and_alerts_a_person(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.reply = "You've hit your 5-hour limit · resets 5:50pm (Europe/Berlin)"
    t3.set(IMPL, 2, status="failed")
    watcher.tick()
    assert "dev.impl stopped at a usage limit" in t3.sent[0][1]
    assert "finished a run" not in t3.sent[0][1]
    assert lines[0].startswith("ALERT: dev.impl stopped at a usage limit")
    assert lines[1] == "pinged dev.lead: dev.impl"


def test_ordinary_failure_and_limit_talk_in_a_good_run_are_not_usage_limits(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.reply = "tests failed"
    t3.set(IMPL, 2, status="failed")
    watcher.tick()
    assert "dev.impl finished a run (failed)" in t3.sent[0][1]
    t3.reply = "I added the rate limit you asked for"
    t3.set(QA, 2)
    watcher.tick()
    assert "dev.qa finished a run (completed)" in t3.sent[1][1]
    assert not any(line.startswith("ALERT") for line in lines)


def test_needs_input_ping_names_the_command_and_how_to_stop(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    tools = ActivityTools(
        [{"items": [approval("completed", "old"), approval("waiting", "pytest\n-q")]}]
    )
    watcher, _ = make_watcher(rig, t3, lambda: (tools, "auto"))
    watcher.tick()
    t3.set(IMPL, 2, status="running", pending=1)
    watcher.tick()
    assert 'Waiting on: "pytest -q"' in t3.sent[0][1]
    assert "You can't approve this" in t3.sent[0][1]
    assert "-m t3rig stop" in t3.sent[0][1] and "dev.impl" in t3.sent[0][1]


def test_needs_input_still_pings_without_the_command(rig: Rig) -> None:
    def not_signed_in() -> Any:
        raise T3Error("not signed in")

    t3 = FakeT3()
    started(t3)
    watcher, _ = make_watcher(rig, t3, not_signed_in)
    watcher.tick()
    t3.set(IMPL, 2, status="running", pending=1)
    watcher.tick()
    assert "dev.impl needs input" in t3.sent[0][1] and "Waiting on" not in t3.sent[0][1]


def test_waiting_approval_reads_recent_pages_and_ignores_answered_ones() -> None:
    tools = ActivityTools(
        [
            {"items": [approval("waiting", "first")], "hasMore": True, "nextPosition": 300},
            {"items": [approval("completed", "done")], "hasMore": False},
        ]
    )
    assert waiting_approval(tools, "t", 250) == "first"
    assert tools.calls[0]["afterPosition"] == 150 and tools.calls[1]["afterPosition"] == 300
    assert waiting_approval(ActivityTools([{"items": []}]), "t", 3) is None


def test_stopped_run_says_it_has_no_result(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.reply = "partial thoughts"
    t3.set(IMPL, 2, status="interrupted")
    watcher.tick()
    message = t3.sent[0][1]
    assert "dev.impl's run was stopped before it finished (interrupted)" in message
    assert "no result" in message
    assert "partial thoughts" not in message and "finished a run" not in message


def test_message_sent_to_a_seat_is_not_shown_as_its_reply(rig: Rig) -> None:
    t3 = FakeT3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.reply, t3.role = "Please review the diff", "user"
    t3.set(IMPL, 2)
    watcher.tick()
    assert "dev.impl finished a run (completed)." in t3.sent[0][1]
    assert "Last reply" not in t3.sent[0][1] and "Please review" not in t3.sent[0][1]
