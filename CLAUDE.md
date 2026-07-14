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
