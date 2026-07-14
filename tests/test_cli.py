from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from factory_runner.cli import app
from factory_runner.client import OrchestratorClient
from factory_runner.command_policy import write_tool_policy
from factory_runner.models import RunnerBrief


def _tool_policy(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    policy, _settings = write_tool_policy(
        tmp_path.with_name(f"{tmp_path.name}-policy"),
        checkout,
        ("uv sync --locked",),
        "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
        edit_allowed=True,
    )
    return policy


def _finalization_authority(tmp_path: Path, brief: RunnerBrief) -> dict[str, object]:
    from factory_runner.command_policy import policy_digest

    policy, _settings = write_tool_policy(
        tmp_path.with_name(f"{tmp_path.name}-policy"),
        Path.cwd(),
        tuple(brief.authority.envelope.constraints["allowed_commands"]),
        brief.authority.fingerprint,
        edit_allowed=True,
        protected_paths=(tmp_path,),
    )
    return {
        "authority_fingerprint": brief.authority.fingerprint,
        "checkout_root": str(Path.cwd().resolve()),
        "policy_digest": policy_digest(
            fingerprint=brief.authority.fingerprint,
            allowed_commands=tuple(brief.authority.envelope.constraints["allowed_commands"]),
            checkout=Path.cwd(),
            edit_allowed=True,
            protected_paths=(tmp_path,),
        ),
        "policy_file": str(policy),
    }


def test_authorize_tool_cli_allows_exact_bash_and_contained_edit(tmp_path: Path) -> None:
    policy = _tool_policy(tmp_path)
    edit_target = tmp_path / "checkout" / "file.py"
    edit_target.write_text("x = 1\n")

    for hook_input in (
        {"tool_name": "Bash", "tool_input": {"command": "uv sync --locked"}},
        {"tool_name": "Edit", "tool_input": {"file_path": str(edit_target)}},
    ):
        result = CliRunner().invoke(
            app,
            ["authorize-tool", "--policy-file", str(policy)],
            input=json.dumps(hook_input),
        )
        assert result.exit_code == 0, result.output
        assert result.output == ""


@pytest.mark.parametrize(
    "hook_input",
    [
        {"tool_name": "Bash", "tool_input": {"command": "uv sync --locked; whoami"}},
        {"tool_name": "Edit", "tool_input": {"file_path": "../outside.txt"}},
        {"tool_name": "Read", "tool_input": {"file_path": "README.md"}},
        {"tool_name": "Bash", "tool_input": {}},
    ],
)
def test_authorize_tool_cli_denies_with_exit_two_and_bounded_stderr(
    tmp_path: Path, hook_input: dict[str, object]
) -> None:
    policy = _tool_policy(tmp_path)

    result = CliRunner().invoke(
        app,
        ["authorize-tool", "--policy-file", str(policy)],
        input=json.dumps(hook_input),
    )

    assert result.exit_code == 2
    assert len(result.stderr) < 200
    assert "uv sync" not in result.stderr


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
                "fingerprint": "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
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
                        "mutation_commands": ["make check"],
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
        "authority_fingerprint": "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
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
    assert "Work unit: unit-1" in prompt
    assert "Package: pkg revision 1" in prompt
    # The trailers belong to the runner's own commit, not to the agent's. Asking the agent
    # for them told it to commit, which left a clean tree finalize refused to submit.
    assert "SDS-Unit: unit-1" not in prompt
    assert "redacted-token" not in prompt
    manifest = json.loads((tmp_path / "run.json").read_text())
    assert manifest["attempt"] == 1
    assert manifest["lease_token"] == "lease-redacted"
    assert manifest["submit_expected_version"] == 5
    assert manifest["base_sha"]
    assert manifest["checkout_root"] == str(Path.cwd().resolve())
    assert manifest["authority_fingerprint"] == brief.authority.fingerprint
    assert manifest["policy_digest"]
    assert "verification_commands" not in manifest
    policy = Path(manifest["policy_file"])
    assert policy.is_file()
    assert policy.is_relative_to(tmp_path.resolve())
    assert policy.is_relative_to(Path.cwd().resolve()) is False
    assert json.loads(policy.read_text())["protected_paths"] == [str(tmp_path.resolve())]
    settings = Path(manifest["settings_file"])
    assert settings.is_file()
    assert calls[1][0] == "brief"
    assert calls[2][0] == "claim"
    assert calls[3][0] == "start"


def test_prepare_run_emits_generated_settings_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

        def claim(self, _unit_id: str, **_kwargs: object) -> dict[str, object]:
            return {"attempt": 1, "claim_id": "claim-1", "lease_token": "lease", "expires_at": None}

        def start(self, _unit_id: str, _payload: dict[str, object]) -> dict[str, object]:
            return {"version": 5}

    from factory_runner import cli as cli_module

    monkeypatch.setattr(cli_module, "OrchestratorClient", FakeClient)
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
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
            str(tmp_path / "workspace"),
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code == 0, result.output
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert Path(values["settings_file"]).is_file()
    assert values["allowed_tools"] == "Read,Edit,Bash,Glob"


def test_policy_directory_moves_outside_an_in_checkout_workspace(tmp_path: Path) -> None:
    from factory_runner.cli import _policy_directory

    checkout = tmp_path / "checkout"
    workspace = checkout / ".factory-runner"
    checkout.mkdir()

    policy_dir = _policy_directory(workspace, checkout)

    assert policy_dir.is_relative_to(checkout) is False


def test_finalize_replays_refreshed_commands_in_order_with_bash_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _runner_brief()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    policy, _settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        ("uv run python -c \"print('quoted')\"", "uv sync --locked", "uv sync --locked"),
        brief.authority.fingerprint,
        edit_allowed=True,
        protected_paths=(tmp_path,),
    )
    brief.authority.envelope.constraints["allowed_commands"] = [
        "uv run python -c \"print('quoted')\"",
        "uv sync --locked",
        "uv sync --locked",
    ]
    brief.authority.envelope.constraints["mutation_commands"] = [
        "uv run python -c \"print('quoted')\"",
        "uv sync --locked",
        "uv sync --locked",
    ]
    from factory_runner.command_policy import policy_digest

    (tmp_path / "brief.json").write_text(brief.model_dump_json())
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "attempt": 1,
                "authority_fingerprint": brief.authority.fingerprint,
                "base_sha": "base",
                "checkout_root": str(checkout),
                "context_snapshot_id": None,
                "lease_token": "lease-redacted",
                "package_revision_id": "rev-1",
                "policy_digest": policy_digest(
                    fingerprint=brief.authority.fingerprint,
                    allowed_commands=(
                        "uv run python -c \"print('quoted')\"",
                        "uv sync --locked",
                        "uv sync --locked",
                    ),
                    checkout=checkout,
                    edit_allowed=True,
                    protected_paths=(tmp_path,),
                ),
                "policy_file": str(policy),
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
            }
        )
    )
    calls: list[list[str]] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

        def list_evidence(self, _unit_id: str) -> list[dict[str, object]]:
            return []

        def submit_evidence(self, _unit_id: str, _payload: dict[str, object]) -> dict[str, object]:
            return {"id": "evidence-1"}

        def submit(self, _unit_id: str, _payload: dict[str, object]) -> dict[str, object]:
            return {"version": 6}

    def fake_run(command: list[str], **_kwargs: object) -> str:
        calls.append(command)
        if command[:3] == ["git", "status", "--porcelain"]:
            return " M file.py\n"
        if command[:3] == ["gh", "pr", "create"]:
            return "https://github.com/AlobarQuest/orchestrator/pull/99\n"
        return "head\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""

    from factory_runner import cli as cli_module

    monkeypatch.chdir(checkout)
    monkeypatch.setattr(cli_module, "OrchestratorClient", FakeClient)
    monkeypatch.setattr(cli_module, "_run_command", fake_run)
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
    bash_calls = [command for command in calls if command[0] == "/bin/bash"]
    assert bash_calls == [
        ["/bin/bash", "--noprofile", "--norc", "-euo", "pipefail", "-c", command]
        for command in (
            "uv run python -c \"print('quoted')\"",
            "uv sync --locked",
            "uv sync --locked",
        )
    ]


