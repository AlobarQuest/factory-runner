from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuthorityEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: dict[str, str]
    budgets: dict[str, int | None] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class RunnerPermissions(BaseModel):
    allowed_tools: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    can_create_pr: bool
    can_submit_evidence: bool
    can_claim: bool
