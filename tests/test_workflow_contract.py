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


def _coding_step() -> dict:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())
    steps = data["jobs"]["run"]["steps"]
    return next(s for s in steps if "claude-code-base-action" in str(s.get("uses", "")))


def _cli_steps() -> str:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())
    return "\n".join(str(s.get("run", "")) for s in data["jobs"]["run"]["steps"] if "run" in s)


def test_the_coding_action_pins_a_current_model() -> None:
    """The action's default model is retired; it reads ANTHROPIC_MODEL from the env.

    Leaving it unset made every run die with `API Error: 404 not_found_error
    model: claude-sonnet-4-20250514`.
    """
    step = _coding_step()
    model = (step.get("env") or {}).get("ANTHROPIC_MODEL")

    assert model == "claude-sonnet-5"


def test_the_workspace_lives_outside_the_repository_checkout() -> None:
    """`.factory-runner/` inside the checkout makes `git status` never empty.

    That kills the "no changes to submit" guard and lets `git add -A` commit the
    runner's own brief.json and prompt.md into the pull request.
    """
    runs = _cli_steps()

    assert "--workspace-dir" in runs
    assert "RUNNER_TEMP" in runs
