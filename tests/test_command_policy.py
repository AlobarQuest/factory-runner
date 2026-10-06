from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from factory_runner.command_policy import authorize_tool, write_tool_policy


def _policy(tmp_path: Path, commands: tuple[str, ...] = ("uv sync --locked",)) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    policy, _settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        commands,
        "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
        edit_allowed=True,
    )
    return policy


def test_write_tool_policy_is_canonical_read_only_and_outside_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    policy, settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        ("uv sync --locked", "uv sync --locked"),
        "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
        edit_allowed=True,
    )

    assert policy.parent == settings.parent == (tmp_path / "policy").resolve()
    assert policy.is_relative_to(checkout.resolve()) is False
    assert json.loads(policy.read_text()) == {
        "allowed_commands": ["uv sync --locked", "uv sync --locked"],
        "authority_fingerprint": "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
        "checkout_root": str(checkout.resolve()),
        "edit_allowed": True,
        "protected_paths": [],
    }
    assert stat.S_IMODE(policy.stat().st_mode) == 0o400
    settings_payload = json.loads(settings.read_text())
    hooks = settings_payload["hooks"]["PreToolUse"]
    assert [hook["matcher"] for hook in hooks] == ["Bash", "Edit"]
    assert all(str(policy) in hook["hooks"][0]["command"] for hook in hooks)


@pytest.mark.parametrize("commands", [(), ("",), ("   ",)])
def test_write_tool_policy_rejects_blank_approved_commands(
    tmp_path: Path, commands: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="approved commands"):
        write_tool_policy(
            tmp_path / "policy",
            tmp_path / "checkout",
            commands,
            "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
            edit_allowed=True,
        )


@pytest.mark.parametrize(
    "command",
    [
        "uv sync --locked && git push",
        "uv sync --locked | tee output.txt",
        "uv sync --locked > output.txt",
        "FOO=bar uv sync --locked",
        "uv sync --locked\nwhoami",
        "uv sync --locked ",
        "uv sync",
        "whoami",
    ],
)
def test_authorize_tool_denies_any_non_exact_bash(command: str, tmp_path: Path) -> None:
    policy = _policy(tmp_path)

    allowed, _reason = authorize_tool(
        policy,
        {"tool_name": "Bash", "tool_input": {"command": command}},
    )

    assert allowed is False


def test_authorize_tool_allows_an_exact_bash_string(tmp_path: Path) -> None:
    policy = _policy(tmp_path)

    allowed, reason = authorize_tool(
        policy,
        {"tool_name": "Bash", "tool_input": {"command": "uv sync --locked"}},
    )

    assert allowed is True
    assert reason == "authorized"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tool_name": "Bash", "tool_input": {}},
        {"tool_name": "Read", "tool_input": {"file_path": "README.md"}},
        {"tool_name": "Bash", "tool_input": {"command": ["uv sync --locked"]}},
    ],
)
def test_authorize_tool_fails_closed_for_non_bash_or_missing_command(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    allowed, _reason = authorize_tool(_policy(tmp_path), payload)

    assert allowed is False


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        {"authority_fingerprint": "bad", "allowed_commands": ["uv sync --locked"]},
        {
            "authority_fingerprint": (
                "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31"
            ),
            "allowed_commands": ["uv sync --locked"],
            "checkout_root": 1,
        },
    ],
)
def test_authorize_tool_denies_missing_or_invalid_policy(tmp_path: Path, payload: object) -> None:
    policy = tmp_path / "policy.json"
    if isinstance(payload, str):
        policy.write_text(payload)
    else:
        policy.write_text(json.dumps(payload))

    allowed, _reason = authorize_tool(
        policy,
        {"tool_name": "Bash", "tool_input": {"command": "uv sync --locked"}},
    )

    assert allowed is False


def test_authorize_tool_allows_existing_non_git_edit_in_checkout(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    target = tmp_path / "checkout" / "src" / "main.py"
    target.parent.mkdir()
    target.write_text("print('ok')\n")

    allowed, _reason = authorize_tool(
        policy,
        {"tool_name": "Edit", "tool_input": {"file_path": str(target)}},
    )

    assert allowed is True


@pytest.mark.parametrize(
    ("edit_allowed", "expected"),
    [(False, False), (True, True)],
)
def test_authorize_tool_requires_explicit_edit_authority(
    tmp_path: Path, edit_allowed: bool, expected: bool
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    target = checkout / "src" / "main.py"
    target.parent.mkdir()
    target.write_text("print('ok')\n")
    policy, _settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        ("uv sync --locked",),
        "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
        edit_allowed=edit_allowed,
    )

    allowed, _reason = authorize_tool(
        policy,
        {"tool_name": "Edit", "tool_input": {"file_path": str(target)}},
    )

    assert allowed is expected


def test_authorize_tool_denies_edit_when_policy_omits_edit_authority(tmp_path: Path) -> None:
    target = tmp_path / "checkout" / "src" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('ok')\n")
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "authority_fingerprint": (
                    "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31"
                ),
                "allowed_commands": ["uv sync --locked"],
                "checkout_root": str((tmp_path / "checkout").resolve()),
                "protected_paths": [],
            }
        )
    )

    allowed, _reason = authorize_tool(
        policy,
        {"tool_name": "Edit", "tool_input": {"file_path": str(target)}},
    )

    assert allowed is False


@pytest.mark.parametrize(
    "file_path",
    [
        "../outside.txt",
        "../../outside.txt",
        "",
    ],
)
def test_authorize_tool_denies_relative_edit_escape(tmp_path: Path, file_path: str) -> None:
    policy = _policy(tmp_path)

    allowed, _reason = authorize_tool(
        policy,
        {"tool_name": "Edit", "tool_input": {"file_path": file_path}},
    )

    assert allowed is False


