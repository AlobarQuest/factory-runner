from typing import Any

from factory_runner.capability_vocabulary import CAPABILITY_VOCABULARY
from factory_runner.models import AuthorityEnvelope, RunnerPermissions

SUPPORTED_CAPABILITIES = frozenset(CAPABILITY_VOCABULARY["runner"])
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
    allowed_commands, mutation_commands, verify_commands = _validate_commands(envelope)
    tools = _infer_tools(envelope)

    return RunnerPermissions(
        allowed_tools=tuple(dict.fromkeys(tools)),
        allowed_commands=allowed_commands,
        mutation_commands=mutation_commands,
        verify_commands=verify_commands,
        can_edit=_allowed(envelope, "repo.edit"),
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


def _validate_commands(
    envelope: AuthorityEnvelope,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    # mutation_commands is required only for dependency-update work, where a command
    # produces the diff. Edit-shaped work mutates through the coding agent, so the
    # honest envelope omits the key entirely; a present key must always be well-formed.
    # verify_commands is optional for every change class (see finalization_script).
    # This predicate is a cross-repo contract with AlobarQuest/orchestrator
    # (kernel/runner_authority.py), pinned by the shared envelope fixtures.
    if not _allowed(envelope, "command.run"):
        return (), (), ()

    allowed_commands = _non_empty_string_list(envelope.constraints.get("allowed_commands"))
    if allowed_commands is None:
        raise AuthorityError(
            "constraints.allowed_commands must be a non-empty list of non-empty strings"
        )
    mutation_commands = _mutation_commands(envelope, allowed_commands)
    return (
        allowed_commands,
        mutation_commands,
        _verify_commands(envelope, allowed_commands, mutation_commands),
    )


def _mutation_commands(
    envelope: AuthorityEnvelope, allowed_commands: tuple[str, ...]
) -> tuple[str, ...]:
    if "mutation_commands" not in envelope.constraints:
        if envelope.change_class == "dependency-update":
            raise AuthorityError(
                "constraints.mutation_commands must be a non-empty list of non-empty strings"
            )
        return ()
    mutation_commands = _non_empty_string_list(envelope.constraints["mutation_commands"])
    if mutation_commands is None:
        raise AuthorityError(
            "constraints.mutation_commands must be a non-empty list of non-empty strings"
        )
    if any(command not in allowed_commands for command in mutation_commands):
        raise AuthorityError(
            "every mutation command must also appear in constraints.allowed_commands"
        )
    return mutation_commands


def _verify_commands(
    envelope: AuthorityEnvelope,
    allowed_commands: tuple[str, ...],
    mutation_commands: tuple[str, ...],
) -> tuple[str, ...]:
    """The ordered verify script, or () when the envelope declares none.

    Disjoint from mutation_commands because finalize labels every command it runs exactly
    once -- a mutator is `applied`, a verifier `passed` -- and runs the mutators before the
    verify script. A command in both lists would run twice, and one of its two evidence
    entries would claim verification about a command whose job is to change the tree.
    """
    if "verify_commands" not in envelope.constraints:
        return ()
    verify_commands = _non_empty_string_list(envelope.constraints["verify_commands"])
    if verify_commands is None:
        raise AuthorityError(
            "constraints.verify_commands must be a non-empty list of non-empty strings"
        )
    if any(command not in allowed_commands for command in verify_commands):
        raise AuthorityError(
            "every verify command must also appear in constraints.allowed_commands"
        )
    if any(command in mutation_commands for command in verify_commands):
        raise AuthorityError("a verify command must not also be a mutation command")
    return verify_commands


def finalization_script(permissions: RunnerPermissions) -> tuple[tuple[str, str], ...]:
    """What finalize executes, in order, each command paired with its evidence label.

    Without verify_commands the script is allowed_commands itself, in its own order -- the
    behaviour every envelope authored before the key existed was approved under. With it, the
    mutators run first, in their allowed_commands order, then the verify script in ITS order;
    an allowed command in neither list is agent vocabulary only and finalize does not run it.
    """
    mutations = set(permissions.mutation_commands)
    if not permissions.verify_commands:
        return tuple(
            (command, "applied" if command in mutations else "passed")
            for command in permissions.allowed_commands
        )
    return tuple(
        (command, "applied") for command in permissions.allowed_commands if command in mutations
    ) + tuple((command, "passed") for command in permissions.verify_commands)


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
