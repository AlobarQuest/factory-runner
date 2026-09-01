import re
from pathlib import Path

import typer.main
import yaml

from factory_runner.cli import app as cli_app


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


_LITERAL_SHA = re.compile(r"\b[0-9a-f]{40}\b")


def test_workflow_pins_runner_and_coding_action_before_any_claim() -> None:
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())
    workflow = Path(".github/workflows/factory-runner.yml").read_text()
    steps = data["jobs"]["run"]["steps"]
    workflow_call_inputs = data["on"]["workflow_call"]["inputs"]
    dispatch_inputs = data["on"]["workflow_dispatch"]["inputs"]

    assert "runner_revision" not in workflow_call_inputs
    assert "runner_revision" not in dispatch_inputs
    assert "inputs.runner_revision" not in workflow
    assert "factory-runner.git@beta" not in workflow
    assert "anthropics/claude-code-base-action@e8132bc5e637a42c27763fc757faa37e1ee43b34" in workflow
    names = [step.get("name") for step in steps]
    assert names.index("Verify factory runner revision") < names.index("Prepare scoped run")


def test_the_install_and_its_verification_both_derive_from_this_workflows_own_commit() -> None:
    """The revision is an EXPRESSION, so there is no literal SHA left to assert identity on.

    A literal was the whole defect class: this workflow could only ever name a commit that
    already existed, so the workflow and the CLI it installed were different revisions by
    construction, and keeping them compatible was a prose rule nothing enforced. `job.*`
    describes the workflow file defining the job — factory-runner, even when called from
    another repo — so building the install target from `job.workflow_sha` makes the caller's
    pin, this workflow and the installed CLI one commit.

    This replaces the retired SHA-identity assertions: a future edit that reintroduces a
    literal, or that reaches for the mutable `workflow_ref`, is caught here.
    """
    install = _named_step("Install pinned factory runner")["run"]
    verify = _named_step("Verify factory runner revision")["run"]

    assert "@${{ job.workflow_sha }}" in install
    assert "github.com/${{ job.workflow_repository }}.git" in install
    assert '--expected "${{ job.workflow_sha }}"' in verify
    for step_name, run in (("install", install), ("verify", verify)):
        assert not _LITERAL_SHA.search(run), (
            f"the {step_name} step names a literal commit again. The workflow can only name a "
            "commit that already exists, so a literal reintroduces the workflow/CLI split this "
            "expression exists to close."
        )
        # workflow_ref carries the ref the caller pinned, UNRESOLVED: a branch ref appears
        # verbatim and is therefore mutable. Only workflow_sha is immutable.
        assert "job.workflow_ref" not in run


def test_workflow_pins_executable_actions_to_exact_commits() -> None:
    """The VALUE is asserted, not the form, and that is the point rather than an oversight.

    This workflow runs a coding agent with a write-capable token inside every factory target, so
    "which commit of this action executes there" is not a thing a bot may change unattended. A
    form assertion -- any 40-character SHA -- would keep the tag-versus-SHA property and give up
    exactly the half doing the work: an update bot moving the pin would then land in silence.

    So an action bump to THIS file reddens here by design, and editing these literals is how the
    review is recorded. Verify the new SHA is the release it claims before doing so -- note
    `astral-sh/setup-uv`'s `refs/tags/v7` is an ANNOTATED tag, so it must be dereferenced
    (`git/tags/<sha>`) and does not appear in a naive ref listing.

    `quality.yml` is deliberately out of scope: it uses mutable tags, runs nothing privileged,
    and its half of the same bump lands without a human.
    """
    data = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())
    uses = [step.get("uses") for step in data["jobs"]["run"]["steps"] if step.get("uses")]

    assert "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5" in uses
    # astral-sh/setup-uv v7.6.0 -- refs/tags/v7 dereferenced, reviewed 2026-09-01.
    assert "astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78" in uses


