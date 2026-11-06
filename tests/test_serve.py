import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_watch import IMPL, LEAD, QA, FakeTracker, fake_t3, put, started

from t3rig.rig import RigError, seat_rows
from t3rig.serve import (
    FRAGMENTS,
    RigServer,
    check_host,
    create_app,
    role_name,
    sort_issues,
    sse_message,
)
from t3rig.serve_demo import demo_server
from t3rig.spec import Edge, Rig, Seat, TrackerSettings
from t3rig.threads import MemoryT3
from t3rig.tracker import Issue
from t3rig.watch import state_path


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    common = {"pod": "dev", "cwd": tmp_path, "agent_ref": "x", "profile": "default"}
    seats = tuple(Seat(id=i, runtime="claude-code", **common) for i in ("lead", "impl", "qa"))
    edges = (Edge("delegates_to", "dev.lead", "dev.impl"),)
    tracker = TrackerSettings("github", "o/r", "dev.lead")
    return Rig(name="r", path=tmp_path / "rig.yaml", seats=seats, edges=edges, tracker=tracker)


def http_client(server: RigServer) -> TestClient:
    return TestClient(create_app(server), base_url="http://127.0.0.1:8765")


def make_server(rig: Rig, interval: float = 15) -> tuple[RigServer, MemoryT3, FakeTracker]:
    t3, tracker = fake_t3(), FakeTracker()
    started(t3)
    server = RigServer(rig, t3, interval, 0, make_tracker=lambda s: tracker, out=lambda line: None)
    return server, t3, tracker


def test_seats_api_is_ps_with_the_latest_message(rig: Rig) -> None:
    server, t3, _ = make_server(rig)
    server.refresh()
    body = http_client(server).get("/api/seats").json()
    assert body["rig"] == "r"
    expected = [
        row | {"last_activity": {"role": "assistant", "text": "all done"}}
        for row in seat_rows(rig, t3)
    ]
    assert body["seats"] == expected
    assert body["watch_last_check"] is None


def test_seat_status_changes_go_to_the_stream(rig: Rig) -> None:
    server, t3, _ = make_server(rig)
    server.refresh()
    put(t3, IMPL, 2, status="running")
    server.refresh()
    events = http_client(server).get("/api/events").json()["events"]
    assert [(e["kind"], e["text"]) for e in events] == [("seat", "dev.impl: completed → running")]


def test_issues_sort_into_needs_you_and_the_queue() -> None:
    def issue(number: int, *labels: str) -> Issue:
        return Issue(number, f"https://t/issues/{number}", frozenset(labels), f"T{number}")

    issues = [
        issue(4, "needs-approval"),
        issue(3, "rig-queue", "needs-approval"),
        issue(2, "in-progress"),
        issue(1, "needs-answer"),
        issue(5, "enhancement"),
    ]
    sorted_ = sort_issues(issues)
    assert [i["number"] for i in sorted_["needs_you"]] == [1, 4]
    assert [i["number"] for i in sorted_["queue"]] == [2, 3]
    assert sorted_["needs_you"][0] == {
        "number": 1,
        "title": "T1",
        "url": "https://t/issues/1",
        "labels": ["needs-answer"],
    }


def test_page_and_scripts_are_served(rig: Rig) -> None:
    server, _, _ = make_server(rig)
    server.refresh()
    client = http_client(server)
    page = client.get("/").text
    assert 'sse-connect="/api/stream"' in page
    assert "dev.impl" in page and "all done" in page and "http://t3/dev-impl@r" in page
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/sse.js").status_code == 200


def test_page_escapes_seat_text(rig: Rig) -> None:
    server, t3, _ = make_server(rig)
    t3.say(f"id-{IMPL}", "<script>alert(1)</script>")
    server.refresh()
    page = http_client(server).get("/").text
    assert "<script>alert(1)" not in page and "&lt;script&gt;" in page


def test_sse_message_puts_each_line_in_a_data_field() -> None:
    assert sse_message("seats", "<p>\n</p>") == "event: seats\ndata: <p>\ndata: </p>\n\n"


