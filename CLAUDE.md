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
  against *this checkout's* CLI, not the CLI at the SHA the workflow installs. It
  catches HEAD drifting away from what the workflow invokes — the direction that
  caused GAP-4 — but not a pinned revision predating an option HEAD has. Closing
  that direction requires installing and introspecting the pinned revision.
