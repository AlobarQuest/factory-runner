# Factory Runner Instructions

## Known Non-obvious Invariants

- Finalizer verification commands must use the target repository's local tool
  environment. When `.venv/bin` exists at the repository root, it precedes the
  inherited `PATH`; other runner subprocesses keep their inherited environment.
- allowed_commands is enforced by a runner-owned exact-match PreToolUse hook;
  prompt text and bare action permissions are not the authority boundary. The
  hook must exit 2 to deny.
- GitHub step success is not coding success. Finalization requires a parsed
  terminal success result; error_max_turns is coding_action_failed even when an
  action version emits is_error:false.
- The trusted pilot allows `repo.edit` to change executable verification wrappers,
  including Makefile targets, pyproject configuration, and test code. This release
  is not hostile-agent-safe and must not be cited as proof of hardened command
  semantics.
- Typer 0.26 vendors click as `typer._click`; `click` is not an installed
  distribution here, so `import click` fails at test collection with
  `ModuleNotFoundError`. There is also no stable public group type to narrow to:
  `typer.main.get_command()` is annotated as returning `Command`, and
  `typer.core.TyperGroup` subclasses that `Command` rather than any exported
  `Group`, so `.commands` is an instance attribute pyright cannot see. Introspect
  it defensively (`getattr(group, "commands", None)`) and assert the result is
  non-empty — a future Typer that stops exposing subcommands must fail loudly
  rather than silently vet the workflow against an empty vocabulary.
- The workflow/CLI contract guard checks `.github/workflows/factory-runner.yml`
  against *this checkout's* CLI. Until WS-P2.23 that was only ONE direction —
  the workflow named a literal SHA, so the CLI it installed was a different
  revision from the checkout being vetted, and a pinned revision predating an
  option HEAD has was invisible. **The workflow now installs `job.workflow_sha`,
  its own commit**, so the CLI it installs *is* the checkout the guard vets and
  the guard is complete. `job.*` describes the workflow file defining the job
  (factory-runner) even when called from another repo; `github.*` describes the
  caller. Use `workflow_sha`, never `workflow_ref` — the ref is what the caller
  pinned, unresolved, so a branch ref appears verbatim and is mutable.
- `RunnerBrief` is `extra="allow"`; every other model here is `extra="forbid"`.
  Strict on the brief guarded only the safe case — an old runner cannot use a
  field it does not know about — while a renamed or removed field is caught by
  required-field validation regardless. What strict actually did was turn "I'll
  ignore this" into "every dispatch in the estate dies at brief-parse", which is
  what happened for a full day from 2026-07-30. Undeclared keys are reported by
  `unknown_brief_keys()` at the parse site and ride into the PR evidence payload;
  do not "simplify" either half away — tolerating silently is the same defect
  wearing the opposite coat.

<!-- code-standards:start -->
# Code Quality (code-standards layer)

Standards reference: `~/Developer/code-standards/STANDARDS.md`

## Before writing a cross-cutting pattern — query Code Brain

Before implementing a recurring cross-cutting concern (logging, error handling,
auth, notifications, API conventions, secrets, …), query **Code Brain** — the
machine source of record for our paved roads — and follow its rules:

- `get_road("<slug>")` → the decided approach + rules + exemplars, or
- `get_rules(severity="BLOCK")` → the must-follow rules.

Do **not** infer the standard from existing code; it may predate the standard.
When you decide a new cross-cutting pattern, write it back (`add_road` / `add_rule`).

## Before declaring a non-trivial change done

1. Run `make check` — full-repo lint, type-check, and tests must be green.
2. Run `/code-review` — review the diff for correctness bugs and simplification opportunities.

Both gates apply to any change that touches logic, interfaces, or configuration.
Trivial fixes (typos, comment edits) may skip `/code-review` at your discretion.

## Enforcement

A diff-scoped Stop hook enforces this automatically: it runs the linters over your
changed files when the session ends and blocks completion if new violations are
introduced. Existing baseline violations are tracked and do not block.

## Canonical example module

The authoritative pattern for this repo's style is:

the cleanest, most idiomatic existing module in this repo

When writing new code, mirror the structure, naming conventions, and documentation
style of that module.

<!-- code-standards:end -->
