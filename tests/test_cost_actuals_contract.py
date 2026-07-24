"""The cost-actuals seam contract (WS-P2.4 Increment 1), runner side.

`tests/fixtures/runner_cost_actuals.json` is byte-identical to the orchestrator's copy.
The two must change together — COST_ACTUALS_CONTRACT_SHA256 is identical in both tests.
"""

import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "runner_cost_actuals.json"
COST_ACTUALS_CONTRACT_SHA256 = "87004ad49dfbca020004d6c5ffa7dec2ce55923bbb0388604cc0bebde6f4386a"


def golden_cost_actuals() -> dict:
    return json.loads(FIXTURE.read_text())


def test_golden_cost_actuals_is_unchanged() -> None:
    canonical = json.dumps(golden_cost_actuals(), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == COST_ACTUALS_CONTRACT_SHA256


def test_cost_actuals_client_parameters_cover_the_contract() -> None:
    import inspect

    from factory_runner.client import OrchestratorClient

    # expected_version is hardcoded by the client (like pr_binding), never a caller-supplied
    # parameter -- exclude it from the expected parameter set.
    body_fields = set(golden_cost_actuals().keys())
    expected_parameters = {"unit_id"} | (body_fields - {"expected_version"})
    assert (
        set(inspect.signature(OrchestratorClient.cost_actuals).parameters) - {"self"}
        == expected_parameters
    )
