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

## Durable Credential

- BWS secret UUID: `d2a4c0fc-128b-4bf5-8e25-b481010e1be0`
- GitHub secret: `FACTORY_RUNNER_TOKEN`
- GitHub secret: `FACTORY_RUNNER_CREDENTIAL_KEY_ID`
- Production Coolify env: `ORCHESTRATOR_M2M_CREDENTIALS` stores only the token hash.
- Production image with active runner registry:
  `ghcr.io/alobarquest/orchestrator:656fcef-ws41-registry`

## Pilot Repo: AlobarQuest/orchestrator

- Workflow consumer committed on a branch.
- `FACTORY_RUNNER_TOKEN` secret configured from BWS UUID
  `d2a4c0fc-128b-4bf5-8e25-b481010e1be0`.
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
