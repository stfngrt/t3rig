"""Sign in to T3's /mcp endpoint and call its tools, for what the `t3` CLI can't do."""

import base64
import hashlib
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from t3rig.t3 import T3Error

PROTOCOL = "2025-06-18"
TIMEOUT_SECONDS = 60
SCOPES = ("orchestration:read", "orchestration:operate")
# firstmate's docs say T3 refuses a full-access sign-in without these as well.
FULL_ACCESS_SCOPES = (*SCOPES, "settings:write", "source-control:write")
# Most to least restricted. A credential can't launch a thread above its own level.
ACCESS_LEVELS = ("approval-required", "auto-accept-edits", "auto", "full-access")
REDIRECT_URI = "http://127.0.0.1:1/t3rig-callback"  # Never contacted; T3 returns the redirect.


def credential_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "t3rig" / "credentials.json"


def server_origin() -> str:
    path = Path(os.environ.get("T3CODE_HOME") or Path.home() / ".t3") / "userdata"
    try:
        return json.loads((path / "server-runtime.json").read_text())["origin"]
    except (OSError, ValueError, KeyError) as error:
        raise T3Error(f"can't find a running T3 server: {error}") from error


def _http(
    url: str, data: bytes, headers: dict[str, str], timeout: float = TIMEOUT_SECONDS
) -> tuple[int, dict[str, str], str]:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode(errors="replace")
    except OSError as error:
        raise T3Error(f"can't reach T3 at {url}: {error}") from error


def _post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    status, _, text = _http(url, json.dumps(body).encode(), {"content-type": "application/json"})
    if status >= 400:
        path = urllib.parse.urlparse(url).path
        raise T3Error(f"{path} refused with HTTP {status}: {_safe_error(text)}")
    return json.loads(text)


def _safe_error(text: str) -> str:
    """The server's error fields, never a whole body that could echo a secret."""
    try:
        data = json.loads(text)
    except ValueError:
        return "no details"
    fields = [data.get(key) for key in ("error", "error_description", "message")]
    return ": ".join(str(field) for field in fields if field) or "no details"


def _save_credential(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(record, handle, indent=2)
    os.replace(temporary, path)


def login(access: str, t3_executable: str = "t3") -> dict[str, Any]:
    """Approve t3rig as an MCP client with a one-time pairing code. Never prints a secret."""
    origin = server_origin()
    client = _post_json(
        f"{origin}/oauth/mcp/register", {"client_name": "t3rig", "redirect_uris": [REDIRECT_URI]}
    )
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    state = secrets.token_urlsafe(12)
    pairing_args = [t3_executable, "auth", "pairing", "create", "--ttl", "2m", "--json"]
    pairing_args += ["--label", "t3rig-mcp-approval"]
    for scope in FULL_ACCESS_SCOPES if access == "full-access" else SCOPES:
        pairing_args += ["--scope", scope]
    try:
        created = subprocess.run(
            pairing_args, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=True
        )
        code = json.loads(created.stdout)["credential"]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # The pairing output holds a secret, so report only the kind of failure.
        raise T3Error(f"couldn't create a pairing code: {type(error).__name__}") from None

    decision = _post_json(
        f"{origin}/oauth/mcp/decision",
        {
            "authorization": {
                "response_type": "code",
                "client_id": client["client_id"],
                "redirect_uri": REDIRECT_URI,
                "code_challenge": base64.urlsafe_b64encode(digest).rstrip(b"=").decode(),
                "code_challenge_method": "S256",
                "state": state,
                "resource": f"{origin}/mcp",
            },
            "decision": {"_tag": "pairing-code", "access": access, "code": code},
        },
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(decision["redirectTo"]).query)
    if query.get("state") != [state]:
        raise T3Error("sign-in failed: the OAuth state didn't match")
    if "code" not in query:
        raise T3Error(f"sign-in refused: {query.get('error', ['no reason given'])[0]}")
    status, _, text = _http(
        f"{origin}/oauth/mcp/token",
        urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": query["code"][0],
                "redirect_uri": REDIRECT_URI,
                "client_id": client["client_id"],
                "code_verifier": verifier,
                "resource": f"{origin}/mcp",
            }
        ).encode(),
        {"content-type": "application/x-www-form-urlencoded"},
    )
    if status >= 400:
        raise T3Error(f"sign-in failed with HTTP {status}: {_safe_error(text)}")
    token = json.loads(text)
    now = time.time()
    record = {
        "origin": origin,
        "access_token": token["access_token"],
        "access": access,
        "scope": token.get("scope"),
        "issued_at": now,
        "expires_at": now + float(token.get("expires_in", 0)),
    }
    _save_credential(credential_path(), record)
    return {key: value for key, value in record.items() if key != "access_token"}


