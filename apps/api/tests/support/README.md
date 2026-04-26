# API Test Support

Shared support code for API contract tests lives here.

Expected responsibilities:

- deterministic test environment loading
- app bootstrap with lifespan support
- database reset and seed helpers
- fakeredis reset helpers
- request builders and data builders

Support helpers may simplify setup, but they must not replace the core runtime behavior being tested.
