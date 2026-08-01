from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuthorityEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: dict[str, str]
    budgets: dict[str, int | None] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    # Orchestrator-owned: the change class its dispatch allowlist admits on, and the
    # conformance attested for this unit's target repository. The runner carries both so
    # the served envelope validates as one document, and grants nothing from either —
    # capabilities remain the sole source of runner permissions.
    change_class: str | None = None
    conformance: dict[str, Any] | None = None


class RunnerPermissions(BaseModel):
    allowed_tools: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    mutation_commands: tuple[str, ...]
    can_edit: bool
    can_create_pr: bool
    can_submit_evidence: bool
    can_claim: bool


class WorkUnitBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    state: str
    version: int
    title: str
    outcome: str
    required_capability: str
    max_attempts: int


class PackageBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    revision_id: str
    revision: int
    content_hash: str
    source_repository: str
    source_path: str
    source_commit: str


class AuthorityBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    envelope: AuthorityEnvelope


class ReadinessBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reasons: list[dict[str, str | None]]


class TargetBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str


class RunnerBrief(BaseModel):
    # `extra="allow"`, deliberately, and ONLY here — the command and authority envelopes
    # keep `extra="forbid"`.
    #
    # Strict guarded only the safe case. An old runner cannot use a field it does not know
    # about, so forbidding additions protected nothing; a RENAMED or REMOVED field is caught
    # by required-field validation whatever `extra` says. What strict actually did was turn
    # "I'll ignore this" into "every dispatch in the estate dies at brief-parse" — which is
    # exactly what happened for a full day from 2026-07-30, unnoticed.
    #
    # Plain relaxation would turn it into silence instead, which is the same defect wearing
    # the opposite coat. So: tolerate AND report. `unknown_brief_keys` reads what landed
    # here, and the runner carries it into the evidence the orchestrator retains.
    model_config = ConfigDict(extra="allow")

    work_unit: WorkUnitBrief
    package: PackageBrief
    authority: AuthorityBrief
    acceptance_criteria: list[dict[str, str]]
    readiness: ReadinessBrief
    target: TargetBrief
    standing_context: dict[str, object]
    # Governed knowledge projected per change class at authoring time (SDS WS-P2.12).
    # Optional so a brief served by an orchestrator that predates the field still
    # parses. It grants nothing: capabilities remain the sole source of permissions.
    enrichment: dict[str, Any] | None = None


def unknown_brief_keys(brief: RunnerBrief) -> tuple[str, ...]:
    """Top-level brief keys this runner revision does not declare.

    Non-empty means the orchestrator is ahead of the pinned runner. The run proceeds —
    an undeclared key grants nothing and is not needed — but the names travel into the
    evidence the orchestrator retains, so the drift is a record rather than a log line
    in an Actions run nobody reads.
    """
    return tuple(sorted(brief.model_extra or {}))
