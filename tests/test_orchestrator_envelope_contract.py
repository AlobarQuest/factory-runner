"""The WS-4.1 <-> WS-4.2 seam contract, runner side.

The orchestrator's dispatch adapter and this runner were each unit-tested against their
own fixtures, and those fixtures disagreed — so an envelope the orchestrator admitted was
rejected here, and the seam had never executed end to end.

`tests/fixtures/runner_authority_envelope.json` and
`tests/fixtures/runner_authority_envelope_edit.json` are byte-identical copies of the files
of the same names in `AlobarQuest/orchestrator`. That repo asserts its decomposition path
*produces* these envelopes and that its dispatch gate admits them; this module asserts
`validate_authority` *accepts* them. The copies must change together — each fixture's
CONTRACT sha is identical in both repos, so a one-sided edit fails here.

The second fixture pins the rule the first one cannot: `mutation_commands` is required for
`change_class: "dependency-update"` and NOT required for edit-shaped work, where the coding
agent produces the diff and no command mutates a tracked file. Both repos enforce the same
predicate; WS-P2.33 exists because they did not, and the byte-identical dependency-update
fixture stayed green while production disagreed.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from factory_runner.authority import (
    SUPPORTED_CAPABILITIES,
    AuthorityError,
    validate_authority,
)
from factory_runner.capability_vocabulary import CAPABILITY_VOCABULARY
from factory_runner.models import AuthorityEnvelope

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "runner_authority_envelope.json"
CONTRACT_SHA256 = "049ab53e2b257fa3d7eb24748a4278ffc7e0e91f8174b05220eefd7d526e5a56"

FIXTURE_EDIT = Path(__file__).resolve().parent / "fixtures" / "runner_authority_envelope_edit.json"
CONTRACT_SHA256_EDIT = "90b73de69bdd9d5ee88be38b0a0ac2eeff1e4bb467ec72062cd1b70f49888f6e"

WORK_UNIT_ID = "8302c75c-e083-5a67-bfd6-63021b90d6da"
TARGET_REPOSITORY = "AlobarQuest/change-manager"

EDIT_WORK_UNIT_ID = "c609dac5-66e0-5b3f-8545-b3b3d128c712"
EDIT_TARGET_REPOSITORY = "AlobarQuest/intent-packages"


def golden_envelope() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def golden_edit_envelope() -> dict[str, Any]:
    return json.loads(FIXTURE_EDIT.read_text())


def test_golden_envelope_is_unchanged() -> None:
    """A one-sided edit here means the orchestrator's copy has silently drifted."""
    canonical = json.dumps(golden_envelope(), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == CONTRACT_SHA256


def test_golden_edit_envelope_is_unchanged() -> None:
    """A one-sided edit here means the orchestrator's copy has silently drifted."""
    canonical = json.dumps(golden_edit_envelope(), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == CONTRACT_SHA256_EDIT


def test_shipped_vocabulary_matches_the_authority_envelope() -> None:
    envelope_capabilities = sorted(golden_envelope()["capabilities"])

    assert list(CAPABILITY_VOCABULARY["runner"]) == envelope_capabilities
    assert SUPPORTED_CAPABILITIES == frozenset(envelope_capabilities)


def test_runner_accepts_the_orchestrator_envelope() -> None:
    """The envelope the orchestrator serves in the runner brief must validate here.

    This is the assertion that never existed: one envelope, both ends. The orchestrator
    stamps constraints.work_unit_id at proposal time, and dispatch fires the workflow in
    the unit's own target repository, so target_repo == current_repo at runtime.
    """
    payload = golden_envelope()
    payload["constraints"]["work_unit_id"] = WORK_UNIT_ID

    permissions = validate_authority(
        AuthorityEnvelope.model_validate(payload),
        work_unit_id=WORK_UNIT_ID,
        target_repo=TARGET_REPOSITORY,
        current_repo=TARGET_REPOSITORY,
    )

    assert permissions.can_claim
    assert permissions.can_create_pr
    assert permissions.can_submit_evidence
    assert permissions.allowed_commands == (
        "uv add --dev 'httpx2>=2.6.0'",
        "uv sync --locked",
        "uv run make check",
    )
    assert permissions.mutation_commands == ("uv add --dev 'httpx2>=2.6.0'",)


def test_runner_accepts_the_edit_shaped_envelope() -> None:
    """Edit-shaped work mutates through the coding agent, not through a command.

    `mutation_commands` is honestly absent — there is no command whose execution
    produces the diff, and inventing one would make the envelope lie about what
    mutates. The runner must accept the shape and derive an empty mutation list.
    This is the envelope shape of the first maintenance-remediation pilot, which
    a pre-WS-P2.33 runner refused 14 seconds into its run.
    """
    payload = golden_edit_envelope()
    payload["constraints"]["work_unit_id"] = EDIT_WORK_UNIT_ID

    permissions = validate_authority(
        AuthorityEnvelope.model_validate(payload),
        work_unit_id=EDIT_WORK_UNIT_ID,
        target_repo=EDIT_TARGET_REPOSITORY,
        current_repo=EDIT_TARGET_REPOSITORY,
    )

    assert permissions.can_claim
    assert permissions.can_create_pr
    assert permissions.can_edit
    assert permissions.allowed_commands == ("uv sync", "make check")
    assert permissions.mutation_commands == ()


def test_mutation_commands_guard_still_fires_on_dependency_update() -> None:
    """The conditional rule must not have deleted the dependency-update requirement."""
    payload = golden_envelope()
    payload["constraints"]["work_unit_id"] = WORK_UNIT_ID
    del payload["constraints"]["mutation_commands"]

    with pytest.raises(AuthorityError, match="mutation_commands"):
        validate_authority(
            AuthorityEnvelope.model_validate(payload),
            work_unit_id=WORK_UNIT_ID,
            target_repo=TARGET_REPOSITORY,
            current_repo=TARGET_REPOSITORY,
        )


def test_edit_shaped_envelope_still_requires_allowed_commands() -> None:
    """command.run authority without a command allowlist is unexecutable at finalize."""
    payload = golden_edit_envelope()
    payload["constraints"]["work_unit_id"] = EDIT_WORK_UNIT_ID
    del payload["constraints"]["allowed_commands"]

    with pytest.raises(AuthorityError, match="allowed_commands"):
        validate_authority(
            AuthorityEnvelope.model_validate(payload),
            work_unit_id=EDIT_WORK_UNIT_ID,
            target_repo=EDIT_TARGET_REPOSITORY,
            current_repo=EDIT_TARGET_REPOSITORY,
        )


def test_runner_grants_nothing_from_the_orchestrator_only_fields() -> None:
    """`change_class` drives the orchestrator's dispatch allowlist and `conformance`
    attests the unit's target repository. The runner derives no PERMISSION from
    either — capabilities remain the sole source — though since WS-P2.33
    `change_class == "dependency-update"` does tighten validation, requiring
    `mutation_commands` to be declared. On a well-formed envelope the derived
    permissions are identical with the fields present or stripped."""
    payload = golden_envelope()
    payload["constraints"]["work_unit_id"] = WORK_UNIT_ID
    envelope = AuthorityEnvelope.model_validate(payload)

    assert envelope.change_class == "dependency-update"
    assert envelope.conformance == {
        "accepted_standards": [],
        "standards_touched": ["project"],
        "status": "green",
    }

    stripped = {k: v for k, v in payload.items() if k not in {"change_class", "conformance"}}
    permissions = validate_authority(
        AuthorityEnvelope.model_validate(stripped),
        work_unit_id=WORK_UNIT_ID,
        target_repo=TARGET_REPOSITORY,
        current_repo=TARGET_REPOSITORY,
    )

    assert permissions == validate_authority(
        envelope,
        work_unit_id=WORK_UNIT_ID,
        target_repo=TARGET_REPOSITORY,
        current_repo=TARGET_REPOSITORY,
    )
