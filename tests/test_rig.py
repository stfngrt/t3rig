from pathlib import Path
from typing import Any

import pytest

from t3rig.rig import RigError, seat_brief, seat_statuses, send, up
from t3rig.spec import Edge, Rig, Seat


class FakeT3:
    def __init__(self, provider: str = "claudeAgent") -> None:
        self.provider = provider
        self.threads: list[dict[str, Any]] = []
        self.started: list[dict[str, Any]] = []
        self.sent: list[tuple[str, str, bool]] = []

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        return list(self.threads)

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
    common = {"pod": "dev", "cwd": tmp_path, "agent_ref": "local:a", "profile": "default"}
    return Rig(
        name="r",
        path=tmp_path / "rig.yaml",
        seats=(
            Seat(id="lead", runtime=runtime, model=model, **common),
            Seat(id="impl", runtime=runtime, model=model, **common),
        ),
        edges=(Edge("delegates_to", "dev.lead", "dev.impl"),),
        culture="Be honest.",
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


def test_send_routes_to_seat_thread(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    up(rig, t3)
    send(rig, t3, "dev.impl", "hello", wait=True)
    assert t3.sent == [("id-dev-impl@r", "hello", True)]


def test_send_refuses_unknown_and_unstarted_seats(tmp_path: Path) -> None:
    rig, t3 = make_rig(tmp_path), FakeT3()
    with pytest.raises(RigError, match="no seat"):
        send(rig, t3, "dev.ghost", "hello")
    with pytest.raises(RigError, match="no thread"):
        send(rig, t3, "dev.impl", "hello")


def test_brief_covers_role_peers_and_culture(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    brief = seat_brief(rig, rig.seats[0])
    assert "seat dev.lead" in brief and "You delegates_to dev.impl" in brief
    assert "Be honest." in brief and "-m t3rig send" in brief