def test_finalize_stops_before_commands_when_refreshed_authority_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _runner_brief()
    refreshed = _runner_brief()
    refreshed.authority.fingerprint = "f" * 64
    (tmp_path / "brief.json").write_text(saved.model_dump_json())
    (tmp_path / "run.json").write_text(
        json.dumps({"authority_fingerprint": saved.authority.fingerprint, "work_unit_id": "unit-1"})
    )
    commands: list[list[str]] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return refreshed

    from factory_runner import cli as cli_module

    monkeypatch.setattr(cli_module, "OrchestratorClient", FakeClient)
    monkeypatch.setattr(
        cli_module, "_run_command", lambda command, **_kwargs: commands.append(command)
    )
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

    assert result.exit_code == 1
    assert "authority fingerprint changed" in result.output
    assert commands == []


def test_refreshed_authority_replay_is_stable_and_preserves_duplicates(tmp_path: Path) -> None:
    brief = _runner_brief()
    brief.authority.envelope.constraints["allowed_commands"] = [
        "uv sync --locked",
        "uv sync --locked",
    ]
    brief.authority.envelope.constraints["mutation_commands"] = ["uv sync --locked"]
    run = _finalization_authority(tmp_path, brief)

    class FakeClient:
        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

    from factory_runner.cli import _refreshed_verification_commands

    first = _refreshed_verification_commands(
        client=cast(OrchestratorClient, FakeClient()),
        work_unit_id="unit-1",
        run=run,
        checkout=Path.cwd(),
        protected_paths=(tmp_path,),
    )
    second = _refreshed_verification_commands(
        client=cast(OrchestratorClient, FakeClient()),
        work_unit_id="unit-1",
        run=run,
        checkout=Path.cwd(),
        protected_paths=(tmp_path,),
    )

    assert first == second == ("uv sync --locked", "uv sync --locked")


