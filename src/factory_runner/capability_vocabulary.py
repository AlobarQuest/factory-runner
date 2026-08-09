"""The capability names an authority envelope may declare.

A module literal rather than a read of `tests/fixtures/runner_envelope_contract.json`, which is
the byte-identical cross-repo DECLARATION this set is pinned to: `tests/` is not in the wheel, so
a vocabulary that loaded the fixture would work in the suite and fail on the runner.
`test_orchestrator_envelope_contract.py` asserts the two agree, which is the same arrangement
`SUPPORTED_LEVELS` and the envelope field set already use.

The golden ENVELOPES are specimens of dispatched work and are asserted to be subsets of this;
they are deliberately not its source, or a name the factory has never dispatched would have to be
written into a record of what it did.
"""

from typing import Final

CAPABILITY_VOCABULARY: Final = {
    "runner": (
        "command.run",
        "github.pr.create",
        # ADR-0020 (orchestrator), WS-P3.7 Increment 3. Recognised so an envelope carrying it
        # PARSES; nothing here derives a permission from it, and `validate_authority` returns no
        # field that reads it. The runner still cannot land a pull request, and the pull-request
        # body still says so. Naming it is what lets a human grant it per unit in the envelope,
        # the way every other capability is granted, instead of it being an ambient property of
        # the factory. The orchestrator may not serve the name until this revision is pinned by
        # every caller -- this model forbids extras and refuses an unknown capability outright,
        # so a one-sided addition kills every dispatch of that unit.
        "github.pr.merge",  # no envelope has ever carried it
        "orchestrator.claim",
        "orchestrator.evidence.write",
        "repo.edit",
        "repo.read",
    )
}
