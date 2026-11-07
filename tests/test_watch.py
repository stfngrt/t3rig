import dataclasses
import fcntl
import json
import os
from pathlib import Path
from typing import Any

import pytest

from t3rig.cli import _ps
from t3rig.rig import RigError
from t3rig.seat_watch import dispatchers, excerpt, waiting_approval
from t3rig.spec import Edge, Rig, Seat, TrackerSettings
from t3rig.t3 import T3Error
from t3rig.threads import MemoryT3
from t3rig.tracker import Issue, TrackerError
from t3rig.watch import Watcher, single_watcher, state_path, watch, watch_running

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


def make_watcher(rig: Rig, t3: MemoryT3) -> tuple[Watcher, list[str]]:
    lines: list[str] = []
    return Watcher(rig, t3, state_path(rig), lines.append), lines


def fake_t3() -> MemoryT3:
    return MemoryT3(access_level=None)  # Not signed in to /mcp unless a test says so.


def put(t3: MemoryT3, title: str, run: int, status: str = "completed", pending: int = 0) -> None:
    """A seat's thread after `run` runs, with a reply if it has none yet."""
    t3.put(
        title,
        status=status,
        latestRunId=f"run{run}",
        link=f"http://t3/{title}",
        runCount=run,
        pendingRequestCount=pending,
    )
    if f"id-{title}" not in t3.messages:
        t3.say(f"id-{title}", "all done")


def approval(status: str, text: str) -> dict[str, str]:
    return {"type": "approval_request", "status": status, "text": text}


def started(t3: MemoryT3) -> None:
    for title in (LEAD, IMPL, QA):
        put(t3, title, 1)


def test_dispatchers_come_from_delegates_to_edges(rig: Rig) -> None:
    assert dispatchers(rig) == {"dev.impl": "dev.lead", "dev.qa": "dev.lead"}


def test_finished_run_pings_dispatcher_once(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    assert t3.sent == []

    put(t3, IMPL, 2, status="running")
    watcher.tick()
    assert t3.sent == []

    put(t3, IMPL, 2)
    watcher.tick()
    watcher.tick()
    assert len(t3.sent) == 1
    thread_id, message, _ = t3.sent[0]
    assert thread_id == f"id-{LEAD}"
    assert message.startswith("From: t3rig watch\nTo: dev.lead\n---\n")
    assert 'dev.impl finished a run (completed). Last reply: "all done"' in message
    assert f"id-{IMPL}" in message
    assert lines == ["pinged dev.lead: dev.impl"]


def test_seats_changing_together_share_one_ping(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 2)
    put(t3, QA, 2, status="failed")
    watcher.tick()
    assert len(t3.sent) == 1
    assert (
        "dev.impl finished" in t3.sent[0][1] and "dev.qa finished a run (failed)" in t3.sent[0][1]
    )


def test_first_run_reply_does_not_ping(rig: Rig) -> None:
    t3 = fake_t3()
    put(t3, LEAD, 1)
    put(t3, IMPL, 1, status="running")
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 1)
    watcher.tick()
    assert t3.sent == []


def test_history_before_watching_does_not_ping(rig: Rig) -> None:
    t3 = fake_t3()
    put(t3, LEAD, 1)
    put(t3, IMPL, 5)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    assert t3.sent == []


def test_run_already_going_when_watching_starts_pings(rig: Rig) -> None:
    t3 = fake_t3()
    put(t3, LEAD, 1)
    put(t3, IMPL, 5, status="running")
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 5)
    watcher.tick()
    assert len(t3.sent) == 1


