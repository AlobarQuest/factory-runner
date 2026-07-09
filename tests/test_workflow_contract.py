from pathlib import Path

import yaml


def test_workflow_has_no_merge_permission_or_merge_command() -> None:
    workflow = Path(".github/workflows/factory-runner.yml").read_text()

    assert "pull-requests: write" in workflow
    assert "contents: write" in workflow
    assert "gh pr merge" not in workflow
    assert "merge-method" not in workflow


def test_workflow_is_manual_and_reusable_only() -> None:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())

    assert set(data["on"]) == {"workflow_dispatch", "workflow_call"}
    assert "schedule" not in data["on"]


def test_workflow_runs_coding_wrapper_without_placeholder_stop() -> None:
    workflow = Path(".github/workflows/factory-runner.yml").read_text()
    data = yaml.safe_load(workflow)
    steps = data["jobs"]["run"]["steps"]

    assert "Stop before coding action" not in workflow
    assert any("factory-runner prepare-run" in (step.get("run") or "") for step in steps)
    assert any("factory-runner finalize-run" in (step.get("run") or "") for step in steps)


def test_workflow_invokes_the_installed_cli_not_a_repo_local_script() -> None:
    """actions/checkout checks out the CALLER's repo, which has no scripts/ of ours.

    The workflow ran `./scripts/run-factory-task.sh` until 2026-07-09 and therefore
    failed with exit 127 in every caller, including the pilot. Only paths provided by
    the installed console script are reachable from a caller's working directory.
    """
    workflow = Path(".github/workflows/factory-runner.yml").read_text()

    assert "./scripts/" not in workflow


def test_workflow_declares_coding_action_secret_without_exposing_m2m_token() -> None:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())
    workflow_call_secrets = data["on"]["workflow_call"]["secrets"]
    job_env = data["jobs"]["run"]["env"]
    steps = data["jobs"]["run"]["steps"]

    assert "ANTHROPIC_API_KEY" in workflow_call_secrets
    assert "ANTHROPIC_API_KEY" not in job_env
    assert "FACTORY_RUNNER_TOKEN" not in job_env
    claude_step = next(step for step in steps if step.get("name") == "Run scoped coding action")
    assert "anthropic_api_key" in claude_step["with"]
    assert "FACTORY_RUNNER_TOKEN" not in str(claude_step)
