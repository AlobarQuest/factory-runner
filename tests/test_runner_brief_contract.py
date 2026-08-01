"""The runner-brief cross-repo contract.

The orchestrator deploys continuously; its consumers are SHA-pinned. Nothing tested
that boundary -- WS-6.4.0 closed exactly this gap for the authority envelope and left
the brief open, so the two ends could drift into mutually unsatisfiable shapes with
both suites green. On 2026-07-30 they did: the orchestrator began serving `enrichment`
against a `extra="forbid"` `RunnerBrief`, and every dispatch in the estate died at
brief-parse for a full day, unnoticed.

`RunnerBrief` is now `extra="allow"` and reports what it tolerated (WS-P2.23 part C).
Strict only ever guarded the safe case; the honest failure modes -- a renamed or
removed field -- are caught by required-field validation, which the fixture below
exercises independently of `extra`.

`tests/fixtures/runner_brief.json` is byte-identical to the orchestrator's copy
under the same name. CONTRACT_SHA256 makes a one-sided edit loud, and
`test_the_golden_brief_reaches_the_worker_prompt` makes an unused fixture loud --
a hash pin proves a file is unchanged and says nothing about whether any code
consumes it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from factory_runner.cli import _prompt
from factory_runner.models import (
    AuthorityEnvelope,
    RunnerBrief,
    WorkUnitBrief,
    unknown_brief_keys,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "runner_brief.json"
CONTRACT_SHA256 = "1cf3c51678ad411092816c9543cb15d6d45aeb021f6478c4a4c2541f378f66e4"


def golden_brief() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def test_golden_brief_is_unchanged() -> None:
    """A one-sided edit here means the orchestrator's copy has silently drifted."""
    canonical = json.dumps(golden_brief(), sort_keys=True, separators=(",", ":"))

    assert hashlib.sha256(canonical.encode()).hexdigest() == CONTRACT_SHA256


def test_the_runner_parses_the_golden_brief() -> None:
    """The assertion that never existed: the served brief, validated by its consumer."""
    brief = RunnerBrief.model_validate(golden_brief())

    assert brief.work_unit.id == "00000000-0000-0000-0000-000000000001"
    assert brief.enrichment is not None
    assert brief.enrichment["rules"][0]["severity"] == "BLOCK"


def test_the_golden_brief_reaches_the_worker_prompt() -> None:
    """Asserts the derivation, not the file: enrichment reaches what the model reads.

    Deleting the prompt's enrichment section would leave both tests above green.
    This one reds, which is the difference between pinning a shape and proving a use.
    """
    prompt = _prompt(RunnerBrief.model_validate(golden_brief()), ("make check",))

    assert "Never log secrets" in prompt
    assert "error-logging" in prompt


def test_a_brief_key_this_revision_does_not_declare_is_tolerated_and_named() -> None:
    """The 2026-07-30 outage, replayed: an orchestrator ahead of this runner.

    Under `extra="forbid"` this raised, and the run died before it claimed. It must now
    parse, leave every declared field intact, and say what it did not recognise -- the
    failure being guarded against is invisibility, so tolerating silently would be the
    same defect in the opposite direction.
    """
    ahead_of_us = golden_brief() | {"provenance": {"emitted_by": "orchestrator"}, "cadence": 3}

    brief = RunnerBrief.model_validate(ahead_of_us)

    assert unknown_brief_keys(brief) == ("cadence", "provenance")
    assert brief.work_unit.id == "00000000-0000-0000-0000-000000000001"
    assert brief.enrichment is not None


def test_a_brief_missing_a_declared_key_still_fails_loudly() -> None:
    """`extra="allow"` relaxes ADDITIONS only. A removal is the failure strict never owned.

    This is why relaxing costs nothing: required-field validation catches a renamed or
    removed field whatever `extra` says, and that is the direction that can actually
    break a run.
    """
    without_target = {key: value for key, value in golden_brief().items() if key != "target"}

    with pytest.raises(ValidationError):
        RunnerBrief.model_validate(without_target)


def test_the_relaxation_is_the_brief_alone() -> None:
    """Scope pin. The command and authority envelopes are different contracts.

    An undeclared key there is a caller sending something the runner will silently not
    honour, which is worth refusing. On the brief it was only ever an orchestrator
    getting ahead of a pinned consumer.
    """
    with pytest.raises(ValidationError):
        AuthorityEnvelope.model_validate({"capabilities": {}, "unexpected": 1})
    with pytest.raises(ValidationError):
        WorkUnitBrief.model_validate(golden_brief()["work_unit"] | {"unexpected": 1})
