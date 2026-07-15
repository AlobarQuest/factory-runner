from typing import Final

CAPABILITY_VOCABULARY: Final = {
    "runner": (
        "command.run",
        "github.pr.create",
        "orchestrator.claim",
        "orchestrator.evidence.write",
        "repo.edit",
        "repo.read",
    )
}
