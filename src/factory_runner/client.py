import sys
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx

from factory_runner.models import RunnerBrief

FailureReason = Literal["coding_action_failed", "finalization_failed"]


def _describe_error(response: httpx.Response) -> str:
    """Summarize an error response WITHOUT echoing the values we submitted.

    A discarded body is why a 422 read as an opaque number for two production runs. But
    FastAPI's 422 detail carries an `input` field holding the exact value that failed
    validation -- for this runner that includes the lease token. Report each failure's
    `loc` and `msg` only; never `input`, never `ctx`.
    """
    try:
        body = response.json()
    except ValueError:
        return "(unparseable body)"
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("code"):
            return f"{error['code']}: {error.get('message', '')}".strip()
        detail = body.get("detail")
        if isinstance(detail, list):
            parts = [
                f"{'.'.join(str(x) for x in item.get('loc', []))}: {item.get('msg', '')}"
                for item in detail
                if isinstance(item, dict)
            ]
            if parts:
                return "; ".join(parts)
        if isinstance(detail, str):
            return detail
    return "(no error detail)"


class OrchestratorError(RuntimeError):
    pass


class OrchestratorAuthError(OrchestratorError):
    pass


# The statuses a proxy answers when it cannot reach the application: the orchestrator's own
# redeploy is not zero-downtime (~22 s of `no available server`, measured 2026-09-01). 500 is
# the application answering, so it is a defect to report, not a gap to wait out.
RETRYABLE_STATUSES = frozenset({502, 503, 504})