def test_authorize_tool_denies_outside_policy_and_symlink_edits(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    checkout = tmp_path / "checkout"
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    run_metadata = tmp_path / "run.json"
    run_metadata.write_text("{}\n")
    escaped = checkout / "escaped.txt"
    os.symlink(outside, escaped)

    for file_path in (
        str(outside),
        str(policy),
        str(policy.parent / "settings.json"),
        str(run_metadata),
        str(escaped),
    ):
        allowed, _reason = authorize_tool(
            policy,
            {"tool_name": "Edit", "tool_input": {"file_path": file_path}},
        )
        assert allowed is False


def test_authorize_tool_denies_default_in_checkout_runner_metadata(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    metadata = checkout / ".factory-runner"
    run_metadata = metadata / "run.json"
    prompt = metadata / "prompt.md"
    brief = metadata / "brief.json"
    metadata.mkdir()
    run_metadata.write_text("{}\n")
    prompt.write_text("prompt\n")
    brief.write_text("{}\n")
    policy, _settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        ("uv sync --locked",),
        "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",
        edit_allowed=True,
        protected_paths=(metadata,),
    )

    for file_path in (run_metadata, prompt, brief):
        allowed, _reason = authorize_tool(
            policy,
            {"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}},
        )
        assert allowed is False


@pytest.mark.parametrize(
    "git_path", [".git/config", ".git/hooks/pre-commit", ".git/refs/heads/main", ".git/index"]
)
def test_authorize_tool_denies_every_git_subtree_edit(tmp_path: Path, git_path: str) -> None:
    policy = _policy(tmp_path)
    target = tmp_path / "checkout" / git_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("protected\n")

    allowed, _reason = authorize_tool(
        policy,
        {"tool_name": "Edit", "tool_input": {"file_path": str(target)}},
    )

    assert allowed is False


_FINGERPRINT = "0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31"

# `_canonical_policy_bytes` for a policy WITHOUT verify_commands, computed with the function as
# it stood on origin/main before 3c-1 (b025a56). Every policy written
# for an envelope without the key must keep these exact bytes.
_PRE_VERIFY_POLICY_BYTES = (
    b'{"allowed_commands":["uv add x","uv lock --check"],'
    b'"authority_fingerprint":"0f7ef81ecfab22d2a7b8258e94a670f414067d7298f5a5e71b66ade70d7b6f31",'
    b'"checkout_root":"/checkout","edit_allowed":true,'
    b'"protected_paths":["/checkout/.factory-runner"]}\n'
)
_PRE_VERIFY_POLICY_DIGEST = "49f4682f9ac82d12948c532d7fc32fd50bf4fd33ba45bff29dc702adba136d2e"


def test_a_policy_without_verify_commands_keeps_its_pre_3c1_bytes() -> None:
    import hashlib

    from factory_runner.command_policy import _canonical_policy_bytes

    written = _canonical_policy_bytes(
        _FINGERPRINT,
        ("uv add x", "uv lock --check"),
        Path("/checkout"),
        True,
        (Path("/checkout/.factory-runner"),),
        (),
    )

    assert written == _PRE_VERIFY_POLICY_BYTES
    assert hashlib.sha256(written).hexdigest() == _PRE_VERIFY_POLICY_DIGEST


def test_a_verify_script_is_written_into_the_policy_and_its_digest(tmp_path: Path) -> None:
    """SDS 1.1 3c-1: the finalize script is attested by the same 0400 file as the vocabulary."""
    from factory_runner.command_policy import policy_digest, read_policy

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    commands = ("uv add x", "uv lock --check")
    policy, _settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        commands,
        _FINGERPRINT,
        edit_allowed=True,
        verify_commands=("uv lock --check",),
    )

    assert json.loads(policy.read_text())["verify_commands"] == ["uv lock --check"]
    _fingerprint, _commands, verify, *_rest, digest = read_policy(policy)
    assert verify == ("uv lock --check",)
    assert digest == policy_digest(
        fingerprint=_FINGERPRINT,
        allowed_commands=commands,
        checkout=checkout,
        edit_allowed=True,
        verify_commands=("uv lock --check",),
    )
    assert digest != policy_digest(
        fingerprint=_FINGERPRINT, allowed_commands=commands, checkout=checkout, edit_allowed=True
    )


def test_a_verify_script_does_not_widen_the_bash_vocabulary(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    policy, _settings = write_tool_policy(
        tmp_path / "policy",
        checkout,
        ("uv add x",),
        _FINGERPRINT,
        edit_allowed=True,
        verify_commands=("uv lock --check",),
    )

    allowed, _reason = authorize_tool(
        policy, {"tool_name": "Bash", "tool_input": {"command": "uv lock --check"}}
    )

    assert allowed is False


@pytest.mark.parametrize("verify", [[], "uv lock --check", [""], [3]])
def test_a_policy_with_a_malformed_verify_script_is_unavailable(
    tmp_path: Path, verify: object
) -> None:
    from factory_runner.command_policy import read_policy

    policy = _policy(tmp_path)
    payload = json.loads(policy.read_text())
    payload["verify_commands"] = verify
    policy.chmod(0o600)
    policy.write_text(json.dumps(payload))

    with pytest.raises(ValueError):
        read_policy(policy)
    assert authorize_tool(
        policy, {"tool_name": "Bash", "tool_input": {"command": "uv sync --locked"}}
    ) == (False, "policy unavailable")
