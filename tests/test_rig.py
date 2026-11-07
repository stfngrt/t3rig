import dataclasses
from pathlib import Path
from typing import Any

import pytest

from t3rig.rig import (
    RigError,
    down,
    log,
    seat_brief,
    seat_rows,
    select_seats,
    send,
    start_task,
    stop,
    up,
)
from t3rig.spec import Edge, Rig, Seat, StartupText
from t3rig.t3 import T3Error
from t3rig.threads import MemoryT3


def memory(tmp_path: Path, **settings: Any) -> MemoryT3:
    return MemoryT3(project_root=str(tmp_path), **settings)


def make_rig(
    tmp_path: Path, runtime: str = "claude-code", model: str | None = None, **seat: Any
) -> Rig:
    common = {
        "pod": "dev",
        "cwd": tmp_path,
        "agent_ref": "local:a",
        "profile": "default",
        "startup": (StartupText("culture.md", "Be honest."),),
    }
    return Rig(
        name="r",
        path=tmp_path / "rig.yaml",
        seats=(
            Seat(id="lead", runtime=runtime, model=model, **common, **seat),
            Seat(id="impl", runtime=runtime, model=model, **common, **seat),
        ),
        edges=(Edge("delegates_to", "dev.lead", "dev.impl"),),
    )


