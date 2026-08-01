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


def _pr_evidence(**overrides: object) -> dict:
    return build_pr_opened_evidence(
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
        **overrides,  # type: ignore[arg-type]
    )


def test_undeclared_brief_keys_reach_the_evidence_the_orchestrator_retains() -> None:
    """WS-P2.23 part C: the durable half of tolerate-and-report.

    An Actions log is not part of the orchestrator's record, so a log line alone would
    leave a runner silently behind the orchestrator serving it -- the invisibility this
    exists to prevent. The evidence payload is the record the runner already writes.

    Field NAMES only. The orchestrator's secret detector matches key names as well as
    values, and `unknown_brief_keys` contains none of its `SECRET_KEY_PARTS`.
    """
    payload = _pr_evidence(unknown_brief_keys=("cadence", "provenance"))["payload"]

    assert payload["unknown_brief_keys"] == ["cadence", "provenance"]
    assert payload["pr_url"].endswith("/pull/99")


def test_an_up_to_date_runner_adds_no_key_to_the_payload() -> None:
    """The ordinary payload is unchanged, so the shape only grows when there is drift."""
    assert "unknown_brief_keys" not in _pr_evidence()["payload"]
    assert "unknown_brief_keys" not in _pr_evidence(unknown_brief_keys=())["payload"]