def test_exact_bash_execution_preserves_shell_quoting_for_uv(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    bin_dir = checkout / "bin"
    bin_dir.mkdir(parents=True)
    captured = tmp_path / "uv-args.txt"
    uv = bin_dir / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURED_ARGS"\n')
    uv.chmod(0o755)
    environment = os.environ.copy()
    environment["CAPTURED_ARGS"] = str(captured)
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"

    from factory_runner.cli import _run_command

    _run_command(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-euo",
            "pipefail",
            "-c",
            "uv run python -c 'print(\"quoted\")'",
        ],
        cwd=checkout,
        env=environment,
    )

    assert captured.read_text().splitlines() == ["run", "python", "-c", 'print("quoted")']


@pytest.mark.parametrize("venv_exists", [True, False])
def test_finalize_run_commits_pr_evidence_and_submits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, venv_exists: bool
) -> None:
    brief = _runner_brief()
    monkeypatch.chdir(tmp_path)
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
    calls: list[tuple[str, object]] = []
    run_calls: list[tuple[list[str], dict[str, object]]] = []
    venv_bin = tmp_path / ".venv" / "bin"
    if venv_exists:
        venv_bin.mkdir(parents=True)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    class FakeClient:
        def __init__(self, *, base_url: str, credential_key_id: str, token: str) -> None:
            calls.append(("init", (base_url, credential_key_id, token)))

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

        def list_evidence(self, unit_id: str) -> list[dict[str, object]]:
            calls.append(("list_evidence", unit_id))
            return []

        def submit_evidence(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append(("evidence", (unit_id, payload)))
            return {"id": f"evidence-{len(calls)}"}

        def submit(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append(("submit", (unit_id, payload)))
            return {"unit_id": unit_id, "state": "submitted", "version": 6}

    def fake_run(command: list[str], **kwargs: object) -> str:
        calls.append(("run", command))
        run_calls.append((command, kwargs))
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
    verification_call = next(call for call in run_calls if call[0][-1] == "make check")
    verification_environment = cast("dict[str, str]", verification_call[1]["env"])
    expected_path = f"{venv_bin}:/usr/bin:/bin" if venv_exists else "/usr/bin:/bin"
    assert verification_environment["PATH"] == expected_path
    assert all(
        "env" not in kwargs for command, kwargs in run_calls if command != verification_call[0]
    )
    run_commands = [item for name, item in calls if name == "run"]
    assert [
        "/bin/bash",
        "--noprofile",
        "--norc",
        "-euo",
        "pipefail",
        "-c",
        "make check",
    ] in run_commands
    commit_commands = [item for item in run_commands if isinstance(item, list) and "commit" in item]
    assert commit_commands
    commit_message = "\n".join(commit_commands[0])
    assert "SDS-Unit: unit-1" in commit_message
    assert "SDS-Package-Rev: 1" in commit_message
    # Exactly one evidence submission: the orchestrator keys current evidence on ac_id, so
    # a second row for the same AC is a 409. Verification rides inside the PR payload.
    evidence_calls = [item for name, item in calls if name == "evidence"]
    assert len(evidence_calls) == 1, f"expected one evidence submission, got {len(evidence_calls)}"
    evidence_payload = cast("tuple[str, dict[str, Any]]", evidence_calls[0])[1]
    assert evidence_payload["evidence_type"] == "runner.pr.opened"
    assert "verification" in evidence_payload["payload"]
    # No prior evidence (list_evidence -> []), so this is a first-write, not a supersede.
    assert evidence_payload["supersede"] is False
    assert any(name == "list_evidence" for name, _ in calls)
    assert calls[-1][0] == "submit"


def test_finalize_run_supersedes_when_prior_evidence_exists(tmp_path: Path) -> None:
    """A retry after a partial-success earlier attempt must supersede the evidence that
    attempt left behind, or the orchestrator rejects the re-post with evidence_already_exists.
    """
    from factory_runner.cli import _first_ac_id

    brief = _runner_brief()
    ac_id = _first_ac_id(brief)
    (tmp_path / "brief.json").write_text(brief.model_dump_json())
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "attempt": 2,
                "claim_id": "claim-2",
                "context_snapshot_id": "snapshot-1",
                "lease_token": "lease-redacted",
                "package_revision_id": "rev-1",
                "submit_expected_version": 9,
                "work_unit_id": "unit-1",
                **_finalization_authority(tmp_path, brief),
            }
        )
    )
    submitted: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **_: object) -> None: ...

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

        def list_evidence(self, unit_id: str) -> list[dict[str, object]]:
            # A row from a prior attempt, same AC.
            return [{"id": "prior", "ac_id": ac_id, "evidence_type": "runner.pr.opened"}]

        def submit_evidence(self, unit_id: str, payload: dict[str, Any]) -> dict[str, object]:
            submitted.update(payload)
            return {"id": "evidence-2"}

        def submit(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            return {"unit_id": unit_id, "state": "submitted", "version": 10}

    def fake_run(command: list[str], **_kwargs: object) -> str:
        if command[:3] == ["git", "status", "--porcelain"]:
            return " M uv.lock\n"
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "def456\n"
        if command[:3] == ["gh", "pr", "create"]:
            return "https://github.com/AlobarQuest/orchestrator/pull/100\n"
        return ""

    from factory_runner import cli as cli_module

    original_client, original_run = cli_module.OrchestratorClient, cli_module._run_command
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
    assert submitted["supersede"] is True


def test_fail_run_reports_bounded_failure_from_workspace(
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
    calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def fail(self, unit_id: str, **payload: object) -> dict[str, object]:
            calls.append({"unit_id": unit_id, **payload})
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
    assert calls == [
        {
            "unit_id": "unit-1",
            "expected_version": 5,
            "idempotency_key": "factory-runner:unit-1:fail:a1:coding_action_failed",
            "attempt": 1,
            "lease_token": "lease-redacted",
            "reason": "coding_action_failed",
        }
    ]
    assert result.output == "failed work unit unit-1 attempt 1\n"
    assert "lease-redacted" not in result.output


@pytest.mark.parametrize(
    ("run", "reason", "expected_message"),
    [
        (
            {
                "attempt": 1,
                "lease_token": "lease-redacted",
                "submit_expected_version": 5,
                "work_unit_id": "unit-2",
            },
            "coding_action_failed",
            "workspace work unit mismatch",
        ),
        (
            {
                "attempt": 1,
                "lease_token": "lease-redacted",
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
            },
            "not_a_failure_reason",
            "Invalid value",
        ),
    ],
)
def test_fail_run_rejects_invalid_local_input_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run: dict[str, object],
    reason: str,
    expected_message: str,
) -> None:
    (tmp_path / "run.json").write_text(json.dumps(run))
    mutations: list[object] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def fail(self, unit_id: str, **payload: object) -> dict[str, object]:
            mutations.append((unit_id, payload))
            return {}

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
            reason,
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code != 0
    assert expected_message in result.output
    assert mutations == []


def test_fail_run_rejects_missing_workspace_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutations: list[object] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def fail(self, unit_id: str, **payload: object) -> dict[str, object]:
            mutations.append((unit_id, payload))
            return {}

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
            "finalization_failed",
        ],
        env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
    )

    assert result.exit_code != 0
    assert "run.json" in result.output
    assert mutations == []


