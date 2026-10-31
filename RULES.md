# Jarvis development rules

Shared practices for the Jarvis repos. Start with [AGENTS.md](AGENTS.md) to find
the owning checkout; its scoped instructions define implementation details,
required checks and merge policy.

## Working style

- Make focused changes that solve the requested problem. Preserve unrelated
  edits, worktrees and running services.
- Read the implementation and nearby tests before changing behavior. Use
  existing patterns and utilities before introducing another abstraction.
- Resolve routine choices from the repo and the user's instructions. Ask a
  specific question when missing information materially changes the outcome;
  do not repeatedly retry an approach without new evidence.
- Keep the user informed of findings, assumptions and blockers. Finish with
  what changed, what was verified and any remaining limits.

## Coding conventions

- Match the language and conventions of the owning repo. New server features
  normally extend jarvisd's Go modules; a new capability does not imply a new
  service.
- **Go:** format with `gofmt`, propagate context and errors, and use the existing
  platform helpers for storage, settings, auth and structured logging.
  Server logging uses `slog` and `internal/platform/logging`.
- **TypeScript/React:** follow the app's types, components, state and theme
  patterns. Read its UI-specific guide before changing screens.
- **Python:** keep imports at the top, grouped stdlib → third-party → local,
  except where a necessary deferred import is explained. Use explicit type
  hints for parameters, returns and variables; prefer `X | None` where the
  supported Python version allows it.
- Keep runtime settings in the owning system's settings mechanism. Use its
  documented environment/configuration inputs for secrets and bootstrap.
  Legacy Python settings/logging clients are not dependencies of jarvisd.
- Preserve household/user isolation and API, MQTT and SDK contracts. Coordinate
  changes with affected clients and follow the repo's authorization review gates.

## Tests and verification

**TDD is required for new behavior and bug fixes:** write a test that fails for
the intended reason, implement the smallest correct change, then refactor while
keeping it green.

- Start with focused tests, then run the owning repo's required checks before
  committing. Use its actual runner: Go tests, Vitest, Jest or pytest.
- Target at least 80% coverage and retain stricter repo-specific gates. Coverage
  is a target, not proof: test observable behavior, failure paths and boundaries.
- Do not skip tests, weaken assertions or lower quality gates to make a change
  pass. Report missing dependencies and existing failures explicitly.
- For wire-compatibility work, use the relevant contract tests and golden
  fixtures. For UI or integration behavior, use the appropriate runtime harness
  as well as unit tests.
- Verify documentation-only changes by checking commands, paths, links and
  consistency against source. Do not manufacture runtime tests for prose edits.
- Record the checks actually run and their outcomes. Do not claim a full suite,
  live hardware test or production validation from a narrower check.

## Performance targets

- Preserve the voice interaction target of **under 5 seconds end-to-end**,
  including transcription, context/date handling, routing and execution.
- Preserve **100% date-key extraction accuracy on the validation suite**.
- For performance-sensitive changes, compare relevant benchmarks on the same
  hardware/model/configuration and report the measurement conditions. Do not
  weaken these targets or the validation corpus to conceal a regression.

## Documentation

Update guidance when a change invalidates it. Keep durable decisions in the
owning repo's decision records and current work in its status/plan files;
commit messages and PRs carry the change history. Avoid duplicating release
numbers, machine-specific values or detailed subsystem instructions across repos.
