from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any


class CodingResultError(ValueError):
    """Raised when a coding action result cannot safely be accepted."""


@dataclass(frozen=True)
class CodingResult:
    subtype: str
    is_error: bool


def _execution_records(path: Path) -> list[dict[str, Any]]:
    try:
        content = path.read_text()
    except OSError as error:
        raise CodingResultError("coding result is unavailable") from error

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        records: list[object] = []
        try:
            for line in content.splitlines():
                if line.strip():
                    records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise CodingResultError("coding result is malformed") from error
    else:
        if isinstance(parsed, list):
            records = parsed
        elif isinstance(parsed, dict):
            records = [parsed]
        else:
            raise CodingResultError("coding result is malformed")

    if not all(isinstance(record, dict) for record in records):
        raise CodingResultError("coding result is malformed")
    return [record for record in records if isinstance(record, dict)]


def classify_execution_file(path: Path) -> CodingResult:
    """Accept exactly one non-error terminal success from an action execution log."""
    results = [record for record in _execution_records(path) if record.get("type") == "result"]
    if len(results) != 1:
        raise CodingResultError("coding result is not a single terminal result")

    result = results[0]
    subtype = result.get("subtype")
    is_error = result.get("is_error", False)
    if not isinstance(subtype, str) or not isinstance(is_error, bool):
        raise CodingResultError("coding result is malformed")
    if subtype != "success" or is_error is True:
        raise CodingResultError("coding result is not successful")
    return CodingResult(subtype=subtype, is_error=is_error)


def verify_install_revision(expected: str) -> None:
    """Verify the installed package was built from the requested immutable VCS revision."""
    if re.fullmatch(r"[0-9a-f]{40}", expected) is None:
        raise CodingResultError("factory runner revision is invalid")
    try:
        direct_url = metadata.distribution("factory-runner").read_text("direct_url.json")
        payload = json.loads(direct_url) if direct_url is not None else None
    except (metadata.PackageNotFoundError, json.JSONDecodeError, OSError, TypeError):
        raise CodingResultError("factory runner revision cannot be verified") from None
    if not isinstance(payload, dict):
        raise CodingResultError("factory runner revision cannot be verified")
    vcs_info = payload.get("vcs_info")
    commit_id = vcs_info.get("commit_id") if isinstance(vcs_info, dict) else None
    if not isinstance(commit_id, str) or commit_id != expected:
        raise CodingResultError("factory runner revision does not match")
