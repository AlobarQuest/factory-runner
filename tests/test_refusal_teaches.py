"""A refusal must teach, because the agent pays a turn for every one it does not understand.

Measured 2026-09-03 on a real zod 3->4 migration into infraops-mcp-server. The agent used its
whole 40-turn budget and hit the ceiling with the migration COMPLETE but unreported. Seven of
those forty turns were refused Bash calls:

    cat package.json | grep -A1 -B1 zod
    grep -n "zod" package.json
    find .../node_modules/zod-to-json-schema -maxdepth 2 -type f | head -50
    wc -l .../README.md 2>&1 || true
    find .../.github/workflows -type f 2>&1
    true
    grep -q '"zod": "4.4.3"' package.json && echo MATCH      <- an AUTHORIZED command + `&& echo`

Every one was read-only investigation the agent could have done with Read/Grep/Glob/LS, which
this policy does not gate at all -- and it DID switch to them after each refusal, having had to
work that out again each time. It was never blocked from the information; it was blocked from
knowing where the door was.

Neither fix widens authority. They stop the agent buying that knowledge a turn at a time.
"""

from pathlib import Path

from test_cli import _runner_brief

from factory_runner.cli import _prompt
from factory_runner.command_policy import authorize_tool, write_tool_policy


def _policy(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    policy, _settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        ("uv sync --locked", "make check"),
        "a" * 64,
        edit_allowed=True,
    )
    return policy


def _refuse(tmp_path: Path, command: str) -> str:
    allowed, reason = authorize_tool(
        _policy(tmp_path), {"tool_name": "Bash", "tool_input": {"command": command}}
    )
    assert allowed is False
    return reason


def test_the_refusal_states_that_matching_is_exact(tmp_path: Path) -> None:
    """The `&& echo MATCH` case: an AUTHORIZED command refused for a trailing suffix.

    Without this the agent reads the refusal as "that command is forbidden" and stops using a
    command it is in fact allowed to run.
    """
    reason = _refuse(tmp_path, "uv sync --locked && echo MATCH")

    assert "EXACT" in reason
    assert "&&" in reason


def test_the_refusal_points_at_the_tools_that_need_no_authorization(tmp_path: Path) -> None:
    """The whole payload. Six of the seven refusals were shell investigation."""
    reason = _refuse(tmp_path, "grep -n zod package.json")

    for tool in ("Read", "Grep", "Glob", "LS"):
        assert tool in reason


def test_the_refusal_stays_within_the_bound_and_does_not_echo_the_policy(
    tmp_path: Path,
) -> None:
    """Pinned HERE as well as in the CLI test, because this is where the string is written.

    Listing the authorized commands was the first instinct and is wrong twice over: the CLI
    bounds this stderr under 200 characters and asserts the policy is not echoed, and the agent
    already receives the list in its prompt. What it lacked was the rule, not the list.
    """
    reason = _refuse(tmp_path, "whoami")

    assert len(reason) < 200
    assert "uv sync" not in reason
    assert "make check" not in reason


def test_an_authorized_command_is_still_authorized(tmp_path: Path) -> None:
    """The control. A refusal that taught well by refusing everything would pass the rest."""
    allowed, reason = authorize_tool(
        _policy(tmp_path), {"tool_name": "Bash", "tool_input": {"command": "uv sync --locked"}}
    )

    assert allowed is True
    assert reason == "authorized"


def test_the_prompt_states_the_exact_rule_and_names_the_ungated_tools() -> None:
    """Say it once up front, so the first refusal is not how the agent learns it.

    The prompt already said "This list bounds every command you may run", which is true and was
    evidently read as a statement about authority-bearing commands rather than "you have no
    shell for anything else". Both missing pieces are added: that matching is exact, and where
    investigation belongs.
    """
    prompt = _prompt(_runner_brief(), ("uv sync --locked", "make check"))
    # Normalised: the prompt is hard-wrapped, so a phrase can straddle a newline.
    flat = " ".join(prompt.split())

    assert "EXACT" in flat
    for tool in ("Read", "Grep", "Glob", "LS"):
        assert tool in flat
    assert "Every refused command costs you a turn" in flat


def test_the_prompt_tells_the_agent_the_runner_does_the_re_execution() -> None:
    """Measured across BOTH zod attempts: the run ends on bookkeeping, not on the work.

    Attempt 1 spent its last 7 turns re-verifying after a clean build at turn 33; attempt 2 spent
    its last 10 running the authorized list TWICE after a clean build at turn 30 — turns 35-40
    are literally `npm ci, grep, npm install, npm run build, npm ci, grep`. Both ended
    `error_max_turns` with the migration complete and unreported.

    That is not confusion, it is this prompt: it said the runner re-executes the list "so each
    command must still succeed when run a second time", and the agent read a statement about
    idempotency as an instruction to demonstrate it. The requirement is kept, because it governs
    how the agent WRITES a command; what is added is who performs the second run.
    """
    prompt = _prompt(_runner_brief(), ("uv sync --locked", "make check"))
    flat = " ".join(prompt.split())

    assert "THE RUNNER DOES THAT RE-EXECUTION. YOU MUST NOT." in flat
    assert "passed ONCE, stop" in flat
    # The idempotency requirement itself must survive: it is why a command may not be one-shot.
    assert "must still succeed when run a second time" in flat
