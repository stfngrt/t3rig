"""A thin wrapper over the `t3` command-line tool."""

import json
import subprocess
from typing import Any

TIMEOUT_SECONDS = 60


class T3Error(Exception):
    """A `t3` command failed or couldn't run."""


def _parse_json(output: str) -> Any:
    """Read `--json` output, skipping any log lines `t3` printed to stdout ahead of it."""
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(("{", "[")):
            try:
                return json.loads("\n".join(lines[index:]))
            except ValueError:
                continue
    raise T3Error(f"`t3` didn't return JSON: {output[:200]}")


class T3Cli:
    def __init__(self, executable: str = "t3") -> None:
        self.executable = executable

    def _run(
        self, args: list[str], stdin: str | None = None, timeout: int | None = TIMEOUT_SECONDS
    ) -> str:
        command = [self.executable, *args]
        try:
            result = subprocess.run(
                command, input=stdin, capture_output=True, text=True, timeout=timeout, check=False
            )
        except FileNotFoundError as error:
            raise T3Error(f"can't find `{self.executable}`; is T3 Code installed?") from error
        except subprocess.TimeoutExpired as error:
            raise T3Error(
                f"`{' '.join(args[:2])}` timed out; it may still have taken effect"
            ) from error
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise T3Error(f"`{' '.join(args[:2])}` exited {result.returncode}: {detail}")
        return result.stdout

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        """Threads in the project containing this path, newest first."""
        output = self._run(["thread", "list", "--project", project, "--json"])
        return _parse_json(output)

    def show_thread(self, thread_id: str, messages: int = 1) -> dict[str, Any]:
        """A thread's state under "thread" and its latest messages under "messages"."""
        args = ["thread", "show", "--messages", str(messages), "--json", thread_id]
        return _parse_json(self._run(args))

    def thread_text(self, thread_id: str, messages: int) -> str:
        """`t3 thread show`'s own text for a thread and its latest messages."""
        return self._run(["thread", "show", "--messages", str(messages), thread_id])

    def start_thread(
        self, project: str, title: str, message: str, provider: str | None, model: str | None
    ) -> str:
        args = ["thread", "start", "--title", title]
        if provider and model:
            args += ["--provider", provider, "--model", model]
        return self._run([*args, project, "-"], stdin=message).strip()

    def send(self, thread_id: str, message: str, wait: bool = False) -> str:
        args = ["thread", "send", *(["--wait"] if wait else []), thread_id, "-"]
        return self._run(args, stdin=message, timeout=None if wait else TIMEOUT_SECONDS)