def test_local_heavy_prepare_writes_sanitized_workspace(tmp_path: Path) -> None:
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
                "local-heavy-prepare",
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
    assert "local-heavy prepared work unit unit-1 attempt 1" in result.output
    assert "lease-redacted" not in result.output
    assert "redacted-token" not in result.output
    manifest = json.loads((tmp_path / "run.json").read_text())
    assert manifest["runtime"] == "local-heavy"
    assert manifest["lease_token"] == "lease-redacted"
    brief_payload = json.loads((tmp_path / "brief.json").read_text())
    assert "secret_values" not in brief_payload["authority"]["envelope"]["constraints"]
    prompt = (tmp_path / "prompt.md").read_text()
    assert "Local-Heavy Runtime Work Unit" in prompt
    assert "Do not merge pull requests" in prompt


def test_local_heavy_renew_updates_workspace_without_printing_lease(tmp_path: Path) -> None:
    brief = _runner_brief()
    (tmp_path / "brief.json").write_text(brief.model_dump_json())
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "attempt": 2,
                "claim_id": "claim-1",
                "context_snapshot_id": "snapshot-1",
                "lease_token": "lease-redacted",
                "package_revision_id": "rev-1",
                "runtime": "local-heavy",
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
                **_finalization_authority(tmp_path, brief),
            }
        )
    )
    calls: list[tuple[str, object]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, credential_key_id: str, token: str) -> None:
            calls.append(("init", (base_url, credential_key_id, token)))

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

        def renew(
            self,
            unit_id: str,
            *,
            attempt: int,
            lease_token: str,
            idempotency_key: str,
            expected_version: int | None = None,
        ) -> dict[str, object]:
            calls.append(
                ("renew", (unit_id, attempt, lease_token, idempotency_key, expected_version))
            )
            return {
                "claim_id": "claim-1",
                "attempt": attempt,
                "lease_token": "",
                "expires_at": "2026-07-08T12:15:00Z",
                "context_snapshot_id": "snapshot-1",
            }

    from factory_runner import cli as cli_module

    original_client = cli_module.OrchestratorClient
    cli_module.OrchestratorClient = FakeClient
    try:
        result = CliRunner().invoke(
            app,
            [
                "local-heavy-renew",
                "--orchestrator-url",
                "https://sds.alobar.net",
                "--credential-key-id",
                "factory-runner-github",
                "--work-unit-id",
                "unit-1",
                "--workspace-dir",
                str(tmp_path),
                "--idempotency-key",
                "local-heavy:unit-1:renew:a2",
            ],
            env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
        )
    finally:
        cli_module.OrchestratorClient = original_client

    assert result.exit_code == 0, result.output
    assert "renewed local-heavy lease for unit-1" in result.output
    assert "lease-redacted" not in result.output
    manifest = json.loads((tmp_path / "run.json").read_text())
    assert manifest["lease_token"] == "lease-redacted"
    assert manifest["lease_expires_at"] == "2026-07-08T12:15:00Z"
    assert calls[1] == (
        "renew",
        ("unit-1", 2, "lease-redacted", "local-heavy:unit-1:renew:a2", None),
    )