# Transport failures that mean "the request did not get a response", not "the request is
# malformed". A bad URL scheme (UnsupportedProtocol) or a local protocol error is a
# configuration defect that no amount of waiting fixes, so the narrower subclasses are named.
RETRYABLE_TRANSPORT_ERRORS: tuple[type[Exception], ...] = (
    httpx.NetworkError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class OrchestratorClient:
    # No retry STARTS after this much elapsed waiting; one request timeout may follow it, so
    # the worst case per call is about three minutes. Sized to outlast the measured swap gap
    # several times over while keeping a genuinely-down orchestrator well inside the job's
    # 60-minute timeout.
    RETRY_BUDGET_SECONDS = 150.0
    RETRY_MAX_DELAY_SECONDS = 30.0

    def __init__(
        self,
        *,
        base_url: str,
        credential_key_id: str,
        token: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = _stderr,
    ) -> None:
        self._sleep = sleep
        self._monotonic = monotonic
        self._log = log
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "X-Credential-Key-Id": credential_key_id,
            },
            timeout=30.0,
            transport=transport,
        )

    def get_runner_brief(self, unit_id: str) -> RunnerBrief:
        response = self._request("GET", f"/api/v1/work-units/{unit_id}/runner-brief")
        return RunnerBrief.model_validate(response.json())

    def get_evidence_pack_markdown(self, unit_id: str) -> str:
        response = self._request("GET", f"/api/v1/work-units/{unit_id}/evidence-pack/markdown")
        return response.text

    def claim(
        self,
        unit_id: str,
        *,
        expected_version: int,
        idempotency_key: str,
        standing_context: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/v1/work-units/{unit_id}/claim",
            json={
                "expected_version": expected_version,
                "idempotency_key": idempotency_key,
                "standing_context": standing_context,
            },
        )
        return response.json()

    def renew(
        self,
        unit_id: str,
        *,
        attempt: int,
        lease_token: str,
        idempotency_key: str,
        expected_version: int,
    ) -> dict[str, Any]:
        """`expected_version` is REQUIRED, and its default is what made renew dead on arrival.

        The orchestrator's `RenewCommand` inherits `expected_version: int = Field(ge=0)` from
        `CommandBase` -- required, no default -- so posting `null` is a 422 every single time.
        With the parameter defaulted to None here and never passed by the CLI, `local-heavy-renew`
        had never once succeeded, and "claim at the evidence push" was inherited through handoffs
        as a preference when it was only ever a workaround for a dead command. Keeping the
        parameter required is what stops that recurring: an omission is now a TypeError at the
        call site rather than a 422 at the far end of the wire.
        """
        response = self._request(
            "POST",
            f"/api/v1/work-units/{unit_id}/renew",
            json={
                "attempt": attempt,
                "lease_token": lease_token,
                "idempotency_key": idempotency_key,
                "expected_version": expected_version,
            },
        )
        return response.json()

    def reclaim_expired_claim(
        self,
        unit_id: str,
        *,
        next_owner_id: str,
        idempotency_key: str,
        expected_version: int | None = None,
        standing_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/v1/work-units/{unit_id}/reclaim-expired-claim",
            json={
                "next_owner_id": next_owner_id,
                "idempotency_key": idempotency_key,
                "expected_version": expected_version,
                "standing_context": standing_context,
            },
        )
        return response.json()

    def start(self, unit_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.command(unit_id, "start", payload or {})

    def submit(self, unit_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.command(unit_id, "submit", payload or {})

    def fail(
        self,
        unit_id: str,
        *,
        expected_version: int,
        idempotency_key: str,
        attempt: int,
        lease_token: str,
        reason: FailureReason,
    ) -> dict[str, Any]:
        return self.command(
            unit_id,
            "fail",
            {
                "expected_version": expected_version,
                "idempotency_key": idempotency_key,
                "attempt": attempt,
                "lease_token": lease_token,
                "reason": reason,
            },
        )

    def command(self, unit_id: str, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/v1/work-units/{unit_id}/commands/{command}",
            json=payload,
            idempotent=True,
        )
        return response.json()

    def submit_evidence(self, unit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST", f"/api/v1/work-units/{unit_id}/evidence", json=payload, idempotent=True
        )
        return response.json()

    def pr_binding(
        self,
        unit_id: str,
        *,
        pr_number: int,
        head_sha: str,
        attempt: int,
        lease_token: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/v1/work-units/{unit_id}/pr-binding",
            json={
                "expected_version": 0,
                "idempotency_key": idempotency_key,
                "pr_number": pr_number,
                "head_sha": head_sha,
                "attempt": attempt,
                "lease_token": lease_token,
            },
            idempotent=True,
        )
        return response.json()

    def cost_actuals(
        self,
        unit_id: str,
        *,
        attempt: int,
        lease_token: str,
        cost_known: bool,
        llm_calls: int | None,
        num_turns: int | None,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/v1/work-units/{unit_id}/cost-actuals",
            json={
                "expected_version": 0,
                "idempotency_key": idempotency_key,
                "attempt": attempt,
                "lease_token": lease_token,
                "cost_known": cost_known,
                "llm_calls": llm_calls,
                "num_turns": num_turns,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            },
            idempotent=True,
        )
        return response.json()

    def list_evidence(self, unit_id: str) -> list[dict[str, Any]]:
        response = self._request("GET", f"/api/v1/work-units/{unit_id}/evidence")
        return response.json()

    def _request(
        self, method: str, path: str, *, idempotent: bool = False, **kwargs: Any
    ) -> httpx.Response:
        """Send one logical request, retrying transient failures when a retry is safe.

        Safe means the orchestrator answers a repeat with the original result: every GET, and a
        POST marked `idempotent` -- which must carry the idempotency key the orchestrator
        replays by, or it is refused here before anything is sent. A retry after a response was
        lost therefore replays rather than performing the operation twice. Claim, renew and
        reclaim are left unmarked on purpose: their replays withhold the lease token, so a retry
        cannot recover a grant whose response was lost.
        """
        if idempotent and method != "GET":
            body = kwargs.get("json")
            key = body.get("idempotency_key") if isinstance(body, dict) else None
            if not isinstance(key, str) or not key:
                raise ValueError(f"{method} {path} is marked idempotent but has no idempotency_key")
        retryable = method == "GET" or idempotent
        started = self._monotonic()
        retries = 0
        while True:
            try:
                response = self._client.request(method, path, **kwargs)
            except RETRYABLE_TRANSPORT_ERRORS as error:
                delay = self._retry_delay(retryable, started, retries)
                if delay is None:
                    raise
                failure = type(error).__name__
            else:
                if response.status_code not in RETRYABLE_STATUSES:
                    return self._checked(response)
                delay = self._retry_delay(retryable, started, retries)
                if delay is None:
                    return self._checked(response)
                failure = str(response.status_code)
            retries += 1
            self._log(
                f"orchestrator {method} {path} failed ({failure}); retry {retries} in {delay:g}s"
            )
            self._sleep(delay)

    def _retry_delay(self, retryable: bool, started: float, retries: int) -> float | None:
        """The wait before the next attempt, or None when no further attempt may start."""
        if not retryable:
            return None
        delay = min(2.0**retries, self.RETRY_MAX_DELAY_SECONDS)
        if self._monotonic() - started + delay > self.RETRY_BUDGET_SECONDS:
            return None
        return delay

    @staticmethod
    def _checked(response: httpx.Response) -> httpx.Response:
        if response.status_code == 401:
            raise OrchestratorAuthError("orchestrator authentication failed")
        if response.status_code >= 400:
            raise OrchestratorError(
                f"orchestrator request failed: {response.status_code} {_describe_error(response)}"
            )
        return response
