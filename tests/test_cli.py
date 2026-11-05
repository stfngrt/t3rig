from pathlib import Path

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
    rig.write_text('version: "0.1"\nname: x\npods: []\n')
    assert main(["validate", str(rig)]) == 1
    assert "rig.version" in capsys.readouterr().err


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
