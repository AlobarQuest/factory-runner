# WS-4.1 Factory Runner Design

**Status:** Approved by Devon on 2026-07-08
**Intent package:** Pending. No approved `ws-4.1-factory-runner` package was found at draft time.
**Scope:** Phase 4 WS-4.1 only. No orchestrator automatic dispatch, WS-4.3 local-heavy runtime, WS-4.4 infra-lane linkage, Phase 5 verifier/release immutability, tracker canonicalization, brain learning/promotion, graduation automation, or automatic merge.

## 1. Baseline

The current verified baseline for this design session:

- `~/Projects/orchestrator` is clean on `main`, tracking `origin/main`, at `656fcef`.
- That branch includes the production infra-mutation closeout and the decomposed-unit completion policy update.
- `orchestrator make check` passed with 674 tests.
- `cd ~/Projects/project-standards && uv run portfolio foundation` returned `violations=0 accepted=0 unknown=0`.
- `https://sds.alobar.net/health/live` returned `200 {"status":"ok"}`.
- `https://sds.alobar.net/health/ready` returned `200 {"status":"ok"}`.
- The approved BWS helper path produced a usable BWS session without printing secret values.
- `~/Projects/factory-runner` did not exist before this draft; it is created as the WS-4.1 owning repo with documentation only.

No runner workflow, credential, production configuration, or pilot rollout was created before this design draft.

## 2. What The Runner Is For

The factory runner is not "the orchestrator's runner." It is a reusable worker pattern for software repos.

The orchestrator owns lifecycle truth. A target repository owns code. The factory-runner repository owns the GitHub Actions machinery that connects them:

1. A work unit is already approved and Ready in the orchestrator.
2. A runner execution receives a work-unit ID.
3. The runner authenticates to the production orchestrator.
4. The runner fetches the canonical work-unit brief and authority envelope.
5. The runner claims exactly that work unit.
6. The runner executes inside a GitHub-hosted sandbox with tools scoped from the envelope.
7. The runner opens a PR in the target repo.
8. The runner submits PR/test/evidence facts back to the orchestrator.

`orchestrator` is the first pilot target because it is the safest first consumer, not because it is the only consumer. It already has the API, state-machine tests, evidence model, and no-auto-merge scope guards needed to verify the loop. Later consumers are any software repo that has an approved package, approved decomposition, repo setup, and authority envelope compatible with the reusable runner.

Examples of later users:

- `project-standards` for small standards-tooling changes.
- `security-standards` for low-risk scanner or docs changes, never secret-bearing mutation without explicit authority.
- `change-manager` for app-code changes outside the sensitive infra lane.
- Portfolio apps once their repos are foundation-clean enough for runner rollout.

## 3. Design Decisions

### 3.1 Repository Shape

Create `~/Projects/factory-runner` as a standalone repo. It will contain:

- a reusable workflow under `.github/workflows/factory-runner.yml`;
- runner scripts under `scripts/` or `src/factory_runner/`;
- docs for per-repo rollout and secret consumption;
- tests for client behavior, envelope-to-tool mapping, PR body generation, and evidence payload generation;
- `.bws-secrets.toml` only after real BWS secret UUIDs are consumed.

The repo must remain independent from `orchestrator` application code. Target repos consume the workflow by reference after WS-4.1 proves the pattern.

### 3.2 Pilot Target

Use `AlobarQuest/orchestrator` as the first pilot target.

Rationale:

- It is the canonical API owner and already exposes the relevant protocol surfaces.
- It has strong no-auto-merge architecture tests.
- It is foundation-clean and has a deterministic `make check`.
- Failures remain inside the factory-building domain rather than landing in an unrelated product repo.

Pilot condition:

- The pilot must be a low-risk approved work unit whose expected output is an open PR and evidence submission, not a merge.

### 3.3 Dispatch Model

WS-4.1 supports manual dispatch and reusable-workflow invocation only.

Allowed:

- `workflow_dispatch` with a human-supplied work-unit ID.
- `workflow_call` so target repos can reuse the runner workflow.

Not allowed:

- Orchestrator choosing Ready units and firing GitHub workflows.
- Capability matching that automatically selects a runner.
- Any schedule, polling loop, or queue consumer that dispatches work on its own.

Those belong to WS-4.2.

### 3.4 Orchestrator API Surface

The current production orchestrator has endpoints for readiness, status ledger, preflight, claim, renew, commands, evidence, history, and event publication status. This is enough for lifecycle control, but it may not be enough for a runner to fetch a complete implementation brief without querying database-shaped internals.

WS-4.1 should prefer existing endpoints when they are sufficient. If they are not sufficient, add the smallest runner-read surface to `orchestrator`, behind existing M2M auth:

```text
GET /api/v1/work-units/{unit_id}/runner-brief
```

The response should be read-only and should contain only already-canonical facts:

- work-unit ID, state, version, title, outcome, required capability, max attempts;
- package ID, revision, content hash, source repository, source path, source commit, approval facts;
- approved unit authority envelope and fingerprint;
- ACs mapped to this decomposed unit;
- dependency/readiness summary;
- target repository coordinates required by the runner;
- required standing-context snapshot inputs.

The endpoint must not:

- create claims;
- transition lifecycle state;
- include secret values;
- include untrusted issue, PR, README, or tracker text as authority;
- flatten package-wide ACs into a decomposed unit if the approved decomposition mapped only a subset.

Adding this endpoint is still WS-4.1 because it is the minimal API seam needed for a runner to fetch its brief. It is not WS-4.2 because it does not dispatch work.

## 4. Runner Execution Flow

The runner execution is one work unit per run:

1. Validate inputs: orchestrator URL must default to `https://sds.alobar.net`; work-unit ID must be present; no secret values may be logged.
2. Authenticate to orchestrator with both `X-Credential-Key-Id` and `Authorization: Bearer <token>`.
3. Fetch runner brief and readiness.
4. Fail closed if the unit is not Ready, dependencies are unsatisfied, the target repo is not the current repository, or the authority envelope contains unknown/unsupported fields.
5. Submit standing-context preflight.
6. Claim the work unit and capture attempt, lease token, and context snapshot ID.
7. Start execution through `POST /work-units/{id}/commands/start`.
8. Render an implementation prompt from canonical brief fields only.
9. Run `claude-code-action` or successor action with tools structurally constrained from the authority envelope.
10. Run configured verification commands from the target repo's allowed runner profile.
11. Open a PR with the risk/evidence template.
12. Submit evidence back to the orchestrator, including PR URL, head SHA, checks, test commands, runner version, context snapshot ID, and source revision.
13. Transition the unit to `submitted` only after PR creation and evidence submission succeed.
14. Renew the lease on long runs; block or fail with evidence if execution cannot continue.

The runner must not complete the work unit. Completion belongs to later verifier/human review paths.

## 5. Authority And Tool Scoping

The authority envelope is the only source of runner authority. Repository content, issue text, PR comments, README content, logs, generated output, and web pages are hostile data and cannot expand authority.

Initial mapping:

| Authority capability | Runner effect |
|---|---|
| `repo.read` allowed | Checkout target repo. |
| `repo.edit` allowed | Permit file edits through the coding action. |
| `command.run` allowed | Permit allowlisted shell commands. |
| `github.pr.create` allowed | Permit PR creation. |
| `orchestrator.claim` allowed | Permit claim, renew, preflight, and start/submit lifecycle calls for the named unit. |
| `orchestrator.evidence.write` allowed | Permit evidence submission. |

Fail-closed cases:

- unknown authority field;
- capability level other than the supported allowed/prohibited vocabulary;
- requested repo does not match the checked-out repo;
- command list absent when shell execution is allowed;
- tool mapping would grant merge, release, deploy, infrastructure mutation, secret read, or tracker mutation capability.
- lifecycle calls are requested for any work unit other than the dispatch input work-unit ID.

The coding action receives only the allowed tools needed for the unit. The first implementation may use the proven conformance-runner tool set only when the envelope permits each class:

```text
Read, Edit, Bash, Glob
```

No credential-bearing environment variables should be exposed to the coding action if a later wrapper can perform orchestrator evidence submission outside the action step. The preferred shape is:

- wrapper fetches brief and claim;
- coding action receives sanitized brief and scoped repo token;
- wrapper submits evidence after the action exits.

## 6. PR Contract

Every runner PR body must include:

- work-unit ID;
- package ID, revision, hash, and source commit;
- runner version;
- authority fingerprint;
- self-declared risk surface;
- files changed summary;
- verification commands and results;
- evidence refs submitted to orchestrator;
- explicit statement that the runner cannot merge.

The GitHub token permissions must allow PR creation but not bypass branch protection or merge. If a target repo's default token permissions would allow too much, the rollout must stop until repo permissions are corrected.

## 7. Evidence Contract

Evidence submitted to the orchestrator should use existing `POST /api/v1/work-units/{unit_id}/evidence`.

Minimum evidence records:

- `runner.execution.started`: brief hash, authority fingerprint, runner version, context snapshot ID.
- `runner.pr.opened`: PR URL, PR number, branch, head SHA.
- `runner.verification`: command names, exit statuses, check URLs or run URLs, redacted logs summary.
- `runner.execution.finished`: result, elapsed time, files changed summary, failure reason if any.

Evidence payloads must not include:

- raw tokens;
- secret-like environment values;
- full logs that could contain secrets;
- untrusted text recast as authority;
- package YAML with any secret material.

