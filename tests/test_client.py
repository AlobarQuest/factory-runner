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
