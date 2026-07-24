"""WS-P2.4: cost actuals are emitted on both the success and failure paths, before the
terminal client.submit / client.fail transition (the lease/claim is still live at that
point -- the cost-actuals route is claim-gated). Reuses the FakeClient + monkeypatched
`_run_command` harness already established in tests/test_cli.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli import _finalization_authority, _runner_brief
from typer.testing import CliRunner

from factory_runner.cli import app
from factory_runner.models import RunnerBrief


def _write_execution_transcript(tmp_path: Path) -> Path:
    path = tmp_path / "execution.jsonl"
    path.write_text(
        json.dumps(
            [
                {"type": "assistant", "message": {}},
                {"type": "assistant", "message": {}},
                {"type": "assistant", "message": {}},
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "num_turns": 7,
                    "total_cost_usd": 1.23,
                    "usage": {"input_tokens": 4000, "output_tokens": 500},
                },
            ]
        )
    )
    return path


def _fake_run_for_finalize(command: list[str], **_kwargs: object) -> str:
    if command[:3] == ["git", "status", "--porcelain"]:
        return " M src/example.py\n"
    if command[:3] == ["git", "rev-parse", "HEAD"]:
        return "abc123\n"
    if command[:3] == ["gh", "pr", "create"]:
        return "https://github.com/AlobarQuest/orchestrator/pull/99\n"
    if command[:3] == ["gh", "pr", "view"]:
        return "99\n"
    return ""


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
    """Mirrors the FakeClient shape used across tests/test_cli.py, but logs every call
    (in order) to a shared list so this module can assert ordering directly."""

    def __init__(self, calls: list[tuple[str, dict[str, object]]], **_kwargs: object) -> None:
        self._calls = calls

    def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
        return self._brief

    def list_evidence(self, _unit_id: str) -> list[dict[str, object]]:
        return []

    def pr_binding(self, unit_id: str, **payload: object) -> dict[str, object]:
        self._calls.append(("pr_binding", {"unit_id": unit_id, **payload}))
        return {"pr_number": payload["pr_number"]}

    def submit_evidence(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
        self._calls.append(("submit_evidence", {"unit_id": unit_id, "payload": payload}))
        return {"id": "evidence-1"}

    def cost_actuals(self, unit_id: str, **payload: object) -> dict[str, object]:
        self._calls.append(("cost_actuals", {"unit_id": unit_id, **payload}))
        return {}

    def submit(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
        self._calls.append(("submit", {"unit_id": unit_id, **payload}))
        return {"unit_id": unit_id, "state": "submitted", "version": 6}


def _make_client_class(brief: RunnerBrief, calls: list[tuple[str, dict[str, object]]]) -> type:
    class Client(_RecordingClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(calls, **kwargs)
            self._brief = brief

    return Client


def test_finalize_run_emits_cost_actuals_before_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    execution_file = _write_execution_transcript(tmp_path)
    calls: list[tuple[str, dict[str, object]]] = []

    from factory_runner import cli as cli_module

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", _fake_run_for_finalize)

    result = CliRunner().invoke(
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
            "--execution-file",
            str(execution_file),
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code == 0, result.output
    names = [name for name, _ in calls]
    assert names.count("cost_actuals") == 1
    assert names.index("cost_actuals") < names.index("submit")

    cost_call = next(payload for name, payload in calls if name == "cost_actuals")
    assert cost_call["unit_id"] == "unit-1"
    assert cost_call["attempt"] == 1
    assert cost_call["lease_token"] == "lease-redacted"
    assert cost_call["cost_known"] is True
    assert cost_call["llm_calls"] == 3
    assert cost_call["num_turns"] == 7
    assert cost_call["input_tokens"] == 4000
    assert cost_call["output_tokens"] == 500
    assert cost_call["cost_usd"] == 1.23
    assert cost_call["idempotency_key"] == "factory-runner:unit-1:cost:a1"


def test_finalize_run_emits_unknown_cost_without_execution_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    from factory_runner import cli as cli_module

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", _fake_run_for_finalize)

    result = CliRunner().invoke(
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

    assert result.exit_code == 0, result.output
    cost_call = next(payload for name, payload in calls if name == "cost_actuals")
    assert cost_call["cost_known"] is False
    assert cost_call["llm_calls"] is None
    assert cost_call["num_turns"] is None
    assert cost_call["input_tokens"] is None
    assert cost_call["output_tokens"] is None
    assert cost_call["cost_usd"] is None


def test_finalize_run_emits_unknown_cost_when_execution_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    _write_finalize_workspace(tmp_path, brief)
    calls: list[tuple[str, dict[str, object]]] = []

    from factory_runner import cli as cli_module

    monkeypatch.setattr(cli_module, "OrchestratorClient", _make_client_class(brief, calls))
    monkeypatch.setattr(cli_module, "_run_command", _fake_run_for_finalize)

    result = CliRunner().invoke(
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
            "--execution-file",
            str(tmp_path / "does-not-exist.jsonl"),
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code == 0, result.output
    cost_call = next(payload for name, payload in calls if name == "cost_actuals")
    assert cost_call["cost_known"] is False


def test_fail_run_emits_cost_actuals_before_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    execution_file = _write_execution_transcript(tmp_path)
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def cost_actuals(self, unit_id: str, **payload: object) -> dict[str, object]:
            calls.append(("cost_actuals", {"unit_id": unit_id, **payload}))
            return {}

        def fail(self, unit_id: str, **payload: object) -> dict[str, object]:
            calls.append(("fail", {"unit_id": unit_id, **payload}))
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
            str(execution_file),
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code == 0, result.output
    names = [name for name, _ in calls]
    assert names.count("cost_actuals") == 1
    assert names.count("fail") == 1
    assert names.index("cost_actuals") < names.index("fail")

    cost_call = next(payload for name, payload in calls if name == "cost_actuals")
    assert cost_call["attempt"] == 2
    assert cost_call["lease_token"] == "lease-redacted"
    assert cost_call["cost_known"] is True
    assert cost_call["llm_calls"] == 3
    assert cost_call["idempotency_key"] == "factory-runner:unit-1:cost:a2"


def test_fail_run_emits_unknown_cost_without_execution_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "attempt": 1,
                "lease_token": "lease-redacted",
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
            }
        )
    )
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def cost_actuals(self, unit_id: str, **payload: object) -> dict[str, object]:
            calls.append(("cost_actuals", {"unit_id": unit_id, **payload}))
            return {}

        def fail(self, unit_id: str, **payload: object) -> dict[str, object]:
            calls.append(("fail", {"unit_id": unit_id, **payload}))
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
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code == 0, result.output
    cost_call = next(payload for name, payload in calls if name == "cost_actuals")
    assert cost_call["cost_known"] is False
    assert cost_call["llm_calls"] is None
    assert cost_call["cost_usd"] is None
