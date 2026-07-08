from __future__ import annotations

import json
import os
from typing import Annotated, Any

import typer

from factory_runner.authority import validate_authority
from factory_runner.client import OrchestratorClient
from factory_runner.models import RunnerBrief

app = typer.Typer(no_args_is_help=True)


@app.callback(invoke_without_command=True)
def main() -> None:
    return None


def _sanitize_runner_brief(brief: RunnerBrief) -> dict[str, Any]:
    payload = brief.model_dump()
    constraints = payload.get("authority", {}).get("envelope", {}).get("constraints", {})
    if isinstance(constraints, dict):
        constraints.pop("secret_values", None)
    return payload


def _context_snapshot_id(brief: RunnerBrief) -> str | None:
    context_snapshot_id = brief.standing_context.get("context_snapshot_id")
    return context_snapshot_id if isinstance(context_snapshot_id, str) else None


def _lease_facts(brief: RunnerBrief) -> dict[str, Any]:
    return {
        "authority_fingerprint": brief.authority.fingerprint,
        "package_revision_id": brief.package.revision_id,
        "target_repository": brief.target.repository,
        "work_unit_id": brief.work_unit.id,
        "work_unit_version": brief.work_unit.version,
    }


@app.command()
def prepare(
    orchestrator_url: Annotated[str, typer.Option()],
    credential_key_id: Annotated[str, typer.Option()],
    work_unit_id: Annotated[str, typer.Option()],
    current_repository: Annotated[str, typer.Option()],
) -> None:
    token = os.environ.get("FACTORY_RUNNER_TOKEN")
    if not token:
        typer.echo("FACTORY_RUNNER_TOKEN environment variable is required", err=True)
        raise typer.Exit(code=1)

    client = OrchestratorClient(
        base_url=orchestrator_url,
        credential_key_id=credential_key_id,
        token=token,
    )
    brief = client.get_runner_brief(work_unit_id)
    permissions = validate_authority(
        brief.authority.envelope,
        work_unit_id=work_unit_id,
        target_repo=brief.target.repository,
        current_repo=current_repository,
    )

    payload = {
        "sanitized_brief": _sanitize_runner_brief(brief),
        "allowed_tools": list(permissions.allowed_tools),
        "allowed_commands": list(permissions.allowed_commands),
        "lease_facts": _lease_facts(brief),
        "context_snapshot_id": _context_snapshot_id(brief),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
