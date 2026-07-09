"""The WS-4.1 <-> WS-4.2 seam contract, runner side.

The orchestrator's dispatch adapter and this runner were each unit-tested against their
own fixtures, and those fixtures disagreed — so an envelope the orchestrator admitted was
rejected here, and the seam had never executed end to end.

`tests/fixtures/runner_authority_envelope.json` is a byte-identical copy of the file of the
same name in `AlobarQuest/orchestrator`. That repo asserts its decomposition path *produces*
this envelope and that its dispatch gate admits it; this module asserts `validate_authority`
*accepts* it. The two copies must change together — `CONTRACT_SHA256` is identical in both
tests, so a one-sided edit fails here.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from factory_runner.authority import validate_authority
from factory_runner.models import AuthorityEnvelope

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "runner_authority_envelope.json"
CONTRACT_SHA256 = "4ec8e88ab4e7d61003072bb15e505e4259fcef1def94675c6bc1b37a8bb17dc6"

WORK_UNIT_ID = "8302c75c-e083-5a67-bfd6-63021b90d6da"
TARGET_REPOSITORY = "AlobarQuest/brain"


def golden_envelope() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def test_golden_envelope_is_unchanged() -> None:
    """A one-sided edit here means the orchestrator's copy has silently drifted."""
    canonical = json.dumps(golden_envelope(), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == CONTRACT_SHA256


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
    assert permissions.allowed_commands == ("make check",)


def test_runner_grants_nothing_from_the_orchestrator_only_fields() -> None:
    """`change_class` drives the orchestrator's dispatch allowlist and `conformance`
    attests the unit's target repository. The runner carries both so the envelope
    validates as one document, but derives no permission from either."""
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
