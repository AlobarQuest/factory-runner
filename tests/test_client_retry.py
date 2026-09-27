"""The end-of-run calls must survive the orchestrator's own redeploy.

The orchestrator's Coolify swap is not zero-downtime: measured 2026-09-01, the proxy answered
`no available server` for about 22 seconds between the old container stopping and the new one
serving. A run whose finalize or fail landed in that gap raised on the first 502/503, stranded
its unit in `executing`, and spent an attempt -- and because `fail-run` fails the same way as
`finalize-run`, it could not even report the failure (GAP-4 attempt 2, 2026-07-29).

Retry is bounded, applies only to transient failures (502/503/504 and transport errors), and
only to calls the orchestrator replays: every GET, and the POSTs that carry an idempotency key
the orchestrator answers with the original result. Claim, renew and reclaim are deliberately
NOT retried -- their replays withhold the lease token, so a retry after a committed-but-lost
response cannot recover what the first attempt granted.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from factory_runner.client import OrchestratorAuthError, OrchestratorClient, OrchestratorError


class _FakeClock:
    """Time that moves only when the client sleeps, so a test never waits."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _failing_then(
    failures: list[int | type[httpx.TransportError]], final: httpx.Response
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """A handler that fails with each entry in turn, then answers `final` forever."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        index = len(seen) - 1
        if index < len(failures):
            failure = failures[index]
            if isinstance(failure, int):
                return httpx.Response(failure, text="no available server")
            raise failure("simulated", request=request)
        return final

    return handler, seen


def _client(
    handler: Callable[[httpx.Request], httpx.Response], clock: _FakeClock, log: list[str]
) -> OrchestratorClient:
    return OrchestratorClient(
        base_url="https://sds.alobar.net",
        credential_key_id="factory-runner-github",
        token="redacted-token",
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        log=log.append,
    )


def _submit(client: OrchestratorClient) -> dict[str, Any]:
    return client.submit(
        "unit-1",
        {
            "expected_version": 5,
            "idempotency_key": "factory-runner:unit-1:submit:a1",
            "attempt": 1,
            "lease_token": "lease",
        },
    )


_OK = httpx.Response(200, json={"state": "submitted", "version": 6})


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_transient_gateway_status_is_retried_until_it_succeeds(status: int) -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([status, status], _OK)

    result = _submit(_client(handler, clock, log))

    assert result == {"state": "submitted", "version": 6}
    assert len(seen) == 3
    assert len(log) == 2
    # The retried request is the SAME operation: the orchestrator replays by key, so a body
    # that changed between attempts would be an idempotency conflict, not a retry.
    assert {request.content for request in seen} == {seen[0].content}


@pytest.mark.parametrize(
    "error", [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ReadError]
)
def test_a_transport_error_is_retried_until_it_succeeds(error: type[httpx.TransportError]) -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([error], _OK)

    assert _submit(_client(handler, clock, log))["version"] == 6
    assert len(seen) == 2


@pytest.mark.parametrize("status", [400, 404, 409, 422])
def test_a_client_error_is_never_retried(status: int) -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([status], _OK)

    with pytest.raises(OrchestratorError, match=str(status)):
        _submit(_client(handler, clock, log))
    assert len(seen) == 1
    assert clock.sleeps == []


def test_an_internal_server_error_is_not_retried() -> None:
    """500 is the application answering, not the proxy failing to reach it: a bug, not a gap."""
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([500], _OK)

    with pytest.raises(OrchestratorError, match="500"):
        _submit(_client(handler, clock, log))
    assert len(seen) == 1


def test_a_401_is_an_auth_error_and_is_not_retried() -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([401], _OK)

    with pytest.raises(OrchestratorAuthError):
        _submit(_client(handler, clock, log))
    assert len(seen) == 1


def test_exhausting_the_budget_raises_the_original_status_error() -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([503] * 1000, _OK)

    with pytest.raises(OrchestratorError, match="503"):
        _submit(_client(handler, clock, log))
    # Bounded: the loop stopped, and the waiting it did fits inside the budget.
    assert 2 < len(seen) < 20
    assert sum(clock.sleeps) <= OrchestratorClient.RETRY_BUDGET_SECONDS


def test_exhausting_the_budget_raises_the_original_transport_error() -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([httpx.ConnectError] * 1000, _OK)

    with pytest.raises(httpx.ConnectError):
        _submit(_client(handler, clock, log))
    assert 2 < len(seen) < 20


def test_the_backoff_is_exponential_capped_and_outlasts_the_swap_gap() -> None:
    clock, log = _FakeClock(), []
    handler, _seen = _failing_then([503] * 1000, _OK)

    with pytest.raises(OrchestratorError):
        _submit(_client(handler, clock, log))

    assert clock.sleeps[:6] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    assert max(clock.sleeps) == 30.0
    # The measured gap is ~22 seconds; the budget must cover it several times over.
    assert sum(clock.sleeps) >= 100.0


def test_each_retry_is_logged_without_the_request_body() -> None:
    clock, log = _FakeClock(), []
    handler, _seen = _failing_then([503], _OK)

    _submit(_client(handler, clock, log))

    assert len(log) == 1
    assert "POST" in log[0] and "/commands/submit" in log[0] and "503" in log[0]
    assert "lease" not in log[0]


def test_a_get_is_retried() -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([502], httpx.Response(200, json=[]))

    assert _client(handler, clock, log).list_evidence("unit-1") == []
    assert len(seen) == 2


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda c: c.pr_binding(
                "unit-1",
                pr_number=1,
                head_sha="abc",
                attempt=1,
                lease_token="l",
                idempotency_key="k",
            ),
            id="pr_binding",
        ),
        pytest.param(
            lambda c: c.submit_evidence("unit-1", {"idempotency_key": "k"}), id="submit_evidence"
        ),
        pytest.param(
            lambda c: c.cost_actuals(
                "unit-1",
                attempt=1,
                lease_token="l",
                cost_known=False,
                llm_calls=None,
                num_turns=None,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                idempotency_key="k",
            ),
            id="cost_actuals",
        ),
        pytest.param(
            lambda c: c.fail(
                "unit-1",
                expected_version=5,
                idempotency_key="k",
                attempt=1,
                lease_token="l",
                reason="finalization_failed",
            ),
            id="fail",
        ),
    ],
)
def test_every_end_of_run_post_is_retried(call: Callable[[OrchestratorClient], Any]) -> None:
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([503], httpx.Response(200, json={}))

    call(_client(handler, clock, log))

    assert len(seen) == 2


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda c: c.claim(
                "unit-1", expected_version=1, idempotency_key="k", standing_context={}
            ),
            id="claim",
        ),
        pytest.param(
            lambda c: c.renew(
                "unit-1", attempt=1, lease_token="l", idempotency_key="k", expected_version=1
            ),
            id="renew",
        ),
        pytest.param(
            lambda c: c.reclaim_expired_claim("unit-1", next_owner_id="o", idempotency_key="k"),
            id="reclaim",
        ),
    ],
)
def test_a_lease_granting_call_is_not_retried(call: Callable[[OrchestratorClient], Any]) -> None:
    """Their replays withhold the lease token, so a retry cannot recover a lost grant."""
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([503], httpx.Response(200, json={}))

    with pytest.raises(OrchestratorError, match="503"):
        call(_client(handler, clock, log))
    assert len(seen) == 1


def test_a_retried_command_without_an_idempotency_key_is_refused_before_sending() -> None:
    """Retrying a POST the orchestrator cannot replay could perform it twice."""
    clock, log = _FakeClock(), []
    handler, seen = _failing_then([], _OK)

    with pytest.raises(ValueError, match="idempotency_key"):
        _client(handler, clock, log).command("unit-1", "submit", {"expected_version": 5})
    assert seen == []
