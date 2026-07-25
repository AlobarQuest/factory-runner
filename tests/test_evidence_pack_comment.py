"""WS-P2.5 Increment 1: factory-runner relays the evidence-pack markdown onto the PR as
a comment at finalize time. Reuses the FakeClient + monkeypatched `_run_command` harness
already established in tests/test_cli.py (see also tests/test_cost_emit.py, which follows
the same pattern for cost actuals).

The comment is a best-effort projection, never a delivery gate: a fetch failure
(`OrchestratorError`) or a `gh` shell-out failure (`RuntimeError`) must not stop the
terminal `client.submit` call that follows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli import _finalization_authority, _runner_brief
from typer.testing import CliRunner

from factory_runner.cli import app
from factory_runner.client import OrchestratorError
from factory_runner.models import RunnerBrief

_MARKER = "<!-- sds-evidence-pack:unit-1 -->"
_MARKDOWN = "# Evidence Pack\n\nunit-1 acceptance criteria and evidence.\n"
_PR_URL = "https://github.com/AlobarQuest/orchestrator/pull/99"


def _write_finalize_workspace(tmp_path: Path, brief: RunnerBrief) -> None:
    (tmp_path / "brief.json").write_text(brief.model_dump_json())
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "attempt": 1,
                "claim_id": "claim-1",
                "context_snapshot_id": "snapshot-1",
                "lease_token": "lease-redacted",
                "package_revision_id": "rev-1",
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
                **_finalization_authority(tmp_path, brief),
            }
        )
    )


class _RecordingClient:
    """Mirrors the FakeClient shape used across tests/test_cli.py, logging every call (in
    order) to a shared list so this module can assert ordering and best-effort continuation
    directly."""

    evidence_pack_error: Exception | None = None

    def __init__(self, calls: list[tuple[str, dict[str, object]]], **_kwargs: object) -> None:
        self._calls = calls

    def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
        return self._brief

    def list_evidence(self, _unit_id: str) -> list[dict[str, object]]:
        return []

    def pr_binding(self, unit_id: str, **payload: object) -> dict[str, object]:
        self._calls.append(("pr_binding", {"unit_id": unit_id, **payload}))
        return {"pr_number": payload["pr_number"]}

    def get_evidence_pack_markdown(self, unit_id: str) -> str:
        self._calls.append(("get_evidence_pack_markdown", {"unit_id": unit_id}))
        if self.evidence_pack_error is not None:
            raise self.evidence_pack_error
        return _MARKDOWN

    def submit_evidence(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
        self._calls.append(("submit_evidence", {"unit_id": unit_id, "payload": payload}))
        return {"id": "evidence-1"}

    def cost_actuals(self, unit_id: str, **payload: object) -> dict[str, object]:
        self._calls.append(("cost_actuals", {"unit_id": unit_id, **payload}))
        return {}

    def submit(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
        self._calls.append(("submit", {"unit_id": unit_id, **payload}))
        return {"unit_id": unit_id, "state": "submitted", "version": 6}


def _make_client_class(
    brief: RunnerBrief,
    calls: list[tuple[str, dict[str, object]]],
    *,
    evidence_pack_error: Exception | None = None,
) -> type:
    class Client(_RecordingClient):
        evidence_pack_error_ = evidence_pack_error

        def __init__(self, **kwargs: object) -> None:
            super().__init__(calls, **kwargs)
            self._brief = brief
            self.evidence_pack_error = evidence_pack_error

    return Client


def _run_finalize(tmp_path: Path) -> object:
    return CliRunner().invoke(
        app,
        [
            "finalize-run",
            "--orchestrator-url",
            "https://sds.alobar.net",
            "--credential-key-id",
            "factory-runner-github",
            "--work-unit-id",
            "unit-1",
            "--workspace-dir",
            str(tmp_path),
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )


def _base_fake_run_command(command: list[str], **_kwargs: object) -> str:
    if command[:3] == ["git", "status", "--porcelain"]:
        return " M src/example.py\n"
    if command[:3] == ["git", "rev-parse", "HEAD"]:
        return "abc123\n"
    if command[:3] == ["gh", "pr", "create"]:
        return f"{_PR_URL}\n"
    if command[:3] == ["gh", "pr", "view"]:
        return "99\n"
    return ""


def test_finalize_posts_evidence_pack_comment_when_none_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    from factory_runner import cli as cli_module

    def fake_run_command(command: list[str], **kwargs: object) -> str:
        if command[:2] == ["gh", "api"] and command[2].startswith("repos/"):
            # No existing marker comment: the listing call returns an empty array.
            return "[]"
        return _base_fake_run_command(command, **kwargs)

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", fake_run_command)

    result = _run_finalize(tmp_path)

    assert result.exit_code == 0, result.output
    names = [name for name, _ in calls]
    assert names.count("get_evidence_pack_markdown") == 1
    assert names.index("pr_binding") < names.index("get_evidence_pack_markdown")
    assert names.count("submit") == 1


def test_finalize_creates_comment_via_gh_pr_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []
    recorded_commands: list[list[str]] = []

    from factory_runner import cli as cli_module

    def fake_run_command(command: list[str], **kwargs: object) -> str:
        recorded_commands.append(command)
        if command[:2] == ["gh", "api"] and command[2].startswith("repos/"):
            return "[]"
        return _base_fake_run_command(command, **kwargs)

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", fake_run_command)

    result = _run_finalize(tmp_path)

    assert result.exit_code == 0, result.output
    comment_commands = [c for c in recorded_commands if c[:3] == ["gh", "pr", "comment"]]
    assert len(comment_commands) == 1
    command = comment_commands[0]
    assert command[0:3] == ["gh", "pr", "comment"]
    assert command[3] == _PR_URL
    assert command[4] == "--body"
    body = command[5]
    assert _MARKER in body
    assert _MARKDOWN in body


def test_finalize_edits_existing_marker_comment_instead_of_duplicating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []
    recorded_commands: list[list[str]] = []
    existing_comments = json.dumps([{"id": 555, "body": f"{_MARKER}\nstale markdown\n"}])

    from factory_runner import cli as cli_module

    def fake_run_command(command: list[str], **kwargs: object) -> str:
        recorded_commands.append(command)
        if (
            command[:2] == ["gh", "api"]
            and command[2].startswith("repos/")
            and "comments" in command[2]
            and "-X" not in command
        ):
            # the listing call (GET) -- an existing marker comment is already there
            return existing_comments
        return _base_fake_run_command(command, **kwargs)

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", fake_run_command)

    result = _run_finalize(tmp_path)

    assert result.exit_code == 0, result.output
    # No new comment created via `gh pr comment` ...
    comment_commands = [c for c in recorded_commands if c[:3] == ["gh", "pr", "comment"]]
    assert comment_commands == []
    # ... instead the existing marker comment is edited via a PATCH to its id.
    patch_commands = [
        c
        for c in recorded_commands
        if c[:2] == ["gh", "api"]
        and c[2] == "repos/{owner}/{repo}/issues/comments/555"
        and "-X" in c
    ]
    assert len(patch_commands) == 1
    patch_command = patch_commands[0]
    assert patch_command[patch_command.index("-X") + 1] == "PATCH"


def test_finalize_continues_and_submits_when_evidence_pack_fetch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    from factory_runner import cli as cli_module

    monkeypatch.setattr(
        cli_module,
        "OrchestratorClient",
        _make_client_class(
            brief, calls, evidence_pack_error=OrchestratorError("evidence-pack route missing")
        ),
    )
    monkeypatch.setattr(cli_module, "_run_command", _base_fake_run_command)

    result = _run_finalize(tmp_path)

    assert result.exit_code == 0, result.output
    assert "evidence-pack comment skipped" in result.output
    names = [name for name, _ in calls]
    assert names.count("submit") == 1


def test_finalize_continues_and_submits_when_gh_comment_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    from factory_runner import cli as cli_module

    def fake_run_command(command: list[str], **kwargs: object) -> str:
        if command[:2] == ["gh", "api"] and command[2].startswith("repos/"):
            raise RuntimeError("command failed (1): gh api ...")
        return _base_fake_run_command(command, **kwargs)

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", fake_run_command)

    result = _run_finalize(tmp_path)

    assert result.exit_code == 0, result.output
    assert "evidence-pack comment skipped" in result.output
    names = [name for name, _ in calls]
    assert names.count("submit") == 1