def test_workflow_classifies_coding_result_before_finalizing_and_reports_it_as_coding_failure() -> (
    None
):
    steps = yaml.safe_load(Path(".github/workflows/factory-runner.yml").read_text())["jobs"]["run"][
        "steps"
    ]
    coding = _named_step("Run scoped coding action")
    classify = _named_step("Classify coding result")
    finalize = _named_step("Finalize scoped run")
    report = _named_step("Report failed scoped run")
    names = [step.get("name") for step in steps]

    assert names.index("Install pinned factory runner") < names.index(
        "Verify factory runner revision"
    )
    assert names.index("Verify factory runner revision") < names.index("Run scoped coding action")
    assert names.index("Run scoped coding action") < names.index("Classify coding result")
    assert names.index("Classify coding result") < names.index("Finalize scoped run")
    assert classify["id"] == "classify"
    assert classify["if"].strip() == "steps.coding.outcome == 'success'"
    assert "--execution-file" in classify["run"]
    assert "steps.coding.outputs.execution_file" in classify["run"]
    assert finalize["if"].strip() == (
        "steps.coding.outcome == 'success' && steps.classify.outcome == 'success'"
    )
    assert coding["with"]["settings"] == "${{ steps.prepare.outputs.settings_file }}"
    assert "steps.classify.outcome == 'failure'" in report["if"]
    assert 'if [[ "${{ steps.finalize.outcome }}" == "failure" ]]; then' in report["run"]


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
    assert finalize["if"].strip() == (
        "steps.coding.outcome == 'success' && steps.classify.outcome == 'success'"
    )

    report = _named_step("Report failed scoped run")
    assert report["id"] == "report_failure"
    assert "always()" in report["if"]
    assert "steps.prepare.outcome == 'success'" in report["if"]
    assert "steps.coding.outcome == 'failure'" in report["if"]
    assert "steps.classify.outcome == 'failure'" in report["if"]
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


_INVOCATION = re.compile(r"factory-runner\s+([a-z][a-z0-9-]*)")
_OPTION = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def _accepted_options() -> dict[str, set[str]]:
    """Every subcommand the CLI exposes, mapped to the long options it accepts.

    Derived from the Typer app itself. A hand-maintained list would be a second
    vocabulary that can drift from the first, which is the very defect class this
    guard exists to catch.
    """
    group = typer.main.get_command(cli_app)
    # Typer vendors click as `typer._click`, so the group type is not importable from a
    # stable public path. Read the subcommands defensively and fail loudly if a future
    # Typer stops exposing them, rather than silently vetting against an empty vocabulary.
    commands = getattr(group, "commands", None)
    assert commands, "cannot read the CLI's subcommands from the Typer app"
    return {
        name: {opt for param in command.params for opt in param.opts if opt.startswith("--")}
        for name, command in commands.items()
    }


def _logical_command(runs: str, start: int) -> str:
    """The invocation at `start` up to the end of its shell command.

    Options are spread over backslash-continued lines, so a single line is not the
    unit of an invocation.
    """
    consumed = []
    for line in runs[start:].splitlines():
        consumed.append(line.rstrip().removesuffix("\\"))
        if not line.rstrip().endswith("\\"):
            break
    return " ".join(consumed)


def _invocations_the_cli_would_reject(runs: str) -> list[str]:
    accepted = _accepted_options()
    rejected = []
    for match in _INVOCATION.finditer(runs):
        subcommand = match.group(1)
        if subcommand not in accepted:
            rejected.append(f"no such subcommand: factory-runner {subcommand}")
            continue
        command = _logical_command(runs, match.start())
        rejected.extend(
            f"factory-runner {subcommand}: unaccepted option {option}"
            for option in _OPTION.findall(command)
            if option not in accepted[subcommand]
        )
    return rejected


def test_every_workflow_invocation_is_accepted_by_the_cli() -> None:
    """Closes the GAP-4 class: SHA identity is not functional consistency.

    On 2026-07-29 the workflow declared the right runner revision and still invoked
    `finalize-run --execution-file`, an option only present in a later CLI. Both
    `finalize-run` and `fail-run` exited 2, so the runner could not report its own
    failure and a recoverable failure became a stranded unit with a spent attempt.
    Neither lint nor type-checking can see across that boundary.
    """
    assert _invocations_the_cli_would_reject(_cli_steps()) == []


def test_the_invocation_guard_rejects_what_the_cli_does_not_accept() -> None:
    """A guard built to detect a failure is worth nothing until it is shown to fire."""
    runs = _cli_steps()

    bogus_option = runs.replace(
        "factory-runner finalize-run \\",
        "factory-runner finalize-run \\\n            --nonexistent-option \\",
        1,
    )
    bogus_subcommand = runs.replace("factory-runner prepare-run", "factory-runner prepare-the-run")

    assert _invocations_the_cli_would_reject(bogus_option) == [
        "factory-runner finalize-run: unaccepted option --nonexistent-option"
    ]
    assert _invocations_the_cli_would_reject(bogus_subcommand) == [
        "no such subcommand: factory-runner prepare-the-run"
    ]
