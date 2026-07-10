from typing import Any

from pydantic import BaseModel, ConfigDict


class VerificationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    exit_code: int
    summary: str
    run_url: str | None = None
    check_url: str | None = None


def build_verification_command_payload(command: dict[str, Any]) -> dict[str, Any]:
    return VerificationCommand.model_validate(command).model_dump(exclude_none=True)


def _base(
    *,
    revision_id: str,
    ac_id: str,
    attempt: int,
    lease_token: str,
    source_revision: str,
    context_snapshot_id: str | None,
    idempotency_key: str,
    expected_version: int,
    evidence_type: str,
    stable_ref: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    # The orchestrator's EvidenceCommand extends CommandBase, so idempotency_key and
    # expected_version are required. Omitting them made every evidence submission a 422 --
    # a seam neither side's fixtures exercised.
    return {
        "work_package_revision_id": revision_id,
        "ac_id": ac_id,
        "attempt": attempt,
        "lease_token": lease_token,
        "evidence_type": evidence_type,
        "stable_ref": stable_ref,
        "payload": payload,
        "source_revision": source_revision,
        # `str(None)` is the string "None", which is not a UUID. A brief without a context
        # snapshot must send null, not a stringified None.
        "context_snapshot_id": context_snapshot_id,
        "idempotency_key": idempotency_key,
        "expected_version": expected_version,
    }


def build_pr_opened_evidence(
    *,
    revision_id: str,
    ac_id: str,
    attempt: int,
    lease_token: str,
    source_revision: str,
    context_snapshot_id: str | None,
    idempotency_key: str,
    expected_version: int,
    pr_url: str,
    head_sha: str,
) -> dict[str, Any]:
    return _base(
        revision_id=revision_id,
        ac_id=ac_id,
        attempt=attempt,
        lease_token=lease_token,
        source_revision=source_revision,
        context_snapshot_id=context_snapshot_id,
        idempotency_key=idempotency_key,
        expected_version=expected_version,
        evidence_type="runner.pr.opened",
        stable_ref=pr_url,
        payload={"pr_url": pr_url, "head_sha": head_sha},
    )


def build_verification_evidence(
    *,
    revision_id: str,
    ac_id: str,
    attempt: int,
    lease_token: str,
    source_revision: str,
    context_snapshot_id: str | None,
    idempotency_key: str,
    expected_version: int,
    commands: list[dict[str, object]],
) -> dict[str, Any]:
    command_payloads = [build_verification_command_payload(command) for command in commands]
    stable_ref = next(
        (
            command.get("run_url") or command.get("check_url")
            for command in command_payloads
            if command.get("run_url") or command.get("check_url")
        ),
        None,
    )
    return _base(
        revision_id=revision_id,
        ac_id=ac_id,
        attempt=attempt,
        lease_token=lease_token,
        source_revision=source_revision,
        context_snapshot_id=context_snapshot_id,
        idempotency_key=idempotency_key,
        expected_version=expected_version,
        evidence_type="runner.verification",
        stable_ref=stable_ref,
        payload={"commands": command_payloads},
    )
