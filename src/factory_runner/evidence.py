from typing import Any


def _base(
    *,
    revision_id: str,
    ac_id: str,
    attempt: int,
    lease_token: str,
    source_revision: str,
    context_snapshot_id: str,
    evidence_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "work_package_revision_id": revision_id,
        "ac_id": ac_id,
        "attempt": attempt,
        "lease_token": lease_token,
        "evidence_type": evidence_type,
        "stable_ref": payload.get("pr_url") or payload.get("run_url"),
        "payload": payload,
        "source_revision": source_revision,
        "context_snapshot_id": context_snapshot_id,
    }


def build_pr_opened_evidence(
    *,
    revision_id: str,
    ac_id: str,
    attempt: int,
    lease_token: str,
    source_revision: str,
    context_snapshot_id: str,
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
        evidence_type="runner.pr.opened",
        payload={"pr_url": pr_url, "head_sha": head_sha},
    )


def build_verification_evidence(
    *,
    revision_id: str,
    ac_id: str,
    attempt: int,
    lease_token: str,
    source_revision: str,
    context_snapshot_id: str,
    commands: list[dict[str, object]],
) -> dict[str, Any]:
    return _base(
        revision_id=revision_id,
        ac_id=ac_id,
        attempt=attempt,
        lease_token=lease_token,
        source_revision=source_revision,
        context_snapshot_id=context_snapshot_id,
        evidence_type="runner.verification",
        payload={"commands": commands},
    )
