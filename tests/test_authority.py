import pytest

from factory_runner.authority import AuthorityError, validate_authority
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
            },
        }
    )


def test_maps_allowed_capabilities_to_minimal_tools() -> None:
    permissions = validate_authority(
        _envelope(),
        work_unit_id="unit-1",
        target_repo="AlobarQuest/orchestrator",
        current_repo="AlobarQuest/orchestrator",
    )

    assert permissions.allowed_tools == ("Read", "Edit", "Bash", "Glob")
    assert permissions.allowed_commands == ("make check",)
    assert permissions.can_create_pr is True
    assert permissions.can_submit_evidence is True
    assert permissions.can_claim is True


def test_unknown_capability_fails_closed() -> None:
    envelope = _envelope().model_copy(
        update={"capabilities": {**_envelope().capabilities, "github.merge": "allowed"}}
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
