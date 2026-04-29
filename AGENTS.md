# Repository Instructions

## Branch Naming

Codex agents and contributors must create branches with this format:

```text
<type>/<user>/<description>
```

- `type` should be lowercase and should normally be one of:
  `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`, `ci`, `build`,
  or `revert`.
- `user` should identify the human owner of the work, usually their GitHub
  username. Do not use a generic tool name such as `codex`.
- `description` should be short, lowercase, and kebab-case.

Examples:

```text
feat/alice/add-document-preview
fix/bob/chunk-position-range
refactor/chris/extract-chunk-converter
```
