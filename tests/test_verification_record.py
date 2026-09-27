"""What finalize reports about the commands it ran, and what a best-effort call may not kill.

The verification list rides inside the `runner.pr.opened` evidence payload and the PR body.
It used to label every entry `passed`, mutators included, so a dependency update's evidence
read `uv lock --upgrade: passed` -- a claim of verification about a command that verifies
nothing. A command the envelope names in `constraints.mutation_commands` is now reported as
`applied`. The payload's shape is unchanged: `summary` was already free text, and the
orchestrator reads no field of this list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from test_cli import _runner_brief
from test_cost_emit import (
    _fake_run_for_finalize,
    _make_client_class,
    _write_execution_transcript,
    _write_finalize_workspace,
)
from typer.testing import CliRunner

from factory_runner.cli import app

_FINALIZE_ARGS = [
    "finalize-run",
    "--orchestrator-url",
    "https://sds.alobar.net",
    "--credential-key-id",
    "factory-runner-github",
    "--work-unit-id",
    "unit-1",
]
_ENV = {"FACTORY_RUNNER_TOKEN": "redacted-token", "GITHUB_TOKEN": "push-token-redacted"}


def _finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client_class: type
) -> tuple[Any, list[list[str]]]:
    from factory_runner import cli as cli_module

    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> str:
        commands.append(command)
        return _fake_run_for_finalize(command, **kwargs)

    monkeypatch.setattr(cli_module, "OrchestratorClient", client_class)
    monkeypatch.setattr(cli_module, "_run_command", run)
    result = CliRunner().invoke(app, [*_FINALIZE_ARGS, "--workspace-dir", str(tmp_path)], env=_ENV)
    return result, commands


def test_a_mutation_command_is_reported_as_applied_not_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    brief.authority.envelope.constraints["allowed_commands"] = ["uv lock --upgrade", "make check"]
    brief.authority.envelope.constraints["mutation_commands"] = ["uv lock --upgrade"]
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    result, commands = _finalize(tmp_path, monkeypatch, _make_client_class(brief, calls))

    assert result.exit_code == 0, result.output
    evidence = next(payload for name, payload in calls if name == "submit_evidence")
    verification = cast("dict[str, Any]", evidence["payload"])["payload"]["verification"]
    assert [(entry["command"], entry["exit_code"], entry["summary"]) for entry in verification] == [
        ("uv lock --upgrade", 0, "applied"),
        ("make check", 0, "passed"),
    ]
    pr_body = next(command for command in commands if command[:3] == ["gh", "pr", "create"])[-1]
    assert "- uv lock --upgrade: applied" in pr_body
    assert "- make check: passed" in pr_body


def test_an_edit_shaped_envelope_reports_every_command_as_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No mutation_commands means the coding agent produced the diff; every command verifies."""
    brief = _runner_brief()
    brief.authority.envelope.constraints["change_class"] = "maintenance-remediation"
    brief.authority.envelope.constraints["allowed_commands"] = ["uv sync", "make check"]
    brief.authority.envelope.constraints.pop("mutation_commands", None)
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    result, _commands = _finalize(tmp_path, monkeypatch, _make_client_class(brief, calls))

    assert result.exit_code == 0, result.output
    evidence = next(payload for name, payload in calls if name == "submit_evidence")
    verification = cast("dict[str, Any]", evidence["payload"])["payload"]["verification"]
    assert [entry["summary"] for entry in verification] == ["passed", "passed"]


def test_an_exhausted_transport_error_on_the_evidence_pack_comment_does_not_stop_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The comment is a projection, never a delivery gate; the client now re-raises the
    original httpx error after its retry budget, which the old `except` did not catch."""
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []
    base = _make_client_class(brief, calls)

    class Client(base):
        def get_evidence_pack_markdown(self, unit_id: str) -> str:
            raise httpx.ConnectError("orchestrator unreachable")

    result, _commands = _finalize(tmp_path, monkeypatch, Client)

    assert result.exit_code == 0, result.output
    assert [name for name, _ in calls][-1] == "submit"


def test_an_exhausted_transport_error_on_cost_actuals_does_not_stop_fail_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise the one call that reports the failure never runs, and the unit strands."""
    import json

    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "attempt": 2,
                "lease_token": "lease-redacted",
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
            }
        )
    )
    calls: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def cost_actuals(self, unit_id: str, **payload: object) -> dict[str, object]:
            calls.append("cost_actuals")
            raise httpx.ConnectError("orchestrator unreachable")

        def fail(self, unit_id: str, **payload: object) -> dict[str, object]:
            calls.append("fail")
            return {"unit_id": unit_id, "state": "failed", "version": 6}

    from factory_runner import cli as cli_module

    monkeypatch.setattr(cli_module, "OrchestratorClient", FakeClient)
    result = CliRunner().invoke(
        app,
        [
            "fail-run",
            "--orchestrator-url",
            "https://sds.alobar.net",
            "--credential-key-id",
            "factory-runner-github",
            "--work-unit-id",
            "unit-1",
            "--workspace-dir",
            str(tmp_path),
            "--reason",
            "coding_action_failed",
            "--execution-file",
            str(_write_execution_transcript(tmp_path)),
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code == 0, result.output
    assert calls == ["cost_actuals", "fail"]
