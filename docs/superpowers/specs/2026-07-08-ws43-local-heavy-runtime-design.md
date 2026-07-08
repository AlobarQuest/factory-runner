# WS-4.3 Local-Heavy Runtime Design

**Status:** Approved for implementation by Devon on 2026-07-08.
**Scope:** Phase 4 WS-4.3 only. No WS-4.2 dispatch automation, WS-4.4 infra-lane linkage, Phase 5 verifier/release immutability, tracker canonicalization, brain learning/promotion, graduation automation, production deployment, or automatic merge.

## 1. Baseline

The verified baseline for this design session:

- `~/Projects/factory-runner` is clean on `main` at `dd4a6224879f74ca1901fc8b9c59645fe2383ce5` and contains the WS-4.1 merge.
- `~/Projects/orchestrator` is clean on `main` at `8cfe7b8baa08013209e30872ff1eb5c39d6cd66d` and contains the WS-4.2 dispatch adapter merge.
- `~/Projects/security-standards` is clean on `main` at `972c64a75ba07e3b8d811b13643aa0c0b803b6fc`.
- `orchestrator make check` passed with 698 tests.
- `factory-runner make check` passed with 22 tests.
- `portfolio foundation` reported `violations=0 accepted=0 unknown=0`.
- The orchestrator security scan reported `0 BLOCK`, `0 WARN`, and one judgment-only BWS least-privilege INFO.
- Production `https://sds.alobar.net/health/live` and `/health/ready` returned 200.
- Missing M2M credentials returned 401; the configured `factory-runner-github` M2M credential returned 200 without printing secret values.
- BWS access through the approved helper can fetch the existing runner credential by UUID without printing the value.

The `@RTK.md` include is not repo-local in this workspace. It resolves to `/Users/devon/.claude/RTK.md`. Future sessions should search the Claude home tree as well as the current repo before treating that include as missing.

## 2. Runtime Boundary

Local-heavy execution is the adapter for Devon's machine as a worker. It is for approved orchestrator work units that are too large, stateful, multi-repo, or context-heavy for the GitHub-hosted factory runner, while still being normal software work rather than production infrastructure mutation.

Routing criteria:

- Use the GitHub-hosted factory runner when the unit is repo-local, stateless, compatible with the reusable workflow, and can be completed inside the GitHub runner's tool and timeout limits.
- Use local-heavy execution when the unit is approved and Ready, but needs persistent local context, multiple checkouts, larger verification loops, interactive judgment during implementation, or a stateful local/cloud agent.
- Use the infra lane when the authority envelope authorizes production infrastructure mutation or existing change-manager/infraops machinery owns the execution path.

The orchestrator remains canonical lifecycle truth in all three cases. Local files, local git state, GitHub PRs, logs, issues, and tracker records are evidence or working state only.

## 3. Owning Repo Shape

WS-4.3 should extend `~/Projects/factory-runner` rather than create a new repo. The factory-runner package already owns:

- authority-envelope validation;
- an authenticated orchestrator client;
- evidence payload builders;
- PR body rendering;
- the no-merge worker contract.

The local-heavy runtime should be a thin CLI/doc layer around those pieces:

- add local-heavy commands to prepare a run workspace, renew a lease, recover an expired lease, and finalize evidence;
- add tests for command behavior and secret redaction;
- add `docs/local-heavy-runtime.md` with the operator flow and decision criteria.

Only add orchestrator code if an existing API gap blocks the flow. The current API already exposes runner brief, claim, renew, reclaim-expired-claim, lifecycle commands, and evidence submission, so the expected orchestrator changes are documentation-only at most.

## 4. Local-Heavy Flow

One local-heavy run handles exactly one work unit:

1. The operator supplies a work-unit ID, current repository, orchestrator URL, and credential key ID.
2. The CLI fetches the runner brief from `https://sds.alobar.net`.
3. The CLI validates readiness and the approved authority envelope.
4. The CLI fails closed if the unit is not Ready, the target repo does not match the current repo, capabilities are unsupported, command constraints are missing, or the envelope would grant merge/deploy/secret/infrastructure authority.
5. The CLI claims the work unit and starts execution through orchestrator APIs.
6. The CLI writes a local workspace with a sanitized brief, prompt, and run manifest.
7. The local agent works from the generated prompt and the approved repo/tool/command boundaries.
8. Long runs renew the lease explicitly through the orchestrator API.
9. Lost or stale leases are recovered only through `reclaim-expired-claim`; no private database edits are allowed.
10. The worker opens an evidence-bearing PR and submits evidence back to the orchestrator.
11. The worker transitions the unit to `submitted` after PR and verification evidence are recorded.

The local-heavy adapter does not complete work units. Completion belongs to later human/verifier paths. No local-heavy command may merge a PR.

## 5. Scope Enforcement

Authority enforcement must happen before local mutation. The adapter should reuse the existing factory-runner authority validator and add local-heavy checks only where the local runtime differs from GitHub Actions.

Minimum fail-closed checks:

- `constraints.work_unit_id` must equal the requested unit.
- `constraints.target_repository` must equal the current repository.
- unsupported capability names or levels are rejected.
- `command.run` requires a non-empty `constraints.allowed_commands` list.
- merge, release, deploy, infra mutation, tracker mutation, and secret-read capabilities are unsupported.
- evidence and lifecycle calls are made only for the claimed unit.

For multi-repo work, the first implementation should not silently broaden repository scope. If multi-repo authority is needed, it must be explicit in the authority envelope and validated as a separate extension rather than inferred from local checkout state.

## 6. Local Secrets

No new credential is required for the first WS-4.3 implementation. Reuse the existing runner M2M credential shape:

- BWS UUID: `d2a4c0fc-128b-4bf5-8e25-b481010e1be0`;
- credential key ID: `factory-runner-github`;
- request headers: `X-Credential-Key-Id` and `Authorization: Bearer <token>`.

Secret handling rules:

- source `BWS_ACCESS_TOKEN` through the approved helper or a gitignored env file;
- fetch secrets by stable UUID only;
- never write raw tokens to tracked files, prompts, logs, package YAML, evidence, PR bodies, or generated artifacts;
- keep local credential files under gitignored patterns before creating them;
- redact lease tokens and secret-like values from PR/evidence text.

If WS-4.3 later needs a distinct local-worker credential, that must be a separate registry actor and BWS secret with only UUIDs/hashes committed. That is not required for the initial local-heavy codification.

## 7. Evidence And PR Contract

Local-heavy evidence should reuse the WS-4.1 evidence conventions:

- `runner.pr.opened` for PR URL and head SHA;
- `runner.verification` for structured verification commands and exit status summaries;
- explicit `SDS-Unit:` and `SDS-Package-Rev:` trailers in commits and PR bodies;
- PR body states that the worker cannot merge.

The local-heavy flow may add a local-runtime marker in evidence payloads, but it must not create a competing lifecycle truth. Logs should be summarized, not pasted wholesale.

## 8. Tests And Verification

Focused tests should cover:

- local-heavy prepare writes only sanitized workspace files;
- renew/reclaim client calls use the orchestrator API shape without exposing tokens;
- finalize evidence redacts lease tokens and submits PR/verification evidence;
- unsupported local-heavy authority fails closed;
- generated operator docs mention no merge, no private DB edits, and BWS-only secret loading.

Final verification should run:

- `make check` in `~/Projects/factory-runner`;
- orchestrator `make check` if orchestrator files change;
- security scan in every touched repo with local runtime credential or secret-handling changes;
- `portfolio foundation`;
- production health and M2M smoke if the local-heavy docs or code rely on `https://sds.alobar.net`.
