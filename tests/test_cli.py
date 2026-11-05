from pathlib import Path

import pytest

from openrigt3 import __version__
from openrigt3.cli import main

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
