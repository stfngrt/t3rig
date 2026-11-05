import json
import os
import stat
import time
from pathlib import Path
from typing import Any

import pytest

from t3rig import mcp
from t3rig.t3 import T3Error


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "t3rig" / "credentials.json"


def write_credential(path: Path, mode: int = 0o600, expires_in: float = 100) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "origin": "http://t3",
                "access_token": "secret",
                "access": "auto",
                "expires_at": time.time() + expires_in,
            }
        )
    )
    os.chmod(path, mode)


def test_saved_credential_is_private(config: Path) -> None:
    mcp._save_credential(config, {"access_token": "secret"})
    assert stat.S_IMODE(config.stat().st_mode) == 0o600


def test_load_refuses_missing_open_and_expired_credentials(config: Path) -> None:
    with pytest.raises(T3Error, match="not signed in"):
        mcp.load_credential()
    write_credential(config, mode=0o644)
    with pytest.raises(T3Error, match="readable by others"):
        mcp.load_credential()
    config.unlink()
    config.parent.rmdir()
    write_credential(config, expires_in=-1)
    with pytest.raises(T3Error, match="expired"):
        mcp.load_credential()


def test_login_never_returns_the_token_and_refuses_bad_state(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp, "server_origin", lambda: "http://t3")

    class Result:
        stdout = json.dumps({"credential": "pairing-secret"})

    seen: dict[str, Any] = {}

    def run(args: list[str], **_: Any) -> Result:
        seen["scopes"] = [args[i + 1] for i, a in enumerate(args) if a == "--scope"]
        return Result()

    monkeypatch.setattr(mcp.subprocess, "run", run)
    bad_state: list[bool] = [False]

    def post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
        if url.endswith("/register"):
            return {"client_id": "c"}
        seen["decision"] = body["decision"]
        state = "wrong" if bad_state[0] else body["authorization"]["state"]
        return {"redirectTo": f"http://127.0.0.1:1/cb?state={state}&code=abc"}

    monkeypatch.setattr(mcp, "_post_json", post_json)
    token = json.dumps({"access_token": "secret", "expires_in": 60, "scope": "s"})
    monkeypatch.setattr(mcp, "_http", lambda *a, **k: (200, {}, token))

    info = mcp.login("auto")
    assert "access_token" not in info and info["access"] == "auto"
    assert json.loads(config.read_text())["access_token"] == "secret"
    assert seen["decision"]["access"] == "auto"
    assert seen["scopes"] == list(mcp.SCOPES)

    mcp.login("full-access")
    assert seen["scopes"] == list(mcp.FULL_ACCESS_SCOPES)

    bad_state[0] = True
    with pytest.raises(T3Error, match="state didn't match"):
        mcp.login("auto")


def test_pairing_failure_hides_output(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp, "server_origin", lambda: "http://t3")
    monkeypatch.setattr(mcp, "_post_json", lambda *a: {"client_id": "c"})

    class Result:
        stdout = "pairing-secret is not json"

    monkeypatch.setattr(mcp.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(T3Error) as info:
        mcp.login("auto")
    assert "pairing-secret" not in str(info.value)


def rpc_reply(monkeypatch: pytest.MonkeyPatch, result: Any, content_type: str = "json") -> None:
    def fake_http(url: str, data: bytes, headers: dict[str, str], **_: Any) -> Any:
        body = json.loads(data)
        if "id" not in body:
            return 202, {}, ""
        reply = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if content_type == "sse":
            text = f"event: message\ndata: {json.dumps(reply)}\n\n"
            return 200, {"Content-Type": "text/event-stream", "Mcp-Session-Id": "s1"}, text
        return 200, {"Content-Type": "application/json"}, json.dumps(reply)

    monkeypatch.setattr(mcp, "_http", fake_http)


@pytest.mark.parametrize("content_type", ["json", "sse"])
def test_call_reads_structured_and_text_results(
    monkeypatch: pytest.MonkeyPatch, content_type: str
) -> None:
    rpc_reply(monkeypatch, {"structuredContent": {"a": 1}}, content_type)
    assert mcp.McpClient("http://t3", "t").call("tool") == {"a": 1}
    rpc_reply(monkeypatch, {"content": [{"type": "text", "text": '{"b": 2}'}]}, content_type)
    assert mcp.McpClient("http://t3", "t").call("tool") == {"b": 2}


def test_tool_refusal_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc_reply(monkeypatch, {"isError": True, "content": [{"type": "text", "text": "denied"}]})
    with pytest.raises(T3Error, match="T3 refused tool: denied"):
        mcp.McpClient("http://t3", "t").call("tool")


def test_rejected_token_says_to_sign_in_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp, "_http", lambda *a, **k: (401, {}, "{}"))
    with pytest.raises(T3Error, match="t3rig login"):
        mcp.McpClient("http://t3", "t").call("tool")
