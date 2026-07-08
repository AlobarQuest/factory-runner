from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from factory_runner.cli import app
from factory_runner.models import RunnerBrief


def _runner_brief() -> RunnerBrief:
    return RunnerBrief.model_validate(
        {
            "work_unit": {
                "id": "unit-1",
                "state": "ready",
                "version": 3,
                "title": "Do work",
                "outcome": "Work done",
                "required_capability": "repository_write",
                "max_attempts": 3,
            },
            "package": {
                "id": "pkg",
                "revision_id": "rev-1",
                "revision": 1,
                "content_hash": "sha256:abc",
                "source_repository": "AlobarQuest/orchestrator",
                "source_path": "package.yaml",
                "source_commit": "abc123",
            },
            "authority": {
                "fingerprint": "fingerprint",
                "envelope": {
                    "capabilities": {
                        "repo.read": "allowed",
                        "repo.edit": "allowed",
                        "command.run": "allowed",
                        "github.pr.create": "allowed",
                        "orchestrator.claim": "allowed",
                        "orchestrator.evidence.write": "allowed",
                    },
                    "constraints": {
                        "work_unit_id": "unit-1",
                        "target_repository": "AlobarQuest/orchestrator",
                        "allowed_commands": ["make check"],
                        "secret_values": ["redacted"],
                    },
                },
            },
            "acceptance_criteria": [],
            "readiness": {"status": "ready", "reasons": []},
            "target": {"repository": "AlobarQuest/orchestrator"},
            "standing_context": {"context_snapshot_id": "snapshot-1"},
        }
    )


def test_prepare_requires_token_without_printing_value() -> None:
    result = CliRunner().invoke(
        app,
        [
            "prepare",
            "--orchestrator-url",
            "https://sds.alobar.net",
            "--credential-key-id",
            "factory-runner-github",
            "--work-unit-id",
            "unit-1",
            "--current-repository",
            "AlobarQuest/orchestrator",
        ],
        env={},
    )

    assert result.exit_code != 0
    assert "FACTORY_RUNNER_TOKEN" in result.output
    assert "Bearer" not in result.output


def test_prepare_emits_sanitized_json_contract() -> None:
    brief = _runner_brief()
    seen: dict[str, str] = {}

    class FakeClient:
        def __init__(self, *, base_url: str, credential_key_id: str, token: str) -> None:
            seen["base_url"] = base_url
            seen["credential_key_id"] = credential_key_id
            seen["token"] = token

        def get_runner_brief(self, unit_id: str) -> RunnerBrief:
            seen["unit_id"] = unit_id
            return brief

    from factory_runner import cli as cli_module

    original_client = cli_module.OrchestratorClient
    cli_module.OrchestratorClient = FakeClient
    try:
        result = CliRunner().invoke(
            app,
            [
                "prepare",
                "--orchestrator-url",
                "https://sds.alobar.net",
                "--credential-key-id",
                "factory-runner-github",
                "--work-unit-id",
                "unit-1",
                "--current-repository",
                "AlobarQuest/orchestrator",
            ],
            env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
        )
    finally:
        cli_module.OrchestratorClient = original_client

    assert result.exit_code == 0
    assert seen == {
        "base_url": "https://sds.alobar.net",
        "credential_key_id": "factory-runner-github",
        "token": "redacted-token",
        "unit_id": "unit-1",
    }

    payload = json.loads(result.stdout)
    assert payload["allowed_tools"] == ["Read", "Edit", "Bash", "Glob"]
    assert payload["allowed_commands"] == ["make check"]
    assert payload["context_snapshot_id"] == "snapshot-1"
    assert payload["lease_facts"] == {
        "authority_fingerprint": "fingerprint",
        "package_revision_id": "rev-1",
        "target_repository": "AlobarQuest/orchestrator",
        "work_unit_id": "unit-1",
        "work_unit_version": 3,
    }
    constraints = payload["sanitized_brief"]["authority"]["envelope"]["constraints"]
    assert constraints["work_unit_id"] == "unit-1"
    assert "secret_values" not in constraints