def test_local_heavy_reclaim_uses_orchestrator_reclaim_api(tmp_path: Path) -> None:
    brief = _runner_brief()
    calls: list[tuple[str, object]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, credential_key_id: str, token: str) -> None:
            calls.append(("init", (base_url, credential_key_id, token)))

        def get_runner_brief(self, unit_id: str) -> RunnerBrief:
            calls.append(("brief", unit_id))
            return brief

        def reclaim_expired_claim(
            self,
            unit_id: str,
            *,
            next_owner_id: str,
            idempotency_key: str,
            expected_version: int | None = None,
            standing_context: dict[str, object] | None = None,
        ) -> dict[str, object]:
            calls.append(
                (
                    "reclaim",
                    (unit_id, next_owner_id, idempotency_key, expected_version, standing_context),
                )
            )
            return {
                "claim_id": "claim-2",
                "attempt": 3,
                "lease_token": "new-lease-redacted",
                "expires_at": "2026-07-08T12:30:00Z",
                "context_snapshot_id": "snapshot-2",
            }

    from factory_runner import cli as cli_module

    original_client = cli_module.OrchestratorClient
    cli_module.OrchestratorClient = FakeClient
    try:
        result = CliRunner().invoke(
            app,
            [
                "local-heavy-reclaim",
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
                "--next-owner-id",
                "factory-runner",
                "--idempotency-key",
                "local-heavy:unit-1:reclaim",
            ],
            env={"FACTORY_RUNNER_TOKEN": "redacted-token"},
        )
    finally:
        cli_module.OrchestratorClient = original_client

    assert result.exit_code == 0, result.output
    assert "reclaimed local-heavy lease for unit-1 attempt 3" in result.output
    assert "new-lease-redacted" not in result.output
    manifest = json.loads((tmp_path / "run.json").read_text())
    assert manifest["runtime"] == "local-heavy"
    assert manifest["attempt"] == 3
    assert manifest["lease_token"] == "new-lease-redacted"
    assert calls[2] == (
        "reclaim",
        (
            "unit-1",
            "factory-runner",
            "local-heavy:unit-1:reclaim",
            None,
            {"context_snapshot_id": "snapshot-1"},
        ),
    )


