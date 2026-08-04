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

The THIRD fixture, `runner_envelope_contract.json`, pins the rules neither envelope can:
every capability in both of them is declared "allowed", so their bytes are satisfied by a
one-term level set and say nothing about "prohibited". It also pins this model's declared
FIELD set, which matters because `extra="forbid"` makes an undeclared key a pydantic crash
before `validate_authority` ever runs — and the orchestrator's own `KNOWN_FIELDS` differs
from it by exactly one member (`unknown_fields`, which that repo emits from `normalized()`
and this model rejects). Both sides key their gate on THIS file, not on their own
vocabulary. Until WS-P2.34 the orchestrator validated capability NAMES and never LEVELS or
top-level FIELDS, and admitted envelopes this module refuses.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from factory_runner.authority import (
    SUPPORTED_CAPABILITIES,
    SUPPORTED_LEVELS,
    AuthorityError,
    validate_authority,
)
from factory_runner.capability_vocabulary import CAPABILITY_VOCABULARY
from factory_runner.models import AuthorityEnvelope

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "runner_authority_envelope.json"
CONTRACT_SHA256 = "049ab53e2b257fa3d7eb24748a4278ffc7e0e91f8174b05220eefd7d526e5a56"

FIXTURE_EDIT = Path(__file__).resolve().parent / "fixtures" / "runner_authority_envelope_edit.json"
CONTRACT_SHA256_EDIT = "90b73de69bdd9d5ee88be38b0a0ac2eeff1e4bb467ec72062cd1b70f49888f6e"

FIXTURE_CONTRACT = Path(__file__).resolve().parent / "fixtures" / "runner_envelope_contract.json"
CONTRACT_SHA256_SURFACE = "c518e3a26a1e0d109ece3ccccaca0bc2fc7a069e26cba470e1f940742a55a1c0"

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


def test_golden_capability_levels_are_unchanged() -> None:
    canonical = json.dumps(json.loads(FIXTURE_CONTRACT.read_text()), sort_keys=True)

    assert hashlib.sha256(canonical.encode()).hexdigest() == CONTRACT_SHA256_SURFACE


def test_shipped_levels_match_the_pinned_contract() -> None:
    """The level vocabulary is a cross-repo contract, pinned here by equality.

    A hash pin proves the file is unchanged; it says nothing about whether anything reads it.
    This asserts the constant `_validate_capabilities` actually consults. The orchestrator
    asserts the same equality against its own RUNNER_CAPABILITY_LEVELS and a byte-identical
    copy, so dropping a term on either side reds the side that was not updated. The behavioural
    floor under "prohibited" is `test_authority.py::test_maps_prohibited_repo_edit_to_false_
    permission` and the CLI tests — do not delete those on the theory that this pin covers them.
    """
    assert SUPPORTED_LEVELS == frozenset(json.loads(FIXTURE_CONTRACT.read_text())["levels"])


def test_declared_envelope_fields_match_the_pinned_contract() -> None:
    """DERIVED, not restated: the field set comes straight out of the pydantic model.

    This is the half the orchestrator cannot compute for itself — its gate must refuse any
    top-level key this model does not declare, and reading `KNOWN_FIELDS` instead is off by one
    in the fail-open direction. Adding or renaming a field on `AuthorityEnvelope` reds this
    until the fixture moves with it, and the orchestrator's copy reds until it does too.
    """
    assert set(AuthorityEnvelope.model_fields) == set(
        json.loads(FIXTURE_CONTRACT.read_text())["envelope_fields"]
    )


def test_a_normalized_orchestrator_envelope_is_rejected_by_this_model() -> None:
    """Why the field set is pinned at all: the orchestrator's own normalized form is not
    parseable here. `normalized()` emits `unknown_fields`; this model forbids it, and the
    failure is a pydantic ValidationError rather than a named AuthorityError."""
    payload = {**json.loads(FIXTURE_EDIT.read_text()), "unknown_fields": []}

    with pytest.raises(ValidationError, match="unknown_fields"):
        AuthorityEnvelope.model_validate(payload)


def test_a_package_authority_level_is_refused() -> None:
    """The rule the level contract pins, negative direction.

    `requires_approval` is the orchestrator's PACKAGE-authority vocabulary, which a human
    projects into unit capabilities by hand. It is not a level this runner accepts, and until
    WS-P2.34 the orchestrator would admit it — the run then died here with its ordinal spent.
    """
    payload = json.loads(FIXTURE_EDIT.read_text())
    payload["capabilities"]["command.run"] = "requires_approval"
    envelope = AuthorityEnvelope.model_validate(payload)

    with pytest.raises(AuthorityError, match="unsupported capability level"):
        validate_authority(
            envelope,
            work_unit_id=payload["constraints"]["work_unit_id"],
            target_repo=payload["constraints"]["target_repository"],
            current_repo=payload["constraints"]["target_repository"],
        )
