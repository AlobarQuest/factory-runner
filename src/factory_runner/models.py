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
    model_config = ConfigDict(extra="forbid")

    work_unit: WorkUnitBrief
    package: PackageBrief
    authority: AuthorityBrief
    acceptance_criteria: list[dict[str, str]]
    readiness: ReadinessBrief
    target: TargetBrief
    standing_context: dict[str, object]
