import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from t3rig import __version__
from t3rig.cli import build_parser, main

EXAMPLE = Path(__file__).parent.parent / "examples" / "two-seat" / "rig.yaml"


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_validate_example(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(EXAMPLE)]) == 0
    assert "two-seat: OK (2 seats, 1 edges)" in capsys.readouterr().out


def test_validate_reports_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rig = tmp_path / "rig.yaml"
    rig.write_text('version: "1"\nname: "bad name"\npods: []\n')
    assert main(["validate", str(rig)]) == 1
    assert "rig.name" in capsys.readouterr().err


def test_send_needs_seat_and_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["send", str(EXAMPLE), "just-a-message"]) == 1
    assert "a seat and a message" in capsys.readouterr().err
    assert main(["send", str(EXAMPLE), "--all", "dev.impl", "hello"]) == 1
    assert "needs a message" in capsys.readouterr().err
    assert main(["send", str(EXAMPLE), "--all", "--wait", "hello"]) == 1
    assert "only works with one seat" in capsys.readouterr().err


def test_log_reports_unknown_seat(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["log", str(EXAMPLE), "dev.nobody"]) == 1
    assert "no seat 'dev.nobody'" in capsys.readouterr().err


def test_log_defaults_to_ten_messages() -> None:
    assert build_parser().parse_args(["log", "rig.yaml", "dev.impl"]).messages == 10
    assert (
        build_parser().parse_args(["log", "rig.yaml", "dev.impl", "--messages", "3"]).messages == 3
    )


def test_log_rejects_fewer_than_one_message_without_calling_t3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    constructed = []

    class FakeT3Cli:
        def __init__(self) -> None:
            constructed.append(self)

        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"shouldn't call t3.{name}")

    monkeypatch.setattr("t3rig.cli.T3Cli", FakeT3Cli)
    assert main(["log", str(EXAMPLE), "dev.impl", "--messages", "0"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "error: --messages must be at least 1\n"
    assert captured.out == ""
    assert len(constructed) == 1  # only the fake; real t3 never ran


SKILLS_EXAMPLE = Path(__file__).parent.parent / "examples" / "skills"


class RecordingT3:
    """Stands in for the t3 CLI: one project, with threads that appear once started."""

    instances: list["RecordingT3"] = []

    def __init__(self) -> None:
        self.threads: list[dict[str, Any]] = []
        self.started: list[str] = []
        RecordingT3.instances.append(self)

    def list_threads(self, project: str) -> list[dict[str, Any]]:
        return list(self.threads)

    def start_thread(self, project, title, message, provider, model) -> str:
        self.started.append(title)
        self.threads.append(
            {
                "threadId": "t1",
                "title": title,
                "status": "idle",
                "providerInstanceId": "claudeAgent",
            }
        )
        return "t1"


@pytest.fixture
def skills_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(SKILLS_EXAMPLE, tmp_path / "skills")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("t3rig.cli.T3Cli", RecordingT3)
    RecordingT3.instances.clear()
    return tmp_path / "skills" / "rig.yaml"


def test_skills_example_validates(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(SKILLS_EXAMPLE / "rig.yaml")]) == 0


def test_up_without_yes_prints_the_plan_and_never_calls_t3(
    skills_rig: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["up", str(skills_rig)]) == 1
    out = capsys.readouterr().out
    assert f"skills in {skills_rig.parent}:" in out
    assert "create  .claude/skills/greeting/  (1 file)  dev.worker" in out
    assert out.endswith(
        "No changes made. Re-run with --yes to apply the skill changes and start the seats.\n"
    )
    assert not (skills_rig.parent / ".claude").exists()
    assert RecordingT3.instances[0].started == []


def test_up_with_yes_installs_then_starts_the_seats(
    skills_rig: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["up", str(skills_rig), "--yes"]) == 0
    out = capsys.readouterr().out
    assert "create  .claude/skills/greeting/" in out and "dev.worker: started t1" in out
    installed = skills_rig.parent / ".claude" / "skills" / "greeting" / "SKILL.md"
    assert "name: greeting" in installed.read_text()
    assert RecordingT3.instances[0].started == ["dev-worker@skills"]


def test_up_with_nothing_to_change_prints_only_the_usual_lines(
    skills_rig: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["up", str(skills_rig), "--yes"]) == 0
    capsys.readouterr()
    RecordingT3.instances.clear()
    assert main(["up", str(skills_rig)]) == 0
    out = capsys.readouterr().out
    assert "skills in" not in out and "dev.worker: started t1" in out


def test_up_refuses_and_starts_nothing_when_a_skill_file_is_hand_written(
    skills_rig: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = skills_rig.parent / ".claude" / "skills" / "greeting" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("mine")
    assert main(["up", str(skills_rig), "--yes"]) == 1
    captured = capsys.readouterr()
    assert "not written by t3rig" in captured.err and captured.out == ""
    assert target.read_text() == "mine"
    assert RecordingT3.instances[0].started == []


def test_down_leaves_installed_skills(skills_rig: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["up", str(skills_rig), "--yes"]) == 0
    assert main(["down", str(skills_rig)]) == 0
    assert (skills_rig.parent / ".claude" / "skills" / "greeting" / "SKILL.md").is_file()


def test_up_without_yes_leaves_no_state_behind(skills_rig: Path, tmp_path: Path) -> None:
    assert main(["up", str(skills_rig)]) == 1
    assert not (tmp_path / "state").exists()


def test_up_stops_before_starting_seats_when_the_record_cant_be_saved(
    skills_rig: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "state" / "t3rig"
    folder.mkdir(parents=True)
    folder.chmod(0o500)
    try:
        if os.access(folder, os.W_OK):
            pytest.skip("permissions aren't enforced (running as root?)")
        assert main(["up", str(skills_rig), "--yes"]) == 1
    finally:
        folder.chmod(0o700)
    assert "can't save t3rig's record" in capsys.readouterr().err
    assert not (skills_rig.parent / ".claude").exists()
    assert RecordingT3.instances[0].started == []


def test_up_prints_notes_when_only_notes_remain_and_still_starts_seats(
    skills_rig: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["up", str(skills_rig), "--yes"]) == 0
    skill = skills_rig.parent / "agents" / "worker" / "skills" / "greeting"
    (skill / "extra.md").write_text("extra")
    assert main(["up", str(skills_rig), "--yes"]) == 0
    (skill / "extra.md").unlink()
    capsys.readouterr()
    assert main(["up", str(skills_rig)]) == 0
    out = capsys.readouterr().out
    assert "extra.md is no longer in source, left in place" in out
    assert "No changes made" not in out and "dev.worker: started" in out
