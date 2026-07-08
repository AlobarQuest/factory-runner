from __future__ import annotations

import json

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