def test_stream_sends_every_fragment_then_only_what_changed(rig: Rig) -> None:
    server, _, _ = make_server(rig)
    server.refresh()

    async def messages() -> list[str]:
        async def connected() -> bool:
            return False

        stream = server.stream(connected)
        sent = [await anext(stream) for _ in FRAGMENTS]
        waiting = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0)
        server.log("pinged dev.lead: dev.impl")
        await server.notify()
        sent.append(await waiting)
        sent.append(await anext(stream))
        return sent

    names = [m.split("\n")[0].removeprefix("event: ") for m in asyncio.run(messages())]
    # The seats and issues didn't change, so an open "more" in a seat card isn't swapped shut.
    assert names == [*FRAGMENTS, "latest", "events"]


def test_watch_runs_inside_the_server(rig: Rig) -> None:
    server, t3, tracker = make_server(rig, interval=0.01)
    tracker.labels[5] = {"rig-queue"}
    with http_client(server) as client:
        deadline = time.monotonic() + 5
        while not t3.sent and time.monotonic() < deadline:
            time.sleep(0.01)
        assert t3.sent and t3.sent[0][0] == f"id-{LEAD}"
        assert "https://t/issues/5" in t3.sent[0][1]
        while not client.get("/api/issues").json()["queue"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [i["number"] for i in client.get("/api/issues").json()["queue"]] == [5]
        events = client.get("/api/events").json()["events"]
        assert any(e["text"] == "pinged dev.lead: #5" for e in events)
        assert client.get("/api/seats").json()["watch_last_check"] is not None


def test_closing_ends_open_streams(rig: Rig) -> None:
    server, _, _ = make_server(rig)

    async def drain() -> int:
        server.loop = asyncio.get_running_loop()

        async def connected() -> bool:
            return False

        stream = server.stream(connected)
        count = 0
        async for _ in stream:
            count += 1
            if count == len(FRAGMENTS):
                server.close_streams()
        return count

    assert asyncio.run(asyncio.wait_for(drain(), 5)) == len(FRAGMENTS)


def test_only_localhost_names_are_answered(rig: Rig) -> None:
    server, _, _ = make_server(rig)
    http = http_client(server)
    assert http.get("/api/seats", headers={"Host": "localhost:8765"}).status_code == 200
    assert http.get("/api/seats", headers={"Host": "evil.example"}).status_code == 400
    assert http.get("/api/seats", headers={"Host": "evil.example:8765"}).status_code == 400


def test_a_failing_round_is_reported_and_the_loop_goes_on(rig: Rig) -> None:
    server, t3, tracker = make_server(rig, interval=0.01)
    lines: list[str] = []
    server.print = lines.append
    assert server.watcher is not None
    step = server.watcher.step
    calls = []

    def flaky() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        step()

    server.watcher.step = flaky  # type: ignore[method-assign]
    tracker.labels[5] = {"rig-queue"}
    with http_client(server) as http:
        deadline = time.monotonic() + 5
        while not t3.sent and time.monotonic() < deadline:
            time.sleep(0.01)
        assert t3.sent
        events = http.get("/api/events").json()["events"]
    assert lines[0] == "ALERT: watch round failed, will retry: ValueError('boom')"
    assert any(e["kind"] == "error" and "boom" in e["text"] for e in events)


def test_host_flag_adds_its_address_to_the_host_check(rig: Rig) -> None:
    server, _, _ = make_server(rig)
    http = TestClient(create_app(server, "192.168.5.10"), base_url="http://192.168.5.10:8765")
    assert http.get("/api/seats").status_code == 200
    assert http.get("/api/seats", headers={"Host": "127.0.0.1:8765"}).status_code == 200
    assert http.get("/api/seats", headers={"Host": "evil.example"}).status_code == 400
    default = http_client(server)
    assert default.get("/api/seats", headers={"Host": "192.168.5.10"}).status_code == 400
    for address in ("fe80::1", "::1"):
        v6 = TestClient(create_app(server, address), base_url=f"http://[{address}]:8765")
        assert v6.get("/api/seats").status_code == 200
        assert v6.get("/api/seats", headers={"Host": f"[{address}]:8765"}).status_code == 200
        assert v6.get("/api/seats", headers={"Host": "evil.example"}).status_code == 400


@pytest.mark.parametrize("host", ["0.0.0.0", "::", ""])
def test_wildcard_hosts_are_refused(host: str) -> None:
    with pytest.raises(RigError, match="the one address"):
        check_host(host)


def test_concrete_hosts_are_accepted() -> None:
    for host in ("127.0.0.1", "192.168.5.10", "fe80::1", "box.local"):
        check_host(host)


def page_of(server: RigServer) -> str:
    return http_client(server).get("/").text


def test_roles_are_named_in_words() -> None:
    assert role_name("dev.lead") == "Lead"
    assert role_name("dev.impl") == "Implementer"
    assert role_name("dev.review") == "Reviewer"
    assert role_name("dev.pm") == "Project manager"
    assert role_name("ops.release-manager") == "Release manager"


def test_seat_cards_show_role_state_and_the_leads_issue(rig: Rig) -> None:
    server, t3, tracker = make_server(rig)
    put(t3, IMPL, 2, status="running")
    put(t3, QA, 2, status="running", pending=1)
    tracker.labels[9] = {"rig-queue", "in-progress"}
    assert server.watcher is not None
    server.watcher.poll_tracker()
    server.refresh()
    seats = server.fragment("seats")
    assert "<h3>Lead</h3>" in seats and "<h3>Implementer</h3>" in seats and "<h3>Qa</h3>" in seats
    assert 'state-working"><span class="dot" aria-hidden="true"></span>working' in seats
    assert "waiting for you" in seats and "idle" in seats
    assert 'On <a href="https://t/issues/9">#9 Issue 9</a>' in seats


def test_long_messages_fold_behind_more(rig: Rig) -> None:
    server, t3, _ = make_server(rig)
    t3.say(f"id-{IMPL}", "line\n" * 10)
    server.refresh()
    seats = server.fragment("seats")
    assert seats.count('<details class="message">') == 1  # Short replies stay plain.
    assert '<span class="more">more</span>' in seats


def test_summary_counts_what_needs_the_operator(rig: Rig) -> None:
    server, t3, tracker = make_server(rig)
    put(t3, QA, 2, status="running", pending=1)
    tracker.labels.update(
        {
            3: {"needs-answer"},
            4: {"needs-approval"},
            5: {"needs-approval", "rig-queue"},
            9: {"rig-queue", "in-progress"},
        }
    )
    assert server.watcher is not None
    server.watcher.poll_tracker()
    server.refresh()
    summary = server.fragment("summary")
    assert "3 things need you" in summary  # A question, an approval and a waiting seat.
    assert "Lead is working on #9" in summary and "1 queued" in summary


def test_needs_you_is_split_and_shows_no_label_names(rig: Rig) -> None:
    server, _, tracker = make_server(rig)
    tracker.labels.update({3: {"needs-answer"}, 4: {"needs-approval"}, 9: {"in-progress"}})
    assert server.watcher is not None
    server.watcher.poll_tracker()
    server.refresh()
    issues = server.fragment("issues")
    questions, rest = issues.split("Waiting for your approval")
    approvals, queue = rest.split("<h2>Queue")
    assert "by issue number" in queue
    assert '<a href="https://t/issues/3"><span class="num">#3</span> Issue 3</a>' in questions
    assert "#4" in approvals and "#3" not in approvals
    assert 'class="current"' in queue and "in progress" in queue
    for label in ("needs-answer", "needs-approval", "in-progress", "rig-queue"):
        assert label not in issues


def test_activity_log_is_collapsed_to_its_latest_line(rig: Rig) -> None:
    server, _, _ = make_server(rig)
    server.log("first")
    server.log("pinged dev.lead: dev.impl")
    server.refresh()
    page = page_of(server)
    assert '<details class="log">' in page  # Closed until opened.
    latest = server.fragment("latest")
    assert "pinged dev.lead: dev.impl" in latest and "first" not in latest
    events = server.fragment("events")
    assert events.index("pinged dev.lead") < events.index("first")  # Newest first.
    # The swapped parts sit inside the <details>, so a swap can't close an open log.
    assert page.index('<details class="log">') < page.index('sse-swap="latest"')
    assert page.index('<details class="log">') < page.index('sse-swap="events"')


def test_demo_shows_every_state_without_real_t3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "unused"))  # Restored after the test.
    server = demo_server(tmp_path)
    assert server.watcher is not None
    server.watcher.step()
    server.refresh()
    page = page_of(server)
    for word in ("working", "idle", "waiting for you", "failed"):
        assert f"</span>{word}</p>" in page
    assert "Questions for you" in page and "#7" in page and "#13" in page
    assert "Lead is working on #9" in page
    assert state_path(server.rig).is_relative_to(tmp_path)
