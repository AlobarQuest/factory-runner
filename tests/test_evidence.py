import pytest
from pydantic import ValidationError

from factory_runner.evidence import build_pr_opened_evidence, build_verification_evidence


def test_pr_opened_evidence_keeps_lease_token_out_of_payload() -> None:
    payload = build_pr_opened_evidence(
        revision_id="rev-1",
        ac_id="AC-001",
        attempt=1,
        lease_token="lease-token-123",
        source_revision="abc123",
        context_snapshot_id="snapshot-1",
        idempotency_key="idem-1",
        expected_version=5,
        pr_url="https://github.com/AlobarQuest/orchestrator/pull/99",
        head_sha="def456",
    )

    assert payload["evidence_type"] == "runner.pr.opened"
    assert payload["payload"]["pr_url"].endswith("/pull/99")
    assert payload["lease_token"] == "lease-token-123"
    assert "lease_token" not in payload["payload"]
    assert payload["stable_ref"].endswith("/pull/99")


def test_verification_evidence_accepts_only_structured_commands() -> None:
    payload = build_verification_evidence(
        revision_id="rev-1",
        ac_id="AC-002",
        attempt=1,
        lease_token="lease-token-456",
        source_revision="abc123",
        context_snapshot_id="snapshot-1",
        idempotency_key="idem-1",
        expected_version=5,
        commands=[
            {
                "command": "make check",
                "exit_code": 0,
                "summary": "passed",
                "run_url": "https://ci.example/runs/1",
            }
        ],
    )

    assert payload["evidence_type"] == "runner.verification"
    assert payload["payload"]["commands"][0]["summary"] == "passed"
    assert payload["payload"]["commands"][0]["run_url"] == "https://ci.example/runs/1"
    assert payload["stable_ref"] == "https://ci.example/runs/1"


def test_verification_evidence_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        build_verification_evidence(
            revision_id="rev-1",
            ac_id="AC-003",
            attempt=1,
            lease_token="lease-token-789",
            source_revision="abc123",
            context_snapshot_id="snapshot-1",
            idempotency_key="idem-1",
            expected_version=5,
            commands=[{"command": "make check", "exit_code": 0}],
        )


def test_verification_evidence_rejects_logs_field() -> None:
    with pytest.raises(ValidationError):
        build_verification_evidence(
            revision_id="rev-1",
            ac_id="AC-004",
            attempt=1,
            lease_token="lease-token-789",
            source_revision="abc123",
            context_snapshot_id="snapshot-1",
            idempotency_key="idem-1",
            expected_version=5,
            commands=[
                {
                    "command": "make check",
                    "exit_code": 0,
                    "summary": "passed",
                    "logs": "secret-bearing log text",
                }
            ],
        )