def test_local_heavy_finalize_submits_evidence_without_leaking_lease(tmp_path: Path) -> None:
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
                "runtime": "local-heavy",
                "submit_expected_version": 5,
                "work_unit_id": "unit-1",
                **_finalization_authority(tmp_path, brief),
            }
        )
    )
    calls: list[tuple[str, object]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, credential_key_id: str, token: str) -> None:
            calls.append(("init", (base_url, credential_key_id, token)))

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

        def list_evidence(self, unit_id: str) -> list[dict[str, object]]:
            calls.append(("list_evidence", unit_id))
            return []

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
            assert "lease-redacted" not in command
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
                "local-heavy-finalize",
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
    assert "local-heavy submitted work unit unit-1" in result.output
    assert "lease-redacted" not in result.output
    evidence_payloads: list[dict[str, object]] = []
    for name, item in calls:
        if name == "evidence" and isinstance(item, tuple):
            payload = item[1]
            if isinstance(payload, dict):
                evidence_payloads.append(payload)
    assert evidence_payloads
    assert all(
        "lease-redacted" not in json.dumps(payload["payload"]) for payload in evidence_payloads
    )


def test_commit_carries_an_explicit_git_identity(tmp_path: Path) -> None:
    """GitHub Actions runners have no git identity; `git commit` exits 128 without one.

    The identity is passed per-command with `-c` rather than written to global config,
    so the runner never mutates the checkout's git configuration.
    """
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
                "work_unit_id": "unit-1",
                **_finalization_authority(tmp_path, brief),
            }
        )
    )
    commands: list[list[str]] = []

    class FakeClient:
        def __init__(self, **_: object) -> None: ...

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

        def list_evidence(self, unit_id: str) -> list[dict[str, object]]:
            return []

        def submit_evidence(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            return {"id": "evidence-1"}

        def submit(self, unit_id: str, payload: dict[str, object]) -> dict[str, object]:
            return {"unit_id": unit_id, "state": "submitted", "version": 6}

        def release(self, *_: object, **__: object) -> dict[str, object]:
            return {}

    def fake_run(command: list[str], **_: object) -> str:
        commands.append(command)
        if command[:2] == ["git", "status"]:
            return " M pyproject.toml\n"
        if command[:3] == ["gh", "pr", "create"]:
            return "https://github.com/AlobarQuest/orchestrator/pull/99\n"
        return ""

    from factory_runner import cli as cli_module

    original_client = cli_module.OrchestratorClient
    original_run = cli_module._run_command
    cli_module.OrchestratorClient = FakeClient
    cli_module._run_command = fake_run
    try:
        CliRunner().invoke(
            app,
            [
                "finalize-run",
                "--orchestrator-url",
                "https://sds.invalid",
                "--credential-key-id",
                "factory-runner-github",
                "--work-unit-id",
                "unit-1",
                "--workspace-dir",
                str(tmp_path),
            ],
            env={"FACTORY_RUNNER_TOKEN": "token"},
        )
    finally:
        cli_module.OrchestratorClient = original_client
        cli_module._run_command = original_run

    commit = next(c for c in commands if "commit" in c)
    assert commit[:2] == ["git", "-c"]
    assert any(part.startswith("user.name=") for part in commit)
    assert any(part.startswith("user.email=") for part in commit)
    assert "config" not in commit


def test_the_pull_request_is_not_created_as_a_draft(tmp_path: Path) -> None:
    """Draft PRs are unavailable on private repos on this plan, and Devon's standing
    instruction (2026-07-05) is that prepared PRs are not left in draft."""
    import inspect

    from factory_runner import cli as cli_module

    source = inspect.getsource(cli_module._finalize_workspace)

    assert '"--draft"' not in source


def test_a_failing_command_surfaces_its_output(tmp_path: Path) -> None:
    """`_run_command` captured stdout+stderr and then discarded it on failure, so a
    `gh pr create` error never reached the log and had to be inferred."""
    from factory_runner import cli as cli_module

    with pytest.raises(RuntimeError) as excinfo:
        cli_module._run_command(["sh", "-c", "echo boom-marker >&2; exit 3"])

    assert "boom-marker" in str(excinfo.value)


def test_prepare_hides_agent_artifacts_from_git(tmp_path: Path) -> None:
    """The coding action writes its full transcript to `output.txt` in the checkout.

    `git add -A` swept it into the commit, which both polluted the PR and defeated the
    "no changes to submit" guard — the guard that would have caught a run where the agent
    did nothing.
    """
    import inspect

    from factory_runner import cli as cli_module

    git_dir = tmp_path / ".git" / "info"
    git_dir.mkdir(parents=True)

    cli_module._exclude_agent_artifacts(tmp_path)

    exclude = (git_dir / "exclude").read_text()
    assert "output.txt" in exclude
    # The helper is worthless unless prepare_run actually calls it, before the coding
    # action runs and writes output.txt.
    assert "_exclude_agent_artifacts(" in inspect.getsource(cli_module.prepare_run)


def _finalize_with_clean_tree(tmp_path: Path, *, base_sha: str | None, head_sha: str):
    """finalize-run against a working tree with nothing uncommitted."""
    brief = _runner_brief()
    (tmp_path / "brief.json").write_text(brief.model_dump_json())
    run: dict[str, object] = {
        "attempt": 1,
        "claim_id": "claim-1",
        "context_snapshot_id": "snapshot-1",
        "lease_token": "lease-redacted",
        "package_revision_id": "rev-1",
        "submit_expected_version": 5,
        "work_unit_id": "unit-1",
    }
    run.update(_finalization_authority(tmp_path, brief))
    if base_sha is not None:
        run["base_sha"] = base_sha
    (tmp_path / "run.json").write_text(json.dumps(run))

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None: ...

        def get_runner_brief(self, _unit_id: str) -> RunnerBrief:
            return brief

    def fake_run(command: list[str], **_kwargs: object) -> str:
        if command[:3] == ["git", "status", "--porcelain"]:
            return ""
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return f"{head_sha}\n"
        return ""

    from factory_runner import cli as cli_module

    original_client, original_run = cli_module.OrchestratorClient, cli_module._run_command
    cli_module.OrchestratorClient = FakeClient
    cli_module._run_command = fake_run
    try:
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
    finally:
        cli_module.OrchestratorClient = original_client
        cli_module._run_command = original_run


def test_finalize_run_reports_agent_commit_distinctly_from_empty_diff(tmp_path: Path) -> None:
    """An agent that commits its own work leaves a tree as clean as one that changed nothing.

    Reporting both as "no changes to submit" sent WS-6.4's canary diagnosis at the envelope
    when the defect was in the runner's own prompt.
    """
    result = _finalize_with_clean_tree(tmp_path, base_sha="aaaa1111", head_sha="bbbb2222")
    assert result.exit_code == 1
    assert "agent committed its own work" in result.output
    assert "aaaa1111..bbbb2222" in result.output
    assert "no changes to submit" not in result.output


def test_finalize_run_reports_empty_diff_when_head_is_unmoved(tmp_path: Path) -> None:
    result = _finalize_with_clean_tree(tmp_path, base_sha="aaaa1111", head_sha="aaaa1111")
    assert result.exit_code == 1
    assert "no changes to submit" in result.output
    assert "agent committed" not in result.output


def test_finalize_run_falls_back_when_base_sha_absent(tmp_path: Path) -> None:
    """Workspaces written before base_sha existed must still report the empty-diff guard."""
    result = _finalize_with_clean_tree(tmp_path, base_sha=None, head_sha="bbbb2222")
    assert result.exit_code == 1
    assert "no changes to submit" in result.output


def test_prompt_forbids_committing_and_states_the_runner_contract() -> None:
    from factory_runner.cli import _prompt

    prompt = _prompt(_runner_brief(), ("uv lock --upgrade", "uv sync", "make check"))

    # The runner writes the commit and its trailers; instructing the agent to commit
    # leaves a clean tree and finalize refuses to submit it.
    assert "When committing" not in prompt
    assert "UNCOMMITTED" in prompt
    assert "`git commit`" in prompt
    assert "gh pr create" in prompt

    # allowed_commands carries mutators and is re-executed in order before the commit.
    assert "Allowed verification commands" not in prompt
    assert "Authorized commands, in order:" in prompt
    assert "re-executes this" in prompt
    assert "uv lock --upgrade" in prompt