def load_credential() -> dict[str, Any]:
    path = credential_path()
    try:
        if path.stat().st_mode & 0o077:
            raise T3Error(f"{path} is readable by others; run `chmod 600 {path}`")
        record = json.loads(path.read_text())
    except FileNotFoundError:
        raise T3Error("not signed in to T3's /mcp; run `t3rig login --access <level>`") from None
    except (OSError, ValueError) as error:
        raise T3Error(f"can't read {path}: {error}") from error
    if record.get("expires_at", 0) <= time.time():
        raise T3Error("your T3 sign-in has expired; run `t3rig login` again")
    return record


def _reply_from(text: str, content_type: str, request_id: int) -> dict[str, Any] | None:
    if "text/event-stream" not in content_type:
        reply = json.loads(text)
        return reply if reply.get("id") == request_id else None
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                reply = json.loads(line[5:])
            except ValueError:
                continue
            if reply.get("id") == request_id:
                return reply
    return None


class McpClient:
    def __init__(self, origin: str, token: str) -> None:
        self.url = f"{origin}/mcp"
        self.token = token
        self.session_id: str | None = None
        self.next_id = 1
        self.opened = False

    @classmethod
    def from_credential(cls) -> "McpClient":
        record = load_credential()
        return cls(record["origin"], record["access_token"])

    def _rpc(self, method: str, params: dict[str, Any] | None, notify: bool = False) -> Any:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        request_id = self.next_id
        if not notify:
            body["id"] = request_id
            self.next_id += 1
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "authorization": f"Bearer {self.token}",
            "mcp-protocol-version": PROTOCOL,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        status, response_headers, text = _http(self.url, json.dumps(body).encode(), headers)
        lowered = {key.lower(): value for key, value in response_headers.items()}
        self.session_id = lowered.get("mcp-session-id", self.session_id)
        if status in (401, 403):
            raise T3Error(f"T3 rejected the sign-in (HTTP {status}); run `t3rig login` again")
        if status >= 400:
            raise T3Error(f"T3 {method} failed with HTTP {status}: {_safe_error(text)}")
        if notify:
            return None
        reply = _reply_from(text, lowered.get("content-type", ""), request_id)
        if reply is None:
            raise T3Error(f"T3 returned no reply to {method}")
        if "error" in reply:
            raise T3Error(f"T3 {method} failed: {reply['error'].get('message', 'unknown error')}")
        return reply["result"]

    def _open(self) -> None:
        if not self.opened:
            self._rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "t3rig", "version": "1"},
                },
            )
            self._rpc("notifications/initialized", None, notify=True)
            self.opened = True

    def list_tools(self) -> list[dict[str, Any]]:
        self._open()
        return self._rpc("tools/list", {})["tools"]

    def call(self, tool: str, **arguments: Any) -> Any:
        """Call a tool and return its result. A refusal raises T3Error."""
        self._open()
        result = self._rpc("tools/call", {"name": tool, "arguments": arguments})
        texts = [item.get("text", "") for item in result.get("content", [])]
        if result.get("isError"):
            raise T3Error(f"T3 refused {tool}: {' '.join(texts)[:500]}")
        if "structuredContent" in result:
            return result["structuredContent"]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except ValueError:
            return joined
