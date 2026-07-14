from typing import Any

from factory_runner.models import AuthorityEnvelope, RunnerPermissions

SUPPORTED_CAPABILITIES = frozenset(
    {
        "repo.read",
        "repo.edit",
        "command.run",
        "github.pr.create",
        "orchestrator.claim",
        "orchestrator.evidence.write",
    }
)
SUPPORTED_LEVELS = frozenset({"allowed", "prohibited"})


class AuthorityError(ValueError):
    pass


def validate_authority(
    envelope: AuthorityEnvelope,
    *,
    work_unit_id: str,
    target_repo: str,
    current_repo: str,
) -> RunnerPermissions:
    _validate_capabilities(envelope)
    _validate_constraints(envelope, work_unit_id, target_repo, current_repo)
    allowed_commands, mutation_commands = _validate_commands(envelope)
    tools = _infer_tools(envelope)

    return RunnerPermissions(
        allowed_tools=tuple(dict.fromkeys(tools)),
        allowed_commands=allowed_commands,
        mutation_commands=mutation_commands,
        can_create_pr=_allowed(envelope, "github.pr.create"),
        can_submit_evidence=_allowed(envelope, "orchestrator.evidence.write"),
        can_claim=_allowed(envelope, "orchestrator.claim"),
    )


def _validate_capabilities(envelope: AuthorityEnvelope) -> None:
    for capability, level in envelope.capabilities.items():
        if capability not in SUPPORTED_CAPABILITIES:
            raise AuthorityError(f"unsupported capability: {capability}")
        if level not in SUPPORTED_LEVELS:
            raise AuthorityError(f"unsupported capability level for {capability}: {level}")


def _validate_constraints(
    envelope: AuthorityEnvelope,
    work_unit_id: str,
    target_repo: str,
    current_repo: str,
) -> None:
    constraint_unit = str(envelope.constraints.get("work_unit_id", ""))
    if constraint_unit != work_unit_id:
        raise AuthorityError("work unit constraint mismatch")

    constraint_repo = str(envelope.constraints.get("target_repository", ""))
    if constraint_repo != target_repo or target_repo != current_repo:
        raise AuthorityError("target repository mismatch")


def _validate_commands(envelope: AuthorityEnvelope) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if _allowed(envelope, "command.run"):
        allowed_commands = _non_empty_string_list(envelope.constraints.get("allowed_commands"))
        if allowed_commands is None:
            raise AuthorityError(
                "constraints.allowed_commands must be a non-empty list of non-empty strings"
            )
        mutation_commands = _non_empty_string_list(envelope.constraints.get("mutation_commands"))
        if mutation_commands is None:
            raise AuthorityError(
                "constraints.mutation_commands must be a non-empty list of non-empty strings"
            )
        if any(command not in allowed_commands for command in mutation_commands):
            raise AuthorityError(
                "every mutation command must also appear in constraints.allowed_commands"
            )
        return allowed_commands, mutation_commands

    return (), ()


def _non_empty_string_list(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return tuple(value)


def _infer_tools(envelope: AuthorityEnvelope) -> list[str]:
    tools: list[str] = []
    if _allowed(envelope, "repo.read"):
        tools.append("Read")
    if _allowed(envelope, "repo.edit"):
        tools.append("Edit")
    if _allowed(envelope, "command.run"):
        tools.append("Bash")
    if _allowed(envelope, "repo.read"):
        tools.append("Glob")
    return tools


def _allowed(envelope: AuthorityEnvelope, capability: str) -> bool:
    return envelope.capabilities.get(capability) == "allowed"
