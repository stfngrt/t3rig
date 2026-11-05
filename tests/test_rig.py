from pathlib import Path
from typing import Any

import pytest

from t3rig.rig import RigError, down, seat_brief, seat_rows, seat_statuses, select_seats, send, up
from t3rig.spec import Edge, Rig, Seat, StartupText
from t3rig.t3 import T3Error


class FakeT3:
    def __init__(self, provider: str = "claudeAgent") -> None:
        self.provider = provider
        self.threads: list[dict[str, Any]] = []
        self.started: list[dict[str, Any]] = []
        self.sent: list[tuple[str, str, bool]] = []
        self.details: dict[str, dict[str, Any]] = {}

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        return list(self.threads)

    def show_thread(self, thread_id: str, messages: int = 1) -> dict[str, Any]:
        return {"thread": self.details.get(thread_id, {})}

    def start_thread(self, project, title, message, provider, model) -> str:
        thread_id = f"id-{title}"
        self.started.append(
            {"title": title, "message": message, "provider": provider, "model": model}
        )
        self.threads.insert(
            0,
            {
                "threadId": thread_id,
                "title": title,
                "status": "running",
                "providerInstanceId": self.provider,
            },
        )
        return thread_id

    def send(self, thread_id: str, message: str, wait: bool = False) -> str:
        self.sent.append((thread_id, message, wait))
        return ""


class FakeTools:
    """T3's /mcp tools, sharing threads with a FakeT3."""

    def __init__(self, t3: FakeT3, root: Path, applied_mode: str | None = None) -> None:
        self.t3, self.root, self.applied_mode = t3, root, applied_mode
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_archive = False

    def call(self, tool: str, **arguments: Any) -> Any:
        self.calls.append((tool, arguments))
        if tool == "t3_project_list":
            return {"projects": [{"id": "p1", "workspaceRoot": str(self.root)}]}
        if tool == "t3_thread_launch":
            selection = arguments.get("modelSelection", {})
            thread = {
                "threadId": f"id-{arguments['title']}",
                "title": arguments["title"],
                "status": "idle",
                "providerInstanceId": selection.get("instanceId", self.t3.provider),
                "model": selection.get("model", "default-model"),
                "runtimeMode": self.applied_mode or arguments.get("runtimeMode", "full-access"),
            }
            self.t3.threads.insert(0, thread)
            self.t3.details[thread["threadId"]] = thread
            options = [{"id": k, "value": v} for k, v in selection.get("options", {}).items()]
            return {"threadId": thread["threadId"], "modelSelection": {"options": options}}
        if tool == "t3_thread_organize":
            if self.fail_archive:
                raise T3Error("nope")
            self.t3.threads = [t for t in self.t3.threads if t["threadId"] != arguments["threadId"]]
        return {}

    def tool_names(self) -> list[str]:
        return [name for name, _ in self.calls]


def connect_as(tools: FakeTools, access: str = "auto") -> Any:
    return lambda: (tools, access)


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
    rig, t3 = make_rig(tmp_path), FakeT3()
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
    t3 = FakeT3()
    up(make_rig(tmp_path, model="m"), t3)
    assert t3.started[0]["provider"] == "claudeAgent" and t3.started[0]["model"] == "m"
    t3 = FakeT3()
    up(make_rig(tmp_path), t3)
    assert t3.started[0]["provider"] is None


def test_up_refuses_codex_without_model_before_starting_anything(tmp_path: Path) -> None:
    t3 = FakeT3(provider="codex")
    with pytest.raises(RigError, match="need a model"):
        up(make_rig(tmp_path, runtime="codex"), t3)
    assert t3.started == []


def test_up_reports_wrong_provider(tmp_path: Path) -> None:
    with pytest.raises(RigError, match="T3 used codex"):
        up(make_rig(tmp_path), FakeT3(provider="codex"))


