from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from factory_runner.cli import app
from factory_runner.coding_result import (
    CodingResultError,
    classify_execution_file,
    verify_install_revision,
)


def _write_execution(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "execution.json"
    path.write_text(content)
    return path


def test_classify_execution_file_accepts_one_success_result_in_json_array(tmp_path: Path) -> None:
    path = _write_execution(
        tmp_path,
        json.dumps(
            [
                {"type": "assistant", "message": "not terminal"},
                {"type": "result", "subtype": "success", "is_error": False},
            ]
        ),
    )

    result = classify_execution_file(path)

    assert result.subtype == "success"
    assert result.is_error is False


def test_classify_execution_file_accepts_one_success_result_in_json_lines(tmp_path: Path) -> None:
    path = _write_execution(
        tmp_path,
        '{"type":"assistant"}\n{"type":"result","subtype":"success","is_error":false}\n',
    )

    assert classify_execution_file(path).subtype == "success"


@pytest.mark.parametrize(
    "content",
    [
        '[{"type":"result","subtype":"success"}]',
        '{"type":"result","subtype":"success"}\n',
    ],
    ids=["json-array", "json-lines"],
)
def test_classify_execution_file_rejects_result_without_explicit_is_error(
    tmp_path: Path, content: str
) -> None:
    path = _write_execution(tmp_path, content)

    with pytest.raises(CodingResultError):
        classify_execution_file(path)


@pytest.mark.parametrize(
    "content",
    [
        '[{"type":"result","subtype":"success","is_error":false},{"type":"assistant"}]',
        '{"type":"result","subtype":"success","is_error":false}\n{"type":"assistant"}\n',
    ],
    ids=["json-array", "json-lines"],
)
def test_classify_execution_file_rejects_records_after_result(tmp_path: Path, content: str) -> None:
    path = _write_execution(tmp_path, content)

    with pytest.raises(CodingResultError):
        classify_execution_file(path)


@pytest.mark.parametrize(
    "content",
    [
        '[{"type":"result","subtype":"error_max_turns","is_error":false}]',
        '[{"type":"result","subtype":"success","is_error":true}]',
        "[]",
        '[{"type":"result","subtype":"success","is_error":false},'
        '{"type":"result","subtype":"success","is_error":false}]',
        "not json",
    ],
)
def test_classify_execution_file_rejects_non_single_success_result(
    tmp_path: Path, content: str
) -> None:
    path = _write_execution(tmp_path, content)

    with pytest.raises(CodingResultError) as error:
        classify_execution_file(path)

    assert str(error.value)
    assert content not in str(error.value)


def test_classify_execution_file_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CodingResultError):
        classify_execution_file(tmp_path / "missing.json")


def test_classify_coding_result_cli_does_not_echo_execution_contents(tmp_path: Path) -> None:
    path = _write_execution(tmp_path, '[{"type":"result","subtype":"success","is_error":true}]')

    result = CliRunner().invoke(app, ["classify-coding-result", "--execution-file", str(path)])

    assert result.exit_code == 1
    assert "coding result rejected" in result.output
    assert path.read_text() not in result.output
    assert str(path) not in result.output


def test_classify_coding_result_cli_prints_only_accepted_success(tmp_path: Path) -> None:
    path = _write_execution(tmp_path, '[{"type":"result","subtype":"success","is_error":false}]')

    result = CliRunner().invoke(app, ["classify-coding-result", "--execution-file", str(path)])

    assert result.exit_code == 0
    assert result.output == "coding result accepted: success\n"


class _Distribution:
    def __init__(self, direct_url: str | None) -> None:
        self.direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        assert filename == "direct_url.json"
        return self.direct_url


@pytest.mark.parametrize(
    ("commit_id", "expected", "matches"),
    [
        ("a" * 40, "a" * 40, True),
        ("a" * 7, "a" * 40, False),
        ("b" * 40, "a" * 40, False),
    ],
)
def test_verify_install_revision_requires_exact_vcs_commit(
    monkeypatch: pytest.MonkeyPatch, commit_id: str, expected: str, matches: bool
) -> None:
    from factory_runner import coding_result

    monkeypatch.setattr(
        coding_result.metadata,
        "distribution",
        lambda _name: _Distribution(json.dumps({"vcs_info": {"commit_id": commit_id}})),
    )

    if matches:
        verify_install_revision(expected)
    else:
        with pytest.raises(CodingResultError):
            verify_install_revision(expected)


@pytest.mark.parametrize("direct_url", [None, "{", json.dumps({"url": "file:///tmp/runner"})])
def test_verify_install_revision_rejects_missing_or_non_vcs_metadata(
    monkeypatch: pytest.MonkeyPatch, direct_url: str | None
) -> None:
    from factory_runner import coding_result

    monkeypatch.setattr(
        coding_result.metadata,
        "distribution",
        lambda _name: _Distribution(direct_url),
    )

    with pytest.raises(CodingResultError):
        verify_install_revision("a" * 40)


def test_verify_install_revision_cli_has_bounded_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from factory_runner import coding_result

    monkeypatch.setattr(
        coding_result.metadata,
        "distribution",
        lambda _name: _Distribution(json.dumps({"vcs_info": {"commit_id": "a" * 40}})),
    )

    result = CliRunner().invoke(app, ["verify-install-revision", "--expected", "a" * 40])

    assert result.exit_code == 0
    assert result.output == ""
