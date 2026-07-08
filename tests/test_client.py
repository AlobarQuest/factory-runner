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
