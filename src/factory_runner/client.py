from typing import Any

import httpx

from factory_runner.models import RunnerBrief


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


class OrchestratorClient:
    def __init__(
        self,
        *,
        base_url: str,
        credential_key_id: str,
        token: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
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
        expected_version: int | None = None,
    ) -> dict[str, Any]:
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
        reason: str,
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
        )
        return response.json()

    def submit_evidence(self, unit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", f"/api/v1/work-units/{unit_id}/evidence", json=payload)
        return response.json()

    def list_evidence(self, unit_id: str) -> list[dict[str, Any]]:
        response = self._request("GET", f"/api/v1/work-units/{unit_id}/evidence")
        return response.json()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        if response.status_code == 401:
            raise OrchestratorAuthError("orchestrator authentication failed")
        if response.status_code >= 400:
            raise OrchestratorError(
                f"orchestrator request failed: {response.status_code} {_describe_error(response)}"
            )
        return response
