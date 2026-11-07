import dataclasses
from pathlib import Path
from typing import Any

import pytest
from test_rig import make_rig, memory

from t3rig.t3 import T3Error
from t3rig.threads import (
    RigError,
    T3Code,
    earlier_thread,
    issue_of,
    issue_threads,
    seat_thread,
    seat_threads,
    task_threads,
)


def test_a_seats_thread_is_the_newest_with_its_session_name(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.threads = [
        {"threadId": "new", "title": "dev-lead@r"},
        {"threadId": "old", "title": "dev-lead@r"},
    ]
    lead, impl = seat_threads(rig, t3)
    assert lead.thread is not None and lead.thread["threadId"] == "new"
    assert lead.duplicates == 1
    assert impl.thread is None
    with pytest.raises(RigError, match="dev.impl has no thread; run `t3rig up` first"):
        seat_thread(rig, t3, rig.seats[1])


def test_an_archived_thread_is_found_by_id_and_checked_by_title(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r", threadId="old")
    t3.archive("old")
    assert seat_threads(rig, t3)[1].thread is None
    earlier_thread(rig, t3, rig.seats[1], "old")
    with pytest.raises(RigError, match="thread old is 'dev-impl@r', not dev.lead's"):
        earlier_thread(rig, t3, rig.seats[0], "old")


class Tools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = False

    def call(self, tool: str, **arguments: Any) -> Any:
        self.calls.append((tool, arguments))
        if self.fail:
            raise T3Error("session gone")
        return {}


def test_t3code_signs_in_once_and_again_after_a_failure() -> None:
    tools, connects = Tools(), []

    def connect() -> tuple[Tools, str]:
        connects.append(1)
        return tools, "auto"

    t3 = T3Code(cli=object(), connect=connect)  # type: ignore[arg-type]
    assert connects == []  # Nothing signs in until an action needs /mcp.
    t3.interrupt("a", reason="why")
    t3.archive("a")
    assert len(connects) == 1
    assert tools.calls == [
        ("t3_thread_interrupt", {"threadId": "a", "reason": "why"}),
        ("t3_thread_organize", {"action": "archive", "threadId": "a"}),
    ]
    tools.fail = True
    with pytest.raises(T3Error):
        t3.archive("a")
    tools.fail = False
    t3.archive("a")
    assert len(connects) == 2


def test_memory_t3_lists_only_what_t3_thread_list_gives(tmp_path: Path) -> None:
    t3 = memory(tmp_path)
    t3.put("dev-impl@r", threadId="i", status="running", pendingRequestCount=1, runCount=3)
    (listed,) = t3.list_threads(str(tmp_path))
    assert "pendingRequestCount" not in listed and "runCount" not in listed
    shown = t3.show_thread("i")["thread"]
    assert shown["pendingRequestCount"] == 1 and shown["runCount"] == 3


def test_memory_t3_refuses_to_send_to_an_archived_or_unknown_thread(tmp_path: Path) -> None:
    t3 = memory(tmp_path)
    t3.put("dev-impl@r", threadId="i")
    t3.archive("i")
    for thread_id in ("i", "nope"):
        with pytest.raises(T3Error, match="no longer available"):
            t3.send(thread_id, "hi")
    assert t3.sent == []


def per_task_rig(tmp_path: Path) -> Any:
    """dev.lead long-lived, dev.impl per issue."""
    return dataclasses.replace(make_rig(tmp_path), per_task={"dev.impl": "issue"})


def test_a_per_task_seat_has_one_entry_per_live_task_thread(tmp_path: Path) -> None:
    rig, t3 = per_task_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r #18", threadId="a18")
    t3.put("dev-impl@r #19", threadId="a19")
    t3.put("dev-impl@r", threadId="old")  # A long-lived thread from before isn't a task thread.
    t3.put("dev-lead@r", threadId="lead")
    t3.put("dev-lead@r #18", threadId="odd")  # A long-lived seat has no task threads.
    found = seat_threads(rig, t3)
    assert [(s.label, s.thread and s.thread["threadId"]) for s in found] == [
        ("dev.lead", "lead"),
        ("dev.impl #19", "a19"),
        ("dev.impl #18", "a18"),
    ]
    assert [s.title for s in found][1] == "dev-impl@r #19"
    assert [s.task for s in task_threads(rig, t3, rig.seats[1])] == ["#19", "#18"]


def test_a_per_task_seat_without_tasks_has_one_empty_entry(tmp_path: Path) -> None:
    rig, t3 = per_task_rig(tmp_path), memory(tmp_path)
    impl = seat_threads(rig, t3)[1]
    assert impl.task is None and impl.thread is None
    with pytest.raises(RigError, match="no live task thread; start one with `send --new --task`"):
        seat_thread(rig, t3, rig.seats[1])


def test_reaching_a_per_task_seat(tmp_path: Path) -> None:
    rig, t3 = per_task_rig(tmp_path), memory(tmp_path)
    t3.put("dev-impl@r #18", threadId="a18")
    assert seat_thread(rig, t3, rig.seats[1])["threadId"] == "a18"  # Its only live one.
    t3.put("dev-impl@r #19", threadId="a19")
    with pytest.raises(RigError, match=r"several task threads \(#19, #18\); pick one with --task"):
        seat_thread(rig, t3, rig.seats[1])
    assert seat_thread(rig, t3, rig.seats[1], "#18")["threadId"] == "a18"
    with pytest.raises(RigError, match="no live thread for task #20"):
        seat_thread(rig, t3, rig.seats[1], "#20")
    with pytest.raises(RigError, match="dev.lead isn't a per-task seat"):
        seat_thread(rig, t3, rig.seats[0], "#18")


def test_an_issue_s_task_threads_include_every_round(tmp_path: Path) -> None:
    rig = dataclasses.replace(
        make_rig(tmp_path), per_task={"dev.impl": "issue", "dev.lead": "round"}
    )
    t3 = memory(tmp_path)
    for title in ("dev-impl@r #18", "dev-lead@r #18 r1", "dev-lead@r #18 r2", "dev-impl@r #180"):
        t3.put(title)
    found = [(s.seat_id, task) for s, task, _ in issue_threads(rig, t3, "#18")]
    assert sorted(found) == [("dev.impl", "#18"), ("dev.lead", "#18 r1"), ("dev.lead", "#18 r2")]
    assert issue_of("#18 r2") == "#18"
