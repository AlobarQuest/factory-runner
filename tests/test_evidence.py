from factory_runner.evidence import build_pr_opened_evidence, build_verification_evidence


def test_pr_opened_evidence_uses_redacted_payload_shape() -> None:
    payload = build_pr_opened_evidence(
        revision_id="rev-1",
        ac_id="AC-001",
        attempt=1,
        lease_token="lease-redacted",
        source_revision="abc123",
        context_snapshot_id="snapshot-1",
        pr_url="https://github.com/AlobarQuest/orchestrator/pull/99",
        head_sha="def456",
    )

    assert payload["evidence_type"] == "runner.pr.opened"
    assert payload["payload"]["pr_url"].endswith("/pull/99")
    assert "token" not in str(payload["payload"]).lower()


def test_verification_evidence_records_commands_without_full_logs() -> None:
    payload = build_verification_evidence(
        revision_id="rev-1",
        ac_id="AC-002",
        attempt=1,
        lease_token="lease-redacted",
        source_revision="abc123",
        context_snapshot_id="snapshot-1",
        commands=[{"command": "make check", "exit_code": 0, "summary": "passed"}],
    )

    assert payload["evidence_type"] == "runner.verification"
    assert payload["payload"]["commands"][0]["summary"] == "passed"
    assert "logs" not in payload["payload"]["commands"][0]