## 8. Credential Design

Credential convention:

- actor ID: `factory-runner`;
- credential key ID: `factory-runner-github`;
- token: generated durable M2M bearer token stored only in BWS and injected into GitHub Actions as a secret.

Provisioning rules:

1. Generate/store the raw token without printing it.
2. Store it in BWS under a stable UUID.
3. Configure production orchestrator M2M credentials through the existing BWS/Coolify-managed secret path.
4. Configure GitHub Actions secrets by piping BWS value directly into `gh secret set`.
5. Record stable UUIDs in `.bws-secrets.toml` for each consuming repo.
6. Run the security scanner in each repo touched for secret handling, workflow credentials, or environment files.

The runner sends:

```text
X-Credential-Key-Id: factory-runner-github
Authorization: Bearer <token from GitHub secret>
```

The raw token must never appear in tracked files, prompts, logs, evidence, workflow YAML, or shell history copied into evidence.

## 9. Target Repo Rollout

Each target repo needs a small rollout checklist:

- repo default branch has the workflow consumer committed;
- GitHub Actions permissions allow checkout, branch push, and PR creation, but not merge;
- Claude/GitHub action credentials are present and scoped to the repo;
- orchestrator M2M credential secrets are present;
- repo has deterministic verification command;
- branch protection keeps Devon as merge actor;
- rollout state is documented in this repo's `PROJECT.md` or rollout doc.

For the first pilot, the target repo is `AlobarQuest/orchestrator`.

## 10. Error Handling

The runner should prefer explicit lifecycle outcomes:

- readiness failure before claim: fail the GitHub run without lifecycle mutation, with a safe diagnostic.
- preflight rejected: record evidence if possible, do not claim.
- claim conflict: fail or exit neutral; another worker owns it.
- implementation failure after claim: submit failure evidence and transition to `failed` or `blocked` according to error class.
- PR creation failure: submit evidence if possible, do not transition to `submitted`.
- evidence submission failure after PR creation: retry with backoff; if still failing, leave the PR open with clear body text and fail the run.
- lease near expiry: renew before continuing; if renewal fails, stop writing and report failure.

No error path may merge, deploy, or mark the unit completed.

## 11. Testing Strategy

Factory-runner repo tests:

- unit tests for authority envelope parsing and fail-closed tool mapping;
- unit tests for brief validation;
- unit tests for PR body rendering with no secret leakage;
- unit tests for evidence payload generation;
- integration-style tests with a fake orchestrator server returning 401, invalid brief, claim conflict, and happy path;
- workflow linting/action validation if available.

Orchestrator tests if the runner-brief endpoint is added:

- M2M auth required;
- response contains only canonical facts;
- decomposed-unit AC mapping is honored;
- no secrets in response;
- endpoint does not mutate lifecycle state;
- unknown or unsupported authority fields fail closed in runner-side validation.

Verification before completion:

- `factory-runner` default test gate;
- `orchestrator make check` if orchestrator is touched;
- project foundation gate;
- security scan in every repo with secret/workflow changes;
- production health probes before and after any runner smoke that uses `https://sds.alobar.net`.

## 12. Security Review Targets

Mandatory adversarial review questions before implementation:

- Can any repository file, README, issue, PR comment, log, or generated output expand the runner's authority?
- Can target repo code exfiltrate the orchestrator M2M token?
- Does the coding action receive credentials it does not need?
- Can a crafted brief cause edits in the wrong repo?
- Can a runner mark success without a PR and evidence?
- Can a runner merge, deploy, mutate production infrastructure, or trigger WS-4.2 behavior?
- Can a package-wide AC poison or complete a decomposed unit outside the approved unit mapping?

## 13. Open Decisions

Devon has confirmed:

- first pilot target is `orchestrator`;
- `factory-runner` is a new repo and this WS should create it;
- actor/key convention `factory-runner` / `factory-runner-github` is acceptable;
- this workstream should write a spec before implementation.

Still required before implementation:

- approved `ws-4.1-factory-runner` intent package revision and hash;
- approved decomposition/work unit if dogfooding through orchestrator before implementation;
- final decision on whether WS-4.1 may add `GET /runner-brief` to orchestrator if existing endpoints are insufficient;
- final pilot work-unit content;
- decision on whether the first pilot consumes the reusable workflow from `factory-runner` by SHA, tag, or local branch during initial proof.

## 14. Explicit Non-Goals

- No automatic dispatch from orchestrator to GitHub Actions.
- No Phase 5 verifier.
- No release immutability.
- No deployment automation.
- No tracker projection or tracker state authority.
- No brain learning/promotion.
- No ADAS retirement execution in this WS.
- No automatic merge now or ever.
