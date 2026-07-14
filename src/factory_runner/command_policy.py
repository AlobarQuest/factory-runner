from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")


def write_tool_policy(
    policy_dir: Path,
    checkout: Path,
    allowed_commands: tuple[str, ...],
    fingerprint: str,
) -> tuple[Path, Path]:
    """Write the runner-owned hook policy and Claude settings outside the checkout."""
    commands = _validated_commands(allowed_commands)
    checkout_root = _resolved_directory(checkout)
    resolved_policy_dir = policy_dir.resolve()
    if _contains(checkout_root, resolved_policy_dir):
        raise ValueError("policy directory must be outside the checkout")
    if not _FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("authority fingerprint must be a lowercase SHA-256 digest")

    resolved_policy_dir.mkdir(parents=True, exist_ok=True)
    policy_path = resolved_policy_dir / "policy.json"
    settings_path = resolved_policy_dir / "settings.json"
    policy_path.write_bytes(_canonical_policy_bytes(fingerprint, commands, checkout_root))
    policy_path.chmod(0o400)
    quoted_policy_path = shlex.quote(str(policy_path))
    _write_canonical_json(
        settings_path,
        {
            "hooks": {
                "PreToolUse": [
                    _hook("Bash", quoted_policy_path),
                    _hook("Edit", quoted_policy_path),
                ]
            }
        },
    )
    return policy_path, settings_path


def authorize_tool(policy_path: Path, hook_input: Mapping[str, object]) -> tuple[bool, str]:
    """Return an allow decision only for an exact Bash command or contained Edit path."""
    try:
        policy = _load_policy(policy_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False, "policy unavailable"

    tool_name = hook_input.get("tool_name")
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return False, "missing tool input"
    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return False, "missing Bash command"
        return (
            (True, "authorized")
            if command in policy["allowed_commands"]
            else (False, "Bash command is not authorized")
        )
    if tool_name == "Edit":
        file_path = tool_input.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            return False, "missing Edit file path"
        return _authorize_edit(policy["checkout_root"], file_path)
    return False, "tool is not authorized"


def policy_digest(*, fingerprint: str, allowed_commands: tuple[str, ...], checkout: Path) -> str:
    """Return the digest for an expected policy built from immutable authority."""
    return hashlib.sha256(
        _canonical_policy_bytes(
            fingerprint, _validated_commands(allowed_commands), _resolved_directory(checkout)
        )
    ).hexdigest()


def read_policy(policy_path: Path) -> tuple[str, tuple[str, ...], Path, str]:
    """Load a valid policy and return its immutable fields plus canonical digest."""
    policy = _load_policy(policy_path)
    return (
        policy["authority_fingerprint"],
        policy["allowed_commands"],
        policy["checkout_root"],
        hashlib.sha256(policy_path.read_bytes()).hexdigest(),
    )


def _hook(matcher: str, quoted_policy_path: str) -> dict[str, object]:
    return {
        "matcher": matcher,
        "hooks": [
            {
                "type": "command",
                "command": f"factory-runner authorize-tool --policy-file {quoted_policy_path}",
            }
        ],
    }


def _load_policy(policy_path: Path) -> dict[str, Any]:
    payload = json.loads(policy_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("policy must be an object")
    fingerprint = payload.get("authority_fingerprint")
    commands = payload.get("allowed_commands")
    checkout = payload.get("checkout_root")
    if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("invalid authority fingerprint")
    if not isinstance(commands, list):
        raise ValueError("invalid allowed commands")
    validated_commands = _validated_commands(tuple(commands))
    if not isinstance(checkout, str):
        raise ValueError("invalid checkout root")
    return {
        "authority_fingerprint": fingerprint,
        "allowed_commands": validated_commands,
        "checkout_root": _resolved_directory(Path(checkout)),
    }


def _authorize_edit(checkout_root: Path, file_path: str) -> tuple[bool, str]:
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = checkout_root / candidate
    try:
        resolved_target = candidate.resolve(strict=False)
        _resolved_existing_parent(candidate)
    except (OSError, RuntimeError):
        return False, "Edit path cannot be resolved"
    git_root = (checkout_root / ".git").resolve(strict=False)
    if not _contains(checkout_root, resolved_target):
        return False, "Edit path is outside checkout"
    if _contains(git_root, resolved_target):
        return False, "Edit path is inside checkout git metadata"
    return True, "authorized"


def _resolved_existing_parent(path: Path) -> Path:
    parent = path if path.exists() else path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent.resolve(strict=True)


def _resolved_directory(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("checkout root must be a directory")
    return resolved


def _validated_commands(commands: tuple[object, ...]) -> tuple[str, ...]:
    if not commands or any(
        not isinstance(command, str) or not command.strip() for command in commands
    ):
        raise ValueError("approved commands must be non-empty strings")
    return tuple(command for command in commands if isinstance(command, str))


def _canonical_policy_bytes(fingerprint: str, commands: tuple[str, ...], checkout: Path) -> bytes:
    return (
        json.dumps(
            {
                "authority_fingerprint": fingerprint,
                "allowed_commands": list(commands),
                "checkout_root": str(checkout),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _write_canonical_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def _contains(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True
