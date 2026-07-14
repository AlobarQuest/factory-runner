import re
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


def _named_step(name: str) -> dict:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())
    return next(step for step in data["jobs"]["run"]["steps"] if step.get("name") == name)


def _cli_steps() -> str:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())
    return "\n".join(str(s.get("run", "")) for s in data["jobs"]["run"]["steps"] if "run" in s)


def test_the_coding_action_pins_a_current_model_via_the_input() -> None:
    """The model must be the action INPUT, never a step-level ANTHROPIC_MODEL env var.

    `claude-code-base-action@beta` is a composite action whose inner step sets
    `ANTHROPIC_MODEL: ${{ inputs.model || inputs.anthropic_model }}`. An inner step's env
    overrides the caller's, so a step-level ANTHROPIC_MODEL is silently replaced by the
    empty input and the CLI falls back to the retired `claude-sonnet-4-20250514`.
    """
    step = _coding_step()

    assert step["with"]["model"] == "claude-sonnet-5"
    assert "ANTHROPIC_MODEL" not in (step.get("env") or {})


def test_the_workspace_lives_outside_the_repository_checkout() -> None:
    """`.factory-runner/` inside the checkout makes `git status` never empty.

    That kills the "no changes to submit" guard and lets `git add -A` commit the
    runner's own brief.json and prompt.md into the pull request.
    """
    runs = _cli_steps()

    assert "--workspace-dir" in runs
    assert "RUNNER_TEMP" in runs


def test_the_turn_budget_is_large_enough_to_finish_a_change() -> None:
    """max_turns 10 exhausted itself on exploration and committed nothing.

    NOTE: the approved authority envelope carries `budgets.max_llm_calls`, which this
    runner does not yet read. Until it does, this literal is the effective budget and
    the envelope's value is not enforced. Recorded as a named gap, not hidden.
    """
    step = _coding_step()

    assert int(step["with"]["max_turns"]) >= 30


def test_failed_coding_or_finalization_is_reported_without_masking_the_failure() -> None:
    coding = _named_step("Run scoped coding action")
    finalize = _named_step("Finalize scoped run")

    assert coding["id"] == "coding"
    assert finalize["id"] == "finalize"
    assert finalize["if"].strip() == "steps.coding.outcome == 'success'"

    report = _named_step("Report failed scoped run")
    assert report["id"] == "report_failure"
    assert "always()" in report["if"]
    assert "steps.prepare.outcome == 'success'" in report["if"]
    assert "steps.coding.outcome == 'failure'" in report["if"]
    assert "steps.finalize.outcome == 'failure'" in report["if"]
    assert "factory-runner fail-run" in report["run"]
    assert "continue-on-error" not in coding
    assert "continue-on-error" not in finalize


def test_failure_reporter_uses_only_supported_reasons_and_runner_credentials() -> None:
    report = _named_step("Report failed scoped run")

    reasons = re.findall(r'reason="([^"]+)"', report["run"])
    assert reasons == ["finalization_failed", "coding_action_failed"]
    assert (
        'if [[ "${{ steps.finalize.outcome }}" == "failure" ]]; then\n'
        '  reason="finalization_failed"'
    ) in report["run"]
    assert set(report["env"]) == {
        "FACTORY_RUNNER_TOKEN",
        "FACTORY_RUNNER_CREDENTIAL_KEY_ID",
    }
    assert "ANTHROPIC_API_KEY" not in str(report)
    assert "FACTORY_PR_TOKEN" not in str(report)