def test_statuses_use_newest_thread(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    t3.threads = [
        {"threadId": "new", "title": "dev-lead@r"},
        {"threadId": "old", "title": "dev-lead@r"},
    ]
    statuses = seat_statuses(rig, t3)
    assert statuses[0].thread["threadId"] == "new"
    assert statuses[1].thread is None


def test_send_wraps_message_with_sender(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    up(rig, t3)
    seats = select_seats(rig, "dev.impl", sender="dev.lead")
    results = send(rig, t3, seats, "hello", sender="dev.lead", wait=True)
    assert t3.sent == [("id-dev-impl@r", "From: dev.lead\nTo: dev.impl\n---\nhello", True)]
    assert results[0].error is None


def test_send_labels_unknown_sender_and_can_be_raw(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    up(rig, t3)
    send(rig, t3, select_seats(rig, "dev.impl"), "hello")
    send(rig, t3, select_seats(rig, "dev.impl"), "hello", raw=True)
    assert t3.sent[0][1].startswith("From: <unknown sender>\nTo: dev.impl")
    assert t3.sent[1][1] == "hello"


def test_fan_out_skips_sender_and_names_recipients(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
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
    rig, t3 = make_rig(tmp_path), FakeT3()
    t3.threads = [{"threadId": "i", "title": "dev-impl@r"}]
    results = send(rig, t3, select_seats(rig, everyone=True), "hi")
    assert "no thread" in results[0].error
    assert results[1].error is None and t3.sent[0][0] == "i"


def test_rows_report_pending_requests_and_older_threads(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    t3.threads = [
        {"threadId": "new", "title": "dev-lead@r", "status": "running", "runtimeMode": "auto"},
        {"threadId": "old", "title": "dev-lead@r", "status": "completed"},
    ]
    t3.details["new"] = {"pendingRequestCount": 2}
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
    t3 = FakeT3()
    tools = FakeTools(t3, tmp_path)
    lines = up(rig, t3, connect_as(tools))
    launch = next(args for name, args in tools.calls if name == "t3_thread_launch")
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
    t3 = FakeT3()
    tools = FakeTools(t3, tmp_path, applied_mode="full-access")
    with pytest.raises(RigError, match="wanted mode auto, but T3 applied full-access"):
        up(rig, t3, connect_as(tools))
    assert "t3_thread_organize" in tools.tool_names()
    assert t3.sent == []


def test_mode_above_sign_in_is_refused_before_starting_anything(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, model="m", runtime_mode="full-access")
    t3 = FakeT3()
    tools = FakeTools(t3, tmp_path)
    with pytest.raises(RigError, match="needs full-access, but you're signed in at auto"):
        up(rig, t3, connect_as(tools))
    assert tools.calls == [] and t3.started == []


def test_effort_needs_a_model(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, effort="low")
    with pytest.raises(RigError, match="need a model"):
        up(rig, FakeT3(), connect_as(FakeTools(FakeT3(), tmp_path)))


def test_unrestricted_seats_need_no_sign_in(tmp_path: Path) -> None:
    def refuse() -> Any:
        raise AssertionError("shouldn't sign in")

    rig, t3 = make_rig(tmp_path), FakeT3()
    up(rig, t3, refuse)
    assert len(t3.started) == 2


def test_seat_outside_any_project_is_refused(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, model="m", runtime_mode="auto")
    t3 = FakeT3()
    with pytest.raises(RigError, match="isn't inside a T3 project"):
        up(rig, t3, connect_as(FakeTools(t3, tmp_path / "elsewhere")))


def test_down_interrupts_busy_threads_and_archives_duplicates(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    t3.threads = [
        {"threadId": "new", "title": "dev-lead@r", "status": "running"},
        {"threadId": "old", "title": "dev-lead@r", "status": "completed"},
        {"threadId": "other", "title": "not-a-seat", "status": "running"},
    ]
    tools = FakeTools(t3, tmp_path)
    lines, ok = down(rig, t3, connect=connect_as(tools))
    assert ok and lines == ["dev.lead: archived new", "dev.lead: archived old"]
    assert [t["threadId"] for t in t3.threads] == ["other"]
    assert [a["threadId"] for n, a in tools.calls if n == "t3_thread_interrupt"] == ["new"]


def test_down_one_seat_leaves_the_others(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    t3.threads = [
        {"threadId": "l", "title": "dev-lead@r", "status": "completed"},
        {"threadId": "i", "title": "dev-impl@r", "status": "completed"},
    ]
    _, ok = down(rig, t3, "dev.impl", connect=connect_as(FakeTools(t3, tmp_path)))
    assert ok and [t["threadId"] for t in t3.threads] == ["l"]


def test_down_reports_failures(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    t3.threads = [{"threadId": "l", "title": "dev-lead@r", "status": "completed"}]
    tools = FakeTools(t3, tmp_path)
    tools.fail_archive = True
    lines, ok = down(rig, t3, connect=connect_as(tools))
    assert not ok and "couldn't stop l" in lines[0]


def test_down_with_nothing_running_needs_no_sign_in(tmp_path: Path) -> None:
    def refuse() -> Any:
        raise AssertionError("shouldn't sign in")

    assert down(make_rig(tmp_path), FakeT3(), connect=refuse) == (["no threads to stop"], True)
