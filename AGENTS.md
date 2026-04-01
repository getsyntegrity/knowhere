# Codex Agent Guidance

## Test Writing Standards

- Write tests around real business behavior and real user or system scenarios.
- Do not write a test only because it can be made to pass.
- The test name and setup should describe the business case, failure mode, or production scenario being verified.
- Prefer tests that exercise the real code flow end to end within the unit or integration boundary under test.

## Mocking Rules

- Do not mock internal modules just to make a test easier to write.
- Only mock true external boundaries such as databases, network calls, object storage, file system operations, clocks, queues, and third-party services.
- If the codebase already uses a library that can faithfully simulate an external dependency, use that library instead of writing a custom fake.
- Avoid replacing large parts of the execution path with mocks when the real implementation is part of what the test should verify.
- Mock only what is not directly related to the scenario under test.

## Test Design

- Verify real behavior, not implementation trivia.
- Cover meaningful success, failure, edge, and regression paths when they reflect realistic production behavior.
- Prefer assertions on observable outcomes, state transitions, persisted results, emitted events, and user-visible errors.
- Keep fixtures and helpers readable and intention-revealing.
- Minimize hidden magic in test setup.

## Test Code Quality

- Treat test code as production code.
- Keep tests clear, maintainable, and refactor-friendly.
- Use descriptive names, small helpers, and explicit assertions.
- Remove duplication when it improves clarity, but do not hide the scenario behind unnecessary abstraction.
- A passing test with poor design is still a bad test.
