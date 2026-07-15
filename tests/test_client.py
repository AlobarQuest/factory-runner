import json
from typing import Literal, get_type_hints

import httpx
import pytest

from factory_runner.client import OrchestratorAuthError, OrchestratorClient


def test_client_sends_key_id_and_bearer_headers() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["Authorization"]
        seen["key"] = request.headers["X-Credential-Key-Id"]
        return httpx.Response(
            200,
            json={
                "work_unit": {
                    "id": "unit-1",
                    "state": "ready",
                    "version": 3,
                    "title": "Do work",
                    "outcome": "Work done",
                    "required_capability": "repository_write",
                    "max_attempts": 3,
                },
                "package": {
                    "id": "pkg",
                    "revision_id": "rev-1",
                    "revision": 1,
                    "content_hash": "sha256:abc",
                    "source_repository": "AlobarQuest/orchestrator",
                    "source_path": "package.yaml",
                    "source_commit": "abc123",
                },
                "authority": {
                    "fingerprint": "fingerprint",
                    "envelope": {
                        "capabilities": {"repo.read": "allowed"},
                        "constraints": {
                            "work_unit_id": "unit-1",
                            "target_repository": "AlobarQuest/orchestrator",
                        },
                    },
                },
                "acceptance_criteria": [],
                "readiness": {"status": "ready", "reasons": []},
                "target": {"repository": "AlobarQuest/orchestrator"},
                "standing_context": {},
            },
        )

    client = OrchestratorClient(
        base_url="https://sds.alobar.net",
        credential_key_id="factory-runner-github",
        token="redacted-token",
        transport=httpx.MockTransport(handler),
    )

    brief = client.get_runner_brief("unit-1")

    assert brief.work_unit.id == "unit-1"
    assert seen == {
        "authorization": "Bearer redacted-token",
        "key": "factory-runner-github",
    }


def test_client_raises_auth_error_on_401() -> None:
    client = OrchestratorClient(
        base_url="https://sds.alobar.net",
        credential_key_id="factory-runner-github",
        token="redacted-token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(401, json={"error": {"code": "authentication_failed"}})
        ),
    )

    with pytest.raises(OrchestratorAuthError):
        client.get_runner_brief("unit-1")


def test_client_renews_claim() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["payload"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "claim_id": "claim-1",
                "attempt": 2,
                "lease_token": "",
                "expires_at": "2026-07-08T12:15:00Z",
                "context_snapshot_id": "snapshot-1",
            },
        )

    client = OrchestratorClient(
        base_url="https://sds.alobar.net",
        credential_key_id="factory-runner-github",
        token="redacted-token",
        transport=httpx.MockTransport(handler),
    )

    result = client.renew(
        "unit-1",
        attempt=2,
        lease_token="lease-redacted",
        idempotency_key="local-heavy:unit-1:renew:a2",
        expected_version=5,
    )

    assert result["expires_at"] == "2026-07-08T12:15:00Z"
    assert seen["path"] == "/api/v1/work-units/unit-1/renew"
    assert seen["payload"] == (
        '{"attempt":2,"lease_token":"lease-redacted",'
        '"idempotency_key":"local-heavy:unit-1:renew:a2","expected_version":5}'
    )


def test_client_fails_work_unit() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.read())
        return httpx.Response(200, json={"unit_id": "unit-1", "state": "failed", "version": 6})

    client = OrchestratorClient(
        base_url="https://sds.alobar.net",
        credential_key_id="factory-runner-github",
        token="redacted-token",
        transport=httpx.MockTransport(handler),
    )

    result = client.fail(
        "unit-1",
        expected_version=5,
        idempotency_key="factory-runner:unit-1:fail:a1:coding_action_failed",
        attempt=1,
        lease_token="lease-redacted",
        reason="coding_action_failed",
    )

    assert result["state"] == "failed"
    assert seen == {
        "path": "/api/v1/work-units/unit-1/commands/fail",
        "payload": {
            "expected_version": 5,
            "idempotency_key": "factory-runner:unit-1:fail:a1:coding_action_failed",
            "attempt": 1,
            "lease_token": "lease-redacted",
            "reason": "coding_action_failed",
        },
    }


def test_client_records_pr_binding_with_exact_command_shape() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.read())
        return httpx.Response(200, json={"work_unit_id": "unit-1", "pr_number": 99})

    client = OrchestratorClient(
        base_url="https://sds.alobar.net",
        credential_key_id="factory-runner-github",
        token="redacted-token",
        transport=httpx.MockTransport(handler),
    )

    client.pr_binding(
        "unit-1",
        pr_number=99,
        head_sha="abc123",
        attempt=2,
        lease_token="lease-redacted",
        idempotency_key="factory-runner:unit-1:pr-binding:a2",
    )

    assert seen == {
        "path": "/api/v1/work-units/unit-1/pr-binding",
        "payload": {
            "expected_version": 0,
            "idempotency_key": "factory-runner:unit-1:pr-binding:a2",
            "pr_number": 99,
            "head_sha": "abc123",
            "attempt": 2,
            "lease_token": "lease-redacted",
        },
    }


def test_client_failure_reason_is_type_bounded() -> None:
    assert (
        get_type_hints(OrchestratorClient.fail)["reason"]
        == Literal["coding_action_failed", "finalization_failed"]
    )


def test_client_reclaims_expired_claim() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["payload"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "claim_id": "claim-2",
                "attempt": 3,
                "lease_token": "new-lease",
                "expires_at": "2026-07-08T12:30:00Z",
                "context_snapshot_id": "snapshot-2",
            },
        )

    client = OrchestratorClient(
        base_url="https://sds.alobar.net",
        credential_key_id="factory-runner-github",
        token="redacted-token",
        transport=httpx.MockTransport(handler),
    )

    result = client.reclaim_expired_claim(
        "unit-1",
        next_owner_id="factory-runner",
        idempotency_key="local-heavy:unit-1:reclaim",
        expected_version=7,
        standing_context={"context_snapshot_id": "snapshot-2"},
    )

    assert result["claim_id"] == "claim-2"
    assert seen["path"] == "/api/v1/work-units/unit-1/reclaim-expired-claim"
    assert seen["payload"] == (
        '{"next_owner_id":"factory-runner","idempotency_key":"local-heavy:unit-1:reclaim",'
        '"expected_version":7,"standing_context":{"context_snapshot_id":"snapshot-2"}}'
    )


def _response(status: int, body: object) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://x/api"))


def test_describe_error_reports_validation_loc_and_msg_without_input() -> None:
    """FastAPI's 422 `input` echoes the submitted value -- here, the lease token."""
    from factory_runner.client import _describe_error

    described = _describe_error(
        _response(
            422,
            {
                "detail": [
                    {
                        "type": "string_too_short",
                        "loc": ["body", "lease_token"],
                        "msg": "String should have at least 1 character",
                        "input": "super-secret-lease-token",
                    }
                ]
            },
        )
    )
    assert "body.lease_token" in described
    assert "at least 1 character" in described
    assert "super-secret-lease-token" not in described


def test_describe_error_reports_domain_error_code() -> None:
    from factory_runner.client import _describe_error

    described = _describe_error(
        _response(
            409, {"error": {"code": "version_conflict", "message": "work unit version changed"}}
        )
    )
    assert "version_conflict" in described
    assert "work unit version changed" in described


def test_describe_error_survives_an_unparseable_body() -> None:
    from factory_runner.client import _describe_error

    response = httpx.Response(
        500, text="<html>502</html>", request=httpx.Request("POST", "https://x/api")
    )
    assert _describe_error(response) == "(unparseable body)"
