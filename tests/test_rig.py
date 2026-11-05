from pathlib import Path
from typing import Any

import pytest

from t3rig.rig import RigError, seat_brief, seat_rows, seat_statuses, select_seats, send, up
from t3rig.spec import Edge, Rig, Seat, StartupText


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


def make_rig(tmp_path: Path, runtime: str = "claude-code", model: str | None = None) -> Rig:
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
            Seat(id="lead", runtime=runtime, model=model, **common),
            Seat(id="impl", runtime=runtime, model=model, **common),
        ),
        edges=(Edge("delegates_to", "dev.lead", "dev.impl"),),
    )


def test_up_starts_each_seat_once(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    assert up(rig, t3) == ["dev.lead: started id-dev-lead@r", "dev.impl: started id-dev-impl@r"]
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