def test_prepare_run_claims_starts_and_writes_workspace(tmp_path: Path) -> None:
    brief = _runner_brief()
    calls: list[tuple[str, object]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, credential_key_id: str, token: str) -> None:
            calls.append(("init", (base_url, credential_key_id, token)))

        def get_runner_brief(self, unit_id: str) -> RunnerBrief:
            calls.append(("brief", unit_id))
            return brief

        def claim(
            self,
            unit_id: str,
            *,
            expected_version: int,
            idempotency_key: str,
            standing_context: dict[str, object],
        ) -> dict[str, object]:
            calls.append(("claim", (unit_id, expected_version, idempotency_key, standing_context)))
            return {
                "claim_id": "claim-1",
                "attempt": 1,
                "lease_token": "lease-redacted",
                "expires_at": "2026-07-08T12:00:00Z",
                "context_snapshot_id": "snapshot-1",
            }

        def start(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append(("start", (unit_id, payload)))
            return {"unit_id": unit_id, "state": "executing", "version": 5}

    from factory_runner import cli as cli_module

    original_client = cli_module.OrchestratorClient
    cli_module.OrchestratorClient = FakeClient
    try:
        result = CliRunner().invoke(
            app,
            [
                "prepare-run",
                "--orchestrator-url",
                "https://sds.alobar.net",
                "--credential-key-id",
                "factory-runner-github",
                "--work-unit-id",
                "unit-1",
                "--current-repository",
                "AlobarQuest/orchestrator",
                "--workspace-dir",
                str(tmp_path),
            ],
            env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
        )
    finally:
        cli_module.OrchestratorClient = original_client

    assert result.exit_code == 0, result.output
    assert (tmp_path / "brief.json").exists()
    prompt = (tmp_path / "prompt.md").read_text()
    assert "SDS-Unit: unit-1" in prompt
    assert "SDS-Package-Rev: 1" in prompt
    assert "redacted-token" not in prompt
    manifest = json.loads((tmp_path / "run.json").read_text())
    assert manifest["attempt"] == 1
    assert manifest["lease_token"] == "lease-redacted"
    assert manifest["submit_expected_version"] == 5
    assert calls[1][0] == "brief"
    assert calls[2][0] == "claim"
    assert calls[3][0] == "start"


def test_finalize_run_commits_pr_evidence_and_submits(tmp_path: Path) -> None:
    brief = _runner_brief()
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
                "verification_commands": ["make check"],
                "work_unit_id": "unit-1",
            }
        )
    )
    calls: list[tuple[str, object]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, credential_key_id: str, token: str) -> None:
            calls.append(("init", (base_url, credential_key_id, token)))

        def submit_evidence(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append(("evidence", (unit_id, payload)))
            return {"id": f"evidence-{len(calls)}"}

        def submit(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append(("submit", (unit_id, payload)))
            return {"unit_id": unit_id, "state": "submitted", "version": 6}

    def fake_run(command: list[str], **_kwargs: object) -> str:
        calls.append(("run", command))
        if command[:3] == ["git", "status", "--porcelain"]:
            return " M src/example.py\n"
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "abc123\n"
        if command[:3] == ["gh", "pr", "create"]:
            return "https://github.com/AlobarQuest/orchestrator/pull/99\n"
        return ""

    from factory_runner import cli as cli_module

    original_client = cli_module.OrchestratorClient
    original_run = cli_module._run_command
    cli_module.OrchestratorClient = FakeClient
    cli_module._run_command = fake_run
    try:
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
    finally:
        cli_module.OrchestratorClient = original_client
        cli_module._run_command = original_run

    assert result.exit_code == 0, result.output
    run_commands = [item for name, item in calls if name == "run"]
    assert ["make", "check"] in run_commands
    commit_commands = [
        item for item in run_commands if isinstance(item, list) and item[:2] == ["git", "commit"]
    ]
    assert commit_commands
    commit_message = "\n".join(commit_commands[0])
    assert "SDS-Unit: unit-1" in commit_message
    assert "SDS-Package-Rev: 1" in commit_message
    assert any(name == "evidence" for name, _item in calls)
    assert calls[-1][0] == "submit"
