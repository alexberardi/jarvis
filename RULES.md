# Jarvis Development Rules

Rules and guidelines for working on the Jarvis codebase.

## Working Style: Be a Scalpel, Not a Hammer

- **Ask questions early** - When stuck or uncertain, ask the user rather than repeatedly trying the same approach
- **Don't bang head against wall** - If something fails 2-3 times, step back and involve the user
- **User prefers questions** - The user would rather answer a clarifying question than watch you spin wheels
- **Precision over persistence** - One well-aimed question beats five failed attempts

## Coding Style

- **Imports at the top** - Always put Python imports at the top of the file unless absolutely necessary to place elsewhere
- **Always use type hints** - Every function parameter, return type, and variable should have explicit types. No ambiguous `def foo(x, y):` - use `def foo(x: str, y: int) -> bool:`. Be clear about what's coming in and going out.

## Test-Driven Development (TDD)

**Always use TDD** - Write tests first, then implement. This is mandatory.

1. **RED** - Write a failing test that defines the expected behavior
2. **GREEN** - Write the minimum code to make the test pass
3. **REFACTOR** - Clean up the code while keeping tests green

Why this matters:
- Tests document expected behavior before implementation
- Prevents over-engineering (only write code needed to pass tests)
- Catches regressions immediately
- Forces clear interface design upfront

TDD workflow for new features:
```bash
# 1. Write tests first
# 2. Run tests (should fail)
pytest tests/test_new_feature.py -v

# 3. Implement minimal code to pass
# 4. Run tests again (should pass)
pytest tests/test_new_feature.py -v

# 5. Refactor if needed, tests should still pass
```

## Performance Targets

- **Total voice interaction latency**: <5 seconds end-to-end
  - Whisper transcription (speech-to-text)
  - Date context extraction
  - Command inference (tool routing)
  - Command execution and response
- **Date key extraction accuracy**: 100% on validation suite
