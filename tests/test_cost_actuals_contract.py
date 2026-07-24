"""The cost-actuals seam contract (WS-P2.4 Increment 1), runner side.

`tests/fixtures/runner_cost_actuals.json` is byte-identical to the orchestrator's copy.
The two must change together — COST_ACTUALS_CONTRACT_SHA256 is identical in both tests.
"""

import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "runner_cost_actuals.json"
COST_ACTUALS_CONTRACT_SHA256 = "1338e794272f983f3d0a4f82e36f6368b11a516b2a66b92d8bea9169fed02fac"


def golden_cost_actuals() -> dict:
    return json.loads(FIXTURE.read_text())


def test_golden_cost_actuals_is_unchanged() -> None:
    canonical = json.dumps(golden_cost_actuals(), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == COST_ACTUALS_CONTRACT_SHA256
