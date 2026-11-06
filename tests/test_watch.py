from pathlib import Path
from typing import Any

import pytest

from t3rig.rig import RigError
from t3rig.spec import Edge, Rig, Seat, TrackerSettings
from t3rig.t3 import T3Error
from t3rig.tracker import Issue, TrackerError
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


class FakeTracker:
    def __init__(self) -> None:
        self.labels: dict[int, set[str]] = {}
        self.notes: dict[int, list[str]] = {}
        self.error: Exception | None = None
        self.read: list[int] = []

    def open_issues(self) -> list[Issue]:
        if self.error:
            raise self.error
        return [Issue(n, f"https://t/issues/{n}", frozenset(ls)) for n, ls in self.labels.items()]

    def comments(self, number: int) -> list[str]:
        self.read.append(number)
        return self.notes.get(number, [])


def tracked(rig: Rig) -> Rig:
    return Rig(
        name=rig.name,
        path=rig.path,
        seats=rig.seats,
        edges=rig.edges,
        tracker=TrackerSettings("github", "o/r", "dev.lead"),
    )


def issue_watcher(rig: Rig) -> tuple[Watcher, FakeT3, FakeTracker, list[str]]:
    t3, tracker, lines = FakeT3(), FakeTracker(), []
    started(t3)
    rig = tracked(rig)
    return Watcher(rig, t3, state_path(rig), lines.append, None, tracker), t3, tracker, lines


def test_queued_issue_pings_the_queue_seat_once(rig: Rig) -> None:
    watcher, t3, tracker, lines = issue_watcher(rig)
    tracker.labels[5] = {"enhancement"}
    watcher.poll_tracker()
    assert t3.sent == []

    tracker.labels[5].add("rig-queue")
    watcher.poll_tracker()
    watcher.poll_tracker()
    assert len(t3.sent) == 1
    thread_id, message = t3.sent[0]
    assert thread_id == f"id-{LEAD}"
    assert "queued with `rig-queue`: https://t/issues/5" in message
    assert lines == ["pinged dev.lead: #5"]


def test_issue_already_queued_on_first_sight_pings_once(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = {"rig-queue"}
    watcher.poll_tracker()
    watcher.poll_tracker()
    assert len(t3.sent) == 1


def test_issue_already_in_progress_on_first_sight_does_not_ping(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = {"rig-queue", "in-progress"}
    watcher.poll_tracker()
    assert t3.sent == []
    tracker.labels[5] = {"in-progress"}  # Requeued later: a fresh approval, so it pings.
    watcher.poll_tracker()
    tracker.labels[5] = {"rig-queue", "in-progress"}
    watcher.poll_tracker()
    assert len(t3.sent) == 1


def test_requeued_issue_pings_again(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = {"rig-queue"}
    watcher.poll_tracker()
    tracker.labels[5] = set()
    watcher.poll_tracker()
    tracker.labels[5] = {"rig-queue"}
    watcher.poll_tracker()
    assert len(t3.sent) == 2


def test_answer_pings_the_seat_that_signed_the_question(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = set()
    tracker.notes[5] = [
        "🤖 dev.lead (t3rig)\nplan",
        "🤖 dev.impl (t3rig)\nQuestions",
        "operator: hm",
    ]
    watcher.poll_tracker()
    tracker.labels[5] = {"needs-answer"}
    watcher.poll_tracker()
    assert t3.sent == []
    # The answer is written by dev.pm, so it is signed too; the question's signer still gets it.
    tracker.notes[5].append("🤖 dev.pm (t3rig)\nAnswers")
    tracker.labels[5] = set()
    watcher.poll_tracker()
    watcher.poll_tracker()
    assert len(t3.sent) == 1
    thread_id, message = t3.sent[0]
    assert thread_id == f"id-{IMPL}"
    assert "`needs-answer` was removed: https://t/issues/5" in message


def test_answer_without_a_signed_question_pings_the_queue_seat(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = {"needs-answer"}
    tracker.notes[5] = ["no signature", "🤖 dev.nobody (t3rig)\nunknown seat"]
    watcher.poll_tracker()
    tracker.labels[5] = set()
    watcher.poll_tracker()
    assert [thread for thread, _ in t3.sent] == [f"id-{LEAD}"]


def test_no_answer_ping_without_prior_state_or_for_closed_issues(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = set()
    tracker.labels[6] = {"needs-answer"}
    watcher.poll_tracker()  # 5 was never seen with needs-answer.
    del tracker.labels[6]  # Closed while waiting.
    watcher.poll_tracker()
    tracker.labels[6] = set()  # Reopened without the label.
    watcher.poll_tracker()
    assert t3.sent == []


def test_failed_issue_ping_retries_then_alerts(rig: Rig) -> None:
    watcher, t3, tracker, lines = issue_watcher(rig)
    t3.send_error = T3Error("send failed")
    tracker.labels[5] = {"rig-queue"}
    for _ in range(3):
        watcher.poll_tracker()
    assert lines[-1].startswith("ALERT: can't ping dev.lead about #5 (try 3)")
    t3.send_error = None
    watcher.poll_tracker()
    assert len(t3.sent) == 1


def test_issue_state_survives_a_restart(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = {"rig-queue", "needs-answer"}
    tracker.notes[5] = ["🤖 dev.impl (t3rig)\nQuestions"]
    watcher.poll_tracker()
    again = Watcher(watcher.rig, t3, watcher.path, print, None, tracker)
    again.poll_tracker()
    assert len(t3.sent) == 1
    tracker.labels[5] = {"rig-queue"}
    again.poll_tracker()
    assert t3.sent[-1][0] == f"id-{IMPL}"


def test_watch_polls_the_tracker_on_its_own_interval(rig: Rig) -> None:
    t3, tracker = FakeT3(), FakeTracker()
    started(t3)
    polls: list[int] = []
    tracker.open_issues = lambda: polls.append(1) or []  # type: ignore[method-assign]
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds
        if now[0] > 100:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        watch(
            tracked(rig),
            t3,
            15,
            sleep=sleep,
            tracker_interval=60,
            make_tracker=lambda settings: tracker,
            clock=lambda: now[0],
        )
    assert len(polls) == 2  # At 0s and 60s, not every 15s.


def test_watch_survives_tracker_errors(rig: Rig) -> None:
    t3, tracker = FakeT3(), FakeTracker()
    tracker.error = TrackerError("gh exited 1")
    lines: list[str] = []
    watch(tracked(rig), t3, 1, once=True, out=lines.append, make_tracker=lambda s: tracker)
    assert lines == ["can't read the tracker, will retry: gh exited 1"]


def test_tracker_alone_is_enough_to_watch(rig: Rig, tmp_path: Path) -> None:
    settings = tracked(rig).tracker
    bare = Rig(name="b", path=tmp_path / "b.yaml", seats=rig.seats, edges=(), tracker=settings)
    watch(bare, FakeT3(), 1, once=True, make_tracker=lambda s: FakeTracker())