def test_up_starts_each_seat_once(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    assert up(rig, t3) == [
        "dev.lead: started id-dev-lead@r (unknown mode)",
        "dev.impl: started id-dev-impl@r (unknown mode)",
    ]
    assert up(rig, t3) == [
        "dev.lead: already has thread id-dev-lead@r",
        "dev.impl: already has thread id-dev-impl@r",
    ]
    assert [s["title"] for s in t3.started] == ["dev-lead@r", "dev-impl@r"]


def test_up_passes_provider_only_with_model(tmp_path: Path) -> None:
    t3 = memory(tmp_path)
    up(make_rig(tmp_path, model="m"), t3)
    assert t3.started[0]["provider"] == "claudeAgent" and t3.started[0]["model"] == "m"
    t3 = memory(tmp_path)
    up(make_rig(tmp_path), t3)
    assert t3.started[0]["provider"] is None


def test_up_refuses_codex_without_model_before_starting_anything(tmp_path: Path) -> None:
    t3 = memory(tmp_path, provider="codex")
    with pytest.raises(RigError, match="need a model"):
        up(make_rig(tmp_path, runtime="codex"), t3)
    assert t3.started == []


def test_up_reports_wrong_provider(tmp_path: Path) -> None:
    with pytest.raises(RigError, match="T3 used codex"):
        up(make_rig(tmp_path), memory(tmp_path, provider="codex"))


def test_send_wraps_message_with_sender(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    up(rig, t3)
    seats = select_seats(rig, "dev.impl", sender="dev.lead")
    results = send(rig, t3, seats, "hello", sender="dev.lead", wait=True)
    assert t3.sent[-1] == ("id-dev-impl@r", "From: dev.lead\nTo: dev.impl\n---\nhello", True)
    assert results[0].error is None


def test_send_defaults_to_operator_and_can_be_raw(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    up(rig, t3)
    send(rig, t3, select_seats(rig, "dev.impl"), "hello")
    send(rig, t3, select_seats(rig, "dev.impl"), "hello", raw=True)
    assert t3.sent[0][1].startswith("From: operator\nTo: dev.impl")
    assert t3.sent[1][1] == "hello"


def test_fan_out_skips_sender_and_names_recipients(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    up(rig, t3)
    assert [s.id for s in select_seats(rig, everyone=True)] == ["lead", "impl"]
    seats = select_seats(rig, pod="dev", sender="dev.lead")
    assert [s.id for s in seats] == ["impl"]
    send(rig, t3, select_seats(rig, everyone=True), "hi")
    assert "To: dev.lead, dev.impl" in t3.sent[0][1] and len(t3.sent) == 2


def test_select_refuses_unknown_targets(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(RigError, match="no seat 'dev.ghost'"):
        select_seats(rig, "dev.ghost")
    with pytest.raises(RigError, match="no pod"):
        select_seats(rig, pod="ghost")
    with pytest.raises(RigError, match="--from"):
        select_seats(rig, "dev.impl", sender="dev.ghost")


def test_send_reports_seat_without_thread_and_continues(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r", threadId="i")
    results = send(rig, t3, select_seats(rig, everyone=True), "hi")
    assert results[0].error == "no thread; run `t3rig up` first"
    assert results[1].error is None and t3.sent[0][0] == "i"


def test_rows_report_pending_requests_and_older_threads(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.threads = [
        {
            "threadId": "new",
            "title": "dev-lead@r",
            "status": "running",
            "runtimeMode": "auto",
            "pendingRequestCount": 2,
        },
        {"threadId": "old", "title": "dev-lead@r", "status": "completed"},
    ]
    lead, impl = seat_rows(rig, t3)
    assert lead["pending_requests"] == 2 and lead["mode"] == "auto"
    assert lead["extra_threads"] == 1 and lead["thread_id"] == "new"
    assert impl["status"] == "not started" and impl["thread_id"] is None


def test_brief_covers_role_peers_and_culture(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    brief = seat_brief(rig, rig.seats[0])
    assert "seat dev.lead" in brief and "You delegates_to dev.impl" in brief
    assert (
        "Instructions from culture.md:\nBe honest." in brief
        and "-m t3rig send --from dev.lead" in brief
    )


def test_restricted_seat_launches_idle_then_gets_its_brief(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, model="m", runtime_mode="auto", effort="low")
    t3 = memory(tmp_path)
    lines = up(rig, t3)
    launch = next(args for name, args in t3.actions if name == "launch")
    assert "message" not in launch and launch["runtimeMode"] == "auto"
    assert launch["projectId"] == "p1"
    assert launch["modelSelection"] == {
        "instanceId": "claudeAgent",
        "model": "m",
        "options": {"effort": "low"},
    }
    assert "You are seat dev.lead" in t3.sent[0][1]
    assert t3.started == []
    assert lines[0] == "dev.lead: started id-dev-lead@r (auto)"


def test_wrong_mode_is_archived_before_the_seat_acts(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, model="m", runtime_mode="auto")
    t3 = memory(tmp_path, applied_mode="full-access")
    with pytest.raises(RigError, match="wanted mode auto, but T3 applied full-access"):
        up(rig, t3)
    assert [name for name, _ in t3.actions][-1] == "archive"
    assert t3.sent == []


def test_mode_above_sign_in_is_refused_before_starting_anything(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, model="m", runtime_mode="full-access")
    t3 = memory(tmp_path)
    with pytest.raises(RigError, match="needs full-access, but you're signed in at auto"):
        up(rig, t3)
    assert t3.actions == [] and t3.started == []


def test_effort_needs_a_model(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, effort="low")
    with pytest.raises(RigError, match="need a model"):
        up(rig, memory(tmp_path))


def test_unrestricted_seats_need_no_sign_in(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path, access_level=None)
    up(rig, t3)
    assert len(t3.started) == 2


def test_seat_outside_any_project_is_refused(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, model="m", runtime_mode="auto")
    t3 = MemoryT3(project_root=str(tmp_path / "elsewhere"))
    with pytest.raises(RigError, match="isn't inside a T3 project"):
        up(rig, t3)


def test_down_interrupts_busy_threads_and_archives_duplicates(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.threads = [
        {"threadId": "new", "title": "dev-lead@r", "status": "running"},
        {"threadId": "old", "title": "dev-lead@r", "status": "completed"},
        {"threadId": "other", "title": "not-a-seat", "status": "running"},
    ]
    lines, ok = down(rig, t3)
    assert ok and lines == ["dev.lead: archived new", "dev.lead: archived old"]
    assert [t["threadId"] for t in t3.threads] == ["other"]
    assert [a["threadId"] for n, a in t3.actions if n == "interrupt"] == ["new"]


def test_down_one_seat_leaves_the_others(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.threads = [
        {"threadId": "l", "title": "dev-lead@r", "status": "completed"},
        {"threadId": "i", "title": "dev-impl@r", "status": "completed"},
    ]
    _, ok = down(rig, t3, "dev.impl")
    assert ok and [t["threadId"] for t in t3.threads] == ["l"]


def test_down_reports_failures(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path, fail_archive=True)
    t3.put("dev-lead@r", threadId="l", status="completed")
    lines, ok = down(rig, t3)
    assert not ok and "couldn't stop l" in lines[0]


def test_down_without_sign_in_is_one_error(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path, access_level=None)
    t3.put("dev-lead@r", threadId="l", status="completed")
    with pytest.raises(T3Error, match="not signed in"):
        down(rig, t3)


def test_down_with_nothing_running_needs_no_sign_in(tmp_path: Path) -> None:
    t3 = memory(tmp_path, access_level=None)
    assert down(make_rig(tmp_path), t3) == (["no threads to stop"], True)


def test_log_shows_the_seats_latest_messages(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    up(rig, t3)
    t3.say("id-dev-impl@r", "hello")
    assert log(rig, t3, "dev.impl", 3) == "[assistant]\nhello\n"
    assert t3.shown == [("id-dev-impl@r", 3)]


def test_log_refuses_unknown_seat_and_seat_without_thread(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    with pytest.raises(RigError, match="no seat 'dev.nobody'"):
        log(rig, t3, "dev.nobody", 10)
    with pytest.raises(RigError, match="dev.impl has no thread; run `t3rig up`"):
        log(rig, t3, "dev.impl", 10)
    assert t3.shown == []


def test_log_shows_an_archived_thread_of_the_seat(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r", threadId="old")
    t3.say("old", "from before")
    down(rig, t3)
    up(rig, t3)
    assert log(rig, t3, "dev.impl", 2, "old") == "[assistant]\nfrom before\n"
    assert t3.shown == [("old", 2)]


def test_log_refuses_a_thread_of_another_seat(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.put("dev-lead@r", threadId="old")
    with pytest.raises(RigError, match="thread old is 'dev-lead@r', not dev.impl's 'dev-impl@r'"):
        log(rig, t3, "dev.impl", 2, "old")
    assert t3.shown == []


@pytest.mark.parametrize("messages", [0, -1])
def test_log_refuses_fewer_than_one_message_before_any_t3_call(
    tmp_path: Path, messages: int
) -> None:
    class Untouchable:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"shouldn't call t3.{name}")

    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    up(rig, t3)
    with pytest.raises(RigError, match="--messages must be at least 1"):
        log(rig, t3, "dev.impl", messages)
    assert t3.shown == []
    # Checked before the seat lookup too: an unknown seat gets this error, and T3 is untouched.
    with pytest.raises(RigError, match="--messages must be at least 1"):
        log(rig, Untouchable(), "dev.nobody", messages)  # type: ignore[arg-type]


def test_stop_interrupts_and_keeps_the_thread(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r", threadId="i", status="running")
    assert stop(rig, t3, "dev.impl") == "dev.impl: stopped (interrupted); it can be messaged again"
    assert [name for name, _ in t3.actions] == ["interrupt"]
    assert [t["threadId"] for t in t3.threads] == ["i"]


def test_stop_needs_no_sign_in_when_nothing_is_running(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path, access_level=None)
    t3.put("dev-impl@r", threadId="i", status="completed")
    assert stop(rig, t3, "dev.impl") == "dev.impl: nothing to stop (completed)"
    with pytest.raises(RigError, match="has no thread"):
        stop(rig, t3, "dev.lead")
    with pytest.raises(RigError, match="no seat"):
        stop(rig, t3, "dev.ghost")


def test_stop_reports_a_seat_that_stays_busy(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path, keep_running=True)
    t3.put("dev-impl@r", threadId="i", status="running")
    result = stop(rig, t3, "dev.impl", lambda _: None, 0)
    assert result == "dev.impl: stop requested, but it's still running"


def task_rig(tmp_path: Path, **settings: Any) -> Rig:
    """dev.lead long-lived, dev.impl per issue."""
    return dataclasses.replace(make_rig(tmp_path), per_task={"dev.impl": "issue"}, **settings)


def test_up_skips_per_task_seats(tmp_path: Path) -> None:
    rig, t3 = task_rig(tmp_path), memory(tmp_path)
    lines = up(rig, t3)
    assert lines == [
        "dev.impl: per-task seat, started per task with `send --new --task`",
        "dev.lead: started id-dev-lead@r (unknown mode)",
    ]
    assert [s["title"] for s in t3.started] == ["dev-lead@r"]


def test_start_task_uses_the_seat_s_settings_and_a_brief_naming_the_task(tmp_path: Path) -> None:
    rig = dataclasses.replace(
        make_rig(tmp_path, model="m", runtime_mode="auto", effort="low"),
        per_task={"dev.impl": "issue"},
    )
    t3 = memory(tmp_path)
    assert (
        start_task(rig, t3, rig.seats[1], "#18") == "dev.impl #18: started id-dev-impl@r #18 (auto)"
    )
    launch = next(args for name, args in t3.actions if name == "launch")
    assert launch["title"] == "dev-impl@r #18" and launch["runtimeMode"] == "auto"
    assert launch["modelSelection"]["options"] == {"effort": "low"}
    brief = t3.sent[0][1]
    assert "This thread is for one task, #18" in brief and "You are seat dev.impl" in brief


def test_start_task_refuses_a_live_task_a_long_lived_seat_and_too_many_issues(
    tmp_path: Path,
) -> None:
    rig, t3 = task_rig(tmp_path), memory(tmp_path)
    start_task(rig, t3, rig.seats[1], "#18")
    with pytest.raises(RigError, match="already has a live thread for task #18"):
        start_task(rig, t3, rig.seats[1], "#18")
    with pytest.raises(RigError, match=r"already works on #18, and max_parallel is 1"):
        start_task(rig, t3, rig.seats[1], "#19")
    start_task(rig, t3, rig.seats[1], "#18 r2")  # Another task of the same issue counts once.
    with pytest.raises(RigError, match="dev.lead isn't a per-task seat"):
        start_task(rig, t3, rig.seats[0], "#18")
    wider = task_rig(tmp_path, max_parallel=2)
    start_task(wider, t3, wider.seats[1], "#19")
    assert len(t3.started) == 3


def test_send_reaches_a_task_thread(tmp_path: Path) -> None:
    rig, t3 = task_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r #18", threadId="a18")
    impl = select_seats(rig, "dev.impl")
    assert send(rig, t3, impl, "fix it", task="#18")[0].error is None
    assert send(rig, t3, impl, "and this")[0].error is None  # Its only live thread.
    assert [to for to, _, _ in t3.sent] == ["a18", "a18"]
    result = send(rig, t3, impl, "hi", task="#19")[0]
    assert result.error == "dev.impl has no live thread for task #19"


def test_down_task_archives_every_round_of_that_issue_only(tmp_path: Path) -> None:
    rig = dataclasses.replace(
        make_rig(tmp_path), per_task={"dev.impl": "issue", "dev.lead": "round"}
    )
    t3 = memory(tmp_path)
    t3.put("dev-impl@r #18", threadId="a18", status="running")
    t3.put("dev-lead@r #18 r1", threadId="r1", status="completed")
    t3.put("dev-impl@r #19", threadId="a19", status="running")
    lines, ok = down(rig, t3, task="#18")
    assert ok and sorted(lines) == ["dev.impl #18: archived a18", "dev.lead #18 r1: archived r1"]
    assert [t["threadId"] for t in t3.threads] == ["a19"]
    assert [a["threadId"] for n, a in t3.actions if n == "interrupt"] == ["a18"]


def test_log_and_rows_cover_task_threads(tmp_path: Path) -> None:
    rig, t3 = task_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r #18", threadId="a18", status="completed", link="http://t3/a18")
    t3.say("a18", "done with #18")
    assert log(rig, t3, "dev.impl", 1, task="#18") == "[assistant]\ndone with #18\n"
    lead, impl = seat_rows(rig, t3)
    assert lead["task"] is None and lead["status"] == "not started"
    assert impl["task"] == "#18" and impl["title"] == "dev-impl@r #18"
    assert impl["link"] == "http://t3/a18"


def test_the_lead_s_brief_says_how_to_start_task_threads(tmp_path: Path) -> None:
    rig = task_rig(tmp_path)
    lead = seat_brief(rig, rig.seats[0])
    assert "These seats get a new T3 thread per task: dev.impl." in lead
    assert '--new --task "#N" <seat>' in lead and '--task "#N"' in lead
    assert "per task" not in seat_brief(make_rig(tmp_path), make_rig(tmp_path).seats[0])
