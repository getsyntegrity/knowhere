# Shared Component Tests

This directory is for narrow tests that still provide value without claiming full end-to-end coverage.

Good fits:

- pure logic
- deterministic transformations
- adapter behavior with a very small boundary

Bad fits:

- HTTP contract tests
- worker task contract tests
- tests that simulate full application behavior with deep mocks
