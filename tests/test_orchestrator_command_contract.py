"""The WS-4.1 <-> WS-3.4 evidence seam contract, runner side.

The runner's evidence payloads were unit-tested against a `FakeClient` that accepted any
dict, and the orchestrator's `EvidenceCommand` was unit-tested against its own fixtures.
Neither side ever validated the other's shape, so the runner shipped payloads missing
`idempotency_key` and `expected_version` — both required by `CommandBase` — and every
evidence submission would have returned 422. The seam had never executed end to end. It
first ran in production on 2026-07-10, after `gh pr create` had already opened the PR.

`tests/fixtures/orchestrator_command_contract.json` is generated from
`orchestrator.api.schemas`. If the orchestrator adds a required field, `CONTRACT_SHA256`
below stops matching and this test fails rather than the next production run.
"""

import hashlib
import json
from pathlib import Path

from factory_runner.evidence import build_pr_opened_evidence, build_verification_evidence

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "orchestrator_command_contract.json"
CONTRACT_SHA256 = "15911dbbf9a0fd4dcd57cfecfc4b282f7fdee96285acbd5f5684c0ec7c161dae"

_COMMON = {
    "revision_id": "3f242a84-deaf-4cbd-bb66-1870235c6411",
    "ac_id": "AC-001",
    "attempt": 3,
    "lease_token": "lease-1",
    "source_revision": "cd1f0659",
    "expected_version": 12,
}


def _contract() -> dict:
    return json.loads(FIXTURE.read_text())


def test_contract_fixture_is_unmodified() -> None:
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert digest == CONTRACT_SHA256, (
        "the orchestrator's command schema changed; regenerate the fixture and re-read "
        "every runner payload before updating CONTRACT_SHA256"
    )


def test_pr_opened_evidence_satisfies_evidence_command() -> None:
    payload = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="factory-runner:unit-1:evidence:pr:a3",
        pr_url="https://github.com/AlobarQuest/orchestrator/pull/37",
        head_sha="cd1f0659",
        **_COMMON,
    )
    required = set(_contract()["EvidenceCommand"]["required"])
    assert required <= set(payload), f"missing required fields: {sorted(required - set(payload))}"


def test_verification_evidence_satisfies_evidence_command() -> None:
    payload = build_verification_evidence(
        context_snapshot_id=None,
        idempotency_key="factory-runner:unit-1:evidence:verification:a3",
        commands=[{"command": "uv sync", "exit_code": 0, "summary": "passed"}],
        **_COMMON,
    )
    required = set(_contract()["EvidenceCommand"]["required"])
    assert required <= set(payload), f"missing required fields: {sorted(required - set(payload))}"


def test_absent_context_snapshot_is_null_not_the_string_none() -> None:
    """`str(None)` == "None", which is not a UUID. A brief without a snapshot must send null."""
    payload = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="k",
        pr_url="https://example.invalid/pr/1",
        head_sha="cd1f0659",
        **_COMMON,
    )
    assert payload["context_snapshot_id"] is None
    assert payload["context_snapshot_id"] != "None"


def test_evidence_idempotency_keys_differ_per_evidence_type() -> None:
    """One key for both submissions would make the second replay the first."""
    pr = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="factory-runner:unit-1:evidence:pr:a3",
        pr_url="https://example.invalid/pr/1",
        head_sha="cd1f0659",
        **_COMMON,
    )
    verification = build_verification_evidence(
        context_snapshot_id=None,
        idempotency_key="factory-runner:unit-1:evidence:verification:a3",
        commands=[{"command": "uv sync", "exit_code": 0, "summary": "passed"}],
        **_COMMON,
    )
    assert pr["idempotency_key"] != verification["idempotency_key"]
    assert pr["evidence_type"] != verification["evidence_type"]


def test_optional_str_collapses_empty_and_none_to_null() -> None:
    """A claim without a snapshot yields "" on one path and None on another; both are
    rejected by `context_snapshot_id: UUID | None`. Attempt 5's 422 was the "" case."""
    from factory_runner.cli import _optional_str

    assert _optional_str("") is None
    assert _optional_str("   ") is None
    assert _optional_str(None) is None
    assert _optional_str("snap-123") == "snap-123"


def test_pr_evidence_with_absent_snapshot_omits_a_bogus_uuid() -> None:
    """The exact shape attempt 5 sent: context_snapshot_id must be null, never "" or 'None'."""
    from factory_runner.cli import _optional_str

    payload = build_pr_opened_evidence(
        context_snapshot_id=_optional_str(""),  # the empty string run.json actually held
        idempotency_key="factory-runner:unit-1:evidence:pr:a5",
        pr_url="https://github.com/AlobarQuest/orchestrator/pull/38",
        head_sha="cd1f0659",
        **_COMMON,
    )
    assert payload["context_snapshot_id"] is None
    assert payload["context_snapshot_id"] not in ("", "None")


def test_pr_evidence_folds_verification_into_its_payload() -> None:
    """The orchestrator keys current evidence on ac_id, so PR and verification cannot be
    two rows. Verification rides inside the single PR evidence payload."""
    payload = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="factory-runner:unit-1:evidence:pr:a6",
        pr_url="https://github.com/AlobarQuest/orchestrator/pull/38",
        head_sha="cd1f0659",
        verification=[
            {"command": "uv lock --upgrade", "exit_code": 0, "summary": "passed"},
            {"command": "uv sync", "exit_code": 0, "summary": "passed"},
            {"command": "uv lock --check", "exit_code": 0, "summary": "passed"},
        ],
        **_COMMON,
    )
    assert payload["evidence_type"] == "runner.pr.opened"
    assert payload["payload"]["pr_url"].endswith("/pull/38")
    commands = payload["payload"]["verification"]
    assert [c["command"] for c in commands] == ["uv lock --upgrade", "uv sync", "uv lock --check"]
    # required EvidenceCommand fields still present
    assert set(_contract()["EvidenceCommand"]["required"]) <= set(payload)


def test_pr_evidence_omits_verification_key_when_none() -> None:
    payload = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="k",
        pr_url="https://example.invalid/pr/1",
        head_sha="cd1f0659",
        verification=None,
        **_COMMON,
    )
    assert "verification" not in payload["payload"]


def test_pr_evidence_carries_supersede_flag() -> None:
    """A retry sets supersede=True so the orchestrator supersedes the current evidence for
    the AC rather than rejecting a first-write with evidence_already_exists."""
    first = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="k1",
        pr_url="https://example.invalid/pr/1",
        head_sha="cd1f0659",
        supersede=False,
        **_COMMON,
    )
    retry = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="k2",
        pr_url="https://example.invalid/pr/1",
        head_sha="cd1f0659",
        supersede=True,
        **_COMMON,
    )
    assert first["supersede"] is False
    assert retry["supersede"] is True


def test_supersede_defaults_false_for_a_first_attempt() -> None:
    payload = build_pr_opened_evidence(
        context_snapshot_id=None,
        idempotency_key="k",
        pr_url="https://example.invalid/pr/1",
        head_sha="cd1f0659",
        **_COMMON,
    )
    assert payload["supersede"] is False
