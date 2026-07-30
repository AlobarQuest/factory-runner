"""The runner-brief cross-repo contract.

`RunnerBrief` is `extra="forbid"`: a key the orchestrator adds and this repo does
not know about raises at parse time, which kills every run at claim rather than
degrading. Nothing tested that across the boundary -- WS-6.4.0 closed exactly this
gap for the authority envelope and left the brief open, so the two ends could
drift into mutually unsatisfiable shapes with both suites green.

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

from factory_runner.cli import _prompt
from factory_runner.models import RunnerBrief

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
