import pytest

from factory_runner.authority import SUPPORTED_CAPABILITIES, AuthorityError, validate_authority
from factory_runner.capability_vocabulary import CAPABILITY_VOCABULARY
from factory_runner.models import AuthorityEnvelope


def _envelope() -> AuthorityEnvelope:
    return AuthorityEnvelope.model_validate(
        {
            "capabilities": {
                "repo.read": "allowed",
                "repo.edit": "allowed",
                "command.run": "allowed",
                "github.pr.create": "allowed",
                "orchestrator.claim": "allowed",
                "orchestrator.evidence.write": "allowed",
            },
            "budgets": {"max_attempts": 3, "max_llm_calls": 4},
            "constraints": {
                "work_unit_id": "unit-1",
                "target_repository": "AlobarQuest/orchestrator",
                "allowed_commands": ["make check"],
                "mutation_commands": ["make check"],
            },
        }
    )


def test_supported_capabilities_are_derived_from_shipped_vocabulary() -> None:
    assert SUPPORTED_CAPABILITIES == frozenset(CAPABILITY_VOCABULARY["runner"])


def test_maps_allowed_capabilities_to_minimal_tools() -> None:
    permissions = validate_authority(
        _envelope(),
        work_unit_id="unit-1",
        target_repo="AlobarQuest/orchestrator",
        current_repo="AlobarQuest/orchestrator",
    )

    assert permissions.allowed_tools == ("Read", "Edit", "Bash", "Glob")
    assert permissions.allowed_commands == ("make check",)
    assert permissions.mutation_commands == ("make check",)
    assert permissions.can_edit is True
    assert permissions.can_create_pr is True
    assert permissions.can_submit_evidence is True
    assert permissions.can_claim is True


def test_maps_prohibited_repo_edit_to_false_permission() -> None:
    envelope = _envelope().model_copy(
        update={"capabilities": {**_envelope().capabilities, "repo.edit": "prohibited"}}
    )

    permissions = validate_authority(
        envelope,
        work_unit_id="unit-1",
        target_repo="AlobarQuest/orchestrator",
        current_repo="AlobarQuest/orchestrator",
    )

    assert permissions.can_edit is False
    assert "Edit" not in permissions.allowed_tools


def test_unknown_capability_fails_closed() -> None:
    """The example is deliberately synthetic, and that is the point of it.

    This test used `github.merge` until WS-P3.7 Increment 3, which added `github.pr.merge` to
    the vocabulary -- one letter-group away from asserting the behaviour that increment changed.
    A negative control keyed on a name somebody might plausibly ship is a control with an expiry
    date on it; `not.a.capability` cannot become real without somebody noticing.
    """
    envelope = _envelope().model_copy(
        update={"capabilities": {**_envelope().capabilities, "not.a.capability": "allowed"}}
    )

    with pytest.raises(AuthorityError, match="unsupported capability"):
        validate_authority(
            envelope,
            work_unit_id="unit-1",
            target_repo="AlobarQuest/orchestrator",
            current_repo="AlobarQuest/orchestrator",
        )


def test_wrong_repository_fails_closed() -> None:
    with pytest.raises(AuthorityError, match="target repository mismatch"):
        validate_authority(
            _envelope(),
            work_unit_id="unit-1",
            target_repo="AlobarQuest/orchestrator",
            current_repo="AlobarQuest/project-standards",
        )


def test_command_run_requires_allowlist() -> None:
    envelope = _envelope().model_copy(
        update={
            "constraints": {
                "work_unit_id": "unit-1",
                "target_repository": "AlobarQuest/orchestrator",
            }
        }
    )

    with pytest.raises(AuthorityError, match="allowed_commands"):
        validate_authority(
            envelope,
            work_unit_id="unit-1",
            target_repo="AlobarQuest/orchestrator",
            current_repo="AlobarQuest/orchestrator",
        )


def test_dependency_update_requires_mutation_commands() -> None:
    """The requirement is keyed on the declared change class, not on command.run alone."""
    envelope = _envelope().model_copy(
        update={
            "change_class": "dependency-update",
            "constraints": {
                "work_unit_id": "unit-1",
                "target_repository": "AlobarQuest/orchestrator",
                "allowed_commands": ["make check"],
            },
        }
    )

    with pytest.raises(AuthorityError, match="mutation_commands"):
        validate_authority(
            envelope,
            work_unit_id="unit-1",
            target_repo="AlobarQuest/orchestrator",
            current_repo="AlobarQuest/orchestrator",
        )


@pytest.mark.parametrize("change_class", [None, "maintenance-remediation"])
def test_edit_shaped_envelope_needs_no_mutation_commands(change_class: str | None) -> None:
    """Edit-shaped work mutates via the coding agent; no command produces the diff."""
    envelope = _envelope().model_copy(
        update={
            "change_class": change_class,
            "constraints": {
                "work_unit_id": "unit-1",
                "target_repository": "AlobarQuest/orchestrator",
                "allowed_commands": ["make check"],
            },
        }
    )

    permissions = validate_authority(
        envelope,
        work_unit_id="unit-1",
        target_repo="AlobarQuest/orchestrator",
        current_repo="AlobarQuest/orchestrator",
    )

    assert permissions.allowed_commands == ("make check",)
    assert permissions.mutation_commands == ()


@pytest.mark.parametrize("change_class", [None, "maintenance-remediation"])
def test_explicit_empty_mutation_commands_is_refused_for_any_class(
    change_class: str | None,
) -> None:
    """Absence says "no command mutates"; a present-but-empty list is malformed."""
    envelope = _envelope().model_copy(
        update={
            "change_class": change_class,
            "constraints": {
                "work_unit_id": "unit-1",
                "target_repository": "AlobarQuest/orchestrator",
                "allowed_commands": ["make check"],
                "mutation_commands": [],
            },
        }
    )

    with pytest.raises(AuthorityError, match="mutation_commands"):
        validate_authority(
            envelope,
            work_unit_id="unit-1",
            target_repo="AlobarQuest/orchestrator",
            current_repo="AlobarQuest/orchestrator",
        )


@pytest.mark.parametrize(
    ("constraints", "message"),
    [
        (
            {
                "allowed_commands": ["uv sync", "make check"],
                "mutation_commands": ["uv lock"],
            },
            "every mutation command must also appear",
        ),
        (
            {"allowed_commands": [""], "mutation_commands": ["uv lock"]},
            "allowed_commands",
        ),
        (
            {"allowed_commands": ["uv lock"], "mutation_commands": ["  "]},
            "mutation_commands",
        ),
        (
            {"allowed_commands": [1], "mutation_commands": ["uv lock"]},
            "allowed_commands",
        ),
        (
            {"allowed_commands": ["uv lock"], "mutation_commands": [True]},
            "mutation_commands",
        ),
        (
            {
                "allowed_commands": {"command": "uv lock"},
                "mutation_commands": ["uv lock"],
            },
            "allowed_commands",
        ),
        (
            {"allowed_commands": ["uv lock"], "mutation_commands": ("uv lock",)},
            "mutation_commands",
        ),
    ],
)
def test_command_run_rejects_invalid_mutation_contract(
    constraints: dict[str, object], message: str
) -> None:
    envelope = _envelope().model_copy(
        update={
            "constraints": {
                "work_unit_id": "unit-1",
                "target_repository": "AlobarQuest/orchestrator",
                **constraints,
            }
        }
    )

    with pytest.raises(AuthorityError, match=message):
        validate_authority(
            envelope,
            work_unit_id="unit-1",
            target_repo="AlobarQuest/orchestrator",
            current_repo="AlobarQuest/orchestrator",
        )