def test_needs_input_pings_once_per_request(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()

    put(t3, IMPL, 2, status="running", pending=1)
    watcher.tick()
    watcher.tick()
    assert len(t3.sent) == 1 and "dev.impl needs input" in t3.sent[0][1]

    put(t3, IMPL, 2, status="running")
    watcher.tick()
    put(t3, IMPL, 2, status="running", pending=1)
    watcher.tick()
    assert len(t3.sent) == 2


def test_stuck_seat_with_no_dispatcher_alerts_a_person(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    put(t3, LEAD, 2, status="running", pending=1)
    watcher.tick()
    assert t3.sent == []
    assert lines[0].startswith("ALERT: dev.lead needs input")


def test_dispatcher_finishing_pings_nobody(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    put(t3, LEAD, 2)
    watcher.tick()
    assert t3.sent == [] and lines == []


def test_failed_ping_retries_then_alerts(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 2)
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
    t3 = fake_t3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 2)
    watcher.tick()
    assert len(t3.sent) == 1

    restarted, _ = make_watcher(rig, t3)
    restarted.tick()
    assert len(t3.sent) == 1

    put(t3, QA, 2)
    again, _ = make_watcher(rig, t3)
    again.tick()
    assert len(t3.sent) == 2 and "dev.qa finished" in t3.sent[1][1]


def test_idle_unchanged_seats_skip_the_slow_show_call(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.read.clear()
    watcher.tick()
    assert t3.read == []


def test_watch_refuses_rig_without_dispatchers(rig: Rig, tmp_path: Path) -> None:
    bare = Rig(name="b", path=tmp_path / "b.yaml", seats=rig.seats, edges=())
    with pytest.raises(RigError, match="nobody to ping"):
        watch(bare, fake_t3(), 1, once=True)


def test_watch_survives_t3_errors(rig: Rig) -> None:
    t3 = fake_t3()

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
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.say(f"id-{IMPL}", "You've hit your 5-hour limit · resets 5:50pm (Europe/Berlin)")
    put(t3, IMPL, 2, status="failed")
    watcher.tick()
    assert "dev.impl stopped at a usage limit" in t3.sent[0][1]
    assert "finished a run" not in t3.sent[0][1]
    assert lines[0].startswith("ALERT: dev.impl stopped at a usage limit")
    assert lines[1] == "pinged dev.lead: dev.impl"


def test_ordinary_failure_and_limit_talk_in_a_good_run_are_not_usage_limits(rig: Rig) -> None:
    # A failed run is still an ALERT (see below), but not a usage limit.
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    t3.say(f"id-{IMPL}", "tests failed")
    put(t3, IMPL, 2, status="failed")
    watcher.tick()
    assert "dev.impl finished a run (failed)" in t3.sent[0][1]
    t3.say(f"id-{QA}", "I added the rate limit you asked for")
    put(t3, QA, 2)
    watcher.tick()
    assert "dev.qa finished a run (completed)" in t3.sent[1][1]
    assert not any("usage limit" in line for line in lines)
    assert [line for line in lines if line.startswith("ALERT")] == [
        f'ALERT: dev.impl finished a run (failed). Last reply: "tests failed" Thread id-{IMPL}: '
        f"http://t3/{IMPL}"
    ]


def test_needs_input_ping_names_the_command_and_how_to_stop(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    t3.access_level = "auto"
    t3.activity_pages = [
        {"items": [approval("completed", "old"), approval("waiting", "pytest\n-q")]}
    ]
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 2, status="running", pending=1)
    watcher.tick()
    assert 'Waiting on: "pytest -q"' in t3.sent[0][1]
    assert "You can't approve this" in t3.sent[0][1]
    assert "-m t3rig stop" in t3.sent[0][1] and "dev.impl" in t3.sent[0][1]


def test_needs_input_still_pings_without_the_command(rig: Rig) -> None:
    t3 = fake_t3()  # Not signed in, so what it waits on can't be read.
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 2, status="running", pending=1)
    watcher.tick()
    assert "dev.impl needs input" in t3.sent[0][1] and "Waiting on" not in t3.sent[0][1]


def test_waiting_approval_reads_recent_pages_and_ignores_answered_ones() -> None:
    t3 = MemoryT3()
    t3.activity_pages = [
        {"items": [approval("waiting", "first")], "hasMore": True, "nextPosition": 300},
        {"items": [approval("completed", "done")], "hasMore": False},
    ]
    assert waiting_approval(t3, "t", 250) == "first"
    assert [a["afterPosition"] for _, a in t3.actions] == [150, 300]
    assert waiting_approval(MemoryT3(), "t", 3) is None


def test_stopped_run_says_it_has_no_result(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.say(f"id-{IMPL}", "partial thoughts")
    put(t3, IMPL, 2, status="interrupted")
    watcher.tick()
    message = t3.sent[0][1]
    assert "dev.impl's run was stopped before it finished (interrupted)" in message
    assert "no result" in message
    assert "partial thoughts" not in message and "finished a run" not in message


def test_message_sent_to_a_seat_is_not_shown_as_its_reply(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    t3.say(f"id-{IMPL}", "Please review the diff", "user")
    put(t3, IMPL, 2)
    watcher.tick()
    assert "dev.impl finished a run (completed)." in t3.sent[0][1]
    assert "Last reply" not in t3.sent[0][1] and "Please review" not in t3.sent[0][1]


class FakeTracker:
    limit = 1000

    def __init__(self) -> None:
        self.labels: dict[int, set[str]] = {}
        self.notes: dict[int, list[str]] = {}
        self.error: Exception | None = None
        self.read: list[int] = []

    def open_issues(self) -> list[Issue]:
        if self.error:
            raise self.error
        return [
            Issue(n, f"https://t/issues/{n}", frozenset(ls), f"Issue {n}")
            for n, ls in self.labels.items()
        ]

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


def issue_watcher(rig: Rig) -> tuple[Watcher, MemoryT3, FakeTracker, list[str]]:
    t3, tracker, lines = fake_t3(), FakeTracker(), []
    started(t3)
    rig = tracked(rig)
    return Watcher(rig, t3, state_path(rig), lines.append, tracker), t3, tracker, lines


def test_queued_issue_pings_the_queue_seat_once(rig: Rig) -> None:
    watcher, t3, tracker, lines = issue_watcher(rig)
    tracker.labels[5] = {"enhancement"}
    watcher.poll_tracker()
    assert t3.sent == []

    tracker.labels[5].add("rig-queue")
    watcher.poll_tracker()
    watcher.poll_tracker()
    assert len(t3.sent) == 1
    thread_id, message, _ = t3.sent[0]
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
    thread_id, message, _ = t3.sent[0]
    assert thread_id == f"id-{IMPL}"
    assert "`needs-answer` was removed: https://t/issues/5" in message


def test_answer_without_a_signed_question_pings_the_queue_seat(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = {"needs-answer"}
    tracker.notes[5] = ["no signature", "🤖 dev.nobody (t3rig)\nunknown seat"]
    watcher.poll_tracker()
    tracker.labels[5] = set()
    watcher.poll_tracker()
    assert [sent[0] for sent in t3.sent] == [f"id-{LEAD}"]


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
    again = Watcher(watcher.rig, t3, watcher.path, print, tracker)
    again.poll_tracker()
    assert len(t3.sent) == 1
    tracker.labels[5] = {"rig-queue"}
    again.poll_tracker()
    assert t3.sent[-1][0] == f"id-{IMPL}"


def test_watch_polls_the_tracker_on_its_own_interval(rig: Rig) -> None:
    t3, tracker = fake_t3(), FakeTracker()
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
    t3, tracker = fake_t3(), FakeTracker()
    tracker.error = TrackerError("gh exited 1")
    lines: list[str] = []
    watch(tracked(rig), t3, 1, once=True, out=lines.append, make_tracker=lambda s: tracker)
    assert lines == ["can't read the tracker, will retry: gh exited 1"]


def test_tracker_alone_is_enough_to_watch(rig: Rig, tmp_path: Path) -> None:
    settings = tracked(rig).tracker
    bare = Rig(name="b", path=tmp_path / "b.yaml", seats=rig.seats, edges=(), tracker=settings)
    watch(bare, fake_t3(), 1, once=True, make_tracker=lambda s: FakeTracker())


def test_watch_running_follows_the_lock_and_creates_nothing(rig: Rig) -> None:
    path = state_path(rig)
    assert not watch_running(rig)
    assert not path.parent.exists()
    with single_watcher(path):
        assert watch_running(rig)
    assert not watch_running(rig)


def test_ps_says_whether_watch_is_running(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    t3 = fake_t3()
    started(t3)
    _ps(rig, t3, as_json=False)
    assert capsys.readouterr().out.splitlines()[-1] == "watch: not running, has never run"
    with single_watcher(state_path(rig)):
        _ps(rig, t3, as_json=True)
        status = json.loads(capsys.readouterr().out)
        assert status["watch_running"] is True and status["watch_last_check"] is None
        assert status["watch_holder"] == f"t3rig watch (pid {os.getpid()})"
        _ps(rig, t3, as_json=False)
        last = capsys.readouterr().out.splitlines()[-1]
        assert last == f"watch: running in t3rig watch (pid {os.getpid()}), has never run"


def test_ps_says_running_when_an_older_t3rig_holds_the_lock_unnamed(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    t3 = fake_t3()
    started(t3)
    lock = state_path(rig).with_suffix(".lock")
    lock.parent.mkdir(parents=True)
    with open(lock, "w") as handle:  # As an older t3rig held it: locked, with nothing written.
        fcntl.flock(handle, fcntl.LOCK_EX)
        _ps(rig, t3, as_json=True)
        status = json.loads(capsys.readouterr().out)
        assert status["watch_running"] is True and status["watch_holder"] is None
        _ps(rig, t3, as_json=False)
        assert capsys.readouterr().out.splitlines()[-1] == "watch: running, has never run"
        with pytest.raises(RigError, match="another t3rig watch or serve is already running"):
            with single_watcher(state_path(rig)):
                pass


def test_signature_with_a_thread_link_still_names_the_seat(rig: Rig) -> None:
    watcher, t3, tracker, _ = issue_watcher(rig)
    tracker.labels[5] = {"needs-answer"}
    tracker.notes[5] = ["🤖 dev.impl (t3rig) · https://app.t3.codes/threads/p/mcp%3Aabc\nQuestions"]
    watcher.poll_tracker()
    tracker.labels[5] = set()
    watcher.poll_tracker()
    assert t3.sent[0][0] == f"id-{IMPL}"


def noticed(rig: Rig, notify_seat: str | None = "dev.qa") -> tuple[Watcher, MemoryT3, FakeTracker]:
    """A watcher whose notify seat is dev.qa, after a first poll of a quiet tracker."""
    t3, tracker = fake_t3(), FakeTracker()
    started(t3)
    rig = Rig(
        name=rig.name,
        path=rig.path,
        seats=rig.seats,
        edges=rig.edges,
        tracker=TrackerSettings("github", "o/r", "dev.lead"),
        notify_seat=notify_seat,
    )
    watcher = Watcher(rig, t3, state_path(rig), lambda line: None, tracker)
    watcher.poll_tracker()
    return watcher, t3, tracker


def notices(t3: MemoryT3) -> list[str]:
    return [
        line
        for to, message, _ in t3.sent
        if to == f"id-{QA}"
        for line in message.splitlines()
        if line.startswith("- ")
    ]


def test_a_question_from_another_seat_is_noticed_once(rig: Rig) -> None:
    watcher, t3, tracker = noticed(rig)
    tracker.labels[5] = {"needs-answer"}
    tracker.notes[5] = ["🤖 dev.lead (t3rig) · https://t3/lead\nOpen decisions"]
    watcher.poll_tracker()
    watcher.poll_tracker()
    assert notices(t3) == ["- #5 needs you: questions from dev.lead https://t/issues/5"]
    assert "Follow up on each as your role says" in t3.sent[-1][1]


def test_the_notify_seats_own_question_is_not_noticed(rig: Rig) -> None:
    watcher, t3, tracker = noticed(rig)
    tracker.labels[5] = {"needs-answer"}
    tracker.notes[5] = ["🤖 dev.qa (t3rig)\nQuestions"]
    watcher.poll_tracker()
    assert notices(t3) == []


def test_an_unsigned_question_is_noticed(rig: Rig) -> None:
    watcher, t3, tracker = noticed(rig)
    tracker.labels[5] = {"needs-answer"}
    watcher.poll_tracker()
    assert notices(t3) == ["- #5 needs you: questions https://t/issues/5"]


def test_questions_already_there_on_the_first_poll_are_not_noticed(rig: Rig) -> None:
    t3, tracker = fake_t3(), FakeTracker()
    started(t3)
    tracker.labels[5] = {"needs-answer"}
    rig = Rig(
        name="r",
        path=rig.path,
        seats=rig.seats,
        edges=rig.edges,
        tracker=TrackerSettings("github", "o/r", "dev.lead"),
        notify_seat="dev.qa",
    )
    Watcher(rig, t3, state_path(rig), lambda line: None, tracker).poll_tracker()
    assert notices(t3) == []


def test_a_tracked_issue_closing_is_noticed_and_an_untracked_one_is_not(rig: Rig) -> None:
    watcher, t3, tracker = noticed(rig)
    tracker.labels[5] = {"rig-queue", "in-progress"}
    watcher.poll_tracker()
    del tracker.labels[5]
    watcher.poll_tracker()
    watcher.poll_tracker()
    assert notices(t3) == ["- #5 closed: Issue 5 https://t/issues/5"]


def test_an_alert_is_noticed_once_however_often_it_repeats(rig: Rig) -> None:
    watcher, t3, _ = noticed(rig)
    watcher.tick()
    t3.threads = [t for t in t3.threads if t["title"] != LEAD]  # dev.impl's dispatcher is gone.
    put(t3, IMPL, 2)
    for _ in range(5):
        watcher.tick()
    (alert,) = notices(t3)
    assert alert.startswith("- ALERT: can't ping dev.lead about dev.impl (try 3)")


def test_notices_survive_a_restart_without_repeating(rig: Rig) -> None:
    watcher, t3, tracker = noticed(rig)
    tracker.labels[5] = {"needs-answer"}
    qa = next(t for t in t3.threads if t["title"] == QA)
    t3.threads.remove(qa)  # The notify seat is down, so the notice waits.
    watcher.poll_tracker()
    assert notices(t3) == []
    t3.threads.insert(0, qa)
    again = Watcher(watcher.rig, t3, watcher.path, lambda line: None, tracker)
    again.poll_tracker()
    again.poll_tracker()
    third = Watcher(watcher.rig, t3, watcher.path, lambda line: None, tracker)
    third.poll_tracker()
    assert notices(t3) == ["- #5 needs you: questions https://t/issues/5"]


def test_a_failing_notice_is_retried_but_never_noticed_itself(rig: Rig) -> None:
    lines: list[str] = []
    watcher, t3, tracker = noticed(rig)
    watcher.delivery.out = lines.append
    tracker.labels[5] = {"needs-answer"}
    qa = next(t for t in t3.threads if t["title"] == QA)
    t3.threads.remove(qa)
    for _ in range(5):
        watcher.poll_tracker()
    assert any(line.startswith("ALERT: can't ping dev.qa about notice (try 3)") for line in lines)
    assert watcher.state["notices"]["pending"] == [
        {"key": None, "text": "#5 needs you: questions https://t/issues/5"}
    ]
    t3.threads.insert(0, qa)
    watcher.poll_tracker()
    assert notices(t3) == ["- #5 needs you: questions https://t/issues/5"]


def test_no_notify_seat_means_no_notices(rig: Rig) -> None:
    watcher, t3, tracker = noticed(rig, notify_seat=None)
    tracker.labels[5] = {"needs-answer"}
    watcher.poll_tracker()
    del tracker.labels[5]
    watcher.poll_tracker()
    assert notices(t3) == [] and "notices" not in watcher.state


def test_a_failed_run_and_a_pending_request_are_alerts_noticed_once(rig: Rig) -> None:
    watcher, t3, _ = noticed(rig)
    lines: list[str] = []
    watcher.delivery.out = lines.append
    watcher.tick()
    put(t3, IMPL, 2, status="failed")
    put(t3, LEAD, 2, status="running", pending=1)  # Has no dispatcher in this rig, as before.
    watcher.tick()
    watcher.tick()
    assert sum(line.startswith("ALERT: dev.impl finished a run (failed)") for line in lines) == 1
    # The dispatcher still gets its ping about the failed run.
    assert any(
        to == f"id-{LEAD}" and "dev.impl finished a run (failed)" in m for to, m, _ in t3.sent
    )
    alerts = notices(t3)
    assert len(alerts) == 2 and all(line.startswith("- ALERT: ") for line in alerts)
    assert any("dev.impl finished a run (failed)" in a for a in alerts)
    assert any("dev.lead needs input" in a for a in alerts)


def test_a_pending_request_with_a_dispatcher_is_an_alert_too(rig: Rig) -> None:
    t3 = fake_t3()
    started(t3)
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    put(t3, IMPL, 2, status="running", pending=1)
    watcher.tick()
    assert "dev.impl needs input" in t3.sent[0][1]  # The dispatcher's ping, as before.
    assert lines[0].startswith("ALERT: dev.impl needs input")


def test_alerts_about_the_notify_seat_are_never_noticed(rig: Rig) -> None:
    watcher, t3, _ = noticed(rig)
    lines: list[str] = []
    watcher.delivery.out = lines.append
    watcher.tick()
    # In real T3 each notice starts a run, which stops at the usage limit again: a new run id.
    for run in range(2, 6):
        t3.say(f"id-{QA}", "You've hit your 5-hour limit · resets 5:50pm")
        put(t3, QA, run, status="failed")
        watcher.tick()
    assert sum(line.startswith("ALERT: dev.qa stopped at a usage limit") for line in lines) == 4
    assert notices(t3) == []


def test_a_capped_tracker_list_closes_nothing(rig: Rig) -> None:
    watcher, t3, tracker = noticed(rig)
    lines: list[str] = []
    watcher.delivery.out = lines.append
    tracker.labels.update({5: {"rig-queue", "in-progress"}, 6: set()})
    watcher.poll_tracker()
    tracker.limit = 1  # Now the list is cut off at one issue, and #5 falls off it.
    del tracker.labels[5]
    watcher.poll_tracker()
    assert notices(t3) == []
    assert "5" in watcher.state["issues"]
    assert lines[-1].startswith("the tracker's list stopped at its limit of 1 open issues")


def test_a_task_thread_finishing_pings_the_dispatcher_naming_the_task(rig: Rig) -> None:
    rig = dataclasses.replace(rig, per_task={"dev.impl": "issue"})
    t3 = fake_t3()
    put(t3, LEAD, 1)
    put(t3, f"{IMPL} #18", 1)
    put(t3, IMPL, 1)  # An old long-lived thread: no longer the seat's.
    watcher, lines = make_watcher(rig, t3)
    watcher.tick()
    put(t3, f"{IMPL} #18", 2)
    put(t3, IMPL, 2)
    watcher.tick()
    assert len(t3.sent) == 1
    assert "- dev.impl #18 finished a run (completed)." in t3.sent[0][1]
    assert lines == ["pinged dev.lead: dev.impl #18"]
    assert f"{IMPL} #18" in watcher.state["seats"]  # Keyed by the task thread's title.


def test_a_task_thread_first_seen_finished_is_pinged_unless_it_only_read_its_brief(
    rig: Rig,
) -> None:
    rig = dataclasses.replace(rig, per_task={"dev.impl": "issue"})
    t3 = fake_t3()
    put(t3, LEAD, 1)
    watcher, _ = make_watcher(rig, t3)
    watcher.tick()
    put(t3, f"{IMPL} #18", 1)  # Started and replied to its brief between two checks.
    put(t3, f"{IMPL} #19", 2)  # Started, given its task and finished between two checks.
    t3.say(f"id-{IMPL} #19", "built #19", "assistant")
    watcher.tick()
    watcher.tick()
    assert len(t3.sent) == 1
    assert "dev.impl #19 finished a run (completed)." in t3.sent[0][1]
    assert "#18" not in t3.sent[0][1]


def test_an_archived_task_thread_s_state_is_forgotten(rig: Rig) -> None:
    rig = dataclasses.replace(rig, per_task={"dev.impl": "issue"})
    t3 = fake_t3()
    started(t3)
    put(t3, f"{IMPL} #18", 1)
    watcher, _ = make_watcher(rig, t3)
    watcher.state["seats"][IMPL] = {"run": "old", "asked": None}  # From before it was per-task.
    watcher.tick()
    assert f"{IMPL} #18" in watcher.state["seats"]
    t3.access_level = "auto"
    t3.archive(f"id-{IMPL} #18")
    watcher.tick()
    assert f"{IMPL} #18" not in watcher.state["seats"]
    # Long-lived entries stay, including a per-task seat's old one, as for closed issues.
    assert {IMPL, LEAD, QA} <= set(watcher.state["seats"])
