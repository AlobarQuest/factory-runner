# Factory Runner Rollout

## Credential Shape

- Actor ID: `factory-runner`
- Credential key ID: `factory-runner-github`
- Header 1: `X-Credential-Key-Id`
- Header 2: `Authorization: Bearer <token from GitHub secret>`

## Secret Rules

- Raw tokens stay only in BWS and GitHub Actions secrets.
- Values are piped from BWS to `gh secret set`.
- Values are never written to tracked files, prompts, logs, package YAML, workflow YAML, or evidence.
- Stable BWS UUIDs are recorded in `.bws-secrets.toml` after creation.

## Pilot Repo: AlobarQuest/orchestrator

- Workflow consumer committed on a branch.
- `FACTORY_RUNNER_TOKEN` secret configured from BWS.
- `FACTORY_RUNNER_CREDENTIAL_KEY_ID` secret configured as `factory-runner-github`.
- GitHub Actions permissions allow PR creation but not merge.
- Branch protection keeps Devon as the only merge actor.
- Default verification command: `make check`.

## Preflight Before Live Pilot

```bash
cd ~/Projects/factory-runner
make check
cd ~/Projects/orchestrator
make check
cd ~/Projects/project-standards
uv run portfolio foundation
cd ~/Projects/security-standards
uv run python -m security_scan.cli ~/Projects/factory-runner --category security
```
