from pathlib import Path
from typing import Any

import pytest
from test_rig import make_rig, memory

from t3rig.t3 import T3Error
from t3rig.threads import RigError, T3Code, earlier_thread, seat_thread, seat_threads


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
