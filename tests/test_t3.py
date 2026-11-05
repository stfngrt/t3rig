import pytest

from t3rig.t3 import T3Error, _parse_json

LOG = """[17:50:14.247] WARN (#20): Database migration history diverges. {
  divergent: [
    '77:Repair (unknown to this build)'
  ]
}
"""


def test_plain_json() -> None:
    assert _parse_json('[{"a": 1}]') == [{"a": 1}]


def test_skips_log_lines_ahead_of_the_json() -> None:
    assert _parse_json(LOG + '[{"a": 1}]\n') == [{"a": 1}]
    assert _parse_json(LOG + '{\n  "a": 1\n}\n') == {"a": 1}


def test_output_without_json_is_a_clear_error() -> None:
    with pytest.raises(T3Error, match="didn't return JSON"):
        _parse_json(LOG)
